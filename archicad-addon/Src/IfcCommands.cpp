#include "IfcCommands.hpp"
#include "ApiCompat.hpp"
#include "Location.hpp"

namespace Loriini {

namespace {

#ifdef ServerMainVers_2900

const char* NotOnThisVersion =
	"Archicad 29 and later give an add-on no way to store an IFC property on an element.";

#else

API_Guid ReadElementGuid (const GS::ObjectState& from)
{
	GS::UniString guid;
	from.Get ("guid", guid);
	return APIGuidFromString (guid.ToCStr ().Get ());
}

// One value as the schedule would show it. Numbers keep their full precision:
// what is being read is what somebody typed, and rounding it here would hide
// whether "68.8%" was typed as text or as 68.8.
GS::ObjectState ValueState (const API_IFCPropertyValue& value)
{
	GS::ObjectState state;
	state.Add ("valueType", value.valueType);
	switch (value.value.primitiveType) {
		case API_IFCPropertyAnyValueIntegerType:	state.Add ("value", static_cast<double> (value.value.intValue)); break;
		case API_IFCPropertyAnyValueRealType:		state.Add ("value", value.value.doubleValue); break;
		case API_IFCPropertyAnyValueBooleanType:
		case API_IFCPropertyAnyValueLogicalType:	state.Add ("value", value.value.boolValue); break;
		default:									state.Add ("value", value.value.stringValue); break;
	}
	return state;
}

const char* KindName (API_IFCPropertyType type)
{
	switch (type) {
		case API_IFCPropertySingleValueType:		return "single";
		case API_IFCPropertyListValueType:			return "list";
		case API_IFCPropertyBoundedValueType:		return "bounded";
		case API_IFCPropertyEnumeratedValueType:	return "enumerated";
		case API_IFCPropertyTableValueType:			return "table";
	}
	return "unknown";
}

#endif

}		// namespace


// -- GetIfcProperties --------------------------------------------------------

GS::String GetIfcPropertiesCommand::GetName () const		{ return "GetIfcProperties"; }

GS::Optional<GS::UniString> GetIfcPropertiesCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"elements": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": { "guid": { "type": "string" } },
					"required": [ "guid" ]
				}
			}
		},
		"required": [ "elements" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> GetIfcPropertiesCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"elements": { "type": "array" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetIfcPropertiesCommand::Execute (const GS::ObjectState& parameters,
												  GS::ProcessControl& /*processControl*/) const
{
#ifdef ServerMainVers_2900
	(void) parameters;
	return Failed (NotOnThisVersion, APIERR_NOTSUPPORTED);
#else
	GS::Array<GS::ObjectState> asked;
	parameters.Get ("elements", asked);

	GS::Array<GS::ObjectState> answers;
	for (const GS::ObjectState& one : asked) {
		GS::ObjectState answer;
		GS::Array<API_IFCProperty> stored;
		// Stored only: the ones on the element, not what the translator would
		// work out at export. A typed value is stored; a mapped one is not.
		const GSErrCode err = ACAPI_Element_GetIFCProperties (ReadElementGuid (one), true, &stored);
		if (err != NoError) {
			answer = Failed ("Failed to read the element's IFC properties.", err);
			answers.Push (answer);
			continue;
		}
		GS::Array<GS::ObjectState> properties;
		for (const API_IFCProperty& property : stored) {
			GS::ObjectState state;
			state.Add ("propertySet", property.head.propertySetName);
			state.Add ("name", property.head.propertyName);
			state.Add ("kind", GS::UniString (KindName (property.head.propertyType)));
			if (property.head.propertyType == API_IFCPropertySingleValueType) {
				state.Add ("nominalValue", ValueState (property.singleValue.nominalValue));
			}
			properties.Push (state);
		}
		answer.Add ("properties", properties);
		answers.Push (answer);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("elements", answers);
	return result;
#endif
}


// -- SetIfcProperties --------------------------------------------------------

GS::String SetIfcPropertiesCommand::GetName () const		{ return "SetIfcProperties"; }

GS::Optional<GS::UniString> SetIfcPropertiesCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"values": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"guid": { "type": "string" },
						"propertySet": { "type": "string", "minLength": 1 },
						"name": { "type": "string", "minLength": 1 },
						"text": { "type": "string", "description": "Written as an IfcLabel." },
						"number": { "type": "number", "description": "Written as an IfcReal." }
					},
					"required": [ "guid", "propertySet", "name" ],
					"additionalProperties": false
				}
			}
		},
		"required": [ "values" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> SetIfcPropertiesCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"results": { "type": "array" },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState SetIfcPropertiesCommand::Execute (const GS::ObjectState& parameters,
												  GS::ProcessControl& /*processControl*/) const
{
#ifdef ServerMainVers_2900
	(void) parameters;
	return Failed (NotOnThisVersion, APIERR_NOTSUPPORTED);
#else
	GS::Array<GS::ObjectState> values;
	parameters.Get ("values", values);

	GS::Array<GS::ObjectState> results;
	const GSErrCode undoErr = ACAPI_CallUndoableCommand ("Write IFC properties", [&] () -> GSErrCode {
		for (const GS::ObjectState& one : values) {
			API_IFCProperty property = {};
			one.Get ("propertySet", property.head.propertySetName);
			one.Get ("name", property.head.propertyName);
			property.head.propertyType = API_IFCPropertySingleValueType;
			property.head.readOnly = false;

			API_IFCPropertyValue& nominal = property.singleValue.nominalValue;
			double number = 0.0;
			if (one.Get ("number", number)) {
				nominal.value.primitiveType = API_IFCPropertyAnyValueRealType;
				nominal.value.doubleValue = number;
				nominal.valueType = "IfcReal";
			} else {
				nominal.value.primitiveType = API_IFCPropertyAnyValueStringType;
				one.Get ("text", nominal.value.stringValue);
				nominal.valueType = "IfcLabel";
			}

			const GSErrCode err = ACAPI_Element_SetIFCProperty (ReadElementGuid (one), property);
			results.Push (err == NoError ? Succeeded () : Failed ("Failed to write the IFC property.", err));
		}
		return NoError;
	});
	if (undoErr != NoError) {
		return Failed ("Failed to write IFC properties in an undoable step.", undoErr);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("results", results);
	return result;
#endif
}

// -- GetIfcTranslators -------------------------------------------------------
//
// The project's IFC export translators by name, so a caller can say which
// one it means -- the QA export's, set up once by hand (D184). The first
// Archicad lists is its preview translator.

GS::String GetIfcTranslatorsCommand::GetName () const		{ return "GetIfcTranslators"; }

GS::Optional<GS::UniString> GetIfcTranslatorsCommand::GetInputParametersSchema () const
{
	return GS::NoValue;
}

GS::Optional<GS::UniString> GetIfcTranslatorsCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"translators": { "type": "array", "items": { "type": "string" } },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetIfcTranslatorsCommand::Execute (const GS::ObjectState& /*parameters*/,
												   GS::ProcessControl& /*processControl*/) const
{
	GS::Array<API_IFCTranslatorIdentifier> translators;
	const GSErrCode err = ACAPI_IFC_GetIFCExportTranslatorsList (translators);
	if (err != NoError) {
		return Failed ("Failed to list the IFC export translators.", err);
	}
	GS::Array<GS::UniString> names;
	for (const API_IFCTranslatorIdentifier& one : translators) {
		names.Push (one.name);
	}
	GS::ObjectState result = Succeeded ();
	result.Add ("translators", names);
	return result;
}

// -- ExportIfc ---------------------------------------------------------------
//
// The whole project saved as IFC through the export translator of the name
// given. Tapir's IFCFileOperation saves through whichever translator is
// selected in Archicad's dialog, and the QA export needs its own.

GS::String ExportIfcCommand::GetName () const		{ return "ExportIfc"; }

GS::Optional<GS::UniString> ExportIfcCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"path": { "type": "string", "description": "The .ifc file to write." },
			"translator": { "type": "string", "description": "The export translator, by name." }
		},
		"additionalProperties": false,
		"required": ["path", "translator"]
	})");
}

