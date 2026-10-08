# Electron Microscopy Workbench — simple verification checklist

Use this in order. A test is a PASS only when the stated result is visible and there is no Python traceback/crash.

## 0. Startup / executable
- Double-click `ElectronMicroscopyWorkbench.exe`.
- ASE GUI opens without PowerShell.
- Open **Tools → Electron Microscopy Workbench**.
- Workbench opens in the same ASE session.

## 1. Exact-view calibration
Use `examples/orientation_marker_Pt4.extxyz`.
- Rotate it to an obviously asymmetric view with the mouse.
- Run TEM.
- Compare ASE and TEM: the same projected features must stay left/right/up/down.
- Rotate again and repeat.
- PASS: no mirror, extra turn, or second rotation.
- JSON: `orientation_transform=ase_view_matrix`, `image_presentation=ase_gui_screen`.

## 2. Pt13 finite-particle / anti-tiling
- Load Pt13; set Finite particle or Auto.
- Rotate and run TEM.
- PASS: one particle only, no repeated/cut-off copies at the borders.
- PASS: TEM orientation matches ASE.
- JSON: `rotate_cell=false`, `rotation_mode=finite_particle`.

## 3. Mouse ↔ X/Y/Z sync
- Rotate with mouse: X/Y/Z changes.
- Type X/Y/Z: ASE view changes.
- PASS: one shared orientation; Run TEM does not add another rotation.

## 4. Silicon orientation
- Bulk Si: click [100], [110], [111].
- Check nearest-zone readout.
- Set plane (111).
- PASS: no errors and orientation is reproducible.

## 5. Silicon diffraction
- Use thick Si (1×1×6).
- Run diffraction.
- PASS: stable symmetric diffraction pattern; no crash.
- Automated physics test checks diamond-Si allowed/forbidden reflections.

## 6. Silicon TEM + metadata
- Run TEM.
- PASS: PNG plus matching JSON sidecar.
- JSON includes voltage, defocus, sampling, dose, orientation, structure/PBC and versions.

## 7. Graphene
- PBC = true,true,false; enough z vacuum.
- Run TEM and diffraction.
- PASS: both complete; JSON records 2D PBC.

## 8. MoS2
- Same as graphene.
- PASS: TEM and diffraction complete; 2D PBC preserved.

## 9. File import
Open EXTXYZ, VASP/POSCAR and CIF.
- PASS: each loads into the same ASE GUI session; no unwanted second app window.

## 10. 2D database import
- Load `examples/sample_2dmatpedia.jsonl`.
- Search MoS2 / WSe2 and load one.
- PASS: structure appears and provenance/database ID is recorded.

## 11. Preview
- Change defocus, focal spread, angular spread and dose.
- Update Preview.
- PASS: preview updates inside Workbench; no extra popup image windows.

## 12. Parameter sweep
Use: defocus `-1,-2`; focal spread `2.0`; angular spread `0.2e-3`.
- PASS: 2 PNGs + 2 JSONs + CSV/index.

## 13. Presets
- Test 80 kV, HRTEM 200 kV, HRTEM 300 kV.
- PASS: fields update; 300 kV preset shows 300 kV.

## 14. Supercell / sample preparation
- Si8 repeat 2×1×1.
- PASS: 16 atoms.
- Test centering/vacuum on a finite structure.

## 15. Results & export
- Export oriented structure and reproducible Python script.
- PASS: structure matches exact ASE orientation and script contains `view_axes`.

## 16. Error / warning handling
Readable message, not traceback, for:
- zero-volume cell
- [0 0 0]
- (0 0 0)
- missing database path
- low/no 2D z vacuum
- huge grid
- coarse/fine sampling
- huge sweep
- non-periodic diffraction

## 17. Automated regression
- `pytest`
- `pytest --run-slow`
- `pytest --run-slow --run-gui`

Hard gates include anti-tiling, exact ASE→abTEM view geometry, display handedness,
Si diffraction rules, Poisson shot noise, Miller/plane math, cell policy,
non-mutation of input atoms and package compatibility.

## Final release PASS
Release only when Pt4 exact-view, Pt13 anti-tiling, Si TEM+diffraction,
graphene+MoS2, import/database/preview/sweep/export/error handling and the full
automated suite all pass.
