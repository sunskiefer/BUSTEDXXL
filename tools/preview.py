"""Offline preview of the built skin: composes a screen the way MPC would, from the skin itself (TUI.json + pictures),
for a given state of the parameters (key -> value). Used by post_skin.py --preview and tools/check_skin.py."""
import os
import re

from PIL import Image

import spec

W, H = spec.PAGE_W, spec.PAGE_H


def bounds(b):
    return [int(round(float(x))) for x in b.split()]


class Composer:
    def __init__(self, skin):
        self.skin = skin
        self.cache = {}

    def img(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(os.path.join(self.skin.dir, name)).convert("RGBA")
        return self.cache[name]

    def shown(self, inst, state):
        for h in inst["bounds"]["additionalInvalidatingHandles"]:
            m = re.match(r"IndexedEnabling/(\d+)/(\d+)/Parameter (\d+)", h)
            if m and state.get(self.skin.keys[int(m.group(3))], 0) != int(m.group(1)):
                return False
        return True

    def norm(self, key, state):
        p = self.skin.params.get(key)
        v = state.get(key, p.get("default", 0) if p else 0)
        if p is None:
            return 0.0
        if "options" in p:
            n = len(p["options"])
            return v / float(n - 1) if n > 1 else 0.0
        lo, hi = p.get("min", 0), p.get("max", 1)
        return (v - lo) / (hi - lo) if hi > lo else 0.0

    def compose(self, state):
        page = Image.new("RGBA", (W, H), (36, 36, 36, 255))
        n = 0
        for inst in self.skin.page["componentsData"]:
            if not self.shown(inst, state):
                continue
            x, y, w, h = bounds(inst["bounds"]["bounds"])
            t = inst["componentData"]["type"]
            if t == "Image":
                name = inst["componentData"]["data"]["image"]
                if name:
                    im = self.img(name)
                    page.alpha_composite(im.resize((w, h), Image.BILINEAR) if im.size != (w, h) else im, (x, y))
                continue
            d = self.skin.defs.get(t)
            if not d:
                continue
            key = self.skin.param_of(inst)
            for sub in d["componentsData"]:
                st = sub["componentData"]["type"]
                sx, sy, sw, sh = bounds(sub["bounds"]["bounds"])
                data = sub["componentData"].get("data", {})
                if st == "Knob" and data.get("filmStrip"):
                    strip = self.img(data["filmStrip"])
                    F = strip.size[0]
                    fr = int(round(self.norm(key, state) * 127))
                    page.alpha_composite(strip.crop((0, fr * F, F, fr * F + F)).resize((sw, sh)), (x + sx, y + sy))
                elif st == "Button":
                    if sub["bounds"].get("whenVisible") == "WhenFocussed":
                        continue
                    nb = data.get("numButtonsInGroup", 1)
                    p = self.skin.params.get(key, {})
                    v = state.get(key, p.get("default", 0))
                    on = (int(round(v)) == data.get("buttonId", 0)) if nb > 1 else bool(round(v)) and not p.get("momentary")
                    name = data.get("onImage") if on else data.get("offImage")
                    if name:
                        im = self.img(name)
                        page.alpha_composite(im.resize((sw, sh)) if im.size != (sw, sh) else im, (x + sx, y + sy))
        return page


def sample_state(skin):
    """A patch that exercises the pictures: a few pairs on each screen, a cross-screen cable, a held jack."""
    st = {}
    byname = {}
    for j in spec.JACKS:
        byname[j.key] = j
    def cab(o, i):
        key, opt, nopt = spec.cable_param(byname[o], byname[i])
        st[key] = opt
    cab("kompas1_cv1", "crust21_a_c_in")
    cab("kompas1_trig1", "crust21_a_g_in")
    cab("crust21_a_out", "abc1_a")
    cab("pizza1_main", "abc1_b")
    cab("pizza1_main", "abc1_d")
    cab("abc1_sum1", "pizza1_cv")
    cab("kompas2_cv1", "wavebard1_c_in")
    cab("wavebard1_l_out", "abc2_a")
    cab("wavebard2_r_out", "abc2_e")
    cab("kompas3_cv1", "alchemist1_c_in")
    cab("alchemist1_l_out", "basil1_l_in")
    cab("basil1_l_out", "abc3_a")
    o = byname["pizza1_main"]
    st["xo_%d_1" % o.gid] = 1
    i = byname["wavebard1_aud_l_in"]
    st["xi_%d_0" % i.gid] = 1
    return st


def run(skin, folder):
    comp = Composer(skin)
    base = sample_state(skin)
    for s in range(spec.NSCREENS):
        st = dict(base)
        st["view"] = s
        # only this screen's picture switches count (the engine zeroes the others)
        keep = {}
        for k, v in st.items():
            if k == "view":
                keep[k] = v
                continue
            m = re.match(r"(cp|xo|xi)_(\d+)", k)
            if m:
                gid = int(m.group(2))
                scr = spec.JACKS[gid].screen
                if scr == s:
                    keep[k] = v
        im = comp.compose(keep).convert("RGB")
        im.save(os.path.join(folder, "screen_%d.png" % (s + 1)))
    return folder
