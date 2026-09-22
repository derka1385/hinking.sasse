#!/usr/bin/env python3
"""Export every SVG in v2/ to PNG (transparent) and to vector PDF.
Goes through headless Chrome: the SVG is inlined in the page, so the PDF stays true vector.
Re-run after any change to gen.py / gen2.py."""

import pathlib, re, subprocess, shutil, sys

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SRC    = pathlib.Path("v2")
PNG_W  = 1024                      # PNG export width
TMP    = pathlib.Path("/tmp/claude-501/-Users-petrinolann/7296ef95-485d-4a61-b8ca-ffd29f9c33ff/scratchpad/exp")

def chrome(*args):
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", *args],
                   capture_output=True)

def page(svg, w, h, pdf=False):
    """Inlined SVG, exact size, no margin."""
    svg = re.sub(r'\s(width|height)="[^"]*"', '', svg, count=2)
    at = f"@page{{size:{w}px {h}px;margin:0}}" if pdf else ""
    return (f'<!DOCTYPE html><meta charset="utf-8"><style>{at}'
            f'html,body{{margin:0;padding:0;background:transparent}}'
            f'svg{{display:block;width:{w}px;height:{h}px}}</style>{svg}')

TMP.mkdir(parents=True, exist_ok=True)
for d in ("exports/png", "exports/pdf"):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)

files = sorted(SRC.glob("*.svg"))
for f in files:
    svg = f.read_text()
    m = re.search(r'viewBox="([\d.\- ]+)"', svg)
    if not m:
        sys.exit(f"pas de viewBox dans {f}")
    _, _, vw, vh = (float(v) for v in m.group(1).split())
    w = PNG_W
    h = round(vh / vw * w)

    html = TMP / (f.stem + ".html")
    html.write_text(page(svg, w, h))
    chrome(f"--screenshot={TMP / (f.stem + '.png')}", f"--window-size={w},{h}",
           "--default-background-color=00000000", "--force-device-scale-factor=1",
           f"file://{html}")
    shutil.move(TMP / (f.stem + ".png"), f"exports/png/{f.stem}.png")

    html.write_text(page(svg, w, h, pdf=True))
    chrome(f"--print-to-pdf={TMP / (f.stem + '.pdf')}", "--no-pdf-header-footer",
           f"file://{html}")
    shutil.move(TMP / (f.stem + ".pdf"), f"exports/pdf/{f.stem}.pdf")
    print(f"{f.stem}: {w}x{h}")
