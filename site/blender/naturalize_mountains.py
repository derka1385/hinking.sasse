"""Replace Blender's pyramidal proxy meshes with editable DEM-based massifs.

Run on intro_mountain_blender_scale.blend. This never reads or writes site JS.
The original meshes stay in a hidden archive collection.
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector, noise

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "intro_mountain_natural.blend"
BASE = -680.0
scene = bpy.context.scene
reference = bpy.data.objects["REAL Kebnekaise • DEM reference"]
vertices = reference.data.vertices
N = round(math.sqrt(len(vertices)))
xmin, ymin = vertices[0].co.x, vertices[0].co.y
dx = (vertices[N - 1].co.x - xmin) / (N - 1)
dy = (vertices[(N - 1) * N].co.y - ymin) / (N - 1)
heights = [v.co.z for v in vertices]


def clamp(v, lo=0.0, hi=1.0):
    return min(hi, max(lo, v))


def smooth(lo, hi, v):
    t = clamp((v - lo) / (hi - lo))
    return t * t * (3 - 2 * t)


def dem(x, y):
    u = clamp((x - xmin) / dx, 0, N - 1.001)
    v = clamp((y - ymin) / dy, 0, N - 1.001)
    i, j = int(u), int(v)
    a, b = u - i, v - j
    k = j * N + i
    return ((1 - a) * (1 - b) * heights[k] + a * (1 - b) * heights[k + 1]
            + (1 - a) * b * heights[k + N] + a * b * heights[k + N + 1])


# Identify separate real summits; each massif uses a different part of the DEM.
candidates = []
for j in range(5, N - 5):
    for i in range(5, N - 5):
        k = j * N + i
        if all(heights[k] >= heights[y * N + x]
               for y in range(j - 4, j + 5) for x in range(i - 4, i + 5)):
            candidates.append((xmin + i * dx, ymin + j * dy, heights[k]))
peaks = []
for p in sorted(candidates, key=lambda q: q[2], reverse=True):
    if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1100 for q in peaks):
        peaks.append(p)

material = bpy.data.objects["Main massif • sculpt"].data.materials[0]
nodes = material.node_tree.nodes
for node in nodes:
    if node.bl_idname == "ShaderNodeVectorMath" and node.operation == "SCALE":
        node.inputs[3].default_value = .0016
    elif node.bl_idname == "ShaderNodeTexNoise":
        node.inputs["Scale"].default_value = .026
        node.inputs["Detail"].default_value = 4
    elif node.bl_idname == "ShaderNodeBump":
        node.inputs["Distance"].default_value = 2.8
        node.inputs["Strength"].default_value = .32
    elif node.bl_idname == "ShaderNodeMapRange":
        if node.inputs["From Min"].default_value == 350:
            node.inputs["From Min"].default_value = 550
            node.inputs["From Max"].default_value = 1450
        else:
            node.inputs["From Min"].default_value = .34
            node.inputs["From Max"].default_value = .78
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .55
sculpt = bpy.data.collections["01 • SCULPT — website mountain"]
sculpt.name = "01 • SCULPT — natural mountain forms"
archive = bpy.data.collections.new("06 • ARCHIVE — pyramidal proxies")
scene.collection.children.link(archive)
for obj in list(sculpt.objects):
    obj["original_sculpt_name"] = obj.name
    obj.name += " • archived proxy"
    archive.objects.link(obj)
    sculpt.objects.unlink(obj)
archive.hide_viewport = True
archive.hide_render = True


class Massif:
    def __init__(self, name, position, template, sx, sy, angle, radius=2450, main=False):
        self.name, self.position, self.template = name, position, template
        self.sx, self.sy, self.radius, self.main = sx, sy, radius, main
        self.angle = angle
        # A common low valley datum avoids exaggerating a small local summit
        # into a needle when its surrounding ridge is already high.
        self.floor = min(heights)
        self.range = max(250.0, template[2] - self.floor)

    def profile(self, u, v):
        c, s = math.cos(self.angle), math.sin(self.angle)
        # Local forward is the direction selected on the original DEM.
        px = self.template[0] + c * v - s * u
        py = self.template[1] + s * v + c * u
        r = math.hypot(u, v)
        q = max(0, (dem(px, py) - self.floor) / self.range)
        q *= math.exp(-.52 * (r / (self.radius * .72)) ** 2)
        q *= 1 - smooth(self.radius * .72, self.radius, r)
        return q

    def height(self, x, y, detail=True):
        u = (x - self.position[0]) / self.sx
        v = (y - self.position[1]) / self.sy
        if abs(u) > self.radius or abs(v) > self.radius:
            return BASE
        q = self.profile(u, v)
        if not self.main:
            # Keep the valley open around the established approach camera.
            axis = 20 + 85 * math.sin(y / 1400)
            q *= smooth(170, 730, abs(x - axis))
        z = BASE + (self.position[2] - BASE) * q
        if detail and q > .04:
            p = Vector((x / 95, y / 95, 13.7))
            relief = noise.fractal(p, .9, 2.1, 3)
            broad = noise.fractal(Vector((x / 230, y / 230, 5.3)), .8, 2, 3)
            z += (relief * 15 + broad * 38) * smooth(.04, .28, q) * (1 - smooth(.91, 1, q))
            # Curving drainage grooves cut into steep faces. Their direction
            # follows the massif's forward fall line rather than adding lumps.
            grad_u = (self.profile(u + 35, v) - self.profile(u - 35, v)) / (70 * self.sx)
            grad_v = (self.profile(u, v + 35) - self.profile(u, v - 35)) / (70 * self.sy)
            slope = math.hypot(grad_u, grad_v) * (self.position[2] - BASE)
            bend = noise.noise(Vector((u / 370, v / 690, 7.8)))
            channel = abs(math.sin(u / 76 + bend * 2.5 + v / 2800)) ** 14
            z -= channel * 48 * smooth(.35, 1.05, slope) * (1 - smooth(.88, 1, q))
        return z

    def mesh(self, steps):
        verts, faces = [], []
        for j in range(steps + 1):
            y = self.position[1] + (-self.radius + 2 * self.radius * j / steps) * self.sy
            for i in range(steps + 1):
                x = self.position[0] + (-self.radius + 2 * self.radius * i / steps) * self.sx
                verts.append((x, y, self.height(x, y)))
        stride = steps + 1
        for j in range(steps):
            for i in range(steps):
                k = j * stride + i
                faces.append((k, k + 1, k + stride + 1, k + stride))
        perimeter = ([i for i in range(stride)]
                     + [j * stride + steps for j in range(1, stride)]
                     + [steps * stride + i for i in range(steps - 1, -1, -1)]
                     + [j * stride for j in range(steps - 1, 0, -1)])
        bottom_start = len(verts)
        verts.extend((verts[k][0], verts[k][1], BASE - 80) for k in perimeter)
        for i, k in enumerate(perimeter):
            nxt = (i + 1) % len(perimeter)
            faces.append((k, bottom_start + i, bottom_start + nxt, perimeter[nxt]))
        faces.append(tuple(reversed(range(bottom_start, len(verts)))))
        mesh = bpy.data.meshes.new(self.name + " • DEM mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        mesh.validate(verbose=False)
        obj = bpy.data.objects.new(self.name, mesh)
        sculpt.objects.link(obj)
        mesh.materials.append(material)
        for face in mesh.polygons:
            face.use_smooth = True
        obj["shape_source"] = "Real Kebnekaise DEM patch, artistically rescaled and rotated"
        obj["dem_peak_xyz"] = list(self.template)
        obj["summit_scene_xyz_m"] = list(self.position)
        obj["blender_only_edit"] = True
        return obj


summit = bpy.data.objects["Summit — site coordinates"].location.copy()
climber = bpy.data.objects["Lead climber — site coordinates"].location.copy()
top = peaks[0]
angles = [i * math.tau / 72 for i in range(72)]
front_angle = min(angles, key=lambda a: dem(top[0] + 700 * math.cos(a),
                                           top[1] + 700 * math.sin(a)))
main = Massif("Main massif • sculpt", tuple(summit), top, .95, .5, front_angle, radius=3300, main=True)
# Match the existing climbing face height to a real steep DEM slope. This
# maintains the approach's camera clearance while removing the planar walls.
goal = (climber.z - BASE) / (summit.z - BASE)
distance = min(range(160, 1600, 4), key=lambda r: abs(main.profile(0, r) - goal))
main.sy = (climber.y - summit.y) / distance
massifs = [main]
template_indices = [4, 6, 8, 2, 7, 9, 1, 3]
for i, source in enumerate(sorted(
        [o for o in archive.objects if o.name.startswith("Side ridge")], key=lambda o:o.name)):
    apex = list(source["site_apex_xyz_m"])
    rear = i >= 6
    lateral = 1.0 if rear else (1.7 if i in (2, 5) else 1.25)
    pos = (apex[0] * lateral, apex[2], apex[1])
    massifs.append(Massif(source["original_sculpt_name"], pos, peaks[template_indices[i]],
                         1.05 if rear else .9, 1.05 if rear else .85,
                         front_angle + [1.1, -.8, .45, 2.1, -1.2, .9, -.5, 1.8][i],
                         radius=3700 if rear else 3000))

# Check the preserved camera path against the new terrain before saving.
clearances = []
for frame in range(1, 102):
    scene.frame_set(frame)
    cam = scene.camera.location
    surface = max(m.height(cam.x, cam.y, detail=False) for m in massifs)
    clearances.append(cam.z - surface)
if min(clearances) < 35:
    raise RuntimeError(f"Camera too close to rebuilt terrain: {min(clearances):.1f} m")
print(f"CAMERA_CLEARANCE minimum={min(clearances):.1f} m main_depth_scale={main.sy:.3f}")

objects = [m.mesh(240 if m.main else 144) for m in massifs]
for obj in bpy.data.objects:
    if obj.name.startswith("Rope team") or obj.name == "Lead climber — site coordinates":
        obj.location.z = main.height(obj.location.x, obj.location.y) + 2

scene["art_direction"] = "Natural DEM ridges and valleys; larger surrounding massifs; Blender-only editing."
scene["shape_source_note"] = "Real elevation patches artistically transformed; not a geographically accurate reconstruction."
bpy.ops.object.select_all(action="DESELECT")
objects[0].select_set(True)
bpy.context.view_layer.objects.active = objects[0]
scene.frame_set(37)
scene.render.resolution_percentage = 100
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.shading.type = "RENDERED"
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
print(f"WROTE_BLEND {OUTPUT}")
for frame in (26, 37, 56):
    scene.frame_set(frame)
    scene.render.resolution_percentage = 75
    scene.render.filepath = str(HERE / f"intro_mountain_natural_preview_{frame:02}.png")
    bpy.ops.render.render(write_still=True)
    print(f"WROTE_PREVIEW frame={frame} path={scene.render.filepath}")
