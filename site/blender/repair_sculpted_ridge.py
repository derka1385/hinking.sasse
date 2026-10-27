import bpy, bmesh, hashlib
from pathlib import Path

root = Path('/Users/petrinolann/Documents/ChatGPT/hiking sasse/site/blender')
name = 'Side ridge 08 • sculpt'
def signature(obj):
    return hashlib.sha256(repr(([tuple(v.co) for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons], tuple(tuple(r) for r in obj.matrix_world))).encode()).hexdigest()

bpy.ops.wm.open_mainfile(filepath=str(root / 'intro_mountain_isolated.blend'))
healthy = [v.co.copy() for v in bpy.data.objects[name].data.vertices]
bpy.ops.wm.open_mainfile(filepath=str(root / 'intro_mountain_before_repair.blend'))
preserved = {o.name: signature(o) for o in bpy.data.objects if o.type == 'MESH' and o.name != name}
obj = bpy.data.objects[name]
assert len(obj.data.vertices) == len(healthy)
# Recover the healthy horizontal sampling while retaining the sculpted height
# field. Filter only the sculpt displacement, leaving the original rock intact.
stride = 145
count = stride * stride
delta = [obj.data.vertices[i].co.z - healthy[i].z for i in range(count)]
for _ in range(10):
    filtered = delta.copy()
    for j in range(1, stride - 1):
        for i in range(1, stride - 1):
            k = j * stride + i
            filtered[k] = .35 * delta[k] + .65 * sum(delta[k+d] for d in (-1, 1, -stride, stride)) / 4
    delta = filtered
for i, vertex in enumerate(obj.data.vertices):
    vertex.co = healthy[i]
    if i < count:
        vertex.co.z += delta[i]
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
bm.to_mesh(obj.data)
bm.free()
obj.data.update()
assert all(signature(bpy.data.objects[n]) == sig for n, sig in preserved.items())
# These kilometre-scale meshes require a practical near clipping distance;
# the previous 1 cm setting produced severe depth flicker and black fragments.
for screen in bpy.data.screens:
    for area in screen.areas:
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.clip_start = 5
                space.clip_end = 40000
        if area.type == 'CONSOLE' and screen.name == 'Layout':
            area.type = 'VIEW_3D'
            area.spaces.active.clip_start = 5
            area.spaces.active.clip_end = 40000
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.save_as_mainfile(filepath=str(root / 'intro_mountain_repaired.blend'))
print('PASS: only ridge 08 geometry changed; all other meshes and transforms preserved')
