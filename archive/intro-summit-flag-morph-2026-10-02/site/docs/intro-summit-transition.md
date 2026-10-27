# Summit flag to page logo

Local preview: http://127.0.0.1:4174/?intro. No deployment or Git push.

The approved Khumbu binary and its broad shape remain intact. `intro-khumbu.js` refines only cells within the summit patch, blending bicubic terrain sampling into the original triangles and adding less than 13 cm of snow relief. The camera collision sampler uses the same height function. Snow material adds filtered wind ridges, packed snow and fine crystal relief. The additional spindrift pass lifts powder along grounded paths and tests against terrain distance.

The flag uses 24 vector strips. Travelling waves stay active during an idle pause. Its printed vertical lockup uses the same SVG symbol as the opening and final title card. Camera position settles at story progress .855; idle drift settles by .885. During .88–.895 the print transfers to the independent SVG lockup. During .895–.995 that exact lockup moves/scales to the final card and changes from paper to ink. The cloth and scene fade independently. The mapping reverses with scroll until the existing intro completion releases WebGL and shows the static card.

Reduced motion skips the 3D sequence and shows the final title card. Existing Skip and Replay behaviour remains available.

Validation: `node site/tools/check_intro.mjs`, `node site/tools/check_khumbu_integration.mjs`, real WebGL2 shader compilation and visual checks in wide and narrow previews. Checks cover archive hashes, unchanged source assets and published atmosphere, summit height queries, triangle budgets, multisample resolves, camera clearance, fixed final camera, and lifecycle fallbacks.
