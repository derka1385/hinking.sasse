"""Sound for the brand film: every sound is synthesised here, placed from the same timeline as
the picture (film.py). Nothing is sampled.

    python3 site/tools/film/sound.py full|cut [out.wav]

Buses: close (breath, hands, boots, dry), env (weather, a little air), far (ice, birds: long
tails), room (hut, doors, the city seen from inside), music (the score, long reverb).

The voice-over is not synthesised. Record it (see README) as vo/<line>.wav, named after the line
(`python3 sound.py lines` prints the names); any file present is placed at its line, in every
timeline that uses the line, and the rest of the mix ducks under it.
"""
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- basics
def slug(txt):
    import re
    return re.sub(r"[^a-z0-9]+", "-", txt.lower().replace("\u2019", "")).strip("-")


def rng(*k):
    import zlib
    return np.random.default_rng(zlib.crc32(repr(k).encode()))


def secs(d):
    return max(1, int(round(d * SR)))


def tvec(n):
    return np.arange(n, dtype=np.float32) / SR


def white(n, r):
    return r.standard_normal(n).astype(np.float32)


def pink(n, r):
    x = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = 1
    x /= np.sqrt(f)
    y = np.fft.irfft(x, n).astype(np.float32)
    return y / (np.std(y) + 1e-9)


def brown(n, r):
    y = np.cumsum(r.standard_normal(n)).astype(np.float32)
    y = hp(y, 20)
    return y / (np.std(y) + 1e-9)


@lru_cache(maxsize=None)
def _sos(kind, lo, hi=None, order=2):
    if kind == "bp":
        return signal.butter(order, [lo, hi], "bandpass", fs=SR, output="sos")
    return signal.butter(order, lo, kind, fs=SR, output="sos")


def lp(x, f, order=2):
    return signal.sosfilt(_sos("lowpass", float(f), None, order), x).astype(np.float32)


def hp(x, f, order=2):
    return signal.sosfilt(_sos("highpass", float(f), None, order), x).astype(np.float32)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(_sos("bp", float(lo), float(hi), order), x).astype(np.float32)


def slow(n, rate, r, lo=0.0, hi=1.0):
    """A smooth random curve: knots at `rate` Hz, eased between."""
    k = max(3, int(n / SR * rate) + 3)
    v = r.uniform(lo, hi, k)
    x = np.linspace(0, k - 1, n)
    i = np.floor(x).astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    i1 = np.minimum(i + 1, k - 1)
    return (v[i] * (1 - f) + v[i1] * f).astype(np.float32)


def fade(x, fin=0.02, fout=0.05):
    n = x.shape[-1]
    a, b = min(n, secs(fin)), min(n, secs(fout))
    e = np.ones(n, np.float32)
    if a > 1:
        e[:a] = np.sin(np.linspace(0, math.pi / 2, a)) ** 2
    if b > 1:
        e[n - b:] *= np.cos(np.linspace(0, math.pi / 2, b)) ** 2
    return x * e


def expdec(n, tau, attack=0.002):
    t = tvec(n)
    e = np.exp(-t / tau)
    a = secs(attack)
    if a > 1:
        e[:a] *= np.linspace(0, 1, a)
    return e.astype(np.float32)


def pan(x, p=0.0, width=0.0, r=None):
    """Mono to stereo, equal power; width decorrelates a little with a short delay."""
    a = (p + 1) * math.pi / 4
    L, R = x * math.cos(a), x * math.sin(a)
    if width:
        d = secs(0.011 * width)
        R = np.concatenate([np.zeros(d, np.float32), R[:-d]]) if d < len(R) else R
    return np.stack([L, R]).astype(np.float32)


def stereo(fn, n, r, corr=0.4):
    """Two partially correlated channels from a noise generator."""
    c = fn(n, r)
    a, b = fn(n, r), fn(n, r)
    return np.stack([c * corr + a * (1 - corr), c * corr + b * (1 - corr)]).astype(np.float32)


def modes(n, parts, r):
    """Damped sinusoids: parts = [(freq, tau, amp)]."""
    t = tvec(n)
    y = np.zeros(n, np.float32)
    for f, tau, a in parts:
        y += a * np.sin(2 * math.pi * f * t + r.uniform(0, 6.28)) * np.exp(-t / tau)
    return y


