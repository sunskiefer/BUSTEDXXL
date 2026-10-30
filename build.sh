#!/usr/bin/env bash
# Build KutilXXL for MPC OS Gen1 (armv7-a hard-float, glibc <= 2.31 so it also loads on MPC OS 2.x).
#   ./build.sh                     (MPC_VST=... to use another framework checkout)
# Needs: python3 + Pillow, a host gcc (for shadow_art) and Zig (pip install ziglang). No Docker.
# Output: build/package/L'Cronx - VST - KutilXXL/  (skin + kutilxxl.so)
set -euo pipefail
cd "$(dirname "$0")"
MPC_VST="${MPC_VST:-$PWD/third_party/mpc-vst-plugins}"
ZIG="${ZIG:-python3 -m ziglang}"
NAME="L'Cronx - VST - KutilXXL"
python3 tools/gen_params.py
mkdir -p build/host build/arm
[ -x build/host/shadow_art ] || gcc -O2 -w -I"$MPC_VST/tools/vendor/force-shadow/tools" -x c -o build/host/shadow_art "$MPC_VST/tools/shadow_art.c" -lm
rm -rf build/skin
SHADOW_TITLE_FONT="$PWD/art/fonts/TitilliumWeb-SemiBold.ttf" SHADOW_ART="$PWD/build/host/shadow_art" python3 "$MPC_VST/tools/gen_vst.py" vst.json 2>&1 | grep -v "QLINK Q-Link" || true
python3 tools/post_skin.py "build/skin/$NAME/Plugin Skins" --preview build/preview
TGT="-target arm-linux-gnueabihf.2.31 -mcpu=generic+v7a+vfp3d16-d32-neon+thumb2 -ffp-contract=off"
COMMON="-O2 -fPIC -fvisibility=hidden -ffunction-sections -fdata-sections -DNDEBUG -w"
CXX="-std=gnu++23 -fno-exceptions -fno-rtti -include cstddef -include cstdint -include algorithm -include cstdlib"
INC="-Isrc -Isrc/bastl -Isrc/bastl/shim -Ibuild -I$MPC_VST/wrapper"
SRCS="src/engine.cc $(find src/bastl/common -name '*.cpp' ! -name Fft.cpp ! -name fastcode.cpp | sort | tr '\n' ' ')"
OBJS=""
for f in $SRCS; do
  o="build/arm/$(echo "$f" | tr / _).o"
  if [ ! -f "$o" ] || [ "$f" -nt "$o" ] || [ src/kutil_ids.h -nt "$o" ]; then $ZIG c++ $TGT $COMMON $CXX $INC -c "$f" -o "$o"; fi
  OBJS="$OBJS $o"
done
$ZIG cc $TGT $COMMON -std=gnu11 -Ibuild -c "$MPC_VST/wrapper/vst2_wrap.c" -o build/arm/vst2_wrap.o
printf '{\n  global: VSTPluginMain;\n  local: *;\n};\n' > build/arm/exports.map
$ZIG c++ $TGT -shared -fPIC -Wl,--no-undefined -Wl,--version-script=build/arm/exports.map -Wl,--gc-sections -Wl,-s \
  $OBJS build/arm/vst2_wrap.o -lm -ldl -lpthread -o build/arm/kutilxxl.so
PKG="build/package/$NAME"
rm -rf build/package && mkdir -p "$PKG"
cp -r "build/skin/$NAME/." "$PKG/"
cp build/arm/kutilxxl.so "$PKG/"
echo "-> $PKG"
