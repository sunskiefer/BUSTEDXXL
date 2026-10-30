#!/usr/bin/env python3
"""Writes everything that follows from tools/spec.py (and so from art/geometry.json):

    python3 tools/gen_params.py

  params.json        the VST parameter list for mpc-vst-plugins' gen_vst.py (index = order; append-only once shipped)
  src/kutil_ids.h    P_* indices, module / jack / control tables, picture-switch tables for the engine
  layout.conf        the skin layout: three screens, each a set of controls shown while 'view' is at it
  docs/INVENTORY.md  every module, control and jack, checked against the build
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec  # noqa: E402

Y0 = 86          # Force Shadow y of the plugin page's top
NAV = [("nav_prev", "<", 70, 36), ("nav_next", ">", 1210, 36)]   # page coordinates of the centres
KNOB_MIN_R, KNOB_MAX_R = 6, 58
SLIDER_R = 5     # sliders are transparent knobs: their own filmstrip size, blank


def trigger(key, name, refresh=False):
    p = {"key": key, "name": name, "min": 0.0, "max": 1.0, "default": 0.0, "momentary": True, "type": "trigger"}
    if refresh:
        p["refresh_display"] = True
    return p


def knob_radius(c):
    """Page radius of a control's knob strip."""
    if c.kind == "v":
        return SLIDER_R
    sc = spec.FIT[c.mod.screen][0]
    return max(KNOB_MIN_R, min(KNOB_MAX_R, int(round(c.r * sc))))   # c.r is already a page radius


def pretty(c):
    return "%s %s" % (c.mod.name, c.label.title())


