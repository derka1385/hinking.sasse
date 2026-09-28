#!/usr/bin/env python3
"""HIKING CLUB — the brand film. Picture: the edit, the type and the renderer.

    python3 site/tools/film/film.py full|cut|loop [--sheet] [--from S --to S] [--jobs N]

full  the film, about 90 s, 16:9, with sound            -> assets/film/hiking-club-film.mp4
cut   the 30 s version for social and promotion         -> assets/film/hiking-club-film-30s.mp4
loop  12 s, silent, seamless, for the website           -> assets/film/hiking-club-loop.mp4 (+ .webm)

--sheet renders one frame per shot into a contact sheet instead of the film. Sound comes from
sound.py, which reads the same timelines, so picture and sound cannot drift apart.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenes as sc  # noqa: E402
from kit import (C, FOG, INK, PAPER, clamp, ease, fog, gblur, grade, grain, hand, logo,  # noqa: E402
                 particles, put_figure, put_hiker, put_mask, put_text, ramp, screen, shot, smooth, solid,
                 src_to_frame, to_pil, vignette, noise)

OUT = Path(__file__).resolve().parents[2] / "assets/film"


# ---------------------------------------------------------------- shots over stills
def still(src, f0, f1=None, z=(1.0, 1.0), ev=0.0, sat=0.62, contrast=1.08, black=0.012, cool=1.0,
          fogp=None, snow=None, rain=None, drift=None, water=None, handheld=0.0, figs=(), hikers=(), soft=0.0,
          curve="ease", night=False, seed=1, vert=None):
    """A camera move over a photograph: from framing f0 to f1 (image fractions) and zoom z0 -> z1,
    graded, with weather and people composited into the image's own space. `vert` overrides the
    framing (f0, f1, z) when the frame is portrait."""
    f1 = f1 or f0
    land = (f0, f1, z)

    def render(t, dur):
        f0, f1, z = (vert.get("f0", land[0]), vert.get("f1", vert.get("f0", land[1])), vert.get("z", land[2])) \
            if (vert and C.h > C.w) else land
        k = t / dur if dur else 0
        k = ease(k) if curve == "ease" else clamp(k) if curve == "linear" else smooth(k)
        fx = f0[0] + (f1[0] - f0[0]) * k
        fy = f0[1] + (f1[1] - f0[1]) * k
        zz = z[0] + (z[1] - z[0]) * k
        hh = hand(t, seed, handheld) if handheld else {}
        a = shot(src, fx, fy, zz, **hh)
        for f in figs:
            a = _figure(a, src, fx, fy, zz, t, hh, f)
        for f in hikers:
            X, Y, sc_ = src_to_frame(src, fx, fy, zz, f["x"], f["y"])
            a = put_hiker(a, X + hh.get("dx", 0), Y + hh.get("dy", 0), f["h"] * sc_, f.get("v", 0), f.get("mirror", False),
                          haze=f.get("haze", 0.0), haze_col=f.get("haze_col", FOG), soft=f.get("soft", 0.0))
        if soft:
            a = gblur(a, soft * C.u)
        if water:
            a = _water(a, t, water)
        a = grade(a, ev=ev, sat=sat, contrast=contrast, black=black, cool=cool)
        if night:
            a = a * np.array([0.72, 0.88, 1.3], np.float32)
        if fogp:
            a = fog(a, t, **fogp)
        if drift:  # spindrift: fast, low, streaked, hugging the snow
            p = particles(t, drift.get("n", 900), seed + 40, wind=drift.get("wind", (0.35, 0.02)),
                          size=(0.8, 2.2), streak=2.5, bright=(0.1, 0.55), turb=0.02)
            y = np.linspace(0, 1, C.h, dtype=np.float32)
            reg = np.clip((y - drift.get("y", 0.55)) / 0.2, 0, 1)[:, None]
            a = screen(a, p * reg, col=(0.93, 0.95, 0.98), amt=drift.get("amt", 0.9))
        if snow:
            p = particles(t, snow.get("n", 700), seed + 50, wind=snow.get("wind", (0.03, 0.07)),
                          size=snow.get("size", (0.9, 3.0)), bright=snow.get("bright", (0.12, 0.8)))
            a = screen(a, p, col=snow.get("col", (0.9, 0.92, 0.95)), amt=snow.get("amt", 0.85))
        if rain:
            p = particles(t, rain.get("n", 500), seed + 60, wind=rain.get("wind", (0.08, 2.4)),
                          size=(0.6, 1.2), streak=2.4, bright=(0.1, 0.7), turb=0.0)
            a = screen(a, p, col=(0.8, 0.84, 0.88), amt=rain.get("amt", 0.6))
        return a
    return render


def _figure(a, src, fx, fy, zz, t, hh, f):
    """f: dict(x, y in image fractions at t=0; vx, vy per second; h in image pixels; ...)."""
    if not (f.get("t0", -1e9) <= t <= f.get("t1", 1e9)):
        return a
    px = f["x"] + f.get("vx", 0) * t
    py = f["y"] + f.get("vy", 0) * t
    X, Y, s = src_to_frame(src, fx, fy, zz, px, py)
    X += hh.get("dx", 0)
    Y += hh.get("dy", 0)
    alpha = f.get("alpha", 1.0) * ramp(t, f.get("in0", -1), f.get("in1", -1 + 1e-6))
    return put_figure(a, X, Y, f["h"] * s, f.get("col", (0.05, 0.055, 0.065)), phase=t * f.get("cad", 0.9) + f.get("ph", 0),
                      walk=f.get("walk", 1.0), facing=f.get("facing", 1), alpha=alpha, pack=f.get("pack", True),
                      pole=f.get("pole", False), haze=f.get("haze", 0.0), haze_col=f.get("haze_col", FOG),
                      shadow=f.get("shadow", 0.0))


def _water(a, t, w):
    """Running water: bright water catches a light that moves downstream."""
    x0, y0, x1, y1 = [int(v * s) for v, s in zip(w["box"], (C.w, C.h, C.w, C.h))]
    reg = a[y0:y1, x0:x1]
    lum = reg[..., 1]
    m = np.clip((lum - w.get("th", 0.45)) / 0.25, 0, 1)
    n = noise(97, 0.05, t * w.get("vx", 0.0), -t * w.get("vy", 0.6))[y0:y1, x0:x1]
    n2 = noise(98, 0.02, t * w.get("vx", 0.0) * 1.7 + 0.3, -t * w.get("vy", 0.6) * 1.6)[y0:y1, x0:x1]
    sh = (n * 0.6 + n2 * 0.4 - 0.5) * 1.1
    a[y0:y1, x0:x1] = reg * (1 + (sh * m)[..., None] * 0.6)
    return a


def footage(path, fx=0.5, fy=0.5, z=(1.0, 1.0), start=0.0, **gk):
    """A real clip in place of a drawn one: frames are read with ffmpeg at the clip's own time,
    framed like a still (so it crops to any format) and graded with the rest of the film."""
    def render(t, dur):
        ff = shutil.which("ffmpeg") or "ffmpeg"
        raw = subprocess.run([ff, "-v", "error", "-ss", f"{start + t:.3f}", "-i", str(path), "-frames:v", "1",
                              "-f", "image2pipe", "-vcodec", "png", "-"], check=True, capture_output=True).stdout
        import io
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        k = ease(t / dur) if dur else 0
        a = shot(im, fx, fy, z[0] + (z[1] - z[0]) * k)
        return grade(a, **gk)
    return render


def black(t, dur):
    return solid((0.0, 0.0, 0.0))


def paper(t, dur):
    return solid(PAPER)


# ---------------------------------------------------------------- the film's timelines
@dataclass
class Clip:
    fn: object
    dur: float
    name: str = ""
    xin: float = 0.0       # dissolve from the previous clip
    fin: float = 0.0       # fade up from black
    fout: float = 0.0      # fade down to black
    offset: float = 0.0    # start the shot's own clock later (reuse a shot, another moment)
    raw: bool = False      # no grain or vignette (the white card)


@dataclass
class Timeline:
    name: str
    clips: list
    vo: list = field(default_factory=list)       # (t0, t1, text, dict)
    labels: list = field(default_factory=list)   # (t0, t1, dict(tl=, tr=, bl=, br=), dict)
    sfx: list = field(default_factory=list)      # (t, name, dict) — read by sound.py
    music: list = field(default_factory=list)    # (t, level) breakpoints — read by sound.py
    card: float = None                           # start of the white end card
    card_lines: tuple = ("logo", "outward", "join")
    loop: bool = False

    @property
    def dur(self):
        return sum(c.dur for c in self.clips)

    def starts(self):
        s, out = 0.0, []
        for c in self.clips:
            out.append(s)
            s += c.dur
        return out


# The stills, framed once and reused by the three timelines.
S = dict(
    fog_open=still("summit-cloud", (0.52, 0.5), (0.54, 0.52), z=(1.0, 1.07), ev=-0.55, sat=0.45,
                   fogp=dict(dens=0.9, scale=1.5, vx=0.016, lo=0.28, hi=0.85, veil=0.18, col=(0.62, 0.66, 0.71))),
    forest=still("tyresta-pines", (0.5, 0.45), (0.53, 0.45), z=(1.05, 1.1), ev=-0.9, sat=0.35, contrast=1.1,
                 fogp=dict(dens=0.65, scale=1.2, vx=0.01, lo=0.3, hi=0.9, veil=0.22, col=(0.55, 0.6, 0.63))),
    lapporten_dawn=still("abisko-lapporten-winter", (0.46, 0.5), (0.54, 0.5), z=(1.12, 1.12), ev=-0.3, sat=0.5,
                         fogp=dict(dens=0.25, scale=2.2, vx=0.006, lo=0.45, hi=0.9, col=(0.72, 0.74, 0.8),
                                   prof=lambda y: math.exp(-((y - 0.6) / 0.08) ** 2)),
                         snow=dict(n=260, wind=(0.02, 0.03), size=(0.7, 1.8), bright=(0.05, 0.4), amt=0.6)),
    whiteout=still("whiteout-tree", (0.42, 0.62), (0.46, 0.63), z=(1.08, 1.14), ev=-0.12, sat=0.4, contrast=1.1,
                   fogp=dict(dens=0.45, scale=1.4, vx=0.02, lo=0.35, hi=0.85, col=(0.9, 0.91, 0.92)),
                   snow=dict(n=600, wind=(0.06, 0.05), size=(0.8, 2.4), bright=(0.0, 0.25), col=(0.6, 0.62, 0.66), amt=0.5),
                   vert=dict(f0=(0.47, 0.62), f1=(0.49, 0.63), z=(1.0, 1.04)),
                   figs=[dict(x=0.66, y=0.852, vx=-0.0065, h=34, col=(0.2, 0.21, 0.23), haze=0.42, haze_col=(0.88, 0.89, 0.9),
                              facing=-1, cad=0.85)]),
    valley=still("winter-valley", (0.6, 0.47), (0.64, 0.46), z=(1.1, 1.16), ev=-0.2, sat=0.45, contrast=1.12,
                 drift=dict(n=1100, wind=(0.4, 0.015), y=0.5, amt=0.8)),
    further=still("expedition-tracks", (0.41, 0.9), (0.5, 0.56), z=(1.9, 1.0), ev=-0.1, sat=0.5, curve="smooth",
                  drift=dict(n=500, wind=(-0.25, 0.01), y=0.6, amt=0.5)),
    higher=still("climbing-wall", (0.5, 0.6), (0.5, 0.29), z=(1.05, 1.1), ev=-0.2, sat=0.5, contrast=1.12, curve="smooth"),
    together=still("kebnekaise-ridge", (0.5, 0.62), (0.52, 0.6), z=(1.12, 1.02), ev=-0.2, sat=0.45, contrast=1.1,
                   drift=dict(n=700, wind=(0.3, -0.02), y=0.35, amt=0.55)),
    wide_group=still("kebnekaise-moraine", (0.5, 0.42), (0.52, 0.42), z=(1.0, 1.03), ev=-0.35, sat=0.42, contrast=1.1,
                     vert=dict(f0=(0.41, 0.42), f1=(0.43, 0.42)),
                     figs=[dict(x=0.335 - i * 0.0085, y=0.412 + (i % 2) * 0.0012, vx=0.0042, h=11.5, col=(0.07, 0.075, 0.09),
                                ph=i * 0.37, cad=0.9, haze=0.1, pole=True) for i in range(6)]),
    moon=still("abisko-moon-ridge", (0.66, 0.62), (0.68, 0.64), z=(1.35, 1.45), ev=-0.45, sat=0.4, contrast=1.1),
    rope=still("alpine-crevasse", (0.66, 0.32), (0.6, 0.42), z=(1.5, 1.3), ev=-0.25, sat=0.45, contrast=1.1, handheld=0.6,
               snow=dict(n=300, wind=(0.1, 0.06), size=(0.8, 2.2), bright=(0.0, 0.3), col=(0.6, 0.62, 0.66), amt=0.4)),
    mountain=still("kebnekaise-moraine", (0.58, 0.2), (0.58, 0.22), z=(1.9, 1.95), ev=-0.3, sat=0.4, contrast=1.12),
    final=still("abisko-lapporten-figure", (0.2, 0.79), (0.5, 0.6), z=(1.9, 1.0), ev=-0.1, sat=0.52, contrast=1.08,
                curve="smooth", vert=dict(f0=(0.2, 0.8), f1=(0.55, 0.72), z=(1.3, 1.0)),
                # the others, further along the edge: the same real hiker, smaller, recoloured, mirrored
                hikers=[dict(x=0.486, y=0.900, h=106, v=1, mirror=True, haze=0.06, haze_col=(0.62, 0.64, 0.68)),
                        dict(x=0.509, y=0.8995, h=101, v=2, haze=0.07, haze_col=(0.62, 0.64, 0.68)),
                        dict(x=0.583, y=0.8955, h=90, v=4, mirror=True, haze=0.1, haze_col=(0.62, 0.64, 0.68)),
                        dict(x=0.672, y=0.892, h=78, v=3, haze=0.13, haze_col=(0.62, 0.64, 0.68))]),
    final_far=still("abisko-lapporten-winter", (0.5, 0.52), (0.5, 0.52), z=(1.06, 1.0), ev=-0.1, sat=0.45,
                    figs=[dict(x=0.5 + i * 0.0042, y=0.772 + (i % 2) * 0.001, h=5.2, walk=0.0, col=(0.1, 0.11, 0.13), haze=0.1)
                          for i in range(5)]),
    # the montage: close, handheld, short
    m_rope=still("alpine-crevasse", (0.9, 0.4), (0.93, 0.43), z=(3.0, 3.2), ev=-0.3, sat=0.4, handheld=1.8, seed=3),
    m_granite=still("archipelago-granite", (0.55, 0.7), (0.58, 0.72), z=(2.2, 2.35), ev=-0.9, sat=0.25, contrast=1.3,
                    handheld=1.6, seed=4, rain=dict(n=700, amt=0.7)),
    m_snow=still("expedition-tracks", (0.42, 0.93), (0.44, 0.9), z=(2.5, 2.7), ev=0.0, sat=0.4, handheld=2.2, seed=5,
                 drift=dict(n=900, wind=(0.9, 0.05), y=0.0, amt=0.9)),
    m_ice=still("ice-fall", (0.65, 0.66), (0.66, 0.62), z=(2.2, 2.4), ev=-0.3, sat=0.4, handheld=1.6, seed=6),
    m_ridge=still("kebnekaise-ridge", (0.82, 0.32), (0.8, 0.33), z=(2.0, 2.1), ev=-0.3, sat=0.35, handheld=1.4, seed=7,
                  drift=dict(n=1600, wind=(1.1, -0.08), y=0.0, amt=1.0)),
    m_water=still("tyresta-stream", (0.78, 0.82), (0.76, 0.86), z=(2.0, 2.15), ev=-0.5, sat=0.3, handheld=1.2, seed=8,
                  water=dict(box=(0, 0, 1, 1), vy=0.9, vx=-0.3, th=0.4)),
    m_rock=still("kebnekaise-moraine", (0.4, 0.8), (0.42, 0.78), z=(2.1, 2.3), ev=-0.4, sat=0.3, contrast=1.2, handheld=1.8, seed=9),
    m_climb=still("climbing-wall", (0.53, 0.5), (0.53, 0.47), z=(2.3, 2.45), ev=-0.3, sat=0.4, handheld=1.5, seed=10),
    m_fog=still("summit-cloud", (0.45, 0.35), (0.5, 0.35), z=(1.6, 1.7), ev=-0.5, sat=0.35, seed=11,
                fogp=dict(dens=0.8, scale=0.8, vx=0.08, lo=0.3, hi=0.8, col=(0.7, 0.73, 0.78))),
    m_belay=still("ice-fall", (0.64, 0.1), (0.64, 0.14), z=(2.4, 2.5), ev=-0.3, sat=0.45, handheld=1.8, seed=12),
    m_forest=still("tyresta-pines", (0.4, 0.4), (0.44, 0.4), z=(2.0, 2.1), ev=-1.0, sat=0.3, handheld=1.2, seed=13,
                   fogp=dict(dens=0.5, scale=1.0, vx=0.03, lo=0.3, hi=0.9, veil=0.15, col=(0.5, 0.55, 0.58))),
    m_stream=still("tyresta-stream", (0.62, 0.72), (0.6, 0.75), z=(1.25, 1.3), ev=-0.55, sat=0.3, seed=14,
                   water=dict(box=(0, 0, 1, 1), vy=0.7, vx=-0.25, th=0.42)),
)

P = dict(
    street=sc.street, doors=sc.doors, window=sc.window, train=sc.train, topo=sc.topo, headlamps=sc.headlamps,
    hut=sc.hut, metro=sc.metro, ceiling=sc.ceiling, laptop=sc.laptop, altimeter=sc.altimeter,
    window_out=lambda t, d: sc.window(t, d, dim=ramp(t, d - 1.6, d - 0.5) * 0.92),
    topo_day=lambda t, d: sc.topo(t, d, lamp=False, fx=0.47, fy=0.5, z=1.7, rot=0.03),
    topo_close=lambda t, d: sc.topo(t, d, lamp=True, fx=0.36, fy=0.42, z=3.6, rot=0.2),
)


def full():
    c = [
        Clip(black, 2.4, "black"),
        Clip(S["fog_open"], 6.2, "fog", fin=4.4),
        Clip(P["street"], 3.0, "streets"),
        Clip(P["doors"], 2.8, "doors"),
        Clip(P["window_out"], 4.4, "window"),
        Clip(P["train"], 3.0, "train"),
        Clip(P["topo"], 2.6, "map"),
        Clip(P["headlamps"], 2.8, "headlamps"),
        Clip(S["lapporten_dawn"], 3.2, "abisko", xin=0.8),
        Clip(S["whiteout"], 3.4, "whiteout"),
        Clip(S["valley"], 3.2, "valley"),
        Clip(S["further"], 3.2, "further"),
        Clip(S["higher"], 2.2, "higher"),
        Clip(S["together"], 3.4, "together"),
        # montage: the body
        Clip(S["m_rope"], 0.85, "m-rope"),
        Clip(S["m_granite"], 0.7, "m-granite"),
        Clip(S["m_snow"], 0.6, "m-snow"),
        Clip(S["m_ice"], 0.6, "m-ice"),
        Clip(S["m_ridge"], 0.6, "m-ridge"),
        Clip(P["topo_close"], 0.5, "m-map"),
        Clip(P["altimeter"], 0.6, "m-alt"),
        Clip(S["m_water"], 0.45, "m-water"),
        Clip(S["m_forest"], 0.45, "m-forest"),
        Clip(S["m_rock"], 0.42, "m-rock"),
        Clip(S["m_climb"], 0.42, "m-climb"),
        Clip(S["m_fog"], 0.4, "m-fog"),
        Clip(S["m_belay"], 0.38, "m-belay"),
        Clip(black, 0.18, "m-black"),
        Clip(S["wide_group"], 4.0, "wide"),
        # the voice returns
        Clip(S["moon"], 3.0, "cold"),
        Clip(P["train"], 2.8, "distance", offset=7.0),
        Clip(P["hut"], 3.4, "legs"),
        Clip(S["rope"], 3.5, "who"),
        # the two lives, intercut
        Clip(P["ceiling"], 0.75, "i-hall"),
        Clip(S["mountain"], 0.75, "i-mountain"),
        Clip(P["laptop"], 0.75, "i-laptop"),
        Clip(P["topo_day"], 0.75, "i-map"),
        Clip(P["metro"], 0.7, "i-metro"),
        Clip(P["train"], 0.9, "i-train", offset=3.0),
        # the ending
        Clip(S["final"], 7.4, "meet", xin=0.0),
        Clip(S["final_far"], 2.2, "far", xin=1.2),
        Clip(paper, 6.6, "card", raw=True),
    ]
    tl = Timeline("full", c)
    st = dict(zip([x.name for x in c], tl.starts()))
    T = lambda n, d=0.0: st[n] + d
    tl.vo = [
        (T("fog", 3.3), T("fog", 6.05), "Most days begin the same way.", {}),
        (T("streets", 0.5), T("streets", 2.8), "The same streets.", {}),
        (T("doors", 0.4), T("doors", 2.6), "The same doors.", {}),
        (T("window", 0.4), T("window", 2.9), "The same distance between where you are…", {}),
        (T("window", 3.0), T("window", 4.35), "…and somewhere else.", {}),
        (T("whiteout", 0.45), T("whiteout", 3.25), "Some places don’t ask who you are.", {"dark": True}),
        (T("valley", 0.4), T("valley", 3.0), "Only whether you keep moving.", {}),
        (T("further", 1.2), T("further", 3.1), "Further.", {}),
        (T("higher", 0.3), T("higher", 2.1), "Higher.", {"y": 0.2}),
        (T("together", 0.5), T("together", 2.9), "Together.", {"dark": True}),
        (T("cold", 0.4), T("cold", 2.9), "You will forget the cold.", {}),
        (T("distance", 0.3), T("distance", 2.7), "You will forget the distance.", {}),
        (T("legs", 0.3), T("legs", 3.4), "You will probably forget how much your legs hurt.", {}),
        (T("who", 0.45), T("who", 3.4), "But you won’t forget who was there.", {}),
        (T("meet", 1.3), T("meet", 3.9), "Stockholm is where we meet.", {"y": 0.3}),
        (T("meet", 4.5), T("meet", 7.25), "Not where we stop.", {"y": 0.3}),
    ]
    tl.labels = [
        (T("streets", 0.3), T("streets", 2.9), dict(bl="Stockholm · 07:42", br="59.3417° N  18.0572° E"), {}),
        (T("doors", 0.3), T("doors", 2.7), dict(bl="Sveavägen 65"), {}),
        (T("train", 0.25), T("train", 2.9), dict(tl="Exp. 004", bl="Stockholm C → Abisko", br="1,002 km · night train"), {}),
        (T("map", 0.2), T("map", 2.5), dict(tl="Exp. 004", tr="17—19 Oct", bl="68.3495° N  18.8312° E"), {"type": "bl"}),
        (T("headlamps", 0.3), T("headlamps", 2.7), dict(bl="05:40", br="−6 °C"), {}),
        (T("abisko", 0.6), T("abisko", 3.1), dict(tl="Exp. 004", bl="Abisko", br="68.3495° N  18.8312° E"), {}),
        (T("together", 0.4), T("together", 3.3), dict(tl="Exp. 002", bl="Kebnekaise", br="+2,097 m"), {"dark": True}),
        (T("wide", 1.1), T("wide", 3.9), dict(bl="Fig. 04 — Six people, 1.8 m"), {}),
        (T("legs", 0.3), T("legs", 3.4), dict(br="Abiskojaure · 21:10"), {}),
        (T("i-hall", 0.0), T("i-hall", 0.75), dict(bl="SSE · 08:15"), {}),
        (T("i-mountain", 0.0), T("i-mountain", 0.75), dict(bl="+2,097 m"), {}),
        (T("meet", 0.8), T("meet", 7.3), dict(tl="Exp. 004", tr="17—19 Oct", bl="Abisko", br="+1,169 m"), {"slow": True}),
    ]
    tl.card = T("card")
    tl.notes = [(T("who", 0.5), 62, 0.5), (T("who", 2.3), 57, 0.4), (T("meet", 0.6), 65, 0.45),
                (T("meet", 3.0), 64, 0.4), (T("meet", 5.2), 62, 0.45), (T("far", 0.6), 57, 0.35)]
    tl.sfx = _sfx_full(T)
    # the arc of the sound, in dB on everything but the score
    tl.ambience = [(0, -26), (T("fog", 2.0), -10, 6.0), (T("streets"), -13), (T("train"), -4), (T("map"), -8),
                   (T("abisko"), -8), (T("whiteout"), -8), (T("together"), -7), (T("m-rope"), 0), (T("m-belay"), 1),
                   (T("wide"), -20, 0.05), (T("cold"), -9, 1.0), (T("legs"), -8), (T("i-hall"), -6), (T("meet"), -10),
                   (T("card"), -10)]
    tl.silence = [(T("wide"), T("cold"))]
    tl.music = [
        (0, 0.0), (T("train"), 0.0), (T("map"), 0.12), (T("abisko"), 0.35), (T("whiteout"), 0.4),
        (T("together"), 0.55), (T("together", 3.0), 0.2), (T("m-rope"), 0.55), (T("m-belay"), 1.0),
        (T("wide"), 0.0), (T("cold"), 0.15), (T("legs"), 0.25), (T("who"), 0.4), (T("i-hall"), 0.55),
        (T("meet"), 0.3), (T("far"), 0.25), (T("card"), 0.0),
    ]
    tl.marks = st
    return tl


def _sfx_full(T):
    """Sound events, placed on the picture. Names are sound.py's instruments."""
    e = []
    add = lambda _t, _n, **k: e.append((_t, _n, k))
    # the dark, before anything is seen
    add(0.2, "wind_bed", level=0.4, until=T("streets"), fin=5.5)
    add(1.15, "boot", pan=-0.2, level=0.7)
    add(1.9, "breath", kind="in", level=0.55)
    add(2.35, "boot", pan=-0.15, level=0.65)
    add(2.8, "breath", kind="out", level=0.6)
    add(3.1, "fabric", level=0.6)
    add(3.6, "boot", pan=-0.1, level=0.55)
    add(4.4, "carabiner", pan=0.3, level=0.75)
    add(5.2, "breath", kind="in", level=0.4)
    add(6.3, "ice", level=0.55, pan=-0.5)
    add(7.8, "breath", kind="out", level=0.35)
    # Stockholm
    add(T("streets"), "city", until=T("train"), level=0.5)
    add(T("streets", 0.8), "steps_city", n=6, rate=1.9, level=0.35, pan=0.2)
    add(T("doors", 0.2), "steps_city", n=5, rate=2.0, level=0.45, pan=-0.2)
    add(T("doors", 1.9), "door", level=0.6)
    add(T("window"), "rain_glass", until=T("train"), level=0.55)
    # the world opens: the train comes in hard
    add(T("train"), "train", until=T("map"), level=0.55, slam=True)
    add(T("map"), "paper", level=0.7)
    add(T("map", 0.15), "click", level=0.6)
    add(T("map"), "tent", until=T("headlamps"), level=0.5)
    add(T("headlamps"), "wind_bed", level=0.45, until=T("abisko", 0.8))
    for i in range(6):
        add(T("headlamps", 0.25 + i * 0.45), "snowstep", level=0.5, pan=-0.3 + i * 0.1)
    add(T("headlamps", 1.2), "carabiner", level=0.35, pan=0.4)
    add(T("abisko"), "wind_bed", level=0.4, until=T("whiteout"))
    add(T("abisko", 1.4), "ice", level=0.4, pan=0.5)
    add(T("abisko", 2.4), "bird", level=0.3, pan=-0.6)
    add(T("whiteout"), "wind_bed", level=0.55, until=T("valley"), bright=True)
    add(T("valley"), "wind_bed", level=0.6, until=T("further"), gust=True)
    for i in range(7):
        add(T("valley", 0.3 + i * 0.44), "snowstep", level=0.35, pan=0.2)
    add(T("further"), "wind_bed", level=0.45, until=T("higher"))
    for i in range(6):
        add(T("further", 0.1 + i * 0.5), "snowstep", level=0.7 - i * 0.07, pan=-0.1)
        add(T("further", 0.35 + i * 1.0), "breath", kind="out" if i % 2 else "in", level=0.55)
    add(T("higher"), "wind_bed", level=0.35, until=T("together"))
    add(T("higher", 0.2), "rock", level=0.6)
    add(T("higher", 0.9), "carabiner", level=0.6, pan=0.2)
    add(T("higher", 1.4), "breath", kind="out", level=0.6)
    add(T("together"), "wind_bed", level=0.5, until=T("m-rope"))
    # the montage, one sound per cut
    for n, snd in (("m-rope", "rope"), ("m-granite", "rain_hit"), ("m-snow", "snowstep"), ("m-ice", "axe"),
                   ("m-ridge", "gust"), ("m-map", "paper"), ("m-alt", "beep"), ("m-water", "water_hit"),
                   ("m-forest", "gust"), ("m-rock", "rock"), ("m-climb", "breath"), ("m-fog", "gust"),
                   ("m-belay", "carabiner")):
        add(T(n), snd, level=1.0)
    add(T("m-rope"), "breath_run", until=T("wide"), level=0.6)
    # silence, then the wide
    add(T("wide", 0.2), "wind_bed", level=0.5, until=T("cold"), still=True, fin=2.0)
    add(T("wide", 2.2), "bird", level=0.18, pan=0.4)
    add(T("cold"), "wind_bed", level=0.4, until=T("distance"))
    add(T("distance"), "train", until=T("legs"), level=0.45)
    add(T("legs"), "wind_bed", level=0.35, until=T("legs", 2.2))
    add(T("legs", 1.9), "door", level=0.45)
    add(T("legs", 2.2), "hut", until=T("who"), level=0.5)
    add(T("legs", 2.9), "mug", level=0.5)
    add(T("who"), "wind_bed", level=0.35, until=T("i-hall"))
    add(T("who", 0.8), "rope", level=0.35)
    # intercut: indoor hum against the outside
    add(T("i-hall"), "hum", until=T("i-mountain"), level=0.5)
    add(T("i-mountain"), "gust", level=0.7)
    add(T("i-laptop"), "keys", until=T("i-map"), level=0.5)
    add(T("i-map"), "paper", level=0.6)
    add(T("i-metro"), "metro", until=T("i-train"), level=0.6)
    add(T("i-train"), "train", until=T("meet"), level=0.6)
    add(T("meet"), "wind_bed", level=0.3, until=T("card"), still=True)
    add(T("meet", 2.2), "bird", level=0.14, pan=-0.3)
    add(T("far", 1.0), "ice", level=0.2, pan=0.6)
    return e


