// Platform settings, before anything from the API is included.
//
// Every add-on carries its own copy of this. It looks like it belongs to the
// Development Kit and it does not: `APIEnvir.h` lives in each example's own
// `Src` folder, not in the kit's `Inc`, so an add-on that includes it without
// having one fails on the very first line of the very first file with
// `C1083: Cannot open include file`.
//
// What it actually does matters here. `WINDOWS` is defined from the compiler's
// own `_MSC_VER`, and `Launch.cpp` picks how to start the app on exactly that
// symbol -- so without this file that choice would silently take the Mac
// branch on a Windows build.
//
// On a Mac the compiler defines nothing of the sort; the build passes
// `macintosh` itself (CMakeLists.txt), and CoreServices is what the kit's own
// example includes for it before any Graphisoft header.

#ifndef LORIINI_APIENVIR_H
#define LORIINI_APIENVIR_H

#if defined (_MSC_VER)
	#if !defined (WINDOWS)
		#define WINDOWS
	#endif
#endif

#if defined (WINDOWS)
	#include "Win32Interface.hpp"
#endif

#if defined (macintosh)
	#include <CoreServices/CoreServices.h>
#endif

#if !defined (ACExtension)
	#define ACExtension
#endif

#endif
