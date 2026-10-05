"""rotate_cell policy + the anti-tiling *mechanism* (no abTEM)."""
import numpy as np
import pytest

from abtem_tem_backend import (resolve_rotate_cell, rotation_mode_name,
                               apply_xyz_rotation, apply_view_rotation,
                               abtem_array_to_ase_screen)


def test_finite_particle_resolves_false(pt13):
    assert resolve_rotate_cell(pt13, None) is False
    assert rotation_mode_name(False) == "finite_particle"


def test_periodic_crystal_resolves_true(si_bulk):
    assert resolve_rotate_cell(si_bulk, None) is True
    assert rotation_mode_name(True) == "periodic_crystal"


def test_2d_slab_auto_is_periodic(graphene_slab):
    # pbc [T,T,F] -> np.any True -> periodic (rotate cell)
    assert resolve_rotate_cell(graphene_slab, None) is True


def test_explicit_override(pt13, si_bulk):
    assert resolve_rotate_cell(pt13, True) is True
    assert resolve_rotate_cell(si_bulk, False) is False


def test_finite_mode_keeps_box_orthogonal_and_unchanged(pt13):
    """The anti-tiling mechanism: finite rotation leaves the vacuum box
    orthogonal and identical, so abTEM cannot tile skewed copies."""
    orig = pt13.cell.array.copy()
    rot = apply_xyz_rotation(pt13, 30, 20, 10, rotate_cell=False)
    assert np.allclose(rot.cell.array, orig, atol=1e-9)        # box unchanged
    assert rot.pbc.tolist() == [False, False, False]
    # atoms actually rotated (not a no-op)
    assert not np.allclose(rot.get_positions(), pt13.get_positions())


def test_periodic_mode_skews_cell(pt13):
    """Forcing rotate_cell=True on the same particle skews the box (the bug
    condition the finite mode avoids)."""
    rot = apply_xyz_rotation(pt13, 30, 20, 10, rotate_cell=True)
    offdiag = rot.cell.array - np.diag(np.diagonal(rot.cell.array))
    assert np.abs(offdiag).max() > 1e-3


def test_input_atoms_never_mutated(si_bulk):
    p0 = si_bulk.get_positions().copy()
    c0 = si_bulk.cell.array.copy()
    apply_xyz_rotation(si_bulk, 45, 30, 15, rotate_cell=True)
    assert np.allclose(si_bulk.get_positions(), p0)
    assert np.allclose(si_bulk.cell.array, c0)


def test_exact_ase_view_matrix_preserves_projected_geometry(pt13):
    """Canonical orientation gate: the copied atoms sent to abTEM have the
    same relative x/y projection as ASE's ``positions @ gui.axes``.

    Recentring may add a constant translation, so compare pairwise relative
    coordinates rather than absolute positions.
    """
    # A deliberately asymmetric proper rotation (not a simple axis swap).
    ax = np.deg2rad(31.0)
    ay = np.deg2rad(-17.0)
    Rx = np.array([[1, 0, 0],
                   [0, np.cos(ax), -np.sin(ax)],
                   [0, np.sin(ax), np.cos(ax)]], float)
    Ry = np.array([[np.cos(ay), 0, np.sin(ay)],
                   [0, 1, 0],
                   [-np.sin(ay), 0, np.cos(ay)]], float)
    axes = Rx @ Ry

    expected = pt13.get_positions() @ axes
    got = apply_view_rotation(pt13, axes, rotate_cell=False).get_positions()
    assert np.allclose(got[1:] - got[0], expected[1:] - expected[0], atol=1e-9)


def test_exact_view_periodic_rotates_cell_same_matrix(si_bulk):
    th = np.deg2rad(23.0)
    axes = np.array([[np.cos(th), -np.sin(th), 0.0],
                     [np.sin(th), np.cos(th), 0.0],
                     [0.0, 0.0, 1.0]])
    original = si_bulk.cell.array.copy()
    out = apply_view_rotation(si_bulk, axes, rotate_cell=True)
    assert np.allclose(out.cell.array, original @ axes, atol=1e-9)


def test_view_rotation_rejects_reflection(pt13):
    bad = np.diag([1.0, 1.0, -1.0])  # det = -1, not a physical rotation
    with pytest.raises(ValueError):
        apply_view_rotation(pt13, bad, rotate_cell=False)


def test_abtem_array_to_ase_screen_is_transpose_plus_vertical_flip():
    raw = np.array([[1, 2, 3],
                    [4, 5, 6]])  # raw[x, y]
    screen = abtem_array_to_ase_screen(raw)
    assert np.array_equal(screen, np.array([[3, 6],
                                             [2, 5],
                                             [1, 4]]))
