"""Builds the Blender scene of the live intro (GitHub V2 scroll animation) from mesh.py's output.

/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python build_blend.py -- <data dir> <out.blend> [grain dir]

Frame f shows scroll progress p = (f - 1) / 360. Everything the site computes per pixel is reproduced with
the same formulas: rock and snow albedo (noise terms baked per vertex by the site's own shader), sun,
sky and bounce light, the height fog, ACES + gamma, cold shadows, vignette, the paper whiteout, the
snow streaks (drawn over everything, after the grade, as the site does) and the CSS grain.
Blender coordinates: X = site x, Y = -site z, Z = site y (up). One unit = one metre.
"""
import bpy, json, math, os, sys
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
DATA, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
GRAIN = os.path.abspath(argv[2]) if len(argv) > 2 else None
HERE = os.path.dirname(os.path.abspath(__file__))
world = json.load(open(os.path.join(HERE, 'intro_world.json')))
FR, FPS = world['frames'], world['fps']
NF = len(FR)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
sc = bpy.context.scene
sc.name = 'Intro • scroll (live V2)'


def B(v):
    return Vector((v[0], -v[2], v[1]))


def Bn(a):
    a = np.asarray(a, np.float64)
    return np.stack([a[:, 0], -a[:, 2], a[:, 1]], 1)


