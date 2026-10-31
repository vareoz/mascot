"""Builds the complete, animatable mascot from scratch.

Usage (from the repository root):

    blender -b --factory-startup -P blender/build_mascot.py

Outputs:
    export/mascot.blend   editable project (geometry, materials, rig, actions)
    export/mascot.glb     model + materials + skeleton + animations (web)
    export/mascot.fbx     same content for DCC / game engines
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "export")

import bpy  # noqa: E402

from mascot_lib import geometry as G, materials as M, studio as S, rig as RG  # noqa: E402
from mascot_lib import animations as A, props as PR  # noqa: E402


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Mascot"
    scene.unit_settings.system = "METRIC"
    scene.render.fps = 24

    top = S.ensure_collection("MASCOT")
    cols = {
        "body": S.ensure_collection("MASCOT_Body", top),
        "limbs": S.ensure_collection("MASCOT_Limbs", top),
        "hands": S.ensure_collection("MASCOT_Hands", top),
        "acc": S.ensure_collection("MASCOT_Accessories", top),
        "mats": S.ensure_collection("MASCOT_Materials", top),
        "rig": S.ensure_collection("MASCOT_Rig", top),
        "wgt": S.ensure_collection("WGT_Widgets", top),
    }

    screen_img = G.draw_screen_image()
    mats = M.build_materials(screen_img)
    objs = G.build_all(cols)
    for k, (ob, _) in objs.items():
        if k == "Body":
            M.assign(ob, mats["body"])
        elif k.startswith("Eye"):
            M.assign(ob, mats["eyes"])
        elif k in ("Smile", "Mouth"):
            M.assign(ob, mats["face"])
        else:
            M.assign(ob, mats["limbs"])
    M.build_swatches(cols["mats"], mats)

    widgets = RG.build_widgets(cols["wgt"])
    rig = RG.build_armature(cols["rig"], widgets)
    RG.skin_all(objs, rig)

    from mascot_lib import poses as PO
    PO.solve_hand_poses(rig, log=A.log)          # contact solver: fist, point, phone grip
    phone, screen = G.build_phone(cols["acc"], screen_img)
    M.assign(phone, mats["phone"])
    M.assign(screen, mats["screen"])
    PR.attach_phone(rig, phone)

    A.build_all(rig, objs["Leg.L"][0])

    S.build_studio(mats)
    cols["wgt"].hide_render = True
    vl = bpy.context.view_layer
    vl.layer_collection.children["MASCOT"].children["WGT_Widgets"].exclude = True
    vl.layer_collection.children["MASCOT"].children["MASCOT_Materials"].hide_viewport = True
    cols["mats"].hide_render = True

    A.set_active(rig, "Idle")
    bpy.context.view_layer.objects.active = rig
    blend = os.path.join(OUT, "mascot.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print(f"[build] saved {blend} ({time.time() - t0:.0f}s)")

    from mascot_lib import export as EX
    EX.export_glb(rig, os.path.join(OUT, "mascot.glb"))
    EX.export_fbx(rig, os.path.join(OUT, "mascot.fbx"))
    # re-open the clean saved file so the export state never leaks into it
    print(f"[build] done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
