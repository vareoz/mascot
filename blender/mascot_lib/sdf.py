"""Signed distance field primitives and operators (vectorised with numpy).

All functions take ``p`` as an (N, 3) float array of points and return an (N,)
array of signed distances (negative inside).  The modelling of the mascot is
done entirely with these analytic shapes, which are then converted to a quad
mesh by :mod:`mascot_lib.meshing`.
"""
import numpy as np


def length(v):
    return np.sqrt(np.einsum("...i,...i->...", v, v))


def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------

def smin(a, b, k):
    """Polynomial smooth union (fillet of size ~k)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    """Polynomial smooth intersection."""
    return -smin(-a, -b, k)


def ssub(a, b, k):
    """Smooth subtraction: a minus b."""
    return smax(a, -b, k)


def round_intersect(a, b, r):
    """Intersection with an exact circular fillet of radius r (hg_sdf)."""
    ux = np.maximum(a + r, 0.0)
    uy = np.maximum(b + r, 0.0)
    return np.minimum(-r, np.maximum(a, b)) + np.sqrt(ux * ux + uy * uy)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def sd_sphere(p, c, r):
    return length(p - np.asarray(c)) - r


def to_local(p, origin, axes):
    """Express points in a local frame. ``axes`` is a 3x3 matrix whose ROWS
    are the local x, y, z axes expressed in world space."""
    return (p - np.asarray(origin)) @ np.asarray(axes).T


def sd_ellipsoid(p, c, radii, axes=None):
    """Approximate (bound-correct) ellipsoid distance (Inigo Quilez)."""
    q = p - np.asarray(c) if axes is None else to_local(p, c, axes)
    r = np.asarray(radii, dtype=np.float64)
    k0 = length(q / r)
    k1 = length(q / (r * r))
    k1 = np.maximum(k1, 1e-9)
    return k0 * (k0 - 1.0) / k1


def sd_round_box(p, c, half, radius, axes=None):
    q = p - np.asarray(c) if axes is None else to_local(p, c, axes)
    q = np.abs(q) - (np.asarray(half) - radius)
    return length(np.maximum(q, 0.0)) + np.minimum(np.max(q, axis=-1), 0.0) - radius


def sd_round_cone(p, a, b, r1, r2):
    """Cone with spherical caps between points a (radius r1) and b (radius r2)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - y[:, None] * ba
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d_b = np.sqrt(x2 + z2) * il2 - r2
    d_a = np.sqrt(x2 + y2) * il2 - r1
    d_m = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - r1
    out = np.where(np.sign(z) * a2 * z2 > k, d_b, np.where(np.sign(y) * a2 * y2 < k, d_a, d_m))
    return out


def sd_capsule(p, a, b, r):
    return sd_round_cone(p, a, b, r, r)


def segment_distance(p, a, b):
    """Unsigned distance from points to segment ab (used for skin weights)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ba = b - a
    t = np.clip(((p - a) @ ba) / max(float(ba @ ba), 1e-12), 0.0, 1.0)
    return length(p - (a + t[:, None] * ba))


def sd_circle2(px, py, cx, cy, r):
    return np.sqrt((px - cx) ** 2 + (py - cy) ** 2) - r


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