# ------------------------------------------------------------------ node helper
class Nodes:
    def __init__(self, tree):
        self.t = tree

    def n(self, kind, **kw):
        node = self.t.nodes.new(kind)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def put(self, sock, val):
        if isinstance(val, bpy.types.NodeSocket):
            self.t.links.new(val, sock)
        elif val is not None:
            sock.default_value = val

    def m(self, op, a, b=None, c=None, clamp=False):
        node = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            self.put(node.inputs[i], v)
        return node.outputs[0]

    def v(self, op, a, b=None, c=None, s=None):
        node = self.n('ShaderNodeVectorMath', operation=op)
        for i, val in enumerate((a, b, c)):
            self.put(node.inputs[i], val)
        if s is not None:
            self.put(node.inputs['Scale'], s)
        return node.outputs[1 if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE') else 0]

    def xyz(self, vec):
        node = self.n('ShaderNodeSeparateXYZ'); self.put(node.inputs[0], vec)
        return node.outputs

    def comb(self, x, y, z):
        node = self.n('ShaderNodeCombineXYZ')
        for i, val in enumerate((x, y, z)):
            self.put(node.inputs[i], val)
        return node.outputs[0]

    def smooth(self, a, b, x):
        node = self.n('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        self.put(node.inputs['Value'], x); node.inputs['From Min'].default_value = a; node.inputs['From Max'].default_value = b
        return node.outputs['Result']

    def mix(self, a, b, t):          # scalar
        return self.m('ADD', a, self.m('MULTIPLY', self.m('SUBTRACT', b, a), t))

    def vmix(self, a, b, t):         # vector, scalar factor
        return self.v('ADD', a, self.v('SCALE', self.v('SUBTRACT', b, a), s=t))

    def prop(self, name, vec=False):
        node = self.n('ShaderNodeAttribute', attribute_type='VIEW_LAYER', attribute_name=name)
        return node.outputs['Vector' if vec else 'Fac']

    def attr(self, name, kind='GEOMETRY'):
        return self.n('ShaderNodeAttribute', attribute_type=kind, attribute_name=name).outputs['Fac']

    def attr8(self, name):
        return self.m('DIVIDE', self.attr(name), 127.0)

    def packed(self, name):
        node = self.n('ShaderNodeAttribute', attribute_type='GEOMETRY', attribute_name=name)
        sep = self.n('ShaderNodeSeparateColor'); self.put(sep.inputs[0], node.outputs['Color'])
        return sep.outputs[0], sep.outputs[1], sep.outputs[2], node.outputs['Alpha']


def group(name, inputs, outputs, kind='ShaderNodeTree'):
    g = bpy.data.node_groups.new(name, kind)
    for n, t in inputs:
        g.interface.new_socket(n, in_out='INPUT', socket_type=t)
    for n, t in outputs:
        g.interface.new_socket(n, in_out='OUTPUT', socket_type=t)
    N = Nodes(g)
    return g, N, N.n('NodeGroupInput').outputs, N.n('NodeGroupOutput').inputs


# ------------------------------------------------------------------ the site's noise, n3(p), sampled from its own 128^3 volume
ATLAS = bpy.data.images.load(os.path.join(HERE, 'noise_atlas.png'))
ATLAS.colorspace_settings.name = 'Non-Color'; ATLAS.pack()


def n3_group():
    # n3(p) = texture(uNoise, p / 16): lattice every unit, 8 texels per cell, trilinear, repeat, no mipmaps
    g, N, I, O = group('Site • n3 noise', [('p', 'NodeSocketVector')], [('n', 'NodeSocketFloat')])
    cx, cy, cz = N.xyz(N.v('SCALE', I['p'], s=8.0))
    fl = lambda a: N.m('FLOOR', a)
    x0, y0, z0 = (fl(N.m('SUBTRACT', c, 0.5)) for c in (cx, cy, cz))
    fx, fy, fz = (N.m('SUBTRACT', N.m('SUBTRACT', c, 0.5), c0) for c, c0 in ((cx, x0), (cy, y0), (cz, z0)))
    wrap = lambda a: N.m('FLOORED_MODULO', a, 128.0)
    xs = (wrap(x0), wrap(N.m('ADD', x0, 1.0)))
    ys = (wrap(y0), wrap(N.m('ADD', y0, 1.0)))

    def fetch(xi, yi, zi):
        col, row = N.m('FLOORED_MODULO', zi, 16.0), N.m('FLOOR', N.m('DIVIDE', zi, 16.0))
        u = N.m('DIVIDE', N.m('ADD', N.m('MULTIPLY', col, 130.0), N.m('ADD', xi, 1.5)), 2080.0)
        v = N.m('DIVIDE', N.m('ADD', N.m('MULTIPLY', row, 130.0), N.m('ADD', yi, 1.5)), 1040.0)
        tex = N.n('ShaderNodeTexImage', image=ATLAS, interpolation='Closest', extension='EXTEND')
        N.put(tex.inputs['Vector'], N.comb(u, v, 0.0))
        sep = N.n('ShaderNodeSeparateColor'); N.put(sep.inputs[0], tex.outputs['Color'])
        return sep.outputs[0]

    layers = []
    for zi in (wrap(z0), wrap(N.m('ADD', z0, 1.0))):
        a = N.mix(fetch(xs[0], ys[0], zi), fetch(xs[1], ys[0], zi), fx)
        b = N.mix(fetch(xs[0], ys[1], zi), fetch(xs[1], ys[1], zi), fx)
        layers.append(N.mix(a, b, fy))
    N.put(O['n'], N.mix(layers[0], layers[1], fz))
    return g


N3 = n3_group()


def site_pos(N, P):
    x, y, z = N.xyz(P)
    return N.comb(x, z, N.m('MULTIPLY', y, -1.0))       # Blender (X, Y, Z) -> site (x, y up, z)


def n3(N, p, scale=1.0):
    node = N.n('ShaderNodeGroup', node_tree=N3)
    N.put(node.inputs[0], p if scale == 1.0 else N.v('SCALE', p, s=1.0 / scale))
    return node.outputs[0]


# ------------------------------------------------------------------ shared shading groups (the site's fogColor, fog, lighting)
def fog_colour_group():
    # fogColor(rd) = fog * (1 + 0.25 rd.y) + sun * (0.05 s^5 + 0.06 s^40), s = max(dot(rd, sunDir), 0)
    g, N, I, O = group('Site • fog colour', [('Direction', 'NodeSocketVector')], [('Color', 'NodeSocketVector')])
    rd = N.v('NORMALIZE', I['Direction'])
    fog, sun, sd = N.prop('fog_col', True), N.prop('sun_col', True), N.prop('sun_dir', True)
    s = N.m('MAXIMUM', N.v('DOT_PRODUCT', rd, sd), 0.0)
    glow = N.m('ADD', N.m('MULTIPLY', N.m('POWER', s, 5.0), 0.05), N.m('MULTIPLY', N.m('POWER', s, 40.0), 0.06))
    col = N.v('ADD', N.v('SCALE', fog, s=N.m('ADD', 1.0, N.m('MULTIPLY', N.xyz(rd)[2], 0.25))), N.v('SCALE', sun, s=glow))
    N.put(O['Color'], col)
    return g


def shade_group(fogc):
    # the site's shade() lighting + the height fog, as an emission. Albedo, AO, spec and rim come from the material.
    g, N, I, O = group('Site • shade and fog',
                       [('Albedo', 'NodeSocketVector'), ('AO', 'NodeSocketFloat'), ('Spec', 'NodeSocketFloat'), ('Rim', 'NodeSocketFloat'),
                        ('Normal', 'NodeSocketVector')],
                       [('Shader', 'NodeSocketShader')])
    geo = N.n('ShaderNodeNewGeometry')
    nrm, inc, P = N.v('NORMALIZE', I['Normal']), geo.outputs['Incoming'], geo.outputs['Position']
    t = N.n('ShaderNodeCameraData').outputs['View Distance']
    rd = N.v('SCALE', inc, s=-1.0)
    fog, sun, sd = N.prop('fog_col', True), N.prop('sun_col', True), N.prop('sun_dir', True)
    den = N.prop('fog_den')
    ny = N.xyz(nrm)[2]
    # sun: white lamp of strength pi through a white diffuse = dif * shadow
    dif_bsdf = N.n('ShaderNodeBsdfDiffuse'); dif_bsdf.inputs['Color'].default_value = (1, 1, 1, 1)
    N.put(dif_bsdf.inputs['Normal'], nrm)
    s2r = N.n('ShaderNodeShaderToRGB'); N.put(s2r.inputs[0], dif_bsdf.outputs[0])
    lit = N.xyz(s2r.outputs['Color'])[0]
    ao = I['AO']
    dif = N.m('MAXIMUM', N.v('DOT_PRODUCT', nrm, sd), 1e-4)
    sh = N.m('DIVIDE', lit, dif, clamp=True)
    sky = N.v('ADD', N.v('SCALE', fog, s=2.2), (0.02, 0.03, 0.05))
    sunk = N.mix(N.m('MULTIPLY', N.m('MAXIMUM', N.v('DOT_PRODUCT', nrm, sd), 0.0), ao), lit, N.m('LESS_THAN', t, 2600.0))   # shadow() only below 2600 m
    lin = N.v('ADD', N.v('SCALE', sun, s=sunk),
              N.v('ADD', N.v('SCALE', sky, s=N.m('MULTIPLY', N.m('ADD', 0.55, N.m('MULTIPLY', 0.45, ny)), ao)),
                  N.v('SCALE', fog, s=N.m('MULTIPLY', N.m('MULTIPLY', 1.4, N.m('SUBTRACT', 0.5, N.m('MULTIPLY', 0.5, ny))), ao))))
    alb = I['Albedo']
    col = N.v('MULTIPLY', alb, lin)
    refl = N.v('REFLECT', rd, nrm)
    spec = N.m('MULTIPLY', N.m('MULTIPLY', I['Spec'], N.m('POWER', N.m('MAXIMUM', N.v('DOT_PRODUCT', refl, sd), 0.0), 8.0)), sh)
    col = N.v('ADD', col, N.v('SCALE', sun, s=spec))
    fres = N.m('POWER', N.m('ADD', 1.0, N.v('DOT_PRODUCT', rd, nrm), clamp=True), 3.0)
    rimk = N.m('MULTIPLY', N.m('MULTIPLY', N.m('MULTIPLY', I['Rim'], 0.35), fres),
               N.m('MAXIMUM', N.m('ADD', N.m('MULTIPLY', N.v('DOT_PRODUCT', rd, sd), 0.5), 0.5), 0.0))
    col = N.v('ADD', col, N.v('SCALE', N.v('MULTIPLY', alb, sun), s=rimk))
    # fogAmount(ro, rd, t): uniform haze + an exponential layer thinning with altitude
    rdy = N.xyz(rd)[2]
    roy = N.m('ADD', N.xyz(P)[2], N.m('MULTIPLY', N.xyz(inc)[2], t))
    b = 1.0 / 420.0
    x = N.m('MULTIPLY', N.m('MULTIPLY', t, rdy), b)
    xs = N.m('ADD', x, N.m('MULTIPLY', N.m('LESS_THAN', N.m('ABSOLUTE', x), 1e-5), 1e-5))
    k = N.m('MULTIPLY', t, N.m('DIVIDE', N.m('SUBTRACT', 1.0, N.m('EXPONENT', N.m('MULTIPLY', xs, -1.0))), xs))
    layer = N.m('MULTIPLY', N.m('MULTIPLY', 1.6, N.m('EXPONENT', N.m('MULTIPLY', N.m('SUBTRACT', roy, 380.0), -b))), k)
    amt = N.m('SUBTRACT', 1.0, N.m('EXPONENT', N.m('MULTIPLY', N.m('MULTIPLY', den, -1.0), N.m('ADD', N.m('MULTIPLY', 0.55, t), layer))))
    fc = N.n('ShaderNodeGroup', node_tree=fogc); N.put(fc.inputs[0], rd)
    final = N.vmix(col, fc.outputs[0], amt)
    em = N.n('ShaderNodeEmission'); N.put(em.inputs['Color'], final); em.inputs['Strength'].default_value = 1.0
    N.put(O['Shader'], em.outputs[0])
    return g


FOGC = fog_colour_group()
SHADE = shade_group(FOGC)


def material(name, build):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree; nt.nodes.clear()
    N = Nodes(nt)
    out = N.n('ShaderNodeOutputMaterial')
    build(N, out)
    return mat


def shade_out(N, out, alb, ao=1.0, spec=0.0, rim=0.0, normal=None):
    g = N.n('ShaderNodeGroup', node_tree=SHADE)
    normal = normal or N.n('ShaderNodeNewGeometry').outputs['Normal']
    for k, v in (('Albedo', alb), ('AO', ao), ('Spec', spec), ('Rim', rim), ('Normal', normal)):
        N.put(g.inputs[k], v)
    N.put(out.inputs['Surface'], g.outputs[0])


def rock_and_snow(N, out):
    # shade(), mat 0: rock with dusting, ledge / gully / couloir / valley snow
    geo = N.n('ShaderNodeNewGeometry')
    nrm = geo.outputs['Normal']
    ny = N.xyz(nrm)[2]
    p = site_pos(N, geo.outputs['Position'])
    v, w, fine, tint = n3(N, p, 23.0), n3(N, p, 5.0), n3(N, p, 1.3), n3(N, p, 170.0)
    rk = N.v('SCALE', (0.050, 0.052, 0.057), s=N.m('ADD', 0.6, N.m('MULTIPLY', 0.8, v)))
    rk = N.v('MULTIPLY', rk, N.vmix((1, 1, 1), (1.1, 1.0, 0.9), tint))
    dust = N.m('MULTIPLY', 0.35, N.smooth(0.35, 0.65, N.m('ADD', ny, N.m('MULTIPLY', 0.4, N.m('SUBTRACT', fine, 0.5)))))
    rk = N.vmix(rk, (0.5, 0.53, 0.58), dust)
    snow = N.smooth(0.56, 0.72, N.m('ADD', N.m('ADD', ny, N.m('MULTIPLY', 0.28, N.m('SUBTRACT', w, 0.5))), N.m('MULTIPLY', 0.1, N.m('SUBTRACT', v, 0.5))))
    ao1400, gully, couloir, floor = N.packed('site_terms')
    snow = N.m('MAXIMUM', snow, N.m('MULTIPLY', gully, N.smooth(0.18, 0.4, ny)))
    t_view = N.n('ShaderNodeCameraData').outputs['View Distance']
    band = N.m('MULTIPLY', N.attr8('snow_couloir_band'), N.smooth(900.0, 1400.0, t_view))   # onFloor = max(floor, far)
    snow = N.m('MAXIMUM', snow, N.m('MAXIMUM', couloir, band))
    snow = N.m('MAXIMUM', snow, N.m('MULTIPLY', floor, N.smooth(0.2, 0.5, ny)))
    white = N.v('SCALE', (0.76, 0.80, 0.87), s=N.m('ADD', 0.88, N.m('MULTIPLY', 0.16, w)))
    # crust and spindrift below the SDF's resolution: n += grad n3(p / (0.3, 1.4, 0.3)) * 0.22 * snow * (1 - t / 160)
    t = N.n('ShaderNodeCameraData').outputs['View Distance']
    q = N.v('MULTIPLY', p, (1 / 0.3, 1 / 1.4, 1 / 0.3))
    gs = [N.m('SUBTRACT', n3(N, N.v('ADD', q, e)), n3(N, N.v('SUBTRACT', q, e))) for e in ((0.35, 0, 0), (0, 0.35, 0), (0, 0, 0.35))]
    grad = N.comb(gs[0], N.m('MULTIPLY', gs[2], -1.0), gs[1])                       # site axes -> Blender
    k = N.m('MULTIPLY', N.m('MULTIPLY', N.m('MULTIPLY', 0.22, snow), N.m('SUBTRACT', 1.0, N.m('DIVIDE', t, 160.0), clamp=True)),
            N.m('GREATER_THAN', snow, 0.05))
    crust = N.v('NORMALIZE', N.v('ADD', nrm, N.v('SCALE', grad, s=k)))
    # AO as the site computes it from this distance: piecewise linear in log2(t) between the baked distances
    # (100, 200, 400, 800, 1400 m; its reach stops growing at 1167 m)
    lt = N.m('LOGARITHM', N.m('DIVIDE', N.m('MINIMUM', N.m('MAXIMUM', t, 100.0), 1400.0), 100.0), 2.0)
    a100, a200, a400, a800 = N.packed('site_ao')
    occ = a100
    for knot, (val, span) in enumerate(((a200, 1.0), (a400, 1.0), (a800, 1.0), (ao1400, math.log2(14.0) - 3.0))):
        occ = N.mix(occ, val, N.m('DIVIDE', N.m('SUBTRACT', lt, float(knot)), span, clamp=True))
    occ = N.mix(occ, 1.0, N.m('GREATER_THAN', t, 3500.0))                                  # t < 3500 ? ao : 1
    shade_out(N, out, N.vmix(rk, white, snow), ao=occ, spec=N.m('MULTIPLY', snow, 0.03), normal=crust)


def flat(alb, spec=0.0):
    def build(N, out):
        occ = N.n('ShaderNodeAmbientOcclusion', samples=16); occ.inputs['Distance'].default_value = 1.5
        shade_out(N, out, alb, ao=occ.outputs['AO'], spec=spec, rim=1.0)
    return build


def rope_mat(N, out):
    # rope: fades to snow once thinner than a pixel, like the site
    t = N.n('ShaderNodeCameraData').outputs['View Distance']
    cover = N.m('DIVIDE', 0.011, N.m('MAXIMUM', 0.011, N.m('MULTIPLY', N.m('MULTIPLY', t, N.prop('upix')), 0.6)))
    shade_out(N, out, N.vmix((0.8, 0.84, 0.9), (0.60, 0.28, 0.06), cover), rim=1.0)


# ------------------------------------------------------------------ meshes
def make_mesh(name, v, f):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v)); me.vertices.foreach_set('co', np.ascontiguousarray(v, np.float32).ravel())
    k = f.shape[1]
    me.loops.add(f.size); me.loops.foreach_set('vertex_index', np.ascontiguousarray(f, np.int32).ravel())
    me.polygons.add(len(f)); me.polygons.foreach_set('loop_start', np.arange(0, f.size, k, dtype=np.int32))
    me.update(calc_edges=True)
    me.shade_smooth()
    return me