def grains(n, count, r, dist=None, glen=(0.001, 0.004), amp=(0.2, 1.0), band=(900, 7000)):
    y = np.zeros(n, np.float32)
    if dist is None:
        pos = r.random(count)
    else:
        pos = dist(count)
    for p in pos:
        g = secs(r.uniform(*glen))
        s = int(p * (n - g - 1))
        if s < 0:
            continue
        y[s:s + g] += white(g, r) * np.hanning(g).astype(np.float32) * r.uniform(*amp)
    return bp(y, *band) if band else y


# ---------------------------------------------------------------- the instruments
# Each returns (stereo array, bus). Levels are roughly peak 0.5 at level 1.

def i_wind_bed(d, r, bright=False, gust=False, still=False, **_):
    n = secs(d)
    depth = 0.8 if gust else 0.45 if not still else 0.25
    am = 1 - depth + depth * slow(n, 0.35 if gust else 0.2, r)
    rumble = lp(brown(n, r), 160) * 0.55
    body = np.stack([bp(pink(n, r), 220, 1300) for _ in range(2)]) * 0.35
    howl = np.zeros((2, n), np.float32)
    for f0 in (430, 610, 870):
        w = r.uniform(0.02, 0.05)
        e = slow(n, 0.25, r) ** 2
        for ch in range(2):
            howl[ch] += bp(white(n, r), f0 * (1 - w), f0 * (1 + w)) * e * 0.8
    hiss = np.stack([bp(white(n, r), 3000, 9000) for _ in range(2)]) * (0.22 if bright else 0.07)
    y = (rumble[None] * 0.8 + body + howl * (0.5 if not still else 0.2) + hiss) * am[None]
    return y * 0.45, "env"


def i_boot(d, r, pan_=0.0, soft=False, **_):
    n = secs(0.34)
    k = int(r.integers(22, 36) * (0.6 if soft else 1))
    cr = grains(n, k, r, dist=lambda c: r.beta(1.3, 3.5, c) * 0.7, band=(1100, 7500))
    cr *= expdec(n, 0.12, 0.012)
    th = modes(n, [(r.uniform(62, 80), 0.05, 0.9)], r) * expdec(n, 0.06, 0.004)
    sq = modes(n, [(r.uniform(1250, 1700), 0.03, 0.12)], r)
    y = cr * 1.5 + lp(th, 200) * (0.4 if soft else 0.7) + sq
    return pan(y / (np.abs(y).max() + 1e-9) * 0.55, pan_), "close"


def i_snowstep(d, r, **k):
    y, b = i_boot(d, r, soft=True, **k)
    return y * 0.8, "close"


def i_breath(d, r, kind="out", **_):
    dur = 0.8 if kind == "in" else 0.62
    n = secs(dur)
    t = tvec(n) / dur
    x = white(n, r)
    y = bp(x, 380, 2600) * 0.6 + bp(x, 650, 1050) * 0.55 + bp(x, 1300, 1800) * 0.3
    if kind == "in":
        e = np.sin(np.clip(t / 0.8, 0, 1) * math.pi / 2) ** 2 * (1 - np.clip((t - 0.8) / 0.2, 0, 1))
    else:
        e = np.clip(t / 0.08, 0, 1) * np.exp(-np.clip(t - 0.08, 0, None) * 4.2)
    e = e * (0.85 + 0.15 * slow(n, 30, r))
    y = y * e.astype(np.float32)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.4, 0.05, 0.2), "close"


def i_breath_run(d, r, **_):
    n = secs(d)
    out = np.zeros((2, n), np.float32)
    t, per, i = 0.0, 0.95, 0
    while t < d - 0.5:
        b, _ = i_breath(0, rng("br", i, int(t * 100)), kind="in" if i % 2 == 0 else "out")
        s = secs(t)
        m = min(b.shape[1], n - s)
        out[:, s:s + m] += b[:, :m] * (0.5 + 0.5 * t / d)
        t += per * (0.45 if i % 2 == 0 else 0.55)
        per = max(0.62, per * 0.985)
        i += 1
    return out * 0.8, "close"


def i_fabric(d, r, **_):
    n = secs(0.7)
    y = grains(n, 60, r, glen=(0.006, 0.03), band=(1500, 7000))
    y *= np.sin(np.linspace(0, math.pi, n)).astype(np.float32) ** 1.5
    return pan(y / (np.abs(y).max() + 1e-9) * 0.28, -0.1, 0.4), "close"


