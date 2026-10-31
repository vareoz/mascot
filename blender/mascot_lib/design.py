"""Single source of truth for the mascot's design.

Every measurement of the character lives here: body silhouette, face layout,
limb joints, hand anatomy and the signed distance functions built from them.
The same joint positions are used to model the geometry, to build the
skeleton and to compute skin weights, so mesh and rig always line up.

Conventions (Blender): metres, Z up, the character faces -Y, its left side is
+X (``.L`` suffix).  The body is 1.0 unit tall and sits 0.38 above the ground.
"""
import math
import numpy as np

from .sdf import (length, normalize, smin, smax, ssub, round_intersect, sd_round_cone,
                  sd_ellipsoid, sd_round_box, sd_capsule, smoothstep, segment_distance)


def rot(axis, ang_deg, v):
    """Rotate vector v around unit axis (Rodrigues)."""
    axis = normalize(axis)
    a = math.radians(ang_deg)
    v = np.asarray(v, dtype=np.float64)
    return (v * math.cos(a) + np.cross(axis, v) * math.sin(a)
            + axis * (axis @ v) * (1 - math.cos(a)))


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def mirror(v):
    v = np.array(v, dtype=np.float64)
    v[..., 0] *= -1
    return v


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------
ZB = 0.50                 # body bottom (centre of the base edge)
BODY_H = 1.0              # nominal body height


class Body:
    # Sharp construction triangle (before corner fillets)
    W0 = 1.12
    H0 = 1.27
    BASE_BULGE = 0.018
    SIDE_BULGE = 0.055
    R_TOP = 0.33           # fillet radius of the top corner (soft, rounded tip as in the reference)
    R_BASE = 0.19           # fillet radius of the two bottom corners
    EDGE_ROLL = 0.105       # radius of the soft edge between front/back faces and the sides
    PILLOW = 0.028          # extra inflation of the front and back faces (puffy vinyl)

    def __init__(self):
        W0, H0 = self.W0, self.H0
        # big circles approximating slightly convex sides
        self.circles = []
        for (p, q) in [((-W0 / 2, 0.0), (W0 / 2, 0.0)),      # base (outward normal -z)
                       ((W0 / 2, 0.0), (0.0, H0)),           # right side
                       ((0.0, H0), (-W0 / 2, 0.0))]:         # left side
            p = np.array(p)
            q = np.array(q)
            m = (p + q) / 2
            d = q - p
            L = np.linalg.norm(d)
            n = np.array([d[1], -d[0]]) / L                  # outward normal (clockwise order)
            bulge = self.BASE_BULGE if p[1] == q[1] else self.SIDE_BULGE
            c = ((L / 2) ** 2 - bulge ** 2) / (2 * bulge)
            centre = m - n * c
            self.circles.append((centre, c + bulge))

    def sd2(self, x, z):
        zr = z - ZB
        d = []
        for centre, R in self.circles:
            d.append(np.sqrt((x - centre[0]) ** 2 + (zr - centre[1]) ** 2) - R)
        d_base, d_right, d_left = d
        top = round_intersect(d_left, d_right, self.R_TOP)
        return round_intersect(top, d_base, self.R_BASE)

    @staticmethod
    def y_extent(z):
        t = np.clip((z - ZB) / BODY_H, 0.0, 1.0)
        yf = -0.315 + 0.090 * t       # front face leans back slightly
        yb = 0.315 - 0.165 * t        # back face leans forward: thinner towards the top
        return (yf + yb) / 2, (yb - yf) / 2

    def __call__(self, p):
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        d2 = self.sd2(x, z)
        c, h = self.y_extent(z)
        re = self.EDGE_ROLL
        pillow = self.PILLOW * smoothstep(0.0, 0.32, -d2)
        wx = d2 + re
        wy = np.abs(y - c) - (h - re) - pillow
        return (np.minimum(np.maximum(wx, wy), 0.0)
                + np.sqrt(np.maximum(wx, 0) ** 2 + np.maximum(wy, 0) ** 2) - re)

    bounds = ((-0.66, -0.42, ZB - 0.08), (0.66, 0.42, ZB + 1.16))