def put_attr(me, name, values, kind='FLOAT'):
    a = me.attributes.new(name, kind, 'POINT')
    a.data.foreach_set('value', np.ascontiguousarray(values, np.float32 if kind == 'FLOAT' else np.int32))


def put_attr8(me, name, values):
    put_attr(me, name, np.round(np.clip(values, 0, 1) * 127).astype(np.int32), 'INT8')


# per-vertex terms, packed in two 8-bit RGBA colour attributes (Metal allows 31 buffers per shader):
#   site_ao    = the site's AO, whose reach is 1.2 % of the view distance, at t = 100, 200, 400, 800 m
#   site_terms = AO at 1400 m, snow in gullies, snow in the couloir, snow on the valley floor
PACK = {'site_ao': (16, 17, 18, 19), 'site_terms': (15, 8, 9, 10)}


def put_packed(me, at, ao_far=None):
    for name, cols in PACK.items():
        a = me.color_attributes.new(name, 'BYTE_COLOR', 'POINT')
        vals = np.clip(at[:, list(cols)], 0, 1).astype(np.float32)
        if ao_far is not None and name == 'site_terms':
            vals[:, 0] = np.clip(ao_far, 0, 1)
        a.data.foreach_set('color', vals.ravel())          # linear in, Blender stores sRGB bytes


