#!/usr/bin/env python3
"""Builds every derived asset of the site from sources. Run from anywhere:

    python3 site/tools/build_assets.py [photos] [maps] [logo] [grain]

photos  tools/raw/*.jpg  -> assets/img/<name>-{960,1920}.webp, one shared documentary grade
maps    Terrarium DEM tiles (public, AWS open data) -> assets/map/<name>.svg, real contour lines
logo    the mark geometry of v2/gen.py + Futura Medium outlines -> assets/img/logo-*.svg
grain   assets/img/grain.png, tileable film grain for the intro
inject  writes the logo sprite and the photo credits into ../index.html, between their markers

The raw photos are not committed (see .gitignore); tools/credits.json lists where each comes from.
"""
import io, json, math, sys, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

SITE = Path(__file__).resolve().parent.parent
RAW, IMG, MAP = SITE / "tools/raw", SITE / "assets/img", SITE / "assets/map"
UA = {"User-Agent": "HikingClubSite/1.0 (student club website)"}


# ---------------------------------------------------------------- photos
def grade(im):
    """Documentary grade shared by every photo: less saturation, a matte floor, cool shadows."""
    a = np.asarray(im, dtype=np.float32) / 255
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    a = lum[..., None] + (a - lum[..., None]) * 0.74                      # desaturate
    a = a + 0.05 * np.sin((a - 0.5) * math.pi)                          # soft S-curve
    shadow = ((1 - lum) ** 2.2)[..., None]
    a = a + shadow * np.array([-0.012, 0.0, 0.022], np.float32)          # cold shadows
    a = 0.028 + a * 0.955                                               # matte floor, no pure white
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))


def photos():
    for src in sorted(RAW.glob("*.jpg")):
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        g = grade(im)
        sizes = []
        for w in (960, 1920):  # long edge, so the one portrait photo does not balloon
            out = g.copy(); out.thumbnail((w, w), Image.LANCZOS)
            out.save(IMG / f"{src.stem}-{w}.webp", "WEBP", quality=70, method=6)
            sizes.append(out.size)
        print("photo", src.stem, sizes)


# ---------------------------------------------------------------- maps
def tile_xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def dem(bbox, z):
    """Mosaic of Terrarium tiles covering bbox (lat0, lon0, lat1, lon1), cropped to it. Metres."""
    lat0, lon0, lat1, lon1 = bbox
    x0, y0 = tile_xy(lat1, lon0, z)
    x1, y1 = tile_xy(lat0, lon1, z)
    tx = range(int(x0), int(x1) + 1)
    ty = range(int(y0), int(y1) + 1)
    rows = []
    for y in ty:
        row = []
        for x in tx:
            url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
            t = np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=30).read())).convert("RGB"), np.float32)
            row.append(t[..., 0] * 256 + t[..., 1] + t[..., 2] / 256 - 32768)
        rows.append(np.hstack(row))
    m = np.vstack(rows)
    px = lambda v, o: int(round((v - o) * 256))
    return m[px(y0, ty[0]):px(y1, ty[0]), px(x0, tx[0]):px(x1, tx[0])]


