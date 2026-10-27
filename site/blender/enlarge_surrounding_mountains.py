"""Enlarge the surrounding ridges in an existing .blend, without editing the site.

Run with Blender, after opening intro_mountain_editable.blend in background:
  blender --background intro_mountain_editable.blend --python enlarge_surrounding_mountains.py

The source file is kept intact. The new .blend is the Blender-only art direction
version; both the sculpt meshes and their hidden source guides are updated.
"""

from pathlib import Path

import bpy


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "intro_mountain_blender_scale.blend"
PREVIEW = HERE / "intro_mountain_blender_scale_preview.png"
BASE_HEIGHT = -680.0

# The approached main summit stays at roughly 1,205 m. Foreground ridges 03
# and 06 remain lower, while the flanks rise in stages toward the taller back
# ridges 07 and 08 (already 2,050 m and 2,230 m in this .blend).
TARGET_HEIGHTS = {
    "01": 1450.0,
    "02": 1550.0,
    "04": 1550.0,
    "05": 1650.0,
}


def enlarge_ridge(index, target_height):
    for suffix in ("", " • sculpt"):
        name = f"Side ridge {index}{suffix}"
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError(f"Missing editable mountain mesh: {name}")
        apex = list(obj["site_apex_xyz_m"])
        original_height = float(apex[1])
        factor = (target_height - BASE_HEIGHT) / (original_height - BASE_HEIGHT)
        for vertex in obj.data.vertices:
            vertex.co.z = BASE_HEIGHT + (vertex.co.z - BASE_HEIGHT) * factor
        obj.data.update()
        apex[1] = target_height
        obj["site_apex_xyz_m"] = apex
        obj["blender_only_height_edit_m"] = target_height - original_height
        print(f"RAISED {name}: {original_height:.0f} -> {target_height:.0f} m")


for ridge_index, height in TARGET_HEIGHTS.items():
    enlarge_ridge(ridge_index, height)

scene = bpy.context.scene
scene["art_direction"] = "Surrounding mountains enlarged in Blender only; website geometry is unchanged."
scene.frame_set(37)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
print(f"WROTE_BLEND {OUTPUT}")

scene.render.resolution_percentage = 50
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"WROTE_PREVIEW {PREVIEW}")
