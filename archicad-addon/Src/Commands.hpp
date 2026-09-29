// The three things Archicad can do and no add-on outside it can ask for.
//
// Everything else this tool needs from Archicad is already reachable through
// Tapir, and stays there. These three are here because there is no command
// for them anywhere: verified against Tapir 1.5.8's own embedded command
// catalogue and against a live Archicad 26, which answers `API.Get3DProjection
// Info` with code 2002, "not found".
//
//   GetProjection          reads the 3D window's projection, sun included.
//   SetProjection          points it along a given direction at a given date.
//   CreateDocumentFrom3D   makes a 3D Document carrying its own projection.
//   SetDocumentFrom3D      re-aims one already made, and sets its shadow fill.
//
// The first is not merely a diagnostic. `API_AxonoPars::tranmat` is a matrix
// whose row order and signs the documentation does not pin down, so the only
// way to know that `SetProjection` builds it the way Archicad reads it is to
// set an angle by hand, read it back, and compare. `GetProjection` is that
// instrument, and it is why it ships first.

#if !defined (LORIINI_COMMANDS_HPP)
#define LORIINI_COMMANDS_HPP

#pragma once

#include "Support.hpp"

namespace Loriini {

// Reads the current 3D projection.
//
// Runs on a parallel thread and touches nothing, so it is safe to call while
// a person is working. Answers with the axonometric parameters when the
// window is parallel and the perspective ones when it is not, plus the raw
// twelve numbers of the transformation matrix, which is the point.
class GetProjectionCommand : public Command {
public:
	virtual GS::String						GetName () const override;
	virtual GS::Optional<GS::UniString>		GetInputParametersSchema () const override;
	virtual GS::Optional<GS::UniString>		GetResponseSchema () const override;

	virtual API_AddOnCommandExecutionPolicy	GetExecutionPolicy () const override
	{
		return API_AddOnCommandExecutionPolicy::ScheduleForExecutionOnMainThread;
	}

	virtual GS::ObjectState					Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& processControl) const override;
};


// Points the 3D window along a direction, at a date and time.
//
// The direction is given as a bearing and an altitude in degrees, because
// that is what a sun position is and what the caller already has. The sun is
// given as a *date*, not as angles: `API_SunAngleSettings` carries a
// `sunPosOpt` of `API_SunPosition_GivenByDate`, so Archicad computes the sun
// from the project's own location and the date it is handed. That is worth
// preferring over pushing angles in. It means the sun in the drawing is
// Archicad's own, computed from the georeferencing the project carries, and a
// disagreement with this tool's astronomy becomes visible instead of being
// papered over by writing our answer into both sides.
class SetProjectionCommand : public Command {
public:
	virtual GS::String						GetName () const override;
	virtual GS::Optional<GS::UniString>		GetInputParametersSchema () const override;
	virtual GS::Optional<GS::UniString>		GetResponseSchema () const override;

	virtual API_AddOnCommandExecutionPolicy	GetExecutionPolicy () const override
	{
		return API_AddOnCommandExecutionPolicy::ScheduleForExecutionOnMainThread;
	}

	virtual bool							IsProcessWindowVisible () const override { return true; }

	virtual GS::ObjectState					Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& processControl) const override;
};


// Creates a 3D Document, and sets the projection and sun it keeps.
//
// This is the step the office does by hand, once per hour, and the reason it
// cannot be scripted today: Tapir has no `Create3DDocuments` and never had
// one. In C++ it is a database create followed by a settings write, and the
// settings struct is the interesting half. `API_DocumentFrom3DType` carries
// its own `projectionSetting`, so a 3D Document remembers the angle and the
// sun it was made at rather than borrowing whatever the 3D window shows now.
// That is what makes seven of them on one sheet mean seven different hours.
//
// The vectorial sun shadows are here too, since roadmap R1. The first build
// said they were not, on the grounds that `vectSunShadow` belongs to
// `API_3DStyle` and a style can be pinned on a view -- true of a view of the
// 3D window, and not of a document's view, which Tapir refuses a 3D style
// (the sun views found that). A document's shadows are its own: the "Vectorial
// Sun Shadows" of its Model Display, which a new document takes from
// `API_DocumentFrom3DDefaults::vectSunShadow`, with the fill they are drawn in
// in `attributeOptions`. So `sunShadows` switches the defaults for the one
// creation and puts them back, and `shadowFill` writes the fill onto both.
class CreateDocumentFrom3DCommand : public Command {
public:
	virtual GS::String						GetName () const override;
	virtual GS::Optional<GS::UniString>		GetInputParametersSchema () const override;
	virtual GS::Optional<GS::UniString>		GetResponseSchema () const override;

	virtual API_AddOnCommandExecutionPolicy	GetExecutionPolicy () const override
	{
		return API_AddOnCommandExecutionPolicy::ScheduleForExecutionOnMainThread;
	}

	virtual bool							IsProcessWindowVisible () const override { return true; }

	virtual GS::ObjectState					Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& processControl) const override;
};


// Re-aims a 3D Document this add-on made, sets its sun, and its shadow fill.
//
// A 3D Document cannot be deleted through the API -- `APIDb_DeleteDatabaseID`
// takes details, worksheets and layouts only -- so a second run over the
// same hours finds the first run's documents under their names. Without this
// they would keep whatever sun and aim they were made with; with it a rerun
// is the same as a first run. `effects3D` is copied whole from a document
// read back with the effects wanted, because which of its bits is the sun
// shadow the kit does not say.
class SetDocumentFrom3DCommand : public Command {
public:
	virtual GS::String						GetName () const override;
	virtual GS::Optional<GS::UniString>		GetInputParametersSchema () const override;
	virtual GS::Optional<GS::UniString>		GetResponseSchema () const override;

	virtual API_AddOnCommandExecutionPolicy	GetExecutionPolicy () const override
	{
		return API_AddOnCommandExecutionPolicy::ScheduleForExecutionOnMainThread;
	}

	virtual GS::ObjectState					Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& processControl) const override;
};


// -- Set3DFilter ------------------------------------------------------------
//
// What storeys the 3D window converts, which is the "Filter Elements in 3D"
// dialog and nothing Tapir can reach: its `SetViewSettings` carries the layer
// combination, the renovation filter, the 3D style and the pen set onto a
// view, and no storey range.
//
// It matters because a saved 3D view keeps the filter it was made under. The
// context model is homed on the storey nearest level zero -- `AHD`, 0.000, on
// the Bondi file -- while the building itself stands on `GROUND` at 10.0 and
// the storeys above it. With the window filtered to one storey the two can
// never appear together, so every sun view carries half a model and says
// nothing about it.
//
// `APIEnv_Get3DImageSetsID` and `APIEnv_Change3DImageSetsID` carry
// `API_3DFilterAndCutSettings`, whose `allStories` is the whole question:
// false means `firstStory3D..lastStory3D` applies. Read first and written back
// whole, because the same struct carries the marquee filter and the element
// type filter, and a command that rebuilt it from nothing would quietly throw
// away a marquee somebody set.
class Set3DFilterCommand : public Command {
public:
	virtual GS::String						GetName () const override;
	virtual GS::Optional<GS::UniString>		GetInputParametersSchema () const override;
	virtual GS::Optional<GS::UniString>		GetResponseSchema () const override;

	virtual API_AddOnCommandExecutionPolicy	GetExecutionPolicy () const override
	{
		return API_AddOnCommandExecutionPolicy::ScheduleForExecutionOnMainThread;
	}

	virtual GS::ObjectState					Execute (const GS::ObjectState& parameters,
													 GS::ProcessControl& processControl) const override;
};

}		// namespace Loriini

#endif
