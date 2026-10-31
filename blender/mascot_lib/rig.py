"""Skeleton, controls, IK/FK switching, grip controls and skinning."""
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix

from . import design as D
from .design import RIG as R, normalize, mirror

RIG_NAME = "MASCOT_Rig"
SIDES = (("L", 1), ("R", -1))
FINGERS = ["Index", "Middle", "Ring"]   # thumb + 3 fingers (4 digits per hand)


def log(*a):
    print("[rig]", *a, flush=True)


def m(v, side):
    """Mirror a left-side vector for the right side."""
    return np.asarray(v, dtype=np.float64) if side == 1 else mirror(v)


def ortho(z, y):
    z = np.asarray(z, dtype=np.float64)
    y = normalize(y)
    z = z - y * (z @ y)
    return normalize(z)


# ---------------------------------------------------------------------------
# Bone layout
# ---------------------------------------------------------------------------

def bone_specs():
    """Returns a list of dicts: name, head, tail, z (roll reference), parent, deform."""
    B = []

    def add(name, head, tail, z, parent=None, deform=False, **kw):
        head = np.asarray(head, dtype=np.float64)
        tail = np.asarray(tail, dtype=np.float64)
        B.append(dict(name=name, head=head, tail=tail, z=ortho(z, tail - head), parent=parent,
                      deform=deform, **kw))

    fwd = np.array([0, -1.0, 0])
    up = np.array([0, 0, 1.0])
    back = np.array([0, 1.0, 0])
    ZB = D.ZB

    add("CTRL_Root", (0, 0, 0), (0, 0.45, 0), up, coll="Root", shape="WGT_Root", color="THEME09")
    add("CTRL_COG", (0, 0.0, ZB + 0.18), (0, 0.32, ZB + 0.18), up, "CTRL_Root", coll="Body",
        shape="WGT_COG", color="THEME09")
    add("DEF_Body", (0, 0, ZB), (0, 0, ZB + 0.98), fwd, "CTRL_COG", True, coll="Body",
        shape="WGT_Body", color="THEME09")
    add("DEF_BodyShape", (0, 0.0, ZB), (0, 0.0, ZB + 0.55), fwd, "DEF_Body", True, coll="Body",
        shape="WGT_Squash", color="THEME09")

    # face
    for sfx, s in SIDES:
        c, n = D.body_front_point(s * D.Face.EYE_X, D.Face.EYE_Z)
        add(f"DEF_Eye.{sfx}", c, c + up * 0.075, n, "DEF_BodyShape", True, coll="Face",
            shape="WGT_Eye", color="THEME05")
        add(f"DEF_EyeHappy.{sfx}", c + up * 0.004, c + up * 0.004 + up * 0.05, n, "DEF_BodyShape", True,
            coll="Face", shape="WGT_Happy", color="THEME05")
    sp = np.array(D.smile_points())
    sc = sp.mean(0)
    _, sn = D.body_front_point(0.0, D.Face.SMILE_Z)
    add("DEF_Smile", sc, sc + up * 0.05, sn, "DEF_BodyShape", True, coll="Face", shape="WGT_Smile",
        color="THEME05")
    tri = np.array(D.Face.MOUTH_TRI).mean(0)
    mc, mn = D.body_front_point(tri[0], tri[1] + ZB)
    add("DEF_Mouth", mc, mc + up * 0.09, mn, "DEF_BodyShape", True, coll="Face", shape="WGT_Mouth",
        color="THEME05")

    for sfx, s in SIDES:
        col = "THEME04" if s == 1 else "THEME01"
        S, E, W = m(R.S, s), m(R.E, s), m(R.W, s)
        a, t, n = m(R.a, s), m(R.t, s), m(R.n, s)
        K = m(R.knuckle_line, s)
        # --- arm: deform, FK and IK chains -----------------------------------------
        for pre, par, dfm, coll in (("DEF", "DEF_Body", True, "Deform"),
                                    ("FK", "DEF_Body", False, "Arm FK"),
                                    ("MCH_IK", "DEF_Body", False, "Mechanism")):
            shape_u = "WGT_FK" if pre == "FK" else None
            add(f"{pre}_UpperArm.{sfx}", S, E, back, par, dfm, coll=coll, shape=shape_u, color=col)
            add(f"{pre}_Forearm.{sfx}", E, W, back, f"{pre}_UpperArm.{sfx}", dfm, coll=coll,
                shape=shape_u, color=col, connect=True)
            add(f"{pre}_Hand.{sfx}", W, K, n, f"{pre}_Forearm.{sfx}", dfm, coll=coll,
                shape="WGT_FKHand" if pre == "FK" else None, color=col, connect=True)
        add(f"CTRL_IK_Hand.{sfx}", W, K, n, "CTRL_Root", coll="Arm IK", shape="WGT_IKHand", color=col)
        add(f"CTRL_Pole_Arm.{sfx}", E + back * 0.32, E + back * 0.40, up, "CTRL_Root", coll="Arm IK",
            shape="WGT_Pole", color=col)
        # --- fingers ----------------------------------------------------------------
        for fname in FINGERS:
            fd = R.fingers[fname]
            pts = [m(p, s) for p in fd["pts"]]
            par = f"DEF_Hand.{sfx}"
            for i in range(3):
                add(f"DEF_{fname}_{i + 1:02d}.{sfx}", pts[i], pts[i + 1], n, par, True, coll="Fingers",
                    shape="WGT_Finger", color=col, connect=i > 0)
                par = f"DEF_{fname}_{i + 1:02d}.{sfx}"
        tp = [m(p, s) for p in R.thumb["pts"]]
        tz = m(R.thumb["n"], s)
        par = f"DEF_Hand.{sfx}"
        for i in range(3):
            add(f"DEF_Thumb_{i + 1:02d}.{sfx}", tp[i], tp[i + 1], tz, par, True, coll="Fingers",
                shape="WGT_Finger", color=col, connect=i > 0)
            par = f"DEF_Thumb_{i + 1:02d}.{sfx}"
        # grip control floats above the back of the hand
        g0 = W + a * 0.07 - n * 0.075
        add(f"CTRL_Grip.{sfx}", g0, g0 + a * 0.05, n, f"DEF_Hand.{sfx}", coll="Fingers", shape="WGT_Grip",
            color="THEME03")
        g1 = m(R.thumb["pts"][1], s) - n * 0.05 + t * 0.03
        add(f"CTRL_ThumbGrip.{sfx}", g1, g1 + a * 0.035, n, f"DEF_Hand.{sfx}", coll="Fingers",
            shape="WGT_Grip", color="THEME03")
        # prop socket: objects held in this hand are parented here
        pc, _ = R.phone_frame(s)
        add(f"DEF_Prop.{sfx}", pc, pc + a * 0.06, n, f"DEF_Hand.{sfx}", True, coll="Props",
            shape="WGT_Prop", color="THEME03")

        # --- legs -------------------------------------------------------------------
        hip, knee, ankle = m(R.hip, s), m(R.knee, s), m(R.ankle, s)
        ball, toe = m(R.ball, s), m(R.toe_tip, s)
        for pre, dfm, coll in (("DEF", True, "Deform"), ("FK", False, "Leg FK"),
                               ("MCH_IK", False, "Mechanism")):
            shp = "WGT_FK" if pre == "FK" else None
            add(f"{pre}_Thigh.{sfx}", hip, knee, fwd, "DEF_Body", dfm, coll=coll, shape=shp, color=col)
            add(f"{pre}_Shin.{sfx}", knee, ankle, fwd, f"{pre}_Thigh.{sfx}", dfm, coll=coll, shape=shp,
                color=col, connect=True)
            add(f"{pre}_Foot.{sfx}", ankle, ball, up, f"{pre}_Shin.{sfx}", dfm, coll=coll,
                shape="WGT_FKFoot" if pre == "FK" else None, color=col, connect=True)
        add(f"DEF_Toe.{sfx}", ball, toe, up, f"DEF_Foot.{sfx}", True, coll="Leg FK", shape="WGT_Toe",
            color=col, connect=True)
        add(f"CTRL_IK_Foot.{sfx}", ankle, ball, up, "CTRL_Root", coll="Leg IK", shape="WGT_IKFoot", color=col)
        add(f"CTRL_Pole_Leg.{sfx}", knee + fwd * 0.40, knee + fwd * 0.48, up, "CTRL_Root", coll="Leg IK",
            shape="WGT_Pole", color=col)
    return B