def rdp(pts, eps):
    """Ramer-Douglas-Peucker, iterative."""
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        L = np.hypot(*ab)
        if L < 1e-6:  # closed loop: measure from the shared end point instead of a degenerate chord
            d = np.hypot(*(pts[i + 1:j] - a).T)
        else:
            d = np.abs(ab[0] * (pts[i + 1:j, 1] - a[1]) - ab[1] * (pts[i + 1:j, 0] - a[0])) / L
        k = int(np.argmax(d))
        if d[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[keep]


MAPS = {
    # Only the two northern maps: south of 60° N the open DEM mixes sources and steps at their seams.
    # name: bbox (lat0, lon0, lat1, lon1), zoom, contour step, index step, marker (lat, lon, label)
    "abisko":     ((68.300, 18.600, 68.400, 18.950), 12, 25, 100, (68.3495, 18.8312, "ABISKO")),
    "kebnekaise": ((67.860, 18.380, 67.945, 18.680), 12, 50, 250, (67.9044, 18.5283, "KEBNEKAISE")),
}


def maps():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for name, (bbox, z, step, index, marker) in MAPS.items():
        Z = dem(bbox, z)
        Z = np.maximum(Z, -1.0)                    # no bathymetry: the sea is flat
        # light smoothing: the tiles are resampled data and step at their seams
        k = np.array([1, 4, 6, 4, 1], np.float32); k /= k.sum()
        Z = np.pad(Z, 2, mode="edge")  # edge padding, or the border reads as a cliff and draws a frame
        Z = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 1, Z)
        Z = np.apply_along_axis(lambda c: np.convolve(c, k, "valid"), 0, Z)
        h, w = Z.shape
        W = 1000.0; H = W * h / w
        lv = np.arange(max(0, math.ceil(Z.min() / step) * step), Z.max(), step)
        cs = plt.contour(np.linspace(0, W, w), np.linspace(0, H, h), Z, levels=lv)
        paths = {True: [], False: []}
        for level, segs in zip(cs.levels, cs.allsegs):
            for s in segs:
                if len(s) < 6:
                    continue
                s = rdp(np.asarray(s), 1.0)
                d = "M" + " ".join(f"{x:.1f} {y:.1f}" for x, y in s)
                paths[abs(level % index) < 1e-6].append(d)
        plt.close("all")
        lat0, lon0, lat1, lon1 = bbox
        mx = (marker[1] - lon0) / (lon1 - lon0) * W
        my = (lat1 - marker[0]) / (lat1 - lat0) * H
        top = np.unravel_index(np.argmax(Z), Z.shape)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" fill="none" '
               f'stroke="#1D1D1B" stroke-linejoin="round" stroke-linecap="round" '
               f'data-max="{Z.max():.0f}" data-min="{Z.min():.0f}" data-step="{step}">'
               f'<path stroke-width="0.55" opacity="0.55" d="{" ".join(paths[False])}"/>'
               f'<path stroke-width="1.1" d="{" ".join(paths[True])}"/>'
               f'<g class="mk" transform="translate({mx:.1f} {my:.1f})"><circle r="4" fill="#1D1D1B" stroke="none"/>'
               f'<circle r="11" stroke-width="1"/></g>'
               f'<g class="top" transform="translate({top[1] * W / w:.1f} {top[0] * H / h:.1f})">'
               f'<path d="M0 -6 L5.2 3 L-5.2 3 Z" fill="#1D1D1B" stroke="none"/></g></svg>')
        (MAP / f"{name}.svg").write_text(svg)
        print("map", name, Z.shape, f"{Z.min():.0f}-{Z.max():.0f} m", len(svg) // 1024, "KB")


# ---------------------------------------------------------------- logo
# Geometry of mark 02, identical to v2/gen.py (slope 2:1, cleft stopping 18 short of the ground).
MARK = ("M134 30 L203 168 L129 168 L97 104 Z M115 98 L137 98 L163 150 L141 150 Z", "M74 84 L116 168 L32 168 Z")
MX0, MY0, MW, MH = 32, 30, 171, 138


def glyphs(text, size, tracking):
    """Futura Medium outlines for text, as one SVG path at the given size and tracking (px)."""
    from fontTools.ttLib import TTCollection
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    font = TTCollection("/System/Library/Fonts/Supplemental/Futura.ttc").fonts[0]
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    s, x, d = size / upm, 0.0, []
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs, lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, 0)))
        d.append(pen.getCommands())
        x += font["hmtx"][g][0] * s + (tracking if i < len(text) - 1 else 0)
    return " ".join(d), x, font["OS/2"].sCapHeight * s


