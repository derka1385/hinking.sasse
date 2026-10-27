"""Edit only peripheral meshes in a snapshot containing the user's sculpture.

Run in Blender with intro_mountain_user_sculpt_snapshot.blend loaded. The main
mesh, its transform, materials, camera and all previous assets are preserved.
"""
from array import array
import hashlib
import math
from pathlib import Path

import bpy
from mathutils import Vector, noise

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "intro_mountain_isolated.blend"
BASE = -680.0
scene = bpy.context.scene
main = bpy.data.objects["Main massif • sculpt"]


def mesh_digest(obj):
    coords = array('f', [0.0]) * (3 * len(obj.data.vertices))
    obj.data.vertices.foreach_get('co', coords)
    indices = array('I', [v for p in obj.data.polygons for v in p.vertices])
    h = hashlib.sha256(coords.tobytes() + indices.tobytes())
    h.update(repr(tuple(tuple(row) for row in obj.matrix_world)).encode())
    h.update(repr([(m.name, m.type) for m in obj.modifiers]).encode())
    h.update(repr([m.name if m else None for m in obj.data.materials]).encode())
    return h.hexdigest()


def smooth(a, b, v):
    t = max(0, min(1, (v - a) / (b - a)))
    return t * t * (3 - 2 * t)


original_hash = mesh_digest(main)

# Outward offset, back offset, height of the original crest before new horns.
settings = {
    1: (600, -170, 1910),
    2: (520, -100, 2070),
    3: (430, 50, 1080),
    4: (640, -230, 2080),
    5: (550, -110, 2240),
    6: (460, 70, 1110),
    7: (700, -380, 2750),
    8: (730, -450, 2960),
}

for index, (outward, back, target) in settings.items():
    obj = bpy.data.objects.get(f"Side ridge {index:02} • sculpt")
    if obj is None:
        raise ValueError(f"Missing visible peripheral massif {index}")
    if obj.data == main.data:
        raise ValueError("Peripheral mesh shares the user's central mesh")
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    apex = obj.get("summit_scene_xyz_m")
    if not apex:
        old = obj["site_apex_xyz_m"]
        apex = (old[0], old[2], old[1])
    cx, cy, old_top = map(float, apex)
    sign = -1 if cx < main.location.x else 1
    scale_z = (target - BASE) / (old_top - BASE)
    original = [v.co.copy() for v in obj.data.vertices]
    new_coords = []
    for p in original:
        q = max(0, min(1.25, (p.z - BASE) / (old_top - BASE)))
        inward = (p.x - cx) * sign < 0
        # Pull upper inner slopes back into the massif while keeping broad
        # outer buttresses. This opens the central valley and steepens walls.
        sx = (1.03 - .20 * smooth(.12, .70, q)) if inward else 1.12
        x = cx + (p.x - cx) * sx + sign * outward
        y = cy + (p.y - cy) * .91 + back
        z = p.z if p.z <= BASE else BASE + (old_top - BASE) * scale_z * q ** 1.10
        new_coords.append(Vector((x, y, z)))

    # The natural terrain meshes retain a regular top grid plus a closed skirt.
    cols = 145
    candidates = []
    for j in range(3, cols - 3):
        for i in range(3, cols - 3):
            k = j * cols + i
            p = new_coords[k]
            if p.z > BASE + (target - BASE) * .58 and all(
                    p.z >= new_coords[y * cols + x].z
                    for y in range(j - 2, j + 3) for x in range(i - 2, i + 3)):
                candidates.append((k, p))
    crests = []
    for k, p in sorted(candidates, key=lambda item: item[1].z, reverse=True):
        if all(math.hypot(p.x - v.x, p.y - v.y) > 400 for v in crests):
            crests.append(p.copy())
        if len(crests) == (5 if index >= 7 else 4):
            break
    if not crests:
        crests = [max(new_coords, key=lambda p: p.z).copy()]

    for k, p in enumerate(new_coords):
        q = max(0, (p.z - BASE) / (target - BASE))
        if q < .24:
            continue
        horn = 0.0
        for n, crest in enumerate(crests):
            angle = index * .73 + n * 1.09
            dx, dy = p.x - crest.x, p.y - crest.y
            a = dx * math.cos(angle) + dy * math.sin(angle)
            b = -dx * math.sin(angle) + dy * math.cos(angle)
            b += 25 * math.sin(a / 155)
            theta = math.atan2(b, a)
            radius = math.hypot(a / (340 + n * 25), b / (155 + (n % 2) * 30))
            radius *= 1 + .12 * math.cos(3 * theta + index) + .08 * math.sin(5 * theta)
            amplitude = (265 if index >= 7 else 175) * (1 - n * .08)
            horn = max(horn, amplitude * max(0, 1 - radius) ** .85)
        p.z += horn
        # Curving narrow couloirs and ledges increase the visible face relief.
        bend = noise.noise(Vector((p.x / 420, p.y / 740, index * 1.7)))
        groove = abs(math.sin(p.x / 82 + bend * 2.1 + p.y / 1900)) ** 16
        p.z -= groove * 34 * smooth(.24, .62, q) * (1 - smooth(.89, 1.1, q))

    for vertex, coord in zip(obj.data.vertices, new_coords):
        vertex.co = coord
    obj.data.update()
    peak = max(new_coords, key=lambda p: p.z)
    obj["summit_scene_xyz_m"] = list(peak)
    obj["peripheral_art_direction"] = "Wider separation, massive outer buttresses, steep inner faces, asymmetric rock horns"
    obj["outward_offset_m"] = outward
    print(f"PERIPHERAL {index:02} outward={outward} m highest={peak.z:.0f} m horns={len(crests)}")

assert mesh_digest(main) == original_hash, "The user's central sculpture changed"
scene["central_sculpture_preserved_sha256"] = original_hash
scene["art_direction"] = "User central sculpture preserved; peripheral massifs separated and sharpened in Blender only."
scene.frame_set(26)
for area in bpy.context.screen.areas:
    if area.type == 'CONSOLE':
        area.type = 'VIEW_3D'
    if area.type == 'VIEW_3D':
        area.spaces.active.region_3d.view_perspective = 'CAMERA'
        area.spaces.active.shading.type = 'RENDERED'
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
print(f"WROTE_BLEND {OUTPUT} central_sha256={original_hash}")
for frame in (26, 37, 56):
    scene.frame_set(frame)
    scene.render.resolution_percentage = 75
    scene.render.filepath = str(HERE / f"intro_mountain_isolated_preview_{frame:02}.png")
    bpy.ops.render.render(write_still=True)
