#!/usr/bin/env python3
"""Builds every derived asset of the site from sources. Run from anywhere:

    python3 site/tools/build_assets.py [photos] [maps] [logo] [grain]

photos  tools/raw/*.jpg  -> assets/img/<name>-{960,1920}.webp, one shared documentary grade
maps    Terrarium DEM tiles (public, AWS open data) -> assets/map/<name>.svg, real contour lines
terrain 16-bit heightmaps (RG PNG) for the relief object and the contour layers -> assets/terrain/
scandi  Scandinavia base map in transverse Mercator (coast + 600/1200 m) -> assets/map/scandinavia.svg
routes  least-cost routes through the DEM between each expedition's waypoints, elevation profiles
        -> data/derived.json (read by build_pages.py)
logo    the mark geometry of v2/gen.py + Futura Medium outlines -> assets/img/logo-*.svg
grain   assets/img/grain.png, tileable film grain for the intro

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
    "abisko":     ((68.260, 18.550, 68.400, 18.950), 12, 25, 100, (68.3495, 18.8312, "ABISKO")),
    "kebnekaise": ((67.830, 18.380, 67.945, 18.680), 12, 50, 250, (67.9044, 18.5283, "KEBNEKAISE")),
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


# ---------------------------------------------------------------- terrain, routes, Scandinavia
DATA = SITE / "data"
TERRAIN = SITE / "assets/terrain"


def smooth_dem(Z, k=(1, 4, 6, 4, 1)):
    k = np.array(k, np.float32); k /= k.sum()
    Z = np.pad(Z, len(k) // 2, mode="edge")
    Z = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 1, Z)
    return np.apply_along_axis(lambda c: np.convolve(c, k, "valid"), 0, Z)


def area(name):
    bbox, z = MAPS[name][0], MAPS[name][1]
    return bbox, np.maximum(smooth_dem(dem(bbox, z)), -1.0)


def derived():
    f = DATA / "derived.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_derived(d):
    (DATA / "derived.json").write_text(json.dumps(d, separators=(",", ":")))


def terrain():
    """RG-encoded 16-bit heightmaps: R = high byte, G = low byte of (h - min) / (max - min)."""
    TERRAIN.mkdir(parents=True, exist_ok=True)
    d = derived(); d.setdefault("terrain", {})
    for name in MAPS:
        bbox, Z = area(name)
        im = Image.fromarray(Z.astype(np.float32), "F").resize((384, 384), Image.BILINEAR)
        A = np.asarray(im, np.float64)
        lo, hi = float(A.min()), float(A.max())
        q = np.round((A - lo) / (hi - lo) * 65535).astype(np.uint32)
        rgb = np.stack([q >> 8, q & 255, np.zeros_like(q)], -1).astype(np.uint8)
        Image.fromarray(rgb, "RGB").save(TERRAIN / f"{name}.png", optimize=True)
        lat0, lon0, lat1, lon1 = bbox
        w_km = (lon1 - lon0) * 111.32 * math.cos(math.radians((lat0 + lat1) / 2)); h_km = (lat1 - lat0) * 110.57
        d["terrain"][name] = dict(min=round(lo), max=round(hi), bbox=bbox, km=[round(w_km, 2), round(h_km, 2)])
        print("terrain", name, f"{lo:.0f}-{hi:.0f} m", f"{w_km:.1f}x{h_km:.1f} km")
    save_derived(d)


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def routes():
    """Trails follow the ground: a least-cost path (cost grows with slope squared) between waypoints."""
    from skimage.graph import route_through_array
    data = json.loads((DATA / "expeditions.json").read_text())
    d = derived(); d.setdefault("routes", {})
    for e in data["expeditions"]:
        if "route" not in e:
            continue
        bbox, Z = area(e["map"])
        lat0, lon0, lat1, lon1 = bbox
        h, w = Z.shape
        to_px = lambda la, lo: (int(round((lat1 - la) / (lat1 - lat0) * (h - 1))), int(round((lo - lon0) / (lon1 - lon0) * (w - 1))))
        cell = hav((lat0, lon0), (lat0, lon0 + (lon1 - lon0) / w)) * 1000
        gy, gx = np.gradient(Z, cell)
        cost = 1 + 30 * (gx ** 2 + gy ** 2) + 40 * (Z < 0.5)            # steep ground and the sea are expensive
        pts = [to_px(*q) for q in e["route"]]
        for i in e.get("summits", []):                                   # published summit coordinates are rounded:
            r0, c0 = pts[i]; rr = 30                                       # take the highest ground within ~1 km
            win = Z[max(0, r0 - rr):r0 + rr + 1, max(0, c0 - rr):c0 + rr + 1]
            dr, dc = np.unravel_index(np.argmax(win), win.shape)
            pts[i] = (max(0, r0 - rr) + dr, max(0, c0 - rr) + dc)
        path, marks = [], [0]
        for a, b in zip(pts[:-1], pts[1:]):
            seg, _ = route_through_array(cost, a, b, fully_connected=True, geometric=True)
            path += seg if not path else seg[1:]
            marks.append(len(path) - 1)
        P = np.array(path, np.float64)
        k = 5; Ps = np.array([P[max(0, i - k):i + k + 1].mean(0) for i in range(len(P))])  # take the pixel steps out
        lat = lat1 - Ps[:, 0] / (h - 1) * (lat1 - lat0); lon = lon0 + Ps[:, 1] / (w - 1) * (lon1 - lon0)
        elev = Z[P[:, 0].astype(int), P[:, 1].astype(int)]
        dist = np.concatenate([[0], np.cumsum([hav((lat[i], lon[i]), (lat[i + 1], lon[i + 1])) for i in range(len(lat) - 1)])])
        total = float(dist[-1])
        # SVG space of the area map (width 1000) and UV space of the relief (0..1)
        W, H = 1000.0, 1000.0 * h / w
        xy = np.stack([(lon - lon0) / (lon1 - lon0) * W, (lat1 - lat) / (lat1 - lat0) * H], 1)
        keep = rdp(xy, 1.2)
        idx = [int(np.argmin(np.abs(xy[:, 0] - x) + np.abs(xy[:, 1] - y))) for x, y in keep]
        n = 160; samp = np.linspace(0, total, n)
        prof = np.interp(samp, dist, elev)
        top = int(np.argmax(elev))
        d["routes"][e["slug"]] = dict(
            map=e["map"], w=W, h=round(H, 1),
            path=[[round(float(x), 1), round(float(y), 1)] for x, y in keep],
            t=[round(float(dist[i] / total), 4) for i in idx],
            uv=[[round(float(x / W), 4), round(float(y / H), 4)] for x, y in keep],
            ll=[[round(float(lat[i]), 5), round(float(lon[i]), 5), round(float(elev[i]))] for i in idx],
            marks=[round(float(dist[m] / total), 4) for m in marks],
            km=round(total, 1), gain=round(float(np.clip(np.diff(prof), 0, None).sum())),
            profile=[round(float(v)) for v in prof], top=[round(float(lat[top]), 4), round(float(lon[top]), 4), round(float(elev[top]))],
        )
        print("route", e["slug"], f"{total:.1f} km", f"+{d['routes'][e['slug']]['gain']} m", f"top {elev[top]:.0f} m", len(keep), "pts")
    save_derived(d)


# spherical transverse Mercator on 15° E, the meridian Sweden is drawn on
R_E, LON0 = 6371.0, 15.0
def tm(lat, lon):
    la, dl = np.radians(lat), np.radians(np.asarray(lon) - LON0)
    return R_E * np.arctanh(np.cos(la) * np.sin(dl)), R_E * np.arctan2(np.tan(la), np.cos(dl))
def tm_inv(x, y):
    D = y / R_E
    return np.degrees(np.arcsin(np.sin(D) / np.cosh(x / R_E))), LON0 + np.degrees(np.arctan2(np.sinh(x / R_E), np.cos(D)))


def scandi():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.ndimage import map_coordinates
    z = 6
    lat0, lon0, lat1, lon1 = 54.0, 3.0, 71.6, 33.0
    x0, y0 = tile_xy(lat1, lon0, z); x1, y1 = tile_xy(lat0, lon1, z)
    M = dem((lat0, lon0, lat1, lon1), z)                                     # web-mercator mosaic of the bbox
    tx0, ty0 = x0, y0
    # the frame: Norway's coast to Finland's east, Denmark to the North Cape
    X0, X1 = -560.0, 900.0; Y0, Y1 = float(tm(54.5, 15)[1]), float(tm(71.3, 15)[1])
    W = 1000; H = int(round(W * (Y1 - Y0) / (X1 - X0)))
    gx, gy = np.meshgrid(np.linspace(X0, X1, W), np.linspace(Y1, Y0, H))
    la, lo = tm_inv(gx, gy)
    px = [tile_xy(a, b, z) for a, b in [(0, 0)]]  # noqa (keeps tile_xy semantics explicit)
    mx = ((lo + 180) / 360 * 2 ** z - tx0) * 256
    my = ((1 - np.arcsinh(np.tan(np.radians(la))) / math.pi) / 2 * 2 ** z - ty0) * 256
    G = map_coordinates(M, [my, mx], order=1, mode="nearest")
    G = smooth_dem(G, (1, 2, 1))
    from scipy.ndimage import gaussian_filter
    Gm = gaussian_filter(G, 2.2)                                            # the relief lines are generalised, the coast is not
    out = {}
    for lv, wdt, op in [(0.0, 0.9, 1.0), (700.0, 0.45, 0.45), (1300.0, 0.45, 0.7)]:
        cs = plt.contour(np.arange(W), np.arange(H), G if lv == 0 else Gm, levels=[lv])
        segs = []
        for s in cs.allsegs[0]:
            if len(s) < (14 if lv == 0 else 22):
                continue
            s = rdp(np.asarray(s), 0.7)
            segs.append("M" + " ".join(f"{x:.1f} {y:.1f}" for x, y in s))
        plt.close("all")
        out[lv] = (segs, wdt, op)
    to_svg = lambda la_, lo_: (float((tm(la_, lo_)[0] - X0) / (X1 - X0) * W), float((Y1 - tm(la_, lo_)[1]) / (Y1 - Y0) * H))
    grat = []
    for L in (55, 60, 65, 70):
        pts = [to_svg(L, lo_) for lo_ in np.linspace(0, 36, 60)]
        grat.append("M" + " ".join(f"{x:.1f} {y:.1f}" for x, y in pts))
    for Lo in (5, 10, 15, 20, 25, 30):
        pts = [to_svg(la_, Lo) for la_ in np.linspace(53, 72, 40)]
        grat.append("M" + " ".join(f"{x:.1f} {y:.1f}" for x, y in pts))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" fill="none" stroke="#1D1D1B" stroke-linejoin="round" stroke-linecap="round">'
           f'<path stroke-width="0.4" stroke-dasharray="1 4" opacity="0.5" d="{" ".join(grat)}"/>'
           + "".join(f'<path stroke-width="{wdt}" opacity="{op}" d="{" ".join(segs)}"/>' for segs, wdt, op in out.values())
           + "</svg>")
    (MAP / "scandinavia.svg").write_text(svg)
    data = json.loads((DATA / "expeditions.json").read_text())
    d = derived()
    d["scandinavia"] = dict(w=W, h=H,
        stockholm=[round(v, 1) for v in to_svg(59.3417, 18.0572)],
        points={e["slug"]: [round(v, 1) for v in to_svg(e["lat"], e["lon"])] for e in data["expeditions"]},
        lat={L: [round(v, 1) for v in to_svg(L, 4)] for L in (55, 60, 65, 70)})
    save_derived(d)
    print("scandinavia", W, H, len(svg) // 1024, "KB")


if __name__ == "__main__":
    jobs = sys.argv[1:] or ["photos", "maps", "logo", "grain", "terrain", "scandi", "routes"]
    for j in jobs:
        globals()[j]()
