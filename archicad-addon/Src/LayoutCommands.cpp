#include "LayoutCommands.hpp"
#include "ApiCompat.hpp"

#include "HashSet.hpp"

namespace Loriini {

namespace {

// The highest display level an element has; one there cannot be brought
// forward, and Archicad says so in a dialog.
const char TopDrawIndex = 14;

// Moves to a layout's database and remembers where we were.
//
// A Drawing lives in its layout's database and `ACAPI_Element_Get` reads
// from the current one, so a caller naming a layout has it made current for
// the duration and put back after -- Tapir's `ChangeWindow` reports success
// and does not always move (D40), and the Python side cannot tell.
class VisitDatabase {
public:
	explicit VisitDatabase (const API_Guid& layout)
	{
		if (Api::GetCurrentDatabase (&was) != NoError) {
			return;
		}
		API_DatabaseInfo target = {};
		target.typeID = APIWind_LayoutID;
		target.databaseUnId.elemSetId = layout;
		moved = Api::ChangeCurrentDatabase (&target) == NoError;
	}

	~VisitDatabase ()
	{
		if (moved) {
			Api::ChangeCurrentDatabase (&was);
		}
	}

	bool	moved = false;

private:
	API_DatabaseInfo	was = {};
};


// Reads the optional layout the caller names, and visits it. Returns the
// failure to report, or an empty state when all is well.
bool VisitNamedLayout (const GS::ObjectState& parameters, GS::Optional<VisitDatabase>& visit, GS::ObjectState& failure)
{
	GS::ObjectState layout;
	if (!parameters.Get ("layoutDatabaseId", layout)) {
		return true;
	}
	GS::UniString guid;
	if (!layout.Get ("guid", guid)) {
		failure = Failed ("layoutDatabaseId needs a guid.", APIERR_BADPARS);
		return false;
	}
	visit.New (APIGuidFromString (guid.ToCStr ().Get ()));
	if (!visit->moved) {
		failure = Failed ("Archicad refused to make that layout current.", APIERR_BADDATABASE);
		return false;
	}
	return true;
}


GS::ObjectState BoxState (const API_Box& box)
{
	GS::ObjectState state;
	state.Add ("xMin", box.xMin);
	state.Add ("yMin", box.yMin);
	state.Add ("xMax", box.xMax);
	state.Add ("yMax", box.yMax);
	return state;
}


const char* AnchorName (API_AnchorID anchor)
{
	switch (anchor) {
		case APIAnc_LT: return "LT";
		case APIAnc_MT: return "MT";
		case APIAnc_RT: return "RT";
		case APIAnc_LM: return "LM";
		case APIAnc_MM: return "MM";
		case APIAnc_RM: return "RM";
		case APIAnc_LB: return "LB";
		case APIAnc_MB: return "MB";
		case APIAnc_RB: return "RB";
		default:        return "?";
	}
}


// The clip frame, as the four corners of its bounding box, from the polygon
// memo. Reported as a box rather than a polygon because that is what the
// caller writes, and a frame that is not a rectangle is not one this add-on
// made.
bool ReadFrame (const API_Element& element, API_Box& frame)
{
	API_ElementMemo memo = {};
	if (ACAPI_Element_GetMemo (element.header.guid, &memo, APIMemoMask_Polygon) != NoError) {
		return false;
	}
	bool found = false;
	if (memo.coords != nullptr && element.drawing.poly.nCoords >= 1) {
		frame = { (*memo.coords)[1].x, (*memo.coords)[1].y, (*memo.coords)[1].x, (*memo.coords)[1].y };
		for (Int32 index = 1; index <= element.drawing.poly.nCoords; ++index) {
			const API_Coord& c = (*memo.coords)[index];
			frame.xMin = GS::Min (frame.xMin, c.x);
			frame.yMin = GS::Min (frame.yMin, c.y);
			frame.xMax = GS::Max (frame.xMax, c.x);
			frame.yMax = GS::Max (frame.yMax, c.y);
		}
		found = true;
	}
	ACAPI_DisposeElemMemoHdls (&memo);
	return found;
}


// A rectangle, as the closed five-point polygon a Drawing's clip frame is.
void WriteFrame (API_Element& element, API_ElementMemo& memo, const API_Box& frame)
{
	element.drawing.poly.nCoords = 5;
	element.drawing.poly.nSubPolys = 1;
	element.drawing.poly.nArcs = 0;

	memo.coords = reinterpret_cast<API_Coord**> (BMAllocateHandle ((element.drawing.poly.nCoords + 1) * sizeof (API_Coord), ALLOCATE_CLEAR, 0));
	memo.pends = reinterpret_cast<Int32**> (BMAllocateHandle ((element.drawing.poly.nSubPolys + 1) * sizeof (Int32), ALLOCATE_CLEAR, 0));
	if (memo.coords == nullptr || memo.pends == nullptr) {
		return;
	}
	(*memo.coords)[1] = { frame.xMin, frame.yMin };
	(*memo.coords)[2] = { frame.xMax, frame.yMin };
	(*memo.coords)[3] = { frame.xMax, frame.yMax };
	(*memo.coords)[4] = { frame.xMin, frame.yMax };
	(*memo.coords)[5] = (*memo.coords)[1];
	(*memo.pends)[0] = 0;
	(*memo.pends)[1] = element.drawing.poly.nCoords;
}


bool ReadBox (const GS::ObjectState& from, API_Box& into)
{
	return from.Get ("xMin", into.xMin) && from.Get ("yMin", into.yMin) &&
		   from.Get ("xMax", into.xMax) && from.Get ("yMax", into.yMax);
}

}		// namespace


// -- GetDrawings -------------------------------------------------------------

GS::String GetDrawingsCommand::GetName () const			{ return "GetDrawings"; }

GS::Optional<GS::UniString> GetDrawingsCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"layoutDatabaseId": {
				"type": "object",
				"description": "The layout to read. Made current for the call and restored after; left out, the current database is read.",
				"properties": { "guid": { "type": "string" } },
				"required": [ "guid" ]
			}
		},
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> GetDrawingsCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"drawings": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"guid": { "type": "string" },
						"name": { "type": "string" },
						"pos": { "type": "object" },
						"anchor": { "type": "string" },
						"useOwnOrigoAsAnchor": { "type": "boolean" },
						"isCutWithFrame": { "type": "boolean" },
						"manualUpdate": { "type": "boolean" },
						"ratio": { "type": "number" },
						"drawingScale": { "type": "number" },
						"angle": { "type": "number" },
						"bounds": { "type": "object" },
						"frame": { "type": "object" },
						"contentBox": { "type": "object" }
					}
				}
			},
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetDrawingsCommand::Execute (const GS::ObjectState& parameters,
											 GS::ProcessControl& /*processControl*/) const
{
	GS::Optional<VisitDatabase> visit;
	GS::ObjectState failure;
	if (!VisitNamedLayout (parameters, visit, failure)) {
		return failure;
	}

	GS::Array<API_Guid> found;
	const GSErrCode err = ACAPI_Element_GetElemList (API_DrawingID, &found);
	if (err != NoError) {
		return Failed ("Failed to list the Drawings in the current database.", err);
	}

	GS::Array<GS::ObjectState> drawings;
	for (const API_Guid& guid : found) {
		API_Element element = {};
		element.header.guid = guid;
		if (ACAPI_Element_Get (&element) != NoError) {
			continue;
		}
		GS::ObjectState one;
		one.Add ("guid", APIGuidToString (guid));
		one.Add ("name", GS::UniString (element.drawing.name));
		GS::ObjectState pos;
		pos.Add ("x", element.drawing.pos.x);
		pos.Add ("y", element.drawing.pos.y);
		one.Add ("pos", pos);
		one.Add ("anchor", GS::UniString (AnchorName (element.drawing.anchorPoint)));
		one.Add ("useOwnOrigoAsAnchor", element.drawing.useOwnOrigoAsAnchor);
		one.Add ("isCutWithFrame", element.drawing.isCutWithFrame);
		one.Add ("manualUpdate", element.drawing.manualUpdate);
		one.Add ("ratio", element.drawing.ratio);
		one.Add ("drawingScale", element.drawing.drawingScale);
		one.Add ("angle", element.drawing.angle);
		one.Add ("bounds", BoxState (element.drawing.bounds));

		API_Box frame = {};
		if (ReadFrame (element, frame)) {
			one.Add ("frame", BoxState (frame));
		}
		// The kit's signature is untyped, so the guid is passed as a copy it
		// is allowed to point at.
		API_Box content = {};
		API_Guid lookup = guid;
		if (Api::GetFullDrawingContentBox (&content, &lookup) == NoError) {
			one.Add ("contentBox", BoxState (content));
		}
		drawings.Push (one);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("drawings", drawings);
	return result;
}


// -- ArrangeDrawings ---------------------------------------------------------

GS::String ArrangeDrawingsCommand::GetName () const			{ return "ArrangeDrawings"; }

GS::Optional<GS::UniString> ArrangeDrawingsCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"layoutDatabaseId": {
				"type": "object",
				"description": "The layout the drawings are on. Made current for the call and restored after; left out, the drawings are looked for in the current database.",
				"properties": { "guid": { "type": "string" } },
				"required": [ "guid" ]
			},
			"drawings": {
				"type": "array",
				"description": "Each Drawing element, where it goes, and optionally the clip frame it gets. Positions are metres on the layout. Every drawing is set square to the sheet, angle 0.",
				"items": {
					"type": "object",
					"properties": {
						"guid": { "type": "string" },
						"x": { "type": "number" },
						"y": { "type": "number" },
						"transparentBackground": { "type": "boolean", "description": "The drawing's own Transparent Background switch, `isTransparentBk`: what lies under it on the layout shows wherever it draws only background. Left out, the drawing keeps what it has." },
						"penTableIndex": { "type": "integer", "description": "Print the drawing in this pen table, by attribute index: `penTableUsageMode` set to use a pen table by index. A drawing of a 3D Document otherwise prints in the model's active pen table, whatever its view pins (D143). Left out, the drawing keeps what it has." },
						"frame": {
							"type": "object",
							"description": "A rectangular clip frame. In layout coordinates, or relative to the drawing's origin when frameRelativeToOrigin is set.",
							"properties": {
								"xMin": { "type": "number" }, "yMin": { "type": "number" },
								"xMax": { "type": "number" }, "yMax": { "type": "number" }
							},
							"required": [ "xMin", "yMin", "xMax", "yMax" ]
						}
					},
					"required": [ "guid", "x", "y" ],
					"additionalProperties": false
				}
			},
			"anchor": {
				"type": "string",
				"enum": [ "centre", "origin" ],
				"description": "What x and y place: the centre of the drawing's box, or the drawing's own origin -- for a 3D Document, the projected model origin. Default centre."
			},
			"frameRelativeToOrigin": { "type": "boolean", "description": "Whether a frame's coordinates are measured from the drawing's own origin rather than the layout's. Default false." },
			"fitFrame": { "type": "boolean", "description": "Drop the clip polygon so the frame follows the drawing's own extent. Ignored for a drawing given a frame. Default false." },
			"autoUpdate": { "type": "boolean", "description": "Let Archicad regenerate the drawing when the layout opens. Default true." },
			"stack": { "type": "boolean", "description": "Bring the drawings to the front in the order given, so the last listed lies on top of the rest: how two documents share one cell, the existing shadow over the proposal's. Default false." }
		},
		"required": [ "drawings" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> ArrangeDrawingsCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"arranged": { "type": "integer" },
			"failures": { "type": "array", "items": { "type": "object" } },
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState ArrangeDrawingsCommand::Execute (const GS::ObjectState& parameters,
												 GS::ProcessControl& /*processControl*/) const
{
	GS::Array<GS::ObjectState> drawings;
	if (!parameters.Get ("drawings", drawings) || drawings.IsEmpty ()) {
		return Failed ("drawings must name at least one Drawing.", APIERR_BADPARS);
	}

	GS::UniString anchor = "centre";
	bool frameRelative = false;
	bool fitFrame = false;
	bool autoUpdate = true;
	bool stack = false;
	parameters.Get ("anchor", anchor);
	parameters.Get ("frameRelativeToOrigin", frameRelative);
	parameters.Get ("fitFrame", fitFrame);
	parameters.Get ("autoUpdate", autoUpdate);
	parameters.Get ("stack", stack);
	const bool byOrigin = anchor == "origin";

	GS::Optional<VisitDatabase> visit;
	GS::ObjectState failure;
	if (!VisitNamedLayout (parameters, visit, failure)) {
		return failure;
	}

	Int32 arranged = 0;
	GS::Array<GS::ObjectState> failures;
	//: The drawings arranged, in the order given, for the stacking after.
	GS::Array<API_Guid> inOrder;

	// One undo step for the whole sheet, which is how a person would want to
	// take it back. An element change outside an undo scope is refused.
	const GSErrCode err = ACAPI_CallUndoableCommand ("Arrange drawings", [&] () -> GSErrCode {
		for (const GS::ObjectState& wanted : drawings) {
			GS::UniString guid;
			double x = 0.0;
			double y = 0.0;
			wanted.Get ("guid", guid);
			wanted.Get ("x", x);
			wanted.Get ("y", y);
			GS::ObjectState frameState;
			API_Box frame = {};
			const bool hasFrame = wanted.Get ("frame", frameState) && ReadBox (frameState, frame);

			API_Element element = {};
			element.header.guid = APIGuidFromString (guid.ToCStr ().Get ());
			GSErrCode one = ACAPI_Element_Get (&element);
			if (one == NoError && element.header.type != API_DrawingID) {
				one = APIERR_BADELEMENTTYPE;
			}
			if (one == NoError) {
				API_Element mask;
				ACAPI_ELEMENT_MASK_CLEAR (mask);

				// By its own origin or by the middle of its box. The origin
				// is what a 3D Document's drawing is about: the projected
				// model origin, which on a site modelled around it is the
				// building, so the building goes where the origin goes
				// whatever size the content turns out to be. The middle is
				// for a drawing whose content is what it should show.
				element.drawing.useOwnOrigoAsAnchor = byOrigin;
				element.drawing.anchorPoint = APIAnc_MM;
				element.drawing.pos.x = x;
				element.drawing.pos.y = y;
				ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, useOwnOrigoAsAnchor);
				ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, anchorPoint);
				ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, pos);

				// Square to the sheet. A Drawing comes down turned by an angle
				// that follows the project's north -- 279.9 degrees on Randwick,
				// 349.55 on Tweed Heads -- and its clip polygon is read in that
				// turned frame. Written here alone, the angle changes the field
				// and leaves an untouched frame where it stood (Tweed Heads,
				// 21 October 2026), so the angle that counts is the one asked of
				// CreateDrawings; this keeps the field in step with it.
				element.drawing.angle = 0.0;
				ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, angle);

				if (autoUpdate) {
					element.drawing.manualUpdate = false;
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, manualUpdate);
				}

				// A drawing laid over another in one cell is no use opaque: the
				// stacked shadow plans set this on every drawing above the
				// lowest (D142).
				bool transparent = false;
				if (wanted.Get ("transparentBackground", transparent)) {
					element.drawing.isTransparentBk = transparent;
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, isTransparentBk);
				}

				// The pen table it prints in. A drawing of a 3D Document prints
				// in the model's active pen table and not in the pen set its
				// view pins, measured on the sample project; the stacked shadow
				// plans give their own pen set, with the legend's colours, to
				// every drawing this way (D143).
				Int32 penTable = 0;
				if (ReadInt (wanted, "penTableIndex", penTable)) {
					element.drawing.penTableUsageMode = APIPenTableUsageMode_UsePenTableIndex;
					element.drawing.penTableIndex = Api::AttributeIndexFromInt (penTable);
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, penTableUsageMode);
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, penTableIndex);
				}

				API_ElementMemo memo = {};
				UInt64 memoMask = 0;
				if (hasFrame) {
					if (frameRelative) {
						frame.xMin += x;  frame.xMax += x;
						frame.yMin += y;  frame.yMax += y;
					}
					element.drawing.isCutWithFrame = true;
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, isCutWithFrame);
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, poly);
					WriteFrame (element, memo, frame);
					memoMask = APIMemoMask_Polygon;
				} else if (fitFrame) {
					element.drawing.isCutWithFrame = false;
					ACAPI_ELEMENT_MASK_SET (mask, API_DrawingType, isCutWithFrame);
				}

				one = ACAPI_Element_Change (&element, &mask, memoMask != 0 ? &memo : nullptr, memoMask, true);
				if (memoMask != 0) {
					ACAPI_DisposeElemMemoHdls (&memo);
				}
			}

			if (one == NoError) {
				++arranged;
				inOrder.Push (element.header.guid);
			} else {
				GS::ObjectState failed;
				failed.Add ("guid", guid);
				failed.Add ("code", static_cast<Int32> (one));
				failures.Push (failed);
			}
		}

		// The display order, when asked. Each drawing is brought to the
		// front in turn, so the list reads bottom to top: a layout draws the
		// frontmost drawing last, over the others, and a drawing is clear
		// wherever it draws nothing. The stacked shadow plans put the
		// existing set's document over the proposal's in every cell.
		if (stack) {
			for (const API_Guid& guid : inOrder) {
				// One at the top already is left there. Brought forward
				// again, Archicad puts up "Cannot bring some element(s) any
				// closer. Top stack level reached." and waits for its OK,
				// a drawing at a time, with the run standing behind it: a
				// second run onto a sheet the first had stacked.
				API_Elem_Head head = {};
				head.guid = guid;
				if (ACAPI_Element_GetHeader (&head) == NoError && head.drwIndex >= TopDrawIndex) {
					continue;
				}
				GS::Array<API_Guid> one;
				one.Push (guid);
				const GSErrCode ordered = Api::ElementTool (one, APITool_BringToFront, nullptr);
				if (ordered != NoError) {
					GS::ObjectState failed;
					failed.Add ("guid", APIGuidToString (guid));
					failed.Add ("code", static_cast<Int32> (ordered));
					failed.Add ("step", "bringToFront");
					failures.Push (failed);
				}
			}
		}
		return NoError;
	});
	if (err != NoError) {
		return Failed ("Failed to open an undo step for the drawings.", err);
	}

	GS::ObjectState result = Succeeded ();
	result.Add ("arranged", arranged);
	result.Add ("failures", failures);
	return result;
}