def cut():
    """The 30 s version: the manifesto, the body, the ending."""
    c = [
        Clip(black, 0.9, "black"),
        Clip(S["fog_open"], 3.0, "fog", fin=2.0, offset=2.5),
        Clip(S["whiteout"], 3.0, "whiteout", offset=0.4),
        Clip(S["valley"], 2.7, "valley"),
        Clip(S["further"], 2.0, "further", offset=1.4),
        Clip(S["higher"], 1.6, "higher", offset=0.4),
        Clip(S["together"], 2.3, "together"),
        Clip(S["m_rope"], 0.55, "m-rope"),
        Clip(S["m_snow"], 0.45, "m-snow"),
        Clip(S["m_ice"], 0.45, "m-ice"),
        Clip(S["m_ridge"], 0.45, "m-ridge"),
        Clip(P["altimeter"], 0.5, "m-alt", offset=0.3),
        Clip(S["m_climb"], 0.4, "m-climb"),
        Clip(S["m_belay"], 0.35, "m-belay"),
        Clip(black, 0.15, "m-black"),
        Clip(S["wide_group"], 2.6, "wide", offset=1.0),
        Clip(S["final"], 5.2, "meet", offset=1.6),
        Clip(paper, 4.0, "card", raw=True),
    ]
    tl = Timeline("cut", c)
    st = dict(zip([x.name for x in c], tl.starts()))
    T = lambda n, d=0.0: st[n] + d
    tl.vo = [
        (T("whiteout", 0.3), T("whiteout", 2.9), "Some places don’t ask who you are.", {"dark": True}),
        (T("valley", 0.2), T("valley", 2.6), "Only whether you keep moving.", {}),
        (T("further", 0.2), T("further", 1.9), "Further.", {}),
        (T("higher", 0.15), T("higher", 1.55), "Higher.", {"y": 0.2}),
        (T("together", 0.2), T("together", 2.2), "Together.", {"dark": True}),
        (T("meet", 0.3), T("meet", 2.5), "Stockholm is where we meet.", {"y": 0.3}),
        (T("meet", 2.8), T("meet", 5.1), "Not where we stop.", {"y": 0.3}),
    ]
    tl.labels = [
        (T("fog", 0.8), T("fog", 2.9), dict(tl="Exp. 004", bl="Abisko", br="17—19 Oct"), {}),
        (T("wide", 0.4), T("wide", 2.5), dict(bl="Fig. 04 — Six people, 1.8 m"), {}),
    ]
    tl.card = T("card")
    tl.card_lines = ("logo_join",)
    tl.notes = [(T("meet", 0.3), 62, 0.45), (T("meet", 2.7), 57, 0.4)]
    e = []
    add = lambda _t, _n, **k: e.append((_t, _n, k))
    add(0.1, "wind_bed", level=0.4, until=T("whiteout"))
    add(0.5, "boot", level=0.6, pan=-0.2)
    add(1.2, "breath", kind="out", level=0.5)
    add(2.2, "carabiner", level=0.6, pan=0.3)
    add(T("whiteout"), "wind_bed", level=0.55, until=T("valley"), bright=True)
    add(T("valley"), "wind_bed", level=0.6, until=T("further"), gust=True)
    add(T("further"), "wind_bed", level=0.45, until=T("m-rope"))
    for i in range(4):
        add(T("further", 0.1 + i * 0.5), "snowstep", level=0.6, pan=-0.1)
    add(T("further", 0.5), "breath", kind="out", level=0.5)
    add(T("higher", 0.3), "carabiner", level=0.55, pan=0.2)
    for n, snd in (("m-rope", "rope"), ("m-snow", "snowstep"), ("m-ice", "axe"), ("m-ridge", "gust"),
                   ("m-alt", "beep"), ("m-climb", "breath"), ("m-belay", "carabiner")):
        add(T(n), snd, level=0.8)
    add(T("m-rope"), "breath_run", until=T("wide"), level=0.5)
    add(T("wide", 0.1), "wind_bed", level=0.3, until=T("meet"))
    add(T("meet"), "wind_bed", level=0.3, until=T("card"), still=True)
    tl.sfx = e
    tl.ambience = [(0, -20), (T("fog", 1.0), -9, 3.0), (T("whiteout"), -6), (T("together"), -5), (T("m-rope"), -1),
                   (T("wide"), -20, 0.05), (T("meet"), -10, 1.0)]
    tl.silence = [(T("wide"), T("meet"))]
    tl.music = [(0, 0.0), (T("fog"), 0.1), (T("whiteout"), 0.35), (T("together"), 0.55), (T("m-rope"), 0.7),
                (T("m-belay"), 1.0), (T("wide"), 0.0), (T("meet"), 0.3), (T("card"), 0.2), (T("card", 3.5), 0.0)]
    tl.marks = st
    return tl


