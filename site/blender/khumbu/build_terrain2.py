import bpy
import numpy as np
D = '/Users/petrinolann/Coding/sasse-mountaineering/site/blender/khumbu/'
d = np.load(D + 'khumbu_processed.npz')
col = bpy.data.collections["08 • REAL TERRAIN — Khumbu (Copernicus DEM 30 m)"]
for o in list(col.objects):
    if o.type == 'MESH': bpy.data.objects.remove(o, do_unlink=True)
for m in list(bpy.data.meshes):
    if m.users == 0: bpy.data.meshes.remove(m)

def grid_mesh(name, z, xs, ys, fields, skip=None, skirt=0.0):
    H, W = z.shape
    X, Y = np.meshgrid(xs, ys)
    verts = np.stack([X.ravel(), Y.ravel(), z.ravel()], 1)
    idx = np.arange(H * W).reshape(H, W)
    q = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], -1)
    keep = np.ones((H - 1, W - 1), bool)
    for (r0, r1), (c0, c1) in (skip or []):
        keep[r0:r1, c0:c1] = False
    quads = q[keep].reshape(-1, 4)
    fields = {k: v.ravel() for k, v in fields.items()}
    if skirt:
        # a wall hanging from the border, hiding any crack against the backdrop
        ring = np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])
        n0 = len(verts)
        low = verts[ring].copy(); low[:, 2] -= skirt
        verts = np.concatenate([verts, low])
        for k in fields: fields[k] = np.concatenate([fields[k], fields[k][ring]])
        a = ring; b = np.roll(ring, -1); la = n0 + np.arange(len(ring)); lb = np.roll(la, -1)
        quads = np.concatenate([quads, np.stack([a, la, lb, b], -1)])
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts)); me.vertices.foreach_set('co', verts.astype(np.float32).ravel())
    me.loops.add(quads.size); me.loops.foreach_set('vertex_index', quads.astype(np.int32).ravel())
    me.polygons.add(len(quads)); me.polygons.foreach_set('loop_start', np.arange(0, quads.size, 4, dtype=np.int32))
    me.update(calc_edges=True)
    for k, v in fields.items():
        at = me.attributes.new(k, 'FLOAT', 'POINT'); at.data.foreach_set('value', v.astype(np.float32))
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me); col.objects.link(ob)
    ob["source"] = "Copernicus DEM GLO-30 (N27 E086) © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the EU and ESA; denoised, sharpened, hero eroded"
    return ob

wins = [[int(v) for v in w] for w in d['windows']]
z = d['z']
back = grid_mesh("Khumbu • backdrop 30 m", z, d['xs'], d['ys'],
                 {"slope": d['slope'], "convexity": d['conv'], "runoff": d['flow'], "streak": d['streak_b']},
                 skip=[((iy0, iy1), (ix0, ix1)) for ix0, ix1, iy0, iy1 in wins])
heroes = []
for hi, name in enumerate(d['hero_names']):
    heroes.append(grid_mesh(f"{name} • hero 10 m", d[f'h{hi}_z'], d[f'h{hi}_x'], d[f'h{hi}_y'],
                  {"slope": d[f'h{hi}_slope'], "convexity": d[f'h{hi}_conv'], "runoff": d[f'h{hi}_flow'], "streak": d[f'h{hi}_streak']}, skirt=40.0))
# ---- material
mat = bpy.data.materials.get("Himalaya • rock and snow") or bpy.data.materials.new("Himalaya • rock and snow")
mat.use_nodes = True; nt = mat.node_tree; N, L = nt.nodes, nt.links; N.clear()
def attr(name):
    a = N.new('ShaderNodeAttribute'); a.attribute_type = 'GEOMETRY'; a.attribute_name = name; return a.outputs['Fac']
geo = N.new('ShaderNodeNewGeometry')
P = N.new('ShaderNodeSeparateXYZ'); L.new(geo.outputs['Position'], P.inputs[0])
def noise(scale, detail=4.0, rough=0.55):
    n = N.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail; n.inputs['Roughness'].default_value = rough
    L.new(geo.outputs['Position'], n.inputs['Vector']); return n.outputs['Fac']
