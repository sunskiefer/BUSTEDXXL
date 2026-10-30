#!/usr/bin/env python3
"""Turns the detected jack and knob positions (art/*_detected.json, from the three panel pictures) into art/geometry.json:
which module each jack and control belongs to, and its role.  Run once; art/geometry.json is then the file to edit by hand
(positions are picture pixels of art/s1.png .. s3.png).

A module is a region of its picture (x0, x1), a type (see spec.MODULE_TYPES) and, for jacks, an ordered list of roles
read off the art: rows top to bottom, left to right inside a row ('rows'), or columns left to right, top to bottom
inside a column ('cols')."""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
J = json.load(open(os.path.join(ROOT, "art", "jacks_detected.json")))
K = json.load(open(os.path.join(ROOT, "art", "knobs_detected.json")))

# extra jacks the detector missed or that the art leaves out (a_pizza: the COLLAB jack beside Latitude; c_basil: D+E+F)
EXTRA_J = {"a_pizza": [(40, 165, 22)], "b_wavebard": [(659, 601, 30)], "c_basil": [(873, 172, 28), (1403, 594, 28), (1403, 860, 28)]}
DROP_J = {"b_wavebard": [(1013, 35)], "c_basil": [(478, 730), (645, 730)], "a_pizza": []}

W = lambda *r: list(r)

SCREENS = [
    dict(id="s1", src="a_pizza", art="s1.png", modules=[
        dict(type="KOMPAS", x=(0, 245), jacks="cols", roles=["COLLAB", "RESET", "CLOCK", "CV1", "TRIG1", "CV2", "TRIG2", "CV3", "TRIG3"]),
        dict(type="CRUST2", x=(246, 872), jacks="crust2"),
        dict(type="PIZZA", x=(873, 1240), jacks="pizza"),
        dict(type="ABC", x=(1241, 1441), jacks="abc"),
    ]),
    dict(id="s2", src="b_wavebard", art="s2.png", modules=[
        dict(type="WAVEBARD", x=(0, 606), jacks="seqv8"),
        dict(type="KOMPAS", x=(607, 790), jacks="cols", roles=["RESET", "CLOCK", "CV1", "TRIG1", "CV2", "TRIG2", "CV3", "TRIG3"]),
        dict(type="ABC", x=(791, 985), jacks="abc"),
        dict(type="WAVEBARD", x=(986, 1592), jacks="seqv8"),
    ]),
    dict(id="s3", src="c_basil", art="s3.png", modules=[
        dict(type="KOMPAS", x=(0, 245), jacks="cols", roles=["COLLAB", "RESET", "CLOCK", "CV1", "TRIG1", "CV2", "TRIG2", "CV3", "TRIG3"]),
        dict(type="ALCHEMIST", x=(246, 905), jacks="seqv10"),
        dict(type="BASIL", x=(906, 1290), jacks="basil"),
        dict(type="ABC", x=(1291, 1454), jacks="abc"),
    ]),
]

SEQV10_ROW1 = ["CLK_IN", "CLK_RESET", "C_IN", "G_IN", "R_IN", "LFO_RESET", "LFO_MOD", "LFO_IN", "AUD_L_IN", "AUD_R_IN"]
SEQV10_ROW2 = ["OUT", "ENV", "CV", "GATE", "LFO_L", "LFO_EDIT", "LFO_A", "LFO_OUT", "L_OUT", "R_OUT"]
SEQV8_ROW1 = ["CLK_IN", "CLK_RESET", "C_IN", "G_IN", "LFO_RESET", "LFO_MOD", "AUD_L_IN", "AUD_R_IN"]
SEQV8_ROW2 = ["OUT", "ENV", "CV", "GATE", "LFO_L", "LFO_A", "L_OUT", "R_OUT"]
SEQV8_ROW3 = ["MIDI_IN", "TRIG", "BANK", "FREE", "NOTE", "SAMPLE", "LENGTH", "AUX"]