# ---------------------------------------------------------------------------
# Widgets (custom bone shapes)
# ---------------------------------------------------------------------------

def _widget(name, verts, edges, col):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def circle(n=32, r=1.0, axis="Y", z=0.0):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = math.cos(a) * r, math.sin(a) * r
        pts.append((x, z, y) if axis == "Y" else (x, y, z))
    return pts, [(i, (i + 1) % n) for i in range(n)]


def build_widgets(col):
    W = {}
    v, e = circle(48, 1.0, "Z")
    W["WGT_Root"] = _widget("WGT_Root", v, e, col)
    v, e = circle(6, 1.0, "Y", 0.5)
    W["WGT_COG"] = _widget("WGT_COG", v, e, col)
    v, e = circle(32, 0.55, "Y", 0.35)
    W["WGT_Body"] = _widget("WGT_Body", v, e, col)
    sq = [(-0.5, 1.0, -0.5), (0.5, 1.0, -0.5), (0.5, 1.0, 0.5), (-0.5, 1.0, 0.5)]
    W["WGT_Squash"] = _widget("WGT_Squash", sq, [(0, 1), (1, 2), (2, 3), (3, 0)], col)
    v, e = circle(24, 0.5, "Y", 0.5)
    W["WGT_Eye"] = _widget("WGT_Eye", v, e, col)
    W["WGT_Happy"] = _widget("WGT_Happy", [(-0.6, 0.2, 0), (0, 0.6, 0), (0.6, 0.2, 0)], [(0, 1), (1, 2)], col)
    W["WGT_Smile"] = _widget("WGT_Smile", [(-0.9, 0.3, 0), (0, -0.2, 0), (0.9, 0.3, 0)], [(0, 1), (1, 2)], col)
    W["WGT_Mouth"] = _widget("WGT_Mouth", [(0, 0.9, 0), (-0.5, 0.0, 0), (0.6, 0.3, 0)],
                             [(0, 1), (1, 2), (2, 0)], col)
    v, e = circle(24, 0.25, "Y", 0.5)
    W["WGT_FK"] = _widget("WGT_FK", v, e, col)
    v, e = circle(24, 0.45, "Y", 0.3)
    W["WGT_FKHand"] = _widget("WGT_FKHand", v, e, col)
    W["WGT_FKFoot"] = W["WGT_FKHand"]
    cube = [(-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5),
            (-0.5, 1, -0.5), (0.5, 1, -0.5), (0.5, 1, 0.5), (-0.5, 1, 0.5)]
    ce = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    W["WGT_IKHand"] = _widget("WGT_IKHand", cube, ce, col)
    W["WGT_IKFoot"] = _widget("WGT_IKFoot", [(x * 1.4, y * 1.6 - 0.3, z * 0.3) for x, y, z in cube], ce, col)
    oct_v = [(0.5, 0, 0), (-0.5, 0, 0), (0, 0.5, 0), (0, -0.5, 0), (0, 0, 0.5), (0, 0, -0.5)]
    oct_e = [(0, 2), (2, 1), (1, 3), (3, 0), (0, 4), (4, 1), (1, 5), (5, 0), (2, 4), (4, 3), (3, 5), (5, 2)]
    W["WGT_Pole"] = _widget("WGT_Pole", oct_v, oct_e, col)
    v, e = circle(12, 0.35, "Y", 0.5)
    W["WGT_Finger"] = _widget("WGT_Finger", v, e, col)
    W["WGT_Toe"] = W["WGT_Finger"]
    W["WGT_Grip"] = _widget("WGT_Grip", [(0, 0, 0), (0, 1, 0), (-0.4, 0.75, 0), (0, 1, 0), (0.4, 0.75, 0)],
                            [(0, 1), (1, 2), (3, 4)], col)
    v, e = circle(4, 0.5, "Y", 0.5)
    W["WGT_Prop"] = _widget("WGT_Prop", v, e, col)
    for ob in W.values():
        ob.hide_render = True
        ob.hide_viewport = True
    return W