def orient(me, sdf_normals):
    """MC winding check: face normals must agree with the SDF gradient (outward)."""
    fn = np.empty(len(me.polygons) * 3, np.float32); me.polygons.foreach_get('normal', fn)
    loops = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_start', loops)
    vi = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', vi)
    agree = (fn.reshape(-1, 3) * sdf_normals[vi[loops]]).sum(1)
    frac = (agree > 0).mean()
    print(f'{me.name}: {frac:.3f} of faces agree with the SDF normal')
    if frac < 0.5:
        me.flip_normals()


def collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or sc.collection).children.link(c)
    return c


C_MNT = collection('Mountains')
C_CLB = collection('Climber')
C_CAM = collection('Camera and sun')
C_ATM = collection('Atmosphere')
C_SNOW = collection('Snow (drawn over everything)')

mat_rock = material('Site • rock and snow', rock_and_snow)

d = np.load(os.path.join(DATA, 'terrain.npz'))
at = d['at']
me = make_mesh('Mountains', Bn(d['v']), d['f'])
orient(me, Bn(at[:, 0:3]))
put_packed(me, at, d['ao_far'])
put_attr8(me, 'snow_couloir_band', d['couloir_band'])
put_attr(me, 'lod_level', d['level'].astype(np.int32), 'INT')
me.materials.append(mat_rock)
ob = bpy.data.objects.new('Mountains', me); C_MNT.objects.link(ob)
# the site carves the couloir only up close (carveAmt = 1 - smoothstep(900, 1400, t)); from further away it is a
# snow-filled hollow. Shape key 'Couloir filled (far)' holds that far surface; its value is keyed per frame.
ob.shape_key_add(name='Basis', from_mix=False)
far_key = ob.shape_key_add(name='Couloir filled (far)', from_mix=False)
nfb = np.array(B(world['NF']))
far_co = Bn(d['v']) + d['far_offset'][:, None] * nfb
far_key.data.foreach_set('co', np.ascontiguousarray(far_co, np.float32).ravel())
mountains = ob
del d, at, far_co

