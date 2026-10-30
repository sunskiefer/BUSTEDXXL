#pragma once
// KutilXXL shim for the Kastle 2 codec class: only the block size the DSP code sizes its buffers by.
#include <stddef.h>
class I2S
{
public:
    static constexpr size_t kAudioBufferSize = 32; // frames per block (Kastle 2 uses 48; the Force host block is 128)
    static constexpr size_t kAudioBufferFrames = kAudioBufferSize * 2;
};
