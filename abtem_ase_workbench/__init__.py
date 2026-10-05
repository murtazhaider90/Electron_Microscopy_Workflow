"""ASE Electron Microscopy Workbench.

A plugin for ASE GUI that drives abTEM TEM-image and diffraction simulations
with crystallographic orientation controls, a 2D-materials database importer,
and a reproducible-script exporter.

Public API (small on purpose):

    from abtem_ase_workbench import simulate_tem_from_atoms, apply_view_rotation
    from abtem_ase_workbench.backend import simulate_diffraction_from_atoms
    from abtem_ase_workbench.orientation import (
        set_view_axes, nearest_zone_axis,
    )
    from abtem_ase_workbench import database_2d  # 2DMatPedia / C2DB / local
    from abtem_ase_workbench.launcher import main, register_tool

The ``ABTEMSimulation`` GUI class lives in ``abtem_ase_workbench.gui`` and
needs Tkinter; the other submodules do not.
"""
from .backend import (
    simulate_tem_from_atoms,
    simulate_diffraction_from_atoms,
    apply_view_rotation,
    apply_xyz_rotation,
    abtem_array_to_ase_screen,
    resolve_rotate_cell,
    rotation_mode_name,
    HAVE_ABTEM,
    ABTEM_VERSION,
    ASE_VERSION,
)

__version__ = "1.4.0"

__all__ = [
    "simulate_tem_from_atoms",
    "simulate_diffraction_from_atoms",
    "apply_view_rotation",
    "apply_xyz_rotation",
    "abtem_array_to_ase_screen",
    "resolve_rotate_cell",
    "rotation_mode_name",
    "HAVE_ABTEM",
    "ABTEM_VERSION",
    "ASE_VERSION",
    "__version__",
]
