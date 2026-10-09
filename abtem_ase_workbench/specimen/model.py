"""ASE editing and orthographic view contract, independent of any GUI/physics."""
from copy import deepcopy
from itertools import product

import numpy as np
from ase import Atom, Atoms
from ase.data import atomic_numbers
from ase import build, io
from ase.cluster import Icosahedron, Decahedron, Octahedron
from ase.neighborlist import natural_cutoffs, neighbor_list
from ..orientation import set_view_axes, zone_axis_direction, plane_normal_direction


def element_number(symbol):
    if symbol not in atomic_numbers:
        raise ValueError("Enter a valid element symbol, for example C, Si or Au.")
    return atomic_numbers[symbol]


def validated_axes(value):
    a = np.asarray(value, dtype=float)
    if (a.shape != (3, 3) or not np.isfinite(a).all()
            or not np.allclose(a.T @ a, np.eye(3), atol=1e-10, rtol=0)
            or not np.isclose(np.linalg.det(a), 1, atol=1e-10, rtol=0)):
        raise ValueError("View matrix must be a finite right-handed orthonormal 3×3 matrix.")
    return a.copy()


class View:
    """Columns are screen right/up/beam. Row positions project as positions @ axes.

    Pan, scale and pivot affect presentation only, never simulation orientation.
    """
    def __init__(self):
        self._axes = np.eye(3)
        self.pivot = np.zeros(3)
        self.pan = np.zeros(2)
        self.scale = 40.0  # logical pixels / Å

    @property
    def axes(self):
        return self._axes.copy()

    def set_axes(self, value):
        self._axes = validated_axes(value)

    def rotate(self, dx, dy):
        # Rodrigues rotation in screen coordinates; no Euler extraction.
        vector = np.array([dy, dx, 0.0], dtype=float)
        angle = np.linalg.norm(vector)
        if not np.isfinite(angle):
            raise ValueError("Rotation must be finite.")
        if angle == 0:
            return
        x, y, z = vector / angle
        k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        r = np.eye(3) + np.sin(angle)*k + (1-np.cos(angle))*(k @ k)
        # Re-orthogonalize drift while retaining the canonical matrix itself.
        u, _, vt = np.linalg.svd(self._axes @ r)
        self.set_axes(u @ vt)

    def project(self, positions, size):
        q = (np.asarray(positions) - self.pivot) @ self._axes
        pixels = q[:, :2] * [self.scale, -self.scale]
        return pixels + np.asarray(size)/2 + self.pan, q[:, 2]

    def fit(self, atoms, size):
        self.pivot = atoms.positions.mean(axis=0) if len(atoms) else np.zeros(3)
        self.pan[:] = 0
        q = (atoms.positions - self.pivot) @ self._axes
        extent = np.ptp(q[:, :2], axis=0) + 3 if len(atoms) else np.ones(2)*3
        self.scale = float(np.min(np.asarray(size)*0.8/extent))

    def pick(self, positions, size, pixel, radius=12):
        xy, z = self.project(positions, size)
        candidates = np.flatnonzero(np.linalg.norm(xy-np.asarray(pixel), axis=1) <= radius)
        # Positive beam depth is nearest the observer in this display convention.
        return int(candidates[np.argmax(z[candidates])]) if len(candidates) else None