def mr(v, a, b, lo=0.0, hi=1.0, smooth=True):
    m = N.new('ShaderNodeMapRange'); m.interpolation_type = 'SMOOTHSTEP' if smooth else 'LINEAR'; m.clamp = True
    (L.new(v, m.inputs['Value']) if not isinstance(v, (int, float)) else setattr(m.inputs['Value'], 'default_value', v))
    for s, x in (('From Min', a), ('From Max', b), ('To Min', lo), ('To Max', hi)):
        if isinstance(x, (int, float)): m.inputs[s].default_value = x
        else: L.new(x, m.inputs[s])
    return m.outputs['Result']
def op(o, a, b=None):
    m = N.new('ShaderNodeMath'); m.operation = o; m.use_clamp = o in ('MULTIPLY_ADD',)
    for i, v in enumerate((a, b)):
        if v is None: continue
        if isinstance(v, (int, float)): m.inputs[i].default_value = v
        else: L.new(v, m.inputs[i])
    return m.outputs[0]
def mix(f, a, b):
    m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'
    (L.new(f, m.inputs['Factor']) if not isinstance(f, (int, float)) else setattr(m.inputs['Factor'], 'default_value', f))
    for s, v in ((m.inputs[6], a), (m.inputs[7], b)):
        if isinstance(v, tuple): s.default_value = v
        else: L.new(v, s)
    return m.outputs[2]
Z = P.outputs['Z']; slope, conv, runoff, streak = attr('slope'), attr('convexity'), attr('runoff'), attr('streak')
nb, nm, nf = noise(1 / 2600.0), noise(1 / 240.0), noise(1 / 22.0, 6.0, 0.6)
# snow as it lies on Himalayan faces: white above a ragged snowline; rock shows only as lines down the
# fall line (flutes and ribs), as horizontal strata on steep faces, and on near-vertical walls; below the
# snowline, rock with snow kept in couloirs and on flats. No slope-threshold blobs.
snowline = op('ADD', 5050.0, op('MULTIPLY', op('SUBTRACT', nb, 0.5), 600.0))
alt = mr(op('SUBTRACT', Z, snowline), -120.0, 280.0)
steep = mr(slope, 0.42, 0.62)
lines = op('MULTIPLY', mr(slope, 0.32, 0.55), op('SUBTRACT', 1.0, mr(streak, 0.26, 0.40)))
band = N.new('ShaderNodeMath'); band.operation = 'SINE'
L.new(op('ADD', op('ADD', op('MULTIPLY', Z, 1.0 / 70.0), op('MULTIPLY', P.outputs['X'], 0.35 / 70.0)), op('ADD', op('MULTIPLY', nb, 10.0), op('MULTIPLY', nm, 3.0))), band.inputs[0])   # tilted, warped strata
strata = op('MULTIPLY', op('MULTIPLY', mr(band.outputs[0], 0.86, 0.96), 0.75), op('MULTIPLY', steep, op('MULTIPLY', mr(nm, 0.5, 0.62), mr(nf, 0.3, 0.5))))   # thin, broken, only here and there
wall = mr(slope, 0.78, 0.9)
bare = op('MAXIMUM', op('MAXIMUM', lines, strata), wall)
high = op('MULTIPLY', alt, op('SUBTRACT', 1.0, bare))
flats = op('MULTIPLY', mr(slope, 0.3, 0.18), mr(nf, 0.45, 0.6))
low = op('MULTIPLY', op('SUBTRACT', 1.0, alt), op('MAXIMUM', op('MULTIPLY', mr(runoff, 0.5, 0.8), mr(Z, 4300.0, 4800.0)), op('MULTIPLY', flats, mr(Z, 4500.0, 5000.0))))
snow = op('MINIMUM', op('MAXIMUM', high, low), 1.0)
glacier = op('MULTIPLY', op('MULTIPLY', mr(slope, 0.2, 0.08), mr(runoff, 0.5, 0.75)), mr(Z, 4700.0, 5000.0))
debris = op('MULTIPLY', glacier, mr(Z, 5350.0, 4900.0))                                           # lower tongues under rubble
rock = mix(mr(nm, 0.35, 0.7), (0.036, 0.031, 0.027, 1), (0.10, 0.085, 0.07, 1))
rock = mix(mr(nf, 0.35, 0.7), rock, (0.055, 0.05, 0.046, 1))
rock = mix(op('MAXIMUM', mr(conv, -0.2, -0.8), mr(streak, 0.4, 0.2)), rock, op('MULTIPLY', 1.0, 0.0) and (0.045, 0.042, 0.04, 1))    # hollows darker
lowland = op('MULTIPLY', mr(Z, 4600.0, 4200.0), mr(slope, 0.45, 0.25))
ground = mix(lowland, rock, mix(mr(nm, 0.3, 0.7), (0.085, 0.072, 0.045, 1), (0.12, 0.105, 0.075, 1)))
ground = mix(debris, ground, mix(mr(nf, 0.3, 0.7), (0.12, 0.112, 0.10, 1), (0.19, 0.18, 0.165, 1)))
ice = mix(mr(nm, 0.3, 0.7), (0.62, 0.68, 0.74, 1), (0.74, 0.78, 0.83, 1))
ground = mix(op('MULTIPLY', glacier, op('SUBTRACT', 1.0, debris)), ground, ice)
snowc = mix(mr(nf, 0.2, 0.8), (0.80, 0.82, 0.86, 1), (0.88, 0.89, 0.92, 1))
base = mix(snow, ground, snowc)
bsdf = N.new('ShaderNodeBsdfPrincipled')
L.new(base, bsdf.inputs['Base Color'])
L.new(mr(snow, 0.0, 1.0, 0.9, 0.5, False), bsdf.inputs['Roughness'])
# rock micro-relief: ridged cracks and ribs at 3-30 m, flattened under snow
def ridged(scale):
    n = N.new('ShaderNodeTexNoise'); n.noise_type = 'RIDGED_MULTIFRACTAL'; n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = 6.0; n.inputs['Roughness'].default_value = 0.6; n.inputs['Lacunarity'].default_value = 2.2
    L.new(geo.outputs['Position'], n.inputs['Vector']); return n.outputs['Fac']
