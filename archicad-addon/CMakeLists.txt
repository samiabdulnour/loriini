# Build for the Loriini Archicad add-on, on Windows and on macOS.
#
# Adapted from the dev kit's own AddOnCommandTest example, which is the
# authority for how an Archicad add-on links: the resource compiler step, the
# two exported ordinals, and the sweep over every module folder in the kit are
# all load-bearing and none of them are obvious.
#
# The Mac kit ships the same example with its macOS half still in it, and the
# Mac branches below are that half put back: a loadable bundle rather than an
# .apx, both processor architectures, the kit's static library and its
# frameworks. Where the example and Tapir's own Mac build differ, Tapir wins,
# because Tapir's commands are most of this add-on and its build is the one
# proven with them on the Xcode the runners carry now.
#
# Two things differ from the example on purpose:
#
#   AC_API_DEVKIT_DIR has no default. The example points at its own parent
#   because it lives inside the kit; this add-on does not, and a wrong guess
#   there fails deep in a compile rather than here.
#
#   AC_ADDON_NAME carries the Archicad version. An .apx is compiled against
#   one major version and cannot be shared across them, so the version belongs
#   in the file name where a person copying it into an Add-Ons folder can see
#   it -- the same reason Tapir's own releases are named that way.
#
# Generated the way Tapir's CI generates its Archicad 26 builds, which are the
# only combinations proven to work for this kit:
#
#   cmake -B Build -G "Visual Studio 17 2022" -A x64 -T v142 \
#         -DAC_API_DEVKIT_DIR=<the folder containing Support> archicad-addon
#
#   cmake -B Build -G Xcode \
#         -DAC_API_DEVKIT_DIR=<the folder containing Support> archicad-addon

cmake_minimum_required (VERSION 3.16)

function (SetCompilerOptions target)
	# The language each kit's headers are written in, as Tapir sets it: 26's
	# are C++14, 27 and 28 need 17, and from 29 they use 20.
	if (AC_VERSION LESS 27)
		target_compile_features (${target} PUBLIC cxx_std_14)
	elseif (AC_VERSION LESS 29)
		target_compile_features (${target} PUBLIC cxx_std_17)
	else ()
		target_compile_features (${target} PUBLIC cxx_std_20)
	endif ()
	target_compile_options (${target} PUBLIC "$<$<CONFIG:Debug>:-DDEBUG>")
	if (WIN32)
		target_compile_options (${target} PUBLIC /W3 /WX /wd4996 /Zc:wchar_t-)
	else ()
		# Warnings are errors here too, as /WX makes them on Windows. The
		# list switched off is the kit example's, with the four Tapir added
		# for newer clangs -- non-c-typedef-for-linkage onwards. Tapir builds
		# its own commands under exactly these, and they are most of this
		# add-on; anything else clang finds is Loriini's to fix.
		target_compile_options (${target} PUBLIC -Wall -Wextra -Werror -fvisibility=hidden
			-Wno-multichar
			-Wno-ctor-dtor-privacy
			-Wno-invalid-offsetof
			-Wno-ignored-qualifiers
			-Wno-reorder
			-Wno-overloaded-virtual
			-Wno-unused-parameter
			-Wno-missing-field-initializers
			-Wno-unknown-pragmas
			-Wno-missing-braces
			-Wno-unused-private-field
			-Wno-return-std-move
			-Wno-unused-value
			-Wno-switch
			-Wno-deprecated
			-Wno-non-c-typedef-for-linkage
			-Wno-uninitialized-const-reference
			-Wno-shorten-64-to-32
			-Wno-sign-compare
		)
	endif ()
endfunction ()

function (SubDirList dirlist curdir)
	file (GLOB children RELATIVE "${curdir}" "${curdir}/*")
	set (result "")
	foreach (child ${children})
		if (IS_DIRECTORY "${curdir}/${child}")
			list (APPEND result ${child})
		endif ()
	endforeach ()
	set (${dirlist} ${result} PARENT_SCOPE)
endfunction ()

function (GetModuleNameFromModuleFolderName module folder)
	set (result "")
	if (${folder} MATCHES "^.*Lib$")
		string (REGEX REPLACE "^(.*)Lib$" "\\1" result ${folder})
	elseif (WIN32 AND ${folder} MATCHES "^Communication.*$")
		string (REGEX REPLACE "^Communication(.*)$" "Communication.\\1" result ${folder})
	else ()
		set (result ${folder})
	endif ()
	set (${module} ${result} PARENT_SCOPE)
