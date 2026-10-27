"""Turn the live intro's raymarched world into meshes, sampling its own shader on the GPU (gpu.mjs).

python mesh.py <data dir>      (needs numpy + scikit-image; writes <data dir>/terrain.npz, ground.npz, climber.npz)

Level of detail follows the site: a point is meshed as finely as the site ever shows it, i.e. from the
closest the scroll camera gets to it while it is on screen. Levels step by sqrt(2) in cell size; each
level is sampled in a narrow band of 32^3-sample blocks around the surface and cut to its own range.
"""
import json, math, os, subprocess, sys, glob
import numpy as np
from skimage.measure import marching_cubes

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(sys.argv[1])
U = 0.0015                    # metres of detail per metre of distance: the site's pixel (~0.001 rad) x1.5
LEVELS = [0.25 * math.sqrt(2) ** k for k in range(11)]   # 0.25 m ... 8 m
OVERLAP = 0.12                # in level steps: neighbouring levels overlap a little, so no cracks show
BOX_O = np.array([-2400.0, -250.0, -1700.0])   # everything that is not plain valley floor
BOX_E = np.array([2000.0, 1450.0, 700.0])
world = json.load(open(os.path.join(HERE, 'intro_world.json')))


def gpu(jobs):
    for j in jobs:                                   # stale slabs from an earlier run would be read back
        for old in glob.glob(os.path.join(DATA, j['name'] + '.[0-9dm]*')) + glob.glob(os.path.join(DATA, j['name'] + '.attr.[0-9]*')):
            if not old.endswith(('.pts', '.blk')):
                os.remove(old)
    path = os.path.join(DATA, 'jobs.json')
    json.dump(jobs, open(path, 'w'))
    subprocess.run(['node', os.path.join(HERE, 'gpu.mjs'), path, DATA], check=True)


def slabs(prefix):
    return np.concatenate([np.fromfile(f, np.float32) for f in sorted(glob.glob(os.path.join(DATA, prefix + '.[0-9]*')))])


def points(name, v):
    v.astype(np.float32).tofile(os.path.join(DATA, name + '.pts'))
    gpu([{'kind': 'points', 'name': name, 'n': int(len(v)), 'u': U}])
    parts = sorted(glob.glob(os.path.join(DATA, name + '.attr.[0-9]*')))
    return np.concatenate([np.fromfile(f, np.float32) for f in parts]).reshape(-1, 20)


def weld(verts, faces, q=1e-4):
    key = np.round(verts / q).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    faces = inv.reshape(-1)[faces]
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    return verts[first], faces


def mc(vol, origin, cell):
    """vol indexed [z][y][x] as sampled; returns world vertices (x, y, z) and outward-facing triangles."""
    v, f, _, _ = marching_cubes(np.ascontiguousarray(vol.transpose(2, 1, 0)), 0.0, spacing=(cell,) * 3,
                                gradient_direction='ascent', allow_degenerate=False)
    return v.astype(np.float64) + origin, f


def level_of(lod):
    c = lod * U / 0.75
    return 2.0 * np.log2(np.maximum(c, 1e-6) / LEVELS[0])


def coarse():
    c = 16.0
    n = np.ceil((BOX_E - BOX_O) / c).astype(int) + 1
    n[0] = (n[0] + 3) // 4 * 4
    gpu([{'kind': 'grid', 'name': 'coarse', 'O': BOX_O.tolist(), 'A': [c, 0, 0], 'B': [0, c, 0], 'C': [0, 0, c],
          'nx': int(n[0]), 'ny': int(n[1]), 'nz': int(n[2]), 'u': U}])
    vol = slabs('coarse').reshape(n[2], n[1], n[0])
    v, f = mc(vol, BOX_O, c)
    at = points('coarse', v)
    return v, f, at


