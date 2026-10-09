"""Metadata schema + value-consistency gates (needs abTEM for a real run)."""
import json
import numpy as np
import pytest


@pytest.mark.slow
def test_image_metadata_schema(si_bulk, tmp_path):
    from abtem_tem_backend import simulate_tem_from_atoms
    out = str(tmp_path / "img.png")
    axes = np.eye(3)
    img, meta = simulate_tem_from_atoms(
        si_bulk, output_file=out, view_axes=axes,
        image_size=48, wave_resolution=48, sampling=0.18,
        extra_metadata={
            "orientation_source": "zone_axis", "zone_axis_uvw": [0, 0, 1],
            "plane_hkl": None, "nearest_zone_axis": [0, 0, 1],
            "structure_source": "local_file", "structure_database_id": "x",
            "structure_formula": "Si8", "structure_pbc": [True, True, True]})
    required = ["rotation_mode", "rotate_cell", "xyz_rotation",
                "ase_view_axes", "orientation_transform", "image_presentation",
                "accelerating_voltage", "defocus", "sampling",
                "image_size", "wave_resolution", "ctf_parameters", "electron_dose",
                "output_image", "abtem_version", "ase_version",
                "orientation_source", "zone_axis_uvw", "plane_hkl",
                "nearest_zone_axis", "structure_source",
                "structure_database_id", "structure_formula", "structure_pbc"]
    for k in required:
        assert k in meta, f"missing metadata key: {k}"
    # consistency
    assert meta["rotate_cell"] is True and meta["rotation_mode"] == "periodic_crystal"
    assert meta["xyz_rotation"] is None
    assert meta["orientation_transform"] == "ase_view_matrix"
    assert meta["image_presentation"] == "ase_gui_screen"
    assert np.allclose(np.asarray(meta["ase_view_axes"]), axes)
    # JSON sidecar written and matches
    disk = json.load(open(str(tmp_path / "img.json")))
    assert disk["structure_source"] == "local_file"
    assert np.isfinite(img).all() and 0.0 <= img.min() and img.max() <= 1.0


@pytest.mark.slow
def test_diffraction_metadata_mode(si_thick, tmp_path):
    from abtem_tem_backend import simulate_diffraction_from_atoms
    out = str(tmp_path / "diff.png")
    img, meta = simulate_diffraction_from_atoms(
        si_thick, output_file=out, voltage=200e3, sampling=0.12,
        wave_resolution=96, image_size=96, log_scale=True)
    assert meta["mode"] == "diffraction"
    for k in ["max_angle_mrad", "block_direct", "log_scale", "rotate_cell",
              "rotation_mode", "sampling", "wave_resolution"]:
        assert k in meta
    assert (tmp_path / "diff.json").exists()
    assert np.isfinite(img).all()


@pytest.mark.slow
def test_metadata_unsupported_orientation_rejected(si_bulk, monkeypatch):
    import abtem
    from abtem_tem_backend import simulate_tem_from_atoms
    from ase.utils import rotate
    before = si_bulk.copy()
    monkeypatch.setattr(abtem, 'Potential', lambda *a, **k: pytest.fail('unsafe Potential created'))
    with pytest.raises(ValueError, match='not exactly representable'):
        simulate_tem_from_atoms(si_bulk, view_axes=rotate('10x,5y,0z'),
                                image_size=48, wave_resolution=48, sampling=.18)
    for key in before.arrays:
        np.testing.assert_array_equal(si_bulk.arrays[key], before.arrays[key])
    np.testing.assert_array_equal(si_bulk.cell, before.cell)
    np.testing.assert_array_equal(si_bulk.pbc, before.pbc)
    assert si_bulk.info == before.info
