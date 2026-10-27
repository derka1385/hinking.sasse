"""Terrain processing for the Khumbu scene (reads khumbu_sharp.npy, xs, ys from fetch_dem.py).
- analysis fields on the 30 m grid: slope, convexity, runoff (D8 flow accumulation), fall-line streaks (LIC)
- hero mountains at 10 m: summit pyramid rebuilt from the data's own aretes (the radar rounds spires),
  then fall-line erosion detail (line integral convolution of noise along the slope)
Writes khumbu_processed.npz."""
import os, time, json
import numpy as np
from scipy import ndimage as nd
os.chdir(os.path.dirname(os.path.abspath(__file__)))
t0 = time.time()
HEROES = [("Ama Dablam", 0.0, 0.0, 6812.0), ("Cholatse", -9540.0, 6184.0, 6440.0)]   # name, centre x/y (m), real summit (m)
z = np.load('khumbu_sharp.npy').astype(np.float64)
xs = np.load('khumbu_xs.npy').astype(np.float64); ys = np.load('khumbu_ys.npy').astype(np.float64)
H, W = z.shape; dx, dy = 27.34, 30.72
rng = np.random.default_rng(7)

def analysis(z, dx, dy, smooth=0.0):
    gy, gx = np.gradient(nd.gaussian_filter(z, smooth) if smooth else z, dy, dx)
    slope = np.arctan(np.hypot(gx, gy)) / (np.pi / 2)
    lap = nd.gaussian_laplace(z, 1.5) + 0.5 * nd.gaussian_laplace(z, 4.0)
    conv = np.tanh(-lap / (np.std(lap) * 1.5))
    return slope, conv

def lic(vx, vy, noise, steps=18, h=1.0):
    Hh, Wh = noise.shape; yy, xx = np.mgrid[0:Hh, 0:Wh].astype(np.float64)
    acc = noise.copy(); n = 1
    for sgn in (1, -1):
        py, px = yy.copy(), xx.copy()
        for _ in range(steps):
            u = nd.map_coordinates(vx, [py, px], order=1, mode='nearest'); v = nd.map_coordinates(vy, [py, px], order=1, mode='nearest')
            px += sgn * h * u; py += sgn * h * v
            acc += nd.map_coordinates(noise, [py, px], order=1, mode='nearest'); n += 1
    return acc / n

def streaks(zz, ddx, ddy, scales):
    gy, gx = np.gradient(zz, ddy, ddx); gn = np.hypot(gx, gy) + 1e-9
    vx, vy = -gx / gn, -gy / gn                      # downhill in (col, row) index space
    out = np.zeros_like(zz)
    for scale, amp in scales:
        nz = nd.zoom(rng.random((int(zz.shape[0] / scale) + 1, int(zz.shape[1] / scale) + 1)), scale, order=1)[:zz.shape[0], :zz.shape[1]]
        s = lic(vx, vy, nz, steps=int(8 + 4 * scale)); out += amp * (s - s.mean()) / (s.std() + 1e-9)
    return out

# ---- runoff on the 30 m grid (highest cells first hand their water to their steepest neighbour)
order = np.argsort(-z, axis=None); zp = np.pad(z, 1, constant_values=np.inf)
nbr = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
drops = np.stack([(z - zp[1+a:H+1+a, 1+b:W+1+b]) / np.hypot(a*dy, b*dx) for a, b in nbr])
k = np.argmax(drops, 0); has = drops.max(0) > 0
ry = np.clip(np.arange(H)[:, None] + np.array([a for a, b in nbr])[k], 0, H-1); rx = np.clip(np.arange(W)[None, :] + np.array([b for a, b in nbr])[k], 0, W-1)
recv = np.where(has, ry * W + rx, -1).ravel(); acc = np.ones(H * W)
for i in order:
    r = recv[i]
    if r >= 0: acc[r] += acc[i]
flow = np.clip(np.log10(acc.reshape(H, W)) / 3.5, 0, 1)
slope, conv = analysis(z, dx, dy, smooth=1.8)
streak_b = np.tanh(streaks(z, dx, dy, ((1.5, 0.8), (4.0, 0.7))) / 1.6) * 0.5 + 0.5
out = dict(z=z, xs=xs, ys=ys, slope=slope, conv=conv, flow=flow, streak_b=streak_b)
print(f"backdrop fields {time.time()-t0:.1f}s")