# ---------------------------------------------------------------------------
# Armature construction
# ---------------------------------------------------------------------------

def add_driver(owner, path, rig, prop, expr="var"):
    fc = owner.driver_add(path)
    drv = fc.driver
    drv.type = "SCRIPTED" if expr != "var" else "AVERAGE"
    if expr != "var":
        drv.expression = expr
    var = drv.variables.new()
    var.name = "var"
    var.type = "SINGLE_PROP"
    var.targets[0].id = rig
    var.targets[0].data_path = f'pose.bones["CTRL_Root"]["{prop}"]'
    return fc


def build_armature(col, widgets):
    arm = bpy.data.armatures.new(RIG_NAME)
    arm.display_type = "OCTAHEDRAL"
    rig = bpy.data.objects.new(RIG_NAME, arm)
    col.objects.link(rig)
    rig.show_in_front = True
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    rig.select_set(True)

    specs = bone_specs()
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for s in specs:
        b = eb.new(s["name"])
        b.head = Vector(s["head"])
        b.tail = Vector(s["tail"])
        b.align_roll(Vector(s["z"]))
        b.use_deform = s["deform"]
    for s in specs:
        if s["parent"]:
            b = eb[s["name"]]
            b.parent = eb[s["parent"]]
            b.use_connect = bool(s.get("connect")) and (b.head - b.parent.tail).length < 1e-5
    bpy.ops.object.mode_set(mode="OBJECT")

    # bone collections, colours and shapes
    for s in specs:
        cname = s.get("coll", "Misc")
        bc = arm.collections.get(cname) or arm.collections.new(cname)
        bc.assign(arm.bones[s["name"]])
        bone = arm.bones[s["name"]]
        if s.get("color"):
            bone.color.palette = s["color"]
        pb = rig.pose.bones[s["name"]]
        pb.rotation_mode = "XYZ" if not s["name"].startswith("CTRL_IK") else "QUATERNION"
        if s["name"].startswith(tuple(f"DEF_{f}_01" for f in FINGERS)):
            # knuckle: spread (Z) first, then flex (X) - like a real MCP joint, so a
            # spread finger keeps its own curling plane and neighbours never collide
            pb.rotation_mode = "ZYX"
        if s.get("shape"):
            pb.custom_shape = widgets[s["shape"]]
            if s["shape"] in ("WGT_IKHand",):
                pb.custom_shape_scale_xyz = (0.12, 0.12, 0.12)
                pb.use_custom_shape_bone_size = False
            if s["shape"] in ("WGT_IKFoot",):
                pb.custom_shape_scale_xyz = (0.14, 0.14, 0.14)
                pb.use_custom_shape_bone_size = False
            if s["shape"] == "WGT_Pole":
                pb.custom_shape_scale_xyz = (0.05, 0.05, 0.05)
                pb.use_custom_shape_bone_size = False
    for cname in ("Mechanism", "Deform"):
        arm.collections[cname].is_visible = False
    if "Arm IK" in arm.collections:
        arm.collections["Arm IK"].is_visible = True

    # custom properties: IK/FK switches
    root = rig.pose.bones["CTRL_Root"]
    for sfx, _ in SIDES:
        for limb, default in (("Arm", 0.0), ("Leg", 1.0)):
            key = f"IK_{limb}.{sfx}"
            root[key] = default
            ui = root.id_properties_ui(key)
            ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
                      description=f"0 = FK, 1 = IK ({limb.lower()} {sfx})")

    P = rig.pose.bones
    for sfx, _ in SIDES:
        # arm
        ik = P[f"MCH_IK_Forearm.{sfx}"].constraints.new("IK")
        ik.target, ik.subtarget = rig, f"CTRL_IK_Hand.{sfx}"
        ik.pole_target, ik.pole_subtarget = rig, f"CTRL_Pole_Arm.{sfx}"
        ik.chain_count = 2
        cr = P[f"MCH_IK_Hand.{sfx}"].constraints.new("COPY_ROTATION")
        cr.target, cr.subtarget = rig, f"CTRL_IK_Hand.{sfx}"
        # leg
        ik = P[f"MCH_IK_Shin.{sfx}"].constraints.new("IK")
        ik.target, ik.subtarget = rig, f"CTRL_IK_Foot.{sfx}"
        ik.pole_target, ik.pole_subtarget = rig, f"CTRL_Pole_Leg.{sfx}"
        ik.chain_count = 2
        cr = P[f"MCH_IK_Foot.{sfx}"].constraints.new("COPY_ROTATION")
        cr.target, cr.subtarget = rig, f"CTRL_IK_Foot.{sfx}"

        for limb, bones in (("Arm", ("UpperArm", "Forearm", "Hand")), ("Leg", ("Thigh", "Shin", "Foot"))):
            for bname in bones:
                d = P[f"DEF_{bname}.{sfx}"]
                c1 = d.constraints.new("COPY_TRANSFORMS")
                c1.name = "FK"
                c1.target, c1.subtarget = rig, f"FK_{bname}.{sfx}"
                c2 = d.constraints.new("COPY_TRANSFORMS")
                c2.name = "IK"
                c2.target, c2.subtarget = rig, f"MCH_IK_{bname}.{sfx}"
                add_driver(c2, "influence", rig, f"IK_{limb}.{sfx}")

        # grip: finger curl from one control (adds to the finger's own rotation)
        for fname in FINGERS:
            for i, infl in ((1, 1.0), (2, 1.0), (3, 0.8)):
                c = P[f"DEF_{fname}_{i:02d}.{sfx}"].constraints.new("COPY_ROTATION")
                c.name = "Grip"
                c.target, c.subtarget = rig, f"CTRL_Grip.{sfx}"
                c.use_y = c.use_z = False
                c.mix_mode = "ADD"
                c.target_space = c.owner_space = "LOCAL_SPACE" if False else "LOCAL"
                c.influence = infl
        for i, infl in ((1, 0.6), (2, 1.0), (3, 1.0)):
            c = P[f"DEF_Thumb_{i:02d}.{sfx}"].constraints.new("COPY_ROTATION")
            c.name = "Grip"
            c.target, c.subtarget = rig, f"CTRL_ThumbGrip.{sfx}"
            c.mix_mode = "ADD"
            c.target_space = c.owner_space = "LOCAL"
            c.influence = infl

        # limit grip controls to rotation
        for g in (f"CTRL_Grip.{sfx}", f"CTRL_ThumbGrip.{sfx}"):
            P[g].lock_location = (True, True, True)
            P[g].lock_scale = (True, True, True)
            P[g].lock_rotation = (False, True, True)       # X = close / open
            lim = P[g].constraints.new("LIMIT_ROTATION")
            lim.use_limit_x = True
            lim.min_x, lim.max_x = math.radians(-15), math.radians(95)
            lim.owner_space = "LOCAL"
            lim.use_transform_limit = True
        # anatomical limits on every finger joint (flexion X, spread Z on the knuckle)
        for fname in FINGERS + ["Thumb"]:
            for i in (1, 2, 3):
                pb = P[f"DEF_{fname}_{i:02d}.{sfx}"]
                lim = pb.constraints.new("LIMIT_ROTATION")
                lim.name = "Joint limits"
                lim.owner_space = "LOCAL"
                lim.use_limit_x = True
                if fname == "Thumb":
                    lim.min_x, lim.max_x = math.radians(-40), math.radians(110)
                else:
                    lim.min_x, lim.max_x = math.radians(-25), math.radians(115)
                    lim.use_limit_z = True
                    lim.min_z, lim.max_z = (math.radians(-25), math.radians(25)) if i == 1 else (0.0, 0.0)

    calibrate_poles(rig)
    return rig