def loop():
    """12 s, silent, seamless: fog, the mountain, a tiny group, snow, and back into the fog."""
    c = [
        Clip(S["fog_open"], 4.4, "fog", offset=1.5),
        Clip(S["wide_group"], 4.4, "wide", xin=1.2, offset=0.5),
        Clip(S["valley"], 4.4, "valley", xin=1.2),
    ]
    tl = Timeline("loop", c, loop=True)
    tl.marks = dict(zip([x.name for x in c], tl.starts()))
    return tl


TIMELINES = dict(full=full, cut=cut, loop=loop)


# ---------------------------------------------------------------- compositing a frame
def frame(tl, t):
    clips, starts = tl.clips, tl.starts()
    i = max(j for j, s in enumerate(starts) if s <= t + 1e-9)
    i = min(i, len(clips) - 1)
    c, s0 = clips[i], starts[i]
    lt = t - s0
    a = c.fn(lt + c.offset, c.dur)
    # dissolve from the previous clip, which keeps running under it
    if c.xin and lt < c.xin and i > 0:
        p, ps = clips[i - 1], starts[i - 1]
        b = p.fn(t - ps + p.offset, p.dur)
        k = smooth(lt / c.xin)
        a = b * (1 - k) + a * k
    if c.fin:
        a = a * smooth(lt / c.fin)
    if c.fout:
        a = a * (1 - smooth((lt - (c.dur - c.fout)) / c.fout))
    if tl.loop:
        a = _loop_seam(tl, t, a)
    if not c.raw:
        a = vignette(a, 0.3)
        a = grain(a, t, 0.028)
    a = np.clip(a, 0, 1)
    a = _labels(tl, t, a)
    a = _vo(tl, t, a)
    if tl.card is not None and t >= tl.card:
        a = _card(tl, t - tl.card, a)
    return a


