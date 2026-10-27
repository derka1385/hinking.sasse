# Intro V2 (GitHub version) in Blender

`intro_v2_scroll.blend` is the scroll intro that is live on GitHub Pages (`hiking/main`, `site/assets/js/intro.js`,
V2 commit `5f2cc49`), rebuilt in Blender 5.2 so the mountains can be edited.

## Opening it

- Frame 1 to 361 = scroll progress 0 to 1 (`p = (frame − 1) / 360`), 24 fps, so 15 s for the whole scroll.
- The viewport opens through `Intro camera • scroll` in Solid mode (for editing); Z → Rendered shows the
  site's look (heavy: 10.8 M triangles and a cloud volume).
- Render: Eevee, 3024 × 1964 (the Retina screen), output `//renders/intro_####.png`.
  The compositor applies the site's grade, then the snow, then the grain: always check in a real render (F12),
  not the viewport.

## What is exact and what is not

Taken from the site's own shader, run on the GPU (`sampler.html`), with no reinterpretation:

- **Mountain geometry**: the site's distance field (`massif()` + `ground()`), meshed at the level of detail
  the site shows. Each area is meshed as finely as the scroll camera ever sees it: 25 cm near the climber,
  8 m on the faces seen from far away (`lod_level` attribute, 0 = finest, 10 = coarsest). 10.8 M triangles.
- **Camera**: the same keys, Catmull-Rom, field of view and hand-held drift (baked per frame).
- **Atmosphere**: fog, fog colour, sun and exposure keyed per frame from `LOOKS` (scene custom properties
  `fog_col`, `fog_den`, `sun_col`, `sun_dir`, `cloud`…). Height fog, lighting, ACES, gamma, cold shadows,
  vignette, paper whiteout: the same formulas, in the materials and the compositor.
- **Noise**: the site's 128³ noise texture itself (`noise_atlas.png`, packed). Clouds, rock tint, dusting,
  snow patches and the snow crust are computed per pixel with it, so they follow any edit.
- **Snow flakes**: the same box around the camera, wind and streaks, drawn over everything after the grade
  (separate `Snow` view layer), as on the site. The CSS grain is added the same way.

Differences you may notice:

- The site changes its terrain with distance (fewer rock octaves far away, the couloir only carved up
  close). A mesh has one shape: it keeps the most detailed version the site ever shows of each area. The couloir
  is the exception: the shape key `Couloir filled (far)` fills it with snow from far away and is keyed to open it
  between 1,400 and 900 m, as the site does. If you sculpt the couloir area, do it on `Basis` and check the key.
- AO and the snow in gullies, in the couloir and on the valley floor are baked per vertex. After a large
  sculpt they stay where they were; slope-based snow and noise update by themselves.
- The climber is at rest (the site swings the axe every 7 s); the rope is a curve. Both are fattened per frame to
  the site's pixel (0.75 px for the climber, 0.6 px for the rope), as the site does, so they read the same size.

## Editing the mountains

- `Mountains` is one mesh. Sculpt Mode with a large Grab/Snake Hook radius, or Edit Mode with proportional
  editing (O), for the big shapes. Select by attribute `lod_level` to isolate a detail band.
- `Valley floor` is the far terrain (12 m grid).
- For a change that the site must also get, change the pyramids in `intro.js` instead and rebuild:

```sh
git show hiking/main:site/assets/js/intro.js > intro_live.js   # or the edited intro.js
node extract.mjs 360                                            # camera, atmosphere, shader
python mesh.py <data dir>                                       # numpy + scikit-image, ~15 min on the GPU
blender -b --factory-startup --python build_blend.py -- <data dir> intro_v2_scroll.blend grain
```

`grain.py` and `noise_atlas.py` rebuild the grain and noise images; `render_check.py` and `compare.py`
render scroll positions and put them next to site screenshots.
