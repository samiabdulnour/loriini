#include "ProjectCommands.hpp"
#include "ApiCompat.hpp"
#include "Support.hpp"

namespace Loriini {

namespace {

// Archicad's window type names, as the JSON side already spells them.
//
// Matched to Tapir's own vocabulary on purpose: the Python adapter already
// says "FloorPlan" and "Worksheet" in `ChangeWindow`, and a second spelling of
// the same idea is a second thing to get wrong.
bool ReadWindowType (const GS::UniString& name, API_WindowTypeID& into)
{
	if (name == "FloorPlan")		{ into = APIWind_FloorPlanID; return true; }
	if (name == "Worksheet")		{ into = APIWind_WorksheetID; return true; }
	if (name == "Detail")			{ into = APIWind_DetailID; return true; }
	if (name == "Layout")			{ into = APIWind_LayoutID; return true; }
	if (name == "Section")			{ into = APIWind_SectionID; return true; }
	if (name == "Elevation")		{ into = APIWind_ElevationID; return true; }
	if (name == "DocumentFrom3D")	{ into = APIWind_DocumentFrom3DID; return true; }
	if (name == "3D")				{ into = APIWind_3DModelID; return true; }
	return false;
}


GS::UniString WindowTypeName (API_WindowTypeID type)
{
	switch (type) {
		case APIWind_FloorPlanID:		return "FloorPlan";
		case APIWind_WorksheetID:		return "Worksheet";
		case APIWind_DetailID:			return "Detail";
		case APIWind_LayoutID:			return "Layout";
		case APIWind_SectionID:			return "Section";
		case APIWind_ElevationID:		return "Elevation";
		case APIWind_DocumentFrom3DID:	return "DocumentFrom3D";
		case APIWind_3DModelID:			return "3D";
		default:						return "Other";
	}
}


GS::ObjectState DatabaseState (const API_DatabaseInfo& database)
{
	GS::ObjectState identifier;
	identifier.Add ("guid", APIGuidToString (database.databaseUnId.elemSetId));

	GS::ObjectState state;
	state.Add ("databaseId", identifier);
	state.Add ("windowType", WindowTypeName (database.typeID));
	state.Add ("name", GS::UniString (database.name));
	state.Add ("referenceId", GS::UniString (database.ref));
	return state;
}

}		// namespace


// -- GetPlace -----------------------------------------------------------------
//
// The project location whole, as `API_PlaceInfo` holds it: where the project
// is, which way north lies, and -- the half Tapir's `GetGeoLocation` leaves
// out -- the clock Archicad keeps for a sun given by date. `timeZoneInMinutes`
// is that clock, east of Greenwich; `summerTime` is the daylight-saving flag
// the dialog's own date carries. Measured on the sample project (D135): with
// the zone at +180 minutes, a document asked for at 09:00 was drawn with the
// sun of 09:00 UTC+3, and the same request with `summerTime` on was drawn an
// hour earlier. Nothing here is written; the location is the project's own.

GS::String GetPlaceCommand::GetName () const		{ return "GetPlace"; }

GS::Optional<GS::UniString> GetPlaceCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetPlaceCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"longitude": { "type": "number", "description": "Degrees east of Greenwich." },
			"latitude": { "type": "number", "description": "Degrees north of the equator." },
			"altitude": { "type": "number", "description": "Metres above sea level." },
			"north": { "type": "number", "description": "Archicad's north angle in radians, exactly as GetGeoLocation reports it." },
			"timeZoneInMinutes": { "type": "integer", "description": "The project location's time zone, in minutes east of Greenwich: the clock Archicad reads a sun date in." },
			"timeZoneOffset": { "type": "integer", "description": "Archicad's tie-breaker between zones with the same minutes; reported whole." },
			"summerTime": { "type": "boolean", "description": "Whether the location's own date has daylight saving in effect." },
			"date": {
				"type": "object",
				"description": "The date and time the project location keeps, as its dialog shows them.",
				"properties": {
					"year": { "type": "integer" },
					"month": { "type": "integer" },
					"day": { "type": "integer" },
					"hour": { "type": "integer" },
					"minute": { "type": "integer" },
					"second": { "type": "integer" }
				}
			},
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetPlaceCommand::Execute (const GS::ObjectState& /*parameters*/,
										  GS::ProcessControl& /*processControl*/) const
{
	API_PlaceInfo place = {};
	const GSErrCode err = Api::GetPlaceSets (&place);
	if (err != NoError) {
		return Failed ("Failed to read the project location.", err);
	}

	GS::ObjectState date;
	date.Add ("year", static_cast<Int32> (place.year));
	date.Add ("month", static_cast<Int32> (place.month));
	date.Add ("day", static_cast<Int32> (place.day));
	date.Add ("hour", static_cast<Int32> (place.hour));
	date.Add ("minute", static_cast<Int32> (place.minute));
	date.Add ("second", static_cast<Int32> (place.second));

	GS::ObjectState result;
	result.Add ("success", true);
	result.Add ("longitude", place.longitude);
	result.Add ("latitude", place.latitude);
	result.Add ("altitude", place.altitude);
	result.Add ("north", place.north);
	result.Add ("timeZoneInMinutes", static_cast<Int32> (place.timeZoneInMinutes));
	result.Add ("timeZoneOffset", static_cast<Int32> (place.timeZoneOffset));
	result.Add ("summerTime", place.sumTime);
	result.Add ("date", date);
	return result;
}


// -- GetCurrentDatabase -----------------------------------------------------

GS::String GetCurrentDatabaseCommand::GetName () const		{ return "GetCurrentDatabase"; }

GS::Optional<GS::UniString> GetCurrentDatabaseCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetCurrentDatabaseCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"databaseId": { "type": "object", "properties": { "guid": { "type": "string" } } },
			"windowType": { "type": "string" },
			"name": { "type": "string" },
			"referenceId": { "type": "string" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetCurrentDatabaseCommand::Execute (const GS::ObjectState& /*parameters*/,
													GS::ProcessControl& /*processControl*/) const
{
	API_DatabaseInfo database = {};
	const GSErrCode err = Api::GetCurrentDatabase (&database);
	if (err != NoError) {
		return Failed ("Failed to read the current database.", err);
	}

	GS::ObjectState result = DatabaseState (database);
	result.Add ("success", true);
	return result;
}


// -- SetCurrentDatabase -----------------------------------------------------

GS::String SetCurrentDatabaseCommand::GetName () const		{ return "SetCurrentDatabase"; }

GS::Optional<GS::UniString> SetCurrentDatabaseCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"databaseId": {
				"type": "object",
				"properties": { "guid": { "type": "string" } },
				"required": [ "guid" ]
			},
			"windowType": {
				"type": "string",
				"description": "Needed alongside the id: a database is identified by its type and its unique id together."
			},
			"floorIndex": {
				"type": "integer",
				"description": "For the floor plan, which storey to stand on."
			},
			"open": {
				"type": "boolean",
				"description": "Open the database's window first, as a double-click in the Project Map does, and move the database after. For a worksheet made through the API, which refuses the plain move until a person has opened it once."
			}
		},
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> SetCurrentDatabaseCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"opened": { "type": "boolean" },
			"databaseId": { "type": "object" },
			"windowType": { "type": "string" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState SetCurrentDatabaseCommand::Execute (const GS::ObjectState& parameters,
													GS::ProcessControl& /*processControl*/) const
{
	// Started from where we are, so a caller naming only a floor index moves
	// storey without having to restate which database it is standing in.
	API_DatabaseInfo database = {};
	GSErrCode err = Api::GetCurrentDatabase (&database);
	if (err != NoError) {
		return Failed ("Failed to read the current database before changing it.", err);
	}

	GS::ObjectState identifier;
	if (parameters.Get ("databaseId", identifier)) {
		GS::UniString guid;
		if (!identifier.Get ("guid", guid)) {
			return Failed ("databaseId needs a guid.", APIERR_BADPARS);
		}
		database.databaseUnId.elemSetId = APIGuidFromString (guid.ToCStr ().Get ());
	}

	GS::UniString windowType;
	if (parameters.Get ("windowType", windowType)) {
		if (!ReadWindowType (windowType, database.typeID)) {
			return Failed ("Unknown windowType " + windowType + ".", APIERR_BADPARS);
		}
	}

	Int32 floor = 0;
	if (parameters.Get ("floorIndex", floor)) {
		database.index = floor;
	}

	// The 3D window is a window, not a database: it has no database of its
	// own to move to, and asked for as one Archicad accepted the move and
	// stayed on the floor plan (17 October 2026). So it is brought to the
	// front as a window, rebuilt so it shows the layers as they are now,
	// and the move is read back by the window's type.
	if (database.typeID == APIWind_3DModelID) {
		API_WindowInfo window = {};
		window.typeID = APIWind_3DModelID;
		err = Api::ChangeWindow (&window);
		if (err != NoError) {
			return Failed ("Archicad refused to bring the 3D window to the front.", err);
		}
		Api::RebuildFrontWindow (true);
		API_DatabaseInfo landed = {};
		err = Api::GetCurrentDatabase (&landed);
		if (err != NoError || landed.typeID != APIWind_3DModelID) {
			return Failed ("Archicad accepted the move to the 3D window and stayed where it was.",
						   err != NoError ? err : APIERR_GENERAL);
		}
		GS::ObjectState result = DatabaseState (landed);
		result.Add ("success", true);
		result.Add ("opened", true);
		return result;
	}

	// A worksheet made through the API refuses `APIDb_ChangeCurrentDatabaseID`
	// with APIERR_BADDATABASE until a person has opened it once, and a save or
	// a reopen does not lift that (D95). What a person does is open its
	// *window*, which is a different call: `APIDo_ChangeWindowID`, the one
	// the 3D export already uses to bring the 3D window to the front
	// (ModelCommands.cpp). Asked for with `open`, the window is opened first
	// and the move made after; whether Archicad takes it for a fresh
	// worksheet is for a live run to say, which is why it is asked for
	// rather than always done, and why the plain move is still tried first.
	bool open = false;
	bool opened = false;
	if (parameters.Get ("open", open) && open) {
		API_WindowInfo window = database;
		err = Api::ChangeWindow (&window);
		if (err != NoError) {
			return Failed ("Archicad refused to open that database's window.", err);
		}
		opened = true;
	}

	err = Api::ChangeCurrentDatabase (&database);
	if (err != NoError) {
		return Failed (opened ? "Archicad opened the window and still refused to move to that database."
							  : "Archicad refused to move to that database.", err);
	}

	// Read back rather than assumed. This command exists because Tapir's
	// `ChangeWindow` reports success and does not move (D40), so a version of
	// it that reports success without checking would be the same trap wearing
	// a different name.
	API_DatabaseInfo landed = {};
	err = Api::GetCurrentDatabase (&landed);
	if (err != NoError) {
		return Failed ("Moved, but could not confirm where to.", err);
	}
	if (landed.databaseUnId != database.databaseUnId) {
		return Failed ("Archicad accepted the move and stayed where it was.", APIERR_GENERAL);
	}

	GS::ObjectState result = DatabaseState (landed);
	result.Add ("success", true);
	result.Add ("opened", opened);
	return result;
}


// -- CreateWorksheet --------------------------------------------------------

GS::String CreateWorksheetCommand::GetName () const			{ return "CreateWorksheet"; }

GS::Optional<GS::UniString> CreateWorksheetCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"name": { "type": "string" },
			"referenceId": { "type": "string" },
			"makeCurrent": {
				"type": "boolean",
				"description": "Stand in the new worksheet straight away, so the same run can draw into it. Default true, which is the point of the command."
			}
		},
		"required": [ "name" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> CreateWorksheetCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"databaseId": { "type": "object", "properties": { "guid": { "type": "string" } } },
			"isCurrent": { "type": "boolean" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState CreateWorksheetCommand::Execute (const GS::ObjectState& parameters,
												 GS::ProcessControl& /*processControl*/) const
{
	GS::UniString name;
	if (!parameters.Get ("name", name) || name.IsEmpty ()) {
		return Failed ("A worksheet needs a name.", APIERR_BADPARS);
	}

	API_DatabaseInfo database = {};
	database.typeID = APIWind_WorksheetID;
	CopyName (name, database.name);

	GS::UniString referenceId;
	if (parameters.Get ("referenceId", referenceId) && !referenceId.IsEmpty ()) {
		CopyName (referenceId, database.ref);
	}

	// Not undoable, on purpose. The kit documents `APIDb_NewDatabaseID` as a
	// non-undoable data structure modifier, and inside an undo scope it
	// answers APIERR_REFUSEDCMD (-2130312312) -- measured on 11 September
	// 2026 against the Kogarah solar study, the same refusal the 3D Document
	// command met on its first live run. A worksheet a run abandons is deleted
	// in the Navigator, as a document is.
	GSErrCode err = Api::NewDatabase (&database);
	if (err != NoError) {
		return Failed ("Failed to create the worksheet.", err);
	}

	// Becoming current is the whole reason this exists rather than Tapir's
	// `CreateWorksheets`. A worksheet made and not entered cannot be drawn
	// into in the same session: -2130313110, before and after `RebuildView`.
	bool makeCurrent = true;
	parameters.Get ("makeCurrent", makeCurrent);

	bool isCurrent = false;
	if (makeCurrent) {
		err = Api::ChangeCurrentDatabase (&database);
		if (err != NoError) {
			return Failed ("The worksheet was created but could not be entered, so nothing "
						   "can be drawn into it yet.", err);
		}
		isCurrent = true;
	}

	GS::ObjectState identifier;
	identifier.Add ("guid", APIGuidToString (database.databaseUnId.elemSetId));

	GS::ObjectState result = Succeeded ();
	result.Add ("databaseId", identifier);
	result.Add ("isCurrent", isCurrent);
	return result;
}


// -- ActivateLayerCombination -----------------------------------------------

GS::String ActivateLayerCombinationCommand::GetName () const		{ return "ActivateLayerCombination"; }

GS::Optional<GS::UniString> ActivateLayerCombinationCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"name": { "type": "string", "description": "The layer combination's name, as Layer Settings shows it." }
		},
		"required": [ "name" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> ActivateLayerCombinationCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"index": { "type": "integer" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState ActivateLayerCombinationCommand::Execute (const GS::ObjectState& parameters,
														  GS::ProcessControl& /*processControl*/) const
{
	GS::UniString name;
	if (!parameters.Get ("name", name) || name.IsEmpty ()) {
		return Failed ("A layer combination needs a name.", APIERR_BADPARS);
	}

	API_Attr_Head head = {};
	head.typeID = API_LayerCombID;
	GS::UniString held;
	CopyAttributeName (name, head, held);

	GSErrCode err = ACAPI_Attribute_Search (&head);
	if (err != NoError) {
		return Failed ("No layer combination named '" + name + "' in this project.", err);
	}

	err = Api::ChangeCurrentLayerCombination (&head.index);
	if (err != NoError) {
		return Failed ("Found '" + name + "' but Archicad would not activate it.", err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("index", Api::AttributeIndexToInt (head.index));
	return result;
}


// -- ModifyLayers -----------------------------------------------------------

GS::String ModifyLayersCommand::GetName () const		{ return "ModifyLayers"; }

GS::Optional<GS::UniString> ModifyLayersCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"layers": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"name": { "type": "string" },
						"isHidden": { "type": "boolean" },
						"isLocked": { "type": "boolean" },
						"isWireframe": { "type": "boolean" }
					},
					"required": [ "name" ]
				},
				"minItems": 1
			}
		},
		"required": [ "layers" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> ModifyLayersCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"changed": { "type": "integer" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState ModifyLayersCommand::Execute (const GS::ObjectState& parameters,
											  GS::ProcessControl& /*processControl*/) const
{
	GS::Array<GS::ObjectState> wanted;
	if (!parameters.Get ("layers", wanted) || wanted.IsEmpty ()) {
		return Failed ("Nothing to change: 'layers' is empty.", APIERR_BADPARS);
	}

	Int32 changed = 0;
	GS::UniString failureText;
	GSErrCode failure = NoError;

	const GSErrCode err = ACAPI_CallUndoableCommand ("Change layer visibility", [&] () -> GSErrCode {
		for (const GS::ObjectState& one : wanted) {
			GS::UniString name;
			if (!one.Get ("name", name) || name.IsEmpty ()) {
				failure = APIERR_BADPARS;
				failureText = "Every layer needs a name.";
				return APIERR_BADPARS;
			}

			API_Attribute layer = {};
			layer.header.typeID = API_LayerID;
			GS::UniString held;
			CopyAttributeName (name, layer.header, held);

			GSErrCode step = ACAPI_Attribute_Search (&layer.header);
			if (step != NoError) {
				failure = step;
				failureText = "No layer named '" + name + "' in this project.";
				return step;
			}
			step = ACAPI_Attribute_Get (&layer);
			if (step != NoError) {
				failure = step;
				failureText = "Found '" + name + "' but could not read it.";
				return step;
			}

			// Read, flip the named bits, write. Only what the caller asked
			// about moves: a layer's locked state is nobody's business when
			// the caller only spoke about visibility, and D59's workaround
			// rewrote all of it every time.
			bool flag = false;
			if (one.Get ("isHidden", flag)) {
				layer.header.flags = static_cast<short> (flag ? (layer.header.flags | APILay_Hidden)
														   : (layer.header.flags & ~APILay_Hidden));
			}
			if (one.Get ("isLocked", flag)) {
				layer.header.flags = static_cast<short> (flag ? (layer.header.flags | APILay_Locked)
														   : (layer.header.flags & ~APILay_Locked));
			}
			if (one.Get ("isWireframe", flag)) {
				layer.header.flags = static_cast<short> (flag ? (layer.header.flags | APILay_ForceToWire)
														   : (layer.header.flags & ~APILay_ForceToWire));
			}

			step = ACAPI_Attribute_Modify (&layer, nullptr);
			if (step != NoError) {
				failure = step;
				failureText = "Archicad refused to change layer '" + name + "'.";
				return step;
			}
			++changed;
		}
		return NoError;
	});

	if (err != NoError) {
		return Failed (failureText.IsEmpty () ? GS::UniString ("Failed to change the layers.") : failureText,
					   failure != NoError ? failure : err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("changed", changed);
	return result;
}



// -- GetGraphicOverrideCombinations -----------------------------------------

GS::String GetGraphicOverrideCombinationsCommand::GetName () const		{ return "GetGraphicOverrideCombinations"; }

GS::Optional<GS::UniString> GetGraphicOverrideCombinationsCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetGraphicOverrideCombinationsCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"combinations": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": { "guid": { "type": "string" }, "name": { "type": "string" } }
				}
			},
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetGraphicOverrideCombinationsCommand::Execute (const GS::ObjectState& /*parameters*/,
																GS::ProcessControl& /*processControl*/) const
{
	GS::Array<API_Guid> guids;
	const GSErrCode err = Api::GetOverrideCombinationList (guids);
	if (err != NoError) {
		return Failed ("Failed to list the graphic override combinations.", err);
	}

	GS::Array<GS::ObjectState> combinations;
	for (const API_Guid& guid : guids) {
		API_OverrideCombination combination;
		combination.guid = guid;
		if (Api::GetOverrideCombination (combination) != NoError) {
			continue;
		}
		GS::ObjectState one;
		one.Add ("guid", APIGuidToString (guid));
		one.Add ("name", combination.name);
		combinations.Push (one);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("combinations", combinations);
	return result;
}



// -- GetRenovationFilters ---------------------------------------------------

GS::String GetRenovationFiltersCommand::GetName () const		{ return "GetRenovationFilters"; }

GS::Optional<GS::UniString> GetRenovationFiltersCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetRenovationFiltersCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"renovationFilters": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": { "guid": { "type": "string" }, "name": { "type": "string" } }
				}
			},
			"current": { "type": "string", "description": "The filter the project is showing now." },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetRenovationFiltersCommand::Execute (const GS::ObjectState& /*parameters*/,
													  GS::ProcessControl& /*processControl*/) const
{
	GS::Array<API_Guid> guids;
	const GSErrCode err = Api::GetRenovationFilters (&guids);
	if (err != NoError) {
		return Failed ("Failed to list the renovation filters.", err);
	}

	// In the project's own order, which is the Renovation palette's: an
	// office that keeps its scenarios as filters numbers them there.
	GS::Array<GS::ObjectState> filters;
	for (const API_Guid& guid : guids) {
		GS::UniString name;
		if (Api::GetRenovationFilterName (&guid, &name) != NoError) {
			continue;
		}
		GS::ObjectState one;
		one.Add ("guid", APIGuidToString (guid));
		one.Add ("name", name);
		filters.Push (one);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("renovationFilters", filters);
	API_Guid current = APINULLGuid;
	if (Api::GetActualRenovationFilter (&current) == NoError && current != APINULLGuid) {
		result.Add ("current", APIGuidToString (current));
	}
	return result;
}

}		// namespace Loriini


// -- SetRenovationFilter ----------------------------------------------------

GS::String SetRenovationFilterCommand::GetName () const		{ return "SetRenovationFilter"; }

GS::Optional<GS::UniString> SetRenovationFilterCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"guid": { "type": "string", "description": "The filter, as GetRenovationFilters lists it." }
		},
		"additionalProperties": false,
		"required": ["guid"]
	})");
}

