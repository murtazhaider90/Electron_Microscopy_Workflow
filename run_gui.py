#!/usr/bin/env python3
"""Zero-touch launcher — thin wrapper over :func:`abtem_ase_workbench.launcher.main`.

Starts ASE GUI with the Workbench tool registered on the GUI class, without
editing your ASE install. All `ase gui` arguments pass straight through:

    python run_gui.py                   # empty ASE GUI
    python run_gui.py structure.cif     # open a file
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from abtem_ase_workbench.launcher import main, register_tool  # noqa: E402,F401


if __name__ == "__main__":
    main()
