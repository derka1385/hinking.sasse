# Hiking Club intro — editable mountain

Open `intro_mountain_isolated.blend` for the current version. It preserves the user's latest central sculpture, including unsaved edits captured from the open Blender scene, and changes only the eight peripheral meshes. They are moved outward by 430–730 m, made taller and more massive, and given steep inner walls and asymmetric rock horns. The user's central geometry, transform, modifiers and material assignments are verified against `intro_mountain_user_sculpt_snapshot.blend`. Select `Main massif • sculpt` and enter Sculpt Mode to continue shaping it. The gneiss image is packed into the `.blend`.

The approached summit stays lower than the surrounding massifs. The real elevation patches are artistically rescaled and rotated to fit the scene; this is not a geographically exact reconstruction of Kebnekaise. The camera animation is preserved. The latest user sculpture already intersects the old close-approach camera path around frames 75–79; this occurs identically in the saved snapshot and peripheral-edit version. Recalibrate that part of the camera before a final animation render.

The original file was seeded from a snapshot of the site's `intro.js`: summit positions, four defining planes for every peak, climber positions, and 101 scroll-camera poses were imported at a scale of one Blender unit per metre. The Blender-only version then raises the surrounding meshes independently of the website. Press Numpad 0 for the intro camera; frames 1–101 correspond to the scroll from beginning to end. Blender uses Z-up, so the original website's Y-up coordinates are converted on import.

Other collections help with editing:

- **SOURCE** holds the original four-plane volumes, hidden by default.
- **CONTEXT** holds a simple valley proxy and light for preview. Its valley mesh is not the full site shader.
- **CAMERA AND CLIMBERS** holds the camera path and markers for the summit and rope teams.
- **REFERENCE** holds the site's real Kebnekaise elevation model (`site/assets/terrain/kebnekaise.png`), hidden and positioned to the side. Enable the collection in the Outliner to compare natural landforms.
- **ARCHIVE** preserves the prior pyramidal sculpt meshes, hidden from view and rendering.

This is a sculptable transfer of the site's mountain layout, not a lossless export of its WebGL raymarcher. The smooth distance-field blends, shader noise, atmospheric fog, snow particles, and browser lighting are approximated or omitted. Editing the `.blend` does **not** alter the live site yet; the next step is an optimized `.glb` export and replacing the site's procedural mountain renderer.

`shape_peripheral_massifs.py` edits the captured user scene and verifies that the central sculpture remains intact. Run it only against `intro_mountain_user_sculpt_snapshot.blend`, since repeating the transforms on an already edited output would compound them. The previous `naturalize_mountains.py`, `enlarge_surrounding_mountains.py`, `extract_intro_geometry.mjs` and `build_intro_mountain.py` are historical construction tools; rebuilding from them would discard the user's latest sculpting.