endfunction ()

function (AddGSModule target folder)
	if (WIN32)
		target_include_directories (${target} PUBLIC "${AC_API_DEVKIT_DIR}/Support/Modules/${folder}")
	else ()
		# A system folder, as Tapir has it, so -Werror stays about this
		# add-on: a newer clang finds warnings inside the kit's headers, and
		# nothing here can fix a Graphisoft header.
		target_include_directories (${target} SYSTEM PUBLIC "${AC_API_DEVKIT_DIR}/Support/Modules/${folder}")
	endif ()
	set (module "")
	GetModuleNameFromModuleFolderName (module ${folder})
	# On a Mac the libraries are the kit's frameworks, and they are linked all
	# at once further down rather than one per module folder.
	set (ModuleLibPath "${AC_API_DEVKIT_DIR}/Support/Modules/${folder}/Win/${module}Imp.lib")
	if (WIN32 AND EXISTS ${ModuleLibPath})
		target_link_libraries (${target} ${ModuleLibPath})
	endif ()
endfunction ()

set_property (GLOBAL PROPERTY USE_FOLDERS ON)

set (CMAKE_SUPPRESS_REGENERATION 1)
set (CMAKE_CONFIGURATION_TYPES Debug;Release;RelWithDebInfo)

# Before project(), where CMake has only the machine it is running on to go by
# -- which is the point: an add-on is built on the platform it is for, and
# there is no cross-compiling one.
if (WIN32)
	set (AC_ADDON_PLATFORM Win)
elseif (APPLE)
	set (AC_ADDON_PLATFORM Mac)
	# Both kinds of Mac Archicad runs natively on from 26. The kit's static
	# library carries an Intel and an Apple silicon half, and an add-on
	# without the half Archicad is running as is not loaded at all. The
	# oldest macOS is set below, once the kit has said which it is.
	set (CMAKE_OSX_ARCHITECTURES "x86_64;arm64" CACHE STRING "" FORCE)
	set (CMAKE_XCODE_ATTRIBUTE_ONLY_ACTIVE_ARCH "NO")
else ()
	message (FATAL_ERROR "An Archicad add-on is built on Windows or on a Mac, and there is no kit for ${CMAKE_HOST_SYSTEM_NAME}.")
endif ()

set (AC_API_DEVKIT_DIR "" CACHE PATH "The folder holding the API Development Kit's Support directory.")
set (AC_VERSION 26 CACHE STRING "Archicad major version to build for.")
set (AC_ADDON_LANGUAGE "INT" CACHE STRING "Add-On language code.")
# The platform is in the name for the same reason the version is: the .apx
# and the .bundle are two different files, and a person copying one into an
# Add-Ons folder should be able to see which one they are holding.
set (AC_ADDON_NAME "LoriiniAddOn_AC${AC_VERSION}_${AC_ADDON_PLATFORM}" CACHE STRING "Add-On name.")

if (NOT AC_API_DEVKIT_DIR)
	message (FATAL_ERROR "AC_API_DEVKIT_DIR is not set. Point it at the folder that contains the kit's Support directory.")
endif ()

# The kit states its own Archicad version, so the value passed in is checked
# against it rather than trusted. Building the 26 add-on against the 28 kit
# produces a file Archicad loads and then behaves strangely with, which is a
# far worse failure than a refusal here.
set (ACAPINC_FILE_LOCATION ${AC_API_DEVKIT_DIR}/Support/Inc/ACAPinc.h)
if (EXISTS ${ACAPINC_FILE_LOCATION})
	file (READ ${ACAPINC_FILE_LOCATION} ACAPIncContent)
	string (REGEX MATCHALL "#define[ \t]+ServerMainVers_([0-9][0-9])" VersionList ${ACAPIncContent})
	set (ARCHICAD_VERSION ${CMAKE_MATCH_1})
	message (STATUS "API DevKit at ${AC_API_DEVKIT_DIR} is for Archicad ${ARCHICAD_VERSION}")
	if (NOT ARCHICAD_VERSION STREQUAL AC_VERSION)
		message (FATAL_ERROR "AC_VERSION says ${AC_VERSION} but the kit is for Archicad ${ARCHICAD_VERSION}.")
	endif ()
