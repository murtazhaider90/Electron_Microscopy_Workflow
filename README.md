# ASE Electron Microscopy Workbench

A plugin that turns the standard ASE GUI into an electron-microscopy simulation workbench.
Build or load a structure in ASE GUI the way you already do, then open the tool
to orient the crystal and run an [abTEM](https://abtem.readthedocs.io) multislice
TEM simulation on it — no coding, no separate application.

The whole workflow is: **the exact ASE view becomes the abTEM specimen
orientation.** ASE's current 3×3 `gui.axes` matrix is the single source of
truth. At run time the tool applies that exact matrix to a *copy* of the atoms
(and, for periodic systems, the cell) so abTEM's fixed +z beam sees the same
projection the user chose. Your edited structure is never mutated unless you
explicitly ask.

---

## What it does

- **Exact ASE → abTEM orientation** — mouse rotation, X/Y/Z entry, zone axes,
  and plane normals all update the same `gui.axes` matrix; simulations use that
  matrix directly rather than reconstructing the orientation from Euler angles.
- **Live view ↔ angle sync** — rotate in ASE GUI with the mouse and the X/Y/Z
  angle fields follow; type angles and the ASE view rotates in the same window.
- **Miller orientation** — set the view to a zone axis `[u v w]` or a plane
  normal `(h k l)` (reciprocal-lattice-correct for non-cubic cells), with quick
  `[100]/[110]/[111]` buttons and a live "nearest zone axis" readout.
- **Full microscope controls** — voltage, defocus, sampling, dose, image size,
  wave resolution, and all CTF/aberration + partial-coherence parameters.
- **Image simulation (TEM)** — full multislice image with CTF, dose/Poisson
  noise, and safe normalization.
- **Diffraction (TEM)** — plane-wave (SAED-style) diffraction pattern from the
  same oriented structure, with optional central-beam blocking and log scaling.
- **Interactive preview + benchmark (one tab)** — defocus / focal-spread /
  angular-spread / dose sliders driving a small live preview, plus a parameter
  sweep that exports one PNG + JSON per combination and a CSV index.
- **2D materials database import** — load real structures from local files
  (CIF/POSCAR/XYZ/…), **2DMatPedia** JSON/JSONL, or a **C2DB** folder; search,
  inspect, load into ASE GUI, and set slab/flake/periodic PBC.
- **Metadata** — every run/sweep writes a JSON sidecar capturing all
  parameters, the orientation provenance, and the structure source.
- **Workbench layout** — nine focused tabs: Structure & Orientation, Sample Preparation, Microscope Setup, TEM / HRTEM Image, Diffraction, Preview & Sweep, 2D Materials, Results & Export, Help / About.
- **Sample Preparation** — vacuum/centering, boundary conditions (finite / 2D / periodic), supercell/repeat.
- **Instrument presets** — 80 kV, HRTEM 200/300 kV, conventional 300 kV.
- **Pre-run validation** — readable warnings (not Python tracebacks) for zero-volume cell, finite+periodic mix, large grids, coarse/fine sampling, non-periodic diffraction, large sweeps.
- **Results & Export** — session file list, open-folder button, copy last-run metadata, export oriented structure (.extxyz), export reproducible Python script.

Every image is saved as a grayscale PNG with a matching `.json` sidecar.

---

## Requirements

- Python 3.8+
- ASE (`pip install ase`) — provides the GUI this plugs into
- **Tkinter** (system package, used by ASE GUI itself):
  `sudo apt install python3-tk` (Debian/Ubuntu) /
  `sudo dnf install python3-tkinter` (Fedora) / included with conda
- abTEM + matplotlib to actually run and display images
  (`pip install abtem matplotlib`)
- *(optional)* pymatgen — only for unusual 2DMatPedia records

Install the Python deps with:

```bash
pip install -r requirements.txt
```

The tool is import-safe: if abTEM or matplotlib is missing, the GUI still opens
and tells you what to install instead of crashing.

---

## Quick start (no changes to your ASE install)

```bash
python run_gui.py                    # opens ASE GUI with the tool registered
python run_gui.py my_structure.cif   # ...opening a file (all `ase gui` args work)
```

Then in ASE GUI: **Tools → "Electron Microscopy Workbench"**
(or a top-level **Microscopy** menu if Tools isn't found).

`run_gui.py` does **not** modify your ASE installation — it registers the tool
on the GUI at runtime.

---

## Install as software (pip)

Install the package and get a console command:

```bash
pip install .            # from this folder (or: pip install <path-to-folder>)
abtem-ase-gui            # launches ASE GUI with the tool registered
abtem-ase-gui foo.cif    # ...opening a file
```

`abtem-ase-gui` is the zero-touch launcher as a command — it does not edit your
ASE install. (Tkinter is still a system package; see Requirements.)

---

## Script API (no GUI required)

```python
from abtem_ase_workbench import simulate_tem_from_atoms, apply_view_rotation
from abtem_ase_workbench.backend import simulate_diffraction_from_atoms
from abtem_ase_workbench.orientation import set_view_axes, nearest_zone_axis
from abtem_ase_workbench import database_2d          # local / 2DMatPedia / C2DB
```

The `backend`, `orientation`, `database_2d`, `validators`, `presets`, and
`export` submodules do not import Tkinter and can be used from any script.
The `gui` submodule is Tk-only.

Backward compatibility: the old flat module names (`abtem_tem`,
`abtem_tem_backend`, `abtem_2d_database`) still work and point to the same
module objects, so existing scripts and the installed-menu patch keep working
without changes.

---

## Optional: permanent install into the ASE menu

If you want `ase gui` (however you normally start it) to always show the tool:

```bash
python install.py            # copies modules into ase/gui and patches gui.py
python install.py --uninstall
```

`install.py` makes a timestamped backup of `gui.py`, is idempotent, and — if it
can't recognize your ASE version — leaves the menu untouched and tells you to use
`run_gui.py` instead. A reference `gui.py.patch` is included for manual patching.

---

## Typical workflow

1. Build or open a structure in ASE GUI (or import one from the **2D Materials**
   tab). For 2D materials, use **Center slab + set 2D PBC** first — 2D materials
   use periodic boundaries in x/y and vacuum in z.
2. Orient it: rotate with the mouse, type X/Y/Z angles, or pick a zone axis /
   plane in the **Orientation** tab.
3. Set microscope parameters in the **Microscope** tab; optionally tune with the
   **Preview** sliders.
4. Set an output PNG path and click **Run TEM** (or **Run Benchmark** for a
   sweep).

---

## Files

| File | Purpose |
|------|---------|
| `run_gui.py` | Zero-touch launcher (recommended) |
| `pyproject.toml` | pip install metadata + `abtem-ase-gui` command |
| `install.py` | Optional permanent install / uninstall |
| `abtem_tem.py` | Backward-compat shim → `abtem_ase_workbench.gui` |
| `abtem_ase_workbench/` | Modular package (backend, gui, orientation, validators, presets, widgets, database_2d, export, launcher) |
| `abtem_tem_backend.py` | Backward-compat shim → `abtem_ase_workbench.backend` |
| `abtem_2d_database.py` | Backward-compat shim → `abtem_ase_workbench.database_2d` |
| `gui.py.patch` | Reference diff for manual ASE menu patching |
| `examples/sample_2dmatpedia.jsonl` | Tiny 2DMatPedia-style sample to try import |

---

## Notes

- 2DMatPedia and C2DB provide *real computed* 2D-material structures. Download
  their database/structure files, then import them here — this avoids fake
  template structures.
- Materials Project import is present in the UI but disabled (it needs `mp-api`
  and an API key); it is a future addition.
- `abtem_tem_backend.py` is deliberately free of Tk/Qt so it can also be used
  from your own scripts:

  ```python
  from abtem_tem_backend import simulate_tem_from_atoms
  # `view_axes` is the exact 3x3 ASE view matrix (e.g. gui.axes).
  img, meta = simulate_tem_from_atoms(atoms, output_file="out.png",
                                      view_axes=view_axes)
  ```

For backwards compatibility, `pre_rotation=(x, y, z)` and
`apply_xyz_rotation(...)` still work for explicit Euler-angle scripts, but the
GUI no longer uses them as its simulation orientation source.

Version 1.5 — exact-view adapter + Windows executable packaging


---

## Windows executable (no PowerShell needed)

The project includes a PyInstaller build for Windows. The distributed app is a
portable folder: keep the folder together and double-click
`ElectronMicroscopyWorkbench.exe`.

To build it locally, double-click `build_windows_exe.bat`. It creates a build
environment, installs the Workbench + PyInstaller, and writes:

`dist\\ElectronMicroscopyWorkbench\\ElectronMicroscopyWorkbench.exe`

After that, launching the Workbench needs no PowerShell. You can also drag a
CIF/XYZ/POSCAR/EXTXYZ file onto the EXE to open it in ASE.

### Optional Qt specimen editor

The isolated PySide6/VisPy specimen editor is available with `pip install -e
'.[qt]'` and the `abtem-specimen` launcher. It retains ASE Atoms and hands the
exact displayed orientation matrix to the existing backend. See
[specimen subsystem design and usage](docs/specimen-view.md) for supported editing,
builders, renderer evaluation and test instructions. The legacy Tk GUI remains
available through its existing launcher.