g = np.load(os.path.join(DATA, 'ground.npz'))
nx, nz = int(g['nx']), int(g['nz'])
a = (np.arange(nz - 1)[:, None] * nx + np.arange(nx - 1)[None, :]).ravel()
quads = np.stack([a, a + nx, a + nx + 1, a + 1], 1)
me = make_mesh('Valley', Bn(g['v']), quads)
orient(me, Bn(g['at'][:, 0:3]))
put_packed(me, g['at'])
me.materials.append(mat_rock)
ob = bpy.data.objects.new('Valley floor', me); C_MNT.objects.link(ob)

c = np.load(os.path.join(DATA, 'climber.npz'))
me = make_mesh('Climber', Bn(c['v']), c['f'])
slot = {1: 0, 2: 1, 3: 2, 5: 3}
mi = np.array([slot.get(int(round(x)), 1) for x in c['mat'][c['f'][:, 0]]], np.int32)
me.polygons.foreach_set('material_index', mi)
for name, alb, spec in (('jacket', (0.52, 0.2, 0.04), 0.0), ('trousers, boots, pack', (0.035, 0.04, 0.05), 0.0),
                        ('helmet', (0.62, 0.62, 0.60), 0.0), ('axes', (0.3, 0.31, 0.33), 0.5)):
    me.materials.append(material('Climber • ' + name, flat(alb, spec)))
ob = bpy.data.objects.new('Climber', me); C_CLB.objects.link(ob)
climber_ob = ob
# the site never lets the climber get thinner than its pixel: its distance field is inflated by 0.75 px
inflate = ob.modifiers.new('Site • pixel inflation (keyed)', 'DISPLACE')
inflate.direction = 'NORMAL'; inflate.mid_level = 0.0

# rope: the three capsules of rope() as a curve
CL, NFv, TY = [np.array(world[k]) for k in ('CLIMBER', 'NF', 'TY')]
DOWN = np.array([0.4472136, 0, 0]) - 0.8944272 * TY; DOWN /= np.linalg.norm(DOWN)
pts = [CL + [0, 0.95, 0.16], CL + DOWN * 1.1 + NFv * 0.42, CL + DOWN * 5.0 + NFv * 0.07, CL + DOWN * 48.0 + NFv * 0.07]
cu = bpy.data.curves.new('Rope', 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 0.011; cu.bevel_resolution = 2
sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
for p, q in zip(sp.points, pts):
    p.co = (*B(q), 1.0)
cu.materials.append(material('Rope', rope_mat))
ob = bpy.data.objects.new('Rope', cu); C_CLB.objects.link(ob)
CL_CENTRE = np.array(world['CLIMBER']) + [0, 1.0, 0]

# ------------------------------------------------------------------ camera, sun and the per-frame look
cam_data = bpy.data.cameras.new('Intro camera')
cam_data.sensor_fit = 'VERTICAL'; cam_data.sensor_height = 24.0
cam_data.clip_start = 0.1; cam_data.clip_end = 20000.0
cam = bpy.data.objects.new('Intro camera • scroll', cam_data); C_CAM.objects.link(cam)
sc.camera = cam
prev_cam = bpy.data.objects.new('Snowfall • camera one frame earlier', None); C_CAM.objects.link(prev_cam)
prev_cam.hide_viewport = prev_cam.hide_render = True
sun_data = bpy.data.lights.new('Sun', 'SUN'); sun_data.energy = math.pi; sun_data.color = (1, 1, 1)
sun_data.angle = math.radians(10.0)          # the site's soft shadow: penumbra ~ 1/8 rad
sun = bpy.data.objects.new('Sun (colour and strength are applied in the shader)', sun_data); C_CAM.objects.link(sun)

for key in ('fog_col', 'sun_col', 'sun_dir'):
    sc[key] = [0.0, 0.0, 0.0]
for key in ('fog_den', 'cloud', 'time_s', 'snow', 'upix'):
    sc[key] = 0.0

prev_rot = None
for i, fr in enumerate(FR):
    f = i + 1
    pos, tgt = np.array(fr['pos']), np.array(fr['tgt'])
    fw = (tgt - pos) / np.linalg.norm(tgt - pos)
    r = np.cross(fw, [0, 1, 0]); r /= np.linalg.norm(r)
    u = np.cross(r, fw)
    m = Matrix((B(r), B(u), -B(fw))).transposed().to_4x4()
    m.translation = B(pos)
    cam.matrix_world = m
    e = m.to_euler('XYZ', prev_rot) if prev_rot else m.to_euler('XYZ')
    cam.rotation_euler = e; prev_rot = e
    cam_data.lens = 12.0 / math.tan(math.radians(fr['fov']) / 2)
    cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)
    cam_data.keyframe_insert('lens', frame=f)
    prev_cam.location = B(np.array(FR[max(i - 1, 0)]['pos']))
    prev_cam.keyframe_insert('location', frame=f)
    sdir = B(fr['sunDir']).normalized()
    sun.rotation_euler = Vector((0, 0, 1)).rotation_difference(sdir).to_euler()
    sun.keyframe_insert('rotation_euler', frame=f)
    sc['fog_col'] = list(fr['fog']); sc['sun_col'] = list(fr['sun']); sc['sun_dir'] = list(sdir)
    sc['fog_den'] = fr['den']; sc['cloud'] = fr['cloud']; sc['time_s'] = i / FPS; sc['snow'] = fr['snow']; sc['upix'] = fr['upix']
    for key in ('fog_col', 'sun_col', 'sun_dir', 'fog_den', 'cloud', 'time_s', 'snow', 'upix'):
        sc.keyframe_insert(f'["{key}"]', frame=f)
    dist = float(np.linalg.norm(pos - CL_CENTRE))
    inflate.strength = 0.75 * fr['upix'] * dist
    inflate.keyframe_insert('strength', frame=f)
    cu.bevel_depth = max(0.011, 0.6 * fr['upix'] * dist)
    cu.keyframe_insert('bevel_depth', frame=f)
    x = min(max((dist - 900.0) / 500.0, 0.0), 1.0)
    far_key.value = x * x * (3 - 2 * x)
    far_key.keyframe_insert('value', frame=f)