BODY = Body()


def body_front_point(x, z, offset=0.0):
    """Point on the front surface of the body at (x, z) plus the outward normal."""
    lo, hi = -0.6, 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if BODY(np.array([[x, mid, z]]))[0] > 0:
            lo = mid
        else:
            hi = mid
    p = np.array([x, (lo + hi) / 2, z])
    e = 1e-4
    g = np.array([(BODY(np.array([p + d]))[0] - BODY(np.array([p - d]))[0]) / (2 * e)
                  for d in np.eye(3) * e])
    n = normalize(g)
    return p + n * offset, n


def body_front_points(xs, zs, offset=0.0):
    """Vectorised version of body_front_point."""
    xs = np.asarray(xs, dtype=np.float64)
    zs = np.asarray(zs, dtype=np.float64)
    lo = np.full(xs.shape, -0.6)
    hi = np.zeros(xs.shape)
    for _ in range(50):
        mid = (lo + hi) / 2
        out = BODY(np.stack([xs, mid, zs], 1)) > 0
        lo = np.where(out, mid, lo)
        hi = np.where(out, hi, mid)
    p = np.stack([xs, (lo + hi) / 2, zs], 1)
    e = 1e-4
    g = np.stack([(BODY(p + d) - BODY(p - d)) / (2 * e) for d in np.eye(3) * e], 1)
    n = g / np.linalg.norm(g, axis=1, keepdims=True)
    return p + n * np.asarray(offset)[..., None] if np.ndim(offset) else p + n * offset, n


def rounded_triangle_outline(verts, r, count=150):
    """Closed outline (count points, counter-clockwise) of a triangle whose
    corners are rounded with radius r while keeping the original size."""
    v = shrink_tri(verts, r)
    if cross2(v[1] - v[0], v[2] - v[0]) < 0:
        v = v[::-1]
    pts = []
    for i in range(3):
        p_prev, p, p_next = v[i - 1], v[i], v[(i + 1) % 3]
        e_in = (p - p_prev) / np.linalg.norm(p - p_prev)
        e_out = (p_next - p) / np.linalg.norm(p_next - p)
        n_in = np.array([e_in[1], -e_in[0]])
        n_out = np.array([e_out[1], -e_out[0]])
        a0 = np.arctan2(n_in[1], n_in[0])
        a1 = np.arctan2(n_out[1], n_out[0])
        while a1 < a0:
            a1 += 2 * np.pi
        for t in np.linspace(a0, a1, 24):
            pts.append(p + r * np.array([np.cos(t), np.sin(t)]))
    pts = np.array(pts)
    # resample uniformly by arc length
    closed = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    ts = np.linspace(0, cum[-1], count, endpoint=False)
    out = np.stack([np.interp(ts, cum, closed[:, k]) for k in range(2)], 1)
    return out


# ---------------------------------------------------------------------------
# Face
# ---------------------------------------------------------------------------
class Face:
    EYE_X = 0.124
    EYE_Z = ZB + 0.658
    EYE_R = (0.046, 0.076, 0.029)        # half width, half height, half depth
    EYE_SINK = 0.009                     # how far the eye's centre sits under the surface
    SMILE_Z = ZB + 0.586
    SMILE_W = 0.053                      # half width
    SMILE_SAG = 0.021
    SMILE_R = 0.0092
    HAPPY_W = 0.040
    HAPPY_H = 0.025
    HAPPY_R = 0.0105
    HAPPY_HIDE = 0.03                    # rest-pose depth of the closed "happy" eye arcs
    # triangular mouth / emblem, in (x, height above body bottom)
    MOUTH_TRI = [(0.0604, 0.5258), (-0.1446, 0.1394), (0.2106, 0.2760)]   # reference x1.12
    MOUTH_ROUND = 0.024
    MOUTH_RAISE = 0.0025                 # relief above the body surface
    MOUTH_DEPTH = 0.006


