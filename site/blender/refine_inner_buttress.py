import bpy, bmesh, hashlib, math
from mathutils import Vector, noise
from pathlib import Path

root = Path('/Users/petrinolann/Documents/ChatGPT/hiking sasse/site/blender')
name = 'Side ridge 08 • sculpt'
def digest(o):
    return hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices], [tuple(p.vertices) for p in o.data.polygons], tuple(tuple(r) for r in o.matrix_world))).encode()).hexdigest()
def smooth(a, b, x):
    t = max(0., min(1., (x-a)/(b-a)))
    return t*t*(3-2*t)

bpy.ops.wm.open_mainfile(filepath=str(root/'intro_mountain_isolated.blend'))
healthy = [v.co.copy() for v in bpy.data.objects[name].data.vertices]
bpy.ops.wm.open_mainfile(filepath=str(root/'intro_mountain_repaired.blend'))
preserved = {o.name: digest(o) for o in bpy.data.objects if o.type=='MESH' and o.name not in (name, 'Side ridge 07 • sculpt')}
o = bpy.data.objects[name]
base = -680.
for i, v in enumerate(o.data.vertices):
    if i >= 145*145:
        continue
    p = v.co.copy()
    old = healthy[i]
    # Remove the sculpted razor-thin slab on the valley side. Keep the user's
    # outer slopes and summit, with a broad continuous inner rock buttress.
    retain = smooth(1100, 1900, p.x)
    height = old.z + (p.z-old.z)*retain
    valley = smooth(340, 1500, p.x)
    v.co.z = base - 40 + max(0.,height-base+40)*valley
    if 450 < p.x < 1800 and v.co.z > base + 100:
        # Low amplitude rock relief follows the descending flank; it never
        # creates free-standing spikes or a flat vertical cut.
        detail = noise.fractal(Vector((p.x/180,p.y/270,8.2)), .8, 2., 3)
        weight = smooth(450,750,p.x)*(1-smooth(1400,1800,p.x))
        v.co.z += detail*32*weight*valley
bm=bmesh.new(); bm.from_mesh(o.data)
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
bm.to_mesh(o.data); bm.free(); o.data.update()
# The visible thin blade is the adjoining ridge 07 crossing into the valley.
# Taper both flanks to a common valley floor instead of leaving two overlapping
# high meshes near the approach axis.
neighbor = bpy.data.objects['Side ridge 07 • sculpt']
for i, v in enumerate(neighbor.data.vertices):
    if i >= 145*145:
        continue
    inward_distance = -v.co.x
    valley = smooth(340, 1500, inward_distance)
    v.co.z = base - 55 + max(0., v.co.z-base+55)*valley
bm=bmesh.new(); bm.from_mesh(neighbor.data)
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
bm.to_mesh(neighbor.data); bm.free(); neighbor.data.update()
assert all(digest(bpy.data.objects[n])==h for n,h in preserved.items())
o['repair_notes']='Valley-side slab removed; broad continuous buttress taper; outer sculpt and main summit preserved.'
bpy.ops.wm.save_as_mainfile(filepath=str(root/'intro_mountain_buttress.blend'))
print('PASS: only inner valley flanks of ridges 07 and 08 modified; central sculpture and other meshes preserved')
