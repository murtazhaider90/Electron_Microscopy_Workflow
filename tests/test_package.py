"""Phase-3 refactor gates: the new package API is reachable, and the
backward-compat shims resolve to the SAME module object as the real package
module (so monkey-patches and attribute writes are shared)."""
import sys

import pytest


def test_package_imports():
    import abtem_ase_workbench as w
    for name in ("simulate_tem_from_atoms", "simulate_diffraction_from_atoms",
                 "apply_view_rotation", "apply_xyz_rotation",
                 "abtem_array_to_ase_screen", "HAVE_ABTEM", "__version__"):
        assert hasattr(w, name), name


def test_pure_submodules_have_no_tk(tmp_path):
    """orientation / validators / presets / export / backend / database_2d do
    not import tkinter at module-load time.

    Runs in a fresh subprocess so this check cannot corrupt the parent's
    ``sys.modules`` and influence other tests.
    """
    import subprocess
    import textwrap
    script = textwrap.dedent("""
        import sys
        for mod in ("abtem_ase_workbench.orientation",
                    "abtem_ase_workbench.validators",
                    "abtem_ase_workbench.presets",
                    "abtem_ase_workbench.export",
                    "abtem_ase_workbench.backend",
                    "abtem_ase_workbench.database_2d"):
            __import__(mod)
        tk = [m for m in sys.modules
              if m == "tkinter" or m.startswith("tkinter.")]
        print("TK:" + repr(tk))
    """)
    f = tmp_path / "probe.py"
    f.write_text(script)
    env = dict(**__import__("os").environ)
    out = subprocess.check_output([sys.executable, str(f)], env=env,
                                  cwd=str(f.parent))
    line = out.decode().strip().splitlines()[-1]
    assert line == "TK:[]", line


def test_backend_shim_shares_module():
    import abtem_tem_backend
    from abtem_ase_workbench import backend
    assert abtem_tem_backend is backend


def test_database_shim_shares_module():
    import abtem_2d_database
    from abtem_ase_workbench import database_2d
    assert abtem_2d_database is database_2d


def test_gui_shim_shares_module():
    import abtem_tem
    from abtem_ase_workbench import gui
    assert abtem_tem is gui


def test_orientation_pure_functions():
    import numpy as np
    from abtem_ase_workbench.orientation import (set_view_axes,
                                                 nearest_zone_axis,
                                                 zone_axis_direction)
    from ase.build import bulk
    cell = bulk("Si", "diamond", a=5.43, cubic=True).cell.array
    axes = set_view_axes(zone_axis_direction((1, 1, 0), cell))
    assert np.isclose(np.linalg.det(axes), 1.0)
    best, ang = nearest_zone_axis(axes[:, 2] * 2.0, cell, max_index=4)
    assert best == (1, 1, 0) and ang < 1e-3


def test_validators_pure_function():
    from abtem_ase_workbench.validators import validate_run
    from ase.build import bulk
    atoms = bulk("Si", "diamond", a=5.43, cubic=True)
    hard, soft = validate_run(atoms, kind="image", have_abtem=True,
                              rotate_cell_effective=True,
                              image_size=4096, wave_resolution=4096,
                              sampling=0.1, sweep_total=0)
    assert not hard
    assert any("Large grid" in s for s in soft)
    hard2, _ = validate_run(None, kind="image", have_abtem=True,
                            rotate_cell_effective=False, image_size=64,
                            wave_resolution=64, sampling=0.1, sweep_total=0)
    assert any("No structure" in h for h in hard2)


def test_presets_lookup():
    from abtem_ase_workbench.presets import get_preset
    assert get_preset("hr300")["voltage"] == 300.0
    assert get_preset("none") is None


def test_export_script_contains_call():
    from abtem_ase_workbench.export import build_repro_script
    axes = [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]
    s = build_repro_script(dict(view_axes=axes, volt=200000.0))
    assert "simulate_tem_from_atoms" in s and "view_axes=" in s
    assert repr(axes) in s
    legacy = build_repro_script(dict(rot=(10.0, 0.0, 0.0)))
    assert "pre_rotation=(10.0, 0.0, 0.0)" in legacy
    assert "view_axes=None" in legacy
