"""Physically based materials (Principled BSDF, glTF-compatible)."""
import bpy


def srgb(r, g, b):
    def c(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (c(r), c(g), c(b), 1.0)


PALETTE = {
    "cream": srgb(238, 222, 197),
    "black": srgb(30, 29, 30),
    "eye": srgb(12, 12, 13),
    "background": srgb(245, 238, 227),
}


def principled(name, color, rough, spec=0.5, coat=0.0, coat_rough=0.1, sss=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (0.02, 0.012, 0.008)
        b.inputs["Subsurface Scale"].default_value = 0.5
    m.diffuse_color = color
    m.roughness = rough
    return m


def build_materials(screen_image=None):
    mats = {
        "body": principled("MAT_Body_CreamVinyl", PALETTE["cream"], 0.50, spec=0.40, sss=0.04),
        "limbs": principled("MAT_Limbs_BlackVinyl", PALETTE["black"], 0.44, spec=0.45, coat=0.12, coat_rough=0.35),
        "eyes": principled("MAT_Eyes_GlossBlack", PALETTE["eye"], 0.16, spec=0.6, coat=1.0, coat_rough=0.04),
        "face": principled("MAT_Face_MatteBlack", PALETTE["black"], 0.52, spec=0.35),
        "phone": principled("MAT_Phone_Frame", srgb(36, 35, 37), 0.30, spec=0.5, coat=0.4, coat_rough=0.12),
    }
    m = bpy.data.materials.get("MAT_Phone_Screen") or bpy.data.materials.new("MAT_Phone_Screen")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.18
    b.inputs["Coat Weight"].default_value = 0.6
    b.inputs["Coat Roughness"].default_value = 0.03
    if screen_image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = screen_image
        tex.location = (-400, 200)
        nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = 0.55
    mats["screen"] = m

    bg = bpy.data.materials.get("MAT_Studio_Backdrop") or bpy.data.materials.new("MAT_Studio_Backdrop")
    bg.use_nodes = True
    bb = bg.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = PALETTE["background"]
    bb.inputs["Roughness"].default_value = 0.9
    bb.inputs["Specular IOR Level"].default_value = 0.1
    mats["backdrop"] = bg
    return mats


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def build_swatches(collection, mats):
    """Small preview spheres (one per material) kept in their own collection."""
    import bmesh
    x = 0.0
    for key, mat in mats.items():
        if key == "backdrop":
            continue
        me = bpy.data.meshes.new(f"SWATCH_{mat.name}")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.05)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        ob = bpy.data.objects.new(f"SWATCH_{mat.name}", me)
        collection.objects.link(ob)
        ob.location = (-1.2 + x, 0.8, 0.05)
        ob.data.materials.append(mat)
        x += 0.13
