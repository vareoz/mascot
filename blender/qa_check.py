"""Numerical quality control on the deformed meshes of every animation.

    blender -b export/mascot.blend -P blender/qa_check.py

Checks, frame by frame (every 2nd frame of every clip, plus every hand pose):
  * feet never go below the floor (except while airborne in the jump);
  * hands / fingers never enter the body;
  * the phone never enters the body;
  * self-intersections of each deformed arm+hand mesh (fingers passing
    through each other or through the palm), using a BVH triangle overlap test
    that ignores neighbouring faces;
  * the body keeps its silhouette (only uniform-ish breathing scale).
Writes renders/qa_report.json and renders/qa_report.md.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from mascot_lib import design as D  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "renders")
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["MASCOT_Rig"]
scene = bpy.context.scene
ANIMS = ["Idle", "Wave", "Celebrate", "Walk", "Phone", "Fist", "Present"]
HAND_BONES = ("DEF_Hand", "DEF_Index", "DEF_Middle", "DEF_Ring", "DEF_Thumb")


def evaluated(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    me = eo.to_mesh()
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3) @ np.array(ob.matrix_world.to_3x3()).T + np.array(ob.matrix_world.translation)
    polys = [tuple(p.vertices) for p in me.polygons]
    eo.to_mesh_clear()
    return v, polys


def hand_mask(ob):
    idx = {g.index for g in ob.vertex_groups if g.name.startswith(HAND_BONES)}
    m = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        m[v.index] = sum(g.weight for g in v.groups if g.group in idx) > 0.5
    return m


def body_space(points):
    pb = rig.pose.bones["DEF_BodyShape"]
    deform = (rig.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted())
    inv = np.array(deform.inverted())
    p = np.c_[points, np.ones(len(points))] @ inv.T
    return p[:, :3]


CHAINS = ("Index", "Middle", "Ring", "Thumb")


def dominant_chains(ob):
    names = {g.index: g.name for g in ob.vertex_groups}
    out = []
    for v in ob.data.vertices:
        g = max(v.groups, key=lambda g: g.weight)
        n = names[g.group]
        out.append(next((c for c in CHAINS if c in n), "Palm/Arm"))
    return out


def self_intersections(v, polys, chains=None):
    """Returns (pairs between different digits, pairs inside one joint crease)."""
    bm = bmesh.new()
    verts = [bm.verts.new(c) for c in v]
    for p in polys:
        bm.faces.new([verts[i] for i in p])
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    pairs = tree.overlap(tree)
    sets = [set(p) for p in polys]
    bad = [(a, b) for a, b in pairs if a < b and not (sets[a] & sets[b])]
    # ignore pairs whose faces share a neighbour vertex ring (tiny creases)
    ring = {}
    for f in bm.faces:
        ring[f.index] = {e.other_vert(vv).index for vv in f.verts for e in vv.link_edges} | sets[f.index]
    real = [(a, b) for a, b in bad if not (ring[a] & sets[b])]
    bm.free()
    if chains is None:
        return len(real), 0
    between = 0
    for a, b in real:
        ca, cb = chains[polys[a][0]], chains[polys[b][0]]
        if ca != cb and "Palm/Arm" not in (ca, cb):
            between += 1
    return between, len(real) - between


def main():
    arms = [bpy.data.objects["MASCOT_ArmHand.L"], bpy.data.objects["MASCOT_ArmHand.R"]]
    legs = [bpy.data.objects["MASCOT_LegFoot.L"], bpy.data.objects["MASCOT_LegFoot.R"]]
    phone = bpy.data.objects["PROP_Phone"]
    masks = [hand_mask(a) for a in arms]
    chains = [dominant_chains(a) for a in arms]
    for t in rig.animation_data.nla_tracks:
        t.mute = True
    report = {"clips": {}, "hand_poses": {}}

    for name in ANIMS:
        act = bpy.data.actions[name]
        rig.animation_data.action = act
        s, e = int(act.frame_range[0]), int(act.frame_range[1])
        worst = dict(floor_mm=1e9, hand_in_body_mm=0.0, phone_in_body_mm=0.0, hand_in_phone_mm=0.0,
                     digit_collisions=0, crease_overlaps=0, body_scale_dev=0.0)
        for f in range(s, e + 1, 2):
            scene.frame_set(f)
            cog_z = rig.pose.bones["CTRL_COG"].location.z
            for lg in legs:
                v, _ = evaluated(lg)
                if not (name == "Celebrate" and cog_z > 0.03):
                    worst["floor_mm"] = min(worst["floor_mm"], v[:, 2].min() * 1000)
            for arm, m, ch in zip(arms, masks, chains):
                v, polys = evaluated(arm)
                d = D.BODY(body_space(v[m]))
                worst["hand_in_body_mm"] = max(worst["hand_in_body_mm"], float(-d.min() * 1000) if d.min() < 0 else 0)
                if f % 6 == 0:
                    btw, crease = self_intersections(v, polys, ch)
                    worst["digit_collisions"] = max(worst["digit_collisions"], btw)
                    worst["crease_overlaps"] = max(worst["crease_overlaps"], crease)
            if rig.pose.bones["DEF_Prop.L"].scale.x > 0.5:
                v, _ = evaluated(phone)
                d = D.BODY(body_space(v))
                worst["phone_in_body_mm"] = max(worst["phone_in_body_mm"], float(-d.min() * 1000) if d.min() < 0 else 0)
                # hand vs phone: phone box in its own (posed) frame
                pm = np.array(phone.matrix_world.inverted())
                hv, _ = evaluated(arms[0])
                loc = np.c_[hv, np.ones(len(hv))] @ pm.T
                q = np.abs(loc[:, :3]) - (np.array([D.Phone.W, D.Phone.T, D.Phone.H]) / 2 - 0.006)
                dbox = np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0) - 0.006
                worst["hand_in_phone_mm"] = max(worst["hand_in_phone_mm"], float(-dbox.min() * 1000) if dbox.min() < 0 else 0)
            sc = rig.pose.bones["DEF_BodyShape"].scale
            worst["body_scale_dev"] = max(worst["body_scale_dev"], max(abs(c - 1) for c in sc))
        worst = {k: round(v, 3) if isinstance(v, float) else v for k, v in worst.items()}
        report["clips"][name] = worst
        print("[qa]", name, worst, flush=True)

    for act in bpy.data.actions:
        if not act.name.startswith("HandPose_"):
            continue
        rig.animation_data.action = act
        scene.frame_set(0)
        btw = crease = 0
        for arm, ch in zip(arms, chains):
            v, polys = evaluated(arm)
            b, c = self_intersections(v, polys, ch)
            btw, crease = max(btw, b), max(crease, c)
        report["hand_poses"][act.name[9:]] = {"digit_collisions": btw, "crease_overlaps": crease}
        print("[qa]", act.name, btw, crease, flush=True)

    rig.animation_data.action = bpy.data.actions["Idle"]
    with open(os.path.join(OUT, "qa_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    lines = ["# Informe de control de calidad (automático)", "",
             "Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).", "",
             "Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del "
             "teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que "
             "se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); "
             "variación máxima de escala del cuerpo (respiración / squash).", "",
             "| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Mano en teléfono (mm) "
             "| Choques entre dedos | Solapes en pliegues | Escala cuerpo |",
             "|---|---|---|---|---|---|---|---|"]
    for k, w in report["clips"].items():
        lines.append(f"| {k} | {w['floor_mm']:.1f} | {w['hand_in_body_mm']:.1f} | {w['phone_in_body_mm']:.1f} "
                     f"| {w['hand_in_phone_mm']:.1f} "
                     f"| {w['digit_collisions']} | {w['crease_overlaps']} | {w['body_scale_dev'] * 100:.1f}% |")
    lines += ["", "| Pose de mano | Choques entre dedos | Solapes en pliegues |", "|---|---|---|"]
    for k, w in report["hand_poses"].items():
        lines.append(f"| {k} | {w['digit_collisions']} | {w['crease_overlaps']} |")
    with open(os.path.join(OUT, "qa_report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("[qa] report written")


main()
