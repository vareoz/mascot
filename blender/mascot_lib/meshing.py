"""Quad-dominant meshing of signed distance fields.

``surface_nets`` extracts an all-quad watertight surface from a sampled SDF
(Naive Surface Nets).  ``relax_and_project`` then evens out the vertex
distribution with Laplacian relaxation and snaps every vertex back onto the
exact zero level set of the analytic SDF (Newton steps along the gradient), so
the final surface is smooth, accurate and free of voxel stair-stepping.
"""
import numpy as np

_CORNERS = np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
_EDGES = []
for _a in range(8):
    for _b in range(_a + 1, 8):
        if np.abs(_CORNERS[_a] - _CORNERS[_b]).sum() == 1:
            _EDGES.append((_a, _b))


def sample_grid(sdf_func, bmin, bmax, h, chunk=400_000):
    bmin = np.asarray(bmin, dtype=np.float64)
    bmax = np.asarray(bmax, dtype=np.float64)
    n = np.ceil((bmax - bmin) / h).astype(int) + 1
    xs = [bmin[i] + h * np.arange(n[i]) for i in range(3)]
    gx, gy, gz = np.meshgrid(*xs, indexing="ij")
    pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    out = np.empty(len(pts))
    for s in range(0, len(pts), chunk):
        out[s:s + chunk] = sdf_func(pts[s:s + chunk])
    return out.reshape(n), bmin


def surface_nets(f, origin, h):
    inside = f < 0.0
    nx, ny, nz = f.shape
    cnt = np.zeros((nx - 1, ny - 1, nz - 1), dtype=np.int8)
    for c in _CORNERS:
        cnt += inside[c[0]:nx - 1 + c[0], c[1]:ny - 1 + c[1], c[2]:nz - 1 + c[2]]
    active = (cnt > 0) & (cnt < 8)
    cells = np.argwhere(active)
    vid = -np.ones(active.shape, dtype=np.int64)
    vid[active] = np.arange(len(cells))

    acc = np.zeros((len(cells), 3))
    num = np.zeros(len(cells))
    for a, b in _EDGES:
        ca, cb = _CORNERS[a], _CORNERS[b]
        ia = cells + ca
        ib = cells + cb
        fa = f[ia[:, 0], ia[:, 1], ia[:, 2]]
        fb = f[ib[:, 0], ib[:, 1], ib[:, 2]]
        cross = (fa < 0) != (fb < 0)
        t = fa[cross] / (fa[cross] - fb[cross])
        acc[cross] += ia[cross] + t[:, None] * (cb - ca)
        num[cross] += 1
    verts = origin + h * acc / num[:, None]

    faces = []
    # edges along x
    s0 = inside[:-1, 1:-1, 1:-1]
    s1 = inside[1:, 1:-1, 1:-1]
    e = np.argwhere(s0 != s1)
    if len(e):
        i, j, k = e[:, 0], e[:, 1] + 1, e[:, 2] + 1
        q = np.stack([vid[i, j - 1, k - 1], vid[i, j, k - 1], vid[i, j, k], vid[i, j - 1, k]], 1)
        flip = ~s0[e[:, 0], e[:, 1], e[:, 2]]
        q[flip] = q[flip][:, ::-1]
        faces.append(q)
    # edges along y
    s0 = inside[1:-1, :-1, 1:-1]
    s1 = inside[1:-1, 1:, 1:-1]
    e = np.argwhere(s0 != s1)
    if len(e):
        i, j, k = e[:, 0] + 1, e[:, 1], e[:, 2] + 1
        q = np.stack([vid[i - 1, j, k - 1], vid[i - 1, j, k], vid[i, j, k], vid[i, j, k - 1]], 1)
        flip = ~s0[e[:, 0], e[:, 1], e[:, 2]]
        q[flip] = q[flip][:, ::-1]
        faces.append(q)
    # edges along z
    s0 = inside[1:-1, 1:-1, :-1]
    s1 = inside[1:-1, 1:-1, 1:]
    e = np.argwhere(s0 != s1)
    if len(e):
        i, j, k = e[:, 0] + 1, e[:, 1] + 1, e[:, 2]
        q = np.stack([vid[i - 1, j - 1, k], vid[i, j - 1, k], vid[i, j, k], vid[i - 1, j, k]], 1)
        flip = ~s0[e[:, 0], e[:, 1], e[:, 2]]
        q[flip] = q[flip][:, ::-1]
        faces.append(q)
    faces = np.concatenate(faces, 0)
    return verts, faces


def unique_edges(faces):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 3]], faces[:, [3, 0]]], 0)
    e = np.sort(e, axis=1)
    return np.unique(e, axis=0)


def gradient(sdf_func, v, eps=1e-4):
    g = np.zeros_like(v)
    for i in range(3):
        d = np.zeros(3)
        d[i] = eps
        g[:, i] = (sdf_func(v + d) - sdf_func(v - d)) / (2 * eps)
    return g


def project(sdf_func, v, steps=4):
    for _ in range(steps):
        d = sdf_func(v)
        g = gradient(sdf_func, v)
        gg = np.maximum(np.einsum("ij,ij->i", g, g), 1e-12)
        v = v - (d / gg)[:, None] * g
    return v


def laplacian(v, edges, values=None):
    x = v if values is None else values
    acc = np.zeros_like(x)
    cnt = np.zeros(len(x))
    np.add.at(acc, edges[:, 0], x[edges[:, 1]])
    np.add.at(acc, edges[:, 1], x[edges[:, 0]])
    np.add.at(cnt, edges[:, 0], 1)
    np.add.at(cnt, edges[:, 1], 1)
    cnt = np.maximum(cnt, 1)
    return acc / (cnt[:, None] if x.ndim == 2 else cnt)


def relax_and_project(sdf_func, verts, faces, iters=4, lam=0.6):
    edges = unique_edges(faces)
    v = project(sdf_func, verts)
    for _ in range(iters):
        avg = laplacian(v, edges)
        v = v + lam * (avg - v)
        v = project(sdf_func, v)
    return v


def mesh_sdf(sdf_func, bmin, bmax, h, relax_iters=4):
    f, origin = sample_grid(sdf_func, bmin, bmax, h)
    if not (f[0].min() > 0 and f[-1].min() > 0 and f[:, 0].min() > 0 and f[:, -1].min() > 0
            and f[:, :, 0].min() > 0 and f[:, :, -1].min() > 0):
        raise ValueError("SDF bounding box clips the surface")
    verts, faces = surface_nets(f, origin, h)
    verts = relax_and_project(sdf_func, verts, faces, iters=relax_iters)
    return verts, faces


def check_manifold(faces):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 3]], faces[:, [3, 0]]], 0)
    e = np.sort(e, axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts != 2).sum())