// -- GetDrawingPrimitives ----------------------------------------------------

namespace {

// How many kinds of primitive the kit names, with room for a later kit's.
constexpr Int32 PrimitiveKinds = 40;

// What one decomposition gathers. Archicad's callback carries no pointer of
// the caller's, so the one being filled is reached through `harvest` below;
// commands run one at a time on the main thread, and the decomposition
// cannot be nested.
struct Harvest {
	GS::HashSet<Int32>			pens;				// empty: every pen
	Int32						limit = 0;
	Int32						counts[PrimitiveKinds] = {};
	Int32						polygons = 0;		// seen, kept or not
	Int32						withArcs = 0;
	bool						truncated = false;
	bool						inHatch = false;	// between a hatch border's begin and end
	Int32						hatchPen = 0;
	Int32						hatchBackgroundPen = 0;
	Int32						hatchFill = 0;
	bool						boxed = false;
	API_Box						box = {};
	GS::Array<GS::ObjectState>	kept;
};

Harvest* harvest = nullptr;


// Plain, with no calling convention named: the kits before 27 declare the
// callback `__cdecl`, which is what a plain function is, and the later ones
// declare none and no longer define the word.
GSErrCode HarvestPrimitive (const API_PrimElement* prim, const void* par1, const void* par2, const void* /*par3*/)
{
	if (harvest == nullptr || prim == nullptr) {
		return NoError;
	}
	Harvest& into = *harvest;
	const Int32 kind = static_cast<Int32> (prim->header.typeID);
	if (kind >= 0 && kind < PrimitiveKinds) {
		++into.counts[kind];
	}

	switch (prim->header.typeID) {
		case API_PrimCtrl_HatchBorderBegID: {
			into.inHatch = true;
			into.hatchPen = 0;
			into.hatchBackgroundPen = 0;
			into.hatchFill = 0;
			const API_PrimHatchBorder* border = reinterpret_cast<const API_PrimHatchBorder*> (par1);
			if (border != nullptr) {
				into.hatchPen = border->fillPen.penIndex;
				into.hatchBackgroundPen = border->fillbkgPen;
				into.hatchFill = Api::AttributeIndexToInt (border->fillInd);
			}
			break;
		}
		case API_PrimCtrl_HatchBorderEndID:
			into.inHatch = false;
			break;

		case API_PrimPolyID: {
			const API_PrimPoly& poly = prim->poly;
			++into.polygons;
			if (poly.nArcs > 0) {
				++into.withArcs;
			}
			const Int32 pen = poly.head.pen.penIndex;
			const Int32 fillPen = poly.fillPen.penIndex;
			if (!into.pens.IsEmpty () && !into.pens.Contains (pen) && !into.pens.Contains (fillPen) &&
				!(into.inHatch && into.pens.Contains (into.hatchPen))) {
				break;
			}
			if (into.limit > 0 && static_cast<Int32> (into.kept.GetSize ()) >= into.limit) {
				into.truncated = true;
				break;
			}
			// As an API_Polygon's memo is laid out: the vertices from index 1,
			// each ring closed on its first, and the index of each ring's last
			// vertex from index 1 of the ends.
			const API_Coord* coords = reinterpret_cast<const API_Coord*> (par1);
			const Int32* ends = reinterpret_cast<const Int32*> (par2);
			if (coords == nullptr || poly.nCoords < 3) {
				break;
			}
			GS::Array<double> xy;
			for (Int32 index = 1; index <= poly.nCoords; ++index) {
				const API_Coord& c = coords[index];
				xy.Push (c.x);
				xy.Push (c.y);
				if (!into.boxed) {
					into.box = { c.x, c.y, c.x, c.y };
					into.boxed = true;
				} else {
					into.box.xMin = GS::Min (into.box.xMin, c.x);
					into.box.yMin = GS::Min (into.box.yMin, c.y);
					into.box.xMax = GS::Max (into.box.xMax, c.x);
					into.box.yMax = GS::Max (into.box.yMax, c.y);
				}
			}
			GS::Array<Int32> ringEnds;
			if (ends != nullptr) {
				for (Int32 ring = 1; ring <= poly.nSubPolys; ++ring) {
					ringEnds.Push (ends[ring]);
				}
			}
			GS::ObjectState one;
			one.Add ("pen", pen);
			one.Add ("fillPen", fillPen);
			one.Add ("solid", poly.solid);
			one.Add ("drawIndex", static_cast<Int32> (poly.head.drwIndex));
			one.Add ("layer", Api::AttributeIndexToInt (poly.head.layer));
			if (into.inHatch) {
				one.Add ("hatchPen", into.hatchPen);
				one.Add ("hatchBackgroundPen", into.hatchBackgroundPen);
				one.Add ("hatchFill", into.hatchFill);
			}
			if (poly.nArcs > 0) {
				one.Add ("arcs", poly.nArcs);
			}
			one.Add ("xy", xy);
			one.Add ("ends", ringEnds);
			into.kept.Push (one);
			break;
		}
		default:
			break;
	}
	return NoError;
}

}		// namespace