else ()
	message (FATAL_ERROR "No ACAPinc.h under ${AC_API_DEVKIT_DIR}/Support/Inc; AC_API_DEVKIT_DIR is wrong.")
endif ()

# The oldest macOS is the one the kit's own frameworks declare: 10.15 for 26
# and 27, 11 for 28 and 29, 14.1 for 30. Read rather than written down, so a
# new kit cannot leave the add-on claiming a macOS its Archicad never ran on.
if (APPLE)
	file (READ "${AC_API_DEVKIT_DIR}/Support/Frameworks/GSRoot.framework/Versions/A/Resources/Info.plist" GSRootPlist)
	string (REGEX REPLACE ".*<key>GSBuildNum</key>[^0-9]*([0-9]+).*" "\\1" GSBuildNum "${GSRootPlist}")
	string (REGEX REPLACE ".*<key>LSMinimumSystemVersion</key>[^0-9]*([0-9.]+).*" "\\1" LORIINI_MINIMUM_MACOS "${GSRootPlist}")
	set (CMAKE_OSX_DEPLOYMENT_TARGET ${LORIINI_MINIMUM_MACOS} CACHE STRING "" FORCE)
endif ()

# Where the kit keeps its static library moved in 27, from a folder per
# platform to Lib itself.
if (AC_VERSION LESS 27)
	set (AC_API_LIB_DIR "${AC_API_DEVKIT_DIR}/Support/Lib/${AC_ADDON_PLATFORM}")
	if (APPLE)
		set (AC_API_LIB_DIR "${AC_API_DEVKIT_DIR}/Support/Lib/Mactel")
	endif ()
else ()
	set (AC_API_LIB_DIR "${AC_API_DEVKIT_DIR}/Support/Lib")
endif ()

if (WIN32)
	add_definitions (-DUNICODE -D_UNICODE)
else ()
	# What every Graphisoft header asks to know it is on a Mac.
	add_definitions (-Dmacintosh=1)
endif ()
add_definitions (-DACExtension)

project (${AC_ADDON_NAME})

set (AddOnSourcesFolder ./Src)
set (AddOnResourcesFolder .)
set (ResourceObjectsDir ${CMAKE_BINARY_DIR}/ResourceObjects)

