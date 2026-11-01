# Testing

Offline (`./test/run_tests.sh`): the engine is built for the Force's CPU (static musl, armv7 NEON) and run under qemu-arm.
143 checks (incl. module windows: open, close, patching across two windows): silence with no cables, tap and cable logic, cross-screen stubs, cable limits, state save/restore, Pizza at C4/C5,
ABC left/right, Kompas clocking Crust, a patched CLOCK, Force key -> CV -> Pizza, Wave Bard, Alchemist, Basil, a fuzz of random
taps, a sweep of every control, and Q-Link renaming. Skin previews: `build/preview/screen_1..3.png`.

0.2.1 loads on a Force and was reported working (2026-11-01); the list below has not been checked one by one.

Never run on a real Force:
* touch-through of cable pictures over the knobs (if touches fail, set `CABLES_ABOVE = False` in tools/post_skin.py);
* redraw of held jack rings after a display_rev change;
* CPU load of all modules at once; the picture count (about 17k pieces);
* the sound of any module against its hardware original (closed-source ones are readings, not copies);
* loading a real Wave Bard SAMPLES.bin.

Known limits: one output feeds one input per picture group on a screen (a new cable in the same group replaces the old one);
sliders have no moving handle; knob pictures share one sprite per module type and size.
