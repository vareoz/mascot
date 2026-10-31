"""GLB / FBX export of the mesh, materials, skeleton (deform bones) and clips."""
import bpy


def _select_character(rig):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    keep = [rig] + [o for o in bpy.data.objects
                    if o.parent == rig and o.type == "MESH"]
    keep += [o for o in bpy.data.objects if o.parent in keep and o.type == "MESH" and o not in keep]
    for o in keep:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    return keep


def _prepare(rig):
    from . import poses as P
    rig.animation_data.action = None
    for t in rig.animation_data.nla_tracks:
        t.mute = False
    P.reset(rig)
    bpy.context.view_layer.update()


def export_glb(rig, path):
    _prepare(rig)
    objs = _select_character(rig)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True,
        export_apply=False, export_texcoords=True, export_normals=True,
        export_materials="EXPORT", export_image_format="AUTO",
        export_skins=True, export_all_influences=False, export_def_bones=True,
        export_animations=True, export_animation_mode="NLA_TRACKS",
        export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=True,
        export_anim_single_armature=True, export_reset_pose_bones=True,
        export_morph=False, export_yup=True, export_extras=False, export_cameras=False,
        export_lights=False)
    print(f"[export] GLB -> {path} ({len(objs)} objects)")


def export_fbx(rig, path):
    _prepare(rig)
    _select_character(rig)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False, use_armature_deform_only=True, primary_bone_axis="Y",
        secondary_bone_axis="X", bake_anim=True, bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=True, bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0,
        path_mode="COPY", embed_textures=True, axis_forward="-Z", axis_up="Y",
        mesh_smooth_type="FACE", use_mesh_modifiers=False)
    print(f"[export] FBX -> {path}")