def tri_sd2(px, pz, verts, r):
    """2-D signed distance to a triangle (rounded by r)."""
    v = [np.array(a, dtype=np.float64) for a in verts]
    p = np.stack([px, pz], -1)
    e = [v[1] - v[0], v[2] - v[1], v[0] - v[2]]
    w = [p - v[0], p - v[1], p - v[2]]
    q = []
    for ei, wi in zip(e, w):
        t = np.clip((wi @ ei) / (ei @ ei), 0, 1)
        q.append(wi - t[:, None] * ei)
    s = np.sign(e[0][0] * e[2][1] - e[0][1] * e[2][0])
    dmin = np.minimum(np.minimum(np.einsum("ij,ij->i", q[0], q[0]), np.einsum("ij,ij->i", q[1], q[1])),
                      np.einsum("ij,ij->i", q[2], q[2]))
    c0 = s * (w[0][:, 0] * e[0][1] - w[0][:, 1] * e[0][0])
    c1 = s * (w[1][:, 0] * e[1][1] - w[1][:, 1] * e[1][0])
    c2 = s * (w[2][:, 0] * e[2][1] - w[2][:, 1] * e[2][0])
    sgn = -np.sign(np.minimum(np.minimum(c0, c1), c2))
    return np.sqrt(dmin) * sgn - r


def shrink_tri(verts, r):
    """Move triangle vertices towards the incentre so that rounding by r keeps the size."""
    v = np.array(verts, dtype=np.float64)
    a = np.linalg.norm(v[1] - v[2])
    b = np.linalg.norm(v[2] - v[0])
    c = np.linalg.norm(v[0] - v[1])
    inc = (a * v[0] + b * v[1] + c * v[2]) / (a + b + c)
    area = abs(cross2(v[1] - v[0], v[2] - v[0])) / 2
    inr = 2 * area / (a + b + c)
    k = (inr - r) / inr
    return inc + (v - inc) * k


def mouth_sdf(p):
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    tri = shrink_tri(Face.MOUTH_TRI, Face.MOUTH_ROUND)
    d2 = tri_sd2(x, z - ZB, tri, Face.MOUTH_ROUND)
    db = BODY(p)
    # thin shell hugging the body surface, raised by MOUTH_RAISE
    mid = (Face.MOUTH_RAISE - Face.MOUTH_DEPTH) / 2
    half = (Face.MOUTH_RAISE + Face.MOUTH_DEPTH) / 2
    shell = np.abs(db - mid) - half
    return round_intersect(d2, shell, 0.0022)


def _surface_polyline(points2d, offset):
    return [body_front_point(x, z, offset)[0] for x, z in points2d]


def smile_points():
    pts = []
    for i in range(13):
        s = -1 + 2 * i / 12
        x = s * Face.SMILE_W
        z = Face.SMILE_Z - Face.SMILE_SAG * (1 - s * s) + 0.004 * s * s
        pts.append((x, z))
    return _surface_polyline(pts, 0.0005)


def happy_points(side):
    cx = side * Face.EYE_X
    pts = []
    for i in range(13):
        s = -1 + 2 * i / 12
        x = cx + s * Face.HAPPY_W
        z = Face.EYE_Z - 0.006 + Face.HAPPY_H * (1 - s * s)
        pts.append((x, z))
    return _surface_polyline(pts, 0.0005)


def tube_sdf(points, r):
    def f(p):
        d = None
        for a, b in zip(points[:-1], points[1:]):
            di = sd_capsule(p, a, b, r)
            d = di if d is None else np.minimum(d, di)
        return d
    return f


def eye_frame(side):
    c, n = body_front_point(side * Face.EYE_X, Face.EYE_Z)
    up = normalize(np.array([0, 0, 1.0]) - n * n[2])
    right = normalize(np.cross(up, n))
    centre = c - n * Face.EYE_SINK
    return centre, np.array([right, up, -n]), n


