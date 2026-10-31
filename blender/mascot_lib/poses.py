"""Pose helpers, hand pose library and keyframing utilities.

Rotations are Euler XYZ in degrees in each bone's local space.  For every
finger bone local +X rotation flexes (curls) the finger towards the palm and
+Z spreads it towards the thumb.  Values written for a ``.L`` bone are
mirrored automatically when applied to the ``.R`` side (X location, Y and Z
rotation flip sign), which is Blender's standard symmetric convention.
"""
import math
import bpy
from mathutils import Euler, Quaternion, Vector

FINGERS = ["Index", "Middle", "Ring", "Pinky"]


def mirror_name(name):
    if name.endswith(".L"):
        return name[:-2] + ".R"
    if name.endswith(".R"):
        return name[:-2] + ".L"
    return name


def mirror_channels(ch):
    out = {}
    for k, v in ch.items():
        if k == "r":
            out[k] = (v[0], -v[1], -v[2])
        elif k == "l":
            out[k] = (-v[0], v[1], v[2])
        elif k == "q":          # quaternion (w, x, y, z)
            out[k] = (v[0], v[1], -v[2], -v[3])
        else:
            out[k] = v
    return out


def expand(pose):
    """Keys ending in '.X' are applied to both sides (mirrored on the right)."""
    out = {}
    for name, ch in pose.items():
        if name.endswith(".X"):
            base = name[:-2]
            out[base + ".L"] = ch
            out[base + ".R"] = mirror_channels(ch)
        else:
            out[name] = ch
    return out


def mirrored(pose):
    """Mirror a one-sided pose to the other side."""
    return {mirror_name(k): (mirror_channels(v) if (k.endswith(".L") or k.endswith(".R")) else v)
            for k, v in pose.items()}


def merge(*poses):
    out = {}
    for p in poses:
        for k, v in p.items():
            out.setdefault(k, {}).update(v)
    return out


def reset(rig):
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)


def apply(rig, pose):
    for name, ch in expand(pose).items():
        pb = rig.pose.bones[name]
        if "r" in ch:
            if pb.rotation_mode == "QUATERNION":
                pb.rotation_quaternion = Euler([math.radians(a) for a in ch["r"]], "XYZ").to_quaternion()
            else:
                pb.rotation_euler = [math.radians(a) for a in ch["r"]]
        if "q" in ch:
            pb.rotation_quaternion = ch["q"]
        if "l" in ch:
            pb.location = ch["l"]
        if "s" in ch:
            s = ch["s"]
            pb.scale = (s, s, s) if isinstance(s, (int, float)) else s
        for k, v in ch.items():
            if k.startswith("prop:"):
                pb[k[5:]] = v


def key(rig, frame, pose, interp=None):
    """Apply and keyframe a pose (only the channels given)."""
    apply(rig, pose)
    for name, ch in expand(pose).items():
        pb = rig.pose.bones[name]
        paths = []
        if "r" in ch:
            paths.append("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler")
        if "q" in ch:
            paths.append("rotation_quaternion")
        if "l" in ch:
            paths.append("location")
        if "s" in ch:
            paths.append("scale")
        for p in paths:
            pb.keyframe_insert(p, frame=frame, group=name)
        for k in ch:
            if k.startswith("prop:"):
                pb.keyframe_insert(f'["{k[5:]}"]', frame=frame, group=name)


# ---------------------------------------------------------------------------
# Hand pose library (left hand; use mirrored() for the right one)
# ---------------------------------------------------------------------------

def fingers(curls, spreads=(0, 0, 0, 0), side="L"):
    """curls: per finger (c1, c2, c3) in degrees."""
    out = {}
    for fname, c, s in zip(FINGERS, curls, spreads):
        out[f"DEF_{fname}_01.{side}"] = {"r": (c[0], 0, s)}
        out[f"DEF_{fname}_02.{side}"] = {"r": (c[1], 0, 0)}
        out[f"DEF_{fname}_03.{side}"] = {"r": (c[2], 0, 0)}
    return out


def thumb(r1, r2, r3, side="L"):
    return {f"DEF_Thumb_01.{side}": {"r": r1}, f"DEF_Thumb_02.{side}": {"r": r2},
            f"DEF_Thumb_03.{side}": {"r": r3}}


def grip_controls(g=0.0, tg=0.0, side="L"):
    return {f"CTRL_Grip.{side}": {"r": (g, 0, 0)}, f"CTRL_ThumbGrip.{side}": {"r": (tg, 0, 0)}}


