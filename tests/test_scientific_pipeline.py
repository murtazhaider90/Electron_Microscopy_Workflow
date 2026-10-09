"""Independent abTEM/statistical oracles for the exact-geometry policy.

See SCIENTIFIC_RESOLUTION.md for supported preparation and rejection contracts.
"""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.utils import rotate

from abtem_ase_workbench import backend as be
from abtem_ase_workbench.export import build_repro_script


PARAMS = dict(voltage=200e3, sampling=.2, wave_resolution=48, image_size=32,
              defocus=-12, Cs=0, C5=0, astigmatism=0, astigmatism_angle=0,
              coma=0, coma_angle=0, focal_spread=0, angular_spread=0,
              dose=2e4, rng_seed=567)


def normalize(array):
    # Independent arithmetic, never call backend normalization/presentation.
    a = np.asarray(array, float)
    return (a-a.min()) / (a.max()-a.min()) if a.max() > a.min() else a*0


def snapshot(atoms):
    return (atoms.copy(), {k: v.copy() for k, v in atoms.arrays.items()})


def unchanged(atoms, before):
    ref, arrays = before
    for key, values in arrays.items():
        np.testing.assert_array_equal(atoms.arrays[key], values)
    np.testing.assert_array_equal(atoms.cell, ref.cell)
    np.testing.assert_array_equal(atoms.pbc, ref.pbc)
    assert atoms.info == ref.info


@pytest.fixture
def asymmetric_particle():
    return Atoms('CSiOAl', positions=[[3, 4, 5], [5, 4.2, 5.1],
                                    [3.3, 7, 5.4], [3.7, 4.8, 9]],
                 cell=[16, 18, 20], pbc=False)


def direct_work(atoms, axes):
    work = atoms.copy()
    work.positions = atoms.positions @ axes
    if atoms.pbc.any():
        work.set_cell(atoms.cell.array @ axes, scale_atoms=False)
    work.center()
    return work


@pytest.mark.slow
@pytest.mark.parametrize('specimen', ['asymmetric_particle', 'si_bulk', 'mos2_slab'])
def test_tem_against_direct_abtem(specimen, request, tmp_path):
    import abtem
    atoms = request.getfixturevalue(specimen)
    before = snapshot(atoms)
    # A z quarter turn is exactly orthogonal; slab uses its native skew cell.
    axes = rotate('90z') if specimen != 'mos2_slab' else np.eye(3)
    work = direct_work(atoms, axes)
    wave = abtem.PlaneWave(energy=PARAMS['voltage'], sampling=PARAMS['sampling'])
    exit_wave = wave.multislice(abtem.Potential(work, gpts=48))
    ctf = abtem.CTF(energy=200e3, defocus=-12, Cs=0, C5=0,
                   astigmatism=0, coma=0, focal_spread=0, angular_spread=0)
    intensity = exit_wave.apply_ctf(ctf).intensity().compute()
    mean = np.asarray(intensity.array, float)*PARAMS['dose']*np.prod(intensity.sampling)
    counts = np.random.default_rng(567).poisson(np.maximum(mean, 0))
    expected = normalize(counts[:32, :32]).T[::-1].copy()
    out = tmp_path / 'image.png'
    got, meta = be.simulate_tem_from_atoms(atoms, view_axes=axes,
                                           output_file=str(out), **PARAMS)
    np.testing.assert_array_equal(got, expected)
    unchanged(atoms, before)
    again, second = be.simulate_tem_from_atoms(atoms, view_axes=axes, **PARAMS)
    np.testing.assert_array_equal(again, got)
    for key in meta:
        if key not in ('timestamp', 'output_image', 'metadata_file'):
            assert second[key] == meta[key]
    disk = json.loads(out.with_suffix('.json').read_text())
    for key in disk:
        assert disk[key] == meta[key]


