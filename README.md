# Hiking Club — visual identity

Brand assets for the Hiking Club at SASSE (Stockholm School of Economics Student Association).
Formerly working-titled Mountaineering Club. Everything here derives from one geometry, generated
by script rather than drawn by hand, so every variant shares exactly the same angles and the same
spacing.

The website lives in [`site/`](site/) (see [site/README.md](site/README.md)).

| | |
|---|---|
| **[brand.html](brand.html)** | The identity guide: mark, clear space, minimum sizes, misuse, colour, type, applications |
| **[logo.html](logo.html)** | The official logo and the dark square variants |
| **[symbol-study.html](symbol-study.html)** | The symbol study that led to the chosen mark |
| **[tokens.css](tokens.css)** | The single source for colour, type and spacing values |

## The mark

Three constants drive the whole drawing: a slope of `K = 0.5` (2:1 on every face), a gap of `13`,
and a ground line at `168`. Nothing is positioned by eye — the cuts are computed as line
intersections, so the distance between the two peaks is rigorously constant. That is what gives
the mark its architectural read.

The right-hand peak carries a **cleft**, which is the club's signature device: it is the one place
colour is allowed to enter. Everything else stays ink, paper or navy.

The cleft stops 18 units short of the ground line. This matters: when it ran all the way down, its
bottom edge coincided with the bottom edge of the triangle, which produced an antialiasing seam,
and the white band beside it detached visually — it read as a leftover fragment of the first
mountain showing through the second. Closing it keeps the mountain one continuous mass.

## Rules worth knowing before you use these files

- **Clear space** = 13 % of the width of whatever you place. That ratio is the width of the cleft
  over the width of the mark, so the margin scales with the logo and never needs recalculating.
- **Minimum sizes**, measured by rendering at real size rather than estimated: vertical logo
  **44 px** tall, horizontal lockup **30 px**, mark on its own **16 px**. For embroidery, allow
  45 mm wide for the mark — below that the needle fills the cleft in.
- **Amber is banned for text on light backgrounds.** Calculated contrast is 2.38:1, which fails
  WCAG. On navy it is 6.51:1 and fine. This is the only genuinely binding colour rule.
- Ink/paper is 15.10:1 and paper/navy 15.52:1, both AAA.

## Type

Futura in print — it draws the wordmark. [Jost](https://fonts.google.com/specimen/Jost) is its free
substitute on the web, within about 2 % on set width. Body text is Inter. Type scale, ratio 1.333:
12 · 14 · 17 · 23 · 31 · 41 · 55.

## Regenerating

```
cd v2 && python3 gen.py && python3 gen2.py   # SVG sources
cd .. && python3 export.py                   # PNG + vector PDF
```

`gen.py` holds the geometry and the symbol studies. `gen2.py` imports it and builds the official
logo and the dark squares, so the two files can never drift apart. `export.py` renders every SVG to
a 1024 px transparent PNG and to a true vector PDF (the SVG is inlined into a page printed by
headless Chrome; no raster image is embedded — the PDFs run 1.8–9.6 KB).

**The SVGs are the source. `exports/` is derived — never edit it, and re-run `export.py` after any
change to the generators.**

## Known debt

- The wordmark in `v2/` is still set with `font-family`, not converted to outlines. A printer or
  an embroiderer will need the letters as paths: use the outlined lockups in `site/assets/img/`
  (`logo-vertical.svg`, `logo-horizontal.svg`), built from the same geometry by
  `site/tools/build_assets.py`. The text-free assets (`marque*.svg`, marks 01–04, tiles 01–04)
  have no font dependency.
- The colour of the club is set to amber `#D98E3C`. Pine and glacier exist as finished tiles if the
  board prefers a different direction; switching is a one-line change in `gen2.py`.
- Nothing yet defines how the club's logo sits alongside the SASSE logo on shared layouts. That
  belongs to the applications phase.
