"""Sculpt only the user's joined cube into a rock rib filling the old summit hole."""
import bpy, bmesh, hashlib
import numpy as np
from pathlib import Path
from mathutils import Vector
from mathutils import noise
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/v2_scroll/intro_v2_base_refined.blend')
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene=bpy.context.scene
mountain=bpy.data.objects['Mountains']
mesh=mountain.data
keys=mesh.shape_keys.key_blocks
def coordinates(data):
    a=np.empty(len(data)*3,np.float32);data.foreach_get('co',a)
    return a.reshape(-1,3)
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
def smooth(a,b,t):
    t=max(0.,min(1.,(t-a)/(b-a)));return t*t*(3-2*t)

# The appended cube is the final eight vertices and final six quad faces.
# Verify this instead of touching any of the user's original sculpt strokes.
start=len(mesh.vertices)-8
faces=[list(mesh.polygons[i].vertices) for i in range(len(mesh.polygons)-6,len(mesh.polygons))]
assert all(len(f)==4 and min(f)>=start for f in faces)
basis=coordinates(keys['Basis'].data)
cube=basis[start:].copy()
assert cube[:,2].min()>1000 and cube[:,2].max()<1300
originals={key.name:digest(coordinates(key.data)[:start]) for key in keys}
floor_before=digest(coordinates(bpy.data.objects['Valley floor'].data.vertices))

centre=cube.mean(0)
axes=np.column_stack((cube[1]-cube[0],cube[2]-cube[0],cube[4]-cube[0]))
inverse=np.linalg.inv(axes)
# Reconstruct the local cliff surface across the opening. At existing rock,
# place the repair skin just inside the original; across the hole, smoothly
# continue the neighbouring wall rather than attaching a round boulder.
far=coordinates(keys['Couloir filled (far)'].data)
surface=basis+(far-basis)*keys['Couloir filled (far)'].value
lo=cube.min(0)-110;hi=cube.max(0)+110
near=((surface>=lo)&(surface<=hi)).all(1)
loop_end=mesh.polygons[len(mesh.polygons)-13].loop_start
indices=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',indices)
triangles=indices[:loop_end].reshape(-1,3)
local_faces=triangles[near[triangles].any(1)]
used=np.unique(local_faces)
remap=np.full(len(surface),-1,np.int32);remap[used]=np.arange(len(used))
tree=BVHTree.FromPolygons([Vector(p) for p in surface[used]],remap[local_faces].tolist())
nu,nw=85,133
us=np.linspace(-.30,1.40,nu);ws=np.linspace(-.70,1.50,nw)
heights=np.full((nw,nu),.78)
known=np.zeros((nw,nu),bool)
direction=Vector(-axes[:,1]).normalized()
for j,w in enumerate(ws):
    for i,u in enumerate(us):
        origin=Vector(cube[0]+axes@np.array((u,3.5,w)))
        hit,normal,_,_=tree.ray_cast(origin,direction,170)
        if hit is not None:
            v=(inverse@(np.array(hit)-cube[0]))[1]
            if (.7<v<2.8) or (-3<v<3.4 and (u<.08 or u>.97 or w<-.12 or w>1.03)):
                heights[j,i]=v-.03;known[j,i]=True
# Harmonic extension follows the adjacent rock contour around the opening.
for iteration in range(1200):
    padded=np.pad(heights,1,mode='edge')
    mean=(padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])*.25
    heights[~known]=mean[~known]
# Restrict the fracture relief to the new cliff, leaving overlapping original
# rock untouched and the perimeter recessed.
unknown=(~known).astype(float)
for iteration in range(12):
    padded=np.pad(unknown,1,mode='edge')
    unknown=(padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])*.25
bm=bmesh.new();front=[];back=[]
for j,w in enumerate(ws):
    for i,u in enumerate(us):
        p=Vector(cube[0]+axes@np.array((u,heights[j,i],w)))
        relief=noise.noise(Vector((u*9,w*3,2.8)))*.11+noise.noise(Vector((u*35,w*14,1.7)))*.028
        blend=smooth(-.30,.0,u)*(1-smooth(1.05,1.40,u))*smooth(-.70,-.25,w)*(1-smooth(1.12,1.50,w))
        v=heights[j,i]+unknown[j,i]*relief
        if not known[j,i]: v-=unknown[j,i]*1.5*(1-blend)
        pos=Vector(cube[0]+axes@np.array((u,v,w)))
        radius=((u-.49)/.66)**2+((w-.39)/.94)**2
        if radius>.58:
            hit,normal,_,distance=tree.find_nearest(pos,60)
            if hit is not None:
                pos=pos.lerp(hit-normal*.8,smooth(.58,.91,radius))
        front.append(bm.verts.new(pos))
        back.append(bm.verts.new(pos-Vector(axes[:,1])*.13))