def build_params():
    P = []
    for c in spec.CONTROL_LIST:
        nm = pretty(c)
        if c.kind in ("k", "v"):
            P.append({"key": c.key, "name": nm, "min": 0.0, "max": 1.0, "default": float(c.default), "dynamic_display": True})
        elif c.kind == "n":
            P.append({"key": c.key, "name": nm, "min": 0.0, "max": 7.0, "default": float(c.default), "display": "int"})
        elif c.kind == "s":
            P.append({"key": c.key, "name": nm, "options": ["Off", "On"], "default": int(c.default)})
        elif c.kind == "b":
            P.append(trigger(c.key, nm))
        else:
            raise ValueError(c.kind)
    P.append({"key": "view", "name": "Screen", "options": ["Screen 1", "Screen 2", "Screen 3"], "default": 0})
    for k, lbl, _, _ in NAV:
        P.append(trigger(k, "Screen " + ("Prev" if k.endswith("prev") else "Next"), True))
    for j in spec.JACKS:
        P.append(trigger("tap_" + j.key, "Jack %s %s" % (j.mod.name, j.label), True))
    P.append({"key": "patch_info", "name": "Patch Info", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    for i in range(16):
        P.append({"key": "ql%d" % (i + 1), "name": "Q-Link %d" % (i + 1), "min": 0.0, "max": 1.0, "default": 0.0,
                  "dynamic_name": True, "dynamic_display": True})
    # picture switches: engine-driven, contiguous. kind 0 cable pair picture, 1 cross-screen output stub,
    # 2 cross-screen input stub, 3 held ring.
    for o in spec.OUTS:
        for gi, grp in enumerate(spec.groups_for_screen(o.screen)):
            P.append({"key": "cp_%d_%d" % (o.gid, gi), "name": "Cable %s %s %d" % (o.mod.name, o.label, gi + 1),
                      "options": ["-"] + [j.key for j in grp], "default": 0, "poll": False})
    for o in spec.OUTS:
        for t in range(spec.NSCREENS):
            if t != o.screen:
                P.append({"key": "xo_%d_%d" % (o.gid, t), "name": "Out %s %s to %d" % (o.mod.name, o.label, t + 1),
                          "options": ["-", "on"], "default": 0, "poll": False})
    for j in spec.INS:
        for t in range(spec.NSCREENS):
            if t != j.screen:
                P.append({"key": "xi_%d_%d" % (j.gid, t), "name": "In %s %s from %d" % (j.mod.name, j.label, t + 1),
                          "options": ["-"] + ["col%d" % k for k in range(len(spec.COLORS))], "default": 0, "poll": False})
    for h in range((len(spec.JACKS) + spec.GROUP - 1) // spec.GROUP):
        grp = spec.JACKS[h * spec.GROUP:(h + 1) * spec.GROUP]
        P.append({"key": "hd_%d" % h, "name": "Held %d" % (h + 1), "options": ["-"] + [j.key for j in grp], "default": 0,
                  "poll": False})
    keys = [p["key"] for p in P]
    assert len(keys) == len(set(keys)), "duplicate keys"
    return P


def write_params(P):
    with open(os.path.join(ROOT, "params.json"), "w") as f:
        json.dump({"name": "KutilXXL", "params": P}, f, indent=1)
        f.write("\n")


def cid(k):
    return "P_" + k.upper()


def cstr(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def pic_switches(P):
    """-> list of (kind, a, b) in param order, for the engine: kind 0 cp (a out gid, b group), 1 xo (out gid, target),
    2 xi (in gid, source), 3 hd (group, -)"""
    out = []
    for p in P:
        k = p["key"]
        if k.startswith("cp_") or k.startswith("xo_") or k.startswith("xi_") or k.startswith("hd_"):
            parts = k.split("_")
            kind = {"cp": 0, "xo": 1, "xi": 2, "hd": 3}[parts[0]]
            a = int(parts[1])
            b = int(parts[2]) if len(parts) > 2 else 0
            out.append((kind, a, b))
    return out


def write_header(P):
    L = ["// Generated by tools/gen_params.py from tools/spec.py -- do not edit.", "#pragma once", ""]
    for i, p in enumerate(P):
        L.append("#define %s %d" % (cid(p["key"]), i))
    L.append("#define P_COUNT %d" % len(P))
    L.append("#define P_TAP_FIRST %d" % [i for i, p in enumerate(P) if p["key"].startswith("tap_")][0])

    def num(p, k, d):
        t = "%.6g" % float(p.get(k, d))
        return t + (".0f" if "." not in t and "e" not in t else "f")
    L.append("static const char *const P_KEY[P_COUNT] = {%s};" % ", ".join(cstr(p["key"]) for p in P))
    L.append("static const char *const P_NAME[P_COUNT] = {%s};" % ", ".join(cstr(p["name"]) for p in P))
    L.append("static const float P_MIN[P_COUNT] = {%s};" % ", ".join(num(p, "min", 0) for p in P))
    L.append("static const float P_MAX[P_COUNT] = {%s};" % ", ".join(
        ("%d.0f" % (len(p["options"]) - 1)) if "options" in p else num(p, "max", 1) for p in P))
    L.append("static const float P_DEF[P_COUNT] = {%s};" % ", ".join(num(p, "default", 0) for p in P))
    L.append("static const unsigned char P_NOPTS[P_COUNT] = {%s};" % ", ".join(str(len(p.get("options", []))) for p in P))
    L.append("static const unsigned char P_TRIG[P_COUNT] = {%s};" % ", ".join("1" if p.get("type") == "trigger" else "0" for p in P))
    L.append("static const unsigned char P_INT[P_COUNT] = {%s};" % ", ".join(
        "1" if p.get("display") == "int" else "0" for p in P))
    L.append("#define N_CONTROLS %d   // the sound controls come first: indices 0..N_CONTROLS-1" % len(spec.CONTROL_LIST))
    L.append("#define N_SCREENS %d" % spec.NSCREENS)
    L.append("#define MAX_CABLES %d" % spec.MAX_CABLES)
    L.append("")
    # module types
    types = list(spec.MODULE_TYPES.keys())
    L.append("enum { %s, N_TYPES };" % ", ".join("T_" + t for t in types))
    for t in types:
        ins, outs = spec.MODULE_TYPES[t]
        L.append("enum { %s };  // %s inputs" % (", ".join("%s_IN_%s" % (t, r) for r in ins), t))
        L.append("enum { %s };  // %s outputs" % (", ".join("%s_OUT_%s" % (t, r) for r in outs), t))
        ctl = spec.CONTROLS[t]
        L.append("enum { %s };  // %s controls" % (", ".join("%s_C_%s" % (t, c[0]) for c in ctl), t))
    L.append("")
    L.append("#define N_MODS %d" % len(spec.MODS))
    L.append("static const unsigned char MOD_TYPE[N_MODS] = {%s};" % ", ".join("T_" + m.type for m in spec.MODS))
    L.append("static const unsigned char MOD_SCREEN[N_MODS] = {%s};" % ", ".join(str(m.screen) for m in spec.MODS))
    L.append("static const char *const MOD_NAME[N_MODS] = {%s};" % ", ".join(cstr(m.name) for m in spec.MODS))
    # control param of a module's control role (or -1 when that module's picture has no such control)
    maxc = max(len(v) for v in spec.CONTROLS.values())
    rows = []
    for m in spec.MODS:
        have = {c.role: c for c in m.controls}
        row = []
        for r in spec.CONTROLS[m.type]:
            row.append(cid(have[r[0]].key) if r[0] in have else "-1")
        row += ["-1"] * (maxc - len(row))
        rows.append("    {%s}," % ", ".join(row))
    L.append("#define MAX_CTL %d" % maxc)
    L.append("static const short MOD_CTL[N_MODS][MAX_CTL] = {")
    L += rows
    L.append("};")
    L.append("static const float CTL_DEF[N_TYPES][MAX_CTL] = {")
    for t in types:
        row = [("%.3ff" % (1.0 if t == "ABC" else c[2])) for c in spec.CONTROLS[t]]
        row += ["0.0f"] * (maxc - len(row))
        L.append("    {%s},  // %s" % (", ".join(row), t))
    L.append("};")
    # jacks
    L.append("")
    L.append("#define N_JACKS %d" % len(spec.JACKS))
    L.append("#define N_OUTS %d" % len(spec.OUTS))
    L.append("#define N_INS %d" % len(spec.INS))
    L.append("static const unsigned char JACK_MOD[N_JACKS] = {%s};" % ", ".join(str(j.mod.idx) for j in spec.JACKS))
    L.append("static const unsigned char JACK_ROLE[N_JACKS] = {%s};" % ", ".join(str(j.role_index) for j in spec.JACKS))
    L.append("static const unsigned char JACK_IS_OUT[N_JACKS] = {%s};" % ", ".join("1" if j.kind == "out" else "0" for j in spec.JACKS))
    L.append("static const unsigned char JACK_SCREEN[N_JACKS] = {%s};" % ", ".join(str(j.screen) for j in spec.JACKS))
    L.append("static const char *const JACK_KEY[N_JACKS] = {%s};" % ", ".join(cstr(j.key) for j in spec.JACKS))
    L.append("static const char *const JACK_LABEL[N_JACKS] = {%s};" % ", ".join(cstr("%s %s" % (j.mod.name, j.label)) for j in spec.JACKS))
    L.append("static const short JACK_OUT_INDEX[N_JACKS] = {%s};" % ", ".join(str(getattr(j, "out_index", -1)) for j in spec.JACKS))
    L.append("static const short JACK_IN_INDEX[N_JACKS] = {%s};" % ", ".join(str(getattr(j, "in_index", -1)) for j in spec.JACKS))
    L.append("static const short OUT_JACK[N_OUTS] = {%s};" % ", ".join(str(o.gid) for o in spec.OUTS))
    L.append("static const short IN_JACK[N_INS] = {%s};" % ", ".join(str(j.gid) for j in spec.INS))
    slot = [spec.IN_SLOT.get(j.gid, (-1, -1)) for j in spec.JACKS]
    L.append("static const signed char JACK_GROUP_OF[N_JACKS] = {%s};   // an input's cable group on its screen" % ", ".join(str(s[0]) for s in slot))
    L.append("static const signed char JACK_GROUP_POS[N_JACKS] = {%s};   // its position in the group (picture option - 1)" % ", ".join(str(s[1]) for s in slot))
    # picture switches
    vis = pic_switches(P)
    first = [i for i, p in enumerate(P) if p["key"].startswith("cp_")][0]
    assert [p["key"] for p in P[first:first + len(vis)]] == [p["key"] for p in P if p["key"][:3] in ("cp_", "xo_", "xi_", "hd_")], "picture switches contiguous"
    L.append("")
    L.append("#define P_VIS_FIRST %d" % first)
    L.append("#define N_VIS %d" % len(vis))
    L.append("#define GROUP %d" % spec.GROUP)
    L.append("static const unsigned char JACK_COLOUR[N_JACKS] = {%s};" % ", ".join(str(getattr(j, "out_index", 0) % len(spec.COLORS)) for j in spec.JACKS))
    L.append("static const unsigned char VIS_KIND[N_VIS] = {%s};" % ", ".join(str(v[0]) for v in vis))
    L.append("static const short VIS_A[N_VIS] = {%s};" % ", ".join(str(v[1]) for v in vis))
    L.append("static const short VIS_B[N_VIS] = {%s};" % ", ".join(str(v[2]) for v in vis))
    # Q-Links per screen: the first 16 knobs of the screen, by module then position
    L.append("")
    L.append("static const short SCREEN_QLINKS[N_SCREENS][16] = {")
    for s in range(spec.NSCREENS):
        cs = [c for c in spec.CONTROL_LIST if c.mod.screen == s and c.kind == "k"]
        cs.sort(key=lambda c: (c.mod.mi, round(c.y / 60), c.x))
        ids = [cid(c.key) for c in cs[:16]] + ["-1"] * (16 - min(16, len(cs)))
        L.append("    {%s}," % ", ".join(ids))
    L.append("};")
    with open(os.path.join(ROOT, "src", "kutil_ids.h"), "w") as f:
        f.write("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------ layout.conf
THEME = """scale_names=1
label_scale=1.25
theme_bg=242424
theme_panel=242424
theme_line=bfbfbf
theme_ink=f2f2f2
theme_ink_dim=c8c8c8
theme_ink_faint=7a7a7a
theme_accent=f07a1e
theme_accent_hi=ffffff
theme_knob_face=151515
theme_knob_ring=3c3c3c
theme_knob_dot=f2f2f2
theme_bar=1a1a1a
theme_seg_active=f07a1e
theme_seg_inactive=151515
theme_seg_active_tx=111111
theme_btn_text=f2f2f2
theme_tab_on=f07a1e
theme_tab_on_tx=111111
theme_lcd=101010
theme_box=151515"""


def jack_box(j):
    """Touch box (page coordinates) of a jack: its circle with a little room, never overlapping the jack row's neighbours."""
    cx, cy = spec.to_page(j.screen, j.x, j.y)
    sc = spec.SY[j.screen]
    r = max(14, int(round(j.r * sc * 1.15)))
    return int(round(cx)) - r, int(round(cy)) - r, 2 * r, 2 * r


def control_box(c):
    cx, cy = spec.to_page(c.mod.screen, c.x, c.y)
    sc = spec.FIT[c.mod.screen][0]
    if c.kind in ("k", "n"):
        R = knob_radius(c)
        return int(round(cx)) - R - 2, int(round(cy)) - R - 2, 2 * R + 4, 2 * R + 4
    r = max(16, int(round(c.r * sc * 1.1)))
    if c.kind == "v":
        # a slider: a tall touch box along the slider's travel
        return int(round(cx)) - 12, int(round(cy)) - 40, 24, 80
    return int(round(cx)) - r, int(round(cy)) - r, 2 * r, 2 * r


def layout_line(c):
    cx, cy = spec.to_page(c.mod.screen, c.x, c.y)
    when = "when=view:%d" % c.mod.screen
    x, y = int(round(cx)), int(round(cy)) + Y0
    if c.kind in ("k", "n"):
        R = knob_radius(c)
        return 'knob cx=%d cy=%d r=%d label="" key=%s ns=0 vs=0 bw=%d %s' % (x, y, R, c.key, 2 * R + 10, when)
    if c.kind == "v":
        return 'knob cx=%d cy=%d r=%d label="" key=%s ns=0 vs=0 bw=36 %s' % (x, y, SLIDER_R, c.key, when)
    if c.kind == "s":
        return 'toggle cx=%d cy=%d label="" key=%s bw=60 ns=0 %s' % (x, y, c.key, when)
    return 'button cx=%d cy=%d label="" key=%s %s' % (x, y, c.key, when)


def write_layout():
    L = ["# KutilXXL page layout. GENERATED by tools/gen_params.py from tools/spec.py -- edit spec.py, not this.",
         "# One tab; each of the three screens is a set of controls shown while 'view' is at it. The panel pictures,",
         "# jack touch areas and cables are placed and drawn by tools/post_skin.py.",
         THEME,
         "qlinks_track = " + ",".join("ql%d" % (i + 1) for i in range(16)),
         "", "[tab KutilXXL]"]
    for k, lbl, x, y in NAV:
        L.append('button cx=%d cy=%d label="%s" key=%s' % (x, y + Y0, lbl, k))
    for j in spec.JACKS:
        bx, by, bw, bh = jack_box(j)
        L.append('button cx=%d cy=%d label="" key=tap_%s when=view:%d' % (bx + bw // 2, by + bh // 2 + Y0, j.key, j.screen))
    L.append('readout cx=640 cy=%d w=700 h=50 label="" key=patch_info' % (36 + Y0))
    for c in spec.CONTROL_LIST:
        L.append(layout_line(c))
    L.append('qlinks "KutilXXL" = ' + ",".join("ql%d" % (i + 1) for i in range(16)))
    with open(os.path.join(ROOT, "layout.conf"), "w") as f:
        f.write("\n".join(L) + "\n")


def write_inventory():
    L = ["# KutilXXL inventory", "",
         "Every module, control and jack of the instrument, generated from `tools/spec.py` and `art/geometry.json`.", ""]
    for s in range(spec.NSCREENS):
        L += ["## Screen %d" % (s + 1), ""]
        for m in [m for m in spec.MODS if m.screen == s]:
            L += ["### %s (%s)" % (m.name, m.type), "", "Controls: " + (", ".join("%s (%s)" % (c.label.lower(), c.kind) for c in m.controls) or "-"),
                  "", "Inputs: " + ", ".join(j.label.lower() for j in m.jacks if j.kind == "in"),
                  "", "Outputs: " + ", ".join(j.label.lower() for j in m.jacks if j.kind == "out"), ""]
    L += ["%d modules, %d controls, %d inputs, %d outputs." % (len(spec.MODS), len(spec.CONTROL_LIST), len(spec.INS), len(spec.OUTS)), ""]
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "INVENTORY.md"), "w") as f:
        f.write("\n".join(L))


def main():
    os.makedirs(os.path.join(ROOT, "src"), exist_ok=True)
    P = build_params()
    write_params(P)
    write_header(P)
    write_layout()
    write_inventory()
    print("gen_params: %d parameters (%d controls), %d jacks, %d picture switches" % (
        len(P), len(spec.CONTROL_LIST), len(spec.JACKS), len(pic_switches(P))))


if __name__ == "__main__":
    main()