def i_carabiner(d, r, pan_=0.2, **_):
    n = secs(0.6)
    parts = [(f * r.uniform(0.97, 1.03), tau, a) for f, tau, a in
             ((1480, 0.16, 0.5), (2350, 0.13, 0.8), (3920, 0.09, 0.6), (5610, 0.07, 0.45), (7420, 0.05, 0.3), (9870, 0.035, 0.2))]
    y = modes(n, parts, r)
    click = np.zeros(n, np.float32)
    g = secs(0.003)
    click[:g] = hp(white(g, r), 2500) * 1.5
    y2 = np.zeros(n, np.float32)
    s = secs(0.034)
    y2[s:] = (modes(n - s, [(p[0] * 1.13, p[1] * 0.6, p[2] * 0.5) for p in parts], r))
    y2[s:s + g] += hp(white(g, r), 2500)
    y = y + click + y2
    return pan(y / (np.abs(y).max() + 1e-9) * 0.42, pan_), "env"


def i_ice(d, r, pan_=-0.4, **_):
    """Lake ice under tension: the dispersive 'pew' a frozen lake sings, and a low boom."""
    n = secs(3.0)
    t = tvec(n)
    y = np.zeros(n, np.float32)
    for k, (dl, a) in enumerate(((0.0, 1.0), (0.09, 0.55), (0.23, 0.3))):
        s = secs(dl)
        tt = t[: n - s]
        f = 170 + 2700 * np.exp(-tt / 0.1)
        ph = 2 * math.pi * np.cumsum(f) / SR
        e = np.exp(-tt / 0.28) * np.clip(tt / 0.004, 0, 1)
        y[s:] += (np.sin(ph) * e * a).astype(np.float32)
    boom = lp(brown(n, r), 90) * expdec(n, 0.5, 0.01)
    y = y * 0.6 + boom * 0.7
    return pan(y / (np.abs(y).max() + 1e-9) * 0.5, pan_, 0.6), "far"


def i_bird(d, r, pan_=-0.5, **_):
    """A golden plover, far off: one mournful falling whistle, then another."""
    n = secs(2.2)
    t = tvec(n)
    y = np.zeros(n, np.float32)
    for st in (0.0, 1.05):
        s = secs(st)
        m = secs(0.34)
        tt = t[:m]
        f = 2780 - 380 * (tt / 0.34) ** 0.8 + 16 * np.sin(2 * math.pi * 7 * tt)
        ph = 2 * math.pi * np.cumsum(f) / SR
        e = np.sin(np.pi * tt / 0.34) ** 1.4
        y[s:s + m] += (np.sin(ph) + 0.08 * np.sin(2 * ph)) * e
    return pan(y * 0.3, pan_), "far"


def i_city(d, r, **_):
    n = secs(d)
    base = lp(brown(n, r), 240) * 0.5
    cars = np.zeros(n, np.float32)
    tt = r.uniform(0.5, 2.5)
    x = pink(n, r)
    band = bp(x, 180, 900)
    t = tvec(n)
    while tt < d:
        w = r.uniform(1.5, 3.0)
        cars += np.exp(-((t - tt) / w) ** 2).astype(np.float32) * r.uniform(0.3, 1.0)
        tt += r.uniform(2.0, 4.5)
    y = base + band * cars * 0.5 + hp(white(n, r), 6000) * 0.01
    y = np.stack([y, np.roll(y, secs(0.013))])
    return fade(y, 0.4, 0.6) * 0.5, "room"


def i_steps_city(d, r, count=5, rate=1.9, pan_=0.0, **_):
    n = secs(count / rate + 0.4)
    y = np.zeros(n, np.float32)
    for i in range(count):
        s = secs(i / rate + r.uniform(-0.02, 0.02))
        m = secs(0.12)
        heel = bp(white(secs(0.003), r), 1200, 5000) * r.uniform(0.7, 1.0)
        sole = lp(white(secs(0.04), r), 1500) * expdec(secs(0.04), 0.012) * 0.4
        splash = bp(white(m, r), 3000, 8000) * expdec(m, 0.03) * 0.12
        y[s:s + len(heel)] += heel
        y[s + secs(0.05):s + secs(0.05) + len(sole)] += sole
        y[s:s + m] += splash
    return pan(y / (np.abs(y).max() + 1e-9) * 0.3, pan_), "room"


def i_door(d, r, **_):
    n = secs(1.0)
    latch = modes(n, [(2600, 0.03, 0.5), (4100, 0.02, 0.3)], r)
    thump = lp(white(n, r), 300) * expdec(n, 0.12, 0.004) * 1.2 + modes(n, [(55, 0.2, 0.8)], r)
    air = bp(pink(n, r), 200, 1000) * np.sin(np.linspace(0, math.pi, n)).astype(np.float32) * 0.2
    y = np.zeros(n, np.float32)
    y += air
    s = secs(0.25)
    y[s:] += (thump[: n - s] + latch[: n - s] * 0.6)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.45, 0.1), "room"