def _loop_seam(tl, t, a):
    """The loop closes in fog: the first and last second fade into the same flat fog."""
    k = max(1 - smooth(t / 1.4), smooth((t - (tl.dur - 1.4)) / 1.4))
    col = np.array([0.66, 0.7, 0.75], np.float32)
    return a * (1 - k) + col * k


def _alpha(t, t0, t1, fi=0.45, fo=0.45):
    return smooth((t - t0) / fi) * (1 - smooth((t - (t1 - fo)) / fo))


def _vo(tl, t, a):
    for t0, t1, txt, st in tl.vo:
        if t0 - 0.01 <= t <= t1:
            al = _alpha(t, t0, t1, 0.55, 0.5)
            col = INK if st.get("dark") else PAPER
            y = C.h * st.get("y", 0.845)
            px = 44 * C.u
            blur = (1 - smooth((t - t0) / 0.7)) * 2.2 * C.u
            # a breath of shade behind the type (light behind dark type), so it never swims on mid-tones
            halo = np.array([1.0, 1.0, 1.0], np.float32) if st.get("dark") else np.array([0.0, 0.0, 0.0], np.float32)
            a = put_text(a, txt, C.w / 2, y, "serif", px, col=halo, alpha=al * 0.32, align="center", wght=330,
                         blur=blur + 7 * C.u)
            a = put_text(a, txt, C.w / 2, y, "serif", px, col=col, alpha=al * 0.95, align="center", wght=330, blur=blur)
    return a