HAND_POSES = {
    # fingers extended and clearly spread apart
    "open": merge(fingers([(-6, -4, -2), (-6, -4, -2), (-6, -4, -2), (-6, -4, -2)], (9, 2, -7, -16)),
                  thumb((0, 0, 14), (-6, 0, 0), (-8, 0, 0))),
    # natural resting hand, fingers gently curved
    "relaxed": merge(fingers([(14, 18, 12), (18, 22, 14), (22, 25, 16), (26, 28, 18)], (2, 0, -2, -4)),
                     thumb((4, 0, -4), (10, 0, 0), (12, 0, 0))),
    # closed fist, thumb wrapped over the middle phalanges of index and middle
    "fist": merge(fingers([(84, 96, 62), (86, 98, 62), (88, 98, 62), (90, 96, 60)], (3, 0, -3, -6)),
                  thumb((22, -28, -38), (34, 0, 0), (38, 0, 0))),
    # waving: open, fingers together but separated, slightly bent back
    "wave": merge(fingers([(-4, -2, 0), (-4, -2, 0), (-4, -2, 0), (-4, -2, 0)], (5, 1, -4, -9)),
                  thumb((0, 0, 8), (-4, 0, 0), (-4, 0, 0))),
    # pointing with the index finger
    "point": merge(fingers([(-4, -2, 0), (86, 98, 62), (88, 98, 62), (90, 96, 60)], (2, 0, -3, -6)),
                   thumb((22, -26, -34), (30, 0, 0), (34, 0, 0))),
}


def hand_pose(name, side="L"):
    p = HAND_POSES[name]
    return p if side == "L" else mirrored(p)


def solve_hand_poses(rig, log=print):
    """Refines the library with the contact solver (thumb over the fist, phone grip)."""
    from . import solver as SV
    from . import design as D
    fk = SV.HandFK(rig, "L")

    def finger_angles(pose):
        out = {}
        for f in FINGERS:
            out[f] = [tuple(pose[f"DEF_{f}_{i:02d}.L"]["r"]) for i in (1, 2, 3)]
        return out

    for name, targets in (("fist", ("Index", "Middle")), ("point", ("Middle", "Ring"))):
        cur = finger_angles(HAND_POSES[name])
        curls = [[a[0] for a in cur[f]] for f in FINGERS]
        if name == "fist":
            sp, adj = SV.solve_spreads(fk, curls)
        else:   # index stays straight: only ring and pinky need to clear each other
            sp, adj = SV.solve_spreads(fk, curls)
        for i, f in enumerate(FINGERS):
            HAND_POSES[name][f"DEF_{f}_01.L"]["r"] = (curls[i][0], 0, float(sp[i]))
        log(f"[poses] {name}: spreads {sp} (min neighbour gap {adj * 1000:.1f}mm)")
        fa = finger_angles(HAND_POSES[name])
        th, s = SV.solve_thumb_over_fingers(fk, fa, targets)
        HAND_POSES[name].update(thumb(*th))
        log(f"[poses] {name}: thumb {th} score {s:.4f}; finger clearances "
            + ", ".join(f"{k} {v * 1000:.1f}mm" for k, v in SV.finger_clearances(fk, fa).items()))

    spreads = {"Index": 3.0, "Middle": 0.0, "Ring": -3.0, "Pinky": -7.0}
    SV.solve_phone_placement(fk, D.RIG, spreads, log=log)
    c, axes = D.RIG.phone_frame(1)
    box = SV.PhoneBox(c, axes, (D.Phone.W / 2, D.Phone.T / 2, D.Phone.H / 2), 0.006)
    grip = {}
    others = []
    for f in FINGERS:
        ang, gaps = SV.solve_finger_grip(fk, f, box, spreads[f])
        grip[f] = ang
        P, Rr, S = fk.capsules(f, ang)
        others.append((P, Rr))
        log(f"[poses] phone grip {f}: {[a[0] for a in ang]} gaps(mm) "
            + " ".join(f"{g * 1000:.1f}" for g in gaps))
    th, gaps, s = SV.solve_thumb_grip(fk, box, others)
    log(f"[poses] phone grip thumb: {th} gaps(mm) {gaps[0] * 1000:.1f} {gaps[1] * 1000:.1f}")
    pose = {}
    for f in FINGERS:
        for i in range(3):
            pose[f"DEF_{f}_{i + 1:02d}.L"] = {"r": grip[f][i]}
    pose.update(thumb(*th))
    HAND_POSES["phone"] = pose
    clear = SV.finger_clearances(fk, grip)
    log("[poses] phone grip finger clearances " + ", ".join(f"{k} {v * 1000:.1f}mm" for k, v in clear.items()))
    return HAND_POSES