# ---- hero mountains
Z = 3; hdx, hdy = dx / Z, dy / Z
windows = []
for hi, (name, cx, cy, top) in enumerate(HEROES):
    ix0, ix1 = np.searchsorted(xs, cx - 3500), np.searchsorted(xs, cx + 3500)
    iy0, iy1 = np.searchsorted(-ys, -(cy + 3500)), np.searchsorted(-ys, -(cy - 3500))
    windows.append([ix0, ix1, iy0, iy1])
    zh = nd.zoom(z[iy0:iy1+1, ix0:ix1+1], Z, order=3)
    hx = np.linspace(xs[ix0], xs[ix1], zh.shape[1]); hy = np.linspace(ys[iy0], ys[iy1], zh.shape[0])
    HX, HY = np.meshgrid(hx, hy)
    # summit rebuilt from its aretes: ridge directions = height maxima on a 700 m circle around the top
    near = np.hypot(HX - cx, HY - cy) < 900
    sy, sx = np.unravel_index(np.argmax(np.where(near, zh, -1e9)), zh.shape); SX, SY = HX[sy, sx], HY[sy, sx]
    def z_at(px, py):
        return nd.map_coordinates(zh, [np.atleast_1d((py - hy[0]) / (hy[1] - hy[0])), np.atleast_1d((px - hx[0]) / (hx[1] - hx[0]))], order=1)
    az = np.radians(np.arange(0, 360, 2.0)); ring = z_at(SX + 700 * np.sin(az), SY + 700 * np.cos(az))
    peaks = sorted([i for i in range(len(az)) if ring[i] >= ring[i-1] and ring[i] >= ring[(i+1) % len(az)]], key=lambda i: -ring[i])
    ridges = []
    for i in peaks:
        if all(abs(((az[i] - az[j]) + np.pi) % (2 * np.pi) - np.pi) > np.radians(50) for j in ridges): ridges.append(i)
        if len(ridges) == 4: break
    recon = np.full_like(zh, -1e9)
    for i in ridges:
        ddx, ddy = np.sin(az[i]), np.cos(az[i]); ang = np.clip(np.degrees(np.arctan((top - ring[i]) / 700.0)), 30.0, 52.0)
        along = np.maximum((HX - SX) * ddx + (HY - SY) * ddy, 0.0); across = np.abs(-(HX - SX) * ddy + (HY - SY) * ddx)
        recon = np.maximum(recon, top - along * np.tan(np.radians(ang)) - across * np.tan(np.radians(58.0)))
    rr = np.hypot(HX - SX, HY - SY); wr = np.clip(1.0 - rr / 1600.0, 0, 1) ** 1.5
    zh = zh + np.maximum(recon - zh, 0.0) * wr
    print(f"{name}: data summit {z[iy0:iy1+1, ix0:ix1+1].max():.0f} m -> {top:.0f} m, aretes at " + ", ".join(f"{np.degrees(az[i]):.0f}" for i in ridges) + " deg")
    # fall-line erosion: ribs and couloirs of 10-25 m on the steep faces
    detail = streaks(zh, hdx, hdy, ((2.5, 0.7), (6.0, 0.8), (14.0, 0.6)))
    sl0, _ = analysis(zh, hdx, hdy)
    zh = zh + detail * (0.8 + 9.0 * np.clip((sl0 - 0.25) / 0.35, 0, 1))
    sl_h, cv_h = analysis(zh, hdx, hdy, smooth=3.0)
    out.update({f"h{hi}_z": zh, f"h{hi}_x": hx, f"h{hi}_y": hy, f"h{hi}_slope": sl_h, f"h{hi}_conv": cv_h,
                f"h{hi}_flow": nd.zoom(flow[iy0:iy1+1, ix0:ix1+1], Z, order=1)[:zh.shape[0], :zh.shape[1]],
                f"h{hi}_streak": np.tanh(detail / 2.0) * 0.5 + 0.5})
out["windows"] = np.array(windows); out["hero_names"] = np.array([h[0] for h in HEROES])
np.savez_compressed('khumbu_processed.npz', **{k: (v.astype(np.float32) if isinstance(v, np.ndarray) and v.dtype == np.float64 else v) for k, v in out.items()})
print(f"done {time.time()-t0:.1f}s")
