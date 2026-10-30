#!/usr/bin/env python3
"""Turn the generated skin into the KutilXXL panel.

    python3 tools/post_skin.py "<skin dir>/Plugin Skins" [--preview build/preview] [--only-check]

mpc-vst-plugins' gen_vst.py builds a working skin from layout.conf (controls shown while 'view' is at their screen).
This script then, in the built skin:
  - paints a full panel picture per screen from art/s1.png .. s3.png (a header with the < > buttons around it);
  - turns the knobs into filmstrips cut from the pictures' own knobs, so they turn in place (one strip per module type and
    radius: a strip is 128 frames; a rotated copy of the art's knob, pointer travel -150..+150 degrees);
  - makes switches and buttons transparent touch areas whose on-picture is a lit ring; the jacks' tap buttons the same;
  - adds the cables: for every output and every input on its screen one picture of the cable, shown only while its
    switch parameter says so (IndexedEnabling, the mechanism PS3100XXL proved on a Force): cp_<out>_<group>, at most
    10 positions each. Cross-screen cables are a stub from the jack out through the left or right edge (xo_) and a stub
    arriving from that edge at the target jack (xi_). A held jack gets a ring (hd_).
    The engine sets every picture switch from the patch and the screen.
Pictures go after the controls (in front of the knobs, as the sketch had it) when spec.CABLES_ABOVE is true.
"""
import copy
import json
import math
import multiprocessing
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec  # noqa: E402
import gen_params as gp  # noqa: E402

W, H = spec.PAGE_W, spec.PAGE_H
HDR = spec.HEADER_H
FONT = os.path.join(ROOT, "art", "fonts", "TitilliumWeb-SemiBold.ttf")
PANEL = (36, 36, 36)
HEADER = (24, 24, 24)
LINE = (191, 191, 191)
INK = (242, 242, 242)
DIM = (170, 170, 170)
ORANGE = (240, 122, 30)
NEUTRAL = (225, 225, 225)
TAB = "KutilXXL|KutilXXL"
CABLE_TILE = 192
HALF = 1            # cable pictures are saved at 1/HALF size and stretched by their bounds (memory)
CABLES_ABOVE = True


def font(size):
    return ImageFont.truetype(FONT, int(size))


def load_param_keys():
    keys = []
    for line in open(os.path.join(ROOT, "build", "params.h")):
        m = re.match(r'\s*\{"([^"]+)",', line)
        if m:
            keys.append(m.group(1))
    return keys


class Skin:
    def __init__(self, folder):
        self.dir = folder
        self.path = os.path.join(folder, "TUI.json")
        self.tui = json.load(open(self.path))
        self.defs_list = self.tui["pageData"]["componentDefinitions"]["localComponentDefinitions"]
        self.defs = {d["key"]: d["value"] for d in self.defs_list}
        self.page = [d for d in self.defs_list if d["key"].endswith("|KutilXXL") or d["key"] == "KutilXXL"][0]["value"] \
            if any(d["key"].endswith("KutilXXL") for d in self.defs_list) else None
        self.keys = load_param_keys()
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.params = {p["key"]: p for p in json.load(open(os.path.join(ROOT, "params.json")))["params"]}

    def param_of(self, inst):
        for m in inst["handle remapping"]["map"]:
            if m["key"] == "Data" and m["value"].startswith("Parameter "):
                return self.keys[int(m["value"].split()[1])]
        return None

    def instances(self, key):
        return [c for c in self.page["componentsData"] if self.param_of(c) == key]

    def add_def(self, key, value):
        self.defs_list.append({"key": key, "value": value})
        self.defs[key] = value

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.tui, f, separators=(",", ":"))


def bounds(b):
    return [int(round(float(x))) for x in b.split()]


def bstr(x, y, w, h):
    return "%d %d %d %d" % (x, y, w, h)


def image_instance(name, img, x, y, w, h, handles):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": "Image",
                              "data": {"version": 2, "imageType": "Regular", "colour": "0", "image": img}},
            "handle remapping": {"version": 1, "map": []},
            "bounds": {"version": 2, "acceptsHWFocus": "No", "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
                       "boundsType": "Absolute", "bounds": bstr(x, y, w, h),
                       "additionalInvalidatingHandles": handles}}


