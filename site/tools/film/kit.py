"""Picture primitives for the brand film: camera moves over stills, weather, light, people, type.

Everything is a pure function of time, so any frame can be rendered alone and in any order
(the renderer spreads frames over processes). Frames are float32 RGB in [0, 1], H x W x 3.
"""
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE = Path(__file__).resolve().parents[2]
IMG = SITE / "assets/img"
FONTS = Path(__file__).resolve().parent / ".fonts"      # TTF copies of the site's woff2, made on demand

PAPER = np.array([0xF4, 0xF2, 0xEE], np.float32) / 255
INK = np.array([0x1D, 0x1D, 0x1B], np.float32) / 255
NAVY = np.array([0x0B, 0x1B, 0x2E], np.float32) / 255
ROPE = np.array([0xD9, 0x8E, 0x3C], np.float32) / 255
FOG = np.array([0.80, 0.83, 0.86], np.float32)


class Ctx:
    """Output geometry. u is one pixel of the 1080p master, so sizes scale with the frame."""
    w, h, fps = 1920, 1080, 24
    u = 1.0

    @classmethod
    def set(cls, w, h, fps=24):
        cls.w, cls.h, cls.fps = w, h, fps
        cls.u = min(w, h) / 1080


C = Ctx


# ---------------------------------------------------------------- easing and noise
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease(t):        # slow in, slow out, softer than smoothstep at the ends
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def ramp(t, a, b):
    return smooth((t - a) / (b - a)) if b != a else float(t >= a)


def wob(t, seed, freqs=(0.13, 0.31, 0.57)):
    """Smooth pseudo-random motion in [-1, 1]: a few incommensurate sines, fixed per seed."""
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 2 * math.pi, len(freqs))
    return sum(math.sin(2 * math.pi * f * t + p) for f, p in zip(freqs, ph)) / len(freqs)


# ---------------------------------------------------------------- conversions
def to_pil(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))


def to_arr(im):
    return np.asarray(im, np.float32) * (1 / 255)


def solid(col):
    a = np.empty((C.h, C.w, 3), np.float32)
    a[:] = col
    return a


def gblur(a, sigma):
    """Gaussian blur of a float array (H x W or H x W x 3) through PIL, downsampling for big radii."""
    if sigma <= 0.3:
        return a
    two = a.ndim == 2
    chans = [a] if two else [a[..., i] for i in range(a.shape[2])]
    h, w = chans[0].shape
    k = 1
    while sigma / k > 12 and min(h, w) // (k * 2) > 32:
        k *= 2
    out = []
    for ch in chans:
        im = Image.fromarray(np.ascontiguousarray(ch, np.float32), "F")
        if k > 1:
            im = im.resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
        # PIL has no gaussian for mode F: three box blurs approximate it
        r = sigma / k * 1.1
        arr = np.asarray(im, np.float32)
        arr = _box3(arr, r)
        im = Image.fromarray(arr, "F")
        if k > 1:
            im = im.resize((w, h), Image.BICUBIC)
        out.append(np.array(im, np.float32))
    return out[0] if two else np.stack(out, -1)


def _box(a, r, axis):
    r = int(r)
    if r < 1:
        return a
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float32)
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def _box3(a, sigma):
    r = max(1, int(round(math.sqrt(12 * sigma * sigma / 3 + 1) / 2)))
    for _ in range(3):
        a = _box(_box(a, r, 0), r, 1)
    return a


# ---------------------------------------------------------------- stills and the camera
@lru_cache(maxsize=None)
def photo(name):
    return Image.open(IMG / f"{name}-1920.webp").convert("RGB")


def shot(src, fx, fy, z=1.0, rot=0.0, dx=0.0, dy=0.0):
    """Frame a still. (fx, fy) is the point of the image placed at the centre of the frame, in
    image fractions; z zooms past 'cover'; the view is kept inside the image. dx, dy nudge the
    result in output pixels (handheld). Returns float RGB."""
    im = photo(src) if isinstance(src, str) else src
    iw, ih = im.size
    s = max(C.w / iw, C.h / ih) * z
    hw, hh = C.w / (2 * s), C.h / (2 * s)
    cx = min(max(fx * iw, hw), iw - hw)
    cy = min(max(fy * ih, hh), ih - hh)
    ca, sa = math.cos(rot), math.sin(rot)
    a, b = ca / s, -sa / s
    d, e = sa / s, ca / s
    ox, oy = C.w / 2 + dx, C.h / 2 + dy
    c = cx - a * ox - b * oy
    f = cy - d * ox - e * oy
    out = im.transform((C.w, C.h), Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)
    return to_arr(out)


