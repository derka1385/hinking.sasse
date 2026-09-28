#!/usr/bin/env python3
"""Official logo + dark square variants.
Reuses the geometry of gen.py (mark 02) and the SASSE lockup structure:
emblem -> rule -> name in widely tracked caps, centred. Proportions measured off the SASSE logo:
rule width = 59 % of the name line, emblem width = 55 %."""

from gen import K, YB, f, poly, main, small, faille, fill   # same geometry, same constants

INK  = "#1D1D1B"                     # warm printing black, like the SASSE logo
FONT = "Futura, Avenir Next, Helvetica Neue, Inter, sans-serif"

MX0, MY0 = min(p[0] for p in main + small), min(p[1] for p in main + small)
MX1, MY1 = max(p[0] for p in main + small), max(p[1] for p in main + small)
MW, MH = MX1 - MX0, MY1 - MY0        # artwork box, in design space

def mark(h, cx, top, ink=INK, faille_ink=None):
    """Mark 02 at height h, centred on cx, apex at top.
    faille_ink=None -> the cleft is a real hole, the background shows through."""
    s = h / MH
    tr = f'translate({f(cx - MW * s / 2)} {f(top)}) scale({s:.5f}) translate({f(-MX0)} {f(-MY0)})'
    if faille_ink:
        inner = (f'<path d="{poly(main)}" fill="{ink}"/><path d="{poly(faille)}" fill="{faille_ink}"/>'
                 f'<path d="{poly(small)}" fill="{ink}"/>')
    else:
        inner = (f'<path d="{poly(main)} {poly(faille)}" fill="{ink}" fill-rule="evenodd"/>'
                 f'<path d="{poly(small)}" fill="{ink}"/>')
    return f'<g transform="{tr}">{inner}</g>', MW * s

def line(cx, y, w, size, weight, txt, ink=INK):
    return (f'<text x="{f(cx - w / 2)}" y="{f(y)}" textLength="{f(w)}" lengthAdjust="spacing" '
            f'font-family="{FONT}" font-size="{f(size)}" font-weight="{weight}" fill="{ink}">{txt}</text>')

def write(name, w, h, els, bg=None):
    rect = f'  <rect width="{f(w)}" height="{f(h)}" fill="{bg}"/>\n' if bg else ""
    open(name, "w").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" width="{f(w)}" '
        f'height="{f(h)}" role="img" aria-label="Hiking Club">\n{rect}'
        + "".join(f"  {e}\n" for e in els) + '</svg>\n')

# ---------- primary logo, vertical, SASSE structure ----------
# HIKING CLUB is much shorter than the working title, so it is set larger (30 px, was 22) on a
# narrower line (280, was 340); the tracking is whatever fills the line. Same as the site lockup.
NAME_W = 280.0                       # width of the name line = reference for the whole system
NAME_PX, CAP = 30.0, 0.761           # Futura Medium cap height = 0.761 em
RULE_W = NAME_W * 0.59
MARK_H = NAME_W * 0.55 / (MW / MH)
PAD, CX = 26.0, NAME_W / 2 + 26.0

def principal(name, ink, bg=None):
    y = PAD
    m, _ = mark(MARK_H, CX, y, ink, None)
    y += MARK_H
    base = y + 22 + 1.8 + 20 + NAME_PX * CAP        # 20 of air between the rule and the caps
    els = [m,
           f'<rect x="{f(CX - RULE_W / 2)}" y="{f(y + 22)}" width="{f(RULE_W)}" height="1.8" fill="{ink}"/>',
           line(CX, base, NAME_W, NAME_PX, 400, "HIKING CLUB", ink)]
    write(name, NAME_W + 2 * PAD, base + PAD, els, bg)

principal("logo.svg", INK)
principal("logo-blanc.svg", "#F4F2EE", None)   # reversed version, for dark backgrounds

# ---------- mark on its own, transparent: the most used variant
for nom, encre, teinte in [("marque.svg", INK, None),
                           ("marque-blanc.svg", "#F4F2EE", None),
                           ("marque-ambre.svg", "#F4F2EE", "#D98E3C")]:
    H = 200.0
    g, w = mark(H, MW * H / MH / 2, 0.0, encre, teinte)
    write(nom, w, H, [g])

# ---------- dark squares, one tint per variant ----------
S = 512.0
TILES = [
    ("carre-01-encre.svg",   "#131312", "#F4F2EE", None,      "Encre"),
    ("carre-02-navy.svg",    "#0B1B2E", "#EAF1F7", None,      "Navy nuit"),
    ("carre-03-glacier.svg", "#0D2233", "#86C4E3", None,      "Glacier"),
    ("carre-04-pin.svg",     "#0E241D", "#E9F1EB", "#74B096", "Pin"),
    ("carre-05-ambre.svg",   "#17130F", "#F2EDE5", "#D98E3C", "Ambre"),
    ("carre-06-ardoise.svg", "#101418", "#5F90A9", None,      "Ardoise"),
]
for i, (name, bg, ink, tint, _) in enumerate(TILES):
    signed = i >= 4                       # two tiles carry the name, the others stay mark-only
    m, w = mark(210.0, S / 2, S * 0.20 if signed else S * 0.285, ink, tint)
    els = [m] + ([line(S / 2, S * 0.735, 150, 16, 500, "HIKING CLUB", ink)] if signed else [])
    write(name, S, S, els, bg)
print("logo + %d carres" % len(TILES))
