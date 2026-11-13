// What a placed Drawing is, once Tapir has placed it.
//
//   GetDrawings       Reads the Drawings on a layout: where each sits, what it
//                     is anchored by, its clip frame and its content box. The
//                     instrument for `ArrangeDrawings`, which is why it is
//                     here: a frame written in the wrong coordinate space is a
//                     drawing off the page, and this is how that is seen.
//
//   ArrangeDrawings   Tapir's `CreateDrawings` puts a Drawing on a layout and
//                     nothing can then touch it: `SetDetailsOfElements` takes
//                     the magnification and refuses the rest. A Drawing made
//                     from a 3D Document arrives clipped to a placeholder frame
//                     about 59 mm square, anchored by its bottom-left corner,
//                     set to manual update -- so a sheet of seven sun eye
//                     views is seven stamps, and opening the layout does not
//                     change that. `API_DrawingType` carries all of it as
//                     plain fields, and `ACAPI_Element_Change` sets them.
//
//                     The frame is the part that matters. Freed, a drawing of
//                     a 3D Document shows the whole site model and swamps the
//                     sheet; the office's diagram is a window around the
//                     building. So the frame stays a clip, sized to the cell
//                     the drawing sits in, and the drawing's own origin -- the
//                     projected model origin, which on a site drawn around it
//                     is the building -- goes to the cell's centre.

#if !defined (LORIINI_LAYOUTCOMMANDS_HPP)
#define LORIINI_LAYOUTCOMMANDS_HPP

#pragma once

#include "Support.hpp"

namespace Loriini {

#define LORIINI_LAYOUT_COMMAND(ClassName)                                                   \
	class ClassName : public Command {                                                      \
	public:                                                                                 \
		virtual GS::String					GetName () const override;                      \
		virtual GS::Optional<GS::UniString>	GetInputParametersSchema () const override;     \
		virtual GS::Optional<GS::UniString>	GetResponseSchema () const override;            \
		virtual GS::ObjectState				Execute (const GS::ObjectState& parameters,     \
													 GS::ProcessControl& processControl) const override; \
	};

LORIINI_LAYOUT_COMMAND (GetDrawingsCommand)
LORIINI_LAYOUT_COMMAND (ArrangeDrawingsCommand)

//   GetDrawingPrimitives   What a placed Drawing draws, as polygons: Archicad
//                     decomposes the drawing into the primitives of its content
//                     (`ACAPI_Element_ShapePrims`), and the filled ones are
//                     handed back with their pens. It is how the shadows a 3D
//                     Document casts are read out of it -- Archicad draws them
//                     as fills on the surfaces they fall on, in the shadow's
//                     pen -- so a shadow diagram can be drawn once as plain
//                     fills instead of being a stack of live documents on a
//                     sheet.
LORIINI_LAYOUT_COMMAND (GetDrawingPrimitivesCommand)

#undef LORIINI_LAYOUT_COMMAND

}		// namespace Loriini

#endif
