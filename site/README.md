# Hiking Club — website

One static page, no build step, no dependencies. The page itself is `index.html` at the repo root,
so GitHub Pages serves it at the site's address; everything it loads lives here in `site/`. Open it,
or serve the repo root (`python3 -m http.server`) to get the font preloads as well.

```
../index.html           all content, in reading order
assets/css/site.css     the design system below
assets/js/intro.js      the ascent: WebGL2 raymarcher + snow, scroll-driven camera, wind
assets/js/site.js       reveals, navigation theme, disciplines, join form
assets/img, map, fonts  derived assets — rebuilt by tools/build_assets.py
tools/build_assets.py   photos (grade + WebP), contour maps (open DEM), logo (Futura outlines), sprite + credits
```

## Before launch — placeholders

| What | Where |
|---|---|
| Club inbox. The form composes an email to it. Swap it for a form endpoint if the board has one | `../index.html`, `data-mailto` on `.join-form` |
| Expedition 004: dates, places left, closing date, distance | `../index.html`, section 02 |
| Archive 001–003: dates, group sizes, distances and notes are illustrative | `../index.html`, section 03 |
| Facts row under the manifesto (004 / 68.35° N / 2,097 m / 1,002 km) follows the archive | `../index.html`, section 01 |

Coordinates, summit heights and the Stockholm–Abisko distance are real.

## Design system

**Colour.** Paper `#F4F2EE` and ink `#1D1D1B` carry the page. Navy `#0B1B2E` is the night: the intro
opens in it, and *What we do*, *Join* and the footer return to it. Slate `#526579` is secondary text on
paper, `#8FA0B3` on navy. Rope `#D98E3C` appears three times: the climber's jacket, the
"registration open" dot, and the hover fill of the one button that commits you. Never use it for text on paper (2.38:1).

**Type.** Newsreader (display cut, opsz 72, weights 300–500) for everything that is read as a
statement: headlines, place names, numbers in the facts row, the three rules. Schibsted Grotesk
(400–600) for everything that is information: labels, body, coordinates. The Futura wordmark exists only as
outlines inside the logo. Labels are 11 px, uppercase, +0.14 em, tabular figures. Scale, fluid:
label 11 · small 13 · body 15–17 · lead 20–28 · h3 30–56 · h2 44–104 · display 52–212 px.

**Grid.** 12 columns, gutter `clamp(14px, 1.7vw, 32px)`, outer margin `clamp(20px, 5.4vw, 104px)` (the brand
boards' 6 %). Section padding `clamp(104px, 11vw, 176px)`. Every section opens with the same row as the
brand boards: number, name, one fact on the right, over a hairline.

**Lines.** Hairlines only, 1 px, ink or paper at 16 %. No shadows, no radii, no gradients in the UI.

**Images.** One documentary grade for all photographs (desaturated, matte floor, cool shadows), done at
build time. Numbered captions (`004.1`, `Plate`). People are small in the frame on purpose.

**Buttons.** Rectangles, 56 px, a label and an arrow. Hover: a second fill rises from the bottom
(ink → navy; paper → rope on the join form). Links: a hairline that retracts.

**Motion.** Everything eases out (`cubic-bezier(.16,1,.3,1)`) over 0.9–1.6 s; nothing bounces. Headlines
rise line by line out of masks. Photographs unmask upwards and settle from 108 %. Archive rows open from
their centre line onto the photograph (a horizon slit). `prefers-reduced-motion` removes all of it.

**Navigation.** Hidden during the ascent, it appears with the page. It takes the theme of the section
under it and underlines the section you are in. Under 860 px it becomes a full-screen serif menu.

## The ascent

A sticky canvas over 640 vh of scroll (520 vh on phones). The camera follows the scrollbar with damping,
so scrolling itself is never hijacked.

| Progress | Chapter | What happens |
|---|---|---|
| 0–0.28 | 01 Whiteout | Navy before dawn. The logo, then cloud streaming past |
| 0.28–0.44 | 02 Emergence | Out of the cloud. The massif appears through the fog |
| 0.44–0.60 | 03 The wall | A 1,150 m north face. A snow couloir cuts it at 2:1, the slope of the mark's cleft |
| 0.60–0.75 | 04 One climber | *Fig. 01* pins a speck in the couloir: one climber, 1.8 m |
| 0.75–0.93 | 04 | The approach, then a low shot up the couloir: rope, ice axes, a jacket in the club's colour |
| 0.93–1.00 | 05 Silence | Past the climber into cloud. The whiteout becomes the paper of the page; the wind stops |

Everything is one full-screen raymarch: the rock is a ridged multifractal stretched along the fall line,
the couloir is carved into the face, and the climber and rope are distance fields. Fog is a height layer plus
drifting cloud, sampled along each ray. Snow is a second, instanced pass of motion-blurred streaks.

Tuning: `KEYS` (camera) and `LOOKS` (atmosphere, keyed by progress) at the top of `intro.js`. `?p=0.62`
freezes the camera at a progress value. `?cam=n,x,y,up,tn,tx,ty,tup,fov` places it in face coordinates,
relative to the climber.

Performance: render resolution adapts live (drops on missed frames, probes back up after a quiet
spell), then soft shadows and AO go. Phones start at lower quality. Rendering stops once the
intro is off screen. On an M4, a 900 × 560 internal frame costs 10–20 ms.

Fallbacks: no WebGL2 → a photograph with the same title; reduced motion → one still frame, no scroll
length. The *Skip intro* link is the first control on the page.

## Credits

Photographs from Wikimedia Commons, graded and cropped. Authors and licences are listed in the
footer and in `tools/credits.json`. Contours come from Mapzen Terrain Tiles (AWS Open Data). Fonts are
Newsreader and Schibsted Grotesk (SIL OFL).
