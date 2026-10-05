"""Pure orientation math for the ASE Electron Microscopy Workbench.

No Tk, no abTEM — only NumPy and ASE lattice helpers. These functions do the
Miller / zone-axis / view-matrix work the GUI uses, so the logic can be
unit-tested and reused by scripts.
"""
from math import gcd

import numpy as np


def _norm(v):
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        raise ValueError("direction has zero length")
    return v / n


def set_view_axes(direction_cart):
    """Build the ASE-GUI 3×3 view-axes matrix for a given beam direction.

    Column 2 of the returned matrix is the normalized beam direction. The
    matrix is a proper rotation (det = +1); a sensible screen-up is picked
    automatically.

    Raises
    ------
    ValueError
        If ``direction_cart`` has zero length.
    """
    z = _norm(direction_cart)
    up_ref = np.array([0.0, 1.0, 0.0])
    if abs(float(up_ref @ z)) > 0.99:
        up_ref = np.array([1.0, 0.0, 0.0])
    x = _norm(np.cross(up_ref, z))
    y = _norm(np.cross(z, x))
    return np.column_stack([x, y, z])


def zone_axis_direction(uvw, cell):
    """Cartesian direction of a crystal zone axis [u v w].

    direction = ``[u, v, w] @ cell`` (cell rows are the lattice vectors a, b, c).
    """
    return np.asarray(uvw, dtype=float) @ np.asarray(cell, dtype=float)


def plane_normal_direction(hkl, cell_reciprocal):
    """Cartesian direction of a plane normal (h k l) via the reciprocal cell.

    normal = ``[h, k, l] @ cell.reciprocal().array``. For non-cubic cells this
    is NOT the same as ``[hkl] @ cell``.
    """
    return np.asarray(hkl, dtype=float) @ np.asarray(cell_reciprocal, dtype=float)


def reduced_triples(max_index):
    """All gcd-reduced, sign-canonical [uvw] triples with |u|,|v|,|w| ≤ N."""
    seen, triples = set(), []
    m = int(max_index)
    for u in range(-m, m + 1):
        for v in range(-m, m + 1):
            for w in range(-m, m + 1):
                if u == 0 and v == 0 and w == 0:
                    continue
                g = gcd(gcd(abs(u), abs(v)), abs(w)) or 1
                ru, rv, rw = u // g, v // g, w // g
                for c in (ru, rv, rw):
                    if c != 0:
                        if c < 0:
                            ru, rv, rw = -ru, -rv, -rw
                        break
                key = (ru, rv, rw)
                if key not in seen:
                    seen.add(key)
                    triples.append(key)
    return triples


def nearest_zone_axis(beam_cart, cell, max_index=4):
    """Return (best [uvw], angle_deg) for the integer triple whose crystal
    direction best matches a Cartesian beam direction (sign-flip insensitive).

    Returns ``(None, None)`` if ``beam_cart`` has zero length.
    """
    beam = np.asarray(beam_cart, dtype=float)
    bn = float(np.linalg.norm(beam))
    if bn < 1e-12:
        return None, None
    beam = beam / bn
    cell = np.asarray(cell, dtype=float)
    best, best_ang = None, 1e9
    for tri in reduced_triples(max_index):
        d = np.array(tri, dtype=float) @ cell
        nd = float(np.linalg.norm(d))
        if nd < 1e-12:
            continue
        cos = abs(float((d / nd) @ beam))
        cos = max(-1.0, min(1.0, cos))
        ang = float(np.degrees(np.arccos(cos)))
        if ang < best_ang:
            best_ang, best = ang, tri
    return best, best_ang


__all__ = [
    "set_view_axes",
    "zone_axis_direction",
    "plane_normal_direction",
    "reduced_triples",
    "nearest_zone_axis",
]
