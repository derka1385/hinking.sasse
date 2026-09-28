#!/usr/bin/env python3
"""Twin-peak marks for the Hiking Club.
Everything derives from three constants: one slope, one gap, one ground line.
The viewBox is cropped to the artwork, with a uniform margin."""

import math

K, YB, GAP, INK = 0.5, 168.0, 13.0, "#111111"

def f(v):  return f"{v:.1f}".rstrip('0').rstrip('.')
def poly(p): return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in p) + " Z"

def peak(ax, ay):
    """Solid triangle, both feet on the ground line."""
    h = (YB - ay) * K
    return [(ax, ay), (ax + h, YB), (ax - h, YB)]

def cut_left(ax, ay, ex, ey):
    """Clip the left flank with a line of slope +K through (ex, ey). Uniform gap by construction."""
    yi = (ax - ex + K * (ay + ey)) / (2 * K)
    return [(ax, ay), (ax + (YB - ay) * K, YB), (ex + K * (YB - ey), YB), (yi and ax - K * (yi - ay), yi)]

def slot(x_base, width, ytop, ybot=YB - 18.0):
    """Cleft: same slope as the right flank, flat top AND flat base.
    It stops short of the ground line so the mountain keeps a continuous base, and no cleft
    edge lies on the triangle's bottom edge - that overlap produced a hairline seam."""
    dt, db = K * (YB - ytop), K * (YB - ybot)
    return [(x_base - dt, ytop), (x_base - dt + width, ytop),
            (x_base - db + width, ybot), (x_base - db, ybot)]

def ridge(pts, w):
    """Ridge as a constant-width stroke, sharp joins."""
    return (f'<path d="M' + " L".join(f"{f(x)} {f(y)}" for x, y in pts) +
            f'" fill="none" stroke="{INK}" stroke-width="{f(w)}" '
            f'stroke-linejoin="miter" stroke-miterlimit="6" stroke-linecap="butt"/>')

def fitted(name, title, els, pts, pad=16, square=False):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    w, h = x1 - x0, y1 - y0
    if square:
        s = max(w, h); x0 -= (s - w) / 2; y0 -= (s - h) / 2; w = h = s
    body = "".join(f"  {e}\n" for e in els)
    open(name, "w").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(x0)} {f(y0)} {f(w)} {f(h)}" '
        f'role="img" aria-label="Hiking Club — {title}">\n'
        f'  <title>{title}</title>\n{body}</svg>\n')

def fill(d, rule=""):
    return f'<path d="{d}" fill="{INK}"{f" fill-rule={chr(34)}{rule}{chr(34)}" if rule else ""}/>'

# ---- base geometry: tall peak on the right, lower second peak on the left
MX, MY, SX, SY = 134.0, 30.0, 74.0, 84.0
small  = peak(SX, SY)
main   = cut_left(MX, MY, SX + GAP, SY)
faille = slot(x_base=150.0, width=22.0, ytop=98.0)

# 01 - twin peaks
fitted("01-sommets-jumeaux.svg", "01 Sommets jumeaux",
       [fill(poly(main)), fill(poly(small))], main + small)

# 02 - twin peaks + cleft (the 01 x 03 blend)
fitted("02-faille.svg", "02 Faille",
       [fill(poly(main) + " " + poly(faille), "evenodd"), fill(poly(small))], main + small)

# 03 - ridge: the same geometry as a constant-width stroke
R = [(34.0, YB), (74.0, 84.0), (94.0, 124.0), (143.0, 30.0), (212.0, YB)]
fitted("03-arete.svg", "03 Arete", [ridge(R, 15.0)],
       [(x - 8, y - 8) for x, y in R] + [(x + 8, y + 8) for x, y in R])

# 04 - emblem: mark 02 inside an open ring. Framed and centred on the visible ink, not on the
# theoretical circle - the opening at the top would otherwise push the mark visually upwards.
xs = [p[0] for p in main + small]; ys = [p[1] for p in main + small]
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
scale, sw, THETA = 0.56, 13.0, 42.0
r = 0.5 * max(max(xs) - min(xs), max(ys) - min(ys)) * scale + 30
ex = r * math.sin(math.radians(THETA))
ey = -r * math.cos(math.radians(THETA))
ink_top, ink_bot = cy + ey - sw / 2, cy + r + sw / 2
vy = (ink_top + ink_bot) / 2                      # optical centre of the ring
arc = (f'<path d="M {f(cx + ex)} {f(cy + ey)} A {f(r)} {f(r)} 0 1 1 '
       f'{f(cx - ex)} {f(cy + ey)}" fill="none" stroke="{INK}" '
       f'stroke-width="{f(sw)}" stroke-linecap="round"/>')
grp = (f'<g transform="translate({f(cx)} {f(vy)}) scale({scale}) translate({f(-cx)} {f(-cy)})">'
       f'{fill(poly(main) + " " + poly(faille), "evenodd")}{fill(poly(small))}</g>')
fitted("04-embleme.svg", "04 Embleme", [arc, grp],
       [(cx - r - sw / 2, ink_top), (cx + r + sw / 2, ink_bot)], pad=10, square=True)

# 05 - horizontal lockup, built on mark 02: mark | rule | HIKING over CLUB, as on the site
FONT = "Futura, Avenir Next, Helvetica Neue, Inter, sans-serif"
mx0, my0, mx1, my1 = min(xs), min(ys), max(xs), max(ys)
MH = 100.0
sc = MH / (my1 - my0)
mw = (mx1 - mx0) * sc
mark = (f'<g transform="translate(0 0) scale({sc:.4f}) translate({f(-mx0)} {f(-my0)})">'
        f'{fill(poly(main) + " " + poly(faille), "evenodd")}{fill(poly(small))}</g>')
rule = f'<rect x="{f(mw + 30)}" y="2" width="1.5" height="{f(MH - 4)}" fill="{INK}"/>'
tx = mw + 58
TW = 122.5   # HIKING at 29 px with 3.2 px tracking; CLUB is tracked out to the same width
txt = "".join(f'<text x="{f(tx)}" y="{y}" textLength="{f(TW)}" lengthAdjust="spacing" '
              f'font-family="{FONT}" font-size="29" font-weight="400" fill="{INK}">{w}</text>'
              for w, y in [("HIKING", 42), ("CLUB", 85)])
fitted("05-lockup.svg", "05 Lockup", [mark, rule, txt],
       [(0, 0), (mw, MH), (tx + TW, MH)], pad=14)
print("ok")
