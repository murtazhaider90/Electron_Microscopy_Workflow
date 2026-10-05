"""Backward-compatibility shim.

The 2D-materials database code moved to :mod:`abtem_ase_workbench.database_2d`
in v1.3. This shim aliases both names to the same module object.
"""
import sys as _sys
from abtem_ase_workbench import database_2d as _db

_sys.modules[__name__] = _db