# ------------------------------------------------------------------ world: the fog colour, seen only by the camera
wd = bpy.data.worlds.new('Site • fog'); sc.world = wd
wn = wd.node_tree; wn.nodes.clear(); N = Nodes(wn)
tc = N.n('ShaderNodeTexCoord')
fc = N.n('ShaderNodeGroup', node_tree=FOGC); N.put(fc.inputs[0], tc.outputs['Generated'])
bg = N.n('ShaderNodeBackground'); N.put(bg.inputs['Color'], fc.outputs[0])
lp = N.n('ShaderNodeLightPath')
N.put(bg.inputs['Strength'], N.m('MULTIPLY', lp.outputs['Is Camera Ray'], N.m('SUBTRACT', 1.0, N.prop('snow_layer'))))
N.put(N.n('ShaderNodeOutputWorld').inputs['Surface'], bg.outputs[0])

# ------------------------------------------------------------------ clouds: drifting noise in the first 420 m in front of the camera
def clouds(N, out):
    geo = N.n('ShaderNodeNewGeometry')
    t = N.prop('time_s')
    q = N.v('SUBTRACT', site_pos(N, geo.outputs['Position']), N.comb(N.m('MULTIPLY', t, 3.0), 0.0, N.m('MULTIPLY', t, 1.2)))   # p - wind
    dsum = None
    for scale, wgt in ((110.0, 0.55), (36.0, 0.3), (11.0, 0.15)):
        term = N.m('MULTIPLY', n3(N, q, scale), wgt)
        dsum = term if dsum is None else N.m('ADD', dsum, term)
    cl = N.prop('cloud')
    dens = N.m('MULTIPLY', N.m('ADD', N.smooth(0.46, 0.72, dsum), N.m('MULTIPLY', 0.16, N.m('MAXIMUM', N.m('SUBTRACT', cl, 1.0), 0.0))), cl)
    sigma = N.m('MULTIPLY', dens, 0.035)
    fc = N.n('ShaderNodeGroup', node_tree=FOGC); N.put(fc.inputs[0], N.v('SCALE', geo.outputs['Incoming'], s=-1.0))
    lit = N.v('ADD', N.v('SCALE', fc.outputs[0], s=1.25), N.v('SCALE', N.prop('sun_col', True), s=0.05))
    ab = N.n('ShaderNodeVolumeAbsorption'); ab.inputs['Color'].default_value = (0, 0, 0, 1); N.put(ab.inputs['Density'], sigma)
    em = N.n('ShaderNodeEmission'); N.put(em.inputs['Color'], lit); N.put(em.inputs['Strength'], sigma)
    add = N.n('ShaderNodeAddShader'); N.put(add.inputs[0], ab.outputs[0]); N.put(add.inputs[1], em.outputs[0])
    N.put(out.inputs['Volume'], add.outputs[0])


bpy.ops.mesh.primitive_cube_add(size=900.0)
cl_ob = bpy.context.object; cl_ob.name = 'Clouds (volume around the camera)'
for coll in cl_ob.users_collection:
    coll.objects.unlink(cl_ob)
C_ATM.objects.link(cl_ob)
cl_ob.data.materials.append(material('Site • clouds', clouds))
cl_ob.parent = cam
cl_ob.matrix_parent_inverse = Matrix.Identity(4); cl_ob.location = (0, 0, 0)
cl_ob.display_type = 'BOUNDS'

