"""KutilXXL: the one source of truth for modules, jacks, controls and screens.

Generated from this file and art/geometry.json (tools/geometry.py):
  tools/gen_params.py -> params.json, src/kutil_tables.h, layout.conf, docs/INVENTORY.md
  tools/post_skin.py  -> the three panel pictures, knob strips, touch areas, cables

Jack roles are listed per module type, inputs first then outputs, in the order the DSP indexes them (src/kutil_tables.h
writes the same order as enums). A module instance on a screen may leave out roles its picture has no jack for.
MPC stores automation by parameter INDEX: once a version ships, the parameter list is append-only.
"""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# type -> (inputs, outputs)
MODULE_TYPES = {
    "KOMPAS": (["RESET", "CLOCK", "COLLAB"], ["CV1", "TRIG1", "CV2", "TRIG2", "CV3", "TRIG3"]),
    "CRUST2": (["A_CLK_IN", "A_CLK_RESET", "A_C_IN", "A_G_IN", "A_R_IN", "B_CLK_IN", "B_CLK_RESET", "B_C_IN", "B_G_IN", "B_R_IN",
                "A_LAYER_CTRL", "A_VELOCITY", "A_TRIG", "B_PITCH_VOCT"],
               ["A_OUT", "A_ENV", "A_CV", "A_GATE", "A_EDIT", "B_OUT", "B_ENV", "B_CV", "B_GATE", "B_EDIT",
                "A_RND_OUT", "B_ENV_OUT1", "B_ENV_OUT2", "B_RND_OUT"]),
    "PIZZA": (["CV", "SYNC", "CTRL", "FM_INDEX", "EXT", "V_OCT"], ["PULSE", "MAIN", "OCT_OSC"]),
    "ABC": (["A", "B", "C", "D", "E", "F"], ["SUM1", "SUM2"]),
    "WAVEBARD": (["CLK_IN", "CLK_RESET", "C_IN", "G_IN", "R_IN", "LFO_RESET", "LFO_MOD", "LFO_IN", "AUD_L_IN", "AUD_R_IN",
                  "MIDI_IN", "TRIG", "BANK", "FREE", "NOTE", "SAMPLE", "LENGTH", "AUX"],
                 ["OUT", "ENV", "CV", "GATE", "LFO_L", "LFO_EDIT", "LFO_A", "LFO_OUT", "L_OUT", "R_OUT"]),
    "BASIL": (["TIME_CV", "SYNC", "CTRL", "L_IN", "R_IN", "MIX_CV", "V_OCT", "FEEDBACK_CV"], ["L_OUT", "R_OUT", "MIX_OUT"]),
}
MODULE_TYPES["ALCHEMIST"] = MODULE_TYPES["WAVEBARD"]

# controls per module type, in the order the DSP indexes them: (role, kind, default)
#   k knob 0..1, v slider 0..1 (a transparent knob over the picture's slider), s switch 0/1, b button (1 while held),
#   n stepped 0..7 (BANK)
CONTROLS = {
    "KOMPAS": [("LATITUDE", "k", 0.5), ("ALTITUDE", "k", 0.5), ("LONGITUDE", "k", 0.5), ("COLLAB", "s", 0), ("STZ_ZOPA", "s", 0), ("FIND", "b", 0)],
    "CRUST2": [("A_PITCH_MOD", "k", 0.5), ("A_SAMPLE_MOD", "k", 0.5), ("A_LFO_MOD", "k", 0.0),
               ("B_PITCH_MOD", "k", 0.5), ("B_SAMPLE_MOD", "k", 0.5), ("B_LFO_MOD", "k", 0.0),
               ("LAYER", "k", 0.5), ("LENGTH", "k", 0.5), ("CTRL", "k", 0.5), ("BANK", "n", 0),
               ("A_CVGATE", "s", 0), ("B_CVGATE", "s", 0), ("SHIFT", "b", 0), ("TAP", "b", 0)],
    "PIZZA": [("PITCH", "k", 0.5), ("INDEX_MOD", "k", 0.0), ("SHAPE", "k", 0.5), ("RATIO", "k", 0.5), ("DETUNE", "k", 0.5), ("WAVE", "k", 0.0),
              ("FM_INDEX_SL", "v", 0.0), ("SHAPE_SL", "v", 0.5), ("OCTAVE", "b", 0)],
    "ABC": [("A", "k", 0.7), ("B", "k", 0.7), ("C", "k", 0.7), ("D", "k", 0.7), ("E", "k", 0.7), ("F", "k", 0.7)],
    "WAVEBARD": [("PITCH_MOD", "k", 0.5), ("SAMPLE_MOD", "k", 0.5), ("LFO_MOD", "k", 0.0), ("PITCH", "k", 0.5), ("SAMPLE", "k", 0.5),
                 ("LFO", "k", 0.5), ("LENGTH", "k", 0.5), ("SHIFT", "b", 0), ("BANK", "n", 0), ("RND_CV", "s", 0), ("TIV_GATE", "s", 0)],
    "ALCHEMIST": [("PITCH_MOD", "k", 0.5), ("TIMBRE_MOD", "k", 0.5), ("LFO_MOD", "k", 0.0), ("ENV", "k", 0.5), ("PITCH", "k", 0.5),
                  ("TIMBRE", "k", 0.5), ("TEMPO", "k", 0.5), ("SHIFT", "b", 0), ("BANK", "n", 0), ("RND_CV", "s", 0), ("TIV_GATE", "s", 0)],
    "BASIL": [("DELAY", "k", 0.4), ("FEEDBACK", "k", 0.4), ("CTRL", "k", 0.5), ("DRY_WET", "v", 0.5), ("SPACE", "v", 0.3),
              ("TIME_BTN", "b", 0), ("STEREO", "s", 0), ("SPEED", "s", 0), ("RANGE", "s", 0), ("BLUR", "s", 0), ("FILTER", "s", 0),
              ("TAPS", "s", 0), ("LO_FI", "s", 0), ("LONG", "s", 0)],
}
# the ABC strip in screen 2 has four knobs only: channels without a knob run at unity (the engine treats a control the
# instance does not have as its default... for ABC that is 1.0, see engine.cc)
ABC_UNITY_IF_MISSING = True

