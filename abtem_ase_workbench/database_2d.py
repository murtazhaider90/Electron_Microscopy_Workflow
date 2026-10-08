"""abtem_2d_database.py -- import real 2D-material structures for the ASE GUI
abTEM tool.

Front-end-agnostic (no Tk / no Qt). Turns downloaded database files into a list
of light-weight ``Entry`` objects that yield ASE ``Atoms`` on demand.

Phase 1 supports:
  * local structure files (CIF / POSCAR / CONTCAR / VASP / XYZ / extxyz / ...)
    via ``ase.io.read``,
  * 2DMatPedia-style JSON / JSONL (each record carries a pymatgen-style
    ``structure`` dict), parsed WITHOUT requiring pymatgen,
  * C2DB-style folders of downloaded structure files (indexed with ase.read).

pymatgen is optional: the standard pymatgen ``structure`` dict (lattice.matrix +
sites with abc/xyz) is parsed directly. Only if that manual parse fails do we
fall back to pymatgen, and if pymatgen is missing we raise ``PymatgenRequired``
with a clear message instead of crashing.
"""

import os
import re
import glob
import json

from ase import Atoms
from ase.io import read as ase_read

try:
    from pymatgen.core import Structure as _PmgStructure
    from pymatgen.io.ase import AseAtomsAdaptor as _AseAdaptor
    HAVE_PYMATGEN = True
except Exception:
    HAVE_PYMATGEN = False


class PymatgenRequired(Exception):
    """Raised when an entry can only be parsed with pymatgen installed."""


class Entry:
    """A single searchable database record."""

    def __init__(self, id=None, formula=None, name=None, metadata=None,
                 atoms=None, raw_structure=None, source=None, path=None):
        self.id = id
        self.formula = formula
        self.name = name
        self.metadata = metadata or {}
        self.source = source
        self.path = path
        self._atoms = atoms
        self._raw_structure = raw_structure

    def to_atoms(self):
        """Return an ASE ``Atoms`` for this entry (built on demand)."""
        if self._atoms is not None:
            return self._atoms
        if self.path is not None:
            return ase_read(self.path)
        if self._raw_structure is not None:
            return structure_dict_to_atoms(self._raw_structure)
        raise ValueError('entry has no structure data')

    def search_text(self):
        return ' '.join(str(x) for x in
                        (self.id, self.formula, self.name, self.source)
                        if x is not None).lower()


# ---------------------------------------------------------------------------
# structure-dict parsing (pymatgen-style, no pymatgen required)
# ---------------------------------------------------------------------------
_ELEMENT_RE = re.compile(r'[A-Z][a-z]?')


def _clean_element(sym):
    """Extract a plain element symbol from things like 'Mo4+', 'S2-', 'Mo'."""
    if sym is None:
        raise ValueError('missing element')
    m = _ELEMENT_RE.match(str(sym))
    if not m:
        raise ValueError('unrecognised element %r' % (sym,))
    return m.group(0)


def _site_element(site):
    sp = site.get('species')
    if isinstance(sp, list) and sp:
        first = sp[0]
        el = (first.get('element') or first.get('specie')
              or first.get('label') or first.get('symbol'))
        return _clean_element(el)
    if isinstance(sp, str):
        return _clean_element(sp)
    return _clean_element(site.get('label') or site.get('element'))


def structure_dict_to_atoms(s):
    """Convert a pymatgen-style structure dict to ASE ``Atoms``.

    Tries a direct manual parse first (no pymatgen needed); falls back to
    pymatgen if available; otherwise raises ``PymatgenRequired``.
    """
    try:
        lattice = s['lattice']['matrix']
        sites = s['sites']
        symbols, scaled, cart = [], [], []
        use_frac = True
        for site in sites:
            symbols.append(_site_element(site))
            if 'abc' in site and site['abc'] is not None:
                scaled.append(site['abc'])
            elif 'xyz' in site and site['xyz'] is not None:
                use_frac = False
                cart.append(site['xyz'])
            else:
                raise KeyError('site has neither abc nor xyz')
        if use_frac:
            return Atoms(symbols=symbols, scaled_positions=scaled,
                         cell=lattice, pbc=True)
        return Atoms(symbols=symbols, positions=cart, cell=lattice, pbc=True)
    except Exception as manual_err:
        if HAVE_PYMATGEN:
            try:
                return _AseAdaptor.get_atoms(_PmgStructure.from_dict(s))
            except Exception as pmg_err:
                raise ValueError('could not parse structure: %s' % (pmg_err,))
        raise PymatgenRequired(
            'This database format requires pymatgen. Install with '
            '`pip install pymatgen`.  (manual parse failed: %s)' % (manual_err,))


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------
def load_local_file(path):
    """Read a single local structure file into ASE ``Atoms``."""
    return ase_read(path)


def _read_json_or_jsonl(path):
    """Return a list of dict records from a JSON or JSON-lines file."""
    with open(path, 'r') as fh:
        text = fh.read()
    text_stripped = text.lstrip()
    # Try a single JSON document first.
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # dict-of-records (id -> record) or a single record
            if 'structure' in obj or 'sites' in obj:
                return [obj]
            vals = list(obj.values())
            if vals and all(isinstance(v, dict) for v in vals):
                return vals
            return [obj]
    except json.JSONDecodeError:
        pass
    # Fall back to JSON-lines.
    records = []
    for line in text.splitlines():
        line = line.strip().rstrip(',')
        if not line or line in '[]':
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


_META_KEYS = ('bandgap', 'band_gap', 'gap', 'decomposition_energy',
              'exfoliation_energy_per_atom', 'energy_per_atom', 'e_above_hull',
              'total_magnetization', 'source', 'source_id', 'discovery_process',
              'stability', 'is_stable')


def _first(d, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def load_2dmatpedia(path):
    """Parse a 2DMatPedia-style JSON/JSONL file into ``Entry`` objects."""
    docs = _read_json_or_jsonl(path)
    entries = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        struct = d.get('structure') or d.get('final_structure')
        sid = _first(d, 'material_id', '2dm_id', 'id', '_id', 'mp_id', 'task_id')
        formula = _first(d, 'formula_pretty', 'pretty_formula', 'formula',
                         'reduced_formula', 'chemical_formula')
        name = _first(d, 'material_name', 'name', 'title')
        meta = {k: d[k] for k in _META_KEYS if k in d and d[k] is not None}
        entries.append(Entry(id=sid, formula=formula, name=name, metadata=meta,
                             raw_structure=struct, source='2dmatpedia_json'))
    return entries


_STRUCT_EXTS = ('*.cif', '*.xyz', '*.extxyz', '*.json', '*.traj', '*.vasp',
                'POSCAR*', 'CONTCAR*', '*.gen', '*.pdb')


def load_c2db_folder(path):
    """Index a folder of downloaded structure files (C2DB-style)."""
    files = []
    for pattern in _STRUCT_EXTS:
        files.extend(glob.glob(os.path.join(path, '**', pattern),
                               recursive=True))
    entries = []
    for f in sorted(set(files)):
        try:
            atoms = ase_read(f)
        except Exception:
            continue
        if isinstance(atoms, list):
            atoms = atoms[-1] if atoms else None
        if atoms is None:
            continue
        entries.append(Entry(id=os.path.basename(f),
                             formula=atoms.get_chemical_formula(),
                             name=os.path.relpath(f, path),
                             atoms=atoms, source='c2db', path=f))
    return entries


def filter_entries(entries, term):
    """Case-insensitive substring filter across id/formula/name/source."""
    term = (term or '').strip().lower()
    if not term:
        return list(entries)
    return [e for e in entries if term in e.search_text()]