GS::Optional<GS::UniString> SetRenovationFilterCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"name": { "type": "string", "description": "What the palette calls the filter now shown." },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState SetRenovationFilterCommand::Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& /*processControl*/) const
{
	GS::UniString text;
	if (!parameters.Get ("guid", text) || text.IsEmpty ()) {
		return Failed ("A renovation filter needs its guid.", APIERR_BADPARS);
	}
	const API_Guid wanted = APIGuidFromString (text.ToCStr ().Get ());

	// Checked against the project's own list first: Archicad's answer to a
	// guid it does not know is a bare error code, and the name is what a
	// person reads back.
	GS::Array<API_Guid> guids;
	if (Api::GetRenovationFilters (&guids) != NoError) {
		return Failed ("Failed to list the renovation filters.", APIERR_GENERAL);
	}
	bool known = false;
	for (const API_Guid& guid : guids) {
		if (guid == wanted) {
			known = true;
			break;
		}
	}
	if (!known) {
		return Failed ("No renovation filter with the guid '" + text + "' in this project.", APIERR_BADPARS);
	}
	GS::UniString name;
	if (Api::GetRenovationFilterName (&wanted, &name) != NoError) {
		name = text;
	}

	const GSErrCode err = Api::SetActualRenovationFilter (&wanted);
	if (err != NoError) {
		return Failed ("Found '" + name + "' but Archicad would not show it.", err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("name", name);
	return result;
}