for j in range(nw-1):
    for i in range(nu-1):
        u=(us[i]+us[i+1])*.5;w=(ws[j]+ws[j+1])*.5
        if ((u-.49)/.66)**2+((w-.39)/.94)**2>.92: continue
        a=j*nu+i;b=a+1;c=b+nu;d=a+nu
        for arr,order in ((front,(a,b,c,d)),(back,(d,c,b,a))):
            bm.faces.new([arr[k] for k in order])
# Close only the irregular retained boundary, with no rectangular side panel.
lookup={front[i]:back[i] for i in range(len(front))}
for edge in list(bm.edges):
    if edge.is_boundary and all(v in lookup for v in edge.verts):
        a,b=edge.verts
        bm.faces.new([b,a,lookup[a],lookup[b]])
for vert in list(bm.verts):
    if not vert.link_faces:bm.verts.remove(vert)
bmesh.ops.triangulate(bm,faces=list(bm.faces))
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.normal_update()
assert all(e.is_manifold for e in bm.edges),'Repair must be a closed volume'
print('Cliff matching:',known.sum(),'original rock samples,',(~known).sum(),'interpolated opening samples',flush=True)
new_mesh=bpy.data.meshes.new('Rock graft • sculpted former cube')
bm.to_mesh(new_mesh);bm.free();new_mesh.update();new_mesh.shade_smooth()
patch=bpy.data.objects.new('Rock rib • integrated hole repair',new_mesh)
mountain.users_collection[0].objects.link(patch)
new_mesh.materials.append(mesh.materials[0])
for name,values in (('site_ao',(.93,.92,.90,.89)),('site_terms',(.89,.20,0.,0.))):
    attr=new_mesh.color_attributes.new(name,'BYTE_COLOR','POINT')
    attr.data.foreach_set('color',np.tile(np.array(values,np.float32),(len(new_mesh.vertices),1)).ravel())
new_mesh.attributes.new('snow_couloir_band','INT8','POINT')
patch['purpose']='Only the user-added cube, sculpted into a fractured rock rib with a buried root; original summit retained.'

# Retire the eight placeholder corners inside the new solid without
# rebuilding 10.8 M original faces or losing shape keys and painted data.
for key in keys:
    for i in range(start,len(mesh.vertices)):key.data[i].co=Vector(centre)
for i in range(start,len(mesh.vertices)):mesh.vertices[i].co=Vector(centre)
mesh.update()
assert all(digest(coordinates(key.data)[:start])==originals[key.name] for key in keys)
assert digest(coordinates(bpy.data.objects['Valley floor'].data.vertices))==floor_before
scene['local_block_integration']='Only the eight added cube corners replaced by a closed sculptable rock rib. Existing summit, user sculpt, valley, materials and animation preserved.'
# Keep the user's close sculpting view, selecting the new rib for further edits.
if mountain.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT');patch.select_set(True);bpy.context.view_layer.objects.active=patch
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_v2_local_rock_repair.blend'))
print('PASS: original sculpt and all original shape-key vertices preserved; closed local rib',len(new_mesh.vertices),'vertices',flush=True)

# First check the integration through the original scroll camera/materials.
scene.render.resolution_percentage=50;scene.eevee.taa_render_samples=16
scene.frame_set(170)
scene.render.filepath=str(ROOT/'v2_local_rock_material.png')
bpy.ops.render.render(write_still=True)

# A close solid preview matching the user's saved Sculpting view.
screen=bpy.data.screens.get('Sculpting') or bpy.data.screens['Layout']
space=next((sp for area in screen.areas for sp in area.spaces if sp.type=='VIEW_3D'),None)
if space:
    data=bpy.data.cameras.new('Temporary repair inspection');data.lens=48;data.clip_end=20000
    camera=bpy.data.objects.new('Temporary repair inspection',data);scene.collection.objects.link(camera)
    camera.location=Vector((360,-290,1380))
    camera.rotation_euler=(Vector((105,320,1170))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera=camera
scene.render.engine='BLENDER_WORKBENCH'
scene.compositing_node_group=None
scene.render.resolution_x=1400;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.display.render_aa='8';sh=scene.display.shading
sh.light='STUDIO';sh.color_type='SINGLE';sh.single_color=(.48,.5,.52)
sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
scene.view_settings.view_transform='Standard';scene.view_settings.exposure=0
for ob in scene.objects:
    if ob.name.startswith('Clouds') or ob.name=='Snowfall':ob.hide_render=True
scene.render.filepath=str(ROOT/'v2_local_rock_solid.png')
bpy.ops.render.render(write_still=True)
