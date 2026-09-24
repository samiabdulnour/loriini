#include "Launch.hpp"

#include "FileSystem.hpp"
#include "Location.hpp"
#include "Name.hpp"

#if defined (WINDOWS)
	#include <windows.h>
	#include <shellapi.h>
#else
	#include <crt_externs.h>
	#include <spawn.h>
	#include <sys/wait.h>

	#include <cstring>
	#include <string>
	#include <vector>
#endif

namespace Loriini {

namespace {

// What the app is called on disk. Looked for beside the add-on itself, which
// is where the install instructions put it: one folder holding the add-on and
// the program, so moving Loriini to another workstation is copying a folder.
//
// On a Mac the program is an application bundle -- a folder the Finder shows
// as one file -- so what sits beside LoriiniAddOn_AC26_Mac.bundle is
// Loriini.app.
#if defined (WINDOWS)
const char* APP_FILE_NAME = "Loriini.exe";
#else
const char* APP_FILE_NAME = "Loriini.app";
#endif


// The folder this add-on is loaded from.
//
// Asked of Archicad rather than assumed, because there is no fixed place: an
// office without administrator rights registers its add-on folder by hand in
// the Add-On Manager, and on this practice's workstations that is a folder
// under Documents rather than anything in Program Files.
bool OwnFolder (IO::Location& folder)
{
	IO::Location ownFile;
	if (ACAPI_GetOwnLocation (&ownFile) != NoError) {
		return false;
	}
	folder = ownFile;
	return folder.DeleteLastLocalName () == NoError;
}


#if !defined (WINDOWS)

// Runs `open` and says whether it managed to start the app.
//
// Through LaunchServices rather than by running the program inside the bundle
// directly. LaunchServices is what brings the window to the front with its own
// Dock icon, and it starts the app in a session of its own rather than as a
// child of Archicad -- so nothing of Archicad's environment is inherited, the
// same reason the study travels as an argument (see Launch.hpp).
//
// `-n` asks for a new instance every time, which is what ShellExecute does on
// Windows. Without it `open` only brings a Loriini that is already running to
// the front and drops `--args`, so a palette button pressed while the window
// is open would ask for its study and be ignored.
bool OpenWithLaunchServices (const GS::UniString& application, const GS::UniString& study)
{
	// Owned strings first and pointers into them after, because posix_spawn
	// wants `char*` and the helper `ToCStr` returns does not outlive its line --
	// the same trap the Windows branch below had to be rebuilt around.
	std::vector<std::string> words = { "/usr/bin/open", "-n", "-a", application.ToCStr (CC_UTF8).Get () };
	if (!study.IsEmpty ()) {
		words.push_back ("--args");
		words.push_back ("--study");
		words.push_back (study.ToCStr (CC_UTF8).Get ());
	}
	std::vector<char*> argv;
	for (std::string& word : words) {
		argv.push_back (&word[0]);
	}
	argv.push_back (nullptr);

	// `environ` itself is out of reach from a bundle -- only a program being
	// linked whole gets it -- so it is asked for, as environ(7) says to.
	pid_t child = 0;
	const int refused = posix_spawn (&child, argv[0], nullptr, nullptr, argv.data (), *_NSGetEnviron ());
	if (refused != 0) {
		ACAPI_WriteReport ("Loriini: could not run /usr/bin/open: " + GS::UniString (std::strerror (refused)), true);
		return false;
	}

	// `open` hands the launch over and exits, within a second or so, and its
	// exit status is the one place a refusal shows. Waited for, so that goes
	// to the report window rather than nowhere, and so Archicad is not left
	// holding a finished child it never collected.
	int status = 0;
	if (waitpid (child, &status, 0) != child) {
		return false;
	}
	return WIFEXITED (status) && WEXITSTATUS (status) == 0;
}

#endif

}		// namespace


void StartTheApp (const GS::UniString& study)
{
	IO::Location folder;
	if (!OwnFolder (folder)) {
		ACAPI_WriteReport ("Loriini: could not work out where the add-on is installed.", true);
		return;
	}

	IO::Location application = folder;
	application.AppendToLocal (IO::Name (APP_FILE_NAME));

	bool exists = false;
	if (application.IsEmpty () || IO::fileSystem.Contains (application, &exists) != NoError || !exists) {
		const GS::UniString path = application.ToDisplayText ();
		ACAPI_WriteReport ("Loriini: " + path + " is not there. Copy " + APP_FILE_NAME + " into the same "
						   "folder as the add-on.", true);
		return;
	}

#if defined (WINDOWS)
	const GS::UniString path = application.ToDisplayText ();

	// Both the string *and* the wide buffer it lends out are held in named
	// locals, which is the half the first version missed.
	//
	// `ToUStr ()` does not return a pointer into the UniString; it returns a
	// helper object that owns the wide buffer, and `Get ()` points into that.
	// Keeping only the UniString alive therefore left `parameters` dangling at
	// the semicolon, because the helper died there. It happened to be harmless
	// from the menu, which passes no study and leaves the pointer null, and
	// would have bitten the first palette button anybody pressed.
	//
	// `auto` because the helper's type is private to GS::UniString -- the same
	// reason `Support.cpp` spells `ToCStr ()`'s result that way.
	const GS::UniString arguments = study.IsEmpty () ? GS::UniString () : "--study " + study;
	const auto argumentChars = arguments.ToUStr ();
	LPCWSTR parameters = nullptr;
	if (!arguments.IsEmpty ()) {
		parameters = reinterpret_cast<LPCWSTR> (argumentChars.Get ());
	}

	// The path's buffer is held the same way, for the same reason. It was safe
	// where it stood -- a temporary lives to the end of the full expression it
	// is written in -- but two pointers into two helper objects with different
	// lifetimes is a thing to have to work out rather than read.
	const auto pathChars = path.ToUStr ();
	const HINSTANCE started = ShellExecuteW (nullptr, L"open",
											 reinterpret_cast<LPCWSTR> (pathChars.Get ()),
											 parameters, nullptr, SW_SHOWNORMAL);
	// ShellExecute returns a value above 32 on success. The convention is
	// odd and worth naming rather than leaving as a bare number.
	const bool ok = reinterpret_cast<INT_PTR> (started) > 32;
	if (!ok) {
		ACAPI_WriteReport ("Loriini: Windows refused to start " + path, true);
	}
#else
	// The path as the file system spells it, for `open`; ToDisplayText is
	// for people, and only promises to be readable.
	GS::UniString path;
	if (application.ToPath (&path) != NoError) {
		ACAPI_WriteReport ("Loriini: could not work out the path of " + application.ToDisplayText (), true);
		return;
	}
	if (!OpenWithLaunchServices (path, study)) {
		ACAPI_WriteReport ("Loriini: macOS refused to start " + path + ". If it was downloaded, it may "
						   "still be quarantined: open it once from the Finder with Control-click > Open.", true);
	}
#endif
}

}		// namespace Loriini