def i_rain_glass(d, r, **_):
    n = secs(d)
    y = lp(pink(n, r), 2500) * 0.08
    k = int(d * 45)
    ticks = grains(n, k, r, glen=(0.0005, 0.0015), band=(2000, 9000), amp=(0.1, 0.8))
    y += ticks * 0.6
    for tt in np.sort(r.random(int(d * 3))) * d:
        s = secs(tt)
        m = secs(0.03)
        if s + m < n:
            y[s:s + m] += modes(m, [(r.uniform(850, 1500), 0.008, 0.25)], r)
    y = np.stack([y, np.roll(y, secs(0.007))])
    return fade(y, 0.3, 0.2) * 0.8, "room"


def i_train(d, r, slam=False, **_):
    n = secs(d)
    t = tvec(n)
    rumble = lp(brown(n, r), 140) * 0.9
    rattle = bp(pink(n, r), 180, 900) * (0.6 + 0.4 * np.abs(np.sin(2 * math.pi * 11.3 * t + slow(n, 2, r) * 3)))
    clack = np.zeros(n, np.float32)
    tt = r.uniform(0.1, 0.5)
    while tt < d:
        for dt, a in ((0.0, 1.0), (0.14, 0.8)):
            s = secs(tt + dt)
            m = secs(0.2)
            if s + m < n:
                clack[s:s + m] += (modes(m, [(r.uniform(60, 75), 0.1, 1.0), (1100, 0.06, 0.12)], r)
                                   + bp(white(m, r), 300, 2000) * expdec(m, 0.03) * 0.5) * a
        tt += 1.05
    y = rumble + rattle * 0.35 + clack * 0.6
    y = np.stack([y, np.roll(y, secs(0.009))])
    return fade(y, 0.0 if slam else 0.35, 0.25) * 0.55, "room"


def i_paper(d, r, **_):
    n = secs(0.75)
    y = grains(n, 45, r, glen=(0.004, 0.028), band=(800, 6500), amp=(0.1, 1.0))
    y *= np.sin(np.linspace(0, math.pi, n)).astype(np.float32)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.35, 0.1, 0.3), "close"


def i_click(d, r, **_):
    n = secs(0.1)
    y = np.zeros(n, np.float32)
    for s in (0, secs(0.022)):
        g = secs(0.0012)
        y[s:s + g] += hp(white(g, r), 3000)
        y[s:] += modes(n - s, [(3500, 0.004, 0.3)], r)
    return pan(y * 0.4, 0.15), "close"


def i_tent(d, r, **_):
    n = secs(d)
    flap = bp(pink(n, r), 90, 700) * (0.3 + 0.7 * slow(n, 7, r) ** 3)
    wind = lp(pink(n, r), 450) * 0.3
    y = flap * 0.6 + wind
    y = np.stack([y, np.roll(y, secs(0.02))])
    return fade(y, 0.2, 0.3) * 0.45, "room"


def i_rock(d, r, **_):
    n = secs(0.45)
    y = grains(n, 70, r, glen=(0.001, 0.006), band=(300, 3500)) * expdec(n, 0.18, 0.02)
    y += lp(white(n, r), 150) * expdec(n, 0.05, 0.003) * 0.8
    return pan(y / (np.abs(y).max() + 1e-9) * 0.45, -0.1), "close"


def i_rope(d, r, **_):
    n = secs(0.6)
    t = tvec(n)
    x = bp(white(n, r), 1200, 4800)
    am = 0.5 + 0.5 * np.abs(np.sin(2 * math.pi * (38 + 10 * t) * t))
    e = np.sin(np.linspace(0, math.pi, n)).astype(np.float32) ** 0.7
    y = x * am * e
    return pan(y / (np.abs(y).max() + 1e-9) * 0.4, 0.2, 0.3), "close"


def i_rain_hit(d, r, **_):
    n = secs(0.8)
    y = grains(n, 180, r, glen=(0.0005, 0.002), band=(1500, 9000)) + lp(pink(n, r), 3000) * 0.15
    y *= np.clip(np.linspace(1.5, 0, n), 0, 1).astype(np.float32)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.45, 0.0, 0.5), "close"