def src_to_frame(src, fx, fy, z, px, py):
    """Where a point of the image (px, py in fractions) lands in the frame, for compositing
    people and lights into a moving still. Mirrors the clamping in shot()."""
    im = photo(src) if isinstance(src, str) else src
    iw, ih = im.size
    s = max(C.w / iw, C.h / ih) * z
    hw, hh = C.w / (2 * s), C.h / (2 * s)
    cx = min(max(fx * iw, hw), iw - hw)
    cy = min(max(fy * ih, hh), ih - hh)
    return (px * iw - cx) * s + C.w / 2, (py * ih - cy) * s + C.h / 2, s


def hand(t, seed, amp=1.0):
    """Handheld: a breathing drift in pixels and a hair of roll."""
    u = C.u * amp
    return dict(dx=wob(t, seed, (0.21, 0.47, 0.83)) * 5 * u,
                dy=wob(t, seed + 1, (0.17, 0.39, 0.91)) * 4 * u,
                rot=wob(t, seed + 2, (0.11, 0.29)) * 0.0022 * amp)


# ---------------------------------------------------------------- grade
def grade(a, ev=0.0, sat=0.62, contrast=1.08, black=0.012, cool=1.0, lift=0.0):
    """The film's grade, on top of the site's documentary grade: colder, deeper, quieter.
    Shadows lean to the club navy, highlights stay a neutral cold paper."""
    if ev:
        a = a * (2.0 ** ev)
    lum = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    a = lum[..., None] + (a - lum[..., None]) * sat
    # contrast around a low pivot, then set the black point
    p = 0.42
    a = p + (a - p) * contrast
    a = (a - black) / (1 - black)
    np.clip(a, 0, None, out=a)
    # split tone: shadows navy-cold, highlights barely cool
    sh = np.clip(1 - lum * 1.6, 0, 1)[..., None] ** 2
    a += sh * (np.array([-0.018, -0.004, 0.02], np.float32) * cool)
    a += (lum[..., None] ** 2) * (np.array([-0.012, -0.002, 0.008], np.float32) * cool)
    if lift:
        a = a * (1 - lift) + lift * NAVY * 2.2
    return a


def vignette(a, amt=0.28, soft=1.0):
    return a * _vig(C.w, C.h, amt, soft)[..., None]


@lru_cache(maxsize=8)
def _vig(w, h, amt, soft):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x = (x / w - 0.5) * 2
    y = (y / h - 0.5) * 2
    # the long side takes the full falloff, the short side ~70 % of it, whichever way the frame turns
    k = min(w, h) / max(w, h) * 1.25
    if w >= h:
        y = y * k
    else:
        x = x * k
    r = np.sqrt(x * x + y * y) / 1.2
    return (1 - amt * np.clip(r, 0, 1.4) ** (2.2 * soft)).astype(np.float32)


def tonemap(a):
    """Soft shoulder for anything above 1 (lights, bloom); leaves the midtones alone."""
    k = 0.82
    hi = a > k
    if hi.any():
        x = a[hi] - k
        a[hi] = k + (1 - k) * (1 - np.exp(-x / (1 - k)))
    return a


def grain(a, t, amt=0.032, seed=0):
    """Mono film grain, clumped (generated at 2/3 size, scaled up), strongest in the midtones."""
    idx = int(round(t * C.fps)) + seed * 100003
    r = np.random.default_rng(idx & 0x7FFFFFFF)
    gw, gh = int(C.w / 1.5), int(C.h / 1.5)
    g = r.standard_normal((gh, gw), dtype=np.float32)
    g = np.asarray(Image.fromarray(g, "F").resize((C.w, C.h), Image.BICUBIC), np.float32)
    lum = a[..., 1]
    m = 0.35 + 2.6 * lum * (1 - lum)
    return a + (g * m * amt)[..., None]


