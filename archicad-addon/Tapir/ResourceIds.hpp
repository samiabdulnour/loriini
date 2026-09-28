// Replaces Tapir's own ResourceIds.hpp, which described Tapir's menus,
// palettes and icons -- none of which are built into Loriini.
//
// The one resource the commands need is the JSON file of shared schema
// definitions, which Loriini's RFIX carries under its own ID.

#pragma once

#include "../Src/ResourceIds.hpp"

#define ID_COMMON_SCHEMA_DEFINITIONS_FILE	ID_TAPIR_SCHEMA_DEFINITIONS_FILE
