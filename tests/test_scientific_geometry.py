"""Independent ASE geometry oracles; no GUI and no abTEM required."""
import numpy as np
import pytest
from ase import Atoms
from ase.io import read, write
from ase.utils import rotate

from abtem_ase_workbench import backend as be
from abtem_ase_workbench.orientation import (
    set_view_axes, zone_axis_direction, plane_normal_direction)


@pytest.fixture
def marker():
    # Species-labelled, scalene tetrahedron: symmetry cannot conceal a mirror.
    a = Atoms('HHeLiBe', positions=[[2, 3, 4], [4, 3.2, 4.1],
                                  [2.3, 6, 4.4], [2.7, 3.8, 8]],
              cell=[18, 20, 22], pbc=False)
    a.set_array('marker_id', np.arange(4))
    a.info['provenance'] = 'asymmetric QA marker'
    return a


def matrices():
    yield np.eye(3)
    for axis in 'xyz':
        for angle in (90, -90, 37):
            yield rotate(f'{angle}{axis}')
    yield rotate('31x,-17y,63z')
    rng = np.random.default_rng(20261008)
    for _ in range(32):
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        q[:, 0] *= np.linalg.det(q)
        yield q


@pytest.mark.parametrize('axes', list(matrices()))
@pytest.mark.parametrize('pbc', [(False, False, False), (True, True, False),
                                 (True, True, True)])
def test_exact_matrix_geometry_and_handedness(marker, axes, pbc):
    marker.pbc = pbc
    before = marker.copy()
    expected = marker.positions @ axes  # ASE viewer's documented projection
    got = be.apply_view_rotation(marker, axes, recenter=False)
    np.testing.assert_allclose(got.positions, expected, atol=2e-14, rtol=0)
    expected_cell = marker.cell.array @ axes if any(pbc) else marker.cell.array
    np.testing.assert_allclose(got.cell.array, expected_cell, atol=2e-14, rtol=0)
    np.testing.assert_array_equal(got.pbc, pbc)
    original_edges = marker.positions[1:] - marker.positions[0]
    edges = got.positions[1:] - got.positions[0]
    assert np.linalg.det(edges) == pytest.approx(np.linalg.det(original_edges))
    np.testing.assert_allclose(edges @ edges.T, original_edges @ original_edges.T,
                               atol=1e-13, rtol=0)
    centered = be.apply_view_rotation(marker, axes)
    np.testing.assert_allclose(centered.positions - centered.positions[0],
                               expected - expected[0], atol=2e-14, rtol=0)
    for key in before.arrays:
        np.testing.assert_array_equal(marker.arrays[key], before.arrays[key])
    np.testing.assert_array_equal(marker.cell, before.cell)
    assert marker.info == before.info
    np.testing.assert_array_equal(centered.numbers, marker.numbers)
    np.testing.assert_array_equal(centered.arrays['marker_id'], marker.arrays['marker_id'])


@pytest.mark.parametrize('axis', list('xyz'))
@pytest.mark.parametrize('angle', [90, -47, 0])
def test_legacy_rotation_against_ase(marker, axis, angle):
    reference = marker.copy()
    reference.rotate(angle, axis, rotate_cell=False)
    angles = [angle if a == axis else 0 for a in 'xyz']
    actual = be.apply_xyz_rotation(marker, *angles, recenter=False)
    np.testing.assert_allclose(actual.positions, reference.positions, atol=1e-14)
    # Cross-check the ASE utility matrix against ASE active rotation.
    view = be.apply_view_rotation(marker, rotate(f'{angle}{axis}'), recenter=False)
    np.testing.assert_allclose(view.positions, reference.positions, atol=1e-14)


def test_public_zone_and_plane_helpers_against_ase():
    from ase.cell import Cell
    cell = Cell([[4, 0, 0], [1.2, 6, 0], [.4, .7, 9]])
    for indices in ([1, 1, 0], [2, -1, 3]):
        zone = zone_axis_direction(indices, cell)
        normal = plane_normal_direction(indices, cell.reciprocal())
        np.testing.assert_allclose(zone, cell.cartesian_positions(indices))
        np.testing.assert_allclose(cell.array @ normal, indices, atol=1e-14)
        for direction in (zone, normal):
            axes = set_view_axes(direction)
            np.testing.assert_allclose(direction @ axes,
                                       [0, 0, np.linalg.norm(direction)], atol=1e-14)
            assert np.linalg.det(axes) == pytest.approx(1)


@pytest.mark.parametrize('bad', [np.eye(2), np.ones((3, 3)),
    np.diag([1, 1, -1]), np.diag([1, 1, 2]), np.full((3, 3), np.nan),
    np.full((3, 3), np.inf)])
def test_invalid_matrix_is_rejected_without_mutation(marker, bad):
    before = marker.positions.copy()
    with pytest.raises(ValueError):
        be.apply_view_rotation(marker, bad)
    np.testing.assert_array_equal(marker.positions, before)


@pytest.mark.parametrize('pbc', [(False, False, False), (True, True, False),
                                 (True, True, True)])
def test_oriented_extxyz_export_roundtrip(marker, pbc, tmp_path):
    marker.pbc = pbc
    axes = rotate('31x,-17y,63z')
    oriented = be.apply_view_rotation(marker, axes)
    path = tmp_path / 'oriented.extxyz'
    write(path, oriented)  # Same ASE writer used by GUI export.
    loaded = read(path)
    expected = marker.positions @ axes
    np.testing.assert_allclose(loaded.positions - loaded.positions[0],
                               expected - expected[0], atol=2e-8)
    np.testing.assert_allclose(loaded.cell, oriented.cell, atol=1e-8)
    np.testing.assert_array_equal(loaded.pbc, pbc)
    np.testing.assert_array_equal(loaded.numbers, marker.numbers)


def test_presentation_has_no_physical_side_effect(marker):
    raw = np.arange(15).reshape(3, 5)
    before = raw.copy()
    screen = be.abtem_array_to_ase_screen(raw)
    # Explicit coordinate oracle: x increases right, y increases upward.
    for x in range(3):
        for y in range(5):
            assert screen[4-y, x] == raw[x, y]
    screen[:] = -1
    np.testing.assert_array_equal(raw, before)
    with pytest.raises(ValueError):
        be.abtem_array_to_ase_screen(np.zeros((2, 3, 4)))


def test_finite_rotation_must_fit_simulation_box():
    """QA-07: rotating an elongated particle can outgrow its fixed vacuum box."""
    particle = Atoms('CSiOAl', positions=[[1, 2, 2], [11, 2.2, 2.1],
                                        [2, 3, 2.4], [3, 2.8, 4]],
                     cell=[12, 6, 6], pbc=False)
    # Accept either safe resizing or explicit rejection; never silently clip.
    try:
        work = be.apply_view_rotation(particle, rotate('90z'))
    except ValueError:
        return
    assert np.all(work.positions >= 0) and np.all(
        work.positions <= work.cell.lengths()), 'oriented particle exceeds fixed box'