def level_mesh(k, cv, cf, cat):
    c = LEVELS[k]
    stride = 31 * c
    lam = level_of(cat[:, 3])[cf].min(1)          # finest need among a coarse triangle's corners
    near = cat[:, 12][cf].min(1) < 120.0           # rock, or the foot of it
    lo, hi = (-1e9 if k == 0 else k - 0.5 - OVERLAP - 0.6), (1e9 if k == len(LEVELS) - 1 else k + 0.5 + OVERLAP + 0.6)
    sel = near & (lam > lo) & (lam < hi)
    if not sel.any():
        return None
    tri = cv[cf[sel]]
    m = 24.0
    bmin = np.floor((tri.min(1) - m - BOX_O) / stride).astype(int)
    bmax = np.floor((tri.max(1) + m - BOX_O) / stride).astype(int)
    blocks = set()
    for a, b in zip(bmin, bmax):
        for i in range(a[0], b[0] + 1):
            for j in range(a[1], b[1] + 1):
                for l in range(a[2], b[2] + 1):
                    blocks.add((i, j, l))
    blocks = np.array(sorted(blocks))
    org = BOX_O + blocks * stride
    name = f'lv{k:02d}'
    org.astype(np.float32).tofile(os.path.join(DATA, name + '.blk'))
    print(f'level {k} cell {c:.3f} m: {len(blocks)} blocks, {len(blocks) * 32768 / 1e6:.0f} M samples', flush=True)
    gpu([{'kind': 'blocks', 'name': name, 'n': int(len(blocks)), 'c': c, 'u': U}])
    vs, fs, base = [], [], 0
    files = sorted(glob.glob(os.path.join(DATA, name + '.[0-9]*')))
    b0 = 0
    for fpath in files:
        a = np.fromfile(fpath, np.float32).reshape(1024, -1, 4)     # [j + 32k][8 texels per block][4]
        nb = a.shape[1] // 8
        a = a.reshape(32, 32, nb, 32).transpose(2, 0, 1, 3)       # [block][k][j][i]
        for bi in range(nb):
            vol = a[bi]
            if vol.min() > 0 or vol.max() < 0:
                continue
            v, f = mc(vol, org[b0 + bi], c)
            vs.append(v); fs.append(f + base); base += len(v)
        b0 += nb
    if not vs:
        return None
    v, f = weld(np.concatenate(vs), np.concatenate(fs))
    return v, f


def cut(v, f, at, k):
    lam = level_of(at[:, 3])[f].mean(1)
    keep = at[:, 12][f].min(1) < 60.0                                # plain valley floor comes from the heightfield
    if k > 0:
        keep &= lam >= k - 0.5 - OVERLAP
    if k < len(LEVELS) - 1:
        keep &= lam < k + 0.5 + OVERLAP
    f = f[keep]
    used = np.unique(f)
    remap = np.full(len(v), -1); remap[used] = np.arange(len(used))
    return v[used], remap[f], at[used]


def terrain():
    cv, cf, cat = coarse()
    print('coarse', len(cv), 'verts; lod range', cat[:, 3].min(), cat[:, 3].max(), flush=True)
    parts = []
    for k in range(len(LEVELS)):
        r = level_mesh(k, cv, cf, cat)
        if r is None:
            continue
        v, f = r
        at = points(f'lv{k:02d}', v)
        v, f, at = cut(v, f, at, k)
        print(f'  level {k}: {len(v)} verts, {len(f)} tris kept', flush=True)
        parts.append((v, f, at, np.full(len(v), k, np.int8)))
    base, F = 0, []
    for v, f, _, _ in parts:
        F.append(f + base); base += len(v)
    np.savez(os.path.join(DATA, 'terrain.npz'), v=np.concatenate([p[0] for p in parts]).astype(np.float32),
             f=np.concatenate(F).astype(np.int32), at=np.concatenate([p[2] for p in parts]),
             level=np.concatenate([p[3] for p in parts]))


def ground():
    c, x0, z0, nx, nz = 12.0, -4500.0, -4500.0, 752, 751
    gpu([{'kind': 'grid', 'name': 'ground', 'mode': 1, 'O': [x0, 0, z0], 'A': [c, 0, 0], 'B': [0, 0, c], 'C': [0, 0, 0],
          'nx': nx, 'ny': nz, 'nz': 1, 'u': U}])
    h = slabs('ground').reshape(nz, nx)
    xs, zs = x0 + c * np.arange(nx), z0 + c * np.arange(nz)
    X, Z = np.meshgrid(xs, zs)
    v = np.stack([X, h, Z], -1).reshape(-1, 3)
    at = points('groundpts', v)
    np.savez(os.path.join(DATA, 'ground.npz'), v=v.astype(np.float32), nx=nx, nz=nz, at=at)


