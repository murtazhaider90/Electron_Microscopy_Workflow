"""2D-materials database parser gates (no abTEM, no pymatgen)."""
import json
import numpy as np
import pytest

import abtem_2d_database as db

_REC = {
    "material_id": "2dm-1", "formula_pretty": "MoS2",
    "material_name": "molybdenum disulfide", "bandgap": 1.6,
    "exfoliation_energy_per_atom": 0.03,
    "structure": {"lattice": {"matrix": [[3.16, 0, 0], [-1.58, 2.73, 0],
                                         [0, 0, 18.0]]},
                  "sites": [
                      {"species": [{"element": "Mo", "occu": 1}],
                       "abc": [0.0, 0.0, 0.5]},
                      {"species": [{"element": "S", "occu": 1}],
                       "abc": [0.3333, 0.6667, 0.43]},
                      {"species": [{"element": "S", "occu": 1}],
                       "abc": [0.3333, 0.6667, 0.57]}]}}


def _write_jsonl(tmp_path):
    p = tmp_path / "db.jsonl"
    rec2 = dict(_REC, material_id="2dm-2", formula_pretty="WSe2",
                material_name="tungsten diselenide")
    p.write_text(json.dumps(_REC) + "\n" + json.dumps(rec2) + "\n")
    return str(p)


def test_parse_jsonl(tmp_path):
    entries = db.load_2dmatpedia(_write_jsonl(tmp_path))
    assert len(entries) == 2
    assert {e.formula for e in entries} == {"MoS2", "WSe2"}
    assert entries[0].metadata.get("bandgap") == 1.6


def test_structure_dict_without_pymatgen():
    atoms = db.structure_dict_to_atoms(_REC["structure"])
    assert atoms.get_chemical_formula() == "MoS2"
    assert np.isclose(atoms.cell[2, 2], 18.0)


def test_clean_charged_label():
    assert db._clean_element("Mo4+") == "Mo"
    assert db._clean_element("S2-") == "S"
    assert db._clean_element("Se") == "Se"


def test_search_filter(tmp_path):
    entries = db.load_2dmatpedia(_write_jsonl(tmp_path))
    assert len(db.filter_entries(entries, "WSe2")) == 1
    assert len(db.filter_entries(entries, "")) == 2
    assert len(db.filter_entries(entries, "nonsense")) == 0


def test_unsupported_format_raises():
    with pytest.raises(db.PymatgenRequired):
        db.structure_dict_to_atoms({"not": "a structure"})
