"""Render the camera route as a solid-shaded MP4 in a separate Blender file."""
import bpy
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'intro_camera_red_route.blend'))
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 30
scene.render.fps_base = 1
scene.render.film_transparent = False
scene.display.render_aa = '8'
shading = scene.display.shading
shading.light = 'STUDIO'
shading.color_type = 'SINGLE'
shading.single_color = (0.38, 0.41, 0.45)
shading.show_shadows = True
shading.show_cavity = True
shading.cavity_type = 'BOTH'
shading.background_type = 'WORLD'
scene.world.color = (0.045, 0.052, 0.065)
scene.view_settings.view_transform = 'Standard'
scene.view_settings.exposure = 0
scene.render.image_settings.media_type = 'VIDEO'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.ffmpeg.audio_codec = 'NONE'
scene.render.filepath = str(ROOT / 'camera_route_preview.mp4')
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'intro_camera_preview_render.blend'))
if os.environ.get('CAMERA_PREVIEW_BENCHMARK'):
    scene.frame_set(421)
    scene.render.image_settings.media_type = 'IMAGE'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(ROOT / 'camera_preview_check.png')
    bpy.ops.render.render(write_still=True)
else:
    bpy.ops.render.render(animation=True)
    print('PREVIEW COMPLETE:', scene.render.filepath, flush=True)
