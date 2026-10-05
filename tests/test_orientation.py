"""Orientation math hard gates (no abTEM, no Tk)."""
import numpy as np
import pytest
from ase.build import bulk

from abtem_tem_backend import resolve_rotate_cell


def _norm(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _set_view_axes(direction_cart):
    """Replica of the tool's _set_view_direction axes construction
    (including its zero-length guard, which raises ValueError)."""
    if np.linalg.norm(np.asarray(direction_cart, float)) < 1e-9:
        raise ValueError("direction has zero length")
    z = _norm(direction_cart)
    up = np.array([0.0, 1.0, 0.0])
    if abs(up @ z) > 0.99:
        up = np.array([1.0, 0.0, 0.0])
    x = _norm(np.cross(up, z))
    y = _norm(np.cross(z, x))
    return np.column_stack([x, y, z])


@pytest.mark.parametrize("uvw", [(1, 0, 0), (0, 1, 0), (0, 0, 1),
                                 (1, 1, 0), (1, 1, 1)])
def test_zone_axis_beam_is_requested_direction(uvw):
    cell = bulk("Si", "diamond", a=5.43, cubic=True).cell.array
    direction = np.array(uvw, float) @ cell
    axes = _set_view_axes(direction)
    # beam = column 2 must equal the normalized crystal direction, det = +1
    assert np.allclose(axes[:, 2], _norm(direction), atol=1e-9)
    assert np.isclose(np.linalg.det(axes), 1.0, atol=1e-9)


@pytest.mark.parametrize("hkl", [(1, 0, 0), (1, 1, 0), (1, 1, 1)])
def test_plane_normal_uses_reciprocal(hkl):
    atoms = bulk("Si", "diamond", a=5.43, cubic=True)
    recip = atoms.cell.reciprocal().array
    normal = np.array(hkl, float) @ recip
    axes = _set_view_axes(normal)
    assert np.allclose(axes[:, 2], _norm(normal), atol=1e-9)


def test_irotate_roundtrip():
    from ase.utils import irotate, rotate
    for uvw in [(1, 0, 0), (1, 1, 0), (1, 1, 1)]:
        A = _set_view_axes(np.array(uvw, float))
        x, y, z = irotate(A)
        assert np.allclose(rotate(f"{x}x,{y}y,{z}z"), A, atol=1e-6)


def test_noncubic_zone_differs_from_plane():
    """For an anisotropic cell, [110] direction != (110) plane normal."""
    atoms = bulk("Si", "diamond", a=5.43, cubic=True)
    atoms.set_cell([4.0, 6.0, 9.0], scale_atoms=True)
    cell = atoms.cell.array
    recip = atoms.cell.reciprocal().array
    zone = _norm(np.array([1, 1, 0], float) @ cell)
    plane = _norm(np.array([1, 1, 0], float) @ recip)
    assert not np.allclose(zone, plane, atol=1e-3)


def _nearest_zone(beam, cell, max_index=4):
    """Replica of the tool's nearest-zone-axis search."""
    from math import gcd
    beam = _norm(beam)
    seen, best, best_ang = set(), None, 1e9
    m = max_index
    for u in range(-m, m + 1):
        for v in range(-m, m + 1):
            for w in range(-m, m + 1):
                if u == v == w == 0:
                    continue
                g = gcd(gcd(abs(u), abs(v)), abs(w)) or 1
                key = (u // g, v // g, w // g)
                for c in key:
                    if c != 0:
                        if c < 0:
                            key = tuple(-x for x in key)
                        break
                if key in seen:
                    continue
                seen.add(key)
                d = np.array(key, float) @ cell
                if np.linalg.norm(d) < 1e-12:
                    continue
                ang = np.degrees(np.arccos(min(1.0, abs(_norm(d) @ beam))))
                if ang < best_ang:
                    best_ang, best = ang, key
    return best, best_ang


@pytest.mark.parametrize("uvw", [(1, 0, 0), (1, 1, 0), (1, 1, 1), (2, 1, 0)])
def test_nearest_zone_axis_exact(uvw):
    cell = bulk("Si", "diamond", a=5.43, cubic=True).cell.array
    beam = np.array(uvw, float) @ cell
    best, ang = _nearest_zone(beam, cell, max_index=4)
    assert best == uvw
    assert ang < 1e-3


def test_zero_vector_rejected():
    with pytest.raises(Exception):
        # zero direction has no normalizable axis
        _set_view_axes(np.array([0.0, 0.0, 0.0]))
