"""Create a continuous alpine saddle beneath the independent sculpt meshes."""
import bpy, math, hashlib
from pathlib import Path
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree

root=Path('/Users/petrinolann/Documents/ChatGPT/hiking sasse/site/blender')
bpy.ops.wm.open_mainfile(filepath=str(root/'intro_mountain_buttress.blend'))
def digest(o):
    return hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices], [tuple(p.vertices) for p in o.data.polygons], tuple(tuple(r) for r in o.matrix_world))).encode()).hexdigest()
original={o.name:digest(o) for o in bpy.data.objects if o.type=='MESH'}
def smooth(a,b,x):
    t=max(0.,min(1.,(x-a)/(b-a))); return t*t*(3-2*t)
names=['Main massif • sculpt','Side ridge 07 • sculpt','Side ridge 08 • sculpt']
trees={n:BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons]) for n in names for o in [bpy.data.objects[n]]}
def height(n,x,y):
    hit=trees[n].ray_cast(Vector((x,y,6000)),Vector((0,0,-1)))
    return hit[0].z if hit[0] else -680.
verts=[]; faces=[]
nx,ny=300,230
for j in range(ny+1):
    y=-9000+11500*j/ny
    left=height(names[1],-2200,y)
    right=height(names[2],2200,y)
    main_axis=height(names[0],0,y)
    # An asymmetric col connects the rocky shoulders, then continues toward
    # the foot of the user's mountain instead of ending in a rectangular pit.
    col=max(-680., (left+right)*.5-1120., main_axis-35.)
    for i in range(nx+1):
        x=-7500+15000*i/nx
        shoulder=left if x<0 else right
        t=min(1.,abs(x)/2200.)
        z=col+(shoulder-col)*t**1.65
        longitudinal=smooth(-8200,-6500,y)*(1-smooth(-100,1350,y))
        lateral=1-smooth(2100,3400,abs(x))
        support=longitudinal*lateral
        z=-745+(z+745)*support
        rock=noise.fractal(Vector((x/280,y/390,4.1)),.85,2.,3)
        channel=abs(math.sin(x/190+noise.noise(Vector((x/600,y/900,7)))*2+y/2300))**12
        z+=(rock*85-channel*38)*support
        main=height(names[0],x,y)
        # Bury the connector as it meets the central sculpture: the artist's
        # summit and upper slopes keep their existing visible shape.
        preserve=smooth(-350,250,main)
        if z>main-25:
            z=z*(1-preserve)+(main-25)*preserve
        # One height field merges the entire two neighbouring massifs and
        # their connecting col. This removes exposed intersection seams.
        flank=max(height(names[1],x,y),height(names[2],x,y))
        if flank>-670:
            d=abs(z-flank)
            z=max(z,flank)+max(0,1-d/45)**2*11.25
        # Keep the outer footprint buried below the existing valley floor.
        footprint=(1-smooth(6700,7500,abs(x)))*smooth(-9000,-8000,y)*(1-smooth(1800,2500,y))
        z=-755+(z+755)*footprint
        verts.append((x,y,z))
for j in range(ny):
    for i in range(nx):
        k=j*(nx+1)+i
        faces.append((k,k+1,k+nx+2,k+nx+1))
mesh=bpy.data.meshes.new('Continuous col • terrain mesh')
mesh.from_pydata(verts,[],faces); mesh.update()
obj=bpy.data.objects.new('Joined outer massifs and col • sculpt',mesh)
bpy.data.collections['01 • SCULPT — natural mountain forms'].objects.link(obj)
mesh.materials.append(bpy.data.objects[names[0]].data.materials[0])
for p in mesh.polygons:p.use_smooth=True
obj['purpose']='Continuous col and scree shoulders linking peripheral massifs; existing sculpt meshes untouched.'
bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active=obj
assert all(digest(bpy.data.objects[n])==h for n,h in original.items())
backup=bpy.data.collections.new('07 • BACKUP — separate outer massifs')
bpy.context.scene.collection.children.link(backup)
for n in names[1:]:
    old=bpy.data.objects[n]
    for collection in list(old.users_collection):collection.objects.unlink(old)
    backup.objects.link(old)
backup.hide_viewport=True; backup.hide_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(root/'intro_mountain_connected.blend'))
print('PASS: all original meshes preserved; continuous connecting terrain added')
