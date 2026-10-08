"""Independent checks for the resolution policies; audit assertions stay intact."""
import ast
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.build import mx2
from ase.utils import rotate

from abtem_ase_workbench import backend as be
from abtem_ase_workbench.export import build_repro_script


@pytest.mark.parametrize('dose', [-1, np.nan, np.inf, -np.inf, 'invalid', None])
def test_dose_rejected_before_engine_and_in_noise(dose, monkeypatch):
    def unexpected():
        pytest.fail('invalid input reached engine')
    monkeypatch.setattr(be, '_load_abtem', unexpected)
    with pytest.raises(ValueError, match='dose'):
        be.simulate_tem_from_atoms(Atoms('C'), dose=dose)
    with pytest.raises(ValueError, match='dose'):
        be.poisson_noise(SimpleNamespace(sampling=(.2, .5), array=np.ones((2, 2))),
                         dose, np.random.default_rng(2))


def test_zero_dose_has_zero_electron_counts():
    m = SimpleNamespace(sampling=(.2, .5), array=np.ones((2, 3)))
    np.testing.assert_array_equal(be.poisson_noise(m, 0, np.random.default_rng(1)), 0)


@pytest.mark.parametrize('entry', [be.simulate_tem_from_atoms, be.simulate_diffraction_from_atoms])
@pytest.mark.parametrize('value', [0, -1, np.nan, np.inf, 2.5, True, '32', None])
def test_invalid_sizes_fail_before_engine(entry, value, monkeypatch):
    monkeypatch.setattr(be, '_load_abtem', lambda: pytest.fail('entered engine'))
    for name in ('image_size', 'wave_resolution'):
        with pytest.raises(ValueError, match=name):
            entry(Atoms('C'), **{name: value})


@pytest.mark.parametrize('axes', [rotate('90z'), rotate('31x,-17y,63z'), rotate('90y')])
def test_elongated_finite_box_policy(axes):
    source = Atoms('CSiOAl', positions=[[1, 2, 2], [11, 2.2, 2.1],
                                       [2, 3, 2.4], [3, 2.8, 4]],
                   cell=[12, 6, 6], pbc=False)
    before = source.copy()
    with pytest.raises(ValueError, match='vacuum'):
        be.apply_view_rotation(source, axes)
    np.testing.assert_array_equal(source.positions, before.positions)
    np.testing.assert_array_equal(source.cell, before.cell)
    assert not source.pbc.any()


def test_export_explicit_optional_parameters():
    script = build_repro_script(dict(rng_seed=567, gaussian_spread=.4,
                                     rotation_angle=12, rotation_axis='y'))
    call = next(n for n in ast.walk(ast.parse(script)) if isinstance(n, ast.Call))
    values = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
    assert values['rng_seed'] == 567
    assert values['gaussian_spread'] == .4
    assert values['rotation_angle'] == 12
    assert values['rotation_axis'] == 'y'


def assert_lattice_equivalent(prepared, oriented):
    """Independent same-species ASE fractional-lattice oracle."""
    inv = np.linalg.inv(oriented.cell.array)
    for number in np.unique(prepared.numbers):
        original = oriented.positions[oriented.numbers == number]
        actual = prepared.positions[prepared.numbers == number]
        frac = (actual[:, None] - original[None]) @ inv
        residual = frac.copy()
        residual[..., oriented.pbc] -= np.rint(frac[..., oriented.pbc])
        distances = np.linalg.norm(residual @ oriented.cell.array, axis=-1)
        assert np.max(distances.min(axis=1)) < 1e-8
    lattice = prepared.cell.array @ inv
    np.testing.assert_allclose(lattice, np.rint(lattice), atol=1e-8, rtol=0)
    assert np.linalg.det(prepared.cell.array) > 0
    assert len(prepared) == round(abs(np.linalg.det(lattice))) * len(oriented)
    np.testing.assert_array_equal(prepared.pbc, oriented.pbc)