def i_axe(d, r, **_):
    n = secs(0.6)
    y = np.zeros(n, np.float32)
    g = secs(0.002)
    y[:g] += white(g, r) * 2
    y += hp(white(n, r), 1800) * expdec(n, 0.03, 0.001)
    y += modes(n, [(1250, 0.15, 0.4), (2870, 0.1, 0.3), (4100, 0.06, 0.2)], r)
    y += lp(white(n, r), 160) * expdec(n, 0.07, 0.002) * 1.2
    return pan(y / (np.abs(y).max() + 1e-9) * 0.5, 0.15), "env"


def i_gust(d, r, **_):
    n = secs(1.0)
    e = np.sin(np.linspace(0, math.pi, n)).astype(np.float32) ** 2
    y = np.stack([bp(pink(n, r), 350, 2600) for _ in range(2)]) * e * 0.6
    y += np.stack([bp(white(n, r), 700, 800) for _ in range(2)]) * e * 0.5
    return y * 0.5, "env"


def i_beep(d, r, **_):
    n = secs(0.2)
    t = tvec(n)
    y = np.zeros(n, np.float32)
    for s in (0.0, 0.09):
        m = (t >= s) & (t < s + 0.045)
        y[m] += np.sin(2 * math.pi * 2900 * t[m]) * 0.3
    return pan(fade(y, 0.002, 0.005) * 0.5, 0.0), "close"


def i_water_hit(d, r, **_):
    n = secs(0.9)
    y = bp(pink(n, r), 300, 6000) * 0.5
    t = tvec(n)
    for _ in range(40):
        s = r.integers(0, n - secs(0.03))
        m = secs(r.uniform(0.008, 0.02))
        f0 = r.uniform(400, 1500)
        tt = t[:m]
        y[s:s + m] += np.sin(2 * math.pi * (f0 + f0 * 3 * tt / 0.02) * tt) * np.hanning(m) * 0.4
    y *= np.clip(np.linspace(1.4, 0, n), 0, 1).astype(np.float32)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.45, -0.2, 0.5), "env"


def i_hut(d, r, **_):
    n = secs(d)
    y = lp(brown(n, r), 200) * 0.12 + lp(pink(n, r), 350) * 0.12
    k = int(d * 6)
    pops = grains(n, k, r, glen=(0.0008, 0.003), band=(700, 8000), amp=(0.1, 1.0))
    y += pops * 0.6
    y = np.stack([y, np.roll(y, secs(0.006))])
    return fade(y, 0.05, 0.4) * 0.6, "room"


def i_mug(d, r, **_):
    n = secs(0.8)
    y = modes(n, [(3150, 0.22, 0.6), (4720, 0.15, 0.4), (6800, 0.08, 0.25)], r)
    g = secs(0.002)
    y[:g] += white(g, r)
    return pan(y / (np.abs(y).max() + 1e-9) * 0.22, 0.25), "room"


def i_hum(d, r, **_):
    n = secs(d)
    t = tvec(n)
    y = sum(a * np.sin(2 * math.pi * f * t) for f, a in ((100, 0.5), (200, 0.3), (300, 0.2), (400, 0.12)))
    y = y.astype(np.float32) + lp(pink(n, r), 800) * 0.2 + hp(white(n, r), 5000) * 0.02
    return pan(fade(y, 0.0, 0.0) * 0.3, 0.0, 0.3), "room"


def i_keys(d, r, **_):
    n = secs(d)
    y = np.zeros(n, np.float32)
    tt = 0.02
    while tt < d:
        s = secs(tt)
        m = secs(0.012)
        if s + m < n:
            y[s:s + m] += bp(white(m, r), 1800, 6000) * expdec(m, 0.003) + modes(m, [(210, 0.006, 0.3)], r)
        tt += r.uniform(0.07, 0.2)
    return pan(y * 0.35, 0.0, 0.2), "close"


def i_metro(d, r, **_):
    n = secs(d)
    y = lp(brown(n, r), 180) * 1.0 + bp(white(n, r), 2800, 3000) * 0.3 * slow(n, 3, r)
    y = np.stack([y, np.roll(y, secs(0.01))])
    return y * 0.45, "room"


def i_riser(d, r, **_):
    """Into the drop: air rising and a held low cluster, cut dead at the end."""
    n = secs(d)
    t = tvec(n) / d
    y = np.zeros(n, np.float32)
    for lo in (300, 700, 1500, 3000):
        y += bp(white(n, r), lo, lo * 1.6) * np.clip((t - (lo / 6000)) * 2, 0, 1) ** 2
    y = y * t ** 2.2
    y = np.stack([y, np.roll(y, secs(0.012))])
    y[:, -secs(0.004):] *= np.linspace(1, 0, secs(0.004))
    return y * 0.25, "musicdry"