# ------------------------------------------------------------------ snow: the site's instanced streaks, as geometry nodes
def snow_nodes():
    ng = bpy.data.node_groups.new('Snowfall (site)', 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    N = Nodes(ng)
    out = N.n('NodeGroupOutput')
    oi = N.n('GeometryNodeObjectInfo', transform_space='ORIGINAL'); oi.inputs['Object'].default_value = cam
    op = N.n('GeometryNodeObjectInfo', transform_space='ORIGINAL'); op.inputs['Object'].default_value = prev_cam
    camp = oi.outputs['Location']
    vel = N.v('SCALE', N.v('SUBTRACT', camp, op.outputs['Location']), s=float(FPS))
    t = N.n('GeometryNodeInputSceneTime').outputs['Seconds']
    rv = N.n('FunctionNodeRandomValue', data_type='FLOAT_VECTOR'); rv.inputs['Seed'].default_value = 7
    rw = N.n('FunctionNodeRandomValue', data_type='FLOAT'); rw.inputs['Seed'].default_value = 11
    seed = next(o for o in rv.outputs if o.type == 'VECTOR' and o.enabled)
    w = next(o for o in rw.outputs if o.type == 'VALUE' and o.enabled)
    sx, sy, _ = N.xyz(seed)
    wind = N.v('SCALE', (4.5, -1.2, -1.6), s=N.m('ADD', 0.6, N.m('MULTIPLY', 0.8, w)))
    sway = N.comb(N.m('MULTIPLY', N.m('SINE', N.m('ADD', N.m('MULTIPLY', t, 1.3), N.m('MULTIPLY', sx, 40.0))), 0.6),
                  N.m('MULTIPLY', N.m('COSINE', N.m('ADD', N.m('MULTIPLY', t, 1.1), N.m('MULTIPLY', sy, 40.0))), -0.6), 0.0)
    BOX = (70.0, 70.0, 44.0)
    raw = N.v('SUBTRACT', N.v('ADD', N.v('ADD', N.v('MULTIPLY', seed, BOX), N.v('SCALE', wind, s=t)), sway), camp)
    rel = N.v('SUBTRACT', N.v('WRAP', raw, BOX, (0.0, 0.0, 0.0)), (35.0, 35.0, 22.0))
    delta = N.v('SCALE', N.v('SUBTRACT', wind, vel), s=0.03)
    centre = N.v('SUBTRACT', N.v('ADD', camp, rel), N.v('SCALE', delta, s=0.5))
    rot = N.n('FunctionNodeRotateVector'); rot.inputs['Vector'].default_value = (0, 0, -1); N.put(rot.inputs['Rotation'], oi.outputs['Rotation'])
    depth = N.v('DOT_PRODUCT', rel, rot.outputs[0])
    blur = N.m('SUBTRACT', 1.0, N.smooth(0.6, 4.0, depth))
    r0 = N.m('ADD', 0.006, N.m('MULTIPLY', 0.01, w))
    rmin = N.m('MULTIPLY', depth, 0.9 * math.tan(math.radians(15.0)) / 491.0)   # 0.9 CSS px at the site's typical fov
    rad = N.m('MULTIPLY', N.m('MAXIMUM', r0, rmin), N.m('ADD', 1.0, N.m('MULTIPLY', 3.0, blur)))
    dl = N.v('LENGTH', delta)
    alpha = N.m('DIVIDE', N.m('MULTIPLY', N.m('ADD', 0.5, N.m('MULTIPLY', 0.5, w)), N.m('SUBTRACT', 1.0, N.m('MULTIPLY', 0.75, blur))),
                N.m('ADD', 1.0, N.m('MULTIPLY', N.m('DIVIDE', dl, N.m('MULTIPLY', rad, 2.0)), 0.5)))
    pts = N.n('GeometryNodePoints'); pts.inputs['Count'].default_value = 2600; N.put(pts.inputs['Position'], centre)
    st = N.n('GeometryNodeStoreNamedAttribute', data_type='FLOAT', domain='POINT')
    N.put(st.inputs['Geometry'], pts.outputs[0]); st.inputs['Name'].default_value = 'flake_alpha'; N.put(st.inputs['Value'], alpha)
    dele = N.n('GeometryNodeDeleteGeometry', domain='POINT')
    N.put(dele.inputs['Geometry'], st.outputs[0]); N.put(dele.inputs['Selection'], N.m('LESS_THAN', depth, 0.3))
    sphere = N.n('GeometryNodeMeshUVSphere'); sphere.inputs['Segments'].default_value = 10; sphere.inputs['Rings'].default_value = 6
    al = N.n('FunctionNodeAlignRotationToVector', axis='Z'); N.put(al.inputs['Vector'], delta)
    inst = N.n('GeometryNodeInstanceOnPoints')
    N.put(inst.inputs['Points'], dele.outputs[0]); N.put(inst.inputs['Instance'], sphere.outputs[0])
    N.put(inst.inputs['Rotation'], al.outputs[0])
    N.put(inst.inputs['Scale'], N.comb(rad, rad, N.m('ADD', rad, N.m('MULTIPLY', dl, 0.5))))
    sm = N.n('GeometryNodeSetMaterial'); N.put(sm.inputs['Geometry'], inst.outputs[0])
    sm.inputs['Material'].default_value = flake_mat
    N.put(out.inputs[0], sm.outputs[0])
    return ng


def flake(N, out):
    geo = N.n('ShaderNodeNewGeometry')
    z = N.n('ShaderNodeCameraData').outputs['View Z Depth']
    facing = N.m('POWER', N.m('ABSOLUTE', N.v('DOT_PRODUCT', geo.outputs['Normal'], geo.outputs['Incoming'])), 4.0)
    a = N.m('MULTIPLY', N.m('MULTIPLY', N.attr('flake_alpha', 'INSTANCER'), facing),
            N.m('MULTIPLY', N.m('EXPONENT', N.m('MULTIPLY', N.m('MULTIPLY', z, N.prop('fog_den')), -18.0)), N.smooth(0.3, 1.2, z)))
    em = N.n('ShaderNodeEmission'); N.put(em.inputs['Color'], N.v('SCALE', (0.8, 0.84, 0.9), s=N.m('MULTIPLY', a, N.prop('snow'))))
    N.put(out.inputs['Surface'], em.outputs[0])


flake_mat = material('Snowflake', flake)
snow_me = bpy.data.meshes.new('Snowfall')
snow_ob = bpy.data.objects.new('Snowfall', snow_me); C_SNOW.objects.link(snow_ob)
mod = snow_ob.modifiers.new('Snowfall', 'NODES'); mod.node_group = snow_nodes()

# ------------------------------------------------------------------ render: Eevee, the user's Retina format, two layers
r = sc.render
r.engine = 'BLENDER_EEVEE'
r.resolution_x, r.resolution_y, r.resolution_percentage = 3024, 1964, 100
r.fps = FPS
sc.frame_start, sc.frame_end = 1, NF
r.image_settings.file_format = 'PNG'
r.filepath = '//renders/intro_####'
ee = sc.eevee
ee.taa_render_samples = 64
ee.use_volume_custom_range = True            # otherwise the froxels span the whole 20 km clip range
ee.volumetric_start, ee.volumetric_end = 0.5, 420.0
ee.volumetric_tile_size = '8'
ee.volumetric_samples = 64
ee.use_volumetric_shadows = False
sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
sc.view_settings.exposure = 0.0; sc.view_settings.gamma = 1.0

main = sc.view_layers[0]; main.name = 'Scene'
snowl = sc.view_layers.new('Snow')
snowl['snow_layer'] = 1.0
main.layer_collection.children[C_SNOW.name].exclude = True
for cn in (C_MNT.name, C_CLB.name, C_ATM.name):
    snowl.layer_collection.children[cn].exclude = True

# ------------------------------------------------------------------ compositor: the site's grade, then the snow, then the CSS grain
post = bpy.data.node_groups.new('Site • grade, snow, grain', 'CompositorNodeTree')
post.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
sc.compositing_node_group = post
N = Nodes(post)
rl = N.n('CompositorNodeRLayers'); rl.layer = 'Scene'
rs = N.n('CompositorNodeRLayers'); rs.layer = 'Snow'
keyed = {}
for name, key in (('Exposure', 'exposure'), ('Vignette', 'vig'), ('Paper white', 'white'), ('Snow brightness', 'snow'), ('Grain opacity', 'grain')):
    node = N.n('ShaderNodeValue', name=name, label=name); keyed[key] = node
for i, fr in enumerate(FR):
    for key, node in keyed.items():
        node.outputs[0].default_value = fr[key]
        node.outputs[0].keyframe_insert('default_value', frame=i + 1)
sep = N.n('CompositorNodeSeparateColor'); N.put(sep.inputs[0], rl.outputs['Image'])
ssep = N.n('CompositorNodeSeparateColor'); N.put(ssep.inputs[0], rs.outputs['Image'])
coords = N.n('CompositorNodeImageCoordinates'); N.put(coords.inputs[0], rl.outputs['Image'])
cx, cy = N.v('DOT_PRODUCT', coords.outputs['Normalized'], (1, 0, 0)), N.v('DOT_PRODUCT', coords.outputs['Normalized'], (0, 1, 0))
qx, qy = N.m('SUBTRACT', cx, 0.5), N.m('SUBTRACT', cy, 0.5)
vign = N.m('SUBTRACT', 1.0, N.m('MULTIPLY', N.m('MULTIPLY', keyed['vig'].outputs[0], 0.512),
                                 N.m('ADD', N.m('MULTIPLY', qx, qx), N.m('MULTIPLY', qy, qy))))
snow_a = N.m('DIVIDE', ssep.outputs['Green'], N.m('MAXIMUM', N.m('MULTIPLY', keyed['snow'].outputs[0], 0.84), 1e-3), clamp=True)
grain_img = None
if GRAIN:
    gi = N.n('CompositorNodeImage')
    img = bpy.data.images.load(os.path.join(GRAIN, 'grain_tiled.png')); img.colorspace_settings.name = 'Non-Color'; img.pack()
    gi.image = img
    tr = N.n('CompositorNodeTranslate', name='Grain shift')
    for prop, val in (('wrap_axis', 'BOTH'), ('interpolation', 'NEAREST')):
        if hasattr(tr, prop):
            setattr(tr, prop, val)
    for sock, val in (('Extension X', 'Repeat'), ('Extension Y', 'Repeat'), ('Interpolation', 'Nearest')):
        if sock in tr.inputs:
            try:
                tr.inputs[sock].default_value = val
            except Exception as e:
                print('grain translate', sock, e)
    N.put(tr.inputs['Image'], gi.outputs['Image'])
    for i, (gx, gy) in enumerate(json.load(open(os.path.join(GRAIN, 'grain_shift.json')))):
        tr.inputs['X'].default_value, tr.inputs['Y'].default_value = gx, gy
        tr.inputs['X'].keyframe_insert('default_value', frame=i + 1); tr.inputs['Y'].keyframe_insert('default_value', frame=i + 1)
    grain_img = N.n('CompositorNodeSeparateColor'); N.put(grain_img.inputs[0], tr.outputs['Image'])


def aces_gamma(c):
    x = N.m('MULTIPLY', N.m('MULTIPLY', c, keyed['exposure'].outputs[0]), 1.6)
    num = N.m('MULTIPLY', x, N.m('MULTIPLY_ADD', x, 2.51, 0.03))
    den = N.m('ADD', N.m('MULTIPLY', x, N.m('MULTIPLY_ADD', x, 2.43, 0.59)), 0.14)
    return N.m('POWER', N.m('DIVIDE', num, den, clamp=True), 1 / 2.2)


gam = [aces_gamma(sep.outputs[k]) for k in ('Red', 'Green', 'Blue')]
paper = (0.957, 0.949, 0.933)
chan = []
for i, (g_, cold, pap, sk) in enumerate(zip(gam, (0.95, 0.985, 1.04), paper, ('Red', 'Green', 'Blue'))):
    x = N.m('MULTIPLY', g_, N.m('ADD', 1.0, N.m('MULTIPLY', cold - 1.0, N.m('SUBTRACT', 1.0, gam[1]))))   # cold shadows
    x = N.m('MULTIPLY', x, vign)
    x = N.mix(x, pap, keyed['white'].outputs[0])
    x = N.m('ADD', ssep.outputs[sk], N.m('MULTIPLY', x, N.m('SUBTRACT', 1.0, snow_a)))                  # snow, over
    if grain_img:                                                                                          # CSS overlay
        s = grain_img.outputs['Red']
        lo = N.m('MULTIPLY', N.m('MULTIPLY', x, s), 2.0)
        hi = N.m('SUBTRACT', 1.0, N.m('MULTIPLY', N.m('MULTIPLY', N.m('SUBTRACT', 1.0, x), N.m('SUBTRACT', 1.0, s)), 2.0))
        ov = N.mix(hi, lo, N.m('LESS_THAN', x, 0.5))
        x = N.mix(x, ov, keyed['grain'].outputs[0])
    x = N.m('MINIMUM', N.m('MAXIMUM', x, 0.0), 1.0)
    # the view transform re-applies the sRGB curve: hand it linear values so the file holds the site's pixels
    lin = N.mix(N.m('DIVIDE', x, 12.92), N.m('POWER', N.m('DIVIDE', N.m('ADD', x, 0.055), 1.055), 2.4), N.m('GREATER_THAN', x, 0.04045))
    chan.append(lin)
comb = N.n('CompositorNodeCombineColor')
for i, cch in enumerate(chan):
    N.put(comb.inputs[i], cch)
N.put(N.n('NodeGroupOutput').inputs[0], comb.outputs[0])

# viewports: through the intro camera, with a clip range that holds the whole valley
for scr in bpy.data.screens:
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.clip_start, sp.clip_end = 0.5, 30000.0
            sp.region_3d.view_perspective = 'CAMERA'
            sp.shading.type = 'SOLID'

sc.frame_set(1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('saved', OUT)
