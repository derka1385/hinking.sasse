"""Build an editable Blender scene from intro_mountain_source.json.

Run with Blender's Python, after extract_intro_geometry.mjs:
  blender --background --python site/blender/build_intro_mountain.py

The apexes, four defining planes, climber positions, and camera path come from
the current website. WebGL's distance-field blends, animated noise and fog do
not have a lossless mesh equivalent; this file provides sculptable geometry and
a close material starting point rather than a pixel-identical shader capture.
"""

import json
import math
from array import array
from pathlib import Path

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
SOURCE = json.loads((HERE / "intro_mountain_source.json").read_text())
ROCK_IMAGE = HERE.parent / "assets" / "img" / "intro-kebnekaise-rock.webp"
OUTPUT = HERE / "intro_mountain_editable.blend"
PREVIEW = HERE / "intro_mountain_preview.png"
REAL_DEM = HERE.parent / "assets" / "terrain" / "kebnekaise.png"
BASE_Y = -680.0


def site_to_blender(v):
    # The website is Y-up; Blender is Z-up. Site depth becomes Blender Y.
    return Vector((v[0], v[2], v[1]))


def collection(name):
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for item in list(bpy.data.collections):
        if item.users == 0:
            bpy.data.collections.remove(item)


def plane_polygon(apex, normals):
    """Intersect the four exact website half-spaces with a low base plane."""
    sx, sy, sz = apex
    corners = []
    for i in range(len(normals)):
        for j in range(i + 1, len(normals)):
            ax, ay, az = normals[i]
            bx, by, bz = normals[j]
            det = ax * bz - bx * az
            if abs(det) < 1e-8:
                continue
            ar = ay * (sy - BASE_Y)
            br = by * (sy - BASE_Y)
            dx = (ar * bz - br * az) / det
            dz = (ax * br - bx * ar) / det
            if all(n[0] * dx + n[1] * (BASE_Y - sy) + n[2] * dz < 0.001 for n in normals):
                p = (sx + dx, BASE_Y, sz + dz)
                if not any(math.dist(p, old) < 0.01 for old in corners):
                    corners.append(p)
    if len(corners) < 3:
        raise ValueError(f"Could not close pyramid at {apex}: {len(corners)} base corners")
    corners.sort(key=lambda p: math.atan2(p[2] - sz, p[0] - sx))
    return corners


