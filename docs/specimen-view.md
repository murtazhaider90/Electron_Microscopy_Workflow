# Specimen subsystem

## Renderer decision

Use VisPy with its PySide6 backend. VisPy provides a Qt-native canvas, GPU
marker and line buffers, orthographic scientific rendering, and explicit
transforms without requiring a camera represented by Euler angles. The prototype
was exercised with PySide6 6.12 / VisPy 0.17 under Xvfb and Mesa software OpenGL;
an actual framebuffer test locates asymmetric atoms at backend-predicted pixels.
This is a suitability evaluation, not a claim of measured million-atom performance.

VTK (and PyVistaQt) is a mature alternative with richer mesh pipelines and
hardware picking, but its larger dependency/distribution footprint and additional
camera convention adapter do not solve a missing requirement for atoms, bonds
and cell lines here. Qt3D requires more custom scientific primitives and is not
better supported for this ASE workflow. Nothing demonstrated a clear advantage
over the preferred VisPy renderer, so no renderer substitution is needed.

Atoms are depth-sorted shaded marker glyphs, with line bonds and cell edges. The
orthographic view deliberately avoids perspective foreshortening: the screen
projection matches the beam projection used by abTEM. This is a 3D orientation
viewer, not an independent perspective camera. Drag rotates; Shift-drag or right
button pans; wheel zooms; click selects; Ctrl-click toggles selection. Closest
beam-depth atom wins when projected marker regions overlap. Cell and periodic
bond images come from ASE; neither display operation changes the physical model.

## Install and launch

On Python 3.10 or later (subject to the chosen PySide6 release support):

```sh
pip install -e '.[qt,dev]'
abtem-specimen
```

The specimen editor is a separable prototype for the new application shell.
The current Tk launcher and simulation controls are unchanged. Windows installer
integration, asynchronous simulation dispatch and instrument controls
are outside this subsystem. VisPy needs a working OpenGL context (including a
software Mesa context for CI).

## Canonical scientific contract

`abtem_ase_workbench.specimen` imports only ASE, NumPy and existing pure orientation
helpers. Import `.widget` explicitly to use Qt. `Specimen` owns an ASE `Atoms`;
public reads and backend handoffs are defensive copies, including structure
metadata. It does not reimplement ASE builders, file formats or cell operations.

`model.view.axes` is the exact proper 3×3 rotation matrix, copied on access.
Its columns are screen right, screen up and beam in specimen coordinates:

```python
projected = positions @ model.view.axes
inputs = model.backend_inputs()
# Existing scientific API; no Euler conversion, no changed physics:
image, metadata = simulate_tem_from_atoms(**inputs, ...)
```

Pan, zoom and pivot are separate presentation values. Screen coordinates are:

```
q = (positions - pivot) @ axes
pixel = q[:, :2] * [scale, -scale] + viewport_size / 2 + pan
```

VisPy receives these projected coordinates and a fixed noninteractive pixel
camera. It has no second orientation that could diverge from the backend matrix.
The y inversion converts Cartesian up to screen down and is not a physical
rotation. Drag rotation composes Rodrigues matrices; SVD corrects numerical
orthogonality drift. Neither orientation nor simulation mutates source positions.
The existing backend retains its finite/slab/crystal rotation policy.

## Editing, builders and history

The editor exposes open/save, picking and multiple selection, add/delete,
Cartesian displacement and element changes, cell/PBC, repeat, integer supercells,
wrap, center/vacuum, zone-axis and reciprocal plane-normal alignment, and exact
matrix inspection/input. Advanced structure controls are initially collapsed.
Button help is available on hover, keyboard focus, F1 and the right-click Help
menu. Form dialogs show scientific meaning and units without Python input.

Builders delegate to ASE: bulk, FCC(111), BCC(110), HCP(0001), general Miller
surface, graphene, MX2, icosahedron, decahedron, octahedron and nanotube. Their
common parameters have native form fields. Specialist builder parameters remain
available through the documented `build_specimen(kind, **parameters)` API.
Finite clusters retain false PBC; nanotubes retain ASE axial PBC; slabs retain
ASE in-plane periodicity. Adding vacuum never changes PBC.

`Specimen.edit(label, operation)` applies an operation to a candidate copy, then
commits a snapshot only if it succeeds. Undo/redo restores atoms, selection and
orientation; new edits invalidate redo. A rotation gesture creates one history
entry. Pan/zoom are presentation-only and do not enter scientific history. The
history default is 100 snapshots; large structures may require a smaller bound.
Observers fire after changes. Selection is cleared after replacement/deletion.

ASE reads the last frame by default; scripts can supply an explicit index.
Extended XYZ saves `specimen_view_axes` in metadata and restores it on opening.
Other ASE formats may not retain this metadata, cell or PBC: choose a format
appropriate to the specimen. Files with invalid orientation metadata are rejected
before replacing the current structure. There is no automatic conversion of a
finite particle into a periodic crystal.

## Verification and limits

`tests/test_specimen.py` compares edits, topology and builders with ASE, verifies
history and isolation, periodic neighbour offsets and direct versus reciprocal
alignment in an oblique cell. The asymmetric matrix tests compare projected
coordinates with `apply_view_rotation(recenter=False)`.
`tests/test_specimen_gui.py` additionally reads an OpenGL framebuffer to check
rendered positions, and exercises orientation gestures, picking, pan and zoom.
Run the complete existing and new tests with:

```sh
xvfb-run -a pytest --run-slow --run-gui
```

No backend physics or existing scientific assertions were changed. Bond generation
uses ASE natural cutoffs with a 1.15 tolerance multiplier as a visual heuristic, not inferred chemical bond order.
Bonds/cell are overlays rather than depth-tested solid geometry. Picking is CPU
projection-based and prioritizes beam depth in a fixed marker hit radius. Very
large structures, animation/trajectory editing, volumetric fields, constraint
editing, and crystallographic symmetry operations need further UI work. Structure
building and file I/O are synchronous; long abTEM simulation remains the shell's
responsibility. The subsystem does not call abTEM while interacting with atoms.