@pytest.mark.slow
@pytest.mark.parametrize('slab', [False, True])
@pytest.mark.parametrize('axes', [np.eye(3), rotate('90z')])
def test_non_cubic_labelled_geometry_at_real_potential_boundary(slab, axes):
    source = Atoms('CSiOAl', scaled_positions=[[.1, .2, .3], [.6, .21, .31],
                                             [.18, .7, .34], [.27, .38, .8]],
                   cell=[4, 6, 9], pbc=[True, True, not slab])
    before = source.copy()
    oriented = source.copy()
    oriented.positions = source.positions @ axes
    oriented.set_cell(source.cell.array @ axes, scale_atoms=False)
    oriented.center()
    be._load_abtem()
    potential, meta = be._prepare_potential(oriented, 32)
    prepared = potential.get_transformed_atoms()
    assert_lattice_equivalent(prepared, oriented)
    assert meta['prepared_atom_count'] == len(prepared)
    assert meta['exact_rigid_geometry_preserved']
    np.testing.assert_allclose(meta['prepared_cell_angstrom'], prepared.cell.array)
    np.testing.assert_array_equal(source.positions, before.positions)
    np.testing.assert_array_equal(source.cell, before.cell)


@pytest.mark.slow
def test_exact_commensurate_replication_and_recorded_preparation():
    # Rational 3:4:5 in-plane rotation: exact rectangular supercell exists.
    # Non-cubic, species-labelled geometry prevents cubic symmetry masking.
    source = Atoms('CSiOAl', scaled_positions=[[.1, .2, .3], [.6, .21, .31],
                                             [.18, .7, .34], [.27, .38, .8]],
                   cell=[4, 4, 9], pbc=True)
    axes = np.array([[.6, .8, 0], [-.8, .6, 0], [0, 0, 1]])
    oriented = source.copy()
    oriented.positions = source.positions @ axes
    oriented.set_cell(source.cell.array @ axes, scale_atoms=False)
    oriented.center()
    be._load_abtem()
    potential, meta = be._prepare_potential(oriented, 32)
    prepared = potential.get_transformed_atoms()
    assert_lattice_equivalent(prepared, oriented)
    assert meta['orthogonalization_occurred'] is True
    assert len(prepared) > len(source)


@pytest.mark.slow
def test_native_slab_unstrained_preparation():
    source = mx2(formula='MoS2', a=3.18, thickness=3.19, vacuum=8)
    before = source.copy()
    be._load_abtem()
    potential, meta = be._prepare_potential(source, 32)
    prepared = potential.get_transformed_atoms()
    assert_lattice_equivalent(prepared, source)
    assert meta['orthogonalization_occurred'] is True
    assert meta['specimen_type'] == '2d_periodic'
    assert prepared.cell[2, 2] == pytest.approx(source.cell[2, 2])
    np.testing.assert_array_equal(source.positions, before.positions)
    np.testing.assert_array_equal(source.cell, before.cell)


@pytest.mark.slow
@pytest.mark.parametrize('specimen', ['si_bulk', 'mos2_slab'])
@pytest.mark.parametrize('entry', [be.simulate_tem_from_atoms, be.simulate_diffraction_from_atoms])
def test_inexact_periodic_orientation_rejected_before_potential(specimen, entry, request, monkeypatch):
    import abtem
    source = request.getfixturevalue(specimen)
    before = source.copy()
    monkeypatch.setattr(abtem, 'Potential', lambda *a, **k: pytest.fail('unsafe Potential created'))
    with pytest.raises(ValueError, match='not exactly representable'):
        entry(source, view_axes=rotate('31x,-17y,63z'), wave_resolution=32)
    np.testing.assert_array_equal(source.positions, before.positions)
    np.testing.assert_array_equal(source.cell, before.cell)
    np.testing.assert_array_equal(source.pbc, before.pbc)


