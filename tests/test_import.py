"""Local structure import gates (no abTEM)."""
import pytest
from ase.build import bulk, graphene
from ase.io import write

import abtem_2d_database as db


@pytest.mark.parametrize("fmt,ext", [("extxyz", ".extxyz"),
                                     ("vasp", ".vasp")])
def test_local_import_roundtrip(fmt, ext, tmp_path):
    atoms = bulk("Si", "diamond", a=5.43, cubic=True)
    p = tmp_path / ("Si" + ext)
    write(str(p), atoms, format=fmt)
    loaded = db.load_local_file(str(p))
    assert loaded.get_chemical_formula() == "Si8"


def test_local_import_cif(tmp_path):
    atoms = graphene()
    p = tmp_path / "gr.cif"
    try:
        write(str(p), atoms, format="cif")
    except Exception:
        pytest.skip("CIF writer unavailable")
    loaded = db.load_local_file(str(p))
    assert len(loaded) == len(atoms)


def test_invalid_path_errors():
    with pytest.raises(Exception):
        db.load_local_file("/no/such/file.xyz")
