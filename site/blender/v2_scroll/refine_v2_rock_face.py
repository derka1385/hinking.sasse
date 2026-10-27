"""Remove the painted snow corridor and close the main summit's artificial arch."""
import bpy, bmesh
import numpy as np
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/petrinolann/Coding/sasse-mountaineering/site/blender/v2_scroll/intro_v2_base_refined.blend')
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene=bpy.context.scene
mountain=bpy.data.objects['Mountains']
mesh=mountain.data
n=len(mesh.vertices)
def coords(data):
    a=np.empty(len(data)*3,np.float32);data.foreach_get('co',a)
    return a.reshape(-1,3)
def smooth(a,b,t):
    t=np.clip((t-a)/(b-a),0,1);return t*t*(3-2*t)

# Snow on natural ledges and in ordinary gullies still follows the original
# material. Remove only the two artificial sources dedicated to the corridor.
terms=mesh.color_attributes['site_terms']
c=np.empty(n*4,np.float32);terms.data.foreach_get('color',c);c=c.reshape(-1,4)
mask=c[:,2].copy()
c[:,2]=0
terms.data.foreach_set('color',c.ravel())
band=mesh.attributes['snow_couloir_band']
bands=np.empty(n,np.int32);band.data.foreach_get('value',bands)
band.data.foreach_set('value',np.zeros(n,np.int32))

# The distant shape key otherwise leaves an artificially flat surface. Keep
# the original carved rock, including the climber's landing and camera route.
basis=coords(mesh.shape_keys.key_blocks['Basis'].data)
far=coords(mesh.shape_keys.key_blocks['Couloir filled (far)'].data)
u=basis[:,0]-60
v=(basis[:,2]-1150)*.9119215051751063+(-basis[:,1]+320)*(-.41036467732879783)+640
along=u*(-.4472136)+v*.8944272
across=u*.8944272-v*(-.4472136)
depth=(basis[:,2]-1150)*.41036467732879783+(-basis[:,1]+320)*.9119215051751063
edge=across+7*np.sin(along*.043)+4*np.sin(along*.093)
cleanup=(1-smooth(35,105,np.abs(edge)))*smooth(-410,-300,along)*(1-smooth(450,590,along))*(1-smooth(90,165,np.abs(depth)))
attr=mesh.attributes.new('corridor_cleanup','FLOAT','POINT')
attr.data.foreach_set('value',cleanup.astype(np.float32))
# Natural-snow tests were also whitening the intentionally smooth gully floor.
# Suppress that snow locally, with an irregular feathered edge, so the entire
# artificial stripe becomes rock rather than merely changing the forced mask.
nt=mesh.materials[0].node_tree
shade=next(node for node in nt.nodes if node.type=='GROUP' and node.node_tree.name=='Site • shade and fog')
albedo_mix=shade.inputs['Albedo'].links[0].from_node
white_scale=albedo_mix.inputs[1].links[0].from_node
snow_socket=white_scale.inputs['Scale']
snow_output=snow_socket.links[0].from_socket
clean=nt.nodes.new('ShaderNodeAttribute');clean.attribute_name='corridor_cleanup'
amount=nt.nodes.new('ShaderNodeMath');amount.operation='MULTIPLY';amount.inputs[1].default_value=.97
nt.links.new(clean.outputs['Fac'],amount.inputs[0])
remaining=nt.nodes.new('ShaderNodeMath');remaining.operation='SUBTRACT';remaining.inputs[0].default_value=1
nt.links.new(amount.outputs[0],remaining.inputs[1])
keep=nt.nodes.new('ShaderNodeMath');keep.operation='MULTIPLY'
nt.links.new(snow_output,keep.inputs[0]);nt.links.new(remaining.outputs[0],keep.inputs[1]);nt.links.new(keep.outputs[0],snow_socket)
protected=np.exp(-(((basis[:,0]-60)/70)**2+((basis[:,2]-563.0873)/90)**2))
strip=np.maximum(mask,smooth(0,30,bands.astype(np.float32)))
rock_weight=np.clip(strip,0,1)*(1-protected)*.82
far=far+(basis-far)*rock_weight[:,None]
mesh.shape_keys.key_blocks['Couloir filled (far)'].data.foreach_set('co',far.ravel())

# A closed, sculptable rocky crown derived from the existing summit envelope.
# Its bottom is buried inside the rock; the new crown fills the arch rather
# than placing a flat screen over it.
effective=basis+(far-basis)*mesh.shape_keys.key_blocks[1].value
selected=(effective[:,2]>990)&(np.abs(effective[:,0]-80)<400)&(np.abs(effective[:,1]-320)<400)
p=effective[selected]
bins=np.floor(p/4).astype(np.int32)
_, first=np.unique(bins,axis=0,return_index=True)
p=p[first]
bm=bmesh.new()
vertices=[bm.verts.new(tuple(v)) for v in p]
hull=bmesh.ops.convex_hull(bm,input=vertices,use_existing_faces=False)
unused=[v for v in hull['geom_unused'] if isinstance(v,bmesh.types.BMVert) and v.is_valid]
if unused:bmesh.ops.delete(bm,geom=unused,context='VERTS')
bmesh.ops.triangulate(bm,faces=list(bm.faces))
for cuts in (3,3,1):
    bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=cuts,use_grid_fill=True)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
bm.normal_update()
for v in bm.verts:
    x,y,z=v.co
    fade=float(smooth(990,1040,z))*(1-float(smooth(1280,1340,z)))
    ridges=(.5+.5*np.sin(x*.072+y*.026+z*.012))**2
    fine=np.sin(x*.19-y*.13)*np.sin(z*.085+y*.061)
    erosion=(3+9*ridges+2*fine)*fade
    v.co-=v.normal*float(erosion)
bm.normal_update()
cap_mesh=bpy.data.meshes.new('Summit crown • continuous alpine rock')
bm.to_mesh(cap_mesh);bm.free();cap_mesh.update();cap_mesh.shade_smooth()
cap=bpy.data.objects.new('Summit • repaired rocky crown',cap_mesh)
mountain.users_collection[0].objects.link(cap)
cap_mesh.materials.append(mesh.materials[0])
for name,values in (('site_ao',(.93,.91,.88,.87)),('site_terms',(.87,.12,0,0))):
    attr=cap_mesh.color_attributes.new(name,'BYTE_COLOR','POINT')
    attr.data.foreach_set('color',np.tile(np.array(values,np.float32),(len(cap_mesh.vertices),1)).ravel())
cap_mesh.attributes.new('snow_couloir_band','INT8','POINT')
cap['purpose']='Solid rock closes the artificial summit arch; sculptable crown derived from original summit silhouette.'
scene['rock_face_refinement']='Removed forced corridor snow and filled summit arch; revised valley base, original snow on ledges and scroll camera retained.'
scene.frame_set(145)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_v2_rock_refined.blend'))
print('PASS: corridor snow masks removed; closed crown',len(cap_mesh.vertices),'vertices;',len(cap_mesh.polygons),'faces',flush=True)

# Original lighting, textures and compositor, at the broad and closer views.
scene.render.resolution_percentage=50
scene.eevee.taa_render_samples=16
for frame,label in ((145,'wide'),(170,'close'),(285,'climber')):
    scene.frame_set(frame)
    scene.render.filepath=str(ROOT/f'v2_rock_{label}_after.png')
    bpy.ops.render.render(write_still=True)
