// What an element carries as IFC data, read and written.
//
//   GetIfcProperties  Reads the IFC properties stored on elements -- the ones
//                     somebody typed into a schedule or the IFC Manager, not
//                     those an export translator would calculate. How the
//                     columns of a hand-made schedule are found: a Fill takes
//                     no classification and so no custom property, but it does
//                     keep an IFC property typed against it, and that never
//                     shows through `GetPropertyValuesOfElements`.
//
//   SetIfcProperties  Writes single-value IFC properties onto elements: text
//                     as an IfcLabel, a number as an IfcReal. Each value is
//                     answered on its own, so one refusal names its element.
//
// Archicad 26 to 28 only. From 29 the IFC API is a reader and a builder for
// export hooks, and nothing in it stores a property on an element; both
// commands are still registered there and answer that they cannot, so the
// Python side hears a reason rather than a missing command.

#if !defined (LORIINI_IFCCOMMANDS_HPP)
#define LORIINI_IFCCOMMANDS_HPP

#pragma once

#include "Support.hpp"

namespace Loriini {

#define LORIINI_IFC_COMMAND(ClassName)                                                      \
	class ClassName : public Command {                                                      \
	public:                                                                                 \
		virtual GS::String					GetName () const override;                      \
		virtual GS::Optional<GS::UniString>	GetInputParametersSchema () const override;     \
		virtual GS::Optional<GS::UniString>	GetResponseSchema () const override;            \
		virtual GS::ObjectState				Execute (const GS::ObjectState& parameters,     \
													 GS::ProcessControl& processControl) const override; \
	};

LORIINI_IFC_COMMAND (GetIfcPropertiesCommand)
LORIINI_IFC_COMMAND (SetIfcPropertiesCommand)
LORIINI_IFC_COMMAND (GetIfcTranslatorsCommand)
LORIINI_IFC_COMMAND (ExportIfcCommand)

#undef LORIINI_IFC_COMMAND

}		// namespace Loriini

#endif
