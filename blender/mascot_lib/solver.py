"""Contact solver for hand poses.

Every phalanx is approximated by a capsule (the same radii used to model the
fingers).  Forward kinematics is evaluated directly from the rest matrices of
the armature, so thousands of candidate poses can be scored per second.  The
solver is used to

* wrap the thumb over the curled fingers in the fist / pointing poses, and
* close every finger and the thumb around the phone so they touch its edges
  without passing through it,

and to report clearance numbers for the quality-control pass.
"""
import math
import itertools
import numpy as np
from mathutils import Euler, Matrix

from . import design as D
from .sdf import sd_round_box

FINGERS = ["Index", "Middle", "Ring", "Pinky"]


def euler_m(deg, order="XYZ"):
    return Euler([math.radians(a) for a in deg], order).to_matrix().to_4x4()


class HandFK:
    def __init__(self, rig, side="L"):
        self.side = side
        self.bones = rig.data.bones
        self.hand = f"DEF_Hand.{side}"
        R = D.RIG
        self.radii = {}
        for f in FINGERS:
            r = R.fingers[f]["radii"]
            for i in range(3):
                self.radii[f"DEF_{f}_{i + 1:02d}.{side}"] = (r[i], r[i + 1])
        r = R.thumb["radii"]
        for i in range(3):
            self.radii[f"DEF_Thumb_{i + 1:02d}.{side}"] = (r[i], r[i + 1])

    def chain(self, base, angles, hand_m=None):
        """angles: list of 3 euler triples for <base>_01..03. Returns posed matrices."""
        hm = hand_m if hand_m is not None else self.bones[self.hand].matrix_local
        parent_rest = self.bones[self.hand].matrix_local
        parent_pose = hm
        out = []
        for i in range(3):
            name = f"DEF_{base}_{i + 1:02d}.{self.side}"
            b = self.bones[name]
            order = "ZYX" if (i == 0 and base != "Thumb") else "XYZ"
            pose = parent_pose @ parent_rest.inverted() @ b.matrix_local @ euler_m(angles[i], order)
            out.append((name, pose, b.length))
            parent_pose, parent_rest = pose, b.matrix_local
        return out

    def capsules(self, base, angles, samples=7):
        pts, rad, seg = [], [], []
        for k, (name, M, L) in enumerate(self.chain(base, angles)):
            h = np.array(M.translation)
            y = np.array(M.col[1].xyz)
            r0, r1 = self.radii[name]
            for s in np.linspace(0, 1, samples):
                pts.append(h + y * L * s)
                rad.append(r0 + (r1 - r0) * s)
                seg.append(k)
        return np.array(pts), np.array(rad), np.array(seg)


def capsule_gap(pa, ra, pb, rb):
    d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=-1) - ra[:, None] - rb[None, :]
    return d.min()


# ---------------------------------------------------------------------------
# Thumb placement over the fingers (fist / point)
# ---------------------------------------------------------------------------

def solve_thumb_over_fingers(fk, finger_angles, target_fingers=("Index", "Middle")):
    """finger_angles: {finger: [(x,y,z)]*3}. Returns best thumb euler triples."""
    others = []
    tgt = []
    for f in FINGERS:
        P, Rr, S = fk.capsules(f, finger_angles[f])
        others.append((P, Rr))
        if f in target_fingers:
            ch = fk.chain(f, finger_angles[f])
            name, M, L = ch[1]
            centre = np.array(M.translation) + np.array(M.col[1].xyz) * L * 0.5
            dorsal = -np.array(M.col[2].xyz)
            tgt.append(centre + dorsal * (fk.radii[name][0] + fk.radii[f"DEF_Thumb_03.{fk.side}"][0]) * 0.92)
    target = np.mean(tgt, 0)
    best = None
    rng = np.random.default_rng(3)

    def score(a1, a2, a3):
        P, Rr, S = fk.capsules("Thumb", [a1, (a2, 0, 0), (a3, 0, 0)])
        pen = 0.0
        for Q, Rq in others:
            g = capsule_gap(P[S > 0], Rr[S > 0], Q, Rq)
            pen += max(0.0, 0.0045 - g)          # keep a small air gap to the fingers
        distal = P[S == 2].mean(0)
        return np.linalg.norm(distal - target) + 25 * pen

    for _ in range(2500):
        a1 = tuple(rng.uniform([-20, -80, -80], [80, 40, 40]))
        a2, a3 = rng.uniform(0, 60), rng.uniform(0, 70)
        s = score(a1, a2, a3)
        if best is None or s < best[0]:
            best = (s, a1, a2, a3)
    s, a1, a2, a3 = best
    step = 6.0
    for _ in range(140):
        cand = []
        for d in itertools.product((-1, 0, 1), repeat=5):
            if not any(d):
                continue
            if rng.random() > 0.25:
                continue
            c1 = (a1[0] + d[0] * step, a1[1] + d[1] * step, a1[2] + d[2] * step)
            c2, c3 = a2 + d[3] * step, a3 + d[4] * step
            if not (0 <= c2 <= 70 and 0 <= c3 <= 80):
                continue
            cand.append((score(c1, c2, c3), c1, c2, c3))
        if cand:
            c = min(cand, key=lambda x: x[0])
            if c[0] < s:
                s, a1, a2, a3 = c
                continue
        step *= 0.7
        if step < 0.3:
            break
    return [tuple(round(x, 1) for x in a1), (round(a2, 1), 0, 0), (round(a3, 1), 0, 0)], s


