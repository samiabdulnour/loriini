// Tapir's JSON commands, as the Loriini add-on registers them.
//
// Included from Src/AddOnMain.cpp by a relative path rather than by putting
// this folder on the include path: Tapir and Loriini both have a
// ProjectCommands.hpp, an APIEnvir.h and a ResourceIds.hpp, and a quoted
// include finds the one beside the file that asks for it first, so each side
// keeps its own only while neither folder is on the other's path.

#pragma once

#include "APIEnvir.h"
#include "ACAPinc.h"

// Every Tapir command, under the "LoriiniTapir" namespace. Returns the first
// failure, so a half-registered set is reported rather than silently served.
GSErrCode InstallTapirCommands ();