def rows_of(js, tol=34):
    js = sorted(js, key=lambda j: j[1])
    rows = []
    for j in js:
        if rows and abs(rows[-1][0] - j[1]) <= tol:
            rows[-1][1].append(j)
            rows[-1][0] = sum(x[1] for x in rows[-1][1]) / len(rows[-1][1])
        else:
            rows.append([j[1], [j]])
    return [sorted(r[1], key=lambda j: j[0]) for r in rows]


def cols_of(js, tol=60):
    js = sorted(js, key=lambda j: j[0])
    cols = []
    for j in js:
        if cols and abs(cols[-1][0] - j[0]) <= tol:
            cols[-1][1].append(j)
            cols[-1][0] = sum(x[0] for x in cols[-1][1]) / len(cols[-1][1])
        else:
            cols.append([j[0], [j]])
    return [sorted(c[1], key=lambda j: j[1]) for c in cols]


def assign(kind, js, m):
    """-> list of (role, jack)"""
    out = []
    if kind == "cols":
        # Kompas: first the COLLAB jack (top left, above the Reset row) if the role list has it, then Reset/Clock row,
        # then (CV, TRIG) pairs. Rows are clustered by y; the collab jack is the one above the first row.
        roles = list(m["roles"])
        js = sorted(js, key=lambda j: (round(j[1] / 45), j[0]))
        rr = rows_of(js, 40)
        flat = [j for r in rr for j in r]
        return list(zip(roles, flat))
    if kind == "seqv10":
        rr = rows_of(js, 40)
        return list(zip(SEQV10_ROW1, rr[0])) + list(zip(SEQV10_ROW2, rr[1]))
    if kind == "seqv8":
        rr = rows_of(js, 45)
        return list(zip(SEQV8_ROW1, rr[0])) + list(zip(SEQV8_ROW2, rr[1])) + list(zip(SEQV8_ROW3, rr[2]))
    if kind == "crust2":
        rr = rows_of(js, 40)
        top1 = ["CLK_IN", "CLK_RESET", "C_IN", "G_IN", "R_IN"]
        top2 = ["OUT", "ENV", "CV", "GATE", "EDIT"]
        r1, r2, r3 = rr[0], rr[1], rr[2]
        res = []
        for v, sl in (("A_", slice(0, 5)), ("B_", slice(5, 10))):
            res += list(zip([v + x for x in top1], r1[sl]))
            res += list(zip([v + x for x in top2], r2[sl]))
        res += list(zip(["A_LAYER_CTRL", "A_VELOCITY", "A_TRIG", "A_RND_OUT", "B_PITCH_VOCT", "B_ENV_OUT1", "B_ENV_OUT2", "B_RND_OUT"], r3))
        return res
    if kind == "pizza":
        # C/V (top), row SYNC CTRL FM_INDEX EXT, row V_OCT PULSE MAIN OCT_OSC
        js = sorted(js, key=lambda j: j[1])
        cv = js[0]
        rest = rows_of(js[1:], 40)
        return [("CV", cv)] + list(zip(["SYNC", "CTRL", "FM_INDEX", "EXT"], rest[0])) + list(zip(["V_OCT", "PULSE", "MAIN", "OCT_OSC"], rest[1]))
    if kind == "abc":
        cc = cols_of(js)
        left, right = cc[0], cc[1]
        n = len(left)
        res = list(zip(["A", "B", "C", "SUM1"][:n], left))
        res += list(zip(["D", "E", "F", "SUM2"][:len(right)], right))
        return res
    if kind == "basil":
        js = sorted(js, key=lambda j: j[1])
        tcv = js[0]
        rest = rows_of(js[1:], 40)
        res = [("TIME_CV", tcv)]
        res += list(zip(["SYNC", "CTRL", "L_IN", "R_IN", "MIX_CV"], rest[0]))
        res += list(zip(["V_OCT", "FEEDBACK_CV", "L_OUT", "R_OUT", "MIX_OUT"], rest[1]))
        return res
    raise SystemExit("unknown jack kind " + kind)