# ---------------------------------------------------------------------------
# Phone grip
# ---------------------------------------------------------------------------

class PhoneBox:
    def __init__(self, centre, axes, half, radius=0.02):
        self.c, self.axes, self.half, self.r = np.asarray(centre), np.asarray(axes), half, radius

    def sdf(self, p):
        return sd_round_box(p, self.c, self.half, self.r, axes=self.axes)


def solve_finger_grip(fk, finger, box, spread=0.0, coarse=False):
    """Curl one finger until it wraps around the phone edge."""
    best = None
    st = (8, 10, 12) if coarse else (3, 4, 5)
    for c1 in np.arange(0, 75, st[0]):
        for c2 in np.arange(0, 115, st[1]):
            for c3 in np.arange(0, 85, st[2]):
                P, Rr, S = fk.capsules(finger, [(c1, 0, spread), (c2, 0, 0), (c3, 0, 0)])
                gap = box.sdf(P) - Rr
                pen = np.maximum(0, -gap - 0.0008).sum()
                g1 = gap[S == 0].min()
                g2 = gap[S == 1].min()
                g3 = gap[S == 2].min()
                # the fingertip has to come round the far edge onto the screen side
                tip = (P[-1] - box.c) @ box.axes.T
                wrap = max(0.0, (box.half[0] - 0.006) - tip[0]) + max(0.0, tip[1] + 0.002)
                s = 30 * pen + abs(g3) + 0.6 * abs(g2) + 0.3 * abs(g1) + 1.5 * wrap \
                    + 0.0002 * (c1 + c2 + c3) / 10
                if best is None or s < best[0]:
                    best = (s, (c1, c2, c3), (g1, g2, g3))
    s, c, g = best
    if coarse:
        return s
    return [(float(c[0]), 0.0, spread), (float(c[1]), 0, 0), (float(c[2]), 0, 0)], g


def solve_thumb_grip(fk, box, others):
    rng = np.random.default_rng(5)

    def score(a1, a2, a3):
        P, Rr, S = fk.capsules("Thumb", [a1, (a2, 0, 0), (a3, 0, 0)])
        gap = box.sdf(P) - Rr
        pen = np.maximum(0, -gap - 0.0008).sum()
        for Q, Rq in others:
            pen += max(0.0, 0.002 - capsule_gap(P, Rr, Q, Rq))
        g3 = gap[S == 2].min()
        g2 = gap[S == 1].min()
        # keep the thumb pad on the near edge of the phone, not over the screen icons
        local = (P[S == 2].mean(0) - box.c) @ box.axes.T
        edge = max(0.0, local[0] - (-box.half[0] + 0.03))
        return 30 * pen + abs(g3) + 0.5 * abs(g2) + 0.6 * edge
    best = None
    for _ in range(3000):
        a1 = tuple(rng.uniform([-30, -80, -80], [80, 60, 60]))
        a2, a3 = rng.uniform(-10, 60), rng.uniform(-10, 70)
        s = score(a1, a2, a3)
        if best is None or s < best[0]:
            best = (s, a1, a2, a3)
    s, a1, a2, a3 = best
    step = 5.0
    lo = [-30, -80, -80, -10, -10]
    hi = [80, 60, 60, 60, 70]
    while step > 0.3:
        improved = False
        for i in range(5):
            for sgn in (-1, 1):
                v = list(a1) + [a2, a3]
                v[i] = min(hi[i], max(lo[i], v[i] + sgn * step))
                c = score(tuple(v[:3]), v[3], v[4])
                if c < s:
                    s, a1, a2, a3 = c, tuple(v[:3]), v[3], v[4]
                    improved = True
        if not improved:
            step *= 0.6
    P, Rr, S = fk.capsules("Thumb", [a1, (a2, 0, 0), (a3, 0, 0)])
    gap = box.sdf(P) - Rr
    return [tuple(round(x, 1) for x in a1), (round(a2, 1), 0, 0), (round(a3, 1), 0, 0)], \
        (gap[S == 1].min(), gap[S == 2].min()), s