INSTR = {k[2:]: v for k, v in globals().items() if k.startswith("i_")}


# ---------------------------------------------------------------- the score
def wavetable_voice(f, n, r, harm=14, tilt=1.35, detune=0.0):
    k = np.arange(1, harm + 1)
    k = k[k * f < 5000]
    tab_n = 4096
    ph = np.linspace(0, 1, tab_n, endpoint=False)
    tab = np.zeros(tab_n, np.float32)
    rp = r.uniform(0, 6.28, len(k))
    for kk, p in zip(k, rp):
        tab += np.sin(2 * math.pi * kk * ph + p).astype(np.float32) / kk ** tilt
    fr = f * (1 + detune)
    pos = (np.arange(n, dtype=np.float64) * fr / SR + r.random()) % 1.0 * tab_n
    i = pos.astype(np.int32)
    fr_ = (pos - i).astype(np.float32)
    return tab[i] * (1 - fr_) + tab[(i + 1) % tab_n] * fr_


def automation(points, n):
    """Gain in dB at breakpoints (t, dB[, ramp s]); each ramps from the previous value."""
    g = np.zeros(n, np.float32)
    cur = points[0][1]
    for i, p in enumerate(points):
        t0, v = p[0], p[1]
        rmp = p[2] if len(p) > 2 else 0.15
        s = secs(t0)
        e = secs(points[i + 1][0]) if i + 1 < len(points) else n
        if e <= s:
            continue
        seg = np.arange(e - s) / SR
        k = np.clip(seg / max(rmp, 1e-3), 0, 1)
        g[s:e] = cur + (v - cur) * k
        cur = float(g[e - 1])
    return (10 ** (g / 20)).astype(np.float32)


def level_curve(tl, n):
    pts = sorted(tl.music)
    # each breakpoint eases towards its value over 1.6 s; a drop to silence is instant
    lv = np.zeros(n, np.float32)
    cur = 0.0
    for i, (t0, v) in enumerate(pts):
        s = int(t0 * SR)
        e = int(pts[i + 1][0] * SR) if i + 1 < len(pts) else n
        if e <= s:
            continue
        seg = np.arange(e - s) / SR
        if v == 0.0 and cur > 0.3:
            lv[s:e] = 0.0
        else:
            k = np.clip(seg / 1.6, 0, 1)
            k = k * k * (3 - 2 * k)
            lv[s:e] = cur + (v - cur) * k
        cur = float(lv[e - 1])
    return lv


def score(tl, n):
    r = rng("score", tl.name)
    L = level_curve(tl, n)
    out = np.zeros((2, n), np.float32)
    # drone: open fifths on D, and a ninth for the cold
    notes = (73.42, 110.0, 146.83, 164.81, 220.0)
    dr = np.zeros((2, n), np.float32)
    for j, f in enumerate(notes):
        for ch, det in enumerate((-0.0016, 0.0017)):
            v = wavetable_voice(f, n, r, detune=det + r.uniform(-0.0004, 0.0004))
            dr[ch] += v * (0.9 - 0.12 * j) * (0.6 + 0.4 * slow(n, 0.12, r))
    dr = np.stack([lp(dr[0], 700), lp(dr[1], 760)])
    out += dr * (L ** 1.1)[None] * 0.16
    # sub
    t = tvec(n)
    sub = np.sin(2 * math.pi * 36.71 * t).astype(np.float32) * 0.5 + np.sin(2 * math.pi * 73.42 * t).astype(np.float32) * 0.25
    out += sub[None] * np.clip((L - 0.25) / 0.75, 0, 1)[None] * 0.35
    # bowed metal, far away
    mt = np.zeros((2, n), np.float32)
    for f in (587.3, 1244.5, 1975.5, 2637.0, 3322.4):
        for ch in range(2):
            mt[ch] += bp(white(n, r), f * 0.996, f * 1.004) * slow(n, 0.18, r) ** 2
    out += mt * (L ** 1.8)[None] * 0.55
    # the pulse: a heartbeat that quickens with the climb
    pulse_env = np.clip((L - 0.5) / 0.5, 0, 1)
    beats = np.zeros(n, np.float32)
    ticks = np.zeros(n, np.float32)
    metal = np.zeros(n, np.float32)
    tt, bpm, bi = 0.0, 68.0, 0
    kick = lambda m, f0, a: (np.sin(2 * math.pi * np.cumsum(f0 * np.exp(-tvec(m) / 0.05) + 42) / SR) * expdec(m, 0.13, 0.003) * a)
    while tt < n / SR - 0.5:
        s = secs(tt)
        pe = pulse_env[min(s, n - 1)]
        if pe > 0.02:
            m = secs(0.35)
            if s + m < n:
                beats[s:s + m] += kick(m, 55, 1.0) * pe
                s2 = s + secs(0.19)
                if s2 + m < n:
                    beats[s2:s2 + m] += kick(m, 45, 0.55) * pe
                for q in (0.5,):
                    s3 = s + secs(60 / bpm * q)
                    g = secs(0.004)
                    if s3 + g < n and pe > 0.5:
                        ticks[s3:s3 + g] += hp(white(g, r), 5000) * (pe - 0.5) * 0.5
                if bi % 4 == 0 and pe > 0.6 and s + secs(1.2) < n:
                    metal[s:s + secs(1.2)] += modes(secs(1.2), [(381, 0.5, 0.5), (913, 0.35, 0.35), (1571, 0.25, 0.25)], r) * (pe - 0.6)
            bpm = min(96.0, bpm + 0.9 * pe)
        else:
            bpm = 68.0
        tt += 60 / bpm
        bi += 1
    out += np.stack([beats, beats]) * 0.9
    out += pan(ticks, 0.3) * 0.5 + pan(metal, -0.35, 0.8) * 0.6
    # felt piano: a few notes, placed by the timeline
    for t0, midi, vel in getattr(tl, "notes", []):
        s = secs(t0)
        pn = piano(440 * 2 ** ((midi - 69) / 12), vel, r)
        m = min(pn.shape[1], n - s)
        if m > 0:
            out[:, s:s + m] += pn[:, :m]
    return out, L