def _bone_world(rig, name):
    return rig.matrix_world @ rig.pose.bones[name].matrix


def calibrate_poles(rig):
    """Find the IK pole angle that leaves the rest pose untouched."""
    P = rig.pose.bones
    for sfx, _ in SIDES:
        for limb, first, second in (("Arm", "UpperArm", "Forearm"), ("Leg", "Thigh", "Shin")):
            ik = P[f"MCH_IK_{second}.{sfx}"].constraints["IK"]
            ref = rig.data.bones[f"MCH_IK_{first}.{sfx}"].matrix_local

            def err(angle):
                ik.pole_angle = math.radians(angle)
                bpy.context.view_layer.update()
                cur = P[f"MCH_IK_{first}.{sfx}"].matrix
                return sum((cur.col[i].xyz - ref.col[i].xyz).length for i in range(3))
            best = min(range(-180, 180, 5), key=err)
            fine = min(np.arange(best - 5, best + 5, 0.1), key=err)
            e = err(fine)
            log(f"pole {limb}.{sfx}: {fine:.1f} deg (residual {e:.5f})")


# ---------------------------------------------------------------------------
# Skinning
# ---------------------------------------------------------------------------

def bind(ob, rig, weights):
    """weights: {vertex_group_name: np.array per vertex} or {name: 1.0} for rigid parts."""
    n = len(ob.data.vertices)
    for name, w in weights.items():
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        w = np.full(n, float(w)) if np.isscalar(w) else w
        nz = np.nonzero(w > 0)[0]
        for val in np.unique(np.round(w[nz], 4)):
            idx = nz[np.round(w[nz], 4) == val]
            vg.add(idx.tolist(), float(val), "REPLACE")
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_deform_preserve_volume = False
    ob.parent = rig
    ob.matrix_parent_inverse = rig.matrix_world.inverted()


