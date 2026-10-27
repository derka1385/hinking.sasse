"""Pre-tiles the site's grain.png at the Retina scale and lists the CSS animation's shift per frame.
Blender's bundled python: grain.py <grain.png> <out dir> <frames> <fps>"""
import sys, os, json, math
import numpy as np
import OpenImageIO as oiio
src, out, nfr, fps = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.makedirs(out, exist_ok=True)
tile = oiio.ImageBufAlgo.resize(oiio.ImageBuf(src), roi=oiio.ROI(0, 512, 0, 512, 0, 1, 0, 1))   # 1 CSS px = 2 device px
a = tile.get_pixels(oiio.FLOAT)[:, :, 0]
big = np.tile(a, (4, 7))                       # 3584 x 2048: periodic, covers 3024 x 1964
spec = oiio.ImageSpec(big.shape[1], big.shape[0], 1, oiio.UINT8)
buf = oiio.ImageBuf(spec); buf.set_pixels(oiio.ROI(0, big.shape[1], 0, big.shape[0], 0, 1, 0, 1), big[:, :, None].astype(np.float32))
buf.write(os.path.join(out, 'grain_tiled.png'))
# .intro-grain { inset: -100%; animation: grain 1.2s steps(6) infinite } -- the timing function applies per keyframe interval
K = [(0, 0), (-7, 4), (5, -9), (-3, 8), (9, 2), (0, 0)]
W, H = 1512, 982
shift = []
for f in range(nfr):
    tau = (f / fps) % 1.2
    j = min(int(tau / 0.24), 4)
    u = math.floor(((tau - 0.24 * j) / 0.24) * 6) / 6
    tx = K[j][0] + (K[j + 1][0] - K[j][0]) * u
    ty = K[j][1] + (K[j + 1][1] - K[j][1]) * u
    x, y = (tx / 100) * 3 * W * 2, (ty / 100) * 3 * H * 2           # device px
    shift.append([round(x % 512, 2), round((-y) % 512, 2)])          # CSS y points down, the compositor's up
json.dump(shift, open(os.path.join(out, 'grain_shift.json'), 'w'))
print('grain', big.shape, len(shift))
