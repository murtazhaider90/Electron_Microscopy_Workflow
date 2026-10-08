"""Scientific specimen contracts: no Qt required."""
import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, graphene, make_supercell
from abtem_ase_workbench.specimen import Specimen, View, build_specimen
from abtem_ase_workbench.backend import apply_view_rotation


@pytest.fixture
def asymmetric():
    return Atoms('CHON', positions=[[0.2, -0.4, 1.1], [2.3, 0.8, -0.7],
                                  [-1.2, 2.1, 0.3], [0.9, -1.3, 2.7]],
                 cell=[[6, 0, 0], [1.1, 7, 0], [0.8, 1.2, 8]])


def test_exact_asymmetric_projection_and_backend(asymmetric):
    s = Specimen(asymmetric)
    for dx, dy in [(0.43, -0.71), (-0.2, 0.6), (0.8, 0.3)]:
        s.view.rotate(dx, dy)
    s.view.pivot = np.array([0.7, 0.2, -0.4])
    s.view.pan = np.array([13, -27.5])
    s.view.scale = 33
    xy, depth = s.view.project(s.atoms.positions, (730, 510))
    inputs = s.backend_inputs()
    oriented = apply_view_rotation(**inputs, recenter=False)
    expected = (oriented.positions - s.view.pivot @ inputs['view_axes'])
    np.testing.assert_allclose(xy, expected[:, :2]*[33, -33]+[378, 227.5], atol=1e-12)
    np.testing.assert_allclose(depth, expected[:, 2], atol=1e-12)
    np.testing.assert_array_equal(s.atoms.positions, asymmetric.positions)
    inputs['atoms'].positions[:] = 100
    inputs['view_axes'][:] = 0
    np.testing.assert_array_equal(s.atoms.positions, asymmetric.positions)
    assert np.linalg.det(s.view.axes) == pytest.approx(1)


def test_view_validation_and_picking():
    v = View()
    for bad in [np.zeros((3, 3)), np.diag([1, 1, -1]), np.full((3, 3), np.nan)]:
        with pytest.raises(ValueError):
            v.set_axes(bad)
    positions = np.array([[0, 0, -1], [0, 0, 3], [2, 1, 0]])
    assert v.pick(positions, (400, 300), (200, 150)) == 1
    assert v.pick(positions, (400, 300), (10, 10)) is None
    v.fit(Atoms(), (400, 300))
    assert np.isfinite(v.scale)


def test_edits_transactions_history(asymmetric):
    s = Specimen(asymmetric)
    s.select([1, 3])
    original = s.atoms
    s.move([1, 2, 3])
    s.change('Si')
    assert s.atoms.get_chemical_symbols() == ['C', 'Si', 'O', 'Si']
    s.delete()
    assert len(s.atoms) == 2 and not s.selection
    assert s.undo() and s.selection == {1, 3}
    assert s.redo() and len(s.atoms) == 2 and not s.selection
    s.undo(); s.undo(); s.undo()
    np.testing.assert_array_equal(s.atoms.positions, original.positions)
    assert s.selection == {1, 3}
    s.add('Au', [3, 4, 5])
    assert not s.redo()
    before = s.atoms
    history = len(s._undo)
    with pytest.raises(ValueError):
        s.add('not-element', [0, 0, 0])
    with pytest.raises(ValueError):
        s.move([np.nan, 0, 0])
    np.testing.assert_array_equal(s.atoms.positions, before.positions)
    assert len(s._undo) == history
    exposed = s.atoms
    exposed.positions[:] = 999
    np.testing.assert_array_equal(s.atoms.positions, before.positions)


@pytest.mark.parametrize('atoms', [bulk('Si', 'diamond', a=5.43), graphene(vacuum=5), build_specimen('icosahedron', symbol='Pt', noshells=2)])
def test_ase_operations_preserve_topology(atoms):
    s = Specimen(atoms)
    expected = atoms.copy()
    expected.center(vacuum=4)
    s.center(4)
    np.testing.assert_allclose(s.atoms.positions, expected.positions)
    np.testing.assert_array_equal(s.atoms.pbc, atoms.pbc)
    s.repeat([2, 1, 1])
    np.testing.assert_allclose(s.atoms.positions, expected.repeat((2, 1, 1)).positions)
    s.undo()
    p = [[2, 1, 0], [0, 1, 0], [0, 0, 1]]
    s.supercell(p)
    np.testing.assert_allclose(s.atoms.positions, make_supercell(expected, p).positions)
    np.testing.assert_array_equal(s.atoms.pbc, atoms.pbc)
    s.wrap()
    comparison = s.atoms
    comparison.wrap()
    np.testing.assert_allclose(s.atoms.positions, comparison.positions)


