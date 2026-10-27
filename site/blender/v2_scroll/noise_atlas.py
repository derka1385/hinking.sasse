"""The site's 128^3 noise volume as a 2D atlas Blender can sample: 128 slices of 130x130 (1-texel wrap border
for bilinear filtering), 16 columns x 8 rows, bottom-up rows. Blender's python: noise_atlas.py <noise128.u8> <out.png>"""
import sys
import numpy as np
import OpenImageIO as oiio
vol = np.fromfile(sys.argv[1], np.uint8).reshape(128, 128, 128)        # [z][y][x], y = 0 at the bottom
pad = np.pad(vol, ((0, 0), (1, 1), (1, 1)), mode='wrap')               # 130 x 130 per slice
atlas = np.zeros((8 * 130, 16 * 130), np.uint8)                        # bottom-up
for z in range(128):
    r, c = divmod(z, 16)
    atlas[r * 130:(r + 1) * 130, c * 130:(c + 1) * 130] = pad[z]
buf = oiio.ImageBuf(oiio.ImageSpec(atlas.shape[1], atlas.shape[0], 1, oiio.UINT8))
buf.set_pixels(oiio.ROI(0, atlas.shape[1], 0, atlas.shape[0], 0, 1, 0, 1), atlas[::-1, :, None].copy())   # files are top-down
buf.write(sys.argv[2])
print('atlas', atlas.shape, 'mean', atlas.mean() / 255)