relief = op('ADD', op('MULTIPLY', ridged(1 / 28.0), 1.0), op('ADD', op('MULTIPLY', ridged(1 / 7.0), 0.45), op('MULTIPLY', nf, 0.5)))
relief = op('MULTIPLY', relief, op('SUBTRACT', 1.0, op('MULTIPLY', snow, 0.8)))
bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 1.0; bump.inputs['Distance'].default_value = 12.0
L.new(relief, bump.inputs['Height']); L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
out = N.new('ShaderNodeOutputMaterial')
cam = N.new('ShaderNodeCameraData'); cam.label = 'haze camera'
hk = op('MULTIPLY', cam.outputs['View Distance'], -1.0 / 90000.0)
hz = op('SUBTRACT', 1.0, op('EXPONENT', hk))
em = N.new('ShaderNodeEmission'); em.label = 'haze air'; em.inputs['Color'].default_value = (0.50, 0.60, 0.78, 1); em.inputs['Strength'].default_value = 0.22
mx = N.new('ShaderNodeMixShader'); mx.label = 'haze mix'
L.new(hz, mx.inputs[0]); L.new(bsdf.outputs['BSDF'], mx.inputs[1]); L.new(em.outputs[0], mx.inputs[2])
L.new(mx.outputs[0], out.inputs['Surface'])
for ob in [back] + heroes: ob.data.materials.append(mat)
print("backdrop", len(back.data.vertices), "|", " | ".join(f"{h.name}: {len(h.data.vertices)} verts, top {max(v.co.z for v in h.data.vertices):.0f} m" for h in heroes))
