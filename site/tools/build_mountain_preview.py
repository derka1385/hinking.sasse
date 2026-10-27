"""Bake one continuous, variable-density terrain from the project's real DEM.

No cones, appended summit, or separate valley floor: all vertices sample the
same Copernicus GLO-30 elevation field. Run with the bundled NumPy runtime.
"""
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/khumbu')
OUT = ROOT / 'assets' / 'mountain'
OUT.mkdir(parents=True, exist_ok=True)
processed = np.load(SOURCE / 'khumbu_processed.npz')
height = processed['z'].astype(np.float32)
source_x = np.load(SOURCE / 'khumbu_xs.npy')
source_north = np.load(SOURCE / 'khumbu_ys.npy')

# The summit/near faces receive the native data's resolution. Outside them,
# spacing increases smoothly rather than placing a high-detail mesh on a slab.
def axis(lo, hi, inner_lo, inner_hi):
    left = np.linspace(lo, inner_lo, round((inner_lo-lo)/95)+1)[:-1]
    middle = np.linspace(inner_lo, inner_hi, round((inner_hi-inner_lo)/16)+1)
    right = np.linspace(inner_hi, hi, round((hi-inner_hi)/95)+1)[1:]
    return np.concatenate((left, middle, right)).astype(np.float32)

xs = axis(-12500, 10500, -4200, 4200)
zs = axis(-15000, 10500, -4000, 4200)  # z points south; north is negative z.
X, Z = np.meshgrid(xs, zs)
u = np.clip(np.interp(X, source_x, np.arange(len(source_x))), 0, height.shape[1]-1.001)
v = np.clip(np.interp(Z, -source_north, np.arange(len(source_north))), 0, height.shape[0]-1.001)
ix, iy = u.astype(int), v.astype(int)
fx, fy = u-ix, v-iy
Y = (height[iy,ix]*(1-fx)*(1-fy) + height[iy,ix+1]*fx*(1-fy)
     + height[iy+1,ix]*(1-fx)*fy + height[iy+1,ix+1]*fx*fy).astype(np.float32)

# The previously processed hero data follows the DEM's own ridge directions and
# fall lines. Blend that higher-detail relief into this same surface, so there
# is no inserted summit object, seam, rectangular pedestal or separate floor.
hx, hz, hero = processed['h0_x'], -processed['h0_y'], processed['h0_z']
hu = np.clip(np.interp(X, hx, np.arange(len(hx))), 0, len(hx)-1.001)
hv = np.clip(np.interp(Z, hz, np.arange(len(hz))), 0, len(hz)-1.001)
hix, hiy = hu.astype(int), hv.astype(int)
hfx, hfy = hu-hix, hv-hiy
detail = (hero[hiy,hix]*(1-hfx)*(1-hfy)+hero[hiy,hix+1]*hfx*(1-hfy)
          + hero[hiy+1,hix]*(1-hfx)*hfy+hero[hiy+1,hix+1]*hfx*hfy)
blend = np.clip((3400-np.maximum(np.abs(X),np.abs(Z)))/650,0,1)
blend = blend*blend*(3-2*blend)
Y = (Y*(1-blend) + detail*blend).astype(np.float32)

# Small-scale radar noise is not amplified into spikes. Preserve the actual
# crests and gullies, then derive normals and concavity from physical metres.
gy, gx = np.gradient(Y, zs, xs)
N = np.stack((-gx, np.ones_like(Y), -gy), -1)
N /= np.linalg.norm(N, axis=-1, keepdims=True)
lap = np.gradient(gx, xs, axis=1) + np.gradient(gy, zs, axis=0)
concavity = np.clip(lap * 38, -1, 1)

# Eight bytes per vertex: height (1/7 metre), signed normal x/z, concavity.
# Horizontal positions come from the shared axes; normal y is reconstructed.
# Quantisation error is <8 cm, far below the source's 30 m sample spacing.
vertex = np.empty((*Y.shape, 4), dtype='<u2')
vertex[...,0] = np.round(Y*7).astype('<u2')
vertex[...,1] = np.round(N[...,0]*32767).astype('<i2').view('<u2')
vertex[...,2] = np.round(N[...,2]*32767).astype('<i2').view('<u2')
vertex[...,3] = np.round(concavity*32767).astype('<i2').view('<u2')
vertex.tofile(OUT / 'khumbu.bin')
meta = {
    'columns': len(xs), 'rows': len(zs), 'encoding': 'height7-normalxz-concavity-i16',
    'x': (xs/1000).tolist(), 'z': (zs/1000).tolist(),
    'summit': [-0.055759, 3.261383, -0.040544],
    'source': 'Copernicus DEM GLO-30', 'mountain': 'Ama Dablam',
    'sourceResolutionMetres': 30, 'datumMetres': 3400,
    'processing': 'Denoised DEM; locally sharpened aretes and fall-line erosion, blended continuously into the valley.',
    'credits': 'Copernicus DEM © DLR e.V. 2010–2014, © Airbus Defence and Space GmbH 2014–2018. Provided under COPERNICUS by the European Union and ESA.',
}
(OUT / 'khumbu.json').write_text(json.dumps(meta, separators=(',', ':')))
print(json.dumps({'grid': [len(xs),len(zs)], 'vertices':Y.size,
                  'triangles':(len(xs)-1)*(len(zs)-1)*2,
                  'bytes':vertex.nbytes, 'heightRange': [float(Y.min()),float(Y.max())]}))