def logo():
    mark = lambda tr: f'<g transform="{tr}"><path fill-rule="evenodd" d="{MARK[0]}"/><path d="{MARK[1]}"/></g>'
    svg = lambda w, h, body, label="Hiking Club": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" fill="currentColor" '
        f'role="img" aria-label="{label}">{body}</svg>')
    (IMG / "logo-mark.svg").write_text(svg(MW, MH, mark(f"translate({-MX0} {-MY0})")))

    # Vertical lockup, SASSE structure kept from gen2.py: emblem, rule, name in widely tracked caps.
    # The name is shorter than MOUNTAINEERING CLUB, so it is set larger (30 instead of 22) and the
    # tracking is what makes the line 300 wide; rule = 59 % of the name, emblem = 55 %, as before.
    NAME_W, PAD = 280.0, 26.0
    _, nat, _ = glyphs("HIKING CLUB", 30, 0)
    word, ww, cap = glyphs("HIKING CLUB", 30, (NAME_W - nat) / 10)
    CX, markW = NAME_W / 2 + PAD, NAME_W * 0.55
    s = markW / MW; markH = MH * s
    y = PAD + markH
    body = (mark(f"translate({CX - markW / 2:.2f} {PAD}) scale({s:.5f}) translate({-MX0} {-MY0})")
            + f'<rect x="{CX - NAME_W * 0.59 / 2:.2f}" y="{y + 22:.2f}" width="{NAME_W * 0.59:.2f}" height="1.8"/>'
            + f'<path transform="translate({PAD} {y + 22 + 1.8 + 20 + cap:.2f})" d="{word}"/>')
    (IMG / "logo-vertical.svg").write_text(svg(NAME_W + 2 * PAD, y + 22 + 1.8 + 20 + cap + PAD, body))

    # Horizontal lockup: mark | HIKING / CLUB, CLUB tracked out to the width of HIKING (as gen.py did).
    top, tw, cap2 = glyphs("HIKING", 29, 3.2)
    _, nat2, _ = glyphs("CLUB", 29, 0)
    bot, _, _ = glyphs("CLUB", 29, (tw - nat2) / 3)
    mh = 100; s = mh / MH
    body = (mark(f"scale({s:.5f}) translate({-MX0} {-MY0})")
            + f'<rect x="{MW * s + 30:.1f}" y="2" width="1.5" height="{mh - 4}"/>'
            + f'<path transform="translate({MW * s + 58:.1f} 42)" d="{top}"/>'
            + f'<path transform="translate({MW * s + 58:.1f} 85)" d="{bot}"/>')
    (IMG / "logo-horizontal.svg").write_text(svg(MW * s + 58 + tw, mh, body))

    # One-line wordmark for the navigation
    word, ww, cap = glyphs("HIKING CLUB", 20, 20 * 0.2)
    (IMG / "logo-wordmark.svg").write_text(svg(ww, cap, f'<path transform="translate(0 {cap:.2f})" d="{word}"/>'))
    print("logo ok")


# ---------------------------------------------------------------- grain
def grain():
    rng = np.random.default_rng(7)
    n = rng.normal(128, 38, (256, 256))
    Image.fromarray(np.clip(n, 0, 255).astype(np.uint8), "L").save(IMG / "grain.png", optimize=True)
    print("grain ok")


# ---------------------------------------------------------------- index.html
def inject():
    """Inline the logos as <symbol>s (so <use> works from file:// too) and list the photo credits."""
    import html, re
    sym = []
    for sid, f in [("mark", "logo-mark"), ("wordmark", "logo-wordmark"), ("lockup", "logo-vertical"), ("lockup-h", "logo-horizontal")]:
        svg = (IMG / f"{f}.svg").read_text()
        vb = re.search(r'viewBox="([^"]+)"', svg).group(1)
        inner = re.sub(r"^<svg[^>]*>|</svg>$", "", svg)
        sym.append(f'<symbol id="{sid}" viewBox="{vb}" fill="currentColor">{inner}</symbol>')
        print(sid, vb)
    sprite = '<svg class="sprite" aria-hidden="true" style="position:absolute;width:0;height:0">' + "".join(sym) + "</svg>"
    lic = {"CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/", "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
           "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/", "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
           "CC0": "https://creativecommons.org/publicdomain/zero/1.0/", "Public domain": "https://en.wikipedia.org/wiki/Public_domain"}
    items = []
    for name, c in json.loads((SITE / "tools/credits.json").read_text()).items():
        title = c["title"].removeprefix("File:").rsplit(".", 1)[0]
        items.append(f'<li><a href="{html.escape(c["page"])}" rel="noopener">{html.escape(title)}</a>, '
                     f'{html.escape(c["artist"] or "unknown")}, <a href="{lic[c["lic"]]}" rel="noopener">{c["lic"]}</a>. Graded and cropped.</li>')
    credits = '<ul class="credits-list">' + "".join(items) + "</ul>"
    page = SITE.parent / "index.html"          # the page sits at the repo root, for GitHub Pages
    t = page.read_text()
    t = re.sub(r"<!-- sprite -->.*?<!-- /sprite -->", lambda m: f"<!-- sprite -->{sprite}<!-- /sprite -->", t, flags=re.S)
    t = re.sub(r"<!-- credits -->.*?<!-- /credits -->", lambda m: f"<!-- credits -->{credits}<!-- /credits -->", t, flags=re.S)
    page.write_text(t)


if __name__ == "__main__":
    jobs = sys.argv[1:] or ["photos", "maps", "logo", "grain", "inject"]
    for j in jobs:
        globals()[j]()
