"""Procedural scenes for the film: what no photograph in the repo shows.

Stockholm is drawn as geometry (a boulevard of lamps, a lit doorway, rain on a window, rows of
ceiling lights, a spreadsheet, a tunnel); the journey as light in the dark (the night train, a
line of headlamps, a map under a headlamp, a hut). Every function takes local time t (s) and
returns a float RGB frame at the current Ctx size.
"""
import json
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from kit import (C, PAPER, ROPE, SITE, clamp, fog, gblur, glow, grade, noise, particles, put_figure,
                 put_text, ramp, screen, shot, smooth, src_to_frame, tonemap, wob, _box, _splat)


def _rng(seed):
    return np.random.default_rng(seed)


@lru_cache(maxsize=16)
def _grid(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x, y


# ---------------------------------------------------------------- a simple pinhole camera
@lru_cache(maxsize=8)
def _rays(w, h, fov, pitch, yaw):
    """Unit ray directions for every pixel (x right, y up, z forward)."""
    x, y = _grid(w, h)
    tf = math.tan(math.radians(fov) / 2)
    px = (x - w / 2 + 0.5) / (h / 2) * tf
    py = (h / 2 - y - 0.5) / (h / 2) * tf
    d = np.stack([px, py, np.ones_like(px)], -1)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    dy = d[..., 1] * cp + d[..., 2] * sp
    dz = -d[..., 1] * sp + d[..., 2] * cp
    dx = d[..., 0] * cy_ + dz * sy_
    dz = -d[..., 0] * sy_ + dz * cy_
    d = np.stack([dx, dy, dz], -1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    return d.astype(np.float32)


def _project(pts, cam, fov, pitch, yaw):
    """World points (N x 3) to pixels; returns x, y, depth (z in camera space)."""
    p = np.asarray(pts, np.float32) - np.asarray(cam, np.float32)
    cy_, sy_ = math.cos(-yaw), math.sin(-yaw)
    x = p[:, 0] * cy_ + p[:, 2] * sy_
    z = -p[:, 0] * sy_ + p[:, 2] * cy_
    cp, sp = math.cos(-pitch), math.sin(-pitch)
    y = p[:, 1] * cp + z * sp
    z = -p[:, 1] * sp + z * cp
    tf = math.tan(math.radians(fov) / 2)
    sx = C.w / 2 + x / z / tf * (C.h / 2)
    sy = C.h / 2 - y / z / tf * (C.h / 2)
    return sx, sy, z


def _hash(*a):
    v = np.zeros_like(np.asarray(a[0], np.float64))
    for i, k in enumerate(a):
        v = v + np.asarray(k, np.float64) * (12.9898 + 31.7 * i)
    return (np.sin(v) * 43758.5453) % 1.0


# ---------------------------------------------------------------- Stockholm: Sveavägen at dawn
def street(t, dur):
    """Long lens down a straight avenue before sunrise: lamps receding into fog, wet asphalt,
    facades with a few lit windows, one car coming, two people far off."""
    fov, pitch, yaw = 9.5, 0.012, 0.0
    cam = np.array([0.6, 1.7, -40 + t * 1.1], np.float32)
    d = _rays(C.w, C.h, fov, pitch, yaw)
    dx, dy, dz = d[..., 0], d[..., 1], d[..., 2]
    XL, XR, BH = -19.0, 19.0, 24.0
    big = np.float32(1e6)
    with np.errstate(divide="ignore", invalid="ignore"):
        tg = np.where(dy < -1e-5, -cam[1] / dy, big)
        tr = np.where(dx > 1e-5, (XR - cam[0]) / dx, big)
        tl = np.where(dx < -1e-5, (XL - cam[0]) / dx, big)
    # facades only up to the roofline
    yr = cam[1] + dy * tr
    tr = np.where(yr < BH, tr, big)
    yl = cam[1] + dy * tl
    tl = np.where(yl < BH + 3, tl, big)
    tt = np.minimum(np.minimum(tg, tr), tl)
    sky = tt >= big
    img = np.zeros((C.h, C.w, 3), np.float32)

    # ground: asphalt, a pale kerb line and lane dashes, wet
    hx = cam[0] + dx * tg
    hz = cam[2] + dz * tg
    g = tg == tt
    asph = np.full(hx.shape, 0.055, np.float32)
    kerb = (np.abs(np.abs(hx) - 12.5) < 0.12)
    walk = np.abs(hx) > 12.5
    lane = (np.abs(np.abs(hx) - 4.2) < 0.08) & ((hz % 12) < 5)
    asph = np.where(walk, 0.085, asph)
    asph = np.where(kerb, 0.16, asph)
    asph = np.where(lane, 0.24, asph)
    img[g] = (asph[g][:, None] * np.array([0.95, 1.0, 1.05], np.float32))

    # facades: storeys of 3.4 m, windows every 3.2 m, a few lit (the city waking)
    for tp, sgn in ((tr, 1), (tl, -1)):
        m = (tp == tt) & ~sky
        zz = cam[2] + dz * tp
        yy = cam[1] + dy * tp
        fl = np.floor((yy - 0.6) / 3.4)
        col = np.floor(zz / 3.2)
        fy = ((yy - 0.6) / 3.4) % 1
        fz = (zz / 3.2) % 1
        win = (fy > 0.28) & (fy < 0.82) & (fz > 0.22) & (fz < 0.72) & (fl >= 1)
        shop = (fl < 1) & (fy > 0.15) & (fy < 0.85) & (fz > 0.08) & (fz < 0.92)
        base = np.full(zz.shape, 0.20, np.float32)
        hsh = _hash(fl, col, sgn)
        lit = win & (hsh > 0.94)
        warm = hsh > 0.93
        c = np.stack([base, base * 1.02, base * 1.06], -1)
        c = np.where(win[..., None], np.array([0.05, 0.06, 0.075], np.float32), c)
        c = np.where(shop[..., None], np.array([0.07, 0.075, 0.08], np.float32), c)
        lc = np.where(warm[..., None], np.array([1.0, 0.78, 0.52], np.float32), np.array([0.75, 0.84, 1.0], np.float32))
        c = np.where(lit[..., None], lc * 0.55, c)
        # cornices, a line every storey
        c = np.where((fy < 0.05)[..., None], c * 1.35, c)
        img[m] = c[m]

    # fog by distance, brighter toward the horizon; sky is the fog itself
    fogc_top = np.array([0.34, 0.39, 0.46], np.float32)
    fogc_hor = np.array([0.52, 0.56, 0.61], np.float32)
    _, yv = _grid(C.w, C.h)
    hv = np.clip(1 - np.abs(yv / C.h - 0.47) * 2.4, 0, 1)[..., None]
    fc = fogc_top + (fogc_hor - fogc_top) * hv
    dist = np.where(sky, 1e4, tt)
    tr_ = np.exp(-dist / 95.0)[..., None]
    img = img * tr_ + fc * (1 - tr_)

    # the geometry is a little soft (long lens, focus far): blur before the lights go on
    img = gblur(img, 1.6 * C.u)
    # lamps: both sides every 34 m, and their reflections in the wet road. Light sources are
    # far brighter than what they light, so they read through fog that hides the buildings.
    zs = np.arange(-40, 900, 34.0)
    pts = [(sx, 8.6, z) for z in zs for sx in (-14.5, 14.5)]
    cz = 520 - t * 16
    pts_car = [(-3.2, 0.7, cz), (-1.6, 0.7, cz)]
    pts_tail = [(3.0, 0.8, 140 + t * 9), (4.4, 0.8, 140 + t * 9)]
    near, far, red, rl = [], [], [], []
    for group, kind, kk in ((pts, "lamp", 1.0), (pts_car, "car", 1.4), (pts_tail, "red", 0.9)):
        sx, sy, sz = _project(group, cam, fov, pitch, yaw)
        for (wx, wy, wz), x_, y_, z_ in zip(group, sx, sy, sz):
            if z_ <= 1 or x_ < -200 or x_ > C.w + 200:
                continue
            a = 5.0 * math.exp(-z_ / 170.0) * kk
            _, ry, _ = _project([(wx, -wy, wz)], cam, fov, pitch, yaw)
            if kind == "red":
                red.append((x_, y_, a * 0.6))
            else:
                (near if z_ < 260 else far).append((x_, y_, a))
            rl.append((x_, ry[0], a * (0.5 if kind != "red" else 0.3)))
    img = img + glow(near, core=1.1, halo=10, big=60, col=(1.0, 0.9, 0.76), gain=0.4)
    img = img + glow(far, core=0.9, halo=7, big=45, col=(1.0, 0.9, 0.76), gain=0.4)
    img = img + glow(red, core=1.0, halo=6, big=30, col=(1.0, 0.16, 0.1), gain=0.45)
    if rl:
        layer = np.zeros((C.h + 8, C.w + 8), np.float32)
        p = np.asarray(rl, np.float32)
        _splat(layer, p[:, 0] + 4, p[:, 1] + 4, p[:, 2])
        layer = layer[4:-4, 4:-4]
        layer = _box(_box(layer, int(3 * C.u), 1), int(30 * C.u), 0)
        layer = gblur(layer, 3 * C.u) * 14
        img = img + layer[..., None] * np.array([0.95, 0.85, 0.72], np.float32) * g[..., None]

    # two people on the far pavement
    for i, (px_, pz, sp) in enumerate(((-15.5, 70, 1.3), (15.8, 95, -1.2))):
        x_, y_, z_ = _project([(px_, 0.0, pz + sp * t)], cam, fov, pitch, yaw)
        hgt = 1.75 / z_[0] / math.tan(math.radians(fov) / 2) * (C.h / 2)
        img = put_figure(img, x_[0], y_[0], hgt, (0.05, 0.055, 0.065), phase=t * 0.9 + i * 0.4,
                         facing=-1 if sp < 0 else 1, haze=1 - math.exp(-z_[0] / 95.0), haze_col=fogc_hor, pack=i == 0)
    img = fog(img, t, dens=0.25, col=fogc_hor, scale=2.0, vx=0.01, lo=0.4, hi=0.9)
    return tonemap(img)


# ---------------------------------------------------------------- Stockholm: the doors
def doors(t, dur):
    """Across the street, long lens: a lit double door in a dark facade before eight, people
    going in one after another. A figure crosses close to the lens, out of focus."""
    x, y = _grid(C.w, C.h)
    u = C.u
    wall = 0.05 + 0.02 * noise(31, 0.35, 0.2, 0.3) + 0.012 * noise(32, 0.08, 0.5, 0.1)
    img = np.stack([wall, wall * 1.01, wall * 1.06], -1).astype(np.float32)
    cx = C.w * 0.28 + wob(t, 3, (0.07, 0.19)) * 6 * u
    dw, dh = 380 * u, 520 * u
    base = C.h * 0.86
    x0, x1, y0, y1 = cx - dw / 2, cx + dw / 2, base - dh, base
    # stone surround, then the glass: warm light from inside, mullions, a transom
    sur = (x > x0 - 30 * u) & (x < x1 + 30 * u) & (y > y0 - 40 * u) & (y < y1)
    img[sur] = img[sur] * 1.25
    inside = (x > x0) & (x < x1) & (y > y0) & (y < y1)
    grad = np.clip((y - y0) / dh, 0, 1)
    light = (1.25 - 0.35 * grad)[..., None] * np.array([1.0, 0.9, 0.76], np.float32)
    img = np.where(inside[..., None], light, img)
    mull = inside & ((np.abs(x - cx) < 5 * u) | (np.abs(y - (y0 + dh * 0.24)) < 4 * u)
                     | (np.abs(x - x0) < 7 * u) | (np.abs(x - x1) < 7 * u))
    img[mull] = 0.05
    # windows above, dark, two lit
    for r in range(2):
        for c in range(-4, 5):
            if c == 0 and r == 0:
                continue
            wx = cx + c * 300 * u
            wy = y0 - 170 * u - r * 330 * u
            m = (np.abs(x - wx) < 72 * u) & (y > wy - 180 * u) & (y < wy)
            lit = (r, c) in ((1, 2),)
            refl = 0.035 + 0.03 * np.clip((y - wy + 120 * u) / (120 * u), 0, 1)
            img[m] = (np.array([0.5, 0.42, 0.32], np.float32) if lit else (refl[m][:, None] * np.array([0.9, 1.0, 1.15], np.float32)))
    # pavement: wet, with the door's reflection
    pav = y > base
    img[pav] = np.array([0.06, 0.065, 0.075], np.float32)
    refl = pav & (x > x0) & (x < x1)
    fall = np.clip(1 - (y - base) / (C.h - base), 0, 1)
    img = img + (refl * fall * 0.35)[..., None] * np.array([1.0, 0.88, 0.72], np.float32)
    # people walking in: they reach the door and are taken by the light
    for i, (start, side, h_) in enumerate(((0.0, -1, 0.94), (0.8, 1, 1.0), (1.7, -1, 0.9), (2.5, 1, 0.97))):
        tt_ = t - start
        if tt_ < 0:
            continue
        walk_t = 2.2
        k = clamp(tt_ / walk_t)
        px = cx + side * (1 - k) * 760 * u + side * 26 * u * (i % 2)
        fade = 1 - ramp(tt_, walk_t - 0.25, walk_t + 0.25)
        hh = 330 * u * h_ * (1 - 0.1 * ramp(tt_, walk_t - 0.3, walk_t + 0.3))
        img = put_figure(img, px, base - 2 * u + (0 if k < 0.95 else -8 * u), hh, (0.02, 0.022, 0.03),
                         phase=tt_ * 0.95 + i * 0.3, facing=-side, alpha=fade, pack=i % 2 == 0)
    # wall lit by the doorway, falling off
    glowwall = np.exp(-(((x - cx) / (420 * u)) ** 2 + ((y - base + dh * 0.5) / (380 * u)) ** 2))
    img = img + glowwall[..., None] * np.array([0.13, 0.1, 0.07], np.float32)
    # focus is on the rain in front: everything behind it is soft
    img = gblur(img, 8.0 * u)
    hot = np.clip(img - 0.75, 0, None)
    img = img + gblur(hot, 16 * u) * 1.1 + gblur(hot, 70 * u) * 0.8
    img = fog(img, t, dens=0.16, col=(0.3, 0.34, 0.4), scale=1.6, vx=0.02, lo=0.4, hi=0.9, veil=0.05)
    rain = particles(t, 520, 33, wind=(0.02, 1.9), size=(0.7, 1.3), streak=2.2, bright=(0.15, 0.7), turb=0.0,
                     depth_speed=True)
    lit = 0.35 + 1.4 * np.exp(-(((x - cx) / (520 * u)) ** 2))
    img = screen(img, rain * lit, col=(0.85, 0.82, 0.78), amt=0.55)
    # a passer-by close to the lens: a dark soft shape crossing
    k = (t - 1.05) / 1.25
    if 0 < k < 1:
        xm = C.w * (1.15 - 1.35 * k)
        m = np.exp(-(((x - xm) / (230 * u)) ** 2)) * np.clip((y - C.h * 0.05) / (C.h * 0.3), 0, 1)
        m = gblur(m.astype(np.float32), 30 * u)
        img = img * (1 - 0.94 * m[..., None]) + 0.01 * m[..., None]
    return tonemap(img)


# ---------------------------------------------------------------- Stockholm: rain on the window
@lru_cache(maxsize=2)
def _drops(w, h, seed=7):
    """A height field of water drops on glass (static ones) and their mask."""
    r = _rng(seed)
    k = 2
    hf = np.zeros((h // k, w // k), np.float32)
    yy, xx = np.mgrid[0:h // k, 0:w // k].astype(np.float32)
    n = int(560 * (w * h) / (1920 * 1080))
    for _ in range(n):
        rad = (r.random() ** 2.4) * 12 + 1.5
        cx_, cy_ = r.random() * w / k, r.random() * h / k
        x0, x1 = int(max(0, cx_ - rad - 1)), int(min(w // k, cx_ + rad + 2))
        y0, y1 = int(max(0, cy_ - rad * 1.2 - 1)), int(min(h // k, cy_ + rad * 1.2 + 2))
        sx = (xx[y0:y1, x0:x1] - cx_) / rad
        sy = (yy[y0:y1, x0:x1] - cy_) / (rad * 1.15)
        dd = 1 - sx * sx - sy * sy
        v = np.sqrt(np.clip(dd, 0, 1)) * rad
        hf[y0:y1, x0:x1] = np.maximum(hf[y0:y1, x0:x1], v)
    hf = np.asarray(Image.fromarray(hf, "F").resize((w, h), Image.BICUBIC), np.float32) * k
    return gblur(hf, 1.2)


def window(t, dur, dim=0.0):
    """Blue hour through a rainy window: the city out of focus, drops in focus, some running."""
    u = C.u
    x, y = _grid(C.w, C.h)
    top = np.array([0.20, 0.25, 0.32], np.float32)
    bot = np.array([0.05, 0.06, 0.08], np.float32)
    k = np.clip(y / C.h, 0, 1)[..., None]
    bg = top * (1 - k) + bot * k
    # bokeh: street and window lights, big soft discs
    r = _rng(21)
    lay = Image.new("F", (C.w, C.h), 0)
    dr = ImageDraw.Draw(lay)
    drift = wob(t, 5, (0.05, 0.13)) * 20 * u
    cols = []
    for i in range(46):
        bx = r.random() * C.w * 1.1 - 0.05 * C.w + drift
        by = C.h * (0.35 + 0.5 * r.random())
        rad = (18 + 50 * r.random() ** 2) * u
        v = 0.25 + 0.75 * r.random()
        dr.ellipse([bx - rad, by - rad, bx + rad, by + rad], fill=float(v))
        cols.append(r.random())
    bok = gblur(np.asarray(lay, np.float32), 3 * u)
    tint = np.array([0.85, 0.9, 1.0], np.float32)
    warm = np.array([1.0, 0.78, 0.55], np.float32)
    wmask = noise(41, 0.6, 0.3, 0.6) > 0.55
    bg = bg + bok[..., None] * np.where(wmask[..., None], warm, tint) * 0.55
    # a car passing below, a moving pair of discs
    cxp = C.w * (1.2 - (t / max(dur, 1e-3)) * 1.6)
    car = np.exp(-(((x - cxp) ** 2 + (y - C.h * 0.8) ** 2) / (45 * u) ** 2)) \
        + np.exp(-(((x - cxp - 120 * u) ** 2 + (y - C.h * 0.8) ** 2) / (45 * u) ** 2))
    bg = bg + car[..., None] * np.array([1.0, 0.95, 0.85], np.float32) * 0.5
    bgb = gblur(bg, 6 * u)
    # drops: refract a flipped, sharper piece of the city
    hf = _drops(C.w, C.h)
    gx = np.gradient(hf, axis=1)
    gy = np.gradient(hf, axis=0)
    wet = hf > 0.05
    ox = np.clip((x - gx * 26 * u).astype(np.int32), 0, C.w - 1)
    oy = np.clip((y - gy * 26 * u).astype(np.int32), 0, C.h - 1)
    ref = bg[oy, ox] * 1.2 + 0.02
    img = np.where(wet[..., None], ref, bgb)
    rim = np.clip(np.sqrt(gx * gx + gy * gy) - 1.2, 0, 1)
    img = img * (1 - 0.15 * rim[..., None])
    spec = np.clip(-gx * 0.6 - gy * 0.8 - 0.5, 0, 1) * wet
    img = img + spec[..., None] * 0.25
    # running drops: three, sliding and leaving a wet trail
    for i, (xr, sp, st) in enumerate(((0.28, 140, 0.2), (0.63, 210, 1.1), (0.81, 170, 2.0))):
        if t < st:
            continue
        cxr = xr * C.w + math.sin((t - st) * 3 + i) * 3 * u
        cyr = C.h * 0.1 + (t - st) * sp * u
        dd = ((x - cxr) / (7 * u)) ** 2 + ((y - cyr) / (9 * u)) ** 2
        blob = np.clip(1 - dd, 0, 1)
        trail = (np.abs(x - cxr) < 2.5 * u) & (y < cyr) & (y > C.h * 0.1)
        img = img * (1 - 0.3 * blob[..., None]) + blob[..., None] * 0.18
        img = np.where(trail[..., None], bg[np.clip(y, 0, C.h - 1).astype(np.int32), np.clip(x, 0, C.w - 1).astype(np.int32)] * 0.9, img)
    # condensation at the bottom of the pane
    cond = np.clip((y / C.h - 0.78) / 0.22, 0, 1) ** 1.5
    img = img * (1 - 0.35 * cond[..., None]) + cond[..., None] * np.array([0.16, 0.18, 0.21], np.float32)
    if dim:
        img = img * (1 - dim)
    return tonemap(img)


# ---------------------------------------------------------------- the night train
@lru_cache(maxsize=4)
def _forest(w, h, seed, n, hmin, hmax, dens=1.0):
    """A tileable band of spruce silhouettes (alpha), drawn 2x and reduced."""
    k = 2
    W, H = w * k, h * k
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    r = _rng(seed)
    base = H
    xs = np.sort(r.random(n)) * W
    for cx_ in xs:
        th = (hmin + (hmax - hmin) * r.random() ** 0.8) * H
        tw = th * (0.16 + 0.08 * r.random())
        for off in (-W, 0, W):
            x0 = cx_ + off
            if x0 < -tw or x0 > W + tw:
                continue
            pts_l, pts_r = [], []
            tiers = int(9 + 8 * r.random())
            for i in range(tiers + 1):
                f = i / tiers
                yy = base - th + f * th
                ww = tw * (0.08 + 0.92 * f ** 0.9) * (0.75 + 0.5 * r.random())
                droop = 0.03 * th * r.random()
                pts_l += [(x0 - ww, yy + droop), (x0 - ww * 0.35, yy + droop * 0.2 + th / tiers * 0.5)]
                pts_r += [(x0 + ww, yy + droop), (x0 + ww * 0.35, yy + droop * 0.2 + th / tiers * 0.5)]
            poly = [(x0, base - th - th * 0.03)] + pts_r + [(x0 + tw * 0.2, base), (x0 - tw * 0.2, base)] + pts_l[::-1]
            dr.polygon(poly, fill=255)
    im = im.resize((w, h), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def _band(t, speed, w_band, h_band, seed, n, hmin, hmax, blur):
    band = _forest(w_band, h_band, seed, n, hmin, hmax)
    off = int(round(speed * t)) % w_band
    reps = int(math.ceil((C.w + w_band) / w_band)) + 1
    wide = np.tile(band, (1, reps))
    cut = wide[:, off:off + C.w]
    if blur >= 1:
        cut = _box(cut, blur, 1)
    return cut


def train(t, dur, reflect=True):
    """From a sleeper compartment at night: forest bands at three speeds, catenary masts,
    a lamp now and then, the compartment faintly reflected, drops sliding back on the glass."""
    u = C.u
    x, y = _grid(C.w, C.h)
    hor = C.h * 0.56
    k = np.clip((y - C.h * 0.05) / (hor - C.h * 0.05), 0, 1)
    sky = np.array([0.015, 0.025, 0.045], np.float32) * (1 - k[..., None] ** 2) \
        + np.array([0.16, 0.19, 0.25], np.float32) * k[..., None] ** 2
    img = sky + (noise(51, 1.4, t * 0.004, 0.2) - 0.5)[..., None] * 0.03
    # snow on the ground below the trees: the first snow of October
    ground = y > hor
    img[ground] = np.array([0.13, 0.145, 0.17], np.float32) * (1 - 0.5 * ((y[ground] - hor) / (C.h - hor)))[:, None]
    shutter = 1 / 48
    layers = [  # speed px/s at 1080p, band height, seed, trees, blur, colour
        (60, 0.16, 61, 150, np.array([0.05, 0.065, 0.085], np.float32)),
        (520, 0.30, 62, 55, np.array([0.012, 0.016, 0.022], np.float32)),
        (2400, 0.80, 63, 9, np.array([0.004, 0.005, 0.007], np.float32)),
    ]
    for sp, hb, sd, n, col in layers:
        bh = int(C.h * hb)
        a = _band(t, sp * u, int(3000 * u), bh, sd, n, 0.35, 1.0, int(sp * u * shutter))
        top = int(hor + C.h * 0.05 - bh)
        full = np.zeros((C.h, C.w), np.float32)
        y0 = max(0, top)
        full[y0:top + bh] = a[y0 - top:]
        full[top + bh:] = 1.0 if 100 < sp < 1000 else 0.0
        img = img * (1 - full[..., None]) + col * full[..., None]
    # catenary masts every ~1.3 s, very fast, very blurred
    per = 1.3
    ph = (t % per) / per
    mx = C.w * (1.3 - ph * 2.2)
    mast = np.exp(-(((x - mx) / (70 * u)) ** 2)) * (y < C.h * 0.93)
    img = img * (1 - 0.9 * mast[..., None])
    # a farm lamp in the distance, slow; a trackside lamp, fast
    lx = (C.w * 1.2 - (t * 60 * u + 400 * u) % (C.w * 1.6))
    pts = [(lx, hor - 18 * u, 0.9)]
    fx = C.w * (1.4 - ((t + 0.7) % 2.9) / 2.9 * 2.6)
    img = img + glow(pts, core=1.0, halo=6, big=30, col=(1.0, 0.75, 0.45), gain=0.7)
    streak = np.exp(-(((y - hor + 60 * u) / (6 * u)) ** 2)) * np.exp(-(((x - fx) / (220 * u)) ** 2))
    img = img + streak[..., None] * np.array([1.0, 0.85, 0.65], np.float32) * 0.8
    if reflect:
        # the compartment's reading lamp, reflected in the glass
        ref = np.zeros((C.h, C.w), np.float32)
        lamp = np.exp(-(((x - C.w * 0.14) ** 2 + (y - C.h * 0.2) ** 2) / (60 * u) ** 2))
        ref += lamp * 0.9
        img = img + ref[..., None] * np.array([1.0, 0.78, 0.5], np.float32) * 0.22
    sill = y > C.h * 0.9
    img[sill] = np.array([0.02, 0.019, 0.018], np.float32)
    edge = np.abs(y - C.h * 0.9) < 2 * u
    img[edge] = img[edge] + np.array([0.09, 0.07, 0.05], np.float32) * np.clip(1 - x[edge] / C.w, 0, 1)[:, None]
    # the window frame at the left, a rubber seal catching the lamp
    fr = x < C.w * 0.055
    img[fr] = np.array([0.018, 0.018, 0.02], np.float32)
    seal = np.abs(x - C.w * 0.055) < 3 * u
    img[seal] = img[seal] + 0.05
    # drops pushed back by the speed
    p = particles(t, 120, 71, wind=(-0.9, 0.12), size=(1.0, 2.0), streak=3.0, bright=(0.1, 0.35), turb=0.0)
    img = screen(img, p, col=(0.7, 0.72, 0.75), amt=0.7)
    return tonemap(img)


def metro(t, dur):
    """The underground: tunnel lights raking past a dark window, cold fluorescent reflection."""
    u = C.u
    x, y = _grid(C.w, C.h)
    img = np.zeros((C.h, C.w, 3), np.float32) + np.array([0.02, 0.022, 0.026], np.float32)
    per = 0.19
    for j in range(8):
        ph = ((t + j * per) % (per * 8)) / (per * 8)
        lx = C.w * (1.5 - ph * 2.0)
        s = np.exp(-(((y - C.h * (0.34 + 0.02 * (j % 2))) / (8 * u)) ** 2)) * np.exp(-(((x - lx) / (260 * u)) ** 2))
        img = img + s[..., None] * np.array([0.95, 0.95, 0.85], np.float32) * 0.9
    cables = (np.abs(y - C.h * 0.6) < 2 * u) | (np.abs(y - C.h * 0.63) < 1.5 * u)
    img[cables] += 0.02
    # the carriage reflected: a strip light and seat backs
    strip = np.exp(-(((y - C.h * 0.1) / (10 * u)) ** 2)) * 0.25
    img = img + strip[..., None] * np.array([0.8, 0.9, 1.0], np.float32)
    seats = (y > C.h * 0.72) & (((x / (C.w / 5)) % 1) < 0.8)
    img[seats] = img[seats] * 0.4 + 0.03
    img = img * (1 + 0.06 * math.sin(t * 50))
    return tonemap(img)


# ---------------------------------------------------------------- Stockholm: lecture hall, laptop
def ceiling(t, dur):
    """A lecture hall at eight: rows of ceiling panels receding, cold, one tube flickering."""
    fov, pitch, yaw = 42.0, 0.42, 0.18
    cam = np.array([0.0, 1.25, t * 0.25], np.float32)
    d = _rays(C.w, C.h, fov, pitch, yaw)
    Hc = 4.2
    with np.errstate(divide="ignore", invalid="ignore"):
        tc = np.where(d[..., 1] > 1e-4, (Hc - cam[1]) / d[..., 1], 1e6)
    hx = cam[0] + d[..., 0] * tc
    hz = cam[2] + d[..., 2] * tc
    tile = 0.11 + 0.02 * ((np.floor(hx / 0.6) + np.floor(hz / 0.6)) % 2)
    seam = ((hx / 0.6) % 1 < 0.02) | ((hz / 0.6) % 1 < 0.02)
    tile = np.where(seam, 0.07, tile)
    px_, pz_ = (hx / 2.4) % 1, (hz / 3.0) % 1
    panel = (px_ > 0.38) & (px_ < 0.62) & (pz_ > 0.3) & (pz_ < 0.7)
    fl = (np.floor(hx / 2.4) == 1) & (np.floor(hz / 3.0) == 4)
    flick = 0.25 if (math.sin(t * 37) > 0.6 and t % 1.3 < 0.5) else 1.0
    val = np.where(panel, np.where(fl, 1.6 * flick, 1.6), tile)
    dist = np.minimum(tc, 200)
    fogk = np.exp(-dist / 60.0)
    val = val * fogk + 0.06 * (1 - fogk)
    img = val[..., None] * np.array([0.9, 0.95, 1.0], np.float32)
    img[tc > 1e5] = 0.04
    hot = np.clip(img - 0.9, 0, None)
    img = img + gblur(hot, 8 * C.u) * 1.2 + gblur(hot, 40 * C.u) * 0.8
    return tonemap(img)


@lru_cache(maxsize=2)
def _sheet(w, h):
    """A spreadsheet: tabular figures in a grid, one selected cell."""
    im = Image.new("RGB", (w, h), (236, 238, 240))
    d = ImageDraw.Draw(im)
    from kit import font
    f = font("sans", int(34 * C.u), 430)
    r = _rng(3)
    cw, ch = int(230 * C.u), int(62 * C.u)
    for i in range(0, h, ch):
        d.line([(0, i), (w, i)], fill=(205, 208, 212), width=max(1, int(2 * C.u)))
    for j in range(0, w, cw):
        d.line([(j, 0), (j, h)], fill=(205, 208, 212), width=max(1, int(2 * C.u)))
    for i in range(h // ch + 1):
        for j in range(w // cw + 1):
            v = r.normal(0, 1) * 10 ** r.integers(2, 5)
            s = f"{v:,.1f}".replace("-", "−")
            tw = d.textlength(s, font=f)
            d.text((j * cw + cw - tw - 14 * C.u, i * ch + 12 * C.u), s, font=f, fill=(40, 44, 50))
    d.rectangle([3 * cw, 7 * ch, 4 * cw, 8 * ch], outline=(30, 90, 60), width=int(5 * C.u))
    return im


def laptop(t, dur):
    """A laptop close up: the grid of a spreadsheet, shallow focus, cold light."""
    im = _sheet(int(C.w * 1.4), int(C.h * 1.5))
    a = shot(im, 0.52 + t * 0.004, 0.52, 1.0, rot=-0.05)
    x, y = _grid(C.w, C.h)
    focus = np.clip(np.abs(y / C.h - 0.55) * 2.2, 0, 1)[..., None]
    b = gblur(a, 9 * C.u)
    a = a * (1 - focus) + b * focus
    a = a * 0.8
    blink = 1.0 if (t % 1.0) < 0.55 else 0.0
    cxr = C.w * 0.5
    cur = (np.abs(x - cxr) < 1.6 * C.u) & (np.abs(y - C.h * 0.55) < 18 * C.u)
    a[cur] = a[cur] * (1 - blink) + 0.1 * blink
    return a


# ---------------------------------------------------------------- the map under a headlamp
@lru_cache(maxsize=2)
def _height(name):
    im = Image.open(SITE / f"assets/terrain/{name}.png").convert("RGB")
    a = np.asarray(im, np.float32)
    v = (a[..., 0] * 256 + a[..., 1]) / 65535
    d = json.load(open(SITE / "data/derived.json"))["terrain"][name]
    return v * (d["max"] - d["min"]) + d["min"], d


@lru_cache(maxsize=2)
def _topo(size):
    """The Abisko sheet: 20 m contours, index contours every 100 m, the lake, a grid, the route."""
    h, meta = _height("abisko")
    big = np.asarray(Image.fromarray(h.astype(np.float32), "F").resize((size, size), Image.BICUBIC), np.float32)
    big = gblur(big, size / 900)
    gy, gx = np.gradient(big)
    gm = np.sqrt(gx * gx + gy * gy) + 1e-3
    out = np.ones((size, size, 3), np.float32) * np.array([0.925, 0.915, 0.885], np.float32)
    # paper fibre
    r = _rng(9)
    fib = r.standard_normal((size // 2, size // 2)).astype(np.float32)
    fib = np.asarray(Image.fromarray(fib, "F").resize((size, size), Image.BICUBIC), np.float32)
    out += fib[..., None] * 0.012
    lake = big < meta["min"] + 4
    out[lake] = np.array([0.80, 0.85, 0.88], np.float32)
    for iv, lw, col in ((20, 1.1, 0.55), (100, 2.2, 0.38)):
        f = big / iv
        dpx = np.abs(f - np.round(f)) * iv / gm
        line = np.clip(1 - dpx / (lw * size / 2400), 0, 1) * (~lake)
        out = out * (1 - line[..., None] * (1 - np.array([col, col * 0.93, col * 0.85], np.float32)))
    # map grid every 2 km, thin cold blue
    km = meta["km"][0]
    step = size / km * 2
    xs = np.arange(size, dtype=np.float32)
    gl = (np.abs(((xs + step * 0.37) % step) - step / 2) > step / 2 - size / 1500)
    out[:, gl] = out[:, gl] * np.array([0.8, 0.88, 0.95], np.float32)
    out[gl, :] = out[gl, :] * np.array([0.8, 0.88, 0.95], np.float32)
    # a fold: one crease across, light one side, shadow the other
    yy = np.arange(size, dtype=np.float32)[:, None]
    cr = yy - size * 0.47
    out = out * (1 - 0.06 * np.exp(-((cr / (size * 0.004)) ** 2)))[..., None]
    out = out * (1 + 0.03 * np.tanh(cr / (size * 0.02)))[..., None]
    im = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
    # route and summit, with the site's rope colour
    uv = json.load(open(SITE / "data/derived.json"))["routes"]["004-abisko"]["uv"]
    pts = [(p[0] * size, p[1] * size) for p in uv]
    d = ImageDraw.Draw(im)
    d.line(pts, fill=(250, 248, 244), width=int(size / 260), joint="curve")
    d.line(pts, fill=tuple(int(c * 255) for c in ROPE), width=int(size / 520), joint="curve")
    return im, pts


def topo(t, dur, lamp=True, fx=0.40, fy=0.46, z=2.6, draw=True, rot=0.1):
    """The route on paper, very close, in a tent at night: only the headlamp's circle is lit."""
    size = 2400
    im, pts = _topo(size)
    hh = wob(t, 13, (0.23, 0.51)) * 0.004
    a = shot(im, fx + t * 0.004 + hh, fy + t * 0.002, z, rot=rot + wob(t, 14, (0.2,)) * 0.004)
    x, y = _grid(C.w, C.h)
    focus = np.clip(np.abs((y - C.h * 0.5) / C.h + (x - C.w * 0.5) / C.w * 0.25) * 2.4 - 0.15, 0, 1)[..., None]
    a = a * (1 - focus) + gblur(a, 7 * C.u) * focus
    if lamp:
        lx = C.w * (0.45 + 0.1 * math.sin(t * 0.7)) + wob(t, 15, (0.4, 0.9)) * 25 * C.u
        ly = C.h * (0.5 + 0.06 * math.cos(t * 0.5)) + wob(t, 16, (0.35, 0.8)) * 18 * C.u
        rr = ((x - lx) ** 2 + ((y - ly) * 1.15) ** 2) / (C.h * 0.42) ** 2
        pool = np.exp(-rr * 2.2) * 1.15 + 0.035
        a = a * pool[..., None] * np.array([1.0, 0.95, 0.86], np.float32)
    return tonemap(a)


# ---------------------------------------------------------------- headlamps in the dark
def headlamps(t, dur, src="winter-valley", n=5):
    """Before dawn: the valley under cloud, a moon behind it, a line of headlamps climbing."""
    fx, fy, z = 0.55, 0.52, 1.25
    a = shot(src, fx, fy, z)
    a = grade(a, ev=-1.5, sat=0.22, contrast=1.25, black=0.006)
    a = a * np.array([0.72, 0.88, 1.3], np.float32)
    lamps = []
    for i in range(n):
        k = t * 0.022 - i * 0.07 + 0.35
        X = C.w * (0.30 + 0.40 * k)
        Y = C.h * (0.475 - 0.05 * k)
        bob = abs(math.sin((t * 1.7 + i * 0.37) * math.pi)) * 1.5 * C.u
        hgt = 36 * C.u * (1 - 0.2 * k)
        a = put_figure(a, X, Y, hgt, (0.012, 0.014, 0.02), phase=t * 0.85 + i * 0.29, facing=1, alpha=0.95, pole=True)
        turn = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 0.9 + i * 1.7))
        lamps.append((X + 2 * C.u, Y - hgt * 0.93 - bob, turn))
    a = a + glow(lamps, core=1.3, halo=8, big=44, col=(0.9, 0.95, 1.0), gain=1.6, hf=0.3, bf=0.08)
    # pools of light on the snow ahead of each walker
    pool = np.zeros((C.h, C.w), np.float32)
    x, y = _grid(C.w, C.h)
    for X, Y, k in lamps:
        pool += k * np.exp(-(((x - X - 22 * C.u) / (26 * C.u)) ** 2 + ((y - Y - 6 * C.u) / (6 * C.u)) ** 2))
    a = a + pool[..., None] * np.array([0.16, 0.18, 0.21], np.float32)
    snow = particles(t, 700, 81, wind=(0.02, 0.05), size=(0.8, 2.4), bright=(0.08, 0.5))
    a = screen(a, snow, col=(0.6, 0.66, 0.75), amt=0.8)
    return tonemap(a)


def hut(t, dur, src="abisko-lapporten-winter"):
    """Shelter: a hut on the shore under the dark fells, two warm windows, smoke, snow falling;
    the last headlamp reaching the door."""
    fx, fy, z = 0.36, 0.63, 1.9
    a = shot(src, fx, fy, z)
    a = grade(a, ev=-2.0, sat=0.25, contrast=1.15, black=0.004)
    a = a * np.array([0.72, 0.88, 1.3], np.float32)
    X, Y, sc = src_to_frame(src, fx, fy, z, 0.33, 0.705)
    u = C.u * 0.62
    w_, h_ = 120 * u, 62 * u
    x, y = _grid(C.w, C.h)
    body = (x > X - w_ / 2) & (x < X + w_ / 2) & (y > Y - h_) & (y < Y)
    roof = (y < Y - h_) & (y > Y - h_ - 44 * u) & (np.abs(x - X) < (w_ / 2 + 10 * u) * (1 - (Y - h_ - y) / (44 * u)))
    snowroof = roof & (y < Y - h_ - 0.0) & (np.abs(x - X) > (w_ / 2 + 10 * u) * (1 - (Y - h_ - y) / (44 * u)) - 6 * u)
    a[body | roof] = np.array([0.012, 0.012, 0.016], np.float32)
    a[snowroof] = np.array([0.16, 0.18, 0.22], np.float32)
    wins = [((X - 30 * u), (Y - 36 * u)), ((X + 22 * u), (Y - 36 * u))]
    for wx, wy in wins:
        m = (np.abs(x - wx) < 9 * u) & (np.abs(y - wy) < 10 * u)
        a[m] = np.array([1.4, 0.9, 0.45], np.float32)
    a = a + glow([(wx, wy, 1.0) for wx, wy in wins], core=2.5, halo=10, big=55, col=(1.0, 0.62, 0.3), gain=0.55)
    spill = np.exp(-(((x - X) / (140 * u)) ** 2 + ((y - Y - 14 * u) / (14 * u)) ** 2))
    a = a + spill[..., None] * np.array([0.35, 0.22, 0.1], np.float32)
    # smoke from the chimney, lit faintly
    sm = noise(91, 0.25, t * 0.02, t * 0.05)
    col_ = np.exp(-(((x - X - 30 * u - (Y - h_ - 44 * u - y) * 0.6) / (18 * u + (Y - y) * 0.12)) ** 2))
    col_ = col_ * (y < Y - h_ - 30 * u) * np.clip((y - (Y - h_ - 300 * u)) / (200 * u), 0, 1)
    a = a + (col_ * sm * 0.12)[..., None] * np.array([0.6, 0.62, 0.66], np.float32)
    # a headlamp arriving from the lake
    k = clamp(t / 3.0)
    lxp = X + 330 * u * (1 - smooth(k)) + 60 * u
    lyp = Y + 6 * u
    a = put_figure(a, lxp, lyp, 30 * u, (0.01, 0.012, 0.018), phase=t * 0.8, facing=-1, alpha=1 - ramp(t, 3.0, 3.4))
    a = a + glow([(lxp - 2 * u, lyp - 28 * u, 1.0 - ramp(t, 3.0, 3.4))], core=0.9, halo=5, big=26,
                 col=(0.9, 0.95, 1.0), gain=1.0)
    a = gblur(a, 0.9 * C.u)
    snow = particles(t, 800, 83, wind=(0.03, 0.05), size=(0.8, 2.6), bright=(0.08, 0.55))
    a = screen(a, snow, col=(0.62, 0.68, 0.78), amt=0.8)
    return tonemap(a)


# ---------------------------------------------------------------- the altimeter
def altimeter(t, dur, frm=1088, to=1169):
    """The figure the day was for, as an instrument reads it."""
    a = shot("kebnekaise-moraine", 0.6, 0.72, 2.2)
    a = gblur(grade(a, ev=-2.3, sat=0.2), 14 * C.u)
    v = int(round(frm + (to - frm) * smooth(t / max(dur * 0.8, 1e-3))))
    s = f"+{v:,}"
    cx, cy = C.w / 2, C.h / 2 + 50 * C.u
    a = put_text(a, s, cx, cy, "sans", 150 * C.u, col=PAPER, align="center", wght=430)
    from kit import text_width
    a = put_text(a, "M", cx + text_width(s, "sans", 150 * C.u, wght=430) / 2 + 16 * C.u, cy, "sans", 40 * C.u,
                 col=PAPER, alpha=0.7, align="left", wght=480)
    a = put_text(a, "ALTITUDE", cx, cy - 170 * C.u, "sans", 20 * C.u, col=PAPER, alpha=0.7, align="center",
                 track=0.24, wght=520)
    return a
