#include "Commands.hpp"
#include "Projection.hpp"
#include "Support.hpp"

#include <cmath>

namespace Loriini {

namespace {

// The twelve numbers of a transformation matrix, in the order the header
// gives them. Reported raw and unrearranged on purpose: the whole reason
// `GetProjection` exists is to compare Archicad's own matrix against the one
// `Projection.cpp` builds, and a tidied-up version would hide exactly the
// disagreement that comparison is looking for.
GS::ObjectState MatrixState (const API_Tranmat& matrix)
{
	GS::Array<double> numbers;
	for (short index = 0; index < 12; ++index) {
		numbers.Push (matrix.tmx[index]);
	}
	GS::ObjectState state;
	state.Add ("tmx", numbers);
	return state;
}


GS::ObjectState SunState (const API_SunAngleSettings& sun)
{
	GS::ObjectState state;
	state.Add ("azimuth", sun.sunAzimuth);
	state.Add ("altitude", sun.sunAltitude);
	state.Add ("givenByDate", sun.sunPosOpt == API_SunPosition_GivenByDate);
	state.Add ("year", static_cast<Int32> (sun.year));
	state.Add ("month", static_cast<Int32> (sun.month));
	state.Add ("day", static_cast<Int32> (sun.day));
	state.Add ("hour", static_cast<Int32> (sun.hour));
	state.Add ("minute", static_cast<Int32> (sun.minute));
	state.Add ("second", static_cast<Int32> (sun.second));
	state.Add ("summerTime", sun.summerTime);
	return state;
}


// Fills a sun setting from the caller's date, leaving anything unnamed as it
// already was.
//
// Partial on purpose. A caller changing only the hour across seven runs
// should not have to restate the year each time, and a caller who states
// nothing should get the sun the project already had rather than midnight on
// the first of January.
void ApplySun (const GS::ObjectState& date, API_SunAngleSettings& sun)
{
	Int32 value = 0;
	bool flag = false;

	if (date.Get ("year", value))		sun.year = static_cast<unsigned short> (value);
	if (date.Get ("month", value))		sun.month = static_cast<unsigned short> (value);
	if (date.Get ("day", value))		sun.day = static_cast<unsigned short> (value);
	if (date.Get ("hour", value))		sun.hour = static_cast<unsigned short> (value);
	if (date.Get ("minute", value))		sun.minute = static_cast<unsigned short> (value);
	if (date.Get ("second", value))		sun.second = static_cast<unsigned short> (value);
	if (date.Get ("summerTime", flag))	sun.summerTime = flag;

	// Given a date at all, the sun is computed from it. Stated explicitly
	// rather than assumed: a project whose sun was last set by dragging the
	// angle sliders is sitting on `API_SunPosition_GivenByAngles`, and
	// writing a date into it without switching the option changes the numbers
	// in the dialog and nothing in the drawing.
	sun.sunPosOpt = API_SunPosition_GivenByDate;
}


// Points a parallel projection at `from`, filling every field Archicad reads.
//
// Three fields, not one. The matrix is what the 3D window draws from, but the
// dialog shows `azimuth` and the preset named by `projMod`, and a matrix
// written under a preset that disagrees with it is at best confusing. Free
// Axonometry is the preset whose matrix is its own, and Archicad's `azimuth`
// is degrees anticlockwise from the project's +X axis -- read off a live
// project, where a camera bearing of 83.372 came back as 6.628.
void Aim (const Direction& from, API_AxonoPars& axono)
{
	axono.projMod = API_Projection_FreeAx;
	axono.azimuth = std::fmod (90.0 - from.azimuthDegrees + 360.0, 360.0);
	axono.tranmat = ViewMatrix (from);
	axono.invtranmat = InverseViewMatrix (from);
}


// Aims a 3D Document's projection and sets its sun, from the parameters
// SetProjection takes, either or both. Returns whether it found anything to
// change.
//
// A document made while the 3D window was in perspective carries perspective
// numbers in the union, so its sun is lifted out before the parallel half is
// written -- the same care SetProjection takes with the window.
bool AimDocument (const GS::ObjectState& parameters, API_3DProjectionInfo& projection)
{
	double azimuth = 0.0;
	double altitude = 0.0;
	const bool hasDirection = parameters.Get ("viewAzimuth", azimuth) &&
							  parameters.Get ("viewAltitude", altitude);
	if (hasDirection) {
		if (projection.isPersp) {
			const API_SunAngleSettings sun = projection.u.persp.sunAngSets;
			projection.u.axono = {};
			projection.u.axono.sunAngSets = sun;
		}
		projection.isPersp = false;
		const Direction from = { azimuth, altitude };
		Aim (from, projection.u.axono);
	}

	GS::ObjectState date;
	const bool hasSun = parameters.Get ("sun", date);
	if (hasSun) {
		ApplySun (date, projection.isPersp ? projection.u.persp.sunAngSets : projection.u.axono.sunAngSets);
	}
	return hasDirection || hasSun;
}


// The fill a document's vectorial sun shadows are drawn in, from
// `{"fillIndex", "fillPen", "backgroundPen", "contourPen"}`, each optional.
// These four are the "Sun Shadows" group of the document's Model Display.
void ApplyShadowFill (const GS::ObjectState& fill, API_UniformAttributeOptions& options)
{
	Int32 index = 0;
	if (ReadInt (fill, "fillIndex", index)) {
		options.shadFill = static_cast<API_AttributeIndex> (index);
	}
	ReadShort (fill, "fillPen", options.shadFillPen);
	ReadShort (fill, "backgroundPen", options.shadFillBkgPen);
	ReadShort (fill, "contourPen", options.shadContPen);
}


GS::ObjectState ShadowFillState (const API_UniformAttributeOptions& options)
{
	GS::ObjectState state;
	state.Add ("fillIndex", static_cast<Int32> (options.shadFill));
	state.Add ("fillPen", static_cast<Int32> (options.shadFillPen));
	state.Add ("backgroundPen", static_cast<Int32> (options.shadFillBkgPen));
	state.Add ("contourPen", static_cast<Int32> (options.shadContPen));
	return state;
}


// A document's settings as they now are, read back rather than assumed.
//
// `effects3D` is Archicad's own word for the document's vectorial effects --
// its sun shadows among them -- and the kit says of it only "Effects to
// apply". Which bit is which is not written down anywhere, so the number is
// reported whole: a caller compares a document made with shadows against one
// made without, and can copy the value from one to the other.
GS::ObjectState DocumentState (API_DatabaseUnId document)
{
	API_DocumentFrom3DType now = {};
	const GSErrCode err = ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, &document, &now);
	GS::ObjectState result = Succeeded ();
	if (err != NoError) {
		return result;
	}
	result.Add ("effects3D", static_cast<Int32> (now.effects3D));
	result.Add ("shadowFill", ShadowFillState (now.attributeOptions));
	result.Add ("isPerspective", now.projectionSetting.isPersp);
	// The settings read back carry a handle the kit's own example frees
	// after use; nothing here owns it.
	BMhFree (reinterpret_cast<GSHandle> (now.cutSetting.shapes));
	now.cutSetting.shapes = nullptr;
	return result;
}


}		// namespace


