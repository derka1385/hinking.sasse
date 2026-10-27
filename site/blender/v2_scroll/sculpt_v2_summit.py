"""Turn the closed summit crown into a broken alpine ridge with uneven rock teeth."""
import bpy, bmesh
import numpy as np
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/v2_scroll/intro_v2_rock_refined.blend')
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene=bpy.context.scene
cap=bpy.data.objects['Summit • repaired rocky crown']
mountain=bpy.data.objects['Mountains']
def coords(data):
    a=np.empty(len(data)*3,np.float32);data.foreach_get('co',a)
    return a.reshape(-1,3)
def smooth(a,b,t):
    t=np.clip((t-a)/(b-a),0,1);return t*t*(3-2*t)
def noise(x,y,scale,seed=0):
    x=x/scale;y=y/scale
    i=np.floor(x);j=np.floor(y);u=x-i;v=y-j
    u=u*u*u*(u*(u*6-15)+10);v=v*v*v*(v*(v*6-15)+10)
    def h(a,b):
        z=np.sin(a*127.1+b*311.7+seed*73.3)*43758.5453
        return z-np.floor(z)
    return ((1-u)*(1-v)*h(i,j)+u*(1-v)*h(i+1,j)+(1-u)*v*h(i,j+1)+u*v*h(i+1,j+1))

# Sample the old crown envelope. The deformation preserves its buried root
# and its watertight topology instead of adding detached spikes.
old=coords(cap.data.vertices)
tree=BVHTree.FromPolygons([Vector(p) for p in old],[list(p.vertices) for p in cap.data.polygons],epsilon=.03)
origin=old[:,:2].min(0)-8
size=np.ceil((old[:,:2].max(0)-origin+8)/4).astype(int)+1
grid=np.full((size[1],size[0]),990.,np.float32)
for j in range(size[1]):
    for i in range(size[0]):
        hit=tree.ray_cast(Vector((float(origin[0]+i*4),float(origin[1]+j*4),1600)),Vector((0,0,-1)))[0]
        if hit is not None:grid[j,i]=max(990,float(hit.z))
def envelope(x,y,fallback):
    values=np.empty(len(x),np.float32)
    for k,(px,py,z) in enumerate(zip(x,y,fallback)):
        hit=tree.ray_cast(Vector((float(px),float(py),1600)),Vector((0,0,-1)))[0]
        values[k]=max(990,float(hit.z)) if hit is not None else max(990,float(z))
    return values

def ridge(x,y):
    # Five asymmetric, overlapping rock teeth with unequal heights and
    # offsets; broad roots remain joined in a continuous shoulder.
    shoulder=1046+29*np.exp(-((x-35)/190)**2-((y-400)/130)**2)+17*(noise(x,y,80,6)-.5)
    height=shoulder.copy()
    for px,py,top,rx,ry in (
        (-112,412,1305,93,118),
        (-20,477,1248,80,95),
        (83,406,1325,93,119),
        (180,451,1240,77,95),
        (153,275,1205,79,104),
    ):
        dx=(x-px)/rx;dy=(y-py)/ry
        angle=np.arctan2(dy,dx)
        r=np.sqrt(dx*dx+dy*dy)*(1+.105*np.sin(angle*3+px*.017)+.06*np.sin(angle*5+.9))
        tip=np.maximum(1-r,0)**.67
        h=shoulder+(top-shoulder)*tip
        height=np.maximum(height,h)
    erosion=23*noise(x,y,43,3)+9*noise(x,y,17,8)+3*noise(x,y,7,2)
    # Irregular channels run down the face, rather than an even saw-tooth row.
    channel=(1-np.abs(2*noise(x,y*.35,35,14)-1))**3
    return height-erosion-16*channel

def deform(a,buried=False):
    result=a.copy()
    selected=(a[:,2]>990)&(a[:,0]>origin[0])&(a[:,0]<origin[0]+4*(size[0]-1))&(a[:,1]>origin[1])&(a[:,1]<origin[1]+4*(size[1]-1))
    q=a[selected]
    old_top=envelope(q[:,0],q[:,1],q[:,2])
    blend=smooth(1005,1080,old_top)
    top=old_top+blend*(ridge(q[:,0],q[:,1])-old_top)
    scale=np.maximum(top-990,1)/np.maximum(old_top-990,1)
    fraction=np.clip((q[:,2]-990)/np.maximum(old_top-990,1),0,1.05)
    if buried:
        # Keep the old summit inside the sculpted solid so it cannot retain
        # the previous single apex or reopen the original arch.
        fraction=np.minimum(fraction,.985)
    z=990+np.minimum(fraction,1)*(top-990)
    if buried:z=990+fraction*(top-990)
    result[selected,2]=q[:,2]+smooth(990,1020,q[:,2])*(z-q[:,2])
    face_weight=smooth(990,1050,result[selected,2])
    zz=result[selected,2]
    result[selected,0]+=face_weight*(18*(noise(q[:,0],zz*.46,48,19)-.5)+6*(noise(q[:,1],zz*.55,22,21)-.5))
    result[selected,1]+=face_weight*(21*(noise(q[:,0],zz*.41,45,23)-.5)+7*(noise(q[:,1],zz*.50,24,25)-.5))
    assert np.array_equal(result[a[:,2]<=990],a[a[:,2]<=990])
    return result

new=deform(old)
cap.data.vertices.foreach_set('co',new.astype(np.float32).ravel())
cap.data.update()
for key in mountain.data.shape_keys.key_blocks:
    a=coords(key.data)
    result=deform(a,buried=True)
    key.data.foreach_set('co',result.astype(np.float32).ravel())
basis=coords(mountain.data.shape_keys.key_blocks['Basis'].data)
mountain.data.vertices.foreach_set('co',basis.ravel());mountain.data.update()

bm=bmesh.new();bm.from_mesh(cap.data)
assert all(e.is_manifold for e in bm.edges),'Summit must remain closed'
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.normal_update();bm.to_mesh(cap.data);bm.free()
cap.data.shade_smooth()
cap.name='Summit • broken alpine ridge'
cap['purpose']='Five irregular connected rock teeth, erosion channels and asymmetrical shoulders; no summit arch.'
scene['summit_sculpt']='Highest crown reshaped as a broken ridge; lower mountain, revised base and scroll rig preserved.'
scene.frame_set(170)
for screen in bpy.data.screens:
    for area in screen.areas:
        for space in area.spaces:
            if space.type=='VIEW_3D':
                space.region_3d.view_perspective='CAMERA'
                space.overlay.show_overlays=False
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_v2_summit_sculpted.blend'))
print('PASS: irregular closed summit; all geometry below 990 m unchanged; new maximum height',float(new[:,2].max()),flush=True)
scene.render.resolution_percentage=50
scene.eevee.taa_render_samples=16
for frame,label in ((145,'wide'),(170,'close')):
    scene.frame_set(frame)
    scene.render.filepath=str(ROOT/f'v2_summit_{label}_after.png')
    bpy.ops.render.render(write_still=True)