if (WIN32)
	file (GLOB AddOnResourceFiles
		${AddOnResourcesFolder}/R${AC_ADDON_LANGUAGE}/*.grc
		${AddOnResourcesFolder}/RFIX/*.grc
		${AddOnResourcesFolder}/RFIX.win/*.rc2
	)
else ()
	file (GLOB AddOnResourceFiles
		${AddOnResourcesFolder}/R${AC_ADDON_LANGUAGE}/*.grc
		${AddOnResourcesFolder}/RFIX/*.grc
		${AddOnResourcesFolder}/RFIX.mac/*.plist.in
	)
endif ()

source_group ("Resources" FILES ${AddOnResourceFiles})
add_custom_target (
	AddOnResources ALL
	DEPENDS "${ResourceObjectsDir}/AddOnResources.stamp"
	SOURCES ${AddOnResourceFiles}
)

get_filename_component (AddOnSourcesFolderAbsolute "${CMAKE_CURRENT_LIST_DIR}/${AddOnSourcesFolder}" ABSOLUTE)
get_filename_component (AddOnResourcesFolderAbsolute "${CMAKE_CURRENT_LIST_DIR}/${AddOnResourcesFolder}" ABSOLUTE)
# The resource compiler is Tapir's copy of the kit's script, in Tools: the
# kit stopped shipping its own in 30, and Tapir's knows what changed in 29.
get_filename_component (APIDevKitSupportFolderAbsolute "${AC_API_DEVKIT_DIR}/Support" ABSOLUTE)

if (WIN32)
	add_custom_command (
		OUTPUT "${ResourceObjectsDir}/AddOnResources.stamp"
		DEPENDS ${AddOnResourceFiles}
		COMMENT "Compiling resources..."
		COMMAND ${CMAKE_COMMAND} -E make_directory "${ResourceObjectsDir}"
		COMMAND python "${CMAKE_CURRENT_LIST_DIR}/Tools/CompileResources.py" "${AC_ADDON_LANGUAGE}" "${AC_VERSION}" "${APIDevKitSupportFolderAbsolute}" "${AddOnSourcesFolderAbsolute}" "${AddOnResourcesFolderAbsolute}" "${ResourceObjectsDir}" "${ResourceObjectsDir}/${AC_ADDON_NAME}.res"
		COMMAND ${CMAKE_COMMAND} -E touch "${ResourceObjectsDir}/AddOnResources.stamp"
	)
else ()
	# On a Mac the resources are not linked in: the kit's script writes them
	# into the bundle as files -- the menus' strings, one .rsrd per resource,
	# the icons as .tif -- and PkgInfo is what marks the folder as an add-on.
	# They go into the bundle of the configuration being built, while the
	# stamp is shared, so a build folder should build one configuration, as
	# CI does. Python by name rather than `python`, which a Mac need not have.
	find_package (Python3 REQUIRED COMPONENTS Interpreter)
	set (AddOnBundleContents "${CMAKE_BINARY_DIR}/$<CONFIG>/${AC_ADDON_NAME}.bundle/Contents")
	add_custom_command (
		OUTPUT "${ResourceObjectsDir}/AddOnResources.stamp"
		DEPENDS ${AddOnResourceFiles}
		COMMENT "Compiling resources..."
		COMMAND ${CMAKE_COMMAND} -E make_directory "${ResourceObjectsDir}"
		COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_LIST_DIR}/Tools/CompileResources.py" "${AC_ADDON_LANGUAGE}" "${AC_VERSION}" "${APIDevKitSupportFolderAbsolute}" "${AddOnSourcesFolderAbsolute}" "${AddOnResourcesFolderAbsolute}" "${ResourceObjectsDir}" "${AddOnBundleContents}/Resources"
		COMMAND ${CMAKE_COMMAND} -E copy "${AC_API_DEVKIT_DIR}/Support/Inc/PkgInfo" "${AddOnBundleContents}/PkgInfo"
		COMMAND ${CMAKE_COMMAND} -E touch "${ResourceObjectsDir}/AddOnResources.stamp"
	)
endif ()

file (GLOB AddOnHeaderFiles ${AddOnSourcesFolder}/*.h ${AddOnSourcesFolder}/*.hpp)
file (GLOB AddOnSourceFiles ${AddOnSourcesFolder}/*.c ${AddOnSourcesFolder}/*.cpp)
set (AddOnFiles ${AddOnHeaderFiles} ${AddOnSourceFiles})
source_group ("Sources" FILES ${AddOnFiles})

# Tapir's commands, built in so the Tapir add-on is no longer needed beside
# this one. See Tapir/README.md for which version, and what was left out.
#
# Deliberately NOT added to the include path. Tapir and Loriini each have a
# ProjectCommands.hpp, an APIEnvir.h and a ResourceIds.hpp; a quoted include
# looks beside the including file first, so each side finds its own only as
# long as neither folder is on the other's search path.
set (TapirSourcesFolder ./Tapir)
file (GLOB TapirHeaderFiles ${TapirSourcesFolder}/*.h ${TapirSourcesFolder}/*.hpp)
file (GLOB TapirSourceFiles ${TapirSourcesFolder}/*.cpp)
set (TapirFiles ${TapirHeaderFiles} ${TapirSourceFiles})
source_group ("Tapir" FILES ${TapirFiles})

if (WIN32)
	add_library (AddOn SHARED ${AddOnFiles} ${TapirFiles})
else ()
	add_library (AddOn MODULE ${AddOnFiles} ${TapirFiles})
endif ()

set_target_properties (AddOn PROPERTIES OUTPUT_NAME ${AC_ADDON_NAME})

if (WIN32)
	set_target_properties (AddOn PROPERTIES SUFFIX ".apx")

	target_link_options (AddOn PUBLIC "${ResourceObjectsDir}/${AC_ADDON_NAME}.res")

	# The two ordinals Archicad looks an add-on up by. Without them the .apx
	# builds, loads, and is never called.
	target_link_options (AddOn PUBLIC /export:GetExportedFuncAddrs,@1 /export:SetImportedFuncAddrs,@2)
else ()
	# LoriiniAddOn_AC26_Mac.bundle. Its Info.plist is written from
	# RFIX.mac/Info.plist.in the way Tapir writes its own: the version is the
	# Archicad version and the kit's build number, and the oldest macOS is
	# the one the kit's frameworks declare -- both read out of the kit, so a
	# newer kit cannot leave the plist claiming an older one.
	string (TOLOWER "com.samiabdulnour.${AC_ADDON_NAME}" LORIINI_BUNDLE_IDENTIFIER)
	string (REPLACE "_" "-" LORIINI_BUNDLE_IDENTIFIER "${LORIINI_BUNDLE_IDENTIFIER}")
	set (LORIINI_BUNDLE_VERSION "${AC_VERSION}.0.0.${GSBuildNum}")
	configure_file ("${AddOnResourcesFolderAbsolute}/RFIX.mac/Info.plist.in" "${CMAKE_BINARY_DIR}/Info.plist" @ONLY)
	message (STATUS "${AC_ADDON_NAME}.bundle is ${LORIINI_BUNDLE_IDENTIFIER} ${LORIINI_BUNDLE_VERSION}, macOS ${LORIINI_MINIMUM_MACOS} and later")

	# USE_HEADERMAP off, and it matters: an Xcode header map resolves a
	# quoted include by file name across the whole target, and Loriini and
	# Tapir each have a ProjectCommands.hpp, an APIEnvir.h and a
	# ResourceIds.hpp. Off, an include finds the file beside it first, which
	# is what the Tapir note above relies on.
	set_target_properties (AddOn PROPERTIES
		BUNDLE TRUE
		MACOSX_BUNDLE_INFO_PLIST "${CMAKE_BINARY_DIR}/Info.plist"
		LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/$<CONFIG>"
		XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${LORIINI_BUNDLE_IDENTIFIER}"
		XCODE_ATTRIBUTE_USE_HEADERMAP NO
	)
endif ()

target_include_directories (AddOn PUBLIC ${AddOnSourcesFolder})
if (WIN32)
	target_include_directories (AddOn PUBLIC ${AC_API_DEVKIT_DIR}/Support/Inc)
else ()
	target_include_directories (AddOn SYSTEM PUBLIC ${AC_API_DEVKIT_DIR}/Support/Inc)
endif ()

if (WIN32)
	# A debug library where the kit has one; 26's does, and later kits
	# may not.
	set (AcapDebugLib "${AC_API_LIB_DIR}/ACAP_STATD.lib")
	if (NOT EXISTS ${AcapDebugLib})
		set (AcapDebugLib "${AC_API_LIB_DIR}/ACAP_STAT.lib")
	endif ()
	target_link_libraries (AddOn
		"$<$<CONFIG:Debug>:${AcapDebugLib}>"
		"$<$<CONFIG:Release>:${AC_API_LIB_DIR}/ACAP_STAT.lib>"
		"$<$<CONFIG:RelWithDebInfo>:${AC_API_LIB_DIR}/ACAP_STAT.lib>"
	)
else ()
	# One library for every configuration: the Mac kit has no debug build of
	# it, and the example links this one throughout.
	find_library (CocoaFramework Cocoa)
	target_link_libraries (AddOn
		"${AC_API_LIB_DIR}/libACAP_STAT.a"
		${CocoaFramework}
	)
endif ()

SetCompilerOptions (AddOn)
add_dependencies (AddOn AddOnResources)

get_filename_component (APIDevKitModulesDir "${AC_API_DEVKIT_DIR}/Support/Modules" ABSOLUTE)
set (GSModules "")
SubDirList (GSModules "${APIDevKitModulesDir}")
foreach (gsModule ${GSModules})
	AddGSModule (AddOn ${gsModule})
endforeach ()

if (NOT WIN32)
	# Every framework in the kit, the way Tapir links its Mac build, rather
	# than the example's one per module folder. 44 of the 49 folders have a
	# framework of the same name, and the other 97 frameworks have no folder
	# at all; linking them all cannot leave out the one a Tapir command needs,
	# and Archicad carries every one of them, so none costs a thing at load.
	file (GLOB GSFrameworks "${AC_API_DEVKIT_DIR}/Support/Frameworks/*.framework")
	target_link_libraries (AddOn ${GSFrameworks})
endif ()