def piano(f, vel, r):
    n = secs(6.0)
    t = tvec(n)
    y = np.zeros(n, np.float32)
    B = 0.00035
    for k in range(1, 12):
        fk = f * k * math.sqrt(1 + B * k * k)
        if fk > 7000:
            break
        tau = 3.2 / k ** 0.75
        y += np.sin(2 * math.pi * fk * t + r.uniform(0, 6.28)).astype(np.float32) * np.exp(-t / tau).astype(np.float32) / k ** 1.7
    att = np.clip(t / 0.012, 0, 1).astype(np.float32)
    y = y * att
    ham = lp(white(secs(0.03), r), 1000) * 0.15
    y[:len(ham)] += ham
    y = lp(y, 2600) * vel * 0.3
    return pan(y, r.uniform(-0.15, 0.15), 0.4)


# ---------------------------------------------------------------- space
@lru_cache(maxsize=None)
def ir(rt60, pre=0.02, bright=0.35, seed=0):
    r = np.random.default_rng(seed)
    n = secs(rt60 * 1.1)
    t = tvec(n)
    env = 10 ** (-3 * t / rt60)
    out = []
    for ch in range(2):
        x = r.standard_normal(n).astype(np.float32)
        dark = lp(x, 1800) * 1.4
        brt = hp(x, 1800) * np.exp(-t / (rt60 / 7))
        y = (dark + brt * bright) * env
        y = np.concatenate([np.zeros(secs(pre), np.float32), y])
        out.append(y / np.sqrt(np.sum(y * y)))
    return np.stack(out)


def reverb(x, rt60, wet, pre=0.02, bright=0.35):
    h = ir(rt60, pre, bright)
    y = np.stack([signal.oaconvolve(x[c], h[c])[: x.shape[1]] for c in range(2)]).astype(np.float32)
    return x * (1 - wet * 0.5) + y * wet


BUS = dict(close=None, env=(1.6, 0.22, 0.02), far=(3.8, 0.7, 0.05), room=(0.55, 0.28, 0.005),
           music=(5.0, 0.55, 0.03), musicdry=None, vo=(0.4, 0.08, 0.003))


