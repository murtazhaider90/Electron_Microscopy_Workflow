"""Backward-compatibility shim.

The GUI code moved to :mod:`abtem_ase_workbench.gui` in v1.3. This shim
aliases to the real GUI module so both `abtem_tem` and
`abtem_ase_workbench.gui` refer to the same module object.
"""
import sys as _sys
from abtem_ase_workbench import gui as _gui

_sys.modules[__name__] = _gui