# ---------------------------------------------------------------- fog
@lru_cache(maxsize=None)
def noise_tex(seed, n=512, beta=3.1):
    """Tileable fractal noise from filtered white noise; returns a PIL F image tiled 3 x 3."""
    r = np.random.default_rng(seed)
    wn = r.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    spec = np.fft.fft2(wn) / f ** (beta / 2)
    spec[0, 0] = 0
    v = np.real(np.fft.ifft2(spec))
    v = (v - v.mean()) / (v.std() * 4.0) + 0.5
    v = np.clip(v, 0, 1).astype(np.float32)
    return Image.fromarray(np.tile(v, (3, 3)), "F"), n


def noise(seed, scale, ox, oy, ang=0.0):
    """Sample the tiled noise over the frame: one tile spans `scale` frame widths."""
    tex, n = noise_tex(seed)
    s = n / (scale * C.w)
    ca, sa = math.cos(ang), math.sin(ang)
    ox, oy = (ox % 1) * n + n, (oy % 1) * n + n
    out = tex.transform((C.w, C.h), Image.AFFINE, (ca * s, -sa * s, ox, sa * s, ca * s, oy),
                        resample=Image.BILINEAR)
    return np.asarray(out, np.float32)


def fog(a, t, dens=0.6, col=FOG, scale=1.3, vx=0.012, vy=0.0, lo=0.35, hi=0.8, prof=None,
        seed=11, veil=0.0):
    """Drifting fog: two noise layers at different scales and speeds; `prof` shapes it by height
    (callable on y in 0..1, top to bottom). `veil` adds an even haze."""
    n1 = noise(seed, scale, t * vx, t * vy)
    n2 = noise(seed + 1, scale * 0.45, -t * vx * 0.6 + 0.37, t * vy * 0.4 + 0.11, 0.4)
    n = n1 * 0.62 + n2 * 0.38
    al = np.clip((n - lo) / (hi - lo), 0, 1)
    al = al * al * (3 - 2 * al) * dens
    if prof is not None:
        y = np.linspace(0, 1, C.h, dtype=np.float32)
        al *= np.asarray([prof(v) for v in y], np.float32)[:, None]
    if veil:
        al = veil + al * (1 - veil)
    al = al[..., None]
    return a * (1 - al) + np.asarray(col, np.float32) * al


# ---------------------------------------------------------------- particles
def particles(t, n, seed, wind=(0.03, 0.06), size=(1.0, 3.2), streak=1.0, bright=(0.35, 1.0),
              turb=0.012, depth_speed=True, region=None):
    """Snow, spindrift, rain. Positions are analytic in t, so every frame stands alone.
    Returns a float intensity layer (H x W) to be added or screened over the frame.
    wind: frame widths / heights per second for the nearest flakes; streak: shutter length (1 = 180°)."""
    r = np.random.default_rng(seed)
    x0, y0 = r.random(n), r.random(n)
    d = r.random(n) ** 1.6                                   # depth: 1 near, 0 far
    ph = r.uniform(0, 2 * math.pi, (n, 2))
    fr = r.uniform(0.3, 1.1, n)
    sp = (0.25 + 0.75 * d) if depth_speed else np.ones(n)
    sz = size[0] + (size[1] - size[0]) * d
    br = bright[0] + (bright[1] - bright[0]) * d
    layer = np.zeros((C.h + 8, C.w + 8), np.float32)
    ksub = 7
    shutter = 1 / (2 * C.fps) * streak
    for k in range(ksub):
        tt = t - shutter * k / (ksub - 1)
        x = x0 + wind[0] * sp * tt + turb * np.sin(fr * tt * 2.1 + ph[:, 0])
        y = y0 + wind[1] * sp * tt + turb * np.sin(fr * tt * 1.7 + ph[:, 1])
        x = (x % 1.0) * (C.w + 40) - 20
        y = (y % 1.0) * (C.h + 40) - 20
        _splat(layer, x + 4, y + 4, br / ksub)
    layer = layer[4:-4, 4:-4]
    # two size classes, blurred to their own radius
    out = gblur(layer, max(0.6, size[0] * 0.55 * C.u))
    if size[1] > 1.8:
        out = out * 0.55 + gblur(layer, size[1] * 0.6 * C.u) * 0.45 * (size[1] / 1.5)
    out = out * ((sz.mean() ** 2) * 0.9)
    if region is not None:
        out *= region
    return out


