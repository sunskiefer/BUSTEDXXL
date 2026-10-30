#!/usr/bin/env bash
# Offline tests, ARM only: the engine built for the Force's CPU (static, musl) and run under qemu-arm.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/gen_params.py >/dev/null
mkdir -p build/arm
ZIG="${ZIG:-python3 -m ziglang}"
TGT="-target arm-linux-musleabihf -mcpu=generic+v7a+vfp3d16-d32-neon+thumb2 -ffp-contract=off"
BASTL="$(find src/bastl/common -name '*.cpp' ! -name 'Fft.cpp' ! -name 'fastcode.cpp' | sort)"
$ZIG c++ $TGT -O2 -std=gnu++23 -fno-exceptions -fno-rtti -Wall -include cstddef -include cstdint -include algorithm -include cstdlib \
  -Isrc -Isrc/bastl -Isrc/bastl/shim -Ibuild -Ithird_party/mpc-vst-plugins/wrapper \
  src/engine.cc $BASTL test/engine_test.cc -static -lm -o build/arm/engine_test
qemu-arm build/arm/engine_test