@pytest.mark.slow
def test_real_calibration_and_authoritative_provenance():
    import abtem
    source = Atoms('CSiOAl', positions=[[3, 4, 5], [5, 4.2, 5.1],
                                     [3.3, 7, 5.4], [3.7, 4.8, 9]],
                   cell=[16, 18, 20], pbc=False)
    params = dict(voltage=200e3, sampling=.2, wave_resolution=48, image_size=32)
    axes = np.eye(3)
    oriented = source.copy()
    oriented.center()
    wave = abtem.PlaneWave(energy=200e3, sampling=.2)
    potential = abtem.Potential(oriented, gpts=48, periodic=False)
    measurement = wave.multislice(potential).intensity().compute()
    annotations = dict(ase_view_axes=[[99]], rng_seed=9, preparation={},
                       structure_pbc=[True]*3, actual_sampling_angstrom=[99, 99],
                       sampling_semantics='false', note='retained')
    image, meta = be.simulate_tem_from_atoms(source, view_axes=axes,
                                            extra_metadata=annotations, **params)
    np.testing.assert_allclose(meta['actual_sampling_angstrom'], measurement.sampling)
    np.testing.assert_allclose(meta['field_of_view_angstrom'], np.array([32, 32])*measurement.sampling)
    assert meta['pixel_area_angstrom2'] == pytest.approx(np.prod(measurement.sampling))
    assert meta['measurement_shape_xy'] == [48, 48]
    assert meta['returned_array_shape'] == list(image.shape)
    assert meta['returned_axis_order'] == ['y_down', 'x']
    assert meta['sampling'] == .2
    assert meta['sampling_semantics'] == 'legacy_requested_real_space_sampling'
    assert meta['user_metadata'] == annotations
    assert meta['rng_seed'] == 12345
    assert meta['structure_pbc'] == [False]*3
    np.testing.assert_array_equal(meta['ase_view_axes'], axes)
    assert meta['preparation']['potential_periodic'] is False
    dp = wave.multislice(potential).diffraction_patterns(max_angle='cutoff').compute()
    _, dm = be.simulate_diffraction_from_atoms(source, view_axes=axes, **params)
    np.testing.assert_allclose(dm['reciprocal_sampling_inverse_angstrom'], dp.sampling)
    np.testing.assert_allclose(dm['angular_sampling_mrad'], dp.angular_sampling)
    np.testing.assert_allclose(dm['actual_real_space_sampling_angstrom'], potential.sampling)
    origin = [max(0, (size-32)//2) for size in dp.array.shape]
    assert dm['crop_origin_xy_pixels'] == origin
    np.testing.assert_allclose(dm['reciprocal_crop_offset_inverse_angstrom'],
                               np.array(dp.offset)+np.array(origin)*dp.sampling)


@pytest.mark.slow
def test_commensurate_change_of_beam_on_non_cubic_lattice():
    source = Atoms('CSiOAl', scaled_positions=[[.1, .2, .3], [.6, .21, .31],
                                             [.18, .7, .34], [.27, .38, .8]],
                   cell=[9, 4, 4], pbc=True)
    axes = np.array([[1, 0, 0], [0, .6, .8], [0, -.8, .6]])
    oriented = source.copy()
    oriented.positions = source.positions @ axes
    oriented.set_cell(source.cell.array @ axes, scale_atoms=False)
    oriented.center()
    be._load_abtem()
    potential, meta = be._prepare_potential(oriented, 32)
    assert_lattice_equivalent(potential.get_transformed_atoms(), oriented)
    # The new +z beam is exactly the viewer's third column in source axes.
    np.testing.assert_allclose(axes[:, 2] @ axes, [0, 0, 1], atol=1e-14)
    assert meta['exact_rigid_geometry_preserved']


@pytest.mark.slow
@pytest.mark.parametrize('axes', [rotate('31x,-17y,63z'), rotate('90z'),
                                  rotate('37y'), rotate('-47x')])
def test_finite_asymmetric_geometry_handedness_at_engine_boundary(axes):
    source = Atoms('CSiOAl', positions=[[3, 4, 5], [5, 4.2, 5.1],
                                     [3.3, 7, 5.4], [3.7, 4.8, 9]],
                   cell=[16, 18, 20], pbc=False)
    expected = source.positions @ axes
    oriented = source.copy()
    oriented.positions = expected
    oriented.center()
    be._load_abtem()
    potential, meta = be._prepare_potential(oriented, 32)
    prepared = potential.get_transformed_atoms()
    np.testing.assert_allclose(prepared.positions-prepared.positions[0],
                               expected-expected[0], atol=1e-13, rtol=0)
    assert np.linalg.det(prepared.positions[1:]-prepared.positions[0]) == pytest.approx(
        np.linalg.det(source.positions[1:]-source.positions[0]))
    assert len(prepared) == len(source)
    assert not prepared.pbc.any()
    assert potential.periodic is False
    assert meta['orthogonalization_occurred'] is False


@pytest.mark.slow
@pytest.mark.parametrize('entry', [be.simulate_tem_from_atoms, be.simulate_diffraction_from_atoms])
def test_periodic_rotation_cannot_detach_atoms_from_lattice(si_bulk, entry):
    with pytest.raises(ValueError, match='rotate the lattice'):
        entry(si_bulk, view_axes=rotate('90z'), rotate_cell=False, wave_resolution=32)


@pytest.mark.slow
def test_finite_skew_box_rejected_not_tiled(pt13):
    with pytest.raises(ValueError, match='axis-aligned'):
        be.simulate_tem_from_atoms(pt13, view_axes=rotate('20x,15y'),
                                   rotate_cell=True, wave_resolution=32)