# ---------------------------------------------------------------- the mix
def mix(tl, out=None, tail=1.5):
    n = secs(tl.dur + tail)
    buses = {k: np.zeros((2, n), np.float32) for k in BUS}
    for i, (t0, name, kw) in enumerate(tl.sfx):
        kw = dict(kw)
        level = kw.pop("level", 1.0)
        until = kw.pop("until", None)
        fin = kw.pop("fin", 0.5)
        fout = kw.pop("fout", 0.5)
        if "pan" in kw:
            kw["pan_"] = kw.pop("pan")
        if until:
            # beds overlap their neighbours by half a second either side of the cut
            hard = kw.get("slam", False)
            t0 = t0 if hard else t0 - fin / 2
            d = until - t0 + fout / 2
        else:
            d = 1.0
        y, bus = INSTR[name](d, rng(tl.name, i, name), **kw)
        if until:
            y = fade(y, 0.0 if kw.get("slam") else fin, fout)
        s = secs(max(0.0, t0))
        m = min(y.shape[1], n - s)
        if m > 0:
            buses[bus][:, s:s + m] += y[:, :m] * level
    # the drop into the wide shot: a riser that is cut dead
    if "wide" in tl.marks:
        y, b = i_riser(1.9, rng("riser"))
        s = secs(tl.marks["wide"] - 1.9)
        buses[b][:, s:s + y.shape[1]] += y[:, : n - s]
    mus, L = score(tl, n)
    buses["music"] += mus
    # the voice, if it has been recorded
    vo_dir = HERE / "vo"
    duck = np.ones(n, np.float32)
    for k, (t0, t1, txt, st) in enumerate(tl.vo):
        f = vo_dir / f"{slug(txt)}.wav"
        if not f.exists():
            continue
        sr, v = wavfile.read(f)
        v = v.astype(np.float32)
        v = v / (np.abs(v).max() + 1e-9) * 0.6
        if v.ndim > 1:
            v = v.mean(1)
        if sr != SR:
            v = signal.resample_poly(v, SR, sr).astype(np.float32)
        s = secs(t0 - 0.15)
        m = min(len(v), n - s)
        buses["vo"][:, s:s + m] += pan(v[:m], 0.0)
        duck[s:s + m] = np.minimum(duck[s:s + m], 0.6)
    duck = lp(duck, 4)
    amb = automation(getattr(tl, "ambience", [(0, 0.0)]), n)
    gate = np.ones(n, np.float32)
    for a, b in getattr(tl, "silence", []):
        sa, sb = secs(a), secs(b)
        f1, f2 = secs(0.06), secs(2.5)
        gate[sa:sb] = 0.0
        gate[max(0, sa - f1):sa] = np.linspace(1, 0, sa - max(0, sa - f1))
        gate[sb:sb + f2] = np.linspace(0, 1, len(gate[sb:sb + f2]))
    mixd = np.zeros((2, n), np.float32)
    for k, x in buses.items():
        if not np.any(x):
            continue
        if BUS[k]:
            x = reverb(x, BUS[k][0], BUS[k][1], BUS[k][2])
        if k in ("music", "musicdry"):
            x = x * gate[None]
        elif k != "vo":
            x = x * amb[None]
        if k != "vo":
            x = x * duck[None]
        mixd += x
    if tl.card is not None:
        s = secs(tl.card)
        mixd[:, s:] *= np.exp(-np.arange(n - s) / SR / 0.06)[None]    # cut to white: the world stops
        for dt, midi, vel in ((0.55, 50, 0.55), (0.6, 57, 0.35), (4.85 if "join" in tl.card_lines else 1.95, 62, 0.25)):
            pn = piano(440 * 2 ** ((midi - 69) / 12), vel, rng("card", midi))
            pn = reverb(np.pad(pn, ((0, 0), (0, secs(2)))), 5.0, 0.55, 0.03)
            s2 = secs(tl.card + dt)
            m = min(pn.shape[1], n - s2)
            mixd[:, s2:s2 + m] += pn[:, :m] * 0.16
    # master: gentle high-pass, level, soft ceiling
    mixd = np.stack([hp(mixd[0], 25), hp(mixd[1], 25)])
    ref = np.percentile(np.abs(mixd), 99.95) + 1e-9
    mixd = mixd * (0.72 / ref)
    over = np.abs(mixd) > 0.72
    mixd[over] = np.sign(mixd[over]) * (0.72 + 0.23 * np.tanh((np.abs(mixd[over]) - 0.72) / 0.23))
    mixd *= 0.76          # about -16 LUFS integrated: room for the quiet parts on a laptop, no pumping
    fo = secs(0.8)
    mixd[:, -fo:] *= np.linspace(1, 0, fo)[None]
    if out:
        wavfile.write(str(out), SR, mixd.T.astype(np.float32))
    return mixd


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    import film
    which = sys.argv[1] if len(sys.argv) > 1 else "full"
    if which == "lines":
        for t0, t1, txt, st in film.full().vo:
            print(f"vo/{slug(txt)}.wav  {t1 - t0:.1f} s  {txt}")
        sys.exit()
    out = sys.argv[2] if len(sys.argv) > 2 else f"{which}.wav"
    mix(film.TIMELINES[which](), out)
    print("wrote", out)
