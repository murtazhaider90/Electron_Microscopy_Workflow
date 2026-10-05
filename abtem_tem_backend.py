"""Backward-compatibility shim.

The backend code moved to :mod:`abtem_ase_workbench.backend` in v1.3. To
preserve the old import path AND let callers monkey-patch module globals
(`abtem_tem_backend.HAVE_ABTEM = False` must affect
`simulate_tem_from_atoms`), this shim registers itself as an alias for the
real backend module, so both names refer to the same module object.
"""
import sys as _sys
from abtem_ase_workbench import backend as _backend

_sys.modules[__name__] = _backend
