"""Blend only the lower massif into its valley, retaining the scroll rig and upper rock."""
import bpy
import numpy as np
from pathlib import Path
from mathutils import Vector

SOURCE = Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/v2_scroll/intro_v2_scroll.blend')
ROOT = Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
mountain = bpy.data.objects['Mountains']
floor = bpy.data.objects['Valley floor']

def coordinates(data):
    a = np.empty(len(data) * 3, np.float32)
    data.foreach_get('co', a)
    return a.reshape(-1, 3)

def smooth(a, b, t):
    t = np.clip((t-a)/(b-a), 0, 1)
    return t*t*(3-2*t)

ground = coordinates(floor.data.vertices)
xs = np.unique(ground[:, 0])
ys = np.unique(ground[:, 1])
height = np.empty((len(ys), len(xs)), np.float32)
ix = np.rint((ground[:, 0]-xs[0])/12).astype(int)
iy = np.rint((ground[:, 1]-ys[0])/12).astype(int)
height[iy, ix] = ground[:, 2]

def old_ground(x, y):
    u = np.clip((x-xs[0])/12, 0, len(xs)-1.001)
    v = np.clip((y-ys[0])/12, 0, len(ys)-1.001)
    i = u.astype(int); j = v.astype(int)
    a = u-i; b = v-j
    return ((1-a)*(1-b)*height[j,i] + a*(1-b)*height[j,i+1]
            + (1-a)*b*height[j+1,i] + a*b*height[j+1,i+1])

def apron(x, y):
    # A broad compactly supported shoulder, with spreading erosion buttresses.
    r = np.sqrt(((x-80)/1330)**2 + ((y-180)/1460)**2)
    envelope = 1-smooth(.7, 1.35, r)
    shoulder = 207*(1-smooth(.08, 1.27, r))
    ribs = np.zeros_like(x)
    for sx, sy, tx, ty, width, amount in (
        (-660, -20, -1120, -1510, 120, 53),
        (-320, -80, -530, -1660, 100, 66),
        (30, -90, -30, -1550, 85, 45),
        (380, -20, 710, -1700, 110, 62),
        (820, 170, 1310, -1180, 120, 46),
    ):
        t = np.clip((sy-y)/(sy-ty), 0, 1)
        cx = sx+(tx-sx)*t + 28*np.sin(t*7+sx*.004)*np.sin(np.pi*t)
        w = width*(.85+1.15*t)
        rib = amount*np.exp(-((x-cx)/w)**2)*(1-smooth(.32, 1, t))
        rib *= smooth(ty-50, ty+150, y)*(1-smooth(sy+130, sy+360, y))
        ribs = np.maximum(ribs, rib)
    # Small, coherent variation on the talus; no random displacement of the cliff tops.
    detail = (9*np.sin(x*.027+y*.012)*np.sin(y*.018-x*.006)
              + 4*np.sin(x*.066+y*.041)) * envelope
    low_valley = 1-smooth(220,350,old_ground(x,y))
    return (np.clip((shoulder+ribs+detail)*envelope, 0, 253)*low_valley).astype(np.float32)

rise = apron(ground[:,0], ground[:,1])
assert rise.max() < 260
changed_ground = ground.copy()
changed_ground[:,2] += rise
floor.data.vertices.foreach_set('co', changed_ground.ravel())
floor.data.update()

# Gently settle the bottom of each existing shape key into the new apron.
# The new ground buries the old meshing skirt instead of carrying its visible
# terrace upward. Above 460 m the mesh is unchanged.
base = coordinates(mountain.data.shape_keys.key_blocks['Basis'].data)
local_ground = old_ground(base[:,0], base[:,1])
support = apron(base[:,0], base[:,1])
weight = 1-smooth(np.minimum(local_ground,300)+15, 460, base[:,2])
delta = support*weight*.12
assert np.all(delta[base[:,2] >= 460] == 0)
assert np.max(1.5*support/np.maximum(460-local_ground-15, 1)) < 1
for key in mountain.data.shape_keys.key_blocks:
    co = coordinates(key.data)
    co[:,2] += delta
    key.data.foreach_set('co', co.ravel())
mountain.data.vertices.foreach_set('co', (base+np.stack((np.zeros_like(delta),np.zeros_like(delta),delta),axis=1)).ravel())
mountain.data.update()

# Refresh floor snow/AO masks locally: the material's slope-based snow remains
# live, while the old fully-white floor mask no longer covers the new banks.
terms = floor.data.color_attributes['site_terms']
packed = np.empty(len(ground)*4, np.float32)
terms.data.foreach_get('color', packed)
packed = packed.reshape(-1,4)
zgrid = np.empty_like(height); zgrid[iy,ix] = changed_ground[:,2]
dy, dx = np.gradient(zgrid,12,12)
slope = np.sqrt(dx[iy,ix]**2+dy[iy,ix]**2)
local = smooth(8,60,rise)
packed[:,3] *= 1-local
packed[:,1] = np.maximum(packed[:,1], .18*local)
terms.data.foreach_set('color', packed.ravel())
ao = floor.data.color_attributes['site_ao']
values = np.empty(len(ground)*4,np.float32); ao.data.foreach_get('color',values)
values=values.reshape(-1,4)
values *= (1-.045*local[:,None]*smooth(.2,.6,slope[:,None]))
ao.data.foreach_set('color',values.ravel())

scene['base_refinement'] = 'Connected talus apron and five spreading buttresses; only the lower 460 m and adjacent valley changed.'
scene['base_refinement_max_lift_m'] = float(rise.max())
mountain['base_refinement'] = 'Both original couloir shape keys preserved; upper vertices above 460 m unchanged.'
scene.frame_set(145)
overview_target=Vector((40,-220,320))
overview_position=Vector((-1450,-3300,1850))
overview_rotation=(overview_target-overview_position).to_track_quat('-Z','Y')
for screen in bpy.data.screens:
    for area in screen.areas:
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.clip_end = 20000
                space.overlay.show_overlays = False
                space.region_3d.view_perspective = 'PERSP'
                space.region_3d.view_location = overview_target
                space.region_3d.view_distance = (overview_position-overview_target).length
                space.region_3d.view_rotation = overview_rotation
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_v2_base_refined.blend'))
print('PASS: upper massif and rig retained; base lift',float(rise.max()),'m;',int(np.count_nonzero(delta)),'lower mountain vertices reshaped',flush=True)

# Geometry overview, without changing the saved original scroll camera/render settings.
original_camera = scene.camera
data=bpy.data.cameras.new('Base inspection lens'); data.lens=38; data.clip_end=30000
camera=bpy.data.objects.new('Base inspection camera',data);scene.collection.objects.link(camera)
camera.location=(-1450,-3300,1850)
camera.rotation_euler=(Vector((40,-220,320))-camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera=camera
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=1400;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.display.render_aa='8'; sh=scene.display.shading
sh.light='STUDIO';sh.color_type='SINGLE';sh.single_color=(.48,.5,.52)
sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0
scene.compositing_node_group=None
for ob in scene.objects:
    if ob.name.startswith('Clouds') or ob.name == 'Snowfall':
        ob.hide_render = True
scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(ROOT/'v2_base_geometry_after.png')
bpy.ops.render.render(write_still=True)

# Re-open the saved edit to preview the actual material and original camera.
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'intro_v2_base_refined.blend'))
scene=bpy.context.scene
scene.render.resolution_percentage=50
scene.eevee.taa_render_samples=16
scene.frame_set(145)
scene.render.filepath=str(ROOT/'v2_base_material_after.png')
bpy.ops.render.render(write_still=True)