def _labels(tl, t, a):
    """Expedition documentation in the corners: small, tracked capitals, inside the safe area."""
    mx, top, bot = C.w * 0.072, C.h * 0.105, C.h * 0.93
    px = 17 * C.u
    for t0, t1, d, st in tl.labels:
        if not (t0 <= t <= t1):
            continue
        al = _alpha(t, t0, t1, 0.5 if not st.get("slow") else 1.2, 0.4)
        col = INK if st.get("dark") else PAPER
        for k, txt in d.items():
            txt = txt.upper()
            if st.get("type") == k:
                n = int(len(txt) * clamp((t - t0) / 1.2))
                txt = txt[:n]
            x = mx if k[1] == "l" else C.w - mx
            y = top if k[0] == "t" else bot
            halo = np.array([1.0, 1.0, 1.0], np.float32) if st.get("dark") else np.array([0.0, 0.0, 0.0], np.float32)
            a = put_text(a, txt, x, y, "sans", px, col=halo, alpha=al * 0.25, align="left" if k[1] == "l" else "right",
                         track=0.2, wght=500, blur=4 * C.u)
            a = put_text(a, txt, x, y, "sans", px, col=col, alpha=al * 0.82, align="left" if k[1] == "l" else "right",
                         track=0.2, wght=500)
    return a


