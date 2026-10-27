"""Renders scroll positions for comparison with the site: blender -b <blend> --python render_check.py -- <out dir> <percent> <samples> p1 p2 ..."""
import bpy, sys, os, math
a = sys.argv[sys.argv.index('--') + 1:]
out, pct, spp, ps = a[0], int(a[1]), int(a[2]), [float(x) for x in a[3:]]
sc = bpy.context.scene
sc.render.resolution_percentage = pct
sc.eevee.taa_render_samples = spp
os.makedirs(out, exist_ok=True)
for p in ps:
    fr = p * (sc.frame_end - 1) + 1
    sc.frame_set(int(math.floor(fr)), subframe=fr - math.floor(fr))
    sc.render.filepath = os.path.join(out, f'p{p:.3f}.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', p, flush=True)
