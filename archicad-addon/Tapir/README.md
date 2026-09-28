# Tapir, built into Loriini

The command sources of the **Tapir Archicad add-on**, copied into this add-on so a
workstation needs Loriini alone. Before this, every study needed two add-ons
installed side by side: Tapir for the ~60 ordinary JSON commands the Python side
uses (reading elements, layers, the navigator, creating hatches, layouts, views...),
and Loriini for the handful of things no JSON command exposes at all.

- Upstream: <https://github.com/ENZYME-APD/tapir-archicad-automation>
- Version: **1.5.8** (tag `1.5.8`, commit `ce033d6`), the version the Python side was
  verified against live on Archicad 26 (see `docs/archicad.md`). `GetAddOnVersion`
  still answers `1.5.8`, so every version gate in `connection.py` holds unchanged.
- Licence: MIT, `LICENSE` in this folder. Keep it with the code.

## What was changed

Only four things, so an upgrade is a copy plus these four again:

1. **The namespace.** `CommandBase.cpp` answers `LoriiniTapir` instead of
   `TapirCommand`. Loriini's own commands already use the names `CreateSlabs` and
   `CreateTexts` with different parameters, and a standalone Tapir left installed
   would otherwise claim the same namespace and names as this add-on.
2. **Registration.** `TapirCommands.cpp` is generated from Tapir's `AddOnMain.cpp`:
   the registration list verbatim, as one function, `InstallTapirCommands`, called
   at the end of Loriini's `Initialize`. The generator is the recipe in
   "Upgrading" below.
3. **Resources.** `ResourceIds.hpp` is replaced by a two-line shim. The only resource
   the commands read is the shared schema file, which Loriini carries as
   `RFIX/Images/TapirCommonSchemaDefinitions.json` under `ID_TAPIR_SCHEMA_DEFINITIONS_FILE`.
4. **Left out:** everything that makes Tapir an add-on of its own rather than a set of
   commands: `AddOnMain.cpp`, its menus and icons, `TapirPalette`, `ScriptUIPalette`
   and the two Script UI commands, `AboutDialog`, `VersionChecker` (the self-updater),
   `Config`/`UvManager` (the palette's Python runner), and the developer-only
   `GenerateDocumentation` command. 233 commands remain.

No command's code was edited.

## Talking to it

`ArchicadConnection.run_tapir` sends to `LoriiniTapir` first. If this add-on is too old
to have the namespace, and a standalone Tapir is still installed, it falls back to
`TapirCommand` for the rest of the connection, so a workstation can update the two
in either order.

## Upgrading

1. `git archive <tag> archicad-addon/Sources LICENSE` from the Tapir repository.
2. Copy every `*.cpp`, `*.hpp`, `*.h` from `Sources` here, except the files listed in
   point 4 and `ResourceIds.hpp`. Copy `LICENSE`, and
   `Sources/RFIX/Images/CommonSchemaDefinitions.json` over
   `RFIX/Images/TapirCommonSchemaDefinitions.json`.
3. Set `CommandNamespace` back to `"LoriiniTapir"` in `CommandBase.cpp`.
4. Regenerate `TapirCommands.cpp` from the new `AddOnMain.cpp`: keep its `#include`s
   minus the UI headers, the `RegisterCommand` template, and every command group from
   "Application Commands" up to, not including, "Script UI Commands".
5. Update the version above, and `VERIFIED_AGAINST_TAPIR_VERSION` in
   `src/sun_study/archicad/connection.py` once it has been checked live.