def _splat(buf, x, y, w):
    h_, w_ = buf.shape
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - ix).astype(np.float32), (y - iy).astype(np.float32)
    ok = (ix >= 0) & (iy >= 0) & (ix < w_ - 1) & (iy < h_ - 1)
    ix, iy, fx, fy = ix[ok], iy[ok], fx[ok], fy[ok]
    w = np.broadcast_to(np.asarray(w, np.float32), ok.shape)[ok]
    np.add.at(buf, (iy, ix), w * (1 - fx) * (1 - fy))
    np.add.at(buf, (iy, ix + 1), w * fx * (1 - fy))
    np.add.at(buf, (iy + 1, ix), w * (1 - fx) * fy)
    np.add.at(buf, (iy + 1, ix + 1), w * fx * fy)


def screen(a, layer, col=(0.92, 0.94, 0.96), amt=1.0):
    l = np.clip(layer * amt, 0, 1)[..., None]
    return a + (np.asarray(col, np.float32) - a) * l


# ---------------------------------------------------------------- light
def glow(points, core=1.2, halo=10.0, big=60.0, col=(1.0, 0.96, 0.9), gain=1.0, flare=0.0, hf=0.22, bf=0.06):
    """Point lights as an HDR layer: a hot core, a halo and a wide bloom. points: [(x, y, k)].
    A light of strength k peaks at k in its core, hf*k in its halo and bf*k in its bloom."""
    buf = np.zeros((C.h + 8, C.w + 8), np.float32)
    if len(points):
        p = np.asarray(points, np.float32)
        _splat(buf, p[:, 0] + 4, p[:, 1] + 4, p[:, 2])
    buf = buf[4:-4, 4:-4]
    tau = 2 * math.pi
    sc, sh, sb = max(core * C.u, 1.0), halo * C.u, big * C.u
    l = gblur(buf, sc) * (tau * (sc * 1.3) ** 2) + gblur(buf, sh) * (hf * tau * sh * sh) \
        + gblur(buf, sb) * (bf * tau * sb * sb)
    if flare:
        l += _hstreak(buf, flare)
    return l[..., None] * np.asarray(col, np.float32) * gain


