# Mountain approach to storm whiteout

Local preview: http://127.0.0.1:4174/?experience=mountaineering&intro&preview=distant1. This is a local variant; nothing has been committed or pushed.

The previous summit flag and logo morph are preserved under `archive/intro-summit-flag-morph-2026-10-02`. Its manifest covers 67 original files, including the complete intro assets. Compare it at http://127.0.0.1:4174/archive/intro-summit-flag-morph-2026-10-02/index.html?intro.

The current intro keeps the approved Khumbu mesh, summit refinement and published lighting/fog/cloud atmosphere. There is no climber or flag. The camera follows a straight, level route from `[40,740,4900]` to `[40,740,1800]`, aimed at `[80,1000,-340]`, with a fixed 42-degree vertical field of view. Smoothstep travel eases to a stop at story progress .855, without reversing. Small wind drift also settles by .855. The camera remains at least 2,194 scene metres from the registered summit; it never climbs to the summit or adds optical zoom.

The previous close camera source is preserved in `archive/camera-before-distant-approach-2026-10-16/intro.js` for restoration.

A separate moving volumetric bank enters from the side during story progress .65–.855, closing the view while the camera is still far from the mountain. Wind strengthens before the image turns white and drives the snowfall sideways. The bank continues moving when scrolling stops. Camera-relative density has fixed pixel jitter, continuous time advection and 8 narrow-screen or 14 desktop ray samples. Density grows monotonically with forward scroll and reverses before intro completion.

During .89–.975 the scene blends to the site's paper colour. The existing Hiking Club SVG lockup appears during .932–.990, followed by the affiliation and coordinates. Wind gusts end at .960; enabled wind audio fades out during .915–.980. Sound stays off by default. The existing completion path releases WebGL and leaves the final static card; Skip, Replay and reduced-motion behaviour remain available.

Validation: `node --check site/assets/js/intro.js`, `node site/tools/check_intro.mjs`, `node site/tools/check_khumbu_integration.mjs`. These cover lifecycle fallbacks, terrain contracts, preserved atmosphere, monotone whiteout, wind timing and both original archive manifests. The new path is also checked for constant field of view, forward-only movement, distance from the summit, terrain clearance and continuity. Sampled height drift stays below .61 metres and lateral drift below 1.30 metres; minimum terrain clearance is 525.89 metres. The previous shader version was verified with real WebGL2; the new camera framing still needs visual inspection because browser automation is unavailable. Existing screenshots in this folder show the previous, closer camera rather than this distant approach.