def _card(tl, lt, a):
    """White. The lockup, the school, then one line, then the invitation."""
    a = solid(PAPER)
    cx = C.w / 2
    if "logo" in tl.card_lines or "logo_join" in tl.card_lines:
        lw = int(300 * C.u)
        m = logo(lw)
        end = 2.7 if "logo" in tl.card_lines else 3.8
        al = _alpha(lt, 0.5, end, 0.8, 0.45)
        ytop = C.h * 0.4 - m.height / 2
        a = put_mask(a, m, cx - m.width / 2, ytop, INK, al)
        al2 = _alpha(lt, 1.1, end, 0.7, 0.45)
        y = ytop + m.height + 58 * C.u
        a = put_text(a, "SASSE", cx, y, "sans", 17 * C.u, col=INK, alpha=al2 * 0.9, align="center", track=0.24, wght=560)
        a = put_text(a, "STOCKHOLM SCHOOL OF ECONOMICS", cx, y + 30 * C.u, "sans", 15 * C.u, col=INK,
                     alpha=al2 * 0.62, align="center", track=0.22, wght=480)
        if "logo_join" in tl.card_lines:
            al3 = _alpha(lt, 1.9, end, 0.6, 0.45)
            a = put_text(a, "JOIN THE NEXT EXPEDITION.", cx, C.h * 0.86, "sans", 17 * C.u, col=INK, alpha=al3 * 0.9,
                         align="center", track=0.26, wght=560)
    if "outward" in tl.card_lines:
        al = _alpha(lt, 2.95, 4.65, 0.6, 0.45)
        w1 = _tw("From Stockholm, ", "serif", 50)
        w2 = _tw("outward.", "italic", 50)
        x0 = cx - (w1 + w2) / 2
        y = C.h * 0.52
        a = put_text(a, "From Stockholm,", x0, y, "serif", 50 * C.u, col=INK, alpha=al, wght=330)
        a = put_text(a, "outward.", x0 + w1, y, "italic", 50 * C.u, col=INK, alpha=al, wght=330)
    if "join" in tl.card_lines:
        al = _alpha(lt, 4.85, 6.55, 0.5, 0.7)
        a = put_text(a, "JOIN THE NEXT EXPEDITION.", cx, C.h * 0.52, "sans", 19 * C.u, col=INK, alpha=al * 0.92,
                     align="center", track=0.26, wght=560)
    return a


