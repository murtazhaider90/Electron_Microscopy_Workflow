"""Shared fixtures, markers and skip logic for the workbench test suite.

Fast tests (orientation math, rotation policy, metadata schema, 2D parser,
local import, error handling) run everywhere with no network and no abTEM.

Physics tests are marked ``slow`` (need abTEM) and GUI tests ``gui`` (need a
display / Xvfb); both are skipped unless the corresponding flag is given:

    pytest                         # fast tests only
    pytest --run-slow              # + abTEM physics gates
    pytest --run-slow --run-gui    # + GUI smoke tests (use xvfb-run)
"""
import os
import sys

import numpy as np
import pytest

# Make the flat package modules importable (tests/ sits inside the package).
_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

try:
    import abtem  # noqa: F401
    HAVE_ABTEM = True
except Exception:
    HAVE_ABTEM = False

# Register the Workbench on the ASE GUI class ONCE for the session, so the
# GUI tests work whether or not install.py has patched ase.gui.gui.py. This is
# the same mechanism the ``abtem-ase-gui`` console command uses.
try:
    from abtem_ase_workbench.launcher import register_tool as _register_tool
    _register_tool()
except Exception:
    pass


def pytest_addoption(parser):
    parser.addoption("--run-slow", action="store_true", default=False,
                     help="run abTEM physics tests (slow)")
    parser.addoption("--run-gui", action="store_true", default=False,
                     help="run Tk GUI smoke tests (need a display / Xvfb)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: abTEM physics tests")
    config.addinivalue_line("markers", "gui: Tk GUI smoke tests")


def pytest_collection_modifyitems(config, items):
    run_slow = config.getoption("--run-slow")
    run_gui = config.getoption("--run-gui")
    skip_slow = pytest.mark.skip(reason="need --run-slow")
    skip_noabtem = pytest.mark.skip(reason="abTEM not installed")
    skip_gui = pytest.mark.skip(reason="need --run-gui")
    for item in items:
        if "slow" in item.keywords:
            if not run_slow:
                item.add_marker(skip_slow)
            elif not HAVE_ABTEM:
                item.add_marker(skip_noabtem)
        if "gui" in item.keywords and not run_gui:
            item.add_marker(skip_gui)


# ----------------------------------------------------------------- structures
@pytest.fixture
def pt13():
    """A — finite Pt13 nanoparticle in vacuum, pbc [F,F,F]."""
    from ase.cluster import Icosahedron
    a = Icosahedron("Pt", noshells=2)
    a.center(vacuum=6.0)
    return a


@pytest.fixture
def si_bulk():
    """B — periodic Si diamond conventional cell, pbc [T,T,T]."""
    from ase.build import bulk
    return bulk("Si", "diamond", a=5.43, cubic=True)


@pytest.fixture
def si_thick():
    """B' — Si with thickness along z for diffraction (still one in-plane cell)."""
    from ase.build import bulk
    return bulk("Si", "diamond", a=5.43, cubic=True) * (1, 1, 6)


@pytest.fixture
def graphene_slab():
    """C — graphene 2D slab, pbc [T,T,F], vacuum in z."""
    from ase.build import graphene
    a = graphene()
    a.center(vacuum=8.0, axis=2)
    a.set_pbc([True, True, False])
    return a


@pytest.fixture
def mos2_slab():
    """C — MoS2 2D slab, pbc [T,T,F]."""
    from ase.build import mx2
    a = mx2(formula="MoS2", kind="2H", a=3.18, thickness=3.19, vacuum=8.0)
    a.set_pbc([True, True, False])
    return a


SI_A = 5.43  # Å, used by the diffraction structure-factor gate