# ---------------------------------------------------------------------------
# Limbs
# ---------------------------------------------------------------------------
class Arm:
    # the shoulder ball sits just under the side surface of the body; the arm
    # hangs alongside the sloped side, slightly more open than the side itself
    SHOULDER = np.array([0.385, -0.030, ZB + 0.425])
    UPPER_LEN = 0.165
    FORE_LEN = 0.160
    ABDUCT = 45.0            # degrees away from the body (from vertical)
    FORWARD = 4.0            # degrees forward swing of the upper arm
    ELBOW_BEND = 10.0        # rest-pose elbow flexion (forward)
    R_SHOULDER = 0.100                   # chunky sausage arms (~18% of the body width)
    R_ELBOW = 0.097
    R_WRIST = 0.088


class Hand:
    SCALE = 1.20                         # overall hand size (all hand numbers below are pre-scale)
    PALM_LEN = 0.098                     # wrist -> knuckle line
    PALM_HALF = (0.050, 0.098, 0.032)    # along a, t, n
    # classic cartoon hand: thumb + three chunky fingers
    # (name, t offset at knuckle, radius, length, fan angle deg)
    # very thick fingers kept close together (a narrow crease between them, never fused)
    FINGERS = [("Index", 0.0665, 0.0310, 0.070, 1.0),
               ("Middle", 0.0000, 0.0318, 0.076, 0.0),
               ("Ring", -0.0665, 0.0306, 0.068, -1.2)]
    SEG = (0.48, 0.29, 0.23)              # long proximal phalanx: room to curl round the thick palm
    REST_CURL = (5.0, 8.0, 6.0)
    THUMB_SEG = (0.044, 0.032, 0.029)
    THUMB_R = (0.0340, 0.0315, 0.0298)
    THUMB_REST_CURL = (0.0, 8.0, 10.0)


class Phone:
    W, H, T = 0.200, 0.400, 0.030          # width, height, thickness
    # centre of the phone in the left-hand frame (along fingers a, towards thumb t,
    # out of the palm n).  The phone's back rests on the palm, its width runs along
    # the fingers and its long axis along the knuckle line (thumb side up).
    GRIP = (0.080, 0.070, 0.0505)
    TILT = 0.0      # degrees around the knuckle line (raises the edge near the wrist)
    # GRIP / TILT are refined at build time by solver.solve_phone_placement


class Leg:
    HIP = np.array([0.180, 0.0, ZB + 0.12])
    KNEE = np.array([0.183, -0.055, 0.335])      # slight rest bend gives the IK some slack
    ANKLE = np.array([0.186, 0.0, 0.150])
    R = (0.115, 0.110, 0.104)                    # thick tubes (~20% of the body width)
    TOE_OUT = 14.0                        # degrees, toes pointing slightly outwards


