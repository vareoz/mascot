"""Quality-control renders of the built mascot.

    blender -b export/mascot.blend -P blender/render_qa.py -- <mode> [out_dir]

modes: turnaround | hands | anims | hero | all
Images are written to renders/ (frames); tools/make_sheets.py assembles them.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from mascot_lib import studio as S, poses as P  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = argv[0] if argv else "all"
OUT = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(HERE), "renders", "frames")
os.makedirs(OUT, exist_ok=True)
FAST = os.environ.get("MASCOT_QA_FAST") == "1"

rig = bpy.data.objects["MASCOT_Rig"]
scene = bpy.context.scene
cam = scene.camera
ANIMS = ["Idle", "Wave", "Celebrate", "Walk", "Phone", "Fist", "Present"]


def use_action(name, frame):
    act = bpy.data.actions[name]
    rig.animation_data.action = act
    for t in rig.animation_data.nla_tracks:
        t.mute = True
    scene.frame_set(int(frame))


def static_pose(pose, phone=False):
    rig.animation_data.action = None
    for t in rig.animation_data.nla_tracks:
        t.mute = True
    P.reset(rig)
    P.apply(rig, pose)
    s = 1.0 if phone else 0.001
    rig.pose.bones["DEF_Prop.L"].scale = (s, s, s)
    rig.pose.bones["DEF_Prop.R"].scale = (0.001,) * 3
    bpy.context.view_layer.update()


def render(path, res, samples):
    S.render_settings(res, max(8, samples // 3) if FAST else samples)
    S.render_to(path)


def turnaround():
    static_pose(P.merge(P.hand_pose("relaxed", "L"), P.hand_pose("relaxed", "R")))
    for name, yaw in (("front", 0), ("q34_left", 35), ("side", 90), ("back", 180), ("q34_right", -35)):
        S.aim_camera(cam, (0, 0, 0.74), yaw, 7, 4.6, 55)
        render(os.path.join(OUT, f"turn_{name}.png"), (640, 760), 64)


def hands():
    lib = {n: bpy.data.actions.get(f"HandPose_{n}") for n in ("open", "relaxed", "fist", "wave", "phone", "point")}
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("MASCOT_") and o.name != "MASCOT_ArmHand.L":
            o.hide_render = True
    for name, act in lib.items():
        rig.animation_data.action = act
        scene.frame_set(0)
        rig.pose.bones["DEF_Prop.L"].scale = (1, 1, 1) if name == "phone" else (0.001,) * 3
        for o in bpy.data.objects:
            if o.name.startswith("PROP_"):
                o.hide_render = name != "phone"
        bpy.context.view_layer.update()
        hm = rig.matrix_world @ rig.pose.bones["DEF_Hand.L"].matrix
        a = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
        n = (hm.to_3x3() @ Vector((0, 0, 1))).normalized()
        x = (hm.to_3x3() @ Vector((1, 0, 0))).normalized()
        c = hm.translation + a * 0.10
        for vname, d in (("palm", n), ("back", -n), ("thumb_side", -x), ("pinky_side", x)):
            cam.location = c + d.normalized() * 0.78
            cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Z").to_euler()
            cam.data.lens = 85
            render(os.path.join(OUT, f"hand_{name}_{vname}.png"), (420, 420), 32)
    for o in bpy.data.objects:
        if o.name.startswith(("MASCOT_", "PROP_")) and not o.name.startswith("MASCOT_EyeHappy_hidden"):
            o.hide_render = False


def anims():
    for name in ANIMS:
        act = bpy.data.actions[name]
        s, e = int(act.frame_range[0]), int(act.frame_range[1])
        frames = [round(s + (e - s) * i / 7) for i in range(8)]
        for f in frames:
            use_action(name, f)
            yaw = {"Walk": 40, "Present": -20, "Phone": 12}.get(name, 15)
            S.aim_camera(cam, (0, 0, 0.84), yaw, 7, 4.3, 55)
            render(os.path.join(OUT, f"anim_{name}_{f:03d}.png"), (360, 420), 24)


def hero():
    use_action("Phone", 50)
    S.aim_camera(cam, (0.08, 0, 0.80), 18, 6, 4.4, 60)
    render(os.path.join(OUT, "hero_phone.png"), (1200, 1200), 128)
    use_action("Celebrate", 23)
    S.aim_camera(cam, (0, 0, 1.0), 10, 5, 5.0, 60)
    render(os.path.join(OUT, "hero_celebrate.png"), (1000, 1200), 128)
    use_action("Walk", 6)
    S.aim_camera(cam, (0, 0, 0.75), 50, 6, 4.6, 60)
    render(os.path.join(OUT, "hero_walk.png"), (1000, 1200), 128)


if MODE in ("turnaround", "all"):
    turnaround()
if MODE in ("hands", "all"):
    hands()
if MODE in ("anims", "all"):
    anims()
if MODE in ("hero", "all"):
    hero()
print("[qa] done", MODE)
