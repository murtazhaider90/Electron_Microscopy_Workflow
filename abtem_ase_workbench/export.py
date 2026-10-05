"""Reproducibility helpers: a standalone Python script that reproduces the
current simulation configuration, and other export-only utilities.

No Tk — the GUI collects the parameters and calls these.
"""


SCRIPT_TEMPLATE = '''"""Reproduce the current Workbench TEM image with abTEM + ASE.
Load your structure into `atoms` (e.g. ase.io.read(...)).
"""
from abtem_tem_backend import simulate_tem_from_atoms
# atoms = ase.io.read("your_structure.cif")

img, meta = simulate_tem_from_atoms(
    atoms,
    output_file="reproduced.png",
    rotate_cell={rc},
    pre_rotation={rot},  # legacy fallback; ignored when view_axes is not None
    view_axes={view_axes},
    voltage={volt},
    defocus={defocus},
    sampling={sampling},
    dose={dose},
    image_size={isize},
    wave_resolution={wres},
    Cs={cs}, C5={c5},
    astigmatism={ast}, astigmatism_angle={asta},
    coma={coma}, coma_angle={comaa},
    focal_spread={fs}, angular_spread={angs},
)
'''


def build_repro_script(params):
    """Return a standalone Python script string for the given ``params`` dict.

    Expected keys match the GUI field names: view_axes, rot, rc, volt, defocus, sampling,
    dose, isize, wres, cs, c5, ast, asta, coma, comaa, fs, angs. Missing keys
    default to zero/sensible values so a partial dict still produces a valid
    file (the user then edits before running it).
    """
    defaults = dict(view_axes=None, rot=(0.0, 0.0, 0.0), rc=None,
                    volt=80000.0, defocus=-3.0,
                    sampling=0.05, dose=50000.0, isize=512, wres=512,
                    cs=0.0, c5=0.0, ast=0.5, asta=0.0, coma=5.0, comaa=0.0,
                    fs=8.0, angs=1.2e-3)
    defaults.update(params or {})
    return SCRIPT_TEMPLATE.format(**defaults)


__all__ = ["build_repro_script", "SCRIPT_TEMPLATE"]