GS::Optional<GS::UniString> ExportIfcCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"translator": { "type": "string" },
			"error": { "type": "object" }
		}
	})");
}

// Where the comparison's case switch lives moved in 28: from inside
// GS::UniString to GS itself.
#ifdef ServerMainVers_2800
constexpr auto IgnoringCase = GS::CaseInsensitive;
#else
constexpr auto IgnoringCase = GS::UniString::CaseInsensitive;
#endif

GS::ObjectState ExportIfcCommand::Execute (const GS::ObjectState& parameters,
										   GS::ProcessControl& /*processControl*/) const
{
	GS::UniString path;
	GS::UniString wanted;
	if (!parameters.Get ("path", path) || path.IsEmpty ()) {
		return Failed ("An IFC export needs the file to write.", APIERR_BADPARS);
	}
	if (!parameters.Get ("translator", wanted) || wanted.IsEmpty ()) {
		return Failed ("An IFC export needs a translator's name.", APIERR_BADPARS);
	}

	GS::Array<API_IFCTranslatorIdentifier> translators;
	const GSErrCode listed = ACAPI_IFC_GetIFCExportTranslatorsList (translators);
	if (listed != NoError) {
		return Failed ("Failed to list the IFC export translators.", listed);
	}
	const API_IFCTranslatorIdentifier* chosen = nullptr;
	GS::UniString known;
	for (const API_IFCTranslatorIdentifier& one : translators) {
		if (one.name.IsEqual (wanted, IgnoringCase)) {
			chosen = &one;
		}
		if (!known.IsEmpty ()) {
			known += ", ";
		}
		known += one.name;
	}
	if (chosen == nullptr) {
		return Failed ("No IFC export translator named '" + wanted + "' in this project. It has: " + known, APIERR_BADPARS);
	}

	IO::Location location (path);
	API_FileSavePars file = {};
	file.fileTypeID = APIFType_IfcFile;
	file.file = &location;

	API_SavePars_Ifc ifc = {};
	ifc.subType = API_IFC;
	ifc.translatorIdentifier = *chosen;
	ifc.elementsToIfcExport = API_EntireProject;
	ifc.elementsSet = nullptr;
	ifc.includeBoundingBoxGeometry = false;

	const GSErrCode err = Api::SaveAsIfc (&file, &ifc);
	if (err != NoError) {
		return Failed ("Archicad would not export the IFC with '" + chosen->name + "'.", err);
	}
	GS::ObjectState result = Succeeded ();
	result.Add ("translator", chosen->name);
	return result;
}

}		// namespace Loriini
