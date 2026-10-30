# Modules

"Bastl code" = the Kastle 2 DSP (MIT) used unchanged. "Own reading" = closed-source hardware, rebuilt here from how it is
documented to behave; the building blocks are still Bastl's where they fit. Signals are volts: audio ±5, CV ±5, 1 V/oct
(0 V = C4), gates 0/5.

| Module | Built from | Notes |
|---|---|---|
| Wave Bard | Bastl code: SamplePlayer (two players, fade-out), AdsrEnv, Quantizer, the firmware's parameter maps, Lfo; Wave Bard file loader | NOTE = quantized 1 V/oct, FREE = unquantized, PITCH MOD attenuverts both, LENGTH below half plays reversed, SHIFT steps the scale, BANK/SAMPLE choose the sample. Trigger = G IN, TRIG, MIDI IN, or CLK IN when none is patched. |
| Alchemist | Own reading on Bastl Fm2, MultiOscillator, Svf, AdsrEnv, Lfo | TIMBRE sweeps sine, FM, ramp, pulse and noise; ENV is the decay; TEMPO free-runs triggers when CLK IN is empty. |
| Crust 2 | Own reading on MultiOscillator, Fm2, AdsrEnv | Two drum halves A/B; BANK picks sine, triangle, square, FM; LENGTH = decay, LAYER = body/click balance, CTRL = pitch drop. |
| Pizza | Own reading on Fm2 and MultiOscillator | SHAPE morphs FM sine, ramp, pulse; RATIO and INDEX set the FM; SYNC resets the phase; OCT OSC is one octave down. |
| Basil | Bastl StereoDelay (1.2 s max) with own switches | STEREO, SPEED, RANGE, LONG, TAPS, FILTER, LO-FI, BLUR; SYNC sets the time from a clock. |
| Kompas | Own (not Bastl code) | Three-channel clock/key tracker. Clocks from the Force transport (16ths) unless CLOCK is patched; the Force's keys go to the Kompas on the screen shown (CV1/TRIG1). |
| ABC | Own | Six channels, SUM1 (A+B+C) to Force output 1, SUM2 (D+E+F) to output 2, soft-limited. |

Every jack and control is listed in `INVENTORY.md`.
