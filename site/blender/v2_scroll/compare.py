"""Side-by-side sheet: site reference (left) | Blender (right). Blender's python: compare.py <ref dir> <render dir> <out.png> p1 p2 ..."""
import sys, OpenImageIO as oiio
ref, ren, out, ps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
tw, th = 756, 491
sheet = oiio.ImageBuf(oiio.ImageSpec(tw * 2 + 8, (th + 8) * len(ps), 3, oiio.UINT8))
for i, p in enumerate(ps):
    for j, d in enumerate((ref, ren)):
        b = oiio.ImageBuf(f'{d}/p{float(p):.3f}.png')
        sm = oiio.ImageBufAlgo.resize(b, roi=oiio.ROI(0, tw, 0, th, 0, 1, 0, 3))
        oiio.ImageBufAlgo.paste(sheet, j * (tw + 8), i * (th + 8), 0, 0, sm)
sheet.write(out)
