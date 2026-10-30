#!/usr/bin/env bash
# Skin only (no ARM build): params, layout, framework skin, then KutilXXL's panel. Used while iterating.
set -euo pipefail
cd "$(dirname "$0")"
MPC_VST="${MPC_VST:-$PWD/third_party/mpc-vst-plugins}"
NAME="L'Cronx - VST - KutilXXL"
python3 tools/gen_params.py
mkdir -p build/host
[ -x build/host/shadow_art ] || gcc -O2 -w -I"$MPC_VST/tools/vendor/force-shadow/tools" -x c -o build/host/shadow_art "$MPC_VST/tools/shadow_art.c" -lm
rm -rf build/skin build/skin_work
SHADOW_TITLE_FONT="$PWD/art/fonts/TitilliumWeb-SemiBold.ttf" SHADOW_ART="$PWD/build/host/shadow_art" python3 "$MPC_VST/tools/gen_vst.py" vst.json 2>&1 | grep -v "QLINK Q-Link" || true
cp -r build/skin build/skin_work
python3 tools/post_skin.py "build/skin_work/$NAME/Plugin Skins" --preview build/preview