def _tw(s, kind, px):
    from kit import text_width
    return text_width(s, kind, px * C.u, wght=330)


# ---------------------------------------------------------------- rendering
_TL = None


def _init(name, w, h):
    global _TL
    C.set(w, h)
    _TL = TIMELINES[name]()


def _job(args):
    i, t, path = args
    a = frame(_TL, t)
    Image.fromarray((a * 255 + 0.5).astype(np.uint8)).save(path, compress_level=1)
    return i


def render(name, w=1920, h=1080, fps=24, jobs=None, t0=None, t1=None, workdir=None, redo=False):
    C.set(w, h)
    tl = TIMELINES[name]()
    n = int(round(tl.dur * fps))
    f0 = 0 if t0 is None else int(t0 * fps)
    f1 = n if t1 is None else min(n, int(t1 * fps))
    workdir = Path(workdir or tempfile.mkdtemp(prefix=f"film-{name}-"))
    workdir.mkdir(parents=True, exist_ok=True)
    todo = [(i, i / fps, workdir / f"{i:05d}.png") for i in range(f0, f1) if redo or not (workdir / f"{i:05d}.png").exists()]
    print(f"{name}: {tl.dur:.2f} s, frames {f0}-{f1}, {len(todo)} to render in {workdir}", flush=True)
    with Pool(jobs or os.cpu_count(), initializer=_init, initargs=(name, w, h)) as pool:
        for k, _ in enumerate(pool.imap_unordered(_job, todo, chunksize=2)):
            if k % 48 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    return workdir, tl


