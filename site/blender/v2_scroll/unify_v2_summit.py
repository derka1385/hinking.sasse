"""Build a single alpine crown with continuous radial cliff walls and a buried join."""
import bpy,bmesh,hashlib
import numpy as np
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/v2_scroll/intro_v2_summit_sculpted.blend')
bpy.ops.wm.open_mainfile(filepath=str(SOURCE));scene=bpy.context.scene
mountain=bpy.data.objects['Mountains'];oldcap=bpy.data.objects['Summit • broken alpine ridge'];mesh=mountain.data
if mountain.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
def coords(data):
    a=np.empty(len(data)*3,np.float32);data.foreach_get('co',a);return a.reshape(-1,3)
def smooth(a,b,t):
    t=np.clip((t-a)/(b-a),0,1);return t*t*(3-2*t)
def noise(x,y,scale,seed=0):
    x=x/scale;y=y/scale;i=np.floor(x);j=np.floor(y);u=x-i;v=y-j
    u=u*u*u*(u*(u*6-15)+10);v=v*v*v*(v*(v*6-15)+10)
    def h(a,b):
        z=np.sin(a*127.1+b*311.7+seed*73.3)*43758.5453;return z-np.floor(z)
    return (1-u)*(1-v)*h(i,j)+u*(1-v)*h(i+1,j)+(1-u)*v*h(i,j+1)+u*v*h(i+1,j+1)
basis=coords(mesh.shape_keys.key_blocks['Basis'].data);far=coords(mesh.shape_keys.key_blocks[1].data)
surface=basis+(far-basis)*mesh.shape_keys.key_blocks[1].value
xy=((surface[:,0]-55)/360)**2+((surface[:,1]-350)/290)**2
near=(xy<1.22)&(surface[:,2]>800)
idx=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',idx)
tris=idx.reshape(-1,3);local=tris[near[tris].any(1)];used=np.unique(local)
remap=np.full(len(surface),-1,np.int32);remap[used]=np.arange(len(used))
tree=BVHTree.FromPolygons([Vector(p) for p in surface[used]],remap[local].tolist())
N=384;NZ=241;zs=np.linspace(835.,1319.,NZ);theta=np.arange(N)*2*np.pi/N
co=np.cos(theta);si=np.sin(theta)
fallback=1/np.sqrt((co/290)**2+(si/215)**2)
# Sample the actual cliff at the join so the new massif begins on the old
# surface. Everything above that join is one continuous sculptable mesh.
root=np.empty((3,N));samplez=(835.,865.,905.)
for j,z in enumerate(samplez):
    for i,(c,s) in enumerate(zip(co,si)):
        origin=Vector((55+390*c,350+390*s,z));direction=Vector((-c,-s,0))
        hit=tree.ray_cast(origin,direction,370)[0]
        r=np.linalg.norm(np.array(hit)[:2]-np.array((55,350))) if hit is not None else fallback[i]
        root[j,i]=r if 55<r<360 else fallback[i]
# Remove isolated sampling jumps without losing the large rock buttresses.
for j in range(3):
    for iteration in range(3):root[j]=(root[j]+np.roll(root[j],1)+np.roll(root[j],-1))/3
print('ROOT RADII',root.min(),root.max(),flush=True)
centres=np.column_stack((55+29*smooth(835,1310,zs),350+56*smooth(835,1310,zs)))
rings=[]
for j,z in enumerate(zs):
    t=(z-835)/(1325-835)
    base=root[1]*.75+fallback*.25
    radial=base*(1-t)**.80
    # Broad asymmetric rock ribs, narrow drainage channels and small facets.
    ribs=1+.12*np.cos(theta*3+.7)+.08*np.cos(theta*5-1.1)
    radial*=1+(ribs-1)*smooth(860,990,z)*(1-smooth(1260,1325,z))
    cut=(1-np.abs(2*noise(theta*130,np.full(N,z*.24),45,13)-1))**3
    detail=28*(noise(theta*145,np.full(N,z*.16),38,7)-.5)+6*(noise(theta*145,np.full(N,z*.78),22,5)-.5)+2.5*(noise(theta*145,np.full(N,z),9,19)-.5)
    radial+=smooth(860,965,z)*(1-smooth(1290,1325,z))*(detail-15*cut)
    if z<=865:old=root[0]+(root[1]-root[0])*(z-835)/30
    else:old=root[1]+(root[2]-root[1])*min(1,(z-865)/40)
    join=smooth(840,1000,z)
    radial=old*(1-join)+radial*join
    radial-=1.5*(1-smooth(835,895,z))
    relief=1.5*(noise(theta*145,np.full(N,z),11,32)-.5)*smooth(850,970,z)*(1-smooth(1300,1325,z))
    rings.append(np.column_stack((centres[j,0]+radial*co,centres[j,1]+radial*si,np.full(N,z)+relief)))