GEOM = json.load(open(os.path.join(ROOT, "art", "geometry.json")))["screens"]
COLORS = [(216, 90, 48), (29, 158, 117), (239, 159, 39), (55, 138, 221), (212, 83, 126), (127, 119, 221), (99, 153, 34), (226, 75, 74)]
GROUP = 9            # a cable picture is switched by a parameter of at most GROUP + 1 positions (PS3100XXL 0.1.4/0.1.5)
PAGE_W, PAGE_H = 1280, 628
HEADER_H = 70
MAX_CABLES = 4       # per jack


class Mod:
    def __init__(self, idx, screen, mi, type_, g):
        self.idx = idx
        self.screen = screen
        self.mi = mi
        self.type = type_
        self.name = "%s%d" % (type_, sum(1 for m in MODS if m.type == type_) + 1)
        self.jacks = []     # Jack objects of this instance
        self.controls = []  # Control objects
        self.g = g


class Jack:
    def __init__(self, gid, mod, role, kind, x, y, r):
        self.gid = gid
        self.mod = mod
        self.role = role
        self.kind = kind          # "in" or "out"
        self.x, self.y, self.r = x, y, r      # picture pixels
        ins, outs = MODULE_TYPES[mod.type]
        self.role_index = (ins.index(role) if kind == "in" else outs.index(role))
        self.key = "%s_%s" % (mod.name.lower(), role.lower())
        self.label = role.replace("_", " ")
        self.screen = mod.screen


class Control:
    def __init__(self, mod, role, kind, x, y, r):
        self.mod = mod
        self.role = role
        self.kind = kind
        self.x, self.y, self.r = x, y, r
        names = [c[0] for c in CONTROLS[mod.type]]
        self.index = names.index(role)
        self.default = CONTROLS[mod.type][self.index][2]
        self.key = "%s_%s" % (mod.name.lower(), role.lower())
        self.label = role.replace("_", " ")


MODS = []
JACKS = []
CONTROL_LIST = []
for si, s in enumerate(GEOM):
    for mi, m in enumerate(s["modules"]):
        mod = Mod(len(MODS), si, mi, m["type"], m)
        MODS.append(mod)
        for j in m["jacks"]:
            ins, outs = MODULE_TYPES[m["type"]]
            kind = "in" if j["role"] in ins else "out"
            jk = Jack(len(JACKS), mod, j["role"], kind, j["x"], j["y"], j["r"])
            mod.jacks.append(jk)
            JACKS.append(jk)
        for c in m["controls"]:
            ct = Control(mod, c["role"], c["kind"], c["x"], c["y"], c["r"])
            mod.controls.append(ct)
            CONTROL_LIST.append(ct)

OUTS = [j for j in JACKS if j.kind == "out"]
INS = [j for j in JACKS if j.kind == "in"]
for i, o in enumerate(OUTS):
    o.out_index = i
    o.colour = COLORS[i % len(COLORS)]
for i, j in enumerate(INS):
    j.in_index = i


def ins_on_screen(s):
    return [j for j in INS if j.screen == s]


def groups_for_screen(s):
    """Inputs of a screen dealt round-robin into groups of at most GROUP: neighbours land in different groups, so one
    output can feed several adjacent inputs (one cable per output per group)."""
    ins = ins_on_screen(s)
    n = (len(ins) + GROUP - 1) // GROUP
    g = [[] for _ in range(n)]
    for k, j in enumerate(ins):
        g[k % n].append(j)
    return g


# for each input: (group index, position in group) on its screen
IN_SLOT = {}
for s in range(len(GEOM)):
    for gi, grp in enumerate(groups_for_screen(s)):
        for pi, j in enumerate(grp):
            IN_SLOT[j.gid] = (gi, pi)
N_GROUPS = {s: len(groups_for_screen(s)) for s in range(len(GEOM))}


def cable_param(out, inp):
    """(param key, option index, option count) of out's cable picture to input inp (both on the same screen)."""
    gi, pi = IN_SLOT[inp.gid]
    n = len(groups_for_screen(inp.screen)[gi])
    return "cp_%d_%d" % (out.gid, gi), 1 + pi, n + 1


# screen layout: picture scaled to fit under the header, centred
def screen_fit(s):
    from PIL import Image
    im = Image.open(os.path.join(ROOT, "art", GEOM[s]["art"]))
    w, h = im.size
    sc = min(PAGE_W / float(w), (PAGE_H - HEADER_H) / float(h))
    ox = (PAGE_W - w * sc) / 2.0
    oy = HEADER_H + ((PAGE_H - HEADER_H) - h * sc) / 2.0
    return sc, ox, oy, w, h


FIT = [screen_fit(s) for s in range(len(GEOM))]
SX = [f[0] for f in FIT]
SY = [f[0] for f in FIT]


def to_page(s, x, y):
    sc, ox, oy, _, _ = FIT[s]
    return ox + x * sc, oy + y * sc


NSCREENS = len(GEOM)