def pyramid_mesh(spec, parent):
    apex, normals = spec["apex"], spec["normals"]
    corners = plane_polygon(apex, normals)
    points = [apex, *corners]
    vertices = [site_to_blender(v) for v in points]
    faces = []
    for i in range(len(corners)):
        j = (i + 1) % len(corners)
        face = [0, i + 1, j + 1]
        # Blender's axis permutation changes winding. Orient each face toward
        # the matching source half-space's outward normal.
        mid = tuple((points[i + 1][k] + points[j + 1][k]) * 0.5 for k in range(3))
        source_normal = min(normals, key=lambda n: abs(sum((mid[k] - apex[k]) * n[k] for k in range(3))))
        actual = (vertices[face[1]] - vertices[face[0]]).cross(vertices[face[2]] - vertices[face[0]])
        if actual.dot(site_to_blender(source_normal)) < 0:
            face.reverse()
        faces.append(face)
    base = list(range(1, len(corners) + 1))
    actual = (vertices[base[1]] - vertices[base[0]]).cross(vertices[base[2]] - vertices[base[0]])
    if actual.z > 0:
        base.reverse()
    faces.append(base)
    mesh = bpy.data.meshes.new(spec["name"] + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(spec["name"], mesh)
    parent.objects.link(obj)
    obj["site_apex_xyz_m"] = list(apex)
    obj["site_face_normals"] = json.dumps(normals)
    obj["source_js_sha256"] = SOURCE["sourceSha256"]
    return obj


def make_rock_material():
    if not ROCK_IMAGE.exists():
        raise FileNotFoundError(ROCK_IMAGE)
    image = bpy.data.images.load(str(ROCK_IMAGE), check_existing=True)
    image.pack()
    mat = bpy.data.materials.new("Nordic gneiss • rock / sparse snow")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    links = mat.node_tree.links

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (920, 100)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (680, 100)
    bsdf.inputs["Roughness"].default_value = 0.88
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    geo = nodes.new("ShaderNodeNewGeometry")
    geo.location = (-960, 220)
    coords = nodes.new("ShaderNodeVectorMath")
    coords.operation = "SCALE"
    coords.inputs[3].default_value = 0.0125  # one photo repeat per 80 metres
    coords.location = (-720, 330)
    links.new(geo.outputs["Position"], coords.inputs[0])
    rock = nodes.new("ShaderNodeTexImage")
    rock.image = image
    rock.projection = "BOX"
    rock.projection_blend = 0.2
    rock.extension = "REPEAT"
    rock.location = (-480, 350)
    links.new(coords.outputs["Vector"], rock.inputs["Vector"])

    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 0.6
    tint.inputs[2].default_value = (0.72, 0.68, 0.62, 1)
    tint.location = (-230, 330)
    links.new(rock.outputs["Color"], tint.inputs[1])

    height = nodes.new("ShaderNodeSeparateXYZ")
    height.location = (-740, -110)
    links.new(geo.outputs["Position"], height.inputs[0])
    altitude = nodes.new("ShaderNodeMapRange")
    altitude.inputs["From Min"].default_value = 350
    altitude.inputs["From Max"].default_value = 1250
    altitude.clamp = True
    altitude.location = (-500, -100)
    links.new(height.outputs["Z"], altitude.inputs["Value"])
    slope = nodes.new("ShaderNodeSeparateXYZ")
    slope.location = (-740, -310)
    links.new(geo.outputs["Normal"], slope.inputs[0])
    ledge = nodes.new("ShaderNodeMapRange")
    ledge.inputs["From Min"].default_value = 0.48
    ledge.inputs["From Max"].default_value = 0.82
    ledge.clamp = True
    ledge.location = (-500, -290)
    links.new(slope.outputs["Z"], ledge.inputs["Value"])
    snow_mask = nodes.new("ShaderNodeMath")
    snow_mask.operation = "MULTIPLY"
    snow_mask.location = (-250, -100)
    links.new(altitude.outputs["Result"], snow_mask.inputs[0])
    links.new(ledge.outputs["Result"], snow_mask.inputs[1])

    snow_mix = nodes.new("ShaderNodeMixRGB")
    snow_mix.blend_type = "MIX"
    snow_mix.inputs[2].default_value = (0.79, 0.81, 0.80, 1)
    snow_mix.location = (220, 250)
    links.new(snow_mask.outputs[0], snow_mix.inputs[0])
    links.new(tint.outputs[0], snow_mix.inputs[1])
    links.new(snow_mix.outputs[0], bsdf.inputs["Base Color"])

    fracture = nodes.new("ShaderNodeTexNoise")
    fracture.inputs["Scale"].default_value = 0.16
    fracture.inputs["Detail"].default_value = 3.0
    fracture.location = (-200, -450)
    links.new(geo.outputs["Position"], fracture.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.32
    bump.location = (400, -210)
    links.new(fracture.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def sculpt_copy(source, parent, material, texture, index):
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = source.name + " • sculpt"
    parent.objects.link(obj)
    obj.data.materials.append(material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.subdivide(number_cuts=48, smoothness=0)
    bpy.ops.object.mode_set(mode="OBJECT")
    for p in obj.data.polygons:
        p.use_smooth = True
    mod = obj.modifiers.new("Broad rock fracture • editable", "DISPLACE")
    mod.texture = texture
    mod.texture_coords = "GLOBAL"
    mod.strength = 14.0 if index < 3 else 18.0
    mod.mid_level = 0.5
    bpy.ops.object.modifier_apply(modifier=mod.name)
    obj["source_primitive"] = source.name
    return obj


def fuse_main_massif(parts):
    """Turn the three overlapping shader masses into one sculptable ridge."""
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = parts[0]
    obj.name = "Main massif • sculpt"
    obj.data.remesh_voxel_size = 18.0
    bpy.ops.object.voxel_remesh()
    smooth = obj.modifiers.new("Soften connected shoulders", "SMOOTH")
    smooth.factor = 0.75
    smooth.iterations = 10
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj["source_primitive"] = "Main summit + West shoulder + East shoulder"
    return obj


def make_context(parent, material):
    # A light proxy to establish the valley in Blender; the browser has a
    # separate, more detailed analytic ground shader.
    n = 50
    verts = []
    faces = []
    for iz in range(n + 1):
        z = -800 + iz * 6000 / n
        for ix in range(n + 1):
            x = -3000 + ix * 6000 / n
            d = (z - 3470 - 60 * math.sin(x / 260)) / 150
            moraine = 36 * math.exp(-(d * d))
            t = max(0, min(1, (2900 - z) / 2600))
            rise = 150 * t * t * (3 - 2 * t)
            y = -SOURCE["valleyDepth"] - .075 * max(z - 250, 0) + moraine + rise
            y += 2.5 * math.sin(x / 37 + 1.3) * math.sin(z / 53) + 1.8 * math.sin(z / 91 + x / 140)
            verts.append((x, z, y))
    for iz in range(n):
        for ix in range(n):
            a = iz * (n + 1) + ix
            faces.append((a, a + 1, a + n + 2, a + n + 1))
    mesh = bpy.data.meshes.new("Valley preview mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Valley floor • preview proxy", mesh)
    parent.objects.link(obj)
    obj.data.materials.append(material)
    obj["export_to_website"] = False
    return obj


def make_real_dem_reference(parent, material):
    """Keep the site's real Kebnekaise heightmap nearby as a sculpt reference."""
    if not REAL_DEM.exists():
        return None
    image = bpy.data.images.load(str(REAL_DEM), check_existing=True)
    image.colorspace_settings.name = "Non-Color"
    width, height = image.size
    pixels = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(pixels)
    image.pack()
    spec = json.loads((HERE.parent / "data" / "derived.json").read_text())["terrain"]["kebnekaise"]
    lo, hi = spec["min"], spec["max"]
    km_x, km_y = spec["km"]
    stride = 2
    cols = list(range(0, width, stride))
    rows = list(range(0, height, stride))
    vertices, faces = [], []
    for y in rows:
        for x in cols:
            offset = (y * width + x) * 4
            red = round(pixels[offset] * 255)
            green = round(pixels[offset + 1] * 255)
            altitude = lo + ((red * 256 + green) / 65535) * (hi - lo)
            vertices.append((17000 + (x / (width - 1) - .5) * km_x * 1000,
                             (y / (height - 1) - .5) * km_y * 1000,
                             altitude - lo - 300))
    row_width = len(cols)
    for y in range(len(rows) - 1):
        for x in range(row_width - 1):
            a = y * row_width + x
            faces.append((a, a + 1, a + row_width + 1, a + row_width))
    mesh = bpy.data.meshes.new("Real Kebnekaise DEM mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("REAL Kebnekaise • DEM reference", mesh)
    parent.objects.link(obj)
    obj.data.materials.append(material)
    obj["height_source"] = "site/assets/terrain/kebnekaise.png"
    obj["altitude_range_m"] = [lo, hi]
    obj["width_km"] = km_x
    obj["depth_km"] = km_y
    obj["export_to_website"] = False
    return obj


def make_camera(parent):
    data = bpy.data.cameras.new("Intro scroll camera")
    data.type = "PERSP"
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.clip_start = 0.03
    data.clip_end = 30000
    cam = bpy.data.objects.new("Intro scroll camera", data)
    parent.objects.link(cam)
    for i, sample in enumerate(SOURCE["cameraSamples"]):
        frame = i + 1
        pos = site_to_blender(sample["pos"])
        tgt = site_to_blender(sample["tgt"])
        cam.location = pos
        cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        data.lens = data.sensor_height / (2 * math.tan(math.radians(sample["fov"]) * .5))
        cam.keyframe_insert(data_path="location", frame=frame)
        cam.keyframe_insert(data_path="rotation_euler", frame=frame)
        data.keyframe_insert(data_path="lens", frame=frame)
    bpy.context.scene.camera = cam
    return cam


def make_guide(parent, name, xyz, size):
    obj = bpy.data.objects.new(name, None)
    parent.objects.link(obj)
    obj.location = site_to_blender(xyz)
    obj.empty_display_type = "SPHERE"
    obj.empty_display_size = size
    obj.hide_render = True
    return obj


def make_sun(parent):
    data = bpy.data.lights.new("Nordic afternoon", "SUN")
    data.energy = 2.8
    data.color = (1.0, .91, .80)
    data.angle = math.radians(3.5)
    obj = bpy.data.objects.new("Nordic afternoon", data)
    parent.objects.link(obj)
    toward = site_to_blender((-.72, -.32, .40))
    obj.rotation_euler = toward.to_track_quat("-Z", "Y").to_euler()


def main():
    clear_scene()
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.frame_start = 1
    scene.frame_end = 101
    scene.render.fps = 30
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.35
    scene.world.color = (.35, .38, .42)
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.35, .38, .42, 1)
    background.inputs["Strength"].default_value = 0.9

    sculpt = collection("01 • SCULPT — website mountain")
    sources = collection("02 • SOURCE — exact shader planes")
    context = collection("03 • CONTEXT — preview only")
    guides = collection("04 • CAMERA AND CLIMBERS")
    real_dem = collection("05 • REFERENCE — real Kebnekaise DEM")
    rock_material = make_rock_material()
    cloud_texture = bpy.data.textures.new("Broad mountain relief • 180 m", type="CLOUDS")
    cloud_texture.noise_scale = 180
    cloud_texture.noise_depth = 3

    specs = SOURCE["main"] + SOURCE["peaks"]
    sculpt_objects = []
    for i, spec in enumerate(specs):
        primitive = pyramid_mesh(spec, sources)
        sculpt_objects.append(sculpt_copy(primitive, sculpt, rock_material, cloud_texture, i))
    sculpt_objects = [fuse_main_massif(sculpt_objects[:3]), *sculpt_objects[3:]]
    sources.hide_viewport = True
    sources.hide_render = True

    make_context(context, rock_material)
    make_real_dem_reference(real_dem, rock_material)
    real_dem.hide_viewport = True
    real_dem.hide_render = True
    make_sun(context)
    make_camera(guides)
    make_guide(guides, "Summit — site coordinates", SOURCE["summit"], 35)
    make_guide(guides, "Lead climber — site coordinates", SOURCE["climber"], 12)
    for i, xyz in enumerate(SOURCE["team"], 1):
        make_guide(guides, f"Rope team {i:02}", xyz, 5)

    scene["intro_source_sha256"] = SOURCE["sourceSha256"]
    scene["conversion_note"] = "Exact plane/apex/camera placement; editable mesh relief and Blender material approximate the live raymarch shader."
    scene.frame_set(37)
    bpy.ops.object.select_all(action="DESELECT")
    sculpt_objects[0].select_set(True)
    bpy.context.view_layer.objects.active = sculpt_objects[0]
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
    print(f"WROTE_BLEND {OUTPUT}  editable_mountains={len(sculpt_objects)}")
    if "--preview" in __import__("sys").argv:
        scene.render.resolution_percentage = 50
        scene.render.filepath = str(PREVIEW)
        bpy.ops.render.render(write_still=True)
        print(f"WROTE_PREVIEW {PREVIEW}")


if __name__ == "__main__":
    main()