GS::String GetDrawingPrimitivesCommand::GetName () const		{ return "GetDrawingPrimitives"; }

GS::Optional<GS::UniString> GetDrawingPrimitivesCommand::GetInputParametersSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"layoutDatabaseId": {
				"type": "object",
				"description": "The layout the drawing is on. Made current for the call and restored after; left out, the drawing is looked for in the current database.",
				"properties": { "guid": { "type": "string" } },
				"required": [ "guid" ]
			},
			"drawing": { "type": "string", "description": "The Drawing element's guid." },
			"pens": {
				"type": "array",
				"description": "Keep only the polygons drawn or filled in one of these pens. Left out or empty, every polygon is kept.",
				"items": { "type": "integer" }
			},
			"limit": { "type": "integer", "description": "The most polygons to hand back; 0, the default, is all of them. The counts are of everything either way." }
		},
		"required": [ "drawing" ],
		"additionalProperties": false
	})");
}

GS::Optional<GS::UniString> GetDrawingPrimitivesCommand::GetResponseSchema () const
{
	return GS::UniString (R"({
		"type": "object",
		"properties": {
			"success": { "type": "boolean" },
			"code": { "type": "integer", "description": "What the decomposition answered: 0, or Archicad's error with whatever had been gathered before it." },
			"counts": { "type": "array", "description": "How many primitives of each kind were drawn, by the kit's API_PrimTypeID.", "items": { "type": "integer" } },
			"polygonsSeen": { "type": "integer" },
			"polygonsWithArcs": { "type": "integer" },
			"truncated": { "type": "boolean" },
			"box": { "type": "object", "description": "The extent of the polygons handed back, in the coordinates they are given in." },
			"polygons": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"pen": { "type": "integer" },
						"fillPen": { "type": "integer" },
						"solid": { "type": "boolean" },
						"drawIndex": { "type": "integer" },
						"layer": { "type": "integer" },
						"hatchPen": { "type": "integer" },
						"hatchBackgroundPen": { "type": "integer" },
						"hatchFill": { "type": "integer" },
						"arcs": { "type": "integer" },
						"xy": { "type": "array", "description": "The vertices, x then y, every ring in turn and each closed on its first.", "items": { "type": "number" } },
						"ends": { "type": "array", "description": "The number of vertices up to and including each ring's last.", "items": { "type": "integer" } }
					}
				}
			},
			"error": { "type": "object" }
		}
	})");
}

