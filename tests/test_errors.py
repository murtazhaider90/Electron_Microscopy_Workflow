"""Graceful error handling gates."""
import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk

import abtem_tem_backend as be


def test_abtem_missing_message(monkeypatch):
    """No abTEM -> clear RuntimeError, not an obscure import error."""
    monkeypatch.setattr(be, "HAVE_ABTEM", False)
    with pytest.raises(RuntimeError) as e:
        be.simulate_tem_from_atoms(bulk("Si", "diamond", a=5.43, cubic=True))
    assert "abtem" in str(e.value).lower()
    with pytest.raises(RuntimeError):
        be.simulate_diffraction_from_atoms(bulk("Si", "diamond", a=5.43,
                                                cubic=True))


@pytest.mark.slow
def test_empty_atoms_raises():
    with pytest.raises(ValueError):
        be.simulate_tem_from_atoms(Atoms())
    with pytest.raises(ValueError):
        be.simulate_diffraction_from_atoms(Atoms())
