# Verification & regression testing

Two layers: an automated `pytest` suite (`tests/`) and a manual GUI checklist.

## Automated tests

```bash
pip install -e ".[dev]"          # installs pytest
pytest                            # fast tests only (no abTEM, no GUI, no network)
pytest --run-slow                 # + abTEM physics gates (small grids)
xvfb-run -a pytest --run-slow --run-gui   # + Tk GUI smoke tests (headless)
```

- Fast tests always run and need neither abTEM nor a display.
- `--run-slow` tests skip automatically if abTEM is not installed.
- `--run-gui` tests skip without a display (use `xvfb-run` on headless boxes).

### Scientific hard gates (pass/fail, not advisory)
- **Anti-tiling** (`test_anti_tiling_finite_particle`): a finite particle in
  vacuum must leave the frame border featureless (border std < 0.03) and beat
  the forced-periodic case by >3× — directly guards the "duplicated particles"
  bug.
- **Diffraction structure factor** (`test_diffraction_structure_factor_si`):
  Si [001] must obey diamond selection rules — (200)/(020)/(110) forbidden,
  (220)/(400) allowed by >50× — on raw abTEM intensities, with reciprocal
  calibration = 1/a.
- **Shot noise** (`test_dose_poisson_sqrt_n`): var ≈ mean and SNR ∝ √dose.
- **Orientation** (`test_orientation.py`): zone-axis beam = normalized
  `[uvw]·cell`; plane normal from the reciprocal cell; `irotate` round-trip;
  nearest-zone exact; non-cubic zone ≠ plane.
- **Exact ASE-view adapter** (`test_rotation_policy.py`): a deliberately
  asymmetric 3×3 view matrix must produce the same relative projected x/y
  coordinates as ASE's `positions @ gui.axes`; periodic cells must receive the
  same matrix; reflections are rejected; abTEM x-first arrays are converted to
  ASE-screen image orientation with a fixed presentation transform.
- **Rotation policy / anti-tiling mechanism**: finite→cell unchanged & orthogonal,
  periodic→skewed; input atoms never mutated.

## Manual GUI checklist

**Startup**
1. `pip install .`  → `abtem-ase-gui`
2. ASE GUI opens; **Tools → abTEM TEM simulation ...** present.

**A — finite nanoparticle (Pt13)**
1. Build/import Pt13 (pbc F,F,F). 2. Rotation mode = Finite particle.
3. Rotate the view → X/Y/Z fields update. 4. Run TEM / HRTEM Image.
5. Confirm **one particle, no tiling** and that its projected orientation
   matches the ASE canvas (left/right/up/down). 6. Check JSON:
   `orientation_transform=ase_view_matrix`, `image_presentation=ase_gui_screen`,
   `rotate_cell=false`, `rotation_mode=finite_particle`.

**B — 3D crystal (Si)**
1. Load Si. 2. Click [100], [110], [111]; check zone-axis readout.
3. Set plane (111). 4. Run Diffraction; 5. Run TEM. 6. Check metadata
   orientation fields.

**C — 2D slab (graphene, then MoS₂)**
1. Import structure. 2. Center slab + set 2D PBC. 3. Run TEM. 4. Run
   Diffraction. 5. Repeat for MoS₂. 6. Check `structure_pbc=[true,true,false]`.

**D — local file import** — load `.extxyz`, POSCAR/VASP, CIF; confirm it loads
into the *same* ASE GUI session (no second window).

**E — 2DMatPedia JSONL** — load `examples/sample_2dmatpedia.jsonl`; search;
load a selected structure; confirm provenance in JSON.

**Preview + sweep** — move sliders, Update Preview; run a tiny sweep
(defocus `-1,-2`, focal `2.0`, angular `0.2e-3`) → CSV + PNGs + JSONs.

**Failure handling** — invalid Miller `[0 0 0]`, plane `(0 0 0)`, missing
database path, abTEM-missing message: all should give a readable dialog, not a
traceback.

### Phase-3 refactor gates (new in v1.3)
- Package public API importable (`from abtem_ase_workbench import ...`).
- Pure submodules (backend, orientation, validators, presets, export,
  database_2d) do not import Tkinter at load time (verified in a subprocess).
- Backward-compat shims (`abtem_tem_backend`, `abtem_tem`, `abtem_2d_database`)
  resolve to the SAME module objects as the real submodules, so monkey-patches
  and attribute writes affect both namespaces.

### Exact-view gates (new in v1.4)
- `gui.axes` is the only orientation source used by Run TEM, Preview,
  Diffraction, Sweep, oriented-structure export, and reproducible-script export.
- X/Y/Z values are display/edit controls only; they are not converted back into
  a second independent atom rotation at simulation time.
- Image presentation correction is separate from the physical atom/cell
  transform, so a display mirror/transpose fix cannot alter the simulated
  specimen orientation.

## Known limitations (see Phase 1C report)
- CIF *write* may be unavailable in minimal ASE installs (read is fine).
- Tilting a 2D slab out-of-plane uses periodic cell rotation; large tilts can
  make the slab approach its z periodic image — in-plane viewing is unaffected.
- The `orthogonalize_cell` fallback can repeat/cut a cell to make it orthogonal;
  `orthogonalized=true` is recorded in metadata when this happens.
