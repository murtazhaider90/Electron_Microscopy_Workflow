# Exact ASE-view orientation fix (v1.4)

The Workbench now uses the **exact current ASE GUI view matrix (`gui.axes`)** as
the simulation orientation.  Mouse rotation, X/Y/Z entry, zone-axis controls,
and plane-normal controls all update the same matrix; Run TEM, Preview,
Diffraction, Sweep, oriented-structure export, and reproducible-script export
all read that matrix directly.

## What changed

1. `apply_view_rotation(atoms, view_axes, ...)` is the canonical ASE -> abTEM
   geometry adapter.
2. Finite particles transform atoms only and keep their vacuum box fixed.
3. Periodic crystals/slabs transform atoms and lattice vectors with the same
   matrix.
4. Legacy `pre_rotation=(x,y,z)` remains supported for scripts but is no longer
   used by the GUI simulation path.
5. abTEM's x-first image arrays are converted to a normal screen image
   convention (`transpose + vertical flip`) for exact ASE left/right/up/down
   presentation.  This display conversion is separate from the physical
   specimen transform.
6. JSON metadata records `orientation_transform`, `ase_view_axes`, and
   `image_presentation`.

## Quick verification

Load an asymmetric/finite structure, rotate it in ASE, and run TEM.  The result
should preserve the same projected left/right/up/down orientation as the ASE
canvas.  The JSON should contain:

```json
"orientation_transform": "ase_view_matrix",
"image_presentation": "ase_gui_screen"
```

For a finite particle it should also contain:

```json
"rotate_cell": false,
"rotation_mode": "finite_particle"
```