GS::ObjectState GetDrawingPrimitivesCommand::Execute (const GS::ObjectState& parameters,
													  GS::ProcessControl& /*processControl*/) const
{
	GS::UniString guid;
	if (!parameters.Get ("drawing", guid) || guid.IsEmpty ()) {
		return Failed ("drawing must be the Drawing element's guid.", APIERR_BADPARS);
	}

	GS::Optional<VisitDatabase> visit;
	GS::ObjectState failure;
	if (!VisitNamedLayout (parameters, visit, failure)) {
		return failure;
	}

	API_Element element = {};
	element.header.guid = APIGuidFromString (guid.ToCStr ().Get ());
	GSErrCode err = ACAPI_Element_Get (&element);
	if (err != NoError) {
		return Failed ("That Drawing is not in the database asked.", err);
	}
	if (element.header.type != API_DrawingID) {
		return Failed ("That element is not a Drawing.", APIERR_BADELEMENTTYPE);
	}

	Harvest gathered;
	GS::Array<Int32> pens;
	if (parameters.Get ("pens", pens)) {
		for (Int32 pen : pens) {
			gathered.pens.Add (pen);
		}
	}
	parameters.Get ("limit", gathered.limit);

	API_Elem_Head head = {};
	head.guid = element.header.guid;
	harvest = &gathered;
	err = Api::ShapePrims (head, HarvestPrimitive);
	harvest = nullptr;

	GS::Array<Int32> counts;
	for (Int32 kind = 0; kind < PrimitiveKinds; ++kind) {
		counts.Push (gathered.counts[kind]);
	}
	GS::ObjectState result = Succeeded ();
	result.Add ("code", static_cast<Int32> (err));
	result.Add ("counts", counts);
	result.Add ("polygonsSeen", gathered.polygons);
	result.Add ("polygonsWithArcs", gathered.withArcs);
	result.Add ("truncated", gathered.truncated);
	if (gathered.boxed) {
		result.Add ("box", BoxState (gathered.box));
	}
	result.Add ("polygons", gathered.kept);
	return result;
}

}		// namespace Loriini
