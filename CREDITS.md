# Credits and licences

KutilXXL is GPL-3.0-or-later (L'Cronx).

* **Bastl Instruments Kastle 2 firmware** (https://github.com/bastl-instruments/kastle2), MIT licence, (c) Bastl Instruments.
  `src/bastl/common/**` (DSP: SamplePlayer, StereoDelay, Fm2, MultiOscillator, AdsrEnv, Lfo, Svf, Quantizer, ...) and the
  parameter maps of the Wave Bard app are used as they are; the licence text is kept in `src/bastl/LICENSE-kastle2-MIT`.
  `src/bastl/shim/` is this project's small stand-in for the Pico SDK headers.
* Bastl's open hardware/library material: bastl library CC-BY-SA 3.0, bastl-vcv GPL-3.0 (read for behaviour, not copied).
* Bastl's sample file (SAMPLES.bin) is all rights reserved and is not included.
* mpc-vst-plugins wrapper (`third_party/mpc-vst-plugins`): see its own licence.
* Titillium Web font (SIL OFL 1.1).

Kompas, Crust 2, Pizza, ABC, Alchemist and Basil are closed-source hardware; the versions here are this project's own readings
of how they behave, built from Bastl DSP blocks where they fit. They are not Bastl's code. No brand names appear on the panels.