def test_cell_bonds_and_reciprocal(asymmetric):
    s = Specimen(asymmetric)
    s.zone_axis([1, 2, 1])
    axis = np.array([1, 2, 1]) @ asymmetric.cell.array
    np.testing.assert_allclose(axis @ s.view.axes, [0, 0, np.linalg.norm(axis)], atol=1e-12)
    s.plane_normal([1, 2, 1])
    normal = np.array([1, 2, 1]) @ asymmetric.cell.reciprocal().array
    np.testing.assert_allclose(normal @ s.view.axes, [0, 0, np.linalg.norm(normal)], atol=1e-12)
    a = Atoms('HH', positions=[[0.1, 0, 0], [2.9, 0, 0]], cell=[3, 4, 5], pbc=[True, False, False])
    s = Specimen(a)
    bonds, edges = s.geometry()
    assert len(edges) == 24
    np.testing.assert_allclose(np.linalg.norm(bonds[1::2]-bonds[::2], axis=1), [0.2])
    s.set_pbc(False)
    assert len(s.geometry()[0]) == 0
    s.set_cell([6, 7, 8])
    np.testing.assert_allclose(s.atoms.cell.lengths(), [6, 7, 8])


def test_io_and_orientation(tmp_path, asymmetric):
    s = Specimen(asymmetric)
    s.view.rotate(0.37, -0.19)
    path = tmp_path/'specimen.extxyz'
    s.save(path)
    loaded = Specimen()
    loaded.open(path)
    np.testing.assert_allclose(loaded.atoms.positions, asymmetric.positions)
    np.testing.assert_array_equal(loaded.atoms.pbc, asymmetric.pbc)
    np.testing.assert_allclose(loaded.atoms.info['specimen_view_axes'], s.view.axes)
    np.testing.assert_array_equal(loaded.view.axes, s.view.axes)
    loaded.undo()
    assert len(loaded.atoms) == 0
    np.testing.assert_array_equal(loaded.view.axes, np.eye(3))
    loaded.redo()
    np.testing.assert_array_equal(loaded.view.axes, s.view.axes)


@pytest.mark.parametrize('kind,parameters', [
    ('bulk', dict(name='Si', crystalstructure='diamond', a=5.43)),
    ('fcc111', dict(symbol='Au', size=(2, 2, 3), vacuum=6)),
    ('bcc110', dict(symbol='Fe', size=(2, 2, 3), vacuum=6)),
    ('hcp0001', dict(symbol='Ti', size=(2, 2, 3), vacuum=6)),
    ('surface', dict(lattice='Au', indices=(1, 1, 1), layers=3, vacuum=6)),
    ('graphene', dict(vacuum=6)), ('mx2', dict(vacuum=6)),
    ('icosahedron', dict(symbol='Pt', noshells=2)),
    ('decahedron', dict(symbol='Pt', p=3, q=2, r=0)),
    ('octahedron', dict(symbol='Pt', length=4, cutoff=1)),
    ('nanotube', dict(n=6, m=0, length=2))])
def test_builders(kind, parameters):
    a = build_specimen(kind, **parameters)
    assert isinstance(a, Atoms) and len(a)
    if kind in {'icosahedron', 'decahedron', 'octahedron'}:
        assert not a.pbc.any()
    elif kind == 'nanotube':
        np.testing.assert_array_equal(a.pbc, [False, False, True])


def test_core_has_no_gui_dependency():
    import subprocess
    import sys
    subprocess.run([sys.executable, "-c", "import sys; import abtem_ase_workbench.specimen; assert not any(m.startswith(('PySide6', 'vispy', 'tkinter')) for m in sys.modules)"], check=True)


def test_failed_orientation_io_does_not_replace(tmp_path, asymmetric):
    from ase.io import write
    invalid = asymmetric.copy()
    invalid.info['specimen_view_axes'] = np.zeros((3, 3)).tolist()
    path = tmp_path/'invalid.extxyz'
    write(path, invalid)
    model = Specimen(asymmetric)
    with pytest.raises(ValueError):
        model.open(path)
    np.testing.assert_array_equal(model.atoms.positions, asymmetric.positions)
    assert not model._undo