// -- GetProjection ----------------------------------------------------------

GS::String GetProjectionCommand::GetName () const			{ return "GetProjection"; }

GS::Optional<GS::UniString> GetProjectionCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetProjectionCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"isPerspective": { "type": "boolean" },
			"azimuth": { "type": "number", "description": "Archicad's own camera azimuth, exactly as reported: degrees anticlockwise from the project's +X axis, so 90 minus the bearing." },
			"projectionMode": { "type": "integer", "description": "API_AxonoPars::projMod, the preset selected in the 3D Projection Settings dialog." },
			"transformation": { "type": "object", "properties": { "tmx": { "type": "array", "items": { "type": "number" } } } },
			"inverseTransformation": { "type": "object", "properties": { "tmx": { "type": "array", "items": { "type": "number" } } } },
			"sun": { "type": "object" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetProjectionCommand::Execute (const GS::ObjectState& /*parameters*/,
											   GS::ProcessControl& /*processControl*/) const
{
	API_3DProjectionInfo info = {};
	const GSErrCode err = ACAPI_Environment (APIEnv_Get3DProjectionSetsID, &info);
	if (err != NoError) {
		return Failed ("Failed to read the 3D projection settings.", err);
	}

	GS::ObjectState result;
	result.Add ("success", true);
	result.Add ("isPerspective", info.isPersp);

	if (info.isPersp) {
		// Reported, but not the case this add-on is for. A sun eye view is a
		// parallel projection: a perspective one puts the near corner of the
		// site at a different scale from the far one, and an assessor
		// measuring off the drawing would be measuring nothing.
		result.Add ("azimuth", info.u.persp.azimuth);
		result.Add ("sun", SunState (info.u.persp.sunAngSets));
	} else {
		result.Add ("azimuth", info.u.axono.azimuth);
		result.Add ("projectionMode", static_cast<Int32> (info.u.axono.projMod));
		result.Add ("transformation", MatrixState (info.u.axono.tranmat));
		result.Add ("inverseTransformation", MatrixState (info.u.axono.invtranmat));
		result.Add ("sun", SunState (info.u.axono.sunAngSets));
	}

	return result;
}


// -- SetProjection ----------------------------------------------------------

GS::String SetProjectionCommand::GetName () const			{ return "SetProjection"; }

GS::Optional<GS::UniString> SetProjectionCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"viewAzimuth": {
				"type": "number",
				"description": "Where the camera stands, in degrees clockwise from the project's own +Y axis -- the project frame, not true north. For a sun eye view this is the sun's bearing turned by the project's north angle."
			},
			"viewAltitude": {
				"type": "number",
				"description": "How high the camera stands, in degrees above the horizon. For a sun eye view this is the sun's own altitude."
			},
			"sun": {
				"type": "object",
				"description": "The date and time Archicad computes its own sun from. Any field left out keeps the value the project already had.",
				"properties": {
					"year": { "type": "integer" },
					"month": { "type": "integer" },
					"day": { "type": "integer" },
					"hour": { "type": "integer" },
					"minute": { "type": "integer" },
					"second": { "type": "integer" },
					"summerTime": { "type": "boolean" }
				},
				"additionalProperties": false
			}
		},
		"required": [ "viewAzimuth", "viewAltitude" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> SetProjectionCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"transformation": { "type": "object" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState SetProjectionCommand::Execute (const GS::ObjectState& parameters,
											   GS::ProcessControl& /*processControl*/) const
{
	double azimuth = 0.0;
	double altitude = 0.0;
	if (!parameters.Get ("viewAzimuth", azimuth) || !parameters.Get ("viewAltitude", altitude)) {
		return Failed ("viewAzimuth and viewAltitude are both required, in degrees.", APIERR_BADPARS);
	}

	// Read first, then change. The struct carries a great deal this command
	// has no opinion about -- the camera set it belongs to, the projection
	// preset, the sun option -- and building one from zero would silently
	// reset every one of them.
	API_3DProjectionInfo info = {};
	GSErrCode err = ACAPI_Environment (APIEnv_Get3DProjectionSetsID, &info);
	if (err != NoError) {
		return Failed ("Failed to read the 3D projection settings before changing them.", err);
	}

	const bool wasPerspective = info.isPersp;
	info.isPersp = false;

	// Coming from a perspective view there is no axonometric half to inherit,
	// so the union holds perspective numbers reinterpreted as parallel ones.
	// Cleared rather than trusted.
	if (wasPerspective) {
		const API_SunAngleSettings sun = info.u.persp.sunAngSets;
		info.u.axono = {};
		info.u.axono.sunAngSets = sun;
	}

	const Direction from = { azimuth, altitude };
	Aim (from, info.u.axono);

	GS::ObjectState date;
	if (parameters.Get ("sun", date)) {
		ApplySun (date, info.u.axono.sunAngSets);
	}

	// No second parameter. The header's note on it reads "switch only axono
	// or persp", which the first build took to mean "touch only the
	// axonometric half". It means the opposite: with it set, Archicad reads
	// `isPersp` and ignores every other field, and the call reports success
	// having changed nothing. Measured on a live project, the matrix read
	// back after the call was the one from before it.
	err = ACAPI_Environment (APIEnv_Change3DProjectionSetsID, &info);
	if (err != NoError) {
		return Failed ("Failed to change the 3D projection settings.", err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("transformation", MatrixState (info.u.axono.tranmat));
	return result;
}


// -- CreateDocumentFrom3D ---------------------------------------------------

GS::String CreateDocumentFrom3DCommand::GetName () const		{ return "CreateDocumentFrom3D"; }

GS::Optional<GS::UniString> CreateDocumentFrom3DCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"name": { "type": "string", "description": "The 3D Document's name in the Project Map." },
			"referenceId": { "type": "string", "description": "Its reference string, the sheet-style ID shown beside the name." },
			"viewAzimuth": { "type": "number", "description": "Where the camera stands, in degrees clockwise from the project's own +Y axis, as for SetProjection." },
			"viewAltitude": { "type": "number", "description": "How high the camera stands, in degrees above the horizon." },
			"sun": { "type": "object", "description": "The date and time this document keeps its sun at." },
			"sunShadows": { "type": "boolean", "description": "Make the document with Archicad's vectorial sun shadows on (or off). The 3D Document defaults are switched for this one document and put back." },
			"shadowContours": { "type": "boolean", "description": "With sunShadows, whether the shadows carry contour lines. Off by default." },
			"shadowFill": {
				"type": "object",
				"description": "The fill the sun shadows are drawn in. Any field left out keeps what the project had.",
				"properties": {
					"fillIndex": { "type": "integer", "description": "The fill type's attribute index." },
					"fillPen": { "type": "integer" },
					"backgroundPen": { "type": "integer" },
					"contourPen": { "type": "integer" }
				},
				"additionalProperties": false
			}
		},
		"required": [ "name" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> CreateDocumentFrom3DCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"databaseId": { "type": "object", "properties": { "guid": { "type": "string" } } },
			"sunShadows": { "type": "boolean", "description": "The defaults' vectorial sun shadow setting the document was made under, when one was asked for." },
			"effects3D": { "type": "integer", "description": "The document's vectorial effects flags, read back. Undocumented bits; reported whole." },
			"shadowFill": { "type": "object" },
			"isPerspective": { "type": "boolean" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState CreateDocumentFrom3DCommand::Execute (const GS::ObjectState& parameters,
													  GS::ProcessControl& /*processControl*/) const
{
	GS::UniString name;
	if (!parameters.Get ("name", name) || name.IsEmpty ()) {
		return Failed ("A 3D Document needs a name.", APIERR_BADPARS);
	}

	GS::UniString referenceId;
	parameters.Get ("referenceId", referenceId);

	API_DatabaseInfo database = {};
	database.typeID = APIWind_DocumentFrom3DID;
	CopyName (name, database.name);
	if (!referenceId.IsEmpty ()) {
		CopyName (referenceId, database.ref);
	}

	// The sun shadows, which a document takes from the 3D Document defaults
	// when it is made. `API_DocumentFrom3DDefaults::vectSunShadow` is the
	// "Vectorial Sun Shadows" of a new document's Model Display, and
	// `contureOff` their contours; the existing document's own switch lives in
	// `effects3D`, whose bits the kit does not document. So the defaults are
	// set for this one creation and put back straight after, whatever
	// happened -- the next document a person makes by hand is theirs.
	bool sunShadows = false;
	const bool askedShadows = parameters.Get ("sunShadows", sunShadows);
	bool shadowContours = false;
	parameters.Get ("shadowContours", shadowContours);
	GS::ObjectState shadowFill;
	const bool hasShadowFill = parameters.Get ("shadowFill", shadowFill);

	API_DocumentFrom3DDefaults before = {};
	bool defaultsChanged = false;
	GSErrCode err = NoError;
	if (askedShadows || hasShadowFill) {
		err = ACAPI_Environment (APIEnv_GetDocumentFrom3DDefaultsID, &before);
		if (err != NoError) {
			return Failed ("Could not read the 3D Document defaults to set the sun shadows.", err);
		}
		API_DocumentFrom3DDefaults wanted = before;
		if (askedShadows) {
			wanted.vectSunShadow = sunShadows;
			wanted.contureOff = !shadowContours;
		}
		if (hasShadowFill) {
			ApplyShadowFill (shadowFill, wanted.attributeOptions);
		}
		err = ACAPI_Environment (APIEnv_ChangeDocumentFrom3DDefaultsID, &wanted);
		if (err != NoError) {
			return Failed ("Could not set the 3D Document defaults for the sun shadows.", err);
		}
		defaultsChanged = true;
	}

	// Not inside an undo scope, and that is not a choice. The kit documents
	// `APIDb_NewDatabaseID` as a non-undoable data structure modifier that
	// answers APIERR_REFUSEDCMD from inside one, which is what the first live
	// run got back (-2130312312) when this was wrapped in
	// ACAPI_CallUndoableCommand. So a document this makes is deleted the way
	// any other is: by hand, in the Navigator. The name it is given is what
	// makes that bearable.
	err = ACAPI_Database (APIDb_NewDatabaseID, &database);
	if (defaultsChanged) {
		ACAPI_Environment (APIEnv_ChangeDocumentFrom3DDefaultsID, &before);
	}
	if (err != NoError) {
		return Failed ("Failed to create the 3D Document.", err);
	}

	// The projection is set afterwards, on the document that now exists. It
	// is the half that matters: a 3D Document created and left alone borrows
	// whatever the 3D window happened to show, so seven of them made in a row
	// would all be the same hour. The shadow fill is written again here as
	// well, on the document itself, in case the defaults were not what it
	// was made from.
	{
		API_DocumentFrom3DType settings = {};
		err = ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, &database.databaseUnId, &settings);
		if (err != NoError) {
			return Failed ("The 3D Document was created but its settings could not be read.", err);
		}

		const bool aimed = AimDocument (parameters, settings.projectionSetting);
		if (hasShadowFill) {
			ApplyShadowFill (shadowFill, settings.attributeOptions);
		}
		if (aimed || hasShadowFill) {
			// Non-undoable as well, per the same documentation.
			err = ACAPI_Environment (APIEnv_ChangeDocumentFrom3DSettingsID, &database.databaseUnId, &settings);
		}

		// The settings read back carry a handle the kit's own example frees
		// after use; nothing here owns it.
		BMhFree (reinterpret_cast<GSHandle> (settings.cutSetting.shapes));
		settings.cutSetting.shapes = nullptr;

		if (err != NoError) {
			return Failed ("The 3D Document was created but its projection could not be set.", err);
		}
	}

	GS::ObjectState identifier;
	identifier.Add ("guid", APIGuidToString (database.databaseUnId.elemSetId));

	GS::ObjectState result = DocumentState (database.databaseUnId);
	result.Add ("databaseId", identifier);
	if (askedShadows) {
		result.Add ("sunShadows", sunShadows);
	}
	return result;
}


// -- SetDocumentFrom3D ------------------------------------------------------

GS::String SetDocumentFrom3DCommand::GetName () const		{ return "SetDocumentFrom3D"; }

GS::Optional<GS::UniString> SetDocumentFrom3DCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"databaseId": { "type": "object", "properties": { "guid": { "type": "string" } }, "description": "The 3D Document, as CreateDocumentFrom3D answered it." },
			"viewAzimuth": { "type": "number", "description": "Where the camera stands, in degrees clockwise from the project's own +Y axis, as for SetProjection." },
			"viewAltitude": { "type": "number", "description": "How high the camera stands, in degrees above the horizon." },
			"sun": { "type": "object", "description": "The date and time the document keeps its sun at. Any field left out keeps its value." },
			"shadowFill": { "type": "object", "description": "The fill its sun shadows are drawn in, as for CreateDocumentFrom3D." },
			"effects3D": { "type": "integer", "description": "The document's vectorial effects flags, copied whole from a document read back with the effects wanted." }
		},
		"required": [ "databaseId" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> SetDocumentFrom3DCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"effects3D": { "type": "integer" },
			"shadowFill": { "type": "object" },
			"isPerspective": { "type": "boolean" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState SetDocumentFrom3DCommand::Execute (const GS::ObjectState& parameters,
												   GS::ProcessControl& /*processControl*/) const
{
	GS::ObjectState identifier;
	GS::UniString guid;
	if (!parameters.Get ("databaseId", identifier) || !identifier.Get ("guid", guid)) {
		return Failed ("databaseId needs a guid.", APIERR_BADPARS);
	}
	API_DatabaseUnId document = {};
	document.elemSetId = APIGuidFromString (guid.ToCStr ().Get ());

	// Read first and written back whole: the struct carries the document's
	// filter, cut planes and model display, and a command that built it from
	// nothing would reset every one of them.
	API_DocumentFrom3DType settings = {};
	GSErrCode err = ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, &document, &settings);
	if (err != NoError) {
		return Failed ("Failed to read the 3D Document's settings.", err);
	}

	AimDocument (parameters, settings.projectionSetting);
	GS::ObjectState fill;
	if (parameters.Get ("shadowFill", fill)) {
		ApplyShadowFill (fill, settings.attributeOptions);
	}
	Int32 effects = 0;
	if (ReadInt (parameters, "effects3D", effects)) {
		settings.effects3D = static_cast<short> (effects);
	}

	err = ACAPI_Environment (APIEnv_ChangeDocumentFrom3DSettingsID, &document, &settings);
	BMhFree (reinterpret_cast<GSHandle> (settings.cutSetting.shapes));
	settings.cutSetting.shapes = nullptr;
	if (err != NoError) {
		return Failed ("Failed to change the 3D Document's settings.", err);
	}
	return DocumentState (document);
}


// -- Set3DFilter ------------------------------------------------------------

GS::String Set3DFilterCommand::GetName () const			{ return "Set3DFilter"; }

GS::Optional<GS::UniString> Set3DFilterCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"allStories": { "type": "boolean", "description": "True converts every storey, which is the dialog's own 'All Stories'. False makes firstStory and lastStory apply." },
			"firstStory": { "type": "integer", "description": "First storey index to convert, when allStories is false." },
			"lastStory": { "type": "integer", "description": "Last storey index to convert, when allStories is false." },
			"trimToStoryRange": { "type": "boolean", "description": "Whether elements are cut at the range rather than shown whole." },
			"databaseId": { "type": "object", "properties": { "guid": { "type": "string" } }, "description": "A 3D Document to change instead of the 3D window. A document keeps its own copy of the filter, so one made under a storey range goes on showing that range however the window is set." }
		},
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> Set3DFilterCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"allStories": { "type": "boolean" },
			"firstStory": { "type": "integer" },
			"lastStory": { "type": "integer" },
			"trimToStoryRange": { "type": "boolean" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState Set3DFilterCommand::Execute (const GS::ObjectState& parameters,
											 GS::ProcessControl& /*processControl*/) const
{
	// A document, if one is named. `API_DocumentFrom3DType` carries an
	// `API_3DFilterAndCutSettings` of its own -- the first field of the struct
	// -- so a document made while the window was filtered to storeys 1..10
	// goes on converting those ten however the window is set afterwards, and
	// cannot be re-aimed or deleted through the API. Changing it in place is
	// the only way to mend one that is already there.
	API_DatabaseUnId document = {};
	bool ofDocument = false;
	{
		GS::ObjectState identifier;
		if (parameters.Get ("databaseId", identifier)) {
			GS::UniString guid;
			if (!identifier.Get ("guid", guid)) {
				return Failed ("databaseId needs a guid.", APIERR_BADPARS);
			}
			document.elemSetId = APIGuidFromString (guid.ToCStr ().Get ());
			ofDocument = true;
		}
	}

	// Read first. The same struct carries the marquee filter and the element
	// type filter, and a command that built it from nothing would throw away
	// a marquee somebody set without ever mentioning it.
	API_3DFilterAndCutSettings settings = {};
	API_DocumentFrom3DType paper = {};
	GSErrCode err = ofDocument
		? ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, &document, &paper)
		: ACAPI_Environment (APIEnv_Get3DImageSetsID, &settings);
	if (err != NoError) {
		return Failed (ofDocument ? "Failed to read the 3D Document's settings."
								  : "Failed to read the 3D filter settings.", err);
	}
	if (ofDocument) {
		settings = paper.filterAndCutSettings;
	}

	bool allStories = settings.allStories;
	if (parameters.Get ("allStories", allStories)) {
		settings.allStories = allStories;
	}
	ReadShort (parameters, "firstStory", settings.firstStory3D);
	ReadShort (parameters, "lastStory", settings.lastStory3D);
	bool trim = settings.trimToStoryRange;
	if (parameters.Get ("trimToStoryRange", trim)) {
		settings.trimToStoryRange = trim;
	}

	if (ofDocument) {
		paper.filterAndCutSettings = settings;
		err = ACAPI_Environment (APIEnv_ChangeDocumentFrom3DSettingsID, &document, &paper);
		// The settings read back carry a handle the kit's own example frees
		// after use; nothing here owns it.
		BMhFree (reinterpret_cast<GSHandle> (paper.cutSetting.shapes));
		paper.cutSetting.shapes = nullptr;
		if (err != NoError) {
			return Failed ("Failed to write the 3D Document's filter.", err);
		}
	} else {
		// par2 is the kit's "must convert" flag: without it the settings
		// change and the window goes on showing what it already converted,
		// which reads exactly like the command having done nothing.
		bool convert = true;
		err = ACAPI_Environment (APIEnv_Change3DImageSetsID, &settings, &convert);
		if (err != NoError) {
			return Failed ("Failed to write the 3D filter settings.", err);
		}
	}

	// Read back rather than report what was asked for: a refused field would
	// otherwise be reported as set, and the symptom -- half a model in a sun
	// view -- says nothing about which storey was dropped.
	API_3DFilterAndCutSettings now = {};
	if (ofDocument) {
		API_DocumentFrom3DType again = {};
		err = ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, &document, &again);
		now = again.filterAndCutSettings;
		BMhFree (reinterpret_cast<GSHandle> (again.cutSetting.shapes));
		again.cutSetting.shapes = nullptr;
	} else {
		err = ACAPI_Environment (APIEnv_Get3DImageSetsID, &now);
	}
	if (err != NoError) {
		return Failed ("The 3D filter was written but could not be read back.", err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("allStories", now.allStories);
	result.Add ("firstStory", static_cast<Int32> (now.firstStory3D));
	result.Add ("lastStory", static_cast<Int32> (now.lastStory3D));
	result.Add ("trimToStoryRange", now.trimToStoryRange);
	return result;
}

}		// namespace Loriini