def sheet(name, w=960, h=540, out=None):
    """One frame from the middle of every clip, labelled, for review."""
    from PIL import ImageDraw
    C.set(w, h)
    tl = TIMELINES[name]()
    ims = []
    for c, s in zip(tl.clips, tl.starts()):
        t = s + c.dur * 0.55
        ims.append((c.name, to_pil(frame(tl, t))))
    cols = 4
    rows = math.ceil(len(ims) / cols)
    sh = Image.new("RGB", (cols * w, rows * (h + 22)), "white")
    d = ImageDraw.Draw(sh)
    for k, (nm, im) in enumerate(ims):
        x, y = (k % cols) * w, (k // cols) * (h + 22)
        sh.paste(im, (x, y))
        d.text((x + 6, y + h + 4), nm, fill="black")
    out = out or f"sheet-{name}.jpg"
    sh.save(out, quality=86)
    return out


LOOP_START = 3.0   # the loop is cut to begin here, on the mountain in the fog: its first frame is the poster


def rotated(workdir, fps=24, start=LOOP_START):
    """A view of the loop's frames that begins at `start` and wraps: the seam lands mid-loop, in fog."""
    frames = sorted(Path(workdir).glob("[0-9]*.png"))
    k = int(round(start * fps))
    rot = Path(workdir) / "rot"
    shutil.rmtree(rot, ignore_errors=True)
    rot.mkdir()
    for i, f in enumerate(frames[k:] + frames[:k]):
        (rot / f"{i:05d}.png").symlink_to(f.resolve())
    return rot


def posters():
    """The two posters: the loop's first frame, and the film's last people standing."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, which, at in (("poster", "loop", LOOP_START), ("poster-film", "full", None)):
        C.set(1920, 1080)
        tl = TIMELINES[which]()
        t = at if at is not None else tl.marks["meet"] + 6.6
        im = to_pil(frame(tl, t))
        im.save(OUT / f"{name}.webp", "WEBP", quality=72, method=6)
        print("wrote", OUT / f"{name}.webp")


# Grain is the most expensive thing in the picture to compress: every frame's is new. The encode
# thins it with a temporal denoise first, which keeps its texture and brings a 1:30 film from a few
# hundred megabytes to a few tens.
DENOISE = "hqdn3d=5:3:12:12"


def encode(workdir, tl, out, fps=24, audio=None, crf=25, webm=False, denoise=DENOISE):
    ff = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ff, "-y", "-v", "error", "-framerate", str(fps), "-i", str(Path(workdir) / "%05d.png")]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", denoise, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-tune", "film", "-movflags", "+faststart"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]
    subprocess.run(cmd, check=True)
    print("wrote", out, f"{Path(out).stat().st_size / 1e6:.1f} MB")
    if webm:
        wout = Path(out).with_suffix(".webm")
        cmd = [ff, "-y", "-v", "error", "-framerate", str(fps), "-i", str(Path(workdir) / "%05d.png"), "-vf", denoise,
               "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "42", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2",
               "-pix_fmt", "yuv420p", "-an", str(wout)]
        subprocess.run(cmd, check=True)
        print("wrote", wout, f"{wout.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=list(TIMELINES) + ["posters"])
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--from", dest="t0", type=float, default=None)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--no-encode", action="store_true")
    ap.add_argument("--redo", action="store_true", help="render frames in --from/--to again even if they exist")
    ap.add_argument("--size", default="1920x1080", help="WxH; 1080x1920 renders the vertical version")
    a = ap.parse_args()
    if a.which == "posters":
        posters()
        sys.exit()
    W, H = map(int, a.size.lower().split("x"))
    if a.sheet:
        print(sheet(a.which, W // 2, H // 2, out=f"sheet-{a.which}-{W}x{H}.jpg"))
        sys.exit()
    wd, tl = render(a.which, W, H, jobs=a.jobs, t0=a.t0, t1=a.t1, workdir=a.work, redo=a.redo)
    if a.t0 is not None or a.t1 is not None:
        sys.exit()          # a partial render is for review or repair, not for encoding
    if a.no_encode:
        sys.exit()
    OUT.mkdir(parents=True, exist_ok=True)
    import sound
    if a.which == "loop":
        encode(rotated(wd), tl, OUT / "hiking-club-loop.mp4", crf=27, webm=True, denoise="hqdn3d=6:4:14:14")
    else:
        wav = Path(wd) / "mix.wav"
        sound.mix(tl, wav)
        vert = "-vertical" if H > W else ""
        # the film is for the site (lighter); the cuts go to social platforms, which re-encode (richer)
        encode(wd, tl, OUT / ("hiking-club-film" + ("" if a.which == "full" else "-30s") + vert + ".mp4"),
               audio=wav, crf=25 if a.which == "full" else 23)