def finger_clearances(fk, angles):
    """Minimum gap between neighbouring fingers (negative = intersection)."""
    caps = {f: fk.capsules(f, angles[f]) for f in angles}
    out = {}
    names = list(angles)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = caps[names[i]], caps[names[j]]
            # ignore the segments that are buried in the palm (first third of the proximal phalanx)
            ma = ~((a[2] == 0) & (np.arange(len(a[2])) % 7 < 3))
            mb = ~((b[2] == 0) & (np.arange(len(b[2])) % 7 < 3))
            out[f"{names[i]}-{names[j]}"] = capsule_gap(a[0][ma], a[1][ma], b[0][mb], b[1][mb])
    return out


def solve_spreads(fk, curls, rng_deg=18, step=3):
    """Pick per-finger spread angles that keep curled neighbours from touching."""
    best = None
    vals = np.arange(-rng_deg, rng_deg + 0.1, step)
    for s0 in vals:
        for s1 in vals[np.abs(vals) <= 4]:
            for s2 in vals:
                for s3 in vals:
                    sp = (s0, s1, s2, s3)
                    ang = {f: [(c[0], 0, sp[i]), (c[1], 0, 0), (c[2], 0, 0)]
                           for i, (f, c) in enumerate(zip(FINGERS, curls))}
                    cl = finger_clearances(fk, {f: ang[f] for f in FINGERS})
                    adj = min(cl["Index-Middle"], cl["Middle-Ring"], cl["Ring-Pinky"])
                    score = -min(adj, 0.0015) + 0.00002 * sum(abs(x) for x in sp)
                    if best is None or score < best[0]:
                        best = (score, sp, adj)
    return best[1], best[2]


def phone_surface_samples(box, n=14):
    hx, hy, hz = box.half
    pts = []
    for u in np.linspace(-1, 1, n):
        for v in np.linspace(-1, 1, 2 * n):
            for y in (-hy, hy):
                pts.append((u * hx, y, v * hz))
            pts.append((hx * np.sign(u + 1e-9), 0, v * hz))
    loc = np.array(pts)
    return box.c + loc @ box.axes


def solve_phone_placement(fk, rig_design, spreads, log=print):
    """Search tilt / position of the phone in the hand: no penetration with palm
    and wrist, back resting on the palm, and the best finger wrap."""
    from . import design as Dm
    parts = rig_design.arm_parts()
    hand = lambda p: np.minimum(parts["arm"](p), parts["palm"](p))   # thumb/fingers get solved afterwards
    best = None
    t_off = Dm.Phone.GRIP[1]
    for tilt in (0.0, 6.0, 12.0, 18.0, 24.0):
        for ca in (0.070, 0.080, 0.090, 0.100):
            Dm.Phone.TILT = tilt
            # lowest offset along the palm normal that keeps the phone outside the hand
            lo, hi = 0.0, 0.12
            for _ in range(22):
                cn = (lo + hi) / 2
                Dm.Phone.GRIP = (ca, t_off, cn)
                c, axes = rig_design.phone_frame(1)
                box = PhoneBox(c, axes, (Dm.Phone.W / 2, Dm.Phone.T / 2, Dm.Phone.H / 2), 0.006)
                if hand(phone_surface_samples(box)).min() < 0.0008:
                    lo = cn
                else:
                    hi = cn
            Dm.Phone.GRIP = (ca, t_off, hi)
            c, axes = rig_design.phone_frame(1)
            box = PhoneBox(c, axes, (Dm.Phone.W / 2, Dm.Phone.T / 2, Dm.Phone.H / 2), 0.006)
            score = sum(solve_finger_grip(fk, f, box, spreads[f], coarse=True) for f in FINGERS[:3])
            if best is None or score < best[0]:
                best = (score, tilt, (ca, t_off, hi))
    Dm.Phone.TILT, Dm.Phone.GRIP = best[1], best[2]
    log(f"[poses] phone placement: tilt {best[1]} deg, grip offset {tuple(round(x, 4) for x in best[2])}, "
        f"score {best[0]:.4f}")
    return best
