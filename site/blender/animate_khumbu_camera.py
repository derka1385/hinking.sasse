"""Approach Cholatse, then orbit it. Original scene and camera are preserved."""
import bpy, math, bisect, hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path('/Users/petrinolann/Documents/ChatGPT/hiking sasse/site/blender')
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'intro_animation_source.blend'))
scene=bpy.context.scene
def digest(o):
    from array import array
    a=array('f',[0])*len(o.data.vertices)*3
    o.data.vertices.foreach_get('co',a)
    return hashlib.sha256(a.tobytes()).hexdigest()
terrain_names=['Khumbu • backdrop 30 m','Cholatse • hero 10 m','Ama Dablam • hero 10 m']
signatures={n:digest(bpy.data.objects[n]) for n in terrain_names}
trees=[]
for n in terrain_names:
    o=bpy.data.objects[n]
    trees.append(BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons]))
def ground(x,y):
    hits=[t.ray_cast(Vector((x,y,12000)),Vector((0,0,-1)))[0] for t in trees]
    return max((p.z for p in hits if p is not None),default=3500.)
def smooth(t):return t*t*(3-2*t)

rig=bpy.data.collections.new('11 • CAMERA — red route approach and orbit')
scene.collection.children.link(rig)
summit=bpy.data.objects['Cholatse (6440 m)'].location.copy()
direction=Vector((-19731.537-summit.x,-12957.756-summit.y,0)).normalized()
start=summit+direction*12000
start.z=5700
radius=3900.
angle=math.atan2(start.y-summit.y,start.x-summit.x)
ring=Vector((summit.x+radius*math.cos(angle),summit.y+radius*math.sin(angle),7000))
tangent=Vector((-math.sin(angle),math.cos(angle),0))
p1=start+Vector((1900,5200,200))
p2=ring-tangent*(radius*2*math.pi/(780)*420/3)
points=[]
approach_end=421
end=1201
for frame in range(1,end+1):
    if frame<=approach_end:
        t=(frame-1)/(approach_end-1)
        # Continuous positional and directional hand-off to the orbit.
        p=(1-t)**3*start+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*ring
    else:
        t=(frame-approach_end)/(end-approach_end)
        a=angle+2*math.pi*t
        r=radius+160*math.sin(math.pi*t)**2
        p=Vector((summit.x+r*math.cos(a),summit.y+r*math.sin(a),7000+120*math.sin(2*math.pi*t)**2))
    # Lift gently above the local relief. A wider neighbourhood reduces sudden
    # vertical reactions when passing a rocky ridge.
    nearby=max(ground(p.x+dx,p.y+dy) for dx,dy in ((0,0),(180,0),(-180,0),(0,180),(0,-180)))
    p.z=max(p.z,nearby+420)
    points.append(p)
# Smooth altitude without ever reducing the 350 m clearance below the terrain.
alt=[p.z for p in points]
for k,p in enumerate(points):
    lo=max(0,k-18);hi=min(len(points),k+19)
    p.z=max(sum(alt[lo:hi])/(hi-lo),ground(p.x,p.y)+350)

curve=bpy.data.curves.new('Red route • editable camera path','CURVE')
curve.dimensions='3D';curve.path_duration=end-1;curve.resolution_u=12
spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
for v,p in zip(spline.points,points):v.co=(*p,1)
path=bpy.data.objects.new('Camera route • approach then full orbit',curve)
rig.objects.link(path);path.hide_render=True;path.show_in_front=True
path['instructions']='Edit the curve in Edit Mode to adjust the route. Camera follows this curve; target controls framing.'

target=bpy.data.objects.new('Look at • Cholatse summit',None)
rig.objects.link(target);target.empty_display_type='SPHERE';target.empty_display_size=100
for frame,z in ((1,5400),(280,5800),(421,6200),(1201,6200)):
    target.location=(summit.x,summit.y,z)
    target.keyframe_insert(data_path='location',frame=frame)

data=bpy.data.cameras.new('Cinematic route lens')
data.lens=29;data.clip_start=10;data.clip_end=100000
camera=bpy.data.objects.new('Camera • red route',data);rig.objects.link(camera)
follow=camera.constraints.new('FOLLOW_PATH')
follow.name='Follow editable red route';follow.target=path;follow.use_fixed_location=True;follow.use_curve_follow=False
track=camera.constraints.new('TRACK_TO');track.name='Keep Cholatse framed';track.target=target;track.track_axis='TRACK_NEGATIVE_Z';track.up_axis='UP_Y'
lengths=[0.]
for a,b in zip(points,points[1:]):lengths.append(lengths[-1]+(b-a).length)
for k,d in enumerate(lengths):
    follow.offset_factor=d/lengths[-1]
    follow.keyframe_insert(data_path='offset_factor',frame=k+1)
# Dense offset keys make scroll/frame scrubbing deterministic. Linear segments
# follow the smooth geometric curve without Bezier overshoot into the terrain.
for layer in camera.animation_data.action.layers:
    for strip in layer.strips:
        for bag in strip.channelbags:
            for fc in bag.fcurves:
                for key in fc.keyframe_points:key.interpolation='LINEAR'
scene.camera=camera;scene.frame_start=1;scene.frame_end=end;scene.render.fps=30
scene.sync_mode='FRAME_DROP'
scene.timeline_markers.clear()
for label,f in [('START • valley approach',1),('APPROACH • reveal the massif',220),('ORBIT • begins',421),('ORBIT • far side',811),('END • full turn',1201)]:
    scene.timeline_markers.new(label,frame=f)

minimum=100000
for frame in range(1,end+1):
    scene.frame_set(frame)
    p=camera.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
    clearance=p.z-ground(p.x,p.y)
    minimum=min(minimum,clearance)
assert minimum>300, f'Camera intersects terrain: clearance {minimum}'
assert all(digest(bpy.data.objects[n])==h for n,h in signatures.items())
scene['red_route_minimum_terrain_clearance_m']=minimum
scene['red_route_description']='40-second valley approach and full orbit around Cholatse; camera and editable curve, original terrain preserved.'
scene.frame_set(421)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='CONSOLE' and screen.name=='Layout':area.type='VIEW_3D'
        for space in area.spaces:
            if space.type=='VIEW_3D':
                space.clip_start=10;space.clip_end=100000
                if screen.name=='Layout':space.region_3d.view_perspective='CAMERA'
bpy.ops.object.select_all(action='DESELECT');camera.select_set(True);bpy.context.view_layer.objects.active=camera
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'intro_camera_red_route.blend'))
print(f'PASS: {end} camera frames checked; minimum ground clearance {minimum:.1f} m; original terrain preserved')
# A neutral motion preview avoids the source scene's overexposed snow shader.
scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO'
scene.display.shading.color_type='SINGLE'
scene.display.shading.single_color=(.38,.41,.45)
scene.display.shading.show_shadows=True
scene.display.shading.show_cavity=True
scene.display.shading.cavity_type='BOTH'
scene.view_settings.view_transform='Standard'
scene.view_settings.exposure=0
for frame in (1,421,811):
    scene.frame_set(frame)
    scene.render.resolution_percentage=50
    scene.render.filepath=str(ROOT/f'camera_red_route_{frame:04}.png')
    bpy.ops.render.render(write_still=True)