class Rig:
    """Joint positions for the left side (+X). Right side is mirrored."""

    def __init__(self):
        A = Arm
        S = A.SHOULDER.copy()
        down = np.array([0, 0, -1.0])
        u = rot([0, 1, 0], -A.ABDUCT, down)             # swing outwards (+X)
        u = rot([1, 0, 0], -A.FORWARD, u)               # slight forward swing (-Y)
        u = normalize(u)
        E = S + u * A.UPPER_LEN
        side_axis = normalize(np.cross(u, [0, -1.0, 0]))
        f = normalize(rot(side_axis, A.ELBOW_BEND, u))   # +angle bends the forearm forward
        W = E + f * A.FORE_LEN
        self.S, self.E, self.W = S, E, W
        self.upper_dir, self.fore_dir = u, f

        # hand frame: a = along the fingers, t = towards the thumb, n = palm normal
        a = f.copy()
        t = np.array([0, -1.0, 0])
        t = normalize(t - a * (a @ t))
        n = normalize(np.cross(a, t))
        self.a, self.t, self.n = a, t, n
        H = Hand
        hs = H.SCALE
        self.hs = hs

        def hp(oa, ot, on):
            return W + (a * oa + t * ot + n * on) * hs
        self.hp = hp
        self.palm_c = hp(0.052, 0.003, 0.002)
        self.knuckle_line = hp(H.PALM_LEN, 0, 0)

        self.fingers = {}
        for name, toff, r, L, fan in H.FINGERS:
            K = hp(H.PALM_LEN, toff, 0.006)        # knuckles sit slightly towards the palm side
            r, L = r * hs, L * hs
            d = normalize(rot(n, fan, a))
            # rotation axis for flexion: perpendicular to finger dir, in palm plane
            hinge = normalize(np.cross(d, n))
            pts = [K]
            dirs = []
            cur = d
            for seg, curl in zip(H.SEG, H.REST_CURL):
                cur = normalize(rot(hinge, curl, cur))      # +angle flexes towards the palm (n)
                pts.append(pts[-1] + cur * L * seg)
                dirs.append(cur)
            radii = [r, r * 0.985, r * 0.97, r * 0.955]     # chunky, barely tapering
            self.fingers[name] = dict(pts=pts, radii=radii, n=n, dir=d)

        # thumb
        cmc = hp(0.030, 0.060, 0.016)
        td = normalize(a * 0.66 + t * 0.70 + n * 0.22)
        tz = normalize(n - t * 0.35)
        tz = normalize(tz - td * (td @ tz))
        hinge = normalize(np.cross(td, tz))
        pts = [cmc]
        cur = td
        for L, curl in zip(H.THUMB_SEG, H.THUMB_REST_CURL):
            cur = normalize(rot(hinge, curl, cur))
            pts.append(pts[-1] + cur * L * hs)
        self.thumb = dict(pts=pts, radii=[r * hs for r in H.THUMB_R] + [H.THUMB_R[-1] * 0.97 * hs], n=tz)

        # legs
        Lg = Leg
        self.hip, self.knee, self.ankle = Lg.HIP.copy(), Lg.KNEE.copy(), Lg.ANKLE.copy()
        fwd = normalize(rot([0, 0, 1], Lg.TOE_OUT, [0, -1.0, 0]))
        self.foot_fwd = fwd
        ax, ay = self.ankle[0], self.ankle[1]
        base = np.array([ax, ay, 0.0])
        self.heel_c = base + fwd * -0.040 + np.array([0, 0, 0.072])
        self.toe_c = base + fwd * 0.165 + np.array([0, 0, 0.070])
        self.ball = base + fwd * 0.130 + np.array([0, 0, 0.055])
        self.toe_tip = base + fwd * 0.360 + np.array([0, 0, 0.055])
        self.heel_pt = base + fwd * -0.095 + np.array([0, 0, 0.052])

    # --- signed distance functions -------------------------------------------------
    def phone_frame(self, side=1):
        """Centre and axis rows (width, thickness, height) of the held phone."""
        a, t, n = self.a, self.t, self.n
        g = Phone.GRIP
        c = self.W + a * g[0] + t * g[1] + n * g[2]
        a2 = rot(t, Phone.TILT, a)
        n2 = rot(t, Phone.TILT, n)
        axes = np.array([a2, -n2, t])   # phone local X, Y (screen = -Y), Z
        if side == -1:
            c = mirror(c)
            axes = np.array([mirror(x) for x in axes])
        return c, axes

    def arm_parts(self):
        A = Arm
        S, E, W, a, t, n = self.S, self.E, self.W, self.a, self.t, self.n
        frame = np.array([a, t, n])
        parts = {}
        root = S - self.upper_dir * 0.035
        parts["arm"] = lambda p: smin(sd_round_cone(p, root, E, A.R_SHOULDER, A.R_ELBOW),
                                      sd_round_cone(p, E, W, A.R_ELBOW, A.R_WRIST), 0.02)

        palm_c = self.palm_c
        hs, hp = self.hs, self.hp
        PH = tuple(x * hs for x in Hand.PALM_HALF)

        def palm(p):
            d = sd_round_box(p, palm_c, PH, 0.024 * hs, axes=frame)
            # soft dorsal dome
            d = smin(d, sd_ellipsoid(p, palm_c - n * 0.004 * hs, tuple(x * hs for x in (0.050, 0.090, 0.032)),
                                     axes=frame), 0.01 * hs)
            # hypothenar pad (pinky side of the palm)
            d = smin(d, sd_ellipsoid(p, hp(0.050, -0.066, 0.015),
                                     tuple(x * hs for x in (0.042, 0.026, 0.020)), axes=frame), 0.012 * hs)
            # palm hollow (shallow cup in the centre of the palm)
            d = ssub(d, sd_ellipsoid(p, hp(0.060, 0.002, 0.044),
                                     tuple(x * hs for x in (0.030, 0.030, 0.019)), axes=frame), 0.012 * hs)
            # wrist to palm transition
            d = smin(d, sd_round_cone(p, W - a * 0.01, palm_c - a * 0.01 * hs, A.R_WRIST, 0.062 * hs), 0.03)
            return d
        parts["palm"] = palm

        for name, fd in self.fingers.items():
            pts, radii = fd["pts"], fd["radii"]

            def finger(p, pts=pts, radii=radii):
                d = None
                for i in range(3):
                    di = sd_round_cone(p, pts[i], pts[i + 1], radii[i], radii[i + 1])
                    d = di if d is None else np.minimum(d, di)
                return d
            parts[name] = finger

        tp, tr = self.thumb["pts"], self.thumb["radii"]

        def thumb(p):
            d = None
            for i in range(3):
                di = sd_round_cone(p, tp[i], tp[i + 1], tr[i], tr[i + 1])
                d = di if d is None else np.minimum(d, di)
            # thenar eminence (muscle pad at the base of the thumb)
            d = smin(d, sd_ellipsoid(p, hp(0.034, 0.042, 0.017),
                                     tuple(x * hs for x in (0.038, 0.032, 0.026)), axes=frame), 0.016 * hs)
            return d
        parts["thumb"] = thumb
        return parts

    def arm_sdf(self):
        parts = self.arm_parts()
        fingers = [parts[n] for n in self.fingers] + [parts["thumb"]]

        def f(p):
            hand = parts["palm"](p)
            arm = parts["arm"](p)
            base = smin(arm, hand, 0.03)
            digits = [smin(base, g(p), 0.015) for g in fingers]
            d = digits[0]
            for di in digits[1:]:
                d = smin(d, di, 0.007)     # tiny web fillet: fingers stay separate
            return d
        return f

    def leg_sdf(self):
        R = Leg.R
        hip_top = self.hip + np.array([0, 0, 0.04])
        fwd = self.foot_fwd
        side = normalize(np.cross(fwd, [0, 0, 1.0]))
        frame = np.array([side, fwd, [0, 0, 1.0]])

        def f(p):
            leg = smin(sd_round_cone(p, hip_top, self.knee, R[0], R[1]),
                       sd_round_cone(p, self.knee, self.ankle, R[1], R[2]), 0.02)
            heel = sd_ellipsoid(p, self.heel_c, (0.125, 0.130, 0.110), axes=frame)
            toe = sd_ellipsoid(p, self.toe_c, (0.150, 0.235, 0.112), axes=frame)
            foot = smin(heel, toe, 0.06)
            d = smin(leg, foot, 0.045)
            # flat sole with a rounded rim
            return round_intersect(d, 0.0008 - p[:, 2], 0.03)   # sole 0.8 mm above the floor
        return f

    def arm_bounds(self):
        pts = [self.S, self.E, self.W] + [q for fd in self.fingers.values() for q in fd["pts"]] \
            + list(self.thumb["pts"])
        pts = np.array(pts)
        return pts.min(0) - 0.16, pts.max(0) + 0.16

    def leg_bounds(self):
        return (np.array([self.hip[0] - 0.20, -0.50, -0.03]),
                np.array([self.hip[0] + 0.21, 0.22, self.hip[2] + 0.17]))

    # --- skin weight groups ---------------------------------------------------------
    def arm_weight_groups(self):
        """List of (group sdf, [(bone, [segments])], chain softness)."""
        parts = self.arm_parts()
        S, E, W = self.S, self.E, self.W
        groups = [
            (parts["arm"], [("UpperArm", [(S - self.upper_dir * 0.05, E)]),
                            ("Forearm", [(E, W)]),
                            ("Hand", [(W, self.palm_c)])], 0.012),
            (parts["palm"], [("Hand", [(W, self.knuckle_line)])], 0.01),
        ]
        for name, fd in self.fingers.items():
            p = fd["pts"]
            groups.append((parts[name], [("Hand", [(W, p[0] - (p[1] - p[0]) * 0.15)]),
                                         (f"{name}_01", [(p[0], p[1])]),
                                         (f"{name}_02", [(p[1], p[2])]),
                                         (f"{name}_03", [(p[2], p[3])])], 0.0032))
        tp = self.thumb["pts"]
        groups.append((parts["thumb"], [("Hand", [(W, self.palm_c - self.t * 0.02)]),
                                        ("Thumb_01", [(tp[0], tp[1])]),
                                        ("Thumb_02", [(tp[1], tp[2])]),
                                        ("Thumb_03", [(tp[2], tp[3])])], 0.0045))
        return groups

    def leg_weight_groups(self):
        hip_top = self.hip + np.array([0, 0, 0.06])
        return [(self.leg_sdf(), [("Thigh", [(hip_top, self.knee)]),
                                  ("Shin", [(self.knee, self.ankle)]),
                                  ("Foot", [(self.ankle, self.ball), (self.ankle, self.heel_pt)]),
                                  ("Toe", [(self.ball, self.toe_tip)])], 0.016)]


