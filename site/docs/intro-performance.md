# Intro: ground and rendering performance

The forest floor uses photographed moss, needles and earth, with filtered world-space texture
coordinates and baked contact shade. Tree bases, camera height and terrain now share one analytic
surface. Forest intersections take six refinement steps instead of the general raymarcher.

Cloud integration runs once at quarter resolution into eight cumulative depth layers, which both
terrain and trees sample. The original fog opening retains its original integration. Four-target
hardware uses two cloud draws. Empty-space mountain bounds skip texture sampling, distant shadows
use less work, and material shading reuses the final hit rather than recalculating its rock noise.
Tree culling/sorting and uploads are cached until the camera changes. Settled atmosphere renders
at up to 30 Hz, moving cameras follow native refresh, and hidden/completed scenes stop.

## Local comparison

Measured in the Codex in-app browser on this Mac, using a fixed **1500 × 825** render and output
buffer, quality 2, the same camera progress, and 120 rolling samples after warmup. The profiler
runs only when explicitly requested. Figures are diagnostic timings for this session, not a
frame-rate guarantee for other devices. GPU values are per-query readings and are not added.

| Camera / metric | Baseline | Optimized |
|---|---:|---:|
| Forest (`p=0.30`), CPU submission mean | 1.27 ms | 0.29 ms |
| Forest, terrain GPU query mean | 17.44 ms | 1.59 ms |
| Forest, trees/snow GPU query mean | 20.56 ms | 2.92 ms |
| Forest, new shared cloud query mean | — | 0.94 ms |
| Mountain (`p=0.61`), CPU submission mean | 0.32 ms | 0.26 ms |
| Mountain, terrain GPU query mean | 22.06 ms | 16.99 ms |

Presentation in this browser stayed around 30 frames/s in the fixed-camera runs, despite the
lower GPU workload. Moving and idle scheduling are tested separately; the measurements do not
claim an increased display refresh rate.

The tree atlas dropped from **1,515,804 to 674,702 bytes** (55.5% smaller). Every alpha pixel is
preserved. The new ground material is 803,540 bytes: both textures together are 1,478,242 bytes,
slightly below the former tree atlas alone. The grain layer's bounds dropped from 9 viewport areas
to 1.54; its overscan still covers every authored translation.

## Reproduce and validate

Serve the project root only on loopback:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
node site/tools/check_intro.mjs
```

Open `/?p=0.30&profile=1500x825` or `/?p=0.61&profile=1500x825`. Wait for warmup and read
`data-profile` on `#intro canvas`. This fixes both buffer dimensions independently of browser zoom;
resolution adaptation and the idle cap are disabled for the profiling run. Normal playback is
`/?intro`. `/?p=0.30&cloud4&profile=390x844` exercises the four-buffer shader path.

Checks passed: shader compilation and rendering at normal size; eight layers through the
four-buffer path at 390 × 844; compressed atlas alpha preservation; native refresh while moving;
idle cap; resize invalidation; hidden-page suspension/resume; completion and listener removal;
reverse scroll; skip; reload; reduced motion; unavailable WebGL; blocked storage; finite, continuous
camera curves. Lifecycle/camera tests use a mocked WebGL context; browser checks validate the
actual shaders. The viewport override is reset after checking.