def _hstreak(buf, amt):
    im = Image.fromarray(buf, "F")
    small = im.resize((C.w // 8, C.h), Image.BILINEAR)
    arr = _box(_box(np.asarray(small, np.float32), 18, 1), 12, 1)
    return np.asarray(Image.fromarray(arr, "F").resize((C.w, C.h), Image.BILINEAR)) * amt * 40


# ---------------------------------------------------------------- people
def figure(h, phase=0.0, walk=1.0, facing=1, pack=True, pole=False, lean=0.0, sub=(0.0, 0.0)):
    """A hiker in silhouette, `h` pixels tall, as an alpha mask (PIL L) and its anchor (feet).
    Drawn 8x large and reduced, so small figures keep soft, correct edges. phase in cycles."""
    k = 8
    H = h * k
    pad = int(H * 0.5)
    im = Image.new("L", (int(H * 1.2) + 2 * pad, int(H * 1.15) + 2 * pad), 0)
    dr = ImageDraw.Draw(im)
    fx0 = im.width / 2 + sub[0] * k
    fy0 = pad + H + sub[1] * k                               # feet line
    s = facing
    sw = math.sin(phase * 2 * math.pi) * walk
    bob = abs(math.cos(phase * 2 * math.pi)) * 0.018 * H * walk
    hip = (fx0 + lean * 0.1 * H * s, fy0 - 0.50 * H + bob)
    sh = (fx0 + lean * 0.22 * H * s + 0.02 * H * s, fy0 - 0.83 * H + bob)
    lw = 0.095 * H

    def leg(a):
        knee = (hip[0] + math.sin(a) * 0.25 * H * s, hip[1] + math.cos(a) * 0.25 * H)
        back = max(0.0, -a)
        foot = (knee[0] + math.sin(a - back * 0.9) * 0.25 * H * s, min(fy0, knee[1] + 0.25 * H))
        dr.line([hip, knee, foot], fill=255, width=int(lw), joint="curve")
        dr.ellipse([foot[0] - lw * 0.45, foot[1] - lw * 0.55, foot[0] + lw * 0.9 * s if s > 0 else foot[0] + lw * 0.45,
                    foot[1] + lw * 0.1], fill=255)

    stance = 0.07 * (1 - walk)
    leg(0.42 * sw + stance)
    leg(-0.42 * sw - stance)
    # torso, a bulky shell jacket
    dr.line([hip, sh], fill=255, width=int(0.19 * H), joint="curve")
    dr.ellipse([sh[0] - 0.105 * H, sh[1] - 0.045 * H, sh[0] + 0.105 * H, sh[1] + 0.07 * H], fill=255)
    if pack:
        bx = sh[0] - 0.13 * H * s
        dr.rounded_rectangle([min(bx - 0.09 * H, bx + 0.09 * H), sh[1] - 0.02 * H,
                              max(bx - 0.09 * H, bx + 0.09 * H), sh[1] + 0.33 * H], radius=0.04 * H, fill=255)
        dr.rounded_rectangle([bx - 0.07 * H, sh[1] - 0.07 * H, bx + 0.07 * H, sh[1] + 0.02 * H],
                             radius=0.03 * H, fill=255)
    # arms swing against the legs
    for a in (-0.5 * sw - 0.1 * (1 - walk), 0.5 * sw + 0.1 * (1 - walk)):
        el = (sh[0] + math.sin(a) * 0.17 * H * s, sh[1] + math.cos(a) * 0.17 * H)
        hd = (el[0] + math.sin(a + 0.35) * 0.16 * H * s, el[1] + 0.15 * H)
        dr.line([sh, el, hd], fill=255, width=int(0.06 * H), joint="curve")
        if pole:
            dr.line([hd, (hd[0] + 0.05 * H * s, fy0)], fill=255, width=max(1, int(0.014 * H)))
    # head and hat
    hc = (sh[0] + 0.02 * H * s, sh[1] - 0.11 * H)
    r = 0.062 * H
    dr.ellipse([hc[0] - r, hc[1] - r, hc[0] + r, hc[1] + r * 1.05], fill=255)
    dr.ellipse([hc[0] - r * 1.05, hc[1] - r * 1.25, hc[0] + r * 1.05, hc[1] + r * 0.2], fill=255)
    small = im.resize((max(1, im.width // k), max(1, im.height // k)), Image.LANCZOS)
    return small, (fx0 / k, fy0 / k)


def put_figure(a, x, y, h, col, phase=0.0, walk=1.0, facing=1, alpha=1.0, pack=True, pole=False,
               lean=0.0, haze=0.0, haze_col=FOG, shadow=0.0):
    """Composite a figure with its feet at (x, y) in frame pixels."""
    if h < 1.5 or alpha <= 0:
        return a
    fx, fy = math.floor(x), math.floor(y)
    m, (ax, ay) = figure(h, phase, walk, facing, pack, pole, lean, sub=(x - fx, y - fy))
    m = np.asarray(m, np.float32) * (alpha / 255)
    x0, y0 = int(fx - ax), int(fy - ay)
    x1, y1 = x0 + m.shape[1], y0 + m.shape[0]
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(C.w, x1), min(C.h, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        return a
    mm = m[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0][..., None]
    c = np.asarray(col, np.float32) * (1 - haze) + np.asarray(haze_col, np.float32) * haze
    if shadow:
        # contact shadow: a short soft smear on the snow at the feet
        sy = int(fy)
        sx0, sx1 = int(fx - h * 0.35), int(fx + h * 0.55)
        if 0 <= sy < C.h - 2 and sx1 > 0 and sx0 < C.w:
            sl = slice(max(0, sx0), min(C.w, sx1))
            a[sy:sy + 2, sl] *= 1 - shadow * alpha
    a[cy0:cy1, cx0:cx1] = a[cy0:cy1, cx0:cx1] * (1 - mm) + c * mm
    return a


# ---------------------------------------------------------------- type
def font_path(name):
    FONTS.mkdir(exist_ok=True)
    out = FONTS / f"{name}.ttf"
    if not out.exists():
        from fontTools.ttLib import TTFont
        f = TTFont(SITE / f"assets/fonts/{name}.woff2")
        f.flavor = None
        f.save(out)
    return str(out)


@lru_cache(maxsize=None)
def font(kind, px, wght=None):
    if kind == "serif":
        f = ImageFont.truetype(font_path("newsreader"), px)
        axes = {"wght": wght or 340, "opsz": 72 if px > 40 else 36}
    elif kind == "italic":
        f = ImageFont.truetype(font_path("newsreader-italic"), px)
        axes = {"wght": wght or 340, "opsz": 72 if px > 40 else 36}
    else:
        f = ImageFont.truetype(font_path("schibsted-grotesk"), px)
        axes = {"wght": wght or 480}
    try:
        names = [a["name"] if isinstance(a["name"], str) else a["name"].decode() for a in f.get_variation_axes()]
        tags = {"Weight": "wght", "Optical size": "opsz", "Optical Size": "opsz"}
        vals = []
        for a, nm in zip(f.get_variation_axes(), names):
            tag = tags.get(nm, nm[:4].lower())
            vals.append(axes.get(tag, a["default"]))
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


@lru_cache(maxsize=512)
def text_mask(txt, kind, px, track=0.0, wght=None):
    """A line of type as an L mask, tracked by hand (PIL has no letter-spacing). Cached."""
    f = font(kind, px, wght)
    if track == 0:
        l, t_, r, b = f.getbbox(txt)
        asc, desc = f.getmetrics()
        im = Image.new("L", (int(r - min(l, 0)) + 4, asc + desc + 4), 0)
        ImageDraw.Draw(im).text((2 - min(l, 0), 2), txt, font=f, fill=255)
        return im, asc + 2
    asc, desc = f.getmetrics()
    ws = [f.getlength(ch) for ch in txt]
    tr = track * px
    total = sum(ws) + tr * (len(txt) - 1)
    im = Image.new("L", (int(total) + 6, asc + desc + 4), 0)
    d = ImageDraw.Draw(im)
    x = 2.0
    for ch, w in zip(txt, ws):
        d.text((x, 2), ch, font=f, fill=255)
        x += w + tr
    return im, asc + 2


def put_text(a, txt, x, y, kind="sans", px=20, col=PAPER, alpha=1.0, align="left", track=0.0,
             wght=None, blur=0.0, anchor="baseline"):
    """Set type at (x, y): x per align, y on the baseline (or the top with anchor='top')."""
    if alpha <= 0.002 or not txt:
        return a
    im, base = text_mask(txt, kind, int(round(px)), track, wght)
    m = np.asarray(im, np.float32) * (alpha / 255)
    if blur > 0.3:
        m = gblur(np.pad(m, int(blur * 3)), blur)
        pad = int(blur * 3)
    else:
        pad = 0
    w_ = m.shape[1] - 2 * pad
    x0 = x - (w_ / 2 if align == "center" else w_ if align == "right" else 0) - 2 - pad
    y0 = y - (base if anchor == "baseline" else 2) - pad
    x0, y0 = int(round(x0)), int(round(y0))
    x1, y1 = x0 + m.shape[1], y0 + m.shape[0]
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(C.w, x1), min(C.h, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        return a
    mm = m[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0][..., None]
    a[cy0:cy1, cx0:cx1] = a[cy0:cy1, cx0:cx1] * (1 - mm) + np.asarray(col, np.float32) * mm
    return a


def text_width(txt, kind="sans", px=20, track=0.0, wght=None):
    im, _ = text_mask(txt, kind, int(round(px)), track, wght)
    return im.width - 6 if track else im.width - 4


@lru_cache(maxsize=4)
def logo(width):
    """The vertical lockup (mark over HIKING CLUB), from the outlined SVG, as an L mask."""
    import cairosvg, io
    png = cairosvg.svg2png(url=str(IMG / "logo-vertical.svg"), output_width=int(width))
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    return im.split()[3]


def put_mask(a, m, x, y, col, alpha=1.0):
    """Composite an L mask with its top-left at (x, y)."""
    m = np.asarray(m, np.float32) * (alpha / 255)
    x0, y0 = int(round(x)), int(round(y))
    x1, y1 = x0 + m.shape[1], y0 + m.shape[0]
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(C.w, x1), min(C.h, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        return a
    mm = m[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0][..., None]
    a[cy0:cy1, cx0:cx1] = a[cy0:cy1, cx0:cx1] * (1 - mm) + np.asarray(col, np.float32) * mm
    return a


# ---------------------------------------------------------------- the real hiker, cloned
@lru_cache(maxsize=None)
def hiker(variant=0):
    """The hiker of the Lapporten photograph, cut out of it (he is the only person in the film we
    did not draw). Variants recolour the red shell; the mask is built from colour and darkness
    against the mountain behind him. Returns RGBA, feet at the bottom centre."""
    im = photo("abisko-lapporten-figure").crop((340, 715, 450, 890))
    a = np.asarray(im, np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    red = (r - np.maximum(g, b)) > 0.1
    dark = lum < 0.13
    h, w = lum.shape
    yy, xx = np.mgrid[0:h, 0:w]
    body = ((xx - 55) / 34.0) ** 2 + ((yy - 90) / 90.0) ** 2 < 1.0          # where he can be
    body &= (yy < 86) | (np.abs(xx - 50) < 21 - np.clip(yy - 150, 0, 8) * 0)
    m = (red | dark) & body & (yy < 166)
    mi = Image.fromarray((m * 255).astype(np.uint8))
    mi = mi.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))   # close small holes
    m = np.asarray(mi, np.float32) / 255
    # keep the largest blob: flood from the torso
    from collections import deque
    keep = np.zeros_like(m, bool)
    q = deque([(60, 55)])
    while q:
        y, x = q.popleft()
        if 0 <= y < h and 0 <= x < w and not keep[y, x] and m[y, x] > 0.5:
            keep[y, x] = True
            q.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
    m = gblur(keep.astype(np.float32), 0.6)
    rgb = a.copy()
    if variant:
        # recolour the shell, keep its folds: navy, slate, a faded yellow
        tint = [None, (0.16, 0.22, 0.34), (0.3, 0.32, 0.33), (0.5, 0.44, 0.24), (0.2, 0.28, 0.24)][variant]
        sh = np.clip((r - np.maximum(g, b) - 0.05) / 0.2, 0, 1)[..., None]
        shade = (lum / max(lum[red].mean(), 1e-3))[..., None] if red.any() else 1
        rgb = rgb * (1 - sh) + np.asarray(tint, np.float32) * np.clip(shade, 0.3, 1.6) * sh
    ys = np.where(keep.any(1))[0]
    xs = np.where(keep.any(0))[0]
    y0, y1, x0, x1 = ys[0], ys[-1] + 1, xs[0], xs[-1] + 1
    out = np.dstack([rgb, m])[y0:y1, x0:x1]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


def put_hiker(a, x, y, h, variant=0, mirror=False, alpha=1.0, haze=0.0, haze_col=FOG, soft=0.0):
    """Composite the real hiker with feet at (x, y), h pixels tall, subpixel placed."""
    sp = hiker(variant)
    if mirror:
        sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
    s = h / sp.height
    w = sp.width * s
    X0, Y0 = math.floor(x - w / 2), math.floor(y - h)
    fx, fy = (x - w / 2) - X0, (y - h) - Y0
    W_, H_ = int(math.ceil(w)) + 3, int(math.ceil(h)) + 3
    tr = sp.transform((W_, H_), Image.AFFINE, (1 / s, 0, -fx / s, 0, 1 / s, -fy / s), resample=Image.BICUBIC)
    if s < 0.9:  # reduce with a proper filter first, then place
        small = sp.resize((max(1, int(round(sp.width * s * 2))), max(1, int(round(sp.height * s * 2)))), Image.LANCZOS)
        s2 = small.height / (h)
        tr = small.transform((W_, H_), Image.AFFINE, (s2, 0, -fx * s2, 0, s2, -fy * s2), resample=Image.BILINEAR)
    arr = np.asarray(tr, np.float32) / 255
    rgb, m = arr[..., :3], arr[..., 3:] * alpha
    if soft:
        rgb, m = gblur(rgb, soft), gblur(m[..., 0], soft)[..., None]
    rgb = rgb * (1 - haze) + np.asarray(haze_col, np.float32) * haze
    cx0, cy0 = max(0, X0), max(0, Y0)
    cx1, cy1 = min(C.w, X0 + W_), min(C.h, Y0 + H_)
    if cx0 >= cx1 or cy0 >= cy1:
        return a
    sl = (slice(cy0 - Y0, cy1 - Y0), slice(cx0 - X0, cx1 - X0))
    a[cy0:cy1, cx0:cx1] = a[cy0:cy1, cx0:cx1] * (1 - m[sl]) + rgb[sl] * m[sl]
    return a