def climber():
    cl = np.array(world['CLIMBER'])
    c = 0.01
    O = cl + np.array([-0.46, -0.1, -1.2])
    n = np.array([92, 260, 160])
    gpu([{'kind': 'climber', 'name': 'climber', 'O': O.tolist(), 'A': [c, 0, 0], 'B': [0, c, 0], 'C': [0, 0, c],
          'nx': int(n[0]), 'ny': int(n[1]), 'nz': int(n[2])}])
    d = slabs('climber.d').reshape(n[2], n[1], n[0])
    m = slabs('climber.m').reshape(n[2], n[1], n[0])
    v, f = mc(d, O, c)
    idx = np.clip(np.round((v - O) / c).astype(int), 0, n - 1)
    mat = m[idx[:, 2], idx[:, 1], idx[:, 0]]
    np.savez(os.path.join(DATA, 'climber.npz'), v=v.astype(np.float32), f=f.astype(np.int32), mat=mat.astype(np.int8))
    print('climber', len(v), 'verts', flush=True)


def reattr():
    """Recomputes the per-vertex shading inputs of existing meshes (after a sampler change), keeping the geometry."""
    for fname, name in (('terrain.npz', 'terrain_all'), ('ground.npz', 'groundpts')):
        d = dict(np.load(os.path.join(DATA, fname)))
        d['at'] = points(name, d['v'].astype(np.float64))
        np.savez(os.path.join(DATA, fname), **d)
        print(fname, d['at'].shape, flush=True)


def couloir():
    """The site fills the couloir with snow beyond 1400 m and carves it below 900 m. For vertices near it, find the
    surface the site draws from far away (along the face normal) and the snow band it paints there."""
    d = dict(np.load(os.path.join(DATA, 'terrain.npz')))
    v = d['v'].astype(np.float64)
    S, NFv, TY = (np.array(world[k]) for k in ('SUMMIT', 'NF', 'TY'))
    q = v - S
    CD = np.array([-0.4472136, 0.8944272])
    uu, vv = q[:, 0] - world['CU'], q @ TY - world['CV']
    along, across = uu * CD[0] + vv * CD[1], uu * CD[1] - vv * CD[0]
    near = (np.abs(across) < 90) & (along > -420) & (along < 620) & (np.abs(q @ NFv) < 150)   # generous: cw is exact below
    idx = np.where(near)[0]
    v[idx].astype(np.float32).tofile(os.path.join(DATA, 'coul.pts'))
    gpu([{'kind': 'couloir', 'name': 'coul', 'n': int(len(idx)), 'u': U}])
    far = np.fromfile(os.path.join(DATA, 'coul.far'), np.float32).reshape(-1, 4)
    sfar, cw, band = far[:, 0], far[:, 1], far[:, 2]
    wgt = np.clip((20.0 - cw) / 8.0, 0, 1); wgt = wgt * wgt * (3 - 2 * wgt)       # carved zone -> 1, fades out by cw = 20 m
    wgt[sfar == 0] = 0
    off = np.zeros(len(v), np.float32); off[idx] = sfar * wgt
    bnd = np.zeros(len(v), np.float32); bnd[idx] = band
    # AO the site computes from 1400 m on that filled surface, blended the same way
    moved = idx[wgt > 0]
    at = points('coulfar', v[moved] + NFv * off[moved, None])
    ao = d['at'][:, 15].copy()
    wm = wgt[wgt > 0]
    ao[moved] = ao[moved] * (1 - wm) + at[:, 15] * wm
    d['far_offset'], d['couloir_band'], d['ao_far'] = off, bnd, ao
    np.savez(os.path.join(DATA, 'terrain.npz'), **d)
    print('couloir: %d vertices move, max %.1f m' % ((off != 0).sum(), np.abs(off).max()), flush=True)


if __name__ == '__main__':
    what = sys.argv[2:] or ['terrain', 'ground', 'climber']
    for w in what:
        globals()[w]()