class Specimen:
    """Transactional snapshots of ASE Atoms, selection and exact view matrix.

    Public atoms are defensive copies. Failed operations never change state or
    history. Observers are called after successful commits/undo/redo.
    """
    def __init__(self, atoms=None, history_limit=100):
        self._atoms = deepcopy(atoms if atoms is not None else Atoms())
        self.selection = set()
        self.view = View()
        if not isinstance(history_limit, int) or history_limit < 1:
            raise ValueError("History limit must be a positive integer.")
        self.history_limit = history_limit
        self.revision = 0
        self._undo, self._redo = [], []
        self.observers = []

    @property
    def atoms(self):
        return deepcopy(self._atoms)

    def _snapshot(self):
        return deepcopy(self._atoms), set(self.selection), self.view.axes

    def notify(self):
        for callback in tuple(self.observers):
            callback()

    def edit(self, label, operation):
        before = self._snapshot()
        candidate = deepcopy(self._atoms)
        result = operation(candidate)
        if result is not None:
            candidate = result
        if (not isinstance(candidate, Atoms) or not np.isfinite(candidate.positions).all()
                or not np.isfinite(candidate.cell.array).all()):
            raise ValueError("Structure must contain finite ASE atom positions.")
        self._atoms = candidate
        self.revision += 1
        self.selection = {i for i in self.selection if i < len(candidate)}
        self._undo.append((label, before))
        self._undo = self._undo[-self.history_limit:]
        self._redo.clear()
        self.notify()

    def _restore(self, source, destination):
        if not source:
            return False
        label, snapshot = source.pop()
        destination.append((label, self._snapshot()))
        self._atoms, self.selection, axes = snapshot
        self.revision += 1
        self.view.set_axes(axes)
        self.notify()
        return True

    def undo(self):
        return self._restore(self._undo, self._redo)

    def redo(self):
        return self._restore(self._redo, self._undo)

    def orient(self, axes):
        axes = validated_axes(axes)
        self._undo.append(("Orient", self._snapshot()))
        self._undo = self._undo[-self.history_limit:]
        self._redo.clear()
        self.view.set_axes(axes)
        self.notify()

    def zone_axis(self, uvw):
        self.orient(set_view_axes(zone_axis_direction(uvw, self._atoms.cell)))

    def plane_normal(self, hkl):
        if self._atoms.cell.rank != 3:
            raise ValueError("Plane normals require a full-rank cell.")
        self.orient(set_view_axes(plane_normal_direction(hkl, self._atoms.cell.reciprocal())))

    def select(self, indices):
        indices = set(int(i) for i in indices)
        if any(i < 0 or i >= len(self._atoms) for i in indices):
            raise ValueError("Atom index outside structure.")
        self.selection = indices
        self.notify()

    def add(self, symbol, position):
        number = element_number(symbol)
        self.edit("Add atom", lambda a: a.append(Atom(number, position)))

    def delete(self):
        indices = sorted(self.selection)
        def remove(a):
            del a[indices]
        self.edit("Delete atoms", remove)
        self.selection.clear()
        self.notify()

    def move(self, displacement):
        indices = sorted(self.selection)
        def move(a):
            a.positions[indices] += np.asarray(displacement, dtype=float)
        self.edit("Move atoms", move)

    def change(self, symbol):
        indices = sorted(self.selection)
        number = element_number(symbol)
        def change(a):
            a.numbers[indices] = number
        self.edit("Change element", change)

    def set_cell(self, cell, scale_atoms=False):
        self.edit("Cell", lambda a: a.set_cell(cell, scale_atoms=scale_atoms))

    def set_pbc(self, pbc):
        self.edit("Periodicity", lambda a: a.set_pbc(pbc))

    def repeat(self, repeats):
        r = np.asarray(repeats)
        if r.shape != (3,) or np.any(r < 1) or np.any(r != r.astype(int)):
            raise ValueError("Repeat counts must be three positive integers.")
        self.edit("Repeat", lambda a: a.repeat(r.astype(int)))

    def supercell(self, matrix):
        p = np.asarray(matrix)
        if p.shape != (3, 3) or not np.isfinite(p).all() or np.any(p != np.rint(p)) or abs(np.linalg.det(p)) < 0.5:
            raise ValueError("Supercell matrix must be nonsingular integer 3×3.")
        self.edit("Supercell", lambda a: build.make_supercell(a, p.astype(int)))

    def wrap(self):
        self.edit("Wrap", lambda a: a.wrap())

    def center(self, vacuum=None, axis=(0, 1, 2)):
        if vacuum is not None and (not np.isfinite(vacuum) or vacuum < 0):
            raise ValueError("Vacuum must be a nonnegative distance in Å.")
        self.edit("Center", lambda a: a.center(vacuum=vacuum, axis=axis))

    def replace(self, atoms):
        self.edit("Replace specimen", lambda a: deepcopy(atoms))
        self.select([])

    def open(self, path, index=-1):
        atoms = io.read(path, index=index)
        axes = atoms.info.get("specimen_view_axes")
        if axes is not None:
            axes = validated_axes(axes)
        self.replace(atoms)
        if axes is not None:
            self.view.set_axes(axes)
            self.notify()

    def save(self, path, **kwargs):
        a = self.atoms
        a.info["specimen_view_axes"] = self.view.axes.tolist()
        io.write(path, a, **kwargs)

    def backend_inputs(self):
        """Pass directly as **kwargs to existing simulate_*_from_atoms APIs."""
        return {"atoms": self.atoms, "view_axes": self.view.axes}

    def geometry(self, bonds=True, cell=True):
        """World coordinates for display only; periodic bond images use ASE offsets."""
        a = self._atoms
        segments = []
        if bonds and len(a):
            i, j, shifts = neighbor_list('ijS', a, natural_cutoffs(a, mult=1.15))
            for start, end, shift in zip(i, j, shifts):
                if start < end or (start == end and tuple(shift) > (0, 0, 0)):
                    segments.extend([a.positions[start], a.positions[end] + shift @ a.cell.array])
        edges = []
        if cell:
            for corner in product((0, 1), repeat=3):
                for axis in range(3):
                    if corner[axis] == 0:
                        other = list(corner)
                        other[axis] = 1
                        edges.extend([np.asarray(corner) @ a.cell.array, np.asarray(other) @ a.cell.array])
        return np.asarray(segments).reshape(-1, 3), np.asarray(edges).reshape(-1, 3)


def build_specimen(kind, **parameters):
    """Explicit ASE builder registry, no Python evaluation or physics duplication."""
    builders = {"bulk": build.bulk, "surface": build.surface,
                "fcc111": build.fcc111, "bcc110": build.bcc110,
                "hcp0001": build.hcp0001, "graphene": build.graphene,
                "mx2": build.mx2, "nanotube": build.nanotube,
                "icosahedron": Icosahedron, "decahedron": Decahedron,
                "octahedron": Octahedron}
    if kind not in builders:
        raise ValueError("Unknown ASE builder.")
    return builders[kind](**parameters)