def compute_weights(verts, groups, group_tau=0.003):
    """Smooth, joint-aware skin weights.

    Each vertex first gets a soft membership to every anatomical group (arm,
    palm, each finger...) from the group's own distance field, then inside a
    group the weight is shared between the bones of that chain according to
    the distance to each bone segment, with a softness proportional to the
    local limb radius.  Returns {bone_name: weights}.
    """
    gd = np.stack([g[0](verts) for g in groups], 1)
    gd = np.maximum(gd, 0.0)
    gm = np.exp(-(gd - gd.min(1, keepdims=True)) / group_tau)
    gm /= gm.sum(1, keepdims=True)
    out = {}
    for gi, (_, bones, tau) in enumerate(groups):
        dists = []
        for bname, segs in bones:
            d = np.min(np.stack([segment_distance(verts, a, b) for a, b in segs], 1), 1)
            dists.append(d)
        dists = np.stack(dists, 1)
        w = np.exp(-(dists - dists.min(1, keepdims=True)) / tau)
        w /= w.sum(1, keepdims=True)
        for bi, (bname, _) in enumerate(bones):
            out[bname] = out.get(bname, 0) + gm[:, gi] * w[:, bi]
    return out


def smooth_and_limit(weights, edges, iters=2, lam=0.5, max_influences=4, prune=0.01):
    from .meshing import laplacian
    names = list(weights)
    W = np.stack([weights[n] for n in names], 1)
    for _ in range(iters):
        W = W + lam * (laplacian(W, edges, W) - W)
    # keep the strongest influences only
    if W.shape[1] > max_influences:
        idx = np.argsort(-W, axis=1)[:, max_influences:]
        np.put_along_axis(W, idx, 0.0, axis=1)
    W[W < prune] = 0.0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    return {n: W[:, i] for i, n in enumerate(names)}


RIG = Rig()
