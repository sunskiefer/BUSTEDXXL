## What and why
Adds `catalog/plugins/kutilxxl.json`: **KutilXXL** by L'Cronx (sunskiefer/BUSTEDXXL), a groovebox of Bastl-style modules for Force / MPC OS, patched with touch cables across three panels, with a tap-to-zoom of each screen's top or bottom half. Release: https://github.com/sunskiefer/BUSTEDXXL/releases/tag/v0.2.0

## Testing status
Offline only (2026-10-30): engine tests under qemu-arm, skin composed offline. Not yet tested on a Force.

## Catalog check
- `catalog_check.py KutilXXL-0.2.0-mpc-armv7.zip --catalog`: `OK: kutilxxl 0.2.0 (2 warnings)` — the two warnings are install.sh/uninstall.sh differing from the current template: the L'Cronx apostrophe being shell-escaped by release.py, same as merged #520.
- SHA-256 of the release zip: `23c2510665489682b5fcd6b84dde393d6959cae99616d290b274f2ad0cca19f5`
- `catalog_build.py --check-registry`: 144 entries, 0 problems.
- The screenshot URL is pinned to the commit that added it (tag creation is not possible from this session).

## Listing status
Listed (no tested.json yet).

## Checks
- [x] catalog_check.py --catalog on the release zip
- [x] catalog_build.py --check-registry
- [x] sh -n on install.sh / uninstall.sh
- [ ] Tested on a device

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01YReGWTeDTkL5iW4TpAexSQ
