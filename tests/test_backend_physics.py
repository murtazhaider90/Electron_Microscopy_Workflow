"""abTEM physics HARD GATES (marked slow). Thresholds calibrated empirically
and cross-checked against theory (diamond structure factors; Poisson √N; a
finite particle must not scatter intensity to the vacuum box border)."""
import numpy as np
import pytest

from conftest import SI_A


def _border_std(im, w=20):
    b = np.concatenate([im[:w].ravel(), im[-w:].ravel(),
                        im[:, :w].ravel(), im[:, -w:].ravel()])
    return float(b.std())


@pytest.mark.slow
def test_image_finite_and_saved(pt13, tmp_path):
    from abtem_tem_backend import simulate_tem_from_atoms
    from ase.utils import rotate
    out = str(tmp_path / "pt.png")
    img, meta = simulate_tem_from_atoms(
        pt13, output_file=out, view_axes=rotate("10x,0y,0z"),
        image_size=64, wave_resolution=64, sampling=0.15)
    assert np.isfinite(img).all()
    assert 0.0 <= img.min() and img.max() <= 1.0
    assert (tmp_path / "pt.png").exists() and (tmp_path / "pt.json").exists()


@pytest.mark.slow
def test_anti_tiling_finite_particle(pt13, monkeypatch):
    """HARD GATE: finite Pt stays in one box with a featureless vacuum border;
    a forced skew calculation box must be rejected before Potential creation."""
    import abtem
    from abtem_tem_backend import simulate_tem_from_atoms
    from ase.utils import rotate
    before = pt13.copy()
    kw = dict(view_axes=rotate("20x,15y,0z"), image_size=200, wave_resolution=200,
              sampling=0.12, dose=1e6)
    img_finite, meta = simulate_tem_from_atoms(pt13, rotate_cell=False, **kw)
    s_fin = _border_std(img_finite)
    assert s_fin < 0.03, f"finite border std {s_fin:.4f} too high (tiling?)"
    assert meta['preparation']['potential_periodic'] is False
    assert meta['preparation']['pbc'] == [False, False, False]
    assert meta['preparation']['prepared_atom_count'] == len(pt13)
    monkeypatch.setattr(abtem, 'Potential', lambda *a, **k: pytest.fail('unsafe Potential created'))
    with pytest.raises(ValueError, match='axis-aligned calculation box'):
        simulate_tem_from_atoms(pt13, rotate_cell=True, **kw)
    for key in before.arrays:
        np.testing.assert_array_equal(pt13.arrays[key], before.arrays[key])
    np.testing.assert_array_equal(pt13.cell, before.cell)
    np.testing.assert_array_equal(pt13.pbc, [False, False, False])
    assert pt13.info == before.info


@pytest.mark.slow
def test_diffraction_structure_factor_si(si_thick):
    """HARD GATE: Si [001] diffraction must obey diamond selection rules —
    (200),(020),(110) forbidden; (220),(400) allowed — on the raw diffraction
    intensities (same abTEM path the tool uses)."""
    import abtem
    wave = abtem.PlaneWave(energy=200e3, sampling=0.09)
    pot = abtem.Potential(atoms=si_thick, gpts=192)
    dp = wave.multislice(pot).diffraction_patterns(max_angle=None)
    dp = dp.compute() if hasattr(dp, "compute") else dp
    arr = np.asarray(dp.array, float)
    # reciprocal sampling = 1/a (one in-plane unit cell) -> integer Miller pixels
    assert np.allclose(np.array(dp.sampling), 1.0 / SI_A, rtol=0.02)
    cy, cx = np.unravel_index(int(np.argmax(arr)), arr.shape)
    I0 = arr[cy, cx]

    def I(h, k):
        return arr[cy + h, cx + k] / I0

    forbidden = max(I(2, 0), I(0, 2), I(1, 1))
    allowed = min(I(2, 2), I(4, 0))
    assert allowed > 1e-3, f"allowed reflection too weak: {allowed:.2e}"
    assert allowed > 50 * forbidden, (
        f"structure-factor violation: allowed {allowed:.2e} vs forbidden "
        f"{forbidden:.2e}")


@pytest.mark.slow
def test_dose_poisson_sqrt_n():
    """HARD GATE: shot noise follows Poisson statistics (var≈mean) and SNR
    scales as √dose."""
    from abtem_tem_backend import poisson_noise

    class M:  # minimal measurement stand-in
        sampling = (0.1, 0.1)
        array = np.ones((96, 96), float)

    rng = np.random.default_rng(0)
    d1 = poisson_noise(M(), 1e5, rng)
    d4 = poisson_noise(M(), 4e5, rng)
    # Poisson: variance ≈ mean
    assert abs(d1.var() / d1.mean() - 1.0) < 0.1
    rel1 = d1.std() / d1.mean()
    rel4 = d4.std() / d4.mean()
    # 4× dose -> half the relative noise
    assert 0.45 < rel4 / rel1 < 0.55, f"ratio {rel4/rel1:.3f} (expect ~0.5)"


@pytest.mark.slow
@pytest.mark.parametrize("slab", ["graphene_slab", "mos2_slab"])
def test_2d_slab_image_and_diffraction(slab, request, tmp_path):
    from abtem_tem_backend import (simulate_tem_from_atoms,
                                   simulate_diffraction_from_atoms)
    atoms = request.getfixturevalue(slab)
    axes = np.eye(3)
    img, meta = simulate_tem_from_atoms(
        atoms, output_file=str(tmp_path / "s.png"),
        view_axes=axes,
        image_size=64, wave_resolution=64, sampling=0.12)
    assert np.isfinite(img).all()
    assert meta["rotate_cell"] is True  # 2D slab -> periodic auto
    d, dm = simulate_diffraction_from_atoms(
        atoms, view_axes=axes, voltage=200e3, sampling=0.12,
        wave_resolution=96, image_size=96)
    assert np.isfinite(d).all() and dm["mode"] == "diffraction"
