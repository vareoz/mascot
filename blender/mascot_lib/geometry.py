"""Builds every mesh of the mascot from the analytic design (runs inside Blender)."""
import time
import numpy as np
import bpy

from . import design as D
from .meshing import mesh_sdf, check_manifold, unique_edges
from .sdf import sd_ellipsoid, sd_round_box, round_intersect, smoothstep


def log(*a):
    print("[geometry]", *a, flush=True)


def make_mesh_object(name, verts, faces, collection, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.validate(clean_customdata=False)
    me.update()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def decimate(ob, ratio):
    """Collapse-decimate small rigid parts (eyes, smile, phone) to keep the GLB light."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    before = len(ob.data.polygons)
    mod = ob.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.data.shade_smooth()
    log(f"decimate {ob.name}: {before} -> {len(ob.data.polygons)} faces")


def mirror_mesh(verts, faces):
    v = verts.copy()
    v[:, 0] *= -1
    return v, faces[:, ::-1].copy()


def sdf_object(name, sdf, bmin, bmax, h, collection, relax=4):
    t0 = time.time()
    v, f = mesh_sdf(sdf, bmin, bmax, h, relax_iters=relax)
    bad = check_manifold(f)
    log(f"{name}: {len(v)} verts, {len(f)} quads, non-manifold edges={bad}, {time.time() - t0:.1f}s")
    return v, f


def mesh_arrays(ob):
    me = ob.data
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", e)
    return v.reshape(-1, 3), e.reshape(-1, 2)


def set_coords(ob, v):
    ob.data.vertices.foreach_set("co", v.ravel())
    ob.data.update()


def retopo(ob, sdf, target_faces, relax=8):
    """Clean quad retopology (QuadriFlow) followed by an exact re-projection of
    every vertex onto the analytic surface."""
    t0 = time.time()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    before = len(ob.data.polygons)
    for seed in (7, 11, 23, 42):
        bpy.ops.object.quadriflow_remesh(target_faces=target_faces, use_mesh_symmetry=False,
                                         use_preserve_sharp=False, use_preserve_boundary=False,
                                         smooth_normals=False, seed=seed)
        after = len(ob.data.polygons)
        if after != before:
            break
        log(f"QuadriFlow retry on {ob.name} (seed {seed} failed)")
    else:
        raise RuntimeError(f"QuadriFlow failed on {ob.name}")
    v, e = mesh_arrays(ob)
    from .meshing import project, laplacian
    v = project(sdf, v)
    for _ in range(relax):
        v = v + 0.4 * (laplacian(v, e) - v)
        v = project(sdf, v)
    set_coords(ob, v)
    ob.data.shade_smooth()
    ntri = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    nq = sum(1 for p in ob.data.polygons if len(p.vertices) == 4)
    log(f"retopo {ob.name}: {before} -> {after} faces ({nq} quads, {ntri} tris eq.), {time.time() - t0:.1f}s")
    return v


def build_mouth(collection):
    """Triangular mouth: a thin, softly bevelled inlay that follows the body surface."""
    F = D.Face
    outline = D.rounded_triangle_outline(F.MOUTH_TRI, F.MOUTH_ROUND, count=168)
    cen = outline.mean(0)
    # (scale towards the centre, offset along the body normal)
    rings = [(1.000, -0.006), (1.000, F.MOUTH_RAISE * 0.25), (0.992, F.MOUTH_RAISE * 0.85),
             (0.980, F.MOUTH_RAISE)]
    rings += [(s, F.MOUTH_RAISE) for s in np.linspace(0.94, 0.06, 12)]
    verts = []
    for s, off in rings:
        q = cen + (outline - cen) * s
        if s == 1.0:
            # widen the side wall a tiny bit so the bevel reads as a soft edge
            d = outline - cen
            q = outline + d / np.linalg.norm(d, axis=1, keepdims=True) * (0.0012 if off > 0 else 0.0)
        p, n = D.body_front_points(q[:, 0], q[:, 1] + D.ZB, off)
        verts.append(p)
    pc, _ = D.body_front_points(np.array([cen[0]]), np.array([cen[1] + D.ZB]), F.MOUTH_RAISE)
    V = np.vstack(verts + [pc])
    N = len(outline)
    faces = []
    for r in range(len(rings) - 1):
        for i in range(N):
            a, b = r * N + i, r * N + (i + 1) % N
            faces.append((a, b, b + N, a + N))
    c = len(V) - 1
    last = (len(rings) - 1) * N
    for i in range(N):
        faces.append((last + i, last + (i + 1) % N, c))
    me = bpy.data.meshes.new("MASCOT_Mouth")
    me.from_pydata(V.tolist(), [], faces)
    me.validate()
    # outline is counter-clockwise in (x, z): make sure normals face the viewer (-Y)
    me.update()
    me.shade_smooth()
    ob = bpy.data.objects.new("MASCOT_Mouth", me)
    collection.objects.link(ob)
    if me.polygons[N * 3].normal.y > 0:
        for p in me.polygons:
            p.flip()
        me.update()
    log(f"Mouth: {len(V)} verts, {len(faces)} faces")
    return ob, V


def build_all(cols):
    """Returns {key: (object, sdf)} for every part of the character."""
    R = D.RIG
    out = {}

    # --- body -------------------------------------------------------------------
    bmin, bmax = D.Body.bounds
    v, f = sdf_object("Body", D.BODY, bmin, bmax, 0.011, cols["body"])
    ob = make_mesh_object("MASCOT_Body", v, f, cols["body"])
    retopo(ob, D.BODY, 9000)
    out["Body"] = (ob, D.BODY)

    # --- face ---------------------------------------------------------------------
    for side, sfx in ((1, "L"), (-1, "R")):
        c, axes, n = D.eye_frame(side)
        rad = D.Face.EYE_R
        sdf = lambda p, c=c, axes=axes: sd_ellipsoid(p, c, rad, axes=axes)
        ext = max(rad) + 0.01
        v, f = sdf_object(f"Eye.{sfx}", sdf, c - ext, c + ext, 0.0026, cols["body"], relax=3)
        out[f"Eye.{sfx}"] = (make_mesh_object(f"MASCOT_Eye.{sfx}", v, f, cols["body"]), sdf)
        decimate(out[f"Eye.{sfx}"][0], 0.3)

        pts = D.happy_points(side)
        sdf = D.tube_sdf(pts, D.Face.HAPPY_R)
        P = np.array(pts)
        v, f = sdf_object(f"EyeHappy.{sfx}", sdf, P.min(0) - 0.012, P.max(0) + 0.012, 0.0015,
                          cols["body"], relax=3)
        # rest pose: hidden under the body surface (the face rig pushes them out)
        v = v - n * D.Face.HAPPY_HIDE
        out[f"EyeHappy.{sfx}"] = (make_mesh_object(f"MASCOT_EyeHappy.{sfx}", v, f, cols["body"]), sdf)
        decimate(out[f"EyeHappy.{sfx}"][0], 0.35)

    pts = D.smile_points()
    P = np.array(pts)
    sdf = D.tube_sdf(pts, D.Face.SMILE_R)
    v, f = sdf_object("Smile", sdf, P.min(0) - 0.012, P.max(0) + 0.012, 0.0016, cols["body"], relax=3)
    out["Smile"] = (make_mesh_object("MASCOT_Smile", v, f, cols["body"]), sdf)
    decimate(out["Smile"][0], 0.35)

    ob, _ = build_mouth(cols["body"])
    out["Mouth"] = (ob, None)

    # --- arms + hands -------------------------------------------------------------
    lo, hi = R.arm_bounds()
    sdf = R.arm_sdf()
    for h in (0.0028, 0.00285, 0.00275, 0.0029):
        v, f = sdf_object("Arm.L", sdf, lo, hi, h, cols["hands"], relax=4)
        if check_manifold(f) == 0:      # QuadriFlow needs a clean manifold input
            break
    ob = make_mesh_object("MASCOT_ArmHand.L", v, f, cols["hands"])
    v = retopo(ob, sdf, 15000)
    out["Arm.L"] = (ob, sdf)
    out["Arm.R"] = (mirrored_copy(ob, "MASCOT_ArmHand.R", cols["hands"]), None)

    # --- legs + feet --------------------------------------------------------------
    lo, hi = R.leg_bounds()
    sdf = R.leg_sdf()
    v, f = sdf_object("Leg.L", sdf, lo, hi, 0.0062, cols["limbs"], relax=4)
    ob = make_mesh_object("MASCOT_LegFoot.L", v, f, cols["limbs"])
    retopo(ob, sdf, 5000)
    out["Leg.L"] = (ob, sdf)
    out["Leg.R"] = (mirrored_copy(ob, "MASCOT_LegFoot.R", cols["limbs"]), None)
    return out


def mirrored_copy(ob, name, collection):
    v, _ = mesh_arrays(ob)
    me = ob.data
    faces = [tuple(p.vertices)[::-1] for p in me.polygons]
    v = v.copy()
    v[:, 0] *= -1
    m2 = bpy.data.meshes.new(name)
    m2.from_pydata(v.tolist(), [], faces)
    m2.validate()
    m2.update()
    m2.shade_smooth()
    o2 = bpy.data.objects.new(name, m2)
    collection.objects.link(o2)
    return o2


# ---------------------------------------------------------------------------
# Phone (independent accessory)
# ---------------------------------------------------------------------------
PHONE_W, PHONE_H, PHONE_T = D.Phone.W, D.Phone.H, D.Phone.T
SCREEN_INSET = 0.0085


def build_phone(collection, screen_image):
    """Phone modelled around its own origin: X = width, Z = height, -Y = screen."""
    hw, hh, ht = PHONE_W / 2, PHONE_H / 2, PHONE_T / 2

    def body(p):
        # rounded rectangle in XZ extruded in Y with soft edges
        from .sdf import length
        q = np.abs(p[:, [0, 2]]) - (np.array([hw, hh]) - 0.022)
        d2 = length(np.maximum(q, 0)) + np.minimum(np.max(q, axis=-1), 0) - 0.022
        wy = np.abs(p[:, 1]) - ht
        r = 0.006
        wx = d2 + r
        wy2 = wy + r
        d = np.minimum(np.maximum(wx, wy2), 0) + np.sqrt(np.maximum(wx, 0) ** 2 + np.maximum(wy2, 0) ** 2) - r
        # shallow screen recess on the front (-Y)
        q2 = np.abs(p[:, [0, 2]]) - (np.array([hw - SCREEN_INSET, hh - SCREEN_INSET]) - 0.015)
        d3 = length(np.maximum(q2, 0)) + np.minimum(np.max(q2, axis=-1), 0) - 0.015
        recess = np.maximum(d3, p[:, 1] + ht - 0.0012)     # only a 1.2 mm deep pocket on the front
        return round_intersect(d, -recess, 0.0008)
    v, f = mesh_sdf(body, (-hw - 0.01, -ht - 0.01, -hh - 0.01), (hw + 0.01, ht + 0.01, hh + 0.01), 0.0016,
                    relax_iters=3)
    log(f"Phone: {len(v)} verts")
    phone = make_mesh_object("PROP_Phone", v, f, collection)
    decimate(phone, 0.1)

    # screen: a real (thin) surface with UVs, slightly in front of the recess floor
    sw, sh = hw - SCREEN_INSET - 0.0005, hh - SCREEN_INSET - 0.0005
    nx, nz = 24, 48
    verts, faces, uvs = [], [], []
    rr = 0.0145
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, w = i / nx, j / nz
            x, z = (u * 2 - 1) * sw, (w * 2 - 1) * sh
            # pull grid into a rounded rectangle
            cx = np.clip(x, -(sw - rr), sw - rr)
            cz = np.clip(z, -(sh - rr), sh - rr)
            dx, dz = x - cx, z - cz
            dl = np.hypot(dx, dz)
            if dl > rr:
                x, z = cx + dx / dl * rr, cz + dz / dl * rr
            verts.append((x, -ht + 0.0004, z))
            uvs.append((u, w))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("PROP_PhoneScreen")
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    me.update()     # quad winding (x then z) already gives a -Y facing normal
    screen = bpy.data.objects.new("PROP_PhoneScreen", me)
    collection.objects.link(screen)
    screen.parent = phone
    return phone, screen


def draw_screen_image(name="PhoneScreen_UI", w=360, h=720):
    """Paints the phone UI (energy tile + bulb/home tiles) into an image."""
    img = np.zeros((h, w, 4), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # numpy row 0 is written as the bottom row of the Blender image, and the
    # screen's v coordinate grows towards the top of the phone: no flip needed

    def rrect(x0, y0, x1, y1, r):
        cx = np.clip(xx, x0 + r, x1 - r)
        cy = np.clip(yy, y0 + r, y1 - r)
        return np.hypot(xx - cx, yy - cy) - r     # <0 inside

    def cover(d):
        return np.clip(0.5 - d, 0, 1)

    def paint(mask, col):
        for c in range(3):
            img[..., c] = img[..., c] * (1 - mask) + col[c] * mask

    def poly_mask(pts):
        pts = np.asarray(pts, dtype=np.float32)
        inside = np.zeros((h, w), bool)
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            cond = ((yi > yy) != (yj > yy)) & (xx < (xj - xi) * (yy - yi) / (yj - yi + 1e-9) + xi)
            inside ^= cond
            j = i
        return inside.astype(np.float32)

    def s2l(c):
        c = np.asarray(c, dtype=np.float32) / 255.0
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    paint(np.ones((h, w), np.float32), s2l((250, 244, 233)))           # warm white screen
    # notch
    paint(cover(rrect(w * 0.36, h * 0.952, w * 0.64, h * 1.02, 14)), s2l((20, 20, 22)))
    # big energy tile with orange->pink gradient
    tile = cover(rrect(w * 0.12, h * 0.50, w * 0.88, h * 0.86, 38))
    g = np.clip((yy - h * 0.50) / (h * 0.36), 0, 1)[..., None]
    col_top, col_bot = s2l((255, 168, 64)), s2l((255, 120, 120))
    grad = col_bot * (1 - g) + col_top * g
    for c in range(3):
        img[..., c] = img[..., c] * (1 - tile) + grad[..., c] * tile
    # lightning bolt
    cx, cy, s = w * 0.5, h * 0.68, w * 0.0042
    bolt = [(10, 52), (-22, -2), (-2, -2), (-12, -52), (22, 6), (2, 6)]
    bolt = [(cx + x * s * 1.25, cy + y * s * 1.25) for x, y in bolt]
    paint(poly_mask(bolt), s2l((255, 250, 240)))
    # two small dark tiles
    for x0 in (0.12, 0.53):
        paint(cover(rrect(w * x0, h * 0.20, w * (x0 + 0.35), h * 0.43, 30)), s2l((32, 30, 30)))
    # bulb icon
    bx, by = w * 0.295, h * 0.33
    paint(cover(np.hypot(xx - bx, yy - by) - w * 0.065), s2l((250, 244, 233)))
    paint(cover(rrect(bx - w * 0.035, by - w * 0.135, bx + w * 0.035, by - w * 0.05, 6)), s2l((250, 244, 233)))
    for k in range(2):   # screw thread of the bulb
        yy0 = by - w * (0.085 + 0.03 * k)
        paint(cover(rrect(bx - w * 0.04, yy0 - 2, bx + w * 0.04, yy0 + 2, 1)), s2l((32, 30, 30)))
    # house icon
    hx, hy, hs = w * 0.705, h * 0.30, w * 0.075
    roof = poly_mask([(hx - hs * 1.25, hy + hs * 0.35), (hx, hy + hs * 1.45), (hx + hs * 1.25, hy + hs * 0.35)])
    paint(roof, s2l((250, 244, 233)))
    paint(cover(rrect(hx - hs * 0.85, hy - hs * 0.9, hx + hs * 0.85, hy + hs * 0.45, 4)), s2l((250, 244, 233)))
    paint(cover(rrect(hx - hs * 0.25, hy - hs * 0.9, hx + hs * 0.25, hy - hs * 0.05, 3)), s2l((32, 30, 30)))
    img[..., 3] = 1.0

    im = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "sRGB"
    # convert linear back to sRGB for an 8-bit sRGB image
    lin = img[..., :3]
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    img[..., :3] = np.clip(srgb, 0, 1)
    im.pixels.foreach_set(img.ravel())
    im.update()
    im.pack()
    return im
