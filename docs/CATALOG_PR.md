## What and why
Adds `catalog/plugins/kutilxxl.json`: **KutilXXL** by L'Cronx (sunskiefer/BUSTEDXXL), a groovebox of Bastl-style modules for Force / MPC OS, patched with touch cables across three screens, with a jack window per module (touch a module, see its jacks big and named, patch across two windows). Release: https://github.com/sunskiefer/BUSTEDXXL/releases/tag/v0.2.1

## Testing status
Loads and runs on an Akai Force (owner report, 2026-11-01); offline engine tests (143 checks under qemu-arm) pass. A full per-module test on the device is still to come.

## Catalog check
See the CI run of the release workflow (`catalog_check.py --catalog` on the zip) and the SHA-256 in the release notes. The install.sh/uninstall.sh warnings are the L'Cronx apostrophe being shell-escaped by release.py, same as merged #520.

## Listing status
Listed (no tested.json yet).

## Checks
- [x] catalog_check.py --catalog on the release zip (release workflow)
- [x] sh -n on install.sh / uninstall.sh (release workflow)
- [ ] catalog_build.py --check-registry (run on the PR branch)
- [ ] Fully tested on a device

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01YReGWTeDTkL5iW4TpAexSQ