# Controls: (role, x, y, r) in picture pixels, by screen id and module index in SCREENS. Knobs are the detected knob
# discs (art/knobs_detected.json); the rest were read off the pictures by eye (plates, small switches, sliders).
# kind: k knob, s switch (toggle), b momentary button, n stepped (BANK), v slider (a transparent knob over the slider)
KOMPAS_C = lambda cx, cy, ky: [("LATITUDE", "k"), ("ALTITUDE", "k"), ("LONGITUDE", "k")]
CONTROLS = {
    ("s1", 0): [("LATITUDE", "k", 103, 162, 38), ("ALTITUDE", "k", 106, 322, 38), ("LONGITUDE", "k", 106, 483, 38),
                ("COLLAB", "s", 85, 258, 30), ("STZ_ZOPA", "s", 82, 420, 30), ("FIND", "b", 117, 965, 34)],
    ("s1", 1): [("A_PITCH_MOD", "k", 315, 468, 38), ("A_SAMPLE_MOD", "k", 320, 640, 38), ("A_LFO_MOD", "k", 318, 802, 38),
                ("B_PITCH_MOD", "k", 787, 468, 38), ("B_SAMPLE_MOD", "k", 787, 640, 38), ("B_LFO_MOD", "k", 787, 802, 38),
                ("LAYER", "k", 558, 445, 36), ("LENGTH", "k", 558, 650, 40), ("CTRL", "k", 459, 871, 40), ("BANK", "n", 659, 871, 40),
                ("A_CVGATE", "s", 493, 765, 24), ("B_CVGATE", "s", 624, 765, 24), ("SHIFT", "b", 417, 927, 26), ("TAP", "b", 690, 927, 26)],
    ("s1", 2): [("PITCH", "k", 1056, 199, 50), ("INDEX_MOD", "k", 1049, 439, 45), ("SHAPE", "k", 1148, 720, 38),
                ("RATIO", "k", 926, 449, 28), ("DETUNE", "k", 1174, 438, 28), ("WAVE", "k", 929, 708, 28),
                ("FM_INDEX_SL", "v", 1052, 310, 70), ("SHAPE_SL", "v", 1100, 600, 60), ("OCTAVE", "b", 927, 257, 34)],
    ("s1", 3): [("A", "k", 1281, 247, 30), ("B", "k", 1276, 402, 30), ("C", "k", 1280, 545, 30),
                ("D", "k", 1370, 328, 30), ("E", "k", 1382, 422, 22), ("F", "k", 1366, 490, 30)],
    ("s2", 0): [("PITCH_MOD", "k", 90, 463, 42), ("SAMPLE_MOD", "k", 90, 632, 42), ("LFO_MOD", "k", 90, 800, 42),
                ("PITCH", "k", 532, 470, 42), ("SAMPLE", "k", 533, 632, 42), ("LFO", "k", 533, 800, 42), ("LENGTH", "k", 303, 545, 60),
                ("SHIFT", "b", 210, 818, 48), ("BANK", "n", 402, 818, 48), ("RND_CV", "s", 240, 703, 24), ("TIV_GATE", "s", 369, 703, 24)],
    ("s2", 1): [("LATITUDE", "k", 693, 130, 36), ("ALTITUDE", "k", 699, 270, 38), ("LONGITUDE", "k", 697, 411, 38),
                ("COLLAB", "s", 680, 215, 30), ("STZ_ZOPA", "s", 676, 351, 30), ("FIND", "b", 705, 833, 34)],
    ("s2", 2): [("D", "k", 920, 130, 28), ("A", "k", 920, 243, 28), ("B", "k", 920, 335, 28), ("E", "k", 920, 437, 28)],
    ("s2", 3): [("PITCH_MOD", "k", 1062, 461, 42), ("SAMPLE_MOD", "k", 1060, 632, 42), ("LFO_MOD", "k", 1060, 800, 42),
                ("PITCH", "k", 1502, 470, 42), ("SAMPLE", "k", 1502, 630, 42), ("LFO", "k", 1503, 802, 42), ("LENGTH", "k", 1288, 550, 60),
                ("SHIFT", "b", 1186, 817, 48), ("BANK", "n", 1379, 817, 48), ("RND_CV", "s", 1220, 703, 24), ("TIV_GATE", "s", 1348, 703, 24)],
    ("s3", 0): [("LATITUDE", "k", 128, 151, 40), ("ALTITUDE", "k", 132, 314, 40), ("LONGITUDE", "k", 126, 475, 40),
                ("COLLAB", "s", 80, 252, 30), ("STZ_ZOPA", "s", 90, 411, 30), ("FIND", "b", 120, 918, 34)],
    ("s3", 1): [("PITCH_MOD", "k", 316, 461, 40), ("TIMBRE_MOD", "k", 317, 638, 40), ("LFO_MOD", "k", 316, 831, 40),
                ("ENV", "k", 563, 563, 52), ("PITCH", "k", 847, 462, 40), ("TIMBRE", "k", 845, 638, 40), ("TEMPO", "k", 845, 832, 40),
                ("SHIFT", "b", 493, 863, 45), ("BANK", "n", 640, 860, 45), ("RND_CV", "s", 478, 730, 24), ("TIV_GATE", "s", 645, 730, 24)],
    ("s3", 2): [("DELAY", "k", 1083, 150, 55), ("FEEDBACK", "k", 1092, 442, 45), ("CTRL", "k", 1182, 700, 40),
                ("DRY_WET", "v", 1093, 305, 70), ("SPACE", "v", 1130, 600, 60),
                ("TIME_BTN", "b", 960, 232, 32), ("STEREO", "s", 1220, 173, 28), ("SPEED", "s", 958, 395, 24), ("RANGE", "s", 960, 463, 24),
                ("BLUR", "s", 966, 643, 24), ("FILTER", "s", 1040, 680, 28), ("TAPS", "s", 968, 716, 24), ("LO_FI", "s", 1222, 390, 24), ("LONG", "s", 1229, 462, 24)],
    ("s3", 3): [("D", "k", 1403, 160, 22), ("A", "k", 1329, 240, 22), ("E", "k", 1403, 310, 22), ("B", "k", 1329, 384, 22),
                ("F", "k", 1403, 452, 22), ("C", "k", 1329, 519, 22)],
}


