"""Download the Copernicus DEM GLO-30 tile N27 E086 (Khumbu), decode it, crop the region, denoise and sharpen.
Writes khumbu_crop.npy, khumbu_xs.npy, khumbu_ys.npy, khumbu_marks.json and khumbu_sharp.npy next to this file.
Data: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under
COPERNICUS by the European Union and ESA. Run with any Python that has numpy, scipy and tifffile."""
import json, math, urllib.request, zlib
from pathlib import Path
import numpy as np, tifffile
from scipy import ndimage as nd
HERE = Path(__file__).resolve().parent
TIF = HERE / "cop_N27_E086.tif"
URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N27_00_E086_00_DEM/Copernicus_DSM_COG_10_N27_00_E086_00_DEM.tif"
if not TIF.exists(): urllib.request.urlretrieve(URL, TIF)
with tifffile.TiffFile(TIF) as t:            # DEFLATE + floating-point predictor, decoded by hand (no imagecodecs)
    p = t.pages[0]; tw, th, W, H = p.tilewidth, p.tilelength, p.imagewidth, p.imagelength
    full = np.zeros((H, W), np.float32); nx = (W + tw - 1) // tw
    for i, (o, c) in enumerate(zip(p.dataoffsets, p.databytecounts)):
        t.filehandle.seek(o); b = np.frombuffer(zlib.decompress(t.filehandle.read(c)), np.uint8).reshape(th, tw * 4)
        b = np.cumsum(b, axis=1, dtype=np.uint8)
        v = np.ascontiguousarray(b.reshape(th, 4, tw)[:, ::-1, :].transpose(0, 2, 1)).view('<f4').reshape(th, tw)
        ty, tx = divmod(i, nx); y0, x0 = ty * th, tx * tw
        full[y0:y0 + th, x0:x0 + tw] = v[:min(th, H - y0), :min(tw, W - x0)]
LON0, LON1, LAT0, LAT1 = 86.66, 86.98, 27.76, 28.0
c0, c1 = round((LON0 - 86) * 3600), round((LON1 - 86) * 3600); r0, r1 = round((28 - LAT1) * 3600), round((28 - LAT0) * 3600)
crop = full[r0:r1 + 1, c0:c1 + 1].astype(np.float32); Hc, Wc = crop.shape
lat0, lon0 = 27.8613, 86.8614                 # origin: Ama Dablam's summit
mx, my = 111320.0 * math.cos(math.radians(27.88)) / 3600.0, 110574.0 / 3600.0
xs = ((c0 + np.arange(Wc)) / 3600.0 + 86 - lon0) * 3600 * mx; ys = ((28 - (r0 + np.arange(Hc)) / 3600.0) - lat0) * 3600 * my
np.save(HERE / 'khumbu_crop.npy', crop); np.save(HERE / 'khumbu_xs.npy', xs.astype(np.float32)); np.save(HERE / 'khumbu_ys.npy', ys.astype(np.float32))
def pos(lat, lon, r=8):
    y, x = round((28 - lat) * 3600) - r0, round((lon - 86) * 3600) - c0; w = crop[max(0, y-r):y+r+1, max(0, x-r):x+r+1]
    iy, ix = np.unravel_index(np.argmax(w), w.shape); yy, xx = max(0, y-r) + iy, max(0, x-r) + ix
    return [float(xs[xx]), float(ys[yy]), float(crop[yy, xx])]
marks = {n: pos(la, lo) for n, la, lo in [("Everest", 27.9881, 86.9250), ("Lhotse", 27.9617, 86.9333), ("Nuptse", 27.9669, 86.8864),
         ("Ama Dablam", 27.8613, 86.8614), ("Island Peak", 27.9224, 86.9361), ("Thamserku", 27.7867, 86.7869), ("Kangtega", 27.8, 86.825),
         ("Taboche", 27.9036, 86.7925), ("Cholatse", 27.915, 86.7667)]}
for n, la, lo in [("Tengboche", 27.836, 86.764), ("Pangboche", 27.858, 86.794), ("Namche Bazaar", 27.8046, 86.7133), ("Dingboche", 27.892, 86.831)]:
    y, x = round((28 - la) * 3600) - r0, round((lo - 86) * 3600) - c0; marks[n] = [float(xs[x]), float(ys[y]), float(crop[y, x])]
json.dump(marks, open(HERE / 'khumbu_marks.json', 'w'), indent=1)
# radar speckle out (twice a 3x3 median; a light blur on gentle ground), then multi-scale unsharp mask
z0 = crop.astype(np.float64); med = nd.median_filter(nd.median_filter(z0, size=3), size=3)
gy, gx = np.gradient(med, 30.72, 27.34); w = np.clip((35.0 - np.degrees(np.arctan(np.hypot(gx, gy)))) / 20.0, 0, 1)
z1 = w * nd.gaussian_filter(med, 1.0) + (1 - w) * med
z2 = z1 + 0.8 * (z1 - nd.gaussian_filter(z1, 2.5)) + 0.4 * (z1 - nd.gaussian_filter(z1, 8.0))
np.save(HERE / 'khumbu_sharp.npy', z2.astype(np.float32)); print("ok", crop.shape)
