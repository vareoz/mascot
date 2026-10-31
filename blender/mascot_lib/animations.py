"""The seven test animations, authored procedurally on the rig controls.

Every action keys the controls it needs (FK bones, IK hand/foot targets,
IK/FK switches, grip, face bones) and is stored on its own NLA track so the
glTF/FBX exporters write one clip per action.
"""
import math
import numpy as np
import bpy
from mathutils import Matrix, Vector, Euler

from . import design as D
from . import poses as P
from .poses import key, merge, hand_pose, mirrored

FPS = 24
ACTIONS = {}           # name -> (action, frame_start, frame_end, loop)


def log(*a):
    print("[anim]", *a, flush=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def rest(rig, name):
    return rig.data.bones[name].matrix_local.copy()


def frame_from_axes(y_axis, z_axis, pos):
    y = Vector(y_axis).normalized()
    z = Vector(z_axis)
    z = (z - y * z.dot(y)).normalized()
    x = y.cross(z)
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = x[i], y[i], z[i], pos[i]
    return M


def place(rig, name, M):
    """Set a pose bone from an armature-space matrix and return its channels."""
    pb = rig.pose.bones[name]
    pb.matrix = M
    bpy.context.view_layer.update()
    ch = {"l": tuple(pb.location)}
    if pb.rotation_mode == "QUATERNION":
        ch["q"] = tuple(pb.rotation_quaternion)
    else:
        ch["r"] = tuple(math.degrees(a) for a in pb.rotation_euler)
    return ch


def hand_target(rig, side, wrist, fingers_dir, palm_normal):
    return {f"CTRL_IK_Hand.{side}": place(rig, f"CTRL_IK_Hand.{side}",
                                         frame_from_axes(fingers_dir, palm_normal, wrist))}


def pole(rig, name, pos):
    r = rest(rig, name)
    return {name: {"l": tuple(r.to_3x3().inverted() @ (Vector(pos) - r.translation))}}


def foot_target(rig, side, ankle, pitch=0.0, yaw=0.0):
    """IK foot at a world ankle position; pitch > 0 lifts the toes."""
    name = f"CTRL_IK_Foot.{side}"
    r = rest(rig, name)
    s = 1 if side == "L" else -1
    fwd = Vector(D.mirror(D.RIG.foot_fwd) if s < 0 else D.RIG.foot_fwd)
    sideax = fwd.cross(Vector((0, 0, 1))).normalized()
    rot = Matrix.Rotation(math.radians(-pitch), 4, sideax) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    M = Matrix.Translation(Vector(ankle)) @ rot @ Matrix.Translation(-r.translation) @ r
    return {name: place(rig, name, M)}


def new_action(rig, name, start, end, loop):
    P.reset(rig)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    act.use_frame_range = True
    act.frame_start, act.frame_end = start, end
    act.use_cyclic = loop
    rig.animation_data_create()
    rig.animation_data.action = act
    ACTIONS[name] = (act, start, end, loop)
    return act


def finish_action(rig, act, loop):
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        if loop:
            fc.modifiers.new("CYCLES")
        fc.update()


def base_keys(rig, frame, arms_ik=(0.0, 0.0), legs_ik=(1.0, 1.0), phone=False):
    """Keys every control to its neutral value, so each clip is self-contained."""
    pose = {}
    for pb in rig.pose.bones:
        n = pb.name
        if n.startswith(("MCH_",)) or n.startswith("DEF_Arm"):
            continue
        if n.startswith("DEF_") and n.split("_")[1].split(".")[0] in ("UpperArm", "Forearm", "Hand", "Thigh",
                                                                       "Shin", "Foot"):
            continue
        ch = {"l": (0, 0, 0), "s": (1, 1, 1)}
        ch["q" if pb.rotation_mode == "QUATERNION" else "r"] = (1, 0, 0, 0) if pb.rotation_mode == "QUATERNION" \
            else (0, 0, 0)
        pose[n] = ch
    s = 1.0 if phone else 0.001
    pose["DEF_Prop.L"]["s"] = (s, s, s)
    pose["DEF_Prop.R"]["s"] = (0.001, 0.001, 0.001)
    pose["CTRL_Root"].update({"prop:IK_Arm.L": arms_ik[0], "prop:IK_Arm.R": arms_ik[1],
                              "prop:IK_Leg.L": legs_ik[0], "prop:IK_Leg.R": legs_ik[1]})
    key(rig, frame, pose)


def relaxed_hands():
    return merge(hand_pose("relaxed", "L"), hand_pose("relaxed", "R"))


def lerp_pose(a, b, t):
    out = {}
    for name in set(a) | set(b):
        ca, cb = a.get(name, {}), b.get(name, {})
        ch = {}
        for k in set(ca) | set(cb):
            va = ca.get(k, cb.get(k))
            vb = cb.get(k, ca.get(k))
            if isinstance(va, (int, float)):
                ch[k] = va + (vb - va) * t
            else:
                ch[k] = tuple(x + (y - x) * t for x, y in zip(va, vb))
        out[name] = ch
    return out


def eyes(look=(0.0, 0.0), blink=1.0, happy=0.0):
    """look: (x, z) offset; blink: 1 open .. 0 closed; happy: 0..1 swaps to ^ ^ arcs."""
    hide = D.Face.HAPPY_HIDE
    out = {}
    for s in ("L", "R"):
        open_y = max(0.05, blink * (1 - happy) + 0.05 * happy)
        out[f"DEF_Eye.{s}"] = {"l": (look[0], look[1], -0.03 * happy), "s": (1, open_y, 1)}
        out[f"DEF_EyeHappy.{s}"] = {"l": (look[0], look[1], hide * happy)}
    return out


def smile(width=1.0, lift=0.0):
    return {"DEF_Smile": {"s": (width, 1.0, 1.0), "l": (0, lift, 0)}}


def breath(t, amp=1.0):
    s = math.sin(2 * math.pi * t) * amp
    return {"DEF_BodyShape": {"s": (1 - 0.006 * s, 1 + 0.016 * s, 1 - 0.006 * s)}}


# ---------------------------------------------------------------------------
# 1. Idle
# ---------------------------------------------------------------------------

def anim_idle(rig):
    n = 96
    act = new_action(rig, "Idle", 0, n, True)
    base_keys(rig, 0)
    for f in range(0, n + 1, 4):
        t = f / n
        s = math.sin(2 * math.pi * t)
        c = math.cos(2 * math.pi * t)
        pose = merge(
            breath(t),
            {"CTRL_COG": {"l": (0, 0, -0.004 * (1 - c) / 2)},
             "DEF_Body": {"r": (0.8 * s, 0, 0.6 * math.sin(4 * math.pi * t))}},
            {"FK_UpperArm.X": {"r": (2.5 * s, 0, -3 + 1.2 * c)}, "FK_Forearm.X": {"r": (-6 - 3 * s, 0, 0)},
             "FK_Hand.X": {"r": (4 + 2 * c, 0, 0)}},
            relaxed_hands(),
        )
        blink = 1.0
        if 58 <= f <= 66:
            blink = {58: 1.0, 60: 0.35, 62: 0.05, 64: 0.4, 66: 1.0}.get(f, 1.0)
        pose = merge(pose, eyes(look=(0.004 * math.sin(2 * math.pi * t), 0), blink=blink))
        key(rig, f, pose)
    # extra blink keys on odd frames for a crisp blink
    for f, b in ((61, 0.1), (63, 0.1)):
        key(rig, f, eyes(blink=b, look=(0.004 * math.sin(2 * math.pi * f / n), 0)))
    finish_action(rig, act, True)


# ---------------------------------------------------------------------------
# 2. Wave (Saludo)
# ---------------------------------------------------------------------------

def anim_wave(rig):
    n = 72
    act = new_action(rig, "Wave", 0, n, True)
    base_keys(rig, 0, arms_ik=(0.0, 1.0))
    R = D.RIG
    rest_w = Vector(D.mirror(R.W))
    rest_a = Vector(D.mirror(R.a))
    rest_n = Vector(D.mirror(R.n))
    up_w = Vector((-0.60, -0.12, 1.17))
    for f in range(0, n + 1, 2):
        # raise 0-14, wave 14-58, lower 58-72
        if f <= 14:
            k = f / 14
        elif f >= 58:
            k = 1 - (f - 58) / 14
        else:
            k = 1.0
        k = k * k * (3 - 2 * k)
        wave = math.sin((f - 14) / 10 * math.pi) if 14 <= f <= 62 else 0.0
        a_up = Vector((-0.30, -0.10, 1.0)).normalized()
        n_up = Vector((0, -1, 0))
        a_up = Matrix.Rotation(math.radians(22 * wave * k), 3, n_up) @ a_up
        a = rest_a.lerp(a_up, k).normalized()
        nn = rest_n.lerp(n_up, k).normalized()
        # arc outwards while raising so the hand never brushes the body
        w = rest_w.lerp(up_w + Vector((0.03 * wave * k, 0, 0)), k) + Vector((-0.16, -0.04, 0)) * math.sin(math.pi * k)
        pose = merge(hand_target(rig, "R", w, a, nn),
                     pole(rig, "CTRL_Pole_Arm.R", (-0.85, 0.35, 0.62)),
                     breath(f / n, 0.6),
                     {"DEF_Body": {"r": (0, -4 * k, 3 * k + 1.0 * wave * k)},
                      "CTRL_COG": {"l": (0, 0, 0.006 * k * abs(math.sin((f - 14) / 20 * math.pi)))}},
                     hand_pose("relaxed", "L"),
                     {"FK_UpperArm.L": {"r": (0, 0, -3 * k)}, "FK_Forearm.L": {"r": (-8, 0, 0)}},
                     eyes(look=(-0.006 * k, 0.003 * k)), smile(1.0 + 0.18 * k, 0.002 * k))
        # fingers: open wave hand with a small ripple through the fingers
        hp = lerp_pose(hand_pose("relaxed", "R"), hand_pose("wave", "R"), k)
        for i, fn in enumerate(P.FINGERS):
            wig = 9 * k * math.sin((f - 14) / 6 * math.pi - i * 0.9) if 14 <= f <= 58 else 0
            for j in (1, 2):
                bn = f"DEF_{fn}_{j:02d}.R"
                r = hp[bn]["r"]
                hp[bn] = {"r": (r[0] + max(0, wig) * (1.0 if j == 1 else 0.6), r[1], r[2])}
        key(rig, f, merge(pose, hp))
    finish_action(rig, act, True)


# ---------------------------------------------------------------------------
# 3. Celebrate (Celebración)
# ---------------------------------------------------------------------------

def anim_celebrate(rig):
    n = 60
    act = new_action(rig, "Celebrate", 0, n, False)
    base_keys(rig, 0, arms_ik=(1.0, 1.0))
    R = D.RIG
    ank = {"L": Vector(R.ankle), "R": Vector(D.mirror(R.ankle))}
    rest_hand = {"L": (Vector(R.W), Vector(R.a), Vector(R.n)),
                 "R": (Vector(D.mirror(R.W)), Vector(D.mirror(R.a)), Vector(D.mirror(R.n)))}
    # (frame, cog_z, squash, arms_up, feet_z, happy)
    keys = [(0, 0.0, 0.0, 0.0, 0.0, 0.0), (6, -0.055, -1.0, 0.25, 0.0, 0.3), (10, -0.06, -1.0, 0.5, 0.0, 1.0),
            (14, 0.05, 0.6, 1.0, 0.02, 1.0), (19, 0.20, 0.25, 1.0, 0.13, 1.0), (23, 0.235, 0.0, 1.0, 0.16, 1.0),
            (27, 0.20, 0.1, 1.0, 0.12, 1.0), (31, 0.06, 0.4, 1.0, 0.02, 1.0), (33, 0.0, 0.0, 1.0, 0.0, 1.0),
            (36, -0.05, -0.9, 0.9, 0.0, 1.0), (42, 0.01, 0.2, 1.0, 0.0, 1.0), (48, 0.0, 0.0, 1.0, 0.0, 1.0),
            (60, 0.0, 0.0, 0.0, 0.0, 0.0)]
    for f, cz, sq, up, fz, happy in keys:
        pose = {"CTRL_COG": {"l": (0, 0, cz)},
                "DEF_BodyShape": {"s": (1 - 0.05 * sq, 1 + 0.08 * sq, 1 - 0.05 * sq)},
                "DEF_Body": {"r": (-3 * up if f < 48 else 0, 0, 0)}}
        for s, sg in (("L", 1), ("R", -1)):
            w0, a0, n0 = rest_hand[s]
            w_up = Vector((sg * 0.50, -0.07, 1.36 + cz))
            a_up = Vector((sg * 0.12, -0.05, 1.0)).normalized()
            n_up = Vector((-sg * 1.0, 0.0, 0.1)).normalized()
            k = up * up * (3 - 2 * up)
            pose.update(hand_target(rig, s, w0.lerp(w_up, k), a0.lerp(a_up, k).normalized(),
                                    n0.lerp(n_up, k).normalized()))
            pose.update(pole(rig, f"CTRL_Pole_Arm.{s}", (sg * 0.95, 0.15, 0.95 + cz)))
            # feet tuck up during the jump and stay planted otherwise
            pitch = -18 if fz > 0.05 else 0
            pose.update(foot_target(rig, s, ank[s] + Vector((0, 0.02 if fz > 0.05 else 0, fz)), pitch))
            pose.update(pole(rig, f"CTRL_Pole_Leg.{s}", tuple(Vector(D.RIG.knee if s == "L" else D.mirror(D.RIG.knee))
                                                             + Vector((0, -0.45, cz)))))
        fist = lerp_pose(merge(hand_pose("relaxed", "L"), hand_pose("relaxed", "R")),
                         merge(hand_pose("fist", "L"), hand_pose("fist", "R")), min(1.0, up * 1.3))
        pose = merge(pose, fist, eyes(happy=happy), smile(1 + 0.3 * happy, 0.004 * happy))
        key(rig, f, pose)
    finish_action(rig, act, False)


# ---------------------------------------------------------------------------
# 4. Walk (Caminata) - in-place cycle
# ---------------------------------------------------------------------------

def sole_points(leg_ob):
    """Sole vertices of the left foot relative to the ankle (rest pose)."""
    me = leg_ob.data
    gi = {g.name: g.index for g in leg_ob.vertex_groups}
    pts = []
    for v in me.vertices:
        if v.co.z > 0.03:
            continue
        w = sum(g.weight for g in v.groups if g.group in (gi.get("DEF_Foot.L"), gi.get("DEF_Toe.L")))
        if w > 0.5:
            pts.append(tuple(v.co))
    return np.array(pts)


def anim_walk(rig, leg_ob):
    n = 32
    act = new_action(rig, "Walk", 0, n, True)
    base_keys(rig, 0)
    R = D.RIG
    sole = sole_points(leg_ob)
    ankle_rest = np.array(R.ankle)
    fwd = np.array(R.foot_fwd)

    def ankle_height(pitch):
        side = np.cross(fwd, [0, 0, 1.0])
        side /= np.linalg.norm(side)
        a = math.radians(-pitch)
        rel = sole - ankle_rest
        rot = rel * math.cos(a) + np.cross(side, rel) * math.sin(a) + np.outer(rel @ side, side) * (1 - math.cos(a))
        return -rot[:, 2].min() + 0.0005

    stride = 0.105

    def foot_state(p):
        p %= 1.0
        if p < 0.5:                      # stance: foot on the floor sliding back
            q = p / 0.5
            y = -stride + 2 * stride * q
            if q < 0.16:
                pitch = 12 * (1 - q / 0.16)
            elif q > 0.78:
                pitch = -20 * ((q - 0.78) / 0.22)
            else:
                pitch = 0.0
            z = ankle_height(pitch)
        else:                            # swing: lift and bring forward
            q = (p - 0.5) / 0.5
            s = q * q * (3 - 2 * q)
            y = stride - 2 * stride * s
            pitch = -20 + 32 * s
            z = ankle_height(pitch) + 0.065 * math.sin(math.pi * q) ** 1.2
        return y, z, pitch

    for f in range(0, n + 1, 1):
        p = f / n
        pose = {}
        for side, ph, sg in (("L", 0.0, 1), ("R", 0.5, -1)):
            y, z, pitch = foot_state(p + ph)
            base = Vector((sg * ankle_rest[0], ankle_rest[1] + y, z))
            pose.update(foot_target(rig, side, base, pitch))
            kn = R.knee if side == "L" else D.mirror(R.knee)
            pose.update(pole(rig, f"CTRL_Pole_Leg.{side}", (kn[0], kn[1] - 0.45 + y * 0.5, kn[2])))
            swing = 17 * math.cos(2 * math.pi * (p + ph))      # + = arm back when the same-side foot is forward
            pose[f"FK_UpperArm.{side}"] = {"r": (swing, 0, -6 * sg)}   # arms swing slightly away from the body
            pose[f"FK_Forearm.{side}"] = {"r": (-10 - 8 * max(0, -math.cos(2 * math.pi * (p + ph))), 0, 0)}
            pose[f"FK_Hand.{side}"] = {"r": (6, 0, 0)}
        bob = 0.016 * (math.cos(4 * math.pi * p) + 1) / 2
        pose["CTRL_COG"] = {"l": (0.012 * math.sin(2 * math.pi * p), 0, -bob)}
        pose["DEF_Body"] = {"r": (2.5, -4 * math.cos(2 * math.pi * p), -2.5 * math.sin(2 * math.pi * p))}
        sq = math.cos(4 * math.pi * p)
        pose["DEF_BodyShape"] = {"s": (1 + 0.008 * sq, 1 - 0.012 * sq, 1 + 0.008 * sq)}
        key(rig, f, merge(pose, relaxed_hands(), eyes(), smile(1.05)))
    finish_action(rig, act, True)


# ---------------------------------------------------------------------------
# 5. Phone (Teléfono)
# ---------------------------------------------------------------------------

def phone_hand_wrist(centre, a, t, n):
    g = D.Phone.GRIP
    return centre - (a * g[0] + t * g[1] + n * g[2])


def anim_phone(rig):
    n = 96
    act = new_action(rig, "Phone", 0, n, True)
    base_keys(rig, 0, arms_ik=(1.0, 1.0), phone=True)
    R = D.RIG
    rest_h = {"L": (Vector(R.W), Vector(R.a), Vector(R.n)),
            "R": (Vector(D.mirror(R.W)), Vector(D.mirror(R.a)), Vector(D.mirror(R.n)))}
    # phone held up next to the body, screen towards the viewer (like the reference)
    t_up = Vector((-0.12, 0.05, 1.0)).normalized()
    n_fw = Vector((0.18, -1.0, 0.08)).normalized()
    n_fw = (n_fw - t_up * n_fw.dot(t_up)).normalized()
    a_out = t_up.cross(n_fw).normalized()            # fingers point outwards (+X)
    centre = Vector((0.60, -0.30, 1.07))
    # desired phone matrix -> hand control matrix through the rest hand/phone offset
    from .props import phone_world_matrix
    rel = rest(rig, "CTRL_IK_Hand.L").inverted() @ phone_world_matrix(1)
    # phone local axes: X = width (a_out), Y = -screen normal, Z = long axis (t_up)
    Mp = Matrix.Identity(4)
    for i in range(3):
        Mp[i][0], Mp[i][1], Mp[i][2], Mp[i][3] = a_out[i], -n_fw[i], t_up[i], centre[i]
    Mh = Mp @ rel.inverted()
    w_phone = Mh.translation.copy()
    a_out_h = (Mh.to_3x3() @ Vector((0, 1, 0))).normalized()
    n_fw_h = (Mh.to_3x3() @ Vector((0, 0, 1))).normalized()
    # right hand: open "look at this" gesture, palm up, towards the phone
    w_g = Vector((-0.50, -0.30, 0.80))
    a_g = Vector((0.25, -1.0, 0.25)).normalized()
    n_g = Vector((0.15, 0.1, 1.0)).normalized()
    for f in range(0, n + 1, 2):
        k = min(1.0, f / 14) if f < 82 else max(0.0, 1 - (f - 82) / 14)
        k = k * k * (3 - 2 * k)
        g = 0.0
        if 20 <= f <= 76:
            g = min(1.0, (f - 20) / 12) if f < 64 else max(0.0, 1 - (f - 64) / 12)
            g = g * g * (3 - 2 * g)
        bob = math.sin((f - 20) / 28 * 2 * math.pi) * g
        w0, a0, n0 = rest_h["L"]
        pose = merge(hand_target(rig, "L", w0.lerp(w_phone, k), a0.lerp(a_out_h, k).normalized(),
                                 n0.lerp(n_fw_h, k).normalized()),
                     pole(rig, "CTRL_Pole_Arm.L", (0.95, 0.15, 0.70)))
        w1, a1, n1 = rest_h["R"]
        pose = merge(pose, hand_target(rig, "R", w1.lerp(w_g + Vector((0, 0, 0.02 * bob)), g),
                                       a1.lerp(a_g, g).normalized(), n1.lerp(n_g, g).normalized()),
                     pole(rig, "CTRL_Pole_Arm.R", (-0.95, 0.30, 0.55)))
        grip = lerp_pose(hand_pose("relaxed", "L"), hand_pose("phone", "L"), min(1.0, k * 1.15))
        # the phone pops into the hand once it is away from the body, and out again at the end
        ps = float(np.interp(f, [0, 6, 10, 12, 14, 80, 84, 88, 96], [0.001, 0.001, 1.08, 0.97, 1, 1, 1.05, 0.001, 0.001]))
        grip["DEF_Prop.L"] = {"s": (ps, ps, ps)}
        free = lerp_pose(hand_pose("relaxed", "R"), hand_pose("open", "R"), g)
        pose = merge(pose, grip, free, breath(f / n, 0.6),
                     {"DEF_Body": {"r": (0, 5 * k, -2 * k + 1.0 * bob)}},
                     eyes(look=(0.012 * k, 0.004 * k), blink=0.1 if f in (46, 48) else 1.0),
                     smile(1.0 + 0.15 * g, 0.002 * g))
        key(rig, f, pose)
    finish_action(rig, act, True)


# ---------------------------------------------------------------------------
# 6. Fist (Puño)
# ---------------------------------------------------------------------------

def anim_fist(rig):
    n = 48
    act = new_action(rig, "Fist", 0, n, True)
    base_keys(rig, 0, arms_ik=(1.0, 1.0))
    open_ = merge(hand_pose("open", "L"), hand_pose("open", "R"))
    fist = merge(hand_pose("fist", "L"), hand_pose("fist", "R"))
    for f in range(0, n + 1, 2):
        # open 0-4, close 4-16, hold 16-26, open 26-38, hold 38-48
        if f <= 4:
            c = 0.0
        elif f <= 16:
            c = (f - 4) / 12
        elif f <= 26:
            c = 1.0
        elif f <= 38:
            c = 1 - (f - 26) / 12
        else:
            c = 0.0
        c = c * c * (3 - 2 * c)
        pose = {}
        for s, sg in (("L", 1), ("R", -1)):
            w = Vector((sg * 0.53, -0.22, 0.90 + 0.01 * c))
            a = Vector((sg * 0.15, -0.15, 1.0)).normalized()
            nn = Vector((sg * 0.25, -1.0, 0.0)).normalized()
            pose.update(hand_target(rig, s, w, a, nn))
            pose.update(pole(rig, f"CTRL_Pole_Arm.{s}", (sg * 0.95, 0.25, 0.60)))
        pose = merge(pose, lerp_pose(open_, fist, c), breath(f / n, 0.5),
                     {"DEF_Body": {"r": (-2 * c, 0, 0)}, "CTRL_COG": {"l": (0, 0, -0.008 * c)}},
                     eyes(blink=1 - 0.25 * c), smile(1 - 0.12 * c))
        key(rig, f, pose)
    finish_action(rig, act, True)


# ---------------------------------------------------------------------------
# 7. Present (Presentación) - point to the side and hold
# ---------------------------------------------------------------------------

def anim_present(rig):
    n = 72
    act = new_action(rig, "Present", 0, n, False)
    base_keys(rig, 0, arms_ik=(0.0, 1.0))
    R = D.RIG
    w0, a0, n0 = Vector(D.mirror(R.W)), Vector(D.mirror(R.a)), Vector(D.mirror(R.n))
    w1 = Vector((-0.80, -0.20, 0.98))
    a1 = Vector((-1.0, -0.30, 0.10)).normalized()
    n1 = Vector((0.0, -0.25, -1.0)).normalized()
    over = Vector((-0.83, -0.21, 1.00))
    for f in range(0, n + 1, 2):
        # anticipation 0-6, point 6-18 (overshoot), settle 18-24, hold
        if f <= 6:
            k = -0.08 * (f / 6)
            w = w0
        elif f <= 18:
            k = (f - 6) / 12
            w = None
        else:
            k = 1.0
            w = None
        kk = max(0.0, min(1.0, k))
        kk = kk * kk * (3 - 2 * kk)
        if f <= 18:
            wp = w0.lerp(over, kk)
        else:
            wp = over.lerp(w1, min(1.0, (f - 18) / 6))
        if f > 24:
            wp = w1 + Vector((0, 0, 0.004 * math.sin((f - 24) / 24 * 2 * math.pi)))
        pose = merge(hand_target(rig, "R", wp, a0.lerp(a1, kk).normalized(), n0.lerp(n1, kk).normalized()),
                     pole(rig, "CTRL_Pole_Arm.R", (-0.55, 0.55, 0.70)),
                     lerp_pose(hand_pose("relaxed", "R"), hand_pose("point", "R"), min(1.0, kk * 1.2)),
                     hand_pose("relaxed", "L"),
                     {"FK_UpperArm.L": {"r": (4 * kk, 0, -3 * kk)}, "FK_Forearm.L": {"r": (-10, 0, 0)}},
                     {"DEF_Body": {"r": (0, -7 * kk, 2.5 * kk)},
                      "CTRL_COG": {"l": (-0.01 * kk, 0, -0.01 * max(0, -k) * 10)}},
                     breath(f / n, 0.5),
                     eyes(look=(-0.012 * kk, 0.002 * kk)), smile(1 + 0.12 * kk, 0.002 * kk))
        key(rig, f, pose)
    finish_action(rig, act, False)


# ---------------------------------------------------------------------------

def build_all(rig, leg_ob):
    bpy.context.view_layer.objects.active = rig
    anim_idle(rig)
    anim_wave(rig)
    anim_celebrate(rig)
    anim_walk(rig, leg_ob)
    anim_phone(rig)
    anim_fist(rig)
    anim_present(rig)
    store_hand_pose_actions(rig)
    push_to_nla(rig)
    P.reset(rig)


def store_hand_pose_actions(rig):
    """One single-frame action per hand pose (both hands) - a reusable pose library."""
    for name in P.HAND_POSES:
        act = bpy.data.actions.new(f"HandPose_{name}")
        act.use_fake_user = True
        rig.animation_data.action = act
        P.reset(rig)
        key(rig, 0, merge(hand_pose(name, "L"), hand_pose(name, "R")))
    rig.animation_data.action = None


def push_to_nla(rig):
    ad = rig.animation_data
    ad.action = None
    for name, (act, s, e, loop) in ACTIONS.items():
        tr = ad.nla_tracks.new()
        tr.name = name
        st = tr.strips.new(name, int(s), act)
        st.action_frame_start, st.action_frame_end = s, e
        tr.mute = True
        tr.is_solo = False
    log("NLA tracks:", [t.name for t in ad.nla_tracks])


def set_active(rig, name):
    act, s, e, loop = ACTIONS[name]
    rig.animation_data.action = act
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = int(s), int(e)
    sc.frame_set(int(s))