def main():
    geom = []
    for s in SCREENS:
        src = s["src"]
        jacks = [tuple(j) for j in J[src]]
        jacks = [j for j in jacks if not any(abs(j[0] - a) < 14 and abs(j[1] - b) < 14 for a, b in DROP_J.get(src, []))]
        for e in EXTRA_J.get(src, []):
            if not any(abs(j[0] - e[0]) < 20 and abs(j[1] - e[1]) < 20 for j in jacks):
                jacks.append(e)
        screen = dict(id=s["id"], art=s["art"], modules=[])
        for mi, m in enumerate(s["modules"]):
            js = [j for j in jacks if m["x"][0] <= j[0] <= m["x"][1]]
            pairs = assign(m["jacks"], js, m)
            ctl = [dict(role=r, kind=k, x=x, y=y, r=rr) for r, k, x, y, rr in CONTROLS.get((s["id"], mi), [])]
            screen["modules"].append(dict(type=m["type"], x=list(m["x"]), jacks=[dict(role=r, x=int(j[0]), y=int(j[1]), r=int(j[2])) for r, j in pairs],
                                          controls=ctl, unassigned=len(js) - len(pairs)))
        geom.append(screen)
    json.dump(dict(screens=geom), open(os.path.join(ROOT, "art", "geometry.json"), "w"), indent=1)
    for s in geom:
        for m in s["modules"]:
            print(s["id"], m["type"], len(m["jacks"]), "jacks", "unassigned", m["unassigned"])


if __name__ == "__main__":
    main()