points=np.concatenate(rings).astype(np.float32);faces=[]
for j in range(NZ-1):
    for i in range(N):
        a=j*N+i;b=j*N+(i+1)%N;c=b+N;d=a+N
        faces.extend(((a,b,c),(a,c,d)))
apex=len(points);points=np.vstack((points,(84.,406.,1325.)))
for i in range(N):faces.append(((NZ-1)*N+i,(NZ-1)*N+(i+1)%N,apex))
faces.append(tuple(range(N-1,-1,-1)))
newmesh=bpy.data.meshes.new('Continuous single summit • alpine cliffs');newmesh.from_pydata(points.tolist(),[],faces);newmesh.update()
bm=bmesh.new();bm.from_mesh(newmesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));assert all(e.is_manifold for e in bm.edges)
bm.to_mesh(newmesh);bm.free();newmesh.shade_smooth()
cap=bpy.data.objects.new('Summit • single continuous alpine peak',newmesh);mountain.users_collection[0].objects.link(cap)
newmesh.materials.append(mesh.materials[0])
for name,values in (('site_ao',(.93,.91,.88,.87)),('site_terms',(.87,.12,0,0))):
    attr=newmesh.color_attributes.new(name,'BYTE_COLOR','POINT');attr.data.foreach_set('color',np.tile(np.array(values,np.float32),(len(newmesh.vertices),1)).ravel())
newmesh.attributes.new('snow_couloir_band','INT8','POINT')
oldcap.hide_render=True;oldcap.hide_set(True)
# Retire the old needles inside the new rock. Both animated shape-key states
# are retained. All coordinates below the local join stay bit-for-bit intact.
radii=np.array([np.linalg.norm(p[:,:2]-centres[j],axis=1) for j,p in enumerate(rings)])
for key in mesh.shape_keys.key_blocks:
    a=coords(key.data);before=hashlib.sha256(a[a[:,2]<=835].tobytes()).hexdigest();result=a.copy()
    mask=(a[:,2]>835)&(((a[:,0]-55)/355)**2+((a[:,1]-350)/285)**2<1)
    q=a[mask].copy();z=np.minimum(q[:,2],1310.)
    cx=np.interp(z,zs,centres[:,0]);cy=np.interp(z,zs,centres[:,1])
    angle=np.mod(np.arctan2(q[:,1]-cy,q[:,0]-cx),2*np.pi);ti=angle*N/(2*np.pi)
    ia=np.floor(ti).astype(int)%N;ib=(ia+1)%N;f=ti-np.floor(ti)
    zi=np.clip(np.searchsorted(zs,z)-1,0,NZ-2);zf=np.clip((z-zs[zi])/(zs[zi+1]-zs[zi]),0,1)
    rr=(1-zf)*((1-f)*radii[zi,ia]+f*radii[zi,ib])+zf*((1-f)*radii[zi+1,ia]+f*radii[zi+1,ib])
    oldr=np.hypot(q[:,0]-cx,q[:,1]-cy);shrink=np.minimum(1,np.maximum(rr-5,1)/np.maximum(oldr,.01))
    amount=smooth(835,900,q[:,2]);shrink=1+(shrink-1)*amount
    q[:,0]=cx+(q[:,0]-cx)*shrink;q[:,1]=cy+(q[:,1]-cy)*shrink;q[:,2]=z
    result[mask]=q;key.data.foreach_set('co',result.astype(np.float32).ravel())
    assert hashlib.sha256(result[a[:,2]<=835].tobytes()).hexdigest()==before
mesh.vertices.foreach_set('co',coords(mesh.shape_keys.key_blocks['Basis'].data).ravel());mesh.update()
cap['purpose']='Single summit following user reference; continuous cliff mesh merges into sampled original rock at its base.'
scene['single_peak_refinement']='One eastern apex; western needle removed into continuous shoulder; local original needles buried; no horizontal crown joint.'
scene.frame_set(170)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.overlay.show_overlays=False
bpy.ops.object.select_all(action='DESELECT');cap.select_set(True);bpy.context.view_layer.objects.active=cap
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_v2_single_summit.blend'))
print('PASS: watertight single summit',len(newmesh.vertices),'vertices; original below join preserved',flush=True)
scene.render.resolution_percentage=50;scene.eevee.taa_render_samples=16
for frame,label in ((145,'wide'),(170,'close')):
    scene.frame_set(frame);scene.render.filepath=str(ROOT/f'v2_single_summit_{label}.png');bpy.ops.render.render(write_still=True)
scene.render.engine='BLENDER_WORKBENCH';scene.compositing_node_group=None
scene.display.render_aa='8';sh=scene.display.shading
sh.light='STUDIO';sh.color_type='SINGLE';sh.single_color=(.48,.5,.52);sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0
for ob in scene.objects:
    if ob.name.startswith('Clouds') or ob.name=='Snowfall':ob.hide_render=True
scene.render.filepath=str(ROOT/'v2_single_summit_solid.png');bpy.ops.render.render(write_still=True)
