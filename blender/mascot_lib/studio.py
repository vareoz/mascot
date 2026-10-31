"""Warm studio lighting, cyclorama backdrop and camera helpers for renders."""
import math
import bpy
from mathutils import Vector

from .materials import PALETTE


def ensure_collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if col.name not in [c.name for c in parent.children]:
        parent.children.link(col)
    return col


def build_cyclorama(col, mat):
    # profile in the YZ plane: floor -> curved wall
    prof = []
    for i in range(12):
        prof.append((-30.0 + i * (31.2 / 11), 0.0))
    r = 2.2
    y0 = 1.2
    for i in range(1, 17):
        a = i / 16 * math.pi / 2
        prof.append((y0 + math.sin(a) * r, r - math.cos(a) * r))
    prof.append((y0 + r, 30.0))
    verts, faces = [], []
    xs = [-30.0, 30.0]
    for x in xs:
        for y, z in prof:
            verts.append((x, y, z))
    n = len(prof)
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))
    me = bpy.data.meshes.new("STUDIO_Cyclorama")
    me.from_pydata(verts, [], faces)
    me.shade_smooth()
    ob = bpy.data.objects.new("STUDIO_Cyclorama", me)
    col.objects.link(ob)
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def area_light(col, name, loc, target, power, size, color):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.shape = "DISK"
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def build_studio(mats):
    col = ensure_collection("STUDIO")
    pivot = bpy.data.objects.new("STUDIO_Pivot", None)     # turns the whole studio with the camera
    col.objects.link(pivot)
    items = [build_cyclorama(col, mats["backdrop"])]
    tgt = (0, 0, 0.75)
    items.append(area_light(col, "LGT_Key", (-2.2, -3.0, 3.2), tgt, 260, 3.0, (1.0, 0.93, 0.84)))
    items.append(area_light(col, "LGT_Fill", (2.8, -2.4, 1.6), tgt, 90, 3.5, (0.95, 0.96, 1.0)))
    items.append(area_light(col, "LGT_Rim", (1.6, 2.4, 2.8), tgt, 160, 2.0, (1.0, 0.95, 0.88)))
    items.append(area_light(col, "LGT_Top", (0.0, -0.5, 4.5), tgt, 70, 4.0, (1.0, 0.97, 0.92)))
    for ob in items:
        ob.parent = pivot

    world = bpy.data.worlds.get("STUDIO_World") or bpy.data.worlds.new("STUDIO_World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    c = PALETTE["background"]
    bg.inputs["Color"].default_value = (c[0], c[1], c[2], 1)
    bg.inputs["Strength"].default_value = 0.30
    bpy.context.scene.world = world

    cam_d = bpy.data.cameras.new("CAM_Main")
    cam_d.lens = 70
    cam = bpy.data.objects.new("CAM_Main", cam_d)
    col.objects.link(cam)
    bpy.context.scene.camera = cam
    return col


def aim_camera(cam, target, yaw_deg, pitch_deg, dist, lens=70):
    """Places the camera on a sphere around target. yaw 0 = front (-Y)."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    t = Vector(target)
    off = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))) * dist
    cam.location = t + off
    pivot = bpy.data.objects.get("STUDIO_Pivot")
    if pivot is not None:
        pivot.rotation_euler = (0, 0, yaw)
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens


def render_settings(res=(900, 1000), samples=48):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.cycles.denoiser = "OPENIMAGEDENOISE"
    s.cycles.max_bounces = 6
    s.cycles.use_adaptive_sampling = True
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.film_transparent = False
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    s.view_settings.exposure = -0.7
    s.render.image_settings.file_format = "PNG"
    s.render.threads_mode = "AUTO"


def render_to(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