@pytest.mark.slow
@pytest.mark.parametrize('presentation', [False, True])
@pytest.mark.parametrize('log_scale,block_direct', [(False, False), (True, True)])
def test_diffraction_against_direct_abtem(si_thick, presentation, log_scale, block_direct):
    import abtem
    before = snapshot(si_thick)
    work = direct_work(si_thick, np.eye(3)) if presentation else si_thick.copy()
    wave = abtem.PlaneWave(energy=200e3, sampling=.12)
    dp = wave.multislice(abtem.Potential(work, gpts=96)).diffraction_patterns(
        max_angle='cutoff', block_direct=block_direct).compute()
    arr = np.asarray(dp.array, float)
    if log_scale:
        arr = np.log1p(np.maximum(arr, 0))
    x0, y0 = [max(0, (s-32)//2) for s in arr.shape]
    expected = normalize(arr[x0:x0+32, y0:y0+32])
    if presentation:
        expected = expected.T[::-1].copy()
    got, _ = be.simulate_diffraction_from_atoms(
        si_thick, voltage=200e3, sampling=.12, wave_resolution=96,
        image_size=32, view_axes=np.eye(3) if presentation else None,
        log_scale=log_scale, block_direct=block_direct)
    np.testing.assert_allclose(got, expected, atol=1e-12, rtol=0)
    unchanged(si_thick, before)


def test_diamond_kinematic_selection_rules_against_ase(si_bulk):
    # Analytic diamond rule checked against ASE fractional atom coordinates.
    fractional = si_bulk.get_scaled_positions()
    for h in range(-4, 5):
        for k in range(-4, 5):
            for l in range(-4, 5):
                same_parity = h % 2 == k % 2 == l % 2
                allowed = same_parity and (h % 2 == 1 or (h+k+l) % 4 == 0)
                factor = np.exp(2j*np.pi*(fractional @ [h, k, l])).sum()
                assert (abs(factor) > 1e-10) == allowed, (h, k, l, factor)


@pytest.mark.parametrize('dose', [5, 50, 500])
def test_poisson_absolute_counts_and_variance(dose):
    measurement = SimpleNamespace(sampling=(.3, .7), array=np.full((512, 512), 2.5))
    before = measurement.array.copy()
    expected = dose*.3*.7*2.5
    samples = be.poisson_noise(measurement, dose, np.random.default_rng(901))
    # Five standard errors of the sample mean; broad variance gate at low count.
    assert abs(samples.mean()-expected) < 5*np.sqrt(expected/samples.size)
    assert samples.var()/expected == pytest.approx(1, rel=.025)
    np.testing.assert_array_equal(samples, np.floor(samples))
    np.testing.assert_array_equal(measurement.array, before)


def test_poisson_snr_and_pixel_area_scaling():
    m = SimpleNamespace(sampling=(.2, .5), array=np.ones((512, 512)))
    low = be.poisson_noise(m, 100, np.random.default_rng(41))
    high = be.poisson_noise(m, 900, np.random.default_rng(42))
    assert high.mean()/low.mean() == pytest.approx(9, rel=.01)
    assert (high.mean()/high.std())/(low.mean()/low.std()) == pytest.approx(3, rel=.02)
    doubled_area = SimpleNamespace(sampling=(.4, .5), array=m.array)
    counts = be.poisson_noise(doubled_area, 100, np.random.default_rng(43))
    assert counts.mean()/low.mean() == pytest.approx(2, rel=.01)


@pytest.mark.slow
def test_sampling_metadata_matches_actual_abtem_grid(asymmetric_particle):
    """QA-01: requested sampling is not the matched Potential grid sampling."""
    import abtem
    atoms = asymmetric_particle
    wave = abtem.PlaneWave(energy=200e3, sampling=.2)
    intensity = wave.multislice(abtem.Potential(atoms, gpts=48)).intensity().compute()
    image, meta = be.simulate_tem_from_atoms(atoms, **PARAMS)
    actual_sampling = np.asarray(intensity.sampling)
    assert meta['sampling'] == PARAMS['sampling']
    assert meta['requested_sampling_angstrom'] == PARAMS['sampling']
    assert meta['sampling_semantics'] == 'legacy_requested_real_space_sampling'
    np.testing.assert_allclose(meta['actual_sampling_angstrom'], actual_sampling,
                               atol=1e-12, rtol=0)
    assert meta['pixel_area_angstrom2'] == pytest.approx(np.prod(actual_sampling),
                                                        abs=1e-12, rel=0)
    assert meta['measurement_axis_order'] == ['x', 'y']
    assert meta['returned_axis_order'] == ['x', 'y']
    assert meta['measurement_shape_xy'] == list(intensity.array.shape)
    assert meta['crop_shape_xy'] == list(image.shape)
    assert meta['crop_origin_xy_pixels'] == [0, 0]
    assert meta['returned_array_shape'] == list(image.shape)
    np.testing.assert_allclose(meta['field_of_view_angstrom'],
                               np.array(image.shape)*actual_sampling,
                               atol=1e-12, rtol=0)


@pytest.mark.slow
@pytest.mark.parametrize('dose', [-1, np.nan])
def test_invalid_dose_must_raise(asymmetric_particle, dose):
    """QA-02: never silently substitute noiseless intensity for invalid dose."""
    with pytest.raises(ValueError):
        be.simulate_tem_from_atoms(asymmetric_particle, **dict(PARAMS, dose=dose))


@pytest.mark.slow
def test_metadata_cannot_overwrite_physical_provenance(asymmetric_particle):
    """QA-03: caller annotation must not falsify actual physical parameters."""
    _, meta = be.simulate_tem_from_atoms(asymmetric_particle, **PARAMS,
                                          extra_metadata={'rng_seed': 999, 'sampling': 99})
    assert meta['rng_seed'] == PARAMS['rng_seed']
    assert meta['sampling'] == PARAMS['sampling']


@pytest.mark.slow
def test_reproducible_script_equivalence(asymmetric_particle, tmp_path, monkeypatch):
    """Exercise generated code with the documented supplied atoms variable."""
    monkeypatch.chdir(tmp_path)
    axes = rotate('17x,-11y,23z').tolist()
    params = dict(view_axes=axes, rc=None, volt=200e3, defocus=-12, sampling=.2,
                  dose=2e4, isize=32, wres=48, cs=0, c5=0, ast=0, asta=0,
                  coma=0, comaa=0, fs=0, angs=0)
    ns = {'atoms': asymmetric_particle}
    exec(compile(build_repro_script(params), '<exported-script>', 'exec'), ns)
    direct, _ = be.simulate_tem_from_atoms(asymmetric_particle, view_axes=axes,
                                          **dict(PARAMS, rng_seed=12345))
    np.testing.assert_array_equal(ns['img'], direct)
    assert (tmp_path / 'reproduced.png').exists()


def test_repro_script_preserves_nondefault_seed():
    """QA-04: the exported script drops a caller's stochastic seed."""
    import ast
    tree = ast.parse(build_repro_script({'rng_seed': 567}))
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == 'simulate_tem_from_atoms')
    values = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
    assert values.get('rng_seed', 12345) == 567


@pytest.mark.slow
@pytest.mark.parametrize('entry', [be.simulate_tem_from_atoms, be.simulate_diffraction_from_atoms])
def test_invalid_view_rejected_by_both_pipelines(asymmetric_particle, entry):
    before = snapshot(asymmetric_particle)
    with pytest.raises(ValueError):
        entry(asymmetric_particle, view_axes=np.diag([1, 1, -1]))
    unchanged(asymmetric_particle, before)


@pytest.mark.slow
@pytest.mark.parametrize('specimen', ['si_bulk', 'mos2_slab'])
@pytest.mark.parametrize('supported', [False, True])
def test_abtem_preparation_preserves_exact_periodic_geometry(specimen, supported, request, monkeypatch):
    """QA-05: inspect the actual abTEM-prepared atoms, beyond the adapter."""
    import abtem
    atoms = request.getfixturevalue(specimen)
    before = snapshot(atoms)
    axes = np.eye(3) if supported else rotate('31x,-17y,63z')
    oriented = direct_work(atoms, axes)
    captured = []
    real_potential = abtem.Potential

    def inspect_potential(*args, **kwargs):
        assert supported, 'unsafe Potential created before rejection'
        potential = real_potential(*args, **kwargs)
        prepared = potential.get_transformed_atoms().copy()
        captured.append(prepared)
        return potential

    monkeypatch.setattr(abtem, 'Potential', inspect_potential)
    if not supported:
        with pytest.raises(ValueError, match='not exactly representable'):
            be.simulate_diffraction_from_atoms(atoms, view_axes=axes, voltage=200e3,
                                               wave_resolution=32, image_size=32)
        assert not captured, 'unsafe Potential created before rejection'
        unchanged(atoms, before)
        return
    be.simulate_diffraction_from_atoms(atoms, view_axes=axes, voltage=200e3,
                                       wave_resolution=32, image_size=32)
    unchanged(atoms, before)
    assert captured
    prepared = captured[-1]
    # Replication and lattice translations are allowed; strain/rotation are not.
    # Each prepared atom must equal one same-species original plus n @ cell.
    residuals = []
    inv_cell = np.linalg.inv(oriented.cell.array)
    for number in np.unique(prepared.numbers):
        originals = oriented.positions[oriented.numbers == number]
        actual = prepared.positions[prepared.numbers == number]
        fractional = (actual[:, None, :] - originals[None, :, :]) @ inv_cell
        delta = fractional - np.rint(fractional)
        # A nonperiodic slab vacuum vector is not a legal lattice translation.
        delta[..., ~oriented.pbc] = fractional[..., ~oriented.pbc]
        residuals.append(np.linalg.norm(delta @ oriented.cell.array, axis=-1).min(axis=1))
    assert max(np.max(r) for r in residuals) < 1e-7, (
        'abTEM prepared atoms differ from the exact oriented ASE lattice; '
        f'max nearest-site residual {max(np.max(r) for r in residuals):.6g} Angstrom')


@pytest.mark.slow
def test_hidden_abtem_orthogonalization_is_recorded(monkeypatch):
    """QA-06: record an exact supercell from the actual Potential boundary."""
    import abtem
    # Labelled non-cubic structure prevents symmetry hiding geometric changes.
    atoms = Atoms('CSiOAl', scaled_positions=[[.1, .2, .3], [.6, .21, .31],
                                            [.18, .7, .34], [.27, .38, .8]],
                  cell=[4, 4, 9], pbc=True)
    before = snapshot(atoms)
    axes = np.array([[.6, .8, 0], [-.8, .6, 0], [0, 0, 1]])
    oriented = direct_work(atoms, axes)
    direct, _ = abtem.orthogonalize_cell(oriented.copy(), allow_transform=False,
                                        return_transform_matrix=True)
    captured = []
    real_potential = abtem.Potential

    def inspect_potential(*args, **kwargs):
        potential = real_potential(*args, **kwargs)
        captured.append(potential.get_transformed_atoms().copy())
        return potential

    monkeypatch.setattr(abtem, 'Potential', inspect_potential)
    _, meta = be.simulate_diffraction_from_atoms(atoms, view_axes=axes,
                                                 wave_resolution=32, image_size=32)
    assert len(captured) == 1
    prepared = captured[0]
    assert len(prepared) > len(atoms)
    np.testing.assert_allclose(prepared.cell.array, direct.cell.array, atol=1e-8, rtol=0)
    np.testing.assert_allclose(prepared.positions, direct.positions, atol=1e-8, rtol=0)
    np.testing.assert_array_equal(prepared.numbers, direct.numbers)
    from test_scientific_resolution import assert_lattice_equivalent
    assert_lattice_equivalent(prepared, oriented)
    preparation = meta['preparation']
    assert meta['orthogonalized'] is True
    assert preparation['preparation_occurred'] is True
    assert preparation['orthogonalization_occurred'] is True
    assert preparation['exact_rigid_geometry_preserved'] is True
    assert preparation['method'] == 'abtem_unstrained_commensurate_cut'
    assert preparation['prepared_atom_count'] == len(prepared)
    assert preparation['source_oriented_atom_count'] == len(atoms)
    np.testing.assert_allclose(preparation['prepared_cell_angstrom'], prepared.cell.array,
                               atol=1e-12, rtol=0)
    np.testing.assert_allclose(preparation['oriented_cell_angstrom'], oriented.cell.array,
                               atol=1e-12, rtol=0)
    unchanged(atoms, before)


@pytest.mark.slow
def test_slab_vacuum_and_periodicity_at_potential_boundary(mos2_slab):
    import abtem
    original = snapshot(mos2_slab)
    work = direct_work(mos2_slab, np.eye(3))
    potential = abtem.Potential(work, gpts=48)
    prepared = potential.get_transformed_atoms()
    np.testing.assert_array_equal(prepared.pbc, [True, True, False])
    assert prepared.cell.lengths()[2] == pytest.approx(mos2_slab.cell.lengths()[2])
    assert np.ptp(prepared.positions[:, 2]) == pytest.approx(np.ptp(mos2_slab.positions[:, 2]))
    # Repeat in plane is legitimate; repeating through the vacuum is not.
    assert len(prepared) >= len(mos2_slab)
    assert prepared.positions[:, 2].min() == pytest.approx(mos2_slab.positions[:, 2].min())
    unchanged(mos2_slab, original)


@pytest.mark.slow
def test_finite_tilt_preserves_one_marker_particle(asymmetric_particle):
    import abtem
    axes = rotate('31x,-17y,63z')
    work = direct_work(asymmetric_particle, axes)
    prepared = abtem.Potential(work, gpts=48).get_transformed_atoms()
    assert len(prepared) == len(asymmetric_particle)
    np.testing.assert_array_equal(prepared.pbc, [False, False, False])
    np.testing.assert_array_equal(prepared.numbers, asymmetric_particle.numbers)
    np.testing.assert_allclose(prepared.positions-prepared.positions[0],
                               asymmetric_particle.positions @ axes -
                               (asymmetric_particle.positions @ axes)[0], atol=1e-13)
    np.testing.assert_array_equal(prepared.cell, asymmetric_particle.cell)


@pytest.mark.slow
@pytest.mark.parametrize('entry', [be.simulate_tem_from_atoms, be.simulate_diffraction_from_atoms])
def test_negative_image_size_must_raise(asymmetric_particle, entry):
    """QA-08: Python negative slices are not a valid physical image size."""
    with pytest.raises(ValueError):
        entry(asymmetric_particle, wave_resolution=32, image_size=-1)


@pytest.mark.slow
def test_source_unchanged_when_engine_fails(asymmetric_particle, monkeypatch):
    import abtem
    before = snapshot(asymmetric_particle)

    def fail(*args, **kwargs):
        raise RuntimeError('deliberate downstream engine failure')

    monkeypatch.setattr(abtem, 'Potential', fail)
    with pytest.raises(RuntimeError, match='deliberate downstream'):
        be.simulate_tem_from_atoms(asymmetric_particle,
                                   view_axes=rotate('31x,-17y,63z'), **PARAMS)
    unchanged(asymmetric_particle, before)