# ------------------------------------------------------------------------------------------------ art primitives
def blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def ring_image(r, w=4, fill=None):
    S = 4
    im = Image.new("RGBA", (2 * r * S, 2 * r * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if fill:
        d.ellipse([S, S, 2 * r * S - S, 2 * r * S - S], fill=fill)
    d.ellipse([S, S, 2 * r * S - S, 2 * r * S - S], outline=ORANGE + (255,), width=w * S)
    return im.resize((2 * r, 2 * r), Image.LANCZOS)


def nav_image(label, on, w, h):
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=8 * S, fill=(ORANGE if on else (21, 21, 21)) + (255,),
                        outline=(120, 120, 120, 255), width=2 * S)
    ink = (17, 17, 17, 255) if on else INK + (255,)
    cx, cy, s = w * S / 2, h * S / 2, h * S * 0.26
    pts = [(cx - s * 0.6, cy - s), (cx - s * 0.6, cy + s), (cx + s * 0.8, cy)] if label == ">" else \
          [(cx + s * 0.6, cy - s), (cx + s * 0.6, cy + s), (cx - s * 0.8, cy)]
    d.polygon(pts, fill=ink)
    return im.resize((w, h), Image.LANCZOS)


def tag_image(text, w=92, h=34, colour=ORANGE):
    S = 4
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=8 * S, fill=(18, 18, 18, 235), outline=colour + (255,), width=2 * S)
    d.text((w * S / 2, h * S / 2), text, font=font(21 * S), fill=INK + (255,), anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


def cable_points(p1, p2, n=48, floor=1e9):
    (x1, y1), (x2, y2) = p1, p2
    dist = math.hypot(x2 - x1, y2 - y1)
    sag = 22 + 0.2 * dist
    bow = 0.0
    if abs(x2 - x1) < 0.35 * abs(y2 - y1):
        bow = (0.18 * abs(y2 - y1) + 16) * (1 if (int(x1) // 7) % 2 else -1)
    low = min(max(y1, y2) + sag, floor)
    c1 = (x1 + (x2 - x1) * 0.2 + bow, low)
    c2 = (x2 - (x2 - x1) * 0.2 + bow, low)
    pts = []
    for i in range(n + 1):
        t = i / float(n)
        a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * x1 + b * c1[0] + c * c2[0] + e * x2, a * y1 + b * c1[1] + c * c2[1] + e * y2))
    return pts


def draw_cable(p1, p2, colour, plug=9, clip=(0, HDR + 2, W, H), plug2=True):
    """-> (image, x, y) of the cable from p1 to p2 (page coordinates), cropped to what it covers."""
    width, outline = 5.5, 8.5
    pts = cable_points(p1, p2, floor=clip[3] - outline - 2)
    m = outline + plug + 2
    x0 = max(clip[0], int(math.floor(min(p[0] for p in pts) - m)))
    y0 = max(clip[1], int(math.floor(min(p[1] for p in pts) - m)))
    x1 = min(clip[2], int(math.ceil(max(p[0] for p in pts) + m)))
    y1 = min(clip[3], int(math.ceil(max(p[1] for p in pts) + m)))
    S = 3
    im = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    sp = [((x - x0) * S, (y - y0) * S) for x, y in pts]
    dark = tuple(int(v * 0.45) for v in colour)
    d.line(sp, fill=dark + (235,), width=max(1, int(outline * S)), joint="curve")
    d.line(sp, fill=colour + (240,), width=max(1, int(width * S)), joint="curve")
    hl = tuple(min(255, int(v * 1.35) + 30) for v in colour)
    d.line([(x, y - width * S * 0.22) for x, y in sp], fill=hl + (150,), width=max(1, int(width * S * 0.25)))
    ends = [sp[0]] + ([sp[-1]] if plug2 else [])
    for (x, y) in ends:
        r = plug * S
        d.ellipse([x - r, y - r, x + r, y + r], fill=dark + (255,))
        d.ellipse([x - r * 0.78, y - r * 0.78, x + r * 0.78, y + r * 0.78], fill=colour + (255,))
        d.ellipse([x - r * 0.35, y - r * 0.55, x + r * 0.1, y - r * 0.1], fill=hl + (200,))
    im = im.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    return im, x0, y0


def tile_pieces(im, x0, y0, T):
    """Cut a cable picture along a page-aligned T x T grid and crop each piece to what it covers."""
    a = im.split()[3]
    out = []
    for gy in range((y0 // T) * T, y0 + im.size[1], T):
        for gx in range((x0 // T) * T, x0 + im.size[0], T):
            bx0, by0 = max(gx, x0) - x0, max(gy, y0) - y0
            bx1, by1 = min(gx + T, x0 + im.size[0]) - x0, min(gy + T, y0 + im.size[1]) - y0
            if bx1 <= bx0 or by1 <= by0:
                continue
            bb = a.crop((bx0, by0, bx1, by1)).getbbox()
            if not bb:
                continue
            l, t, r, b = bx0 + bb[0], by0 + bb[1], bx0 + bb[2], by0 + bb[3]
            out.append((im.crop((l, t, r, b)), x0 + l, y0 + t))
    return out


# ------------------------------------------------------------------------------------------------ jobs for the pool
_FOLDER = None


def _init(folder):
    global _FOLDER
    _FOLDER = folder


def _save_pieces(prefix, im, x0, y0):
    meta = []
    for k, (piece, px, py) in enumerate(tile_pieces(im, x0, y0, CABLE_TILE)):
        name = "%s_%d.png" % (prefix, k)
        pw, ph = piece.size
        small = piece.resize((max(1, (pw + HALF - 1) // HALF), max(1, (ph + HALF - 1) // HALF)), Image.LANCZOS) if HALF > 1 else piece
        small.save(os.path.join(_FOLDER, name), optimize=False, compress_level=3)
        meta.append((name, px, py, pw, ph, small.size[0] * small.size[1]))
    return meta


def job_pair(a):
    """a = (prefix, p1, p2, colour, plug)"""
    prefix, p1, p2, colour, plug = a
    im, x0, y0 = draw_cable(p1, p2, colour, plug)
    return prefix, _save_pieces(prefix, im, x0, y0)


def job_stub(a):
    """a = (prefix, jack xy, side 'l'/'r', colour, plug, label, jack_is_start)"""
    prefix, p1, side, colour, plug, label = a
    ex = -14 if side == "l" else W + 14
    p2 = (ex, min(H - 40, p1[1] + 34))
    im, x0, y0 = draw_cable(p1, p2, colour, plug, plug2=False)
    full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    full.alpha_composite(im, (x0, y0))
    tg = tag_image(label, colour=colour)
    tx = 4 if side == "l" else W - tg.size[0] - 4
    ty = int(max(HDR + 4, min(H - tg.size[1] - 4, p2[1] - tg.size[1] - 18)))
    full.alpha_composite(tg, (tx, ty))
    bb = full.getbbox()
    full = full.crop(bb)
    return prefix, _save_pieces(prefix, full, bb[0], bb[1])


# ------------------------------------------------------------------------------------------------ the skin
def panel_image(s, z=0):
    sc, ox, oy, ya, yb = spec.VIEWS[s][z]
    w, h = spec.FIT[s][3], spec.FIT[s][4]
    S = 2
    ov = Image.new("RGB", (W * S, HDR * S), HEADER)
    d = ImageDraw.Draw(ov)
    d.line([0, (HDR - 1) * S, W * S, (HDR - 1) * S], fill=LINE, width=2 * S)
    d.text((130 * S, 36 * S), "KUTILXXL", font=font(32 * S), fill=INK, anchor="lm")
    d.text((1150 * S, 36 * S), "%d / %d" % (s + 1, spec.NSCREENS), font=font(32 * S), fill=ORANGE, anchor="rm")
    if z:
        d.text((640 * S, 36 * S), "TOP HALF" if z == 1 else "BOTTOM HALF", font=font(30 * S), fill=INK, anchor="mm")
    page = Image.new("RGB", (W, H), PANEL)
    page.paste(ov.resize((W, HDR), Image.LANCZOS), (0, 0))
    art = Image.open(os.path.join(ROOT, "art", spec.GEOM[s]["art"])).convert("RGB")
    art = art.crop((0, int(round(ya)), w, int(round(yb))))
    art = art.resize((int(round(w * sc)), int(round((yb - ya) * sc))), Image.LANCZOS)
    page.paste(art, (int(round(ox)), int(round(oy))))
    return page


def knob_sprite(c, R):
    """The art's own knob as a transparent disc, 2R+10 square, scaled to the page."""
    s = c.mod.screen
    art = Image.open(os.path.join(ROOT, "art", spec.GEOM[s]["art"])).convert("RGB")
    src = c
    if getattr(c, "sprite_from_first_knob", False):
        src = next(k for k in c.mod.controls if k.kind in ("k", "n") and not getattr(k, "sprite_from_first_knob", False))
    rr = src.r * 1.06
    box = (int(round(src.x - rr)), int(round(src.y - rr)), int(round(src.x + rr)), int(round(src.y + rr)))
    crop = art.crop(box)
    diam = 2 * int(round(R * 1.06))
    S = 4
    crop = crop.resize((diam * S, diam * S), Image.LANCZOS)
    mask = Image.new("L", (diam * S, diam * S), 0)
    ImageDraw.Draw(mask).ellipse([S, S, diam * S - S, diam * S - S], fill=255)
    crop = crop.convert("RGBA")
    crop.putalpha(mask)
    F = 2 * R + 10
    sp = Image.new("RGBA", (F * S, F * S), (0, 0, 0, 0))
    sp.alpha_composite(crop, ((F * S - diam * S) // 2, (F * S - diam * S) // 2))
    return sp, S


SWEEP = 150.0


def write_knob_strip(path, c, R, frames=128):
    sp, S = knob_sprite(c, R)
    F = 2 * R + 10
    strip = Image.new("RGBA", (F, F * frames), (0, 0, 0, 0))
    for i in range(frames):
        ang = -SWEEP + 2 * SWEEP * i / (frames - 1.0)
        fr = sp.rotate(-ang, resample=Image.BICUBIC).resize((F, F), Image.LANCZOS)
        strip.paste(fr, (0, i * F))
    strip.save(path, optimize=False, compress_level=3)


def main():
    folder = sys.argv[1]
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    skin = Skin(folder)
    vidx = skin.index["view"]
    comps = skin.page["componentsData"]
    nview = spec.NSCREENS

    # 1) base background, panel pictures
    comps[:] = [c for c in comps if not (c["componentData"]["type"] == "Image" and
                                         c["componentData"]["data"].get("image", "").startswith("sh_mode_"))]
    for name in os.listdir(folder):
        if name.startswith("sh_mode_") or re.match(r"sh_knob_r\d+\.png$", name):
            os.remove(os.path.join(folder, name))
    Image.new("RGB", (W, H), PANEL).save(os.path.join(folder, "sh_bg_0.png"))
    zidx = skin.index["zoom"]

    def en(s_, z_):
        """the view + zoom a component is shown in (both conditions must hold)"""
        return ["IndexedEnabling/%d/%d/Parameter %d" % (s_, nview, vidx), "IndexedEnabling/%d/%d/Parameter %d" % (z_, spec.ZOOMS, zidx)]
    ZOOM0 = "IndexedEnabling/0/%d/Parameter %d" % (spec.ZOOMS, zidx)
    panels = []
    for s in range(nview):
        for z in range(spec.ZOOMS):
            nm = "ku_screen_%d.png" % s if z == 0 else "ku_screen_%d_z%d.png" % (s, z)
            panel_image(s, z).save(os.path.join(folder, nm))
            panels.append(image_instance("Screen %d%s" % (s + 1, ["", " top", " bottom"][z]), nm, 0, 0, W, H, en(s, z)))
    comps[1:1] = panels

    # 2) knobs: a strip per (module type, radius) from the first knob of that kind; sliders are blank
    clusters = {}
    for c in spec.CONTROL_LIST:
        if c.kind in ("k", "n"):
            R = gp.knob_radius(c)
            clusters.setdefault((c.mod.type, R), c)
    template = next(d for k, d in skin.defs.items() if k.startswith("shKnob"))
    for (typ, R), c in sorted(clusters.items()):
        F = 2 * R + 10
        write_knob_strip(os.path.join(folder, "ku_knob_%s_r%d.png" % (typ.lower(), R)), c, R)
        d = copy.deepcopy(template)
        for sub in d["componentsData"]:
            sub["bounds"]["bounds"] = bstr(0, 0, F, F)
            if sub["componentData"]["type"] == "Knob":
                sub["componentData"]["data"]["filmStrip"] = "ku_knob_%s_r%d.png" % (typ.lower(), R)
        skin.add_def("kuKnob_%s_%d" % (typ.lower(), R), d)
    Image.new("RGBA", (20, 20 * 128), (0, 0, 0, 0)).save(os.path.join(folder, "ku_knob_blank.png"))
    dsl = copy.deepcopy(template)
    for sub in dsl["componentsData"]:
        sub["bounds"]["bounds"] = bstr(0, 0, 36, 80)
        if sub["componentData"]["type"] == "Knob":
            sub["componentData"]["data"]["filmStrip"] = "ku_knob_blank.png"
    skin.add_def("kuKnob_slider", dsl)
    for c in spec.CONTROL_LIST:
        if c.kind not in ("k", "n", "v"):
            continue
        for inst in skin.instances(c.key):
            bx, by, bw, bh = gp.control_box(c)
            inst["bounds"]["bounds"] = bstr(bx, by, bw, bh)
            inst["componentData"]["type"] = "kuKnob_slider" if c.kind == "v" else \
                "kuKnob_%s_%d" % (c.mod.type.lower(), gp.knob_radius(c))

    # 3) switches and buttons: transparent, a lit ring while on / pressed
    def restyle_def(typ, w, h, off_img, on_img):
        d = skin.defs[typ]
        d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
        for s in d["componentsData"]:
            s["bounds"]["bounds"] = bstr(0, 0, w, h)
            if s["componentData"]["type"] == "Button":
                s["componentData"]["data"]["offImage"] = off_img
                s["componentData"]["data"]["onImage"] = on_img

    for k, lbl, x, y in gp.NAV:
        nav_image(lbl, False, 80, 52).save(os.path.join(folder, "ku_%s_off.png" % k))
        nav_image(lbl, True, 80, 52).save(os.path.join(folder, "ku_%s_on.png" % k))
        restyle_def("shTrig_%s_x" % k, 80, 52, "ku_%s_off.png" % k, "ku_%s_on.png" % k)
        for inst in skin.instances(k):
            inst["bounds"]["bounds"] = bstr(x - 40, y - 26, 80, 52)
    blank(4, 4).save(os.path.join(folder, "ku_blank.png"))
    for r in sorted(set([max(14, int(round(j.r * spec.SY[j.screen] * 1.15))) for j in spec.JACKS])):
        ring_image(r).save(os.path.join(folder, "ku_ring_%d.png" % r))
    for j in spec.JACKS:
        bx, by, bw, bh = gp.jack_box(j)
        restyle_def("shTrig_tap_%s_x" % j.key, bw, bh, "ku_blank.png", "ku_ring_%d.png" % (bw // 2))
        for inst in skin.instances("tap_" + j.key):
            inst["bounds"]["bounds"] = bstr(bx, by, bw, bh)
    for c in spec.CONTROL_LIST:
        if c.kind not in ("s", "b"):
            continue
        bx, by, bw, bh = gp.control_box(c)
        r = bw // 2
        nm = "ku_lit_%d.png" % r
        if not os.path.exists(os.path.join(folder, nm)):
            ring_image(r, 3, fill=ORANGE + (70,)).save(os.path.join(folder, nm))
        if c.kind == "b":
            restyle_def("shTrig_%s_x" % c.key, bw, bh, "ku_blank.png", nm)
        else:
            d = copy.deepcopy(next(v for k, v in skin.defs.items() if k.startswith("shToggle")))
            d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
            for s in d["componentsData"]:
                s["bounds"]["bounds"] = bstr(0, 0, bw, bh)
                if s["componentData"]["type"] == "Button":
                    s["componentData"]["data"]["offImage"] = "ku_blank.png"
                    s["componentData"]["data"]["onImage"] = nm
            skin.add_def("kuToggle_%s" % c.key, d)
        for inst in skin.instances(c.key):
            inst["bounds"]["bounds"] = bstr(bx, by, bw, bh)
            if c.kind == "s":
                inst["componentData"]["type"] = "kuToggle_%s" % c.key

    # 3b) zoom: every overview component of a screen gets "whole" as an extra condition; the controls, jack touch areas and
    # the tap-to-zoom areas get a second, enlarged copy shown while their half of the screen is zoomed
    vh = "IndexedEnabling/"
    for inst in comps:
        hs = inst["bounds"]["additionalInvalidatingHandles"]
        if any(h.startswith(vh) and h.endswith("Parameter %d" % vidx) for h in hs) and ZOOM0 not in hs and \
                not any(h.endswith("Parameter %d" % zidx) for h in hs):
            hs.append(ZOOM0)
    zctl = []
    kframes = 64

    def clone_def(src, new, w, h, off=None, on=None, strip=None, frames=None):
        d = copy.deepcopy(skin.defs[src])
        for sub in d["componentsData"]:
            sub["bounds"]["bounds"] = bstr(0, 0, w, h)
            t = sub["componentData"]["type"]
            if t == "Button":
                if off:
                    sub["componentData"]["data"]["offImage"] = off
                if on:
                    sub["componentData"]["data"]["onImage"] = on
            if t == "Knob" and strip:
                sub["componentData"]["data"]["filmStrip"] = strip
                sub["componentData"]["data"]["numFrames"] = frames - 1
        skin.add_def(new, d)
        return new

    zclusters = {}
    for c in spec.CONTROL_LIST:
        if c.kind in ("k", "n"):
            for z in spec.zviews(c.mod.screen, c.y, c.r):
                zclusters.setdefault((c.mod.type, gp.knob_radius(c, z)), c)
    for (typ, R), c in sorted(zclusters.items()):
        write_knob_strip(os.path.join(folder, "ku_zknob_%s_r%d.png" % (typ.lower(), R)), c, R, kframes)
        F = 2 * R + 10
        clone_def("kuKnob_%s_%d" % (c.mod.type.lower(), gp.knob_radius(c, 0)), "kuZKnob_%s_%d" % (typ.lower(), R), F, F,
                  strip="ku_zknob_%s_r%d.png" % (typ.lower(), R), frames=kframes)
    zring = set()
    for c, z in [(c_, z_) for c_ in spec.CONTROL_LIST for z_ in spec.zviews(c_.mod.screen, c_.y, c_.r)]:
        s_ = c.mod.screen
        bx, by, bw, bh = gp.control_box(c, z)
        for inst in skin.instances(c.key):
            dup = copy.deepcopy(inst)
            dup["bounds"]["bounds"] = bstr(bx, by, bw, bh)
            dup["bounds"]["additionalInvalidatingHandles"] = en(s_, z)
            if c.kind in ("k", "n"):
                dup["componentData"]["type"] = "kuZKnob_%s_%d" % (c.mod.type.lower(), gp.knob_radius(c, z))
            elif c.kind == "v":
                dup["componentData"]["type"] = clone_def("kuKnob_slider", "kuZSlider_%s_%d" % (c.key, z), bw, bh)
            elif c.kind == "s":
                r = bw // 2
                nm = "ku_lit_%d.png" % r
                if not os.path.exists(os.path.join(folder, nm)):
                    ring_image(r, 3, fill=ORANGE + (70,)).save(os.path.join(folder, nm))
                dup["componentData"]["type"] = clone_def("kuToggle_%s" % c.key, "kuZToggle_%s_%d" % (c.key, z), bw, bh, "ku_blank.png", nm)
            else:
                r = bw // 2
                nm = "ku_lit_%d.png" % r
                if not os.path.exists(os.path.join(folder, nm)):
                    ring_image(r, 3, fill=ORANGE + (70,)).save(os.path.join(folder, nm))
                dup["componentData"]["type"] = clone_def("shTrig_%s_x" % c.key, "kuZBtn_%s_%d" % (c.key, z), bw, bh, "ku_blank.png", nm)
            zctl.append(dup)
    for j, z in [(j_, z_) for j_ in spec.JACKS for z_ in spec.zviews(j_.screen, j_.y, j_.r)]:
        s_ = j.screen
        bx, by, bw, bh = gp.jack_box(j, z)
        if not os.path.exists(os.path.join(folder, "ku_ring_%d.png" % (bw // 2))):
            ring_image(bw // 2).save(os.path.join(folder, "ku_ring_%d.png" % (bw // 2)))
        for inst in skin.instances("tap_" + j.key):
            dup = copy.deepcopy(inst)
            dup["bounds"]["bounds"] = bstr(bx, by, bw, bh)
            dup["bounds"]["additionalInvalidatingHandles"] = en(s_, z)
            dup["componentData"]["type"] = clone_def("shTrig_tap_%s_x" % j.key, "kuZTap_%s_%d" % (j.key, z), bw, bh,
                                                     "ku_blank.png", "ku_ring_%d.png" % (bw // 2))
            zctl.append(dup)
    # the tap-to-zoom areas sit behind every control: empty art zooms in (whole view) or out (a zoomed view)
    usable_h = H - HDR
    for s_ in range(nview):
        cut_y = int(round(spec.to_page(s_, 0, spec.CUT[s_])[1]))
        for key, rect, zs_ in (("zin_top", (0, HDR, W, cut_y - HDR), [0]), ("zin_bot", (0, cut_y, W, H - cut_y), [0]),
                               ("zout", (0, HDR, W, usable_h), [1, 2])):
            insts = [i for i in skin.instances(key)
                     if any(h.endswith("Parameter %d" % vidx) and h.startswith("IndexedEnabling/%d/" % s_) for h in i["bounds"]["additionalInvalidatingHandles"])]
            base = insts[0]
            for zz in zs_:
                dup = copy.deepcopy(base)
                dup["bounds"]["bounds"] = bstr(*rect)
                dup["bounds"]["additionalInvalidatingHandles"] = en(s_, zz)
                dup["componentData"]["type"] = clone_def("shTrig_%s_x" % key, "kuZoomTap_%s_%d_%d" % (key, s_, zz), rect[2], rect[3],
                                                         "ku_blank.png", "ku_blank.png")
                comps.append(dup)
            comps.remove(base)
    # the zoom taps went to the end of the list; move them in front of the controls so controls take the touch first
    ztap = [c_ for c_ in comps if c_["componentData"]["type"].startswith("kuZoomTap_")]
    comps[:] = [c_ for c_ in comps if not c_["componentData"]["type"].startswith("kuZoomTap_")]
    comps[1 + len(panels):1 + len(panels)] = ztap

    # 4) cables, stubs, rings
    pos = {j.gid: spec.to_page(j.screen, j.x, j.y) for j in spec.JACKS}
    plugr = {j.gid: max(7, int(round(j.r * spec.SY[j.screen] * 0.85))) for j in spec.JACKS}
    jobs_pair, jobs_stub, handles = [], [], {}
    for o in spec.OUTS:
        for j in spec.INS:
            if j.screen != o.screen:
                continue
            key, opt, nopt = spec.cable_param(o, j)
            prefix = "ku_c_%d_%d" % (o.gid, j.gid)
            jobs_pair.append((prefix, pos[o.gid], pos[j.gid], o.colour, plugr[o.gid]))
            handles[prefix] = "IndexedEnabling/%d/%d/Parameter %d" % (opt, nopt, skin.index[key])
    for o in spec.OUTS:
        for t in range(nview):
            if t == o.screen:
                continue
            side = "r" if t > o.screen else "l"
            prefix = "ku_xo_%d_%d" % (o.gid, t)
            jobs_stub.append((prefix, pos[o.gid], side, o.colour, plugr[o.gid], ("TO %d" if side == "r" else "TO %d") % (t + 1)))
            handles[prefix] = "IndexedEnabling/1/2/Parameter %d" % skin.index["xo_%d_%d" % (o.gid, t)]
    for j in spec.INS:
        for t in range(nview):
            if t == j.screen:
                continue
            side = "l" if t < j.screen else "r"
            for ci in range(len(spec.COLORS)):
                prefix = "ku_xi_%d_%d_%d" % (j.gid, t, ci)
                jobs_stub.append((prefix, pos[j.gid], side, spec.COLORS[ci], plugr[j.gid], "FROM %d" % (t + 1)))
                handles[prefix] = "IndexedEnabling/%d/%d/Parameter %d" % (1 + ci, 1 + len(spec.COLORS), skin.index["xi_%d_%d" % (j.gid, t)])
    cpus = max(1, multiprocessing.cpu_count())
    with multiprocessing.Pool(cpus, initializer=_init, initargs=(folder,)) as pool:
        res = pool.map(job_pair, jobs_pair, chunksize=16) + pool.map(job_stub, jobs_stub, chunksize=16)
    pic = []
    total_px, npieces = 0, 0
    pair_meta = []
    for prefix, meta in res:
        for (name, px, py, pw, ph, spx) in meta:
            pic.append(image_instance("Cable", name, px, py, pw, ph, [handles[prefix], ZOOM0]))
            total_px += spx
            npieces += 1
            pair_meta.append((prefix, name, px, py, pw, ph))
    # zoom cables and stubs: the overview pieces again, enlarged by their bounds (cut where they leave the view)
    opair = {}
    for o in spec.OUTS:
        opair[o.gid] = o
    ncut = 0
    for (prefix, name, px, py, pw, ph) in pair_meta:
        gid_o = int(prefix.split("_")[2])
        s_ = spec.JACKS[gid_o].screen
        for z in (1, 2):
            zs, zox, zoy, ya, yb = spec.VIEWS[s_][z]
            sc, ox, oy = spec.VIEWS[s_][0][:3]
            k = zs / sc
            x0, y0 = zox + (px - ox) * k, zoy + (py - oy) * k - ya * zs
            x1, y1 = x0 + pw * k, y0 + ph * k
            if min(x1, float(W)) - max(x0, 0.0) < 1.5 or min(y1, float(H)) - max(y0, float(HDR)) < 1.5:
                continue   # entirely outside the view
            ix0, iy0, ix1, iy1 = x0, max(y0, float(HDR)), x1, y1   # only the header edge is cut: the page clips the rest
            hdl = handles[prefix]
            if ix0 > x0 + 0.5 or iy0 > y0 + 0.5 or ix1 < x1 - 0.5 or iy1 < y1 - 0.5:
                l, t = int(math.floor((ix0 - x0) / k)), int(math.floor((iy0 - y0) / k))
                r, b = int(math.ceil((ix1 - x0) / k)), int(math.ceil((iy1 - y0) / k))
                r, b = min(r, pw), min(b, ph)
                if r - l < 1 or b - t < 1:
                    continue
                cn = "ku_zc_%d.png" % ncut
                ncut += 1
                Image.open(os.path.join(folder, name)).crop((l, t, r, b)).save(os.path.join(folder, cn), compress_level=3)
                bx0, by0, bw_, bh_ = int(round(x0 + l * k)), int(round(y0 + t * k)), max(1, int(round((r - l) * k))), max(1, int(round((b - t) * k)))
                pic.append(image_instance("Cable", cn, bx0, by0, bw_, bh_, [hdl, "IndexedEnabling/%d/%d/Parameter %d" % (z, spec.ZOOMS, zidx)]))
            else:
                pic.append(image_instance("Cable", name, int(round(x0)), int(round(y0)), max(1, int(round(pw * k))), max(1, int(round(ph * k))),
                                          [hdl, "IndexedEnabling/%d/%d/Parameter %d" % (z, spec.ZOOMS, zidx)]))
            npieces += 1
    # held rings
    for j in spec.JACKS:
        bx, by, bw, bh = gp.jack_box(j)
        h, p = divmod(j.gid, spec.GROUP)
        hh = "IndexedEnabling/%d/%d/Parameter %d" % (p + 1, min(spec.GROUP, len(spec.JACKS) - h * spec.GROUP) + 1, skin.index["hd_%d" % h])
        pic.append(image_instance("Held", "ku_ring_%d.png" % (bw // 2), bx, by, bw, bh, [hh, ZOOM0]))
        for z in spec.zviews(j.screen, j.y, j.r):
            zx, zy, zw, zh = gp.jack_box(j, z)
            pic.append(image_instance("Held", "ku_ring_%d.png" % (zw // 2), zx, zy, zw, zh,
                                      [hh, "IndexedEnabling/%d/%d/Parameter %d" % (z, spec.ZOOMS, zidx)]))
    if CABLES_ABOVE:
        comps.extend(zctl)
        comps.extend(pic)
    else:
        at = 1 + len(panels)
        comps[at:at] = pic
        comps.extend(zctl)
    skin.save()
    print("post_skin: %d screens, %d knob strips, %d cable/stub/ring pictures (%d pieces, %.1f MB decoded), %d components" % (
        nview, len(clusters), len(pic), npieces, total_px * 4 / 1e6, len(comps)))
    tot = sum(os.path.getsize(os.path.join(folder, n)) for n in os.listdir(folder))
    print("skin folder: %d files, %.1f MB on disk" % (len(os.listdir(folder)), tot / 1e6))

    if preview:
        os.makedirs(preview, exist_ok=True)
        import preview as pv
        pv.run(skin, preview)


if __name__ == "__main__":
    main()
