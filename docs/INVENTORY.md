# KutilXXL inventory

Every module, control and jack of the instrument, generated from `tools/spec.py` and `art/geometry.json`.

## Screen 1

### KOMPAS1 (KOMPAS)

Controls: latitude (k), altitude (k), longitude (k), collab (s), stz zopa (s), find (b)

Inputs: collab, reset, clock

Outputs: cv1, trig1, cv2, trig2, cv3, trig3

### CRUST21 (CRUST2)

Controls: a pitch mod (k), a sample mod (k), a lfo mod (k), b pitch mod (k), b sample mod (k), b lfo mod (k), layer (k), length (k), ctrl (k), bank (n), a cvgate (s), b cvgate (s), shift (b), tap (b)

Inputs: a clk in, a clk reset, a c in, a g in, a r in, b clk in, b clk reset, b c in, b g in, b r in, a layer ctrl, a velocity, a trig, b pitch voct

Outputs: a out, a env, a cv, a gate, a edit, b out, b env, b cv, b gate, b edit, a rnd out, b env out1, b env out2, b rnd out

### PIZZA1 (PIZZA)

Controls: pitch (k), index mod (k), shape (k), ratio (k), detune (k), wave (k), fm index sl (v), shape sl (v), octave (b)

Inputs: cv, sync, ctrl, fm index, ext, v oct

Outputs: pulse, main, oct osc

### ABC1 (ABC)

Controls: a (k), b (k), c (k), d (k), e (k), f (k)

Inputs: a, b, c, d, e, f

Outputs: sum1, sum2

## Screen 2

### WAVEBARD1 (WAVEBARD)

Controls: pitch mod (k), sample mod (k), lfo mod (k), pitch (k), sample (k), lfo (k), length (k), shift (b), bank (n), rnd cv (s), tiv gate (s)

Inputs: clk in, clk reset, c in, g in, lfo reset, lfo mod, aud l in, aud r in, midi in, trig, bank, free, note, sample, length, aux

Outputs: out, env, cv, gate, lfo l, lfo a, l out, r out

### KOMPAS2 (KOMPAS)

Controls: latitude (k), altitude (k), longitude (k), collab (s), stz zopa (s), find (b)

Inputs: reset, clock

Outputs: cv1, trig1, cv2, trig2, cv3, trig3

### ABC2 (ABC)

Controls: d (k), a (k), b (k), e (k)

Inputs: a, b, c, d, e, f

Outputs: sum1, sum2

### WAVEBARD2 (WAVEBARD)

Controls: pitch mod (k), sample mod (k), lfo mod (k), pitch (k), sample (k), lfo (k), length (k), shift (b), bank (n), rnd cv (s), tiv gate (s)

Inputs: clk in, clk reset, c in, g in, lfo reset, lfo mod, aud l in, aud r in, midi in, trig, bank, free, note, sample, length, aux

Outputs: out, env, cv, gate, lfo l, lfo a, l out, r out

## Screen 3

### KOMPAS3 (KOMPAS)

Controls: latitude (k), altitude (k), longitude (k), collab (s), stz zopa (s), find (b)

Inputs: collab, reset, clock

Outputs: cv1, trig1, cv2, trig2, cv3, trig3

### ALCHEMIST1 (ALCHEMIST)

Controls: pitch mod (k), timbre mod (k), lfo mod (k), env (k), pitch (k), timbre (k), tempo (k), shift (b), bank (n), rnd cv (s), tiv gate (s)

Inputs: clk in, clk reset, c in, g in, r in, lfo reset, lfo mod, lfo in, aud l in, aud r in

Outputs: out, env, cv, gate, lfo l, lfo edit, lfo a, lfo out, l out, r out

### BASIL1 (BASIL)

Controls: delay (k), feedback (k), ctrl (k), dry wet (v), space (v), time btn (b), stereo (s), speed (s), range (s), blur (s), filter (s), taps (s), lo fi (s), long (s)

Inputs: time cv, sync, ctrl, l in, r in, mix cv, v oct, feedback cv

Outputs: l out, r out, mix out

### ABC3 (ABC)

Controls: d (k), a (k), e (k), b (k), f (k), c (k)

Inputs: a, b, c, d, e, f

Outputs: sum1, sum2

12 modules, 104 controls, 96 inputs, 70 outputs.