def limb_weights(ob, groups, prefix_map):
    from .design import compute_weights, smooth_and_limit
    from .geometry import mesh_arrays
    v, e = mesh_arrays(ob)
    w = compute_weights(v, groups)
    w = smooth_and_limit(w, e, iters=2)
    return {prefix_map(k): val for k, val in w.items()}


def skin_all(objs, rig):
    bind(objs["Body"][0], rig, {"DEF_BodyShape": 1.0})
    for sfx in ("L", "R"):
        bind(objs[f"Eye.{sfx}"][0], rig, {f"DEF_Eye.{sfx}": 1.0})
        bind(objs[f"EyeHappy.{sfx}"][0], rig, {f"DEF_EyeHappy.{sfx}": 1.0})
    bind(objs["Smile"][0], rig, {"DEF_Smile": 1.0})
    bind(objs["Mouth"][0], rig, {"DEF_Mouth": 1.0})

    arm_w = limb_weights(objs["Arm.L"][0], R.arm_weight_groups(), lambda k: f"DEF_{k}")
    leg_w = limb_weights(objs["Leg.L"][0], R.leg_weight_groups(), lambda k: f"DEF_{k}")
    for sfx in ("L", "R"):
        bind(objs[f"Arm.{sfx}"][0], rig, {f"{k}.{sfx}": w for k, w in arm_w.items()})
        bind(objs[f"Leg.{sfx}"][0], rig, {f"{k}.{sfx}": w for k, w in leg_w.items()})
    log("skinning done:", sorted(arm_w), sorted(leg_w))
