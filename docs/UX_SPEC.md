# Electron Microscopy Workbench: UX specification

Status: design proposal, 8 October 2026. This document specifies a future standalone desktop interface; it does not implement a GUI or change scientific behavior. AGENTS.md is authoritative. The intended implementation is PySide6 / Qt 6, with a high-performance ASE-compatible viewer (VisPy is the current candidate), calling the independently scriptable scientific core.

## 1. Audience, promise, and scope

The primary user is an experimental electron microscopist who understands specimens, beam voltage, focus, and diffraction, but may never have used Python or a simulation package. Their question is: “What would this specimen look like in my microscope at this orientation?” A secondary user needs exact parameter control and reproducibility.

The default path is always:

**Open/build specimen → orient specimen visually → choose microscope/preset → Simulate.**

No terminal, code editor, scripting, output-path configuration, or advanced numerical choices are prerequisites. Launch from the Windows Start Menu/Desktop after normal installation. Provide helpful starting settings, but identify assumptions: a preset is an illustrative configuration, not a calibration of a particular instrument. Never imply that a plausible image proves a structure or reproduces an experiment exactly.

This design covers specimen preparation, TEM images, plane-wave diffraction, reproducible runs, and visual experiment comparison. STEM, acquisition control, automatic structure identification, instrument connection, and quantitative fitting are outside this proposal. Useful ASE structure tools remain accessible through Edit specimen and Build specimen rather than a reproduction of ASE's old GUI.

## 2. Research and design rationale

Reviewed official documentation on 8 October 2026. These are documented interaction patterns, not usability-study findings; the proposed adaptations require testing with experimentalists.

| Reference and observed pattern | Adaptation for this workbench |
| --- | --- |
| [napari image controls](https://napari.org/0.8.0/howtos/layers/image.html): contrast limits, histogram, opacity, and numerical controls; contrast mapping changes visualization rather than underlying values. | Put image display controls beside results. Label display adjustments explicitly, provide numerical alternatives to sliders, and retain the original result. |
| [OVITO multi-viewport layouts](https://www.ovito.org/manual/advanced_topics/viewport_layouts.html): resizable viewports, per-view visibility, reversible layout changes. | Keep specimen and results visible together, with adjustable splits and a reset-layout action. Only one specimen view defines simulation orientation. |
| [OVITO simulation cell](https://www.ovito.org/manual/reference/pipelines/visual_elements/simulation_cell.html): a visible wireframe cell communicates spatial extent. | Distinguish the unit cell, finite calculation box, and repeating boundaries in the specimen viewer; a box alone must not imply periodicity. |
| [3D Slicer interface](https://slicer.readthedocs.io/en/v5.12.0/user_guide/user_interface.html): task controls beside views, contextual data readout, and application status area. | Use a short setup rail, a data readout at the focused pixel/atom, and a persistent run-status strip. |
| [3D Slicer getting started](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html): start with personal data or sample data in a Welcome panel. | Offer Open, Build, and an offline example with a short optional tour. |

The design recommendation is to combine direct visual manipulation, recognizable microscope settings, progressive disclosure, and persistent provenance. Avoid a maze of specialist tabs. A simple interface must still show meaningful uncertainty and scientific warnings.

## 3. Scientific trust and state model

1. **One exact orientation:** visual specimen rotation, zone-axis entry, plane-normal entry, and numeric rotation all update one canonical 3×3 orientation/view matrix. The run snapshots this exact matrix and passes it to the scientific core. Displayed angles are explanatory values, never a reconstruction source for simulation.
2. **Preserve the source:** specimen edits act on an editable working specimen with undo/redo. Simulation operates on a copy and never mutates the original ASE Atoms object. Open preserves a reference to the original source; Save as is the default for changed structures.
3. **Explicit boundaries:** Finite particle, 2D sheet/slab, and 3D crystal are separate choices with per-cell-axis repeat information. Loading must preserve file PBC and disclose it. Unspecified boundaries require a deliberate choice; never infer that every box is periodic. Tilt must not silently change PBC or convert a particle to a crystal.
4. **Separate physical and presentation changes:** specimen rotation changes simulation input; canvas zoom/pan, image contrast, and comparison alignment do not. Label these distinctions in the relevant toolbar and help. Do not flip or rotate scientific data to make a picture look right.
5. **Immutable run inputs:** each run retains specimen revision/source, exact matrix, cell/PBC, requested and effective settings, preset identity/version and overrides, engine versions, stochastic seed, warnings, output transformations, and supported/ignored controls. Do not overwrite authoritative core metadata through extra metadata.
6. **Truthful capability:** if a parameter is unsupported or ignored by the installed engine, show “Not applied” beside it and in results, never a successful-setting indicator. If orientation/boundary handling is unsupported, explain the limitation and block the misleading operation rather than changing physics.

State progression: Empty → Specimen ready → Orientation chosen → Microscope ready → Checking → Running → Complete / Cancelled / Failed. A valid initial orientation counts as chosen and is visibly stated. A valid, explicitly chosen preset can supply microscope readiness. No repeated mandatory wizard confirmations.

Changing specimen, orientation, or physical settings after a completed run marks that result **“Previous settings — simulate to update”**. It remains inspectable with its own snapshot. Display-only changes do not mark it stale. During a run, its input snapshot is locked; users can inspect previous results and help. Cancel before changing physical setup. No automatic simulation on slider movement in the normal workflow.

## 4. Main window: one workspace

Design at 1280×800 logical pixels; remain usable at 1024×700 through collapsible rails and a single-view layout. Respect OS scaling. Use a native menu (File, Edit, View, Help), restrained toolbar, left setup rail (~280 px), central specimen viewer, right result area, and bottom status/run history. Allocate the remaining width approximately equally to specimen and results. Splitters are keyboard adjustable; Reset layout is always available. Smaller windows switch between Specimen and Results without losing state.

```text
+--------------------------------------------------------------------------+
| Electron Microscopy Workbench - Copper specimen *                         |
| File  Edit  View  Help            [Save project]   Beginner [v]            |
+------------------+--------------------------+----------------------------+
| 1 Specimen       | SPECIMEN - beam view      | RESULTS                    |
| [Open] [Build]   | [Orient] [Select] [Fit] ?  | [TEM image] [Diffraction]  |
| Cu, 864 atoms    |                          |                            |
| 3D crystal ?     |       atomic model       |   Simulate to see a result |
| [Edit specimen]  |       + cell edges       |                            |
|                  |                          |                            |
| 2 Orientation    | beam into screen         |                            |
| Drag to orient ? | axes / scale / legend    |                            |
| [Zone axis...]   +--------------------------+----------------------------+
|                  | orientation summary      | run / scale / data readout |
| 3 Microscope     +--------------------------+----------------------------+
| [Choose preset]  | Runs: [Run 1] [Run 2] ... [Compare experiment] [Export] |
| Voltage [ ] kV ? |                                                        |
| Defocus [ ] nm ? |                                                        |
| Output [TEM v]   |                                                        |
| [Advanced (0)]   |                                                        |
| [4 Simulate]     |                                                        |
+------------------+-------------------------------------------------------+
| Ready. Current view will be simulated.                          [? Help] |
+--------------------------------------------------------------------------+
```

The four numbered steps are navigational anchors, not four isolated screens. Simulate is the dominant button and remains in a stable location. Its disabled state has an adjacent explanation and a focusable “What is missing?” action. Selecting an output tab never secretly changes the requested simulation type: the setup rail has TEM image / Diffraction / Both. Both means two explicit jobs with separately reported outcomes.

File offers Open specimen, Open project, Save project, Save specimen as, Import experiment, and Export result. A project contains working specimen, orientation, configuration, run references, and comparison state. Show unsaved changes in the title; close prompts offer Save / Discard / Cancel. Save/export failures must preserve the in-memory session. Autosave recovery is a future session-layer requirement, not a guarantee from the current backend.

## 5. Open and build specimen

Open uses a native file picker plus drag/drop on the specimen area, with supported formats described in ordinary language (for example CIF, XYZ, POSCAR, and extended XYZ, as supported by ASE). Do not advertise every format without checking installed readers. Multi-frame files offer a frame selector and atom/cell preview before loading. Preserve source filename, format, and frame in provenance. Dropped images route to Import experiment, never to a structure reader.

```text
+------------------------------------------------------------+
| Open specimen                                         [X]  |
| File: copper.cif                      [Choose file...]      |
| Frame [1 v]   Preview: Cu, 864 atoms, cell present           |
| Boundaries from file: repeats along a, b, c                  |
| Specimen type: [3D crystal v] ?                             |
| [small preview]  Cell lengths / angles and source summary   |
| [!] Check that repeating boundaries match your specimen.    |
|                                       [Cancel] [Open]      |
+------------------------------------------------------------+
```

If type and file flags conflict, show the conflict and let users preserve flags or explicitly change them in preparation; do not silently normalize them. For XYZ without a usable cell, offer “Add a calculation box” with vacuum/centering preview, explaining that it does not create repeating copies.

Build provides named categories: Crystal, Surface/slab, Nanoparticle, and Nanotube (where ASE supports the requested builder). Each has a compact form and preview, not a code template. Start with material/element, lattice or builder choice, and dimensions with units. Distinguish supported reference lattice values from user-supplied values and retain their source.

```text
+------------------------------------------------------------+
| Build specimen                                        [X]  |
| [Crystal] [Surface/slab] [Nanoparticle] [Nanotube]            |
| Element/material [Cu v] ?    Crystal structure [fcc v] ?     |
| Lattice parameter [       ] Angstrom ?                      |
| Repeat cells  a [3] b [3] c [3] ?                          |
|                                                            |
|       live geometry preview          108 atoms              |
| Boundaries: repeats in a, b, c ?                            |
| Source of starting values: [reference / entered]            |
|                                   [Cancel] [Use specimen]  |
+------------------------------------------------------------+
```

Edit specimen preserves ASE functionality: selection by atom/element/region and table; add/delete/move/change element; cell lengths and angles; per-axis PBC; repeat/supercell; wrap; center/add vacuum; builders and local 2D database import. Destructive edits show selected count and a preview, support undo, and never unexpectedly replace the source file. Wrapping is explained as moving atoms into their periodic cell, not cropping a particle.

```text
+------------------------------------------------------------+
| Edit specimen - working copy                         [Done]|
| [Select] [Atoms] [Cell & boundaries] [Repeat] [Vacuum]        |
| Selected: 4 atoms       [Change element] [Move] [Delete]     |
|                         |                                  |
|     geometry preview    | Atom table: ID / element / xyz   |
|                         | [Select by element...]           |
|                         |                                  |
| Pending: repeat a x2    | [Preview change] [Apply]          |
| [Undo] [Redo]           | Original source retained          |
+------------------------------------------------------------+
```

Show atom count and predicted extent before repeats; validate huge edits before allocating them. Preparation actions and orientation are distinct undo entries. Done returns to the same workspace and marks old results stale when physical input changed.

## 6. Specimen viewer and orientation

The default is an orthographic beam view with the same projection convention as the simulation adapter. The beam travels into the screen along the backend's +z beam direction; screen right/up and crystallographic axes are labeled. The projection convention and handedness are documented in help. Perspective inspection, if provided, is explicitly secondary and cannot replace the canonical beam view or determine a run's orientation.

```text
+------------------------------------------------------------+
| SPECIMEN - this orientation will be simulated               |
| [Orient] [Select atoms] [Pan] [Fit] [Restore orientation] ?  |
|                                                            |
|              o---o---o                beam: into screen     |
|             /   /   /                 screen up ^           |
|            o---o---o                   screen right >       |
|                                                            |
| Legend: Cu   [x] Cell   Repeats: a, b, c   scale: 1 nm       |
| Zone axis: near [1 1 0] (approximate)                        |
| [Set zone axis...] [Set plane normal...] [Numeric tilt...]  |
| Tip: drag to change specimen orientation; zoom changes view|
+------------------------------------------------------------+
```

In Orient mode, left drag rotates the specimen relative to the fixed beam and changes the canonical matrix; wheel/pinch zoom and Pan only change framing. A drag is one undo action. Fit only changes framing; Restore orientation changes physical orientation and is undoable. Atom selection requires the explicit Select mode; never interpret the same drag as selection and rotation. Cell and atom appearance controls are display-only.

Provide discrete tilt buttons (left/right/up/down), beam-axis rotation, editable step size in degrees, and numeric entry as alternatives to dragging. Numeric edits compose a rotation into the canonical matrix. Offer Save orientation / Restore saved orientation. Approximate nearest-zone readouts include angular mismatch and must not claim an exact zone axis. No automatic snapping.

Zone-axis dialog accepts [u v w]; plane-normal dialog accepts (h k l), each with a plain explanation and live preview. For non-cubic cells these are different directions; delegate calculation to the established orientation core. Reject [0 0 0] and unusable cells. For finite particles without lattice information, retain free orientation and disable crystallographic actions with a reason. Tilted slabs show repeat directions on cell axes, not misleading fixed screen x/y labels. Any required orthogonalization/remapping is disclosed in run details with the effective geometry; unsupported cases are not silently “fixed.”

## 7. Microscope and preset workflow

Choose preset opens a searchable list of illustrative configurations and user-saved configurations. Initial choices mirror existing presets: Low-voltage TEM (80 kV), HRTEM 200 kV (Cs-corrected), HRTEM 300 kV (Cs-corrected), and Conventional 300 kV. Never imply brand-specific calibration or rewrite their scientific values in this design exercise.

```text
+------------------------------------------------------------+
| Choose microscope/preset                              [X]  |
| Search [                         ]                         |
| Illustrative presets         | Selected settings           |
| Low-voltage TEM (80 kV)       | Voltage: 200 kV             |
| > HRTEM 200 kV (Cs-corrected) | Spherical aberration: ... ? |
| HRTEM 300 kV (Cs-corrected)   | Focus spread: ... nm ?      |
| Conventional 300 kV          | Beam angular spread: ... ?  |
| My presets                   | Source: bundled preset      |
|                              | Not an instrument calibration|
| Changes: 4 settings [Show before/after]                     |
|                    [Cancel] [Apply preset]                  |
+------------------------------------------------------------+
```

Selecting a row previews; Apply changes only the listed fields and records the preset/version. Show before/after values, especially overridden advanced values. Preserve specimen/orientation and settings not owned by the preset. Switching presets requires an explicit Apply, supports Undo, and never runs a simulation. Saving “My microscope” creates a named copy with optional calibration/source notes; it does not overwrite bundled presets.

The normal rail exposes preset, accelerating voltage (kV), defocus (nm, TEM only), output type, and calculation quality (Quick look / Standard / Custom). Quality describes numerical settings and estimated cost, not a scientific accuracy guarantee; expand its resolved values in a summary. Defocus includes an explicit underfocus/overfocus convention verified against the installed abTEM API; until verified, do not claim a sign mapping. No automatic Scherzer setting or thickness inference.

Diffraction hides imaging-only settings from the normal rail and labels retained values “TEM only”; they do not affect the diffraction run. Dose/noise is available in the drawer with its actual engine behavior explained. Preset overrides display “Modified” plus a count, including hidden settings. Beginner mode must not discard them.

## 8. Advanced controls drawer and expertise levels

Advanced is a docked, scrollable drawer on the right, leaving specimen context visible. At narrow sizes it becomes a full-width panel with a Back action. Opening/closing never changes settings. Changed values appear in a compact run summary even with the drawer closed.

```text
+------------------------------------+-----------------------+
| Specimen / selected result          | ADVANCED          [X] |
| remains visible                    | Search controls [   ] |
|                                    | v Numerical settings  |
|                                    | Pixel spacing [ ] A ? |
|                                    | Output pixels [ ] ?   |
|                                    | > Lens aberrations    |
|                                    | > Partial coherence   |
|                                    | > Dose and noise      |
|                                    | > Diffraction options |
|                                    | > Reproducibility     |
|                                    | Modified: 3 [Review]  |
|                                    | [Reset section...]    |
+------------------------------------+-----------------------+
```

Groups contain only supported controls: numerical spacing/grid controls; Cs/C5, astigmatism/coma and directions; focal/angular spread; electron dose and random seed; diffraction angle extent, central-beam exclusion, and backend log option; output/provenance details. Slice thickness and other future engine options appear only when a documented API supports them. Explain relationships among output size, field of view, pixel spacing, and internal wave grid; do not pretend they are interchangeable. Current core may crop/resize results: report effective sampling and transformations from verified metadata, or label scale unavailable.

Reset section previews changed values and can be undone. “Use preset values” affects preset-owned fields only. Search can find both plain names and scientific aliases, reveal the group, focus the control, and open its help. Unsupported values remain visible in imported run records but are not editable as if supported.

| Beginner (default) | Expert |
| --- | --- |
| Four-step workflow, brief guidance, grouped advanced settings closed. | Same workflow, can persist expanded groups and precise numerical readouts. |
| Plain names with scientific alias in help. | Scientific aliases alongside plain names and inspectable exact matrix. |
| Explicit presets and visible assumptions. | Custom configurations, seed, parameter sweeps, and metadata inspection where supported. |
| All scientific warnings and hidden overrides visible. | Same validation; expertise never bypasses invariants. |

Switching mode is a view preference, not a reset or change of physics. Sweeps are a separate expert task with combination count, cost/output estimate, preview list, cancellation, and per-run provenance; they are never launched by the default Simulate button. Exporting a reproducible script is optional expert functionality, not a required workflow.

## 9. Contextual help: hover, focus, and click

Every non-obvious scientific field, builder choice, boundary control, orientation action, and display transformation has a named `?` button. Hover over its label or help target shows a short explanation after ~500 ms. Keyboard focus exposes the same concise description through accessible description text and the status/help area; do not steal focus or cover the input. Clicking `?`, activating it with Enter/Space, or pressing F1 on its control opens persistent help. Escape closes it and returns focus. No meaning available only through hover or a right-click menu.

```text
+------------------------------------------------------------+
| HELP: Defocus                                         [X]  |
| Focus offset from the reference image plane.               |
| Unit: nm. Sign convention: [verified backend convention].   |
| Effect: changes phase contrast and which details transfer. |
| Starting point: selected preset; useful range depends on   |
| voltage, lens settings, specimen and imaging objective.    |
| Warning: a brighter atom is not necessarily a heavier atom.|
| [Illustration] [Related: Cs] [More details]                 |
+------------------------------------------------------------+
```

Each help entry supplies meaning, unit, effect, applicable mode, typical/useful range when defensible, caveats, and setting provenance. Distinguish supported limits from suggested starting points. If no general range is defensible, say why rather than inventing one. Scientific help must be reviewed and versioned with the backend convention. Essential help is bundled offline; external links are optional and visibly open a browser. Long help is selectable, searchable, and screen-reader accessible.

Examples: Voltage — electron accelerating voltage in kV; influences wavelength/scattering, not a universal quality slider. Pixel spacing — calculation spacing in Å/pixel; smaller values cost more and may resolve finer detail, but are not a detector calibration. Boundaries — whether atoms repeat along cell axes; a finite particle must remain finite. Beam direction — exact current specimen orientation to be used in the calculation.

## 10. Validation, warnings, and recovery

Validate individual fields after edit/focus leave without interrupting typing; rerun full validation immediately before snapshotting a run. Units are always adjacent; accept scientific notation in expert fields and locale-aware decimal input. Reject non-finite values and invalid integer/grid entries rather than silently coercing them. Unit conversion must preserve precision and be shown in run metadata.

Errors block a run; warnings communicate a limitation and offer a specific remedy or Continue with warning. Aggregate warnings in one review panel, with links to controls. Recheck if relevant settings change. Do not repeatedly require acknowledgement for unchanged input, but retain acknowledgements in that run's provenance. Never globally suppress scientifically material warnings.

```text
+------------------------------------------------------------+
| Check before simulation                                    |
| [ERROR] No usable calculation box. [Cell & boundaries]      |
| [WARNING] Fine pixel spacing may require substantial memory|
| Current: 0.008 A/pixel. [Numerical settings] [?]             |
| [WARNING] Finite specimen diffraction may contain broadened|
| features; not necessarily sharp crystal spots. [?]         |
|                                   [Back to setup]          |
| [Simulate with warnings] (disabled while error remains)     |
+------------------------------------------------------------+
```

| Condition | User-facing response and action |
| --- | --- |
| No/empty specimen | “Open or build a specimen before simulating.” Open / Build. |
| Zero-volume/invalid cell | “The specimen needs a valid calculation box.” Preview a box/centering change; never auto-add periodicity. |
| Finite/PBC mismatch | Explain recorded flags and chosen handling; require explicit resolution if a finite particle would become periodic. |
| Too little slab vacuum | Warn based on actual cell geometry and engine checks; offer Vacuum preview, not an automatic modification. |
| Coarse spacing | “Fine detail/high-angle scattering may be undersampled.” Link spacing and limitations. |
| Fine spacing/large grid/repeat/sweep | Show computed size/count and memory/time estimate when available; offer smaller settings. |
| Invalid zone/plane/matrix | Explain invalid direction or unavailable lattice, keep last valid orientation. |
| Unsupported engine setting | “This setting will not be applied by this engine version.” Review effective settings before proceeding. |
| Missing output calibration | “Physical scale is unavailable for this output.” Allow inspection; disable misleading measurements/scale bars. |

Existing validator thresholds (spacing >0.3 Å/pixel or <0.01 Å/pixel, large grids >2048, sweeps >200) are current backend heuristics, not universal accuracy or safety limits. Preserve existing scientific checks; future refinements require scientific review. Do not classify all finite-specimen diffraction as diffuse: features depend on specimen size and order.

A failure message states what failed, what was retained, and the next useful action. Example: “Simulation stopped: insufficient memory for this calculation. Your specimen and settings are retained. Try a smaller calculation grid in Advanced.” Actions: Review settings / Retry / Copy diagnostic report. Do not suggest a smaller output crop if it does not reduce the wave calculation.

```text
+------------------------------------------------------------+
| Simulation could not finish                               |
| The simulation engine could not start. Your setup is saved. |
| [Retry] [Installation help] [Copy diagnostic report]        |
| > Technical details (optional, selectable)                 |
| Run 003: Failed. No completed result.                      |
+------------------------------------------------------------+
```

Normal users never see raw Python tracebacks. Optional technical details are collapsed and separate from the actionable explanation. Reports include run ID, versions, failure category, and relevant settings; users preview paths/metadata before copying or sharing. No automatic upload. File-read errors name the file/format and offer another file; export errors offer another destination while preserving results. Packaged-engine failures offer repair/install guidance, never instruct normal users to run pip.

## 11. Progress and cancellation

The GUI remains responsive: simulations run outside the GUI event loop. Show phase text from actual job state (Checking, Preparing specimen, Calculating scattering, Forming image/pattern, Saving, Complete) and real progress only when the core provides it. If a phase cannot report its internal progress, use an indeterminate indicator and elapsed time. Never synthesize percentages or claim a ETA without evidence; estimates are labeled estimates and updated cautiously.

```text
+------------------------------------------------------------+
| Run 003 - TEM image - snapshot: Cu / [110] / 200 kV         |
| Calculating scattering                                     |
| [=================...................]  actual work / total |
| Elapsed 01:42   Remaining: estimating...                    |
| [Cancel run]                     [View run settings]       |
| Previous results remain available.                         |
+------------------------------------------------------------+
```

Cancel requests a safe stop, changes the label to “Stopping safely…”, and never falsely reports instant termination. Disable repeated cancellation. If interruption is unavailable within the current engine phase, explain that it will stop at the next safe boundary. Cancellation preserves inputs and earlier results, labels partial artifacts incomplete, and never exports them as finished. A Both request reports each job independently. Completion announces the selected output and keeps focus stable; do not replace a previous result the user is actively inspecting. Closing during a run offers Keep running / Cancel run and close, respecting safe termination.

## 12. TEM and diffraction results

Each result belongs to a run, not to the current editable setup. Show run ID, output type, completion status, preset/voltage, orientation summary, and settings link. Use grayscale by default, a physical scale bar only with verified calibration, and a focused-pixel readout with explicit units/normalization. Fit/1:1/zoom, pan, contrast limits, Auto contrast once, reset display, histogram, and measurements have visible buttons and keyboard alternatives.

```text
+------------------------------------------------------------+
| RESULTS  [TEM image] [Diffraction]     Run [003 v]           |
| Complete | 200 kV | exact orientation saved [Settings]      |
| [Fit] [1:1] [Pan] [Measure] [Reset display] [?]              |
|                                                            |
|                  image or diffraction pattern              |
|                                              ---- 1 nm     |
|                                                            |
| Contrast [low ----o-------o---- high] [Auto once] [Histogram]|
| Display: grayscale  | Diffraction: [Log display] ?          |
| Pixel x/y: ...  Value: normalized ...  Scale: verified      |
| [Compare experiment] [Export...]                            |
+------------------------------------------------------------+
```

TEM displays a real-space image, explicitly not an atom map. Diffraction displays reciprocal space, with angle (mrad) or reciprocal length only when a verified conversion and calibration exist. Explain the central beam and compressed contrast. A TEM Fourier transform, if later offered, is a separately labeled derived view, never passed off as the simulated diffraction pattern.

Current diffraction log scaling and central-beam blocking occur in the backend before normalized output. Record these as run/output transformations; changing them currently requires a new run. Do not apply another log transform to already log-scaled output or promise recovery of blocked intensity. Purely viewer-side controls must operate on the available output without changing core behavior. Surface “Log-scaled output” / “Central beam excluded” badges so users know what they see.

Run history retains thumbnails, timestamp, status, and a short settings summary. Inspecting a previous run does not load its setup; “Use these settings” is a separate, undoable action. Export dialog distinguishes Figure (display adjustments and annotations), Available result data, and Reproducibility metadata/oriented structure. Identify normalized PNGs as normalized, never raw detector counts. Export a package with manifest and linked files where supported; report partial write failure and prevent silent overwrites.

```text
+------------------------------------------------------------+
| Export Run 003                                        [X]  |
| [x] Figure PNG (current contrast + scale annotations)       |
| [x] Result PNG (normalized backend output)                  |
| [x] JSON run metadata   [x] Oriented specimen               |
| Destination [                              ] [Browse]      |
| Quantitative intensity data: unavailable in this run        |
|                                     [Cancel] [Export]      |
+------------------------------------------------------------+
```

## 13. Experiment versus simulation

Start from a completed result → Compare experiment → choose experimental image/pattern → verify calibration → align explicitly → inspect side by side or overlay → save comparison. This is a visual interpretation workflow, not automated fitting or a structure-identification claim.

```text
+------------------------------------------------------------------------+
| Compare experiment with Run 003                              [Close]   |
| Experiment [Open...]  Type [TEM image v]  Calibration [Review...] ?    |
| [Side by side] [Overlay] [Blink]   [Link pan/zoom] [Reset alignment]    |
+----------------------------------+-------------------------------------+
| EXPERIMENT: acquisition.tif       | SIMULATION: Run 003                 |
| Original retained                | Normalized TEM image                |
|                                  |                                     |
|              image               |               image                 |
|                                  |                                     |
+----------------------------------+-------------------------------------+
| Align: translation x/y [ ] [ ]   rotation [ ] deg  [Apply] [Undo]      |
| Overlay opacity [----o----]   Intensity: independent display contrast  |
| Calibration: nm/pixel [ ] ?   source: entered, not verified             |
| [Line profile] [Save comparison] [Export figure + comparison settings] |
+------------------------------------------------------------------------+
```

Import supports documented image readers, initially ordinary TIFF/PNG where available; DM3/DM4/MRC and other microscope formats require evaluated readers and are not advertised prematurely. Review orientation, crop/binning, voltage if known, pixel spacing for images, and reciprocal/angle calibration plus beam center for diffraction. Mark metadata as imported, manually entered, unknown, or verified. Missing calibration permits pixel-space viewing with a prominent label; disable physical measurements, shared physical zoom, and quantitative comparisons until compatible scales exist. Do not assume PNG scale from dimensions.

Side-by-side is default. Link pan/zoom only after compatible calibration; overlays can be manually aligned in pixel space but remain labeled uncalibrated. Align with explicit translation/rotation controls and landmarks; resampling, interpolation, crop, and any intentional reflection are recorded as comparison transforms on derived views. Reflection is off by default and requires explicit acknowledgement because it changes handedness. Original arrays and specimen matrix remain untouched. A comparison rotation never updates specimen orientation or simulation provenance.

Blink is manual by default; optional timed blink has Pause and respects reduced-motion preferences. Profiles show distance units, interpolation, and normalized/display intensity labels. Independent auto contrast can exaggerate apparent agreement; show separate contrast settings, and do not claim equal brightness means equal scattering. Quantitative differences, correlation scores, and intensity fitting remain unavailable for normalized/log-transformed outputs without suitable data, calibration, noise/detector handling, and an explicit scientifically reviewed method.

Save comparison records both sources/run IDs, calibration provenance, transforms, contrast/normalization, ROI, and annotations. Experiment import never silently overwrites microscope settings. A “Use experimental metadata” action previews supported changes and produces a new setup/run; the comparison retains its original reference run.

## 14. Terminology and units

| Primary label | Explanation / expert alias |
| --- | --- |
| Specimen | Atomic model of the sample; ASE Atoms in technical details only. |
| Repeating boundaries | Whether the specimen repeats along cell axes; periodic boundary conditions (PBC). |
| Calculation box | Spatial box used by the calculation; does not by itself imply repetition. |
| Zone axis [u v w] | Crystallographic direction aligned with the beam. |
| Plane normal (h k l) | Direction perpendicular to a lattice plane; different from a zone axis in general. |
| Accelerating voltage | Beam voltage, kV. |
| Defocus | Focus offset, nm, with a verified signed convention. |
| Pixel spacing (calculation) | Numerical real-space sampling, Å/pixel; distinguish from experimental detector sampling. |
| Lens aberrations | Lens imperfections; include Cs/C5 aliases and units. |
| Focus spread / beam angular spread | Partial-coherence controls, nm / mrad; effects explained without requiring jargon. |
| Electron dose | Electrons per unit area; show e−/Å² and whether noise was applied. |
| Diffraction pattern | Plane-wave scattering pattern; describe SAED-style approximation and unsupported instrument effects. |
| Calculation quality | Numerical workload choice; does not certify physical realism. |

Use nm for experimental lengths/focus, Å for atomistic lengths and numerical spacing, kV for voltage, mrad for angular spread, and degrees for orientation. Offer expert unit preferences with lossless conversions at the GUI/core boundary (e.g. kV↔eV, nm↔Å, mrad↔rad); the core's values stay unchanged. State symbols in accessible text. Avoid “gpts,” “multislice,” “CTF,” “frozen phonons,” and “orthogonalization” as unexplained primary labels. Explain them where relevant rather than removing scientific specificity.

## 15. Accessibility and keyboard navigation

Target WCAG 2.2 AA principles adapted to a Qt desktop application: scalable text, OS high-contrast themes, 4.5:1 normal text contrast, 3:1 meaningful non-text controls, visible focus, and no color-only status/element coding. Controls should have comfortable targets (~32 logical px minimum where possible). Respect reduced motion; no auto-spinning specimen or flashing progress. Support keyboard, mouse, touchpad, and screen-reader access through Qt accessibility APIs.

Tab order follows setup rail → viewer toolbar and orientation controls → result controls → history/status. F6/Shift+F6 moves between major regions. Native menus provide equivalent commands for every toolbar action. Dialog focus starts at the task's first control, remains contained while modal, and returns to its invoker. Non-modal drawers do not trap focus. Errors link to and focus the first invalid field; disabled actions have an accessible reason outside the disabled control.

| Shortcut | Behavior |
| --- | --- |
| Ctrl+O / Ctrl+S / Ctrl+Shift+S | Open specimen / Save project / Save project as. |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo edits and orientation; run history is not undone. |
| Ctrl+Enter | Simulate after the same validation as the button, only from the main workspace. |
| F1 / Escape | Open focused control help / close current help, dialog, or tool. Escape alone never cancels a running job. |
| F6 / Shift+F6 | Next / previous main region. |
| Arrow keys in Orient viewer | Discrete tilt by the displayed step; separate buttons provide beam-axis rotation. |
| + / − and Fit button | Zoom / fit focused viewer; do not intercept numeric-field editing. |
| Arrow keys in result inspection | Move pixel cursor for coordinates/value readout; separate Pan mode controls framing. |

Shortcuts are discoverable in menus/help and must avoid OS/assistive-tool conflicts. Numeric controls expose name, value, units, bounds, and help. All sliders have editable numeric equivalents. The 3D canvas exposes a text summary (atom count, selected atoms, cell, boundaries, beam orientation) plus an accessible atom table and numeric orientation commands. Do not rely on canvas pixels alone to communicate state. Announce run start/phase/error/completion politely, throttle updates, and never move focus on completion. Verify the design with Windows Narrator and keyboard-only use; these are acceptance targets, not currently tested capabilities.

## 16. First-time onboarding

```text
+------------------------------------------------------------+
| Welcome to Electron Microscopy Workbench                   |
| See how your specimen may appear in TEM or diffraction.    |
|                                                            |
| [Open my specimen] [Build a specimen] [Try example]          |
|                                                            |
| Open/build -> Orient -> Microscope/preset -> Simulate        |
| No programming required. [? What is being simulated?]       |
| [ ] Show this welcome screen at startup                    |
| [Start short tour]                     [Continue]          |
+------------------------------------------------------------+
```

Default welcome on first launch; thereafter reopen via Help. Provide one small bundled example with known provenance and boundary type, requiring no network or account. It is labeled educational, not an experimental dataset. An optional four-step coach guides opening it, tilting visually, choosing an illustrative preset, and simulating. Each step has Next / Back / Skip; users can operate the real controls, and guidance never locks out their own data. Store completion preference and offer Restart tour.

The orientation step explicitly explains “This view is the orientation simulated.” The preset step explains illustrative settings. After the first result, point out run settings, display-only contrast, and comparison, with no compulsory tour extension. For absent engines or graphics support, show a readable readiness/repair message before the example run, retain setup, and avoid a blank or frozen window.

## 17. Delivery boundaries and acceptance criteria

This commit is documentation only. Existing scientific code, presets, assertions, and baseline tests remain unchanged. Future implementation must use documented scientific-core APIs; missing capabilities are separate reviewed work, not permission to alter physics inside GUI code.

**Available foundations:** ASE structure operations, exact-matrix orientation, TEM and plane-wave diffraction, existing presets/validators, normalized PNG + JSON metadata, and export functions. **Future GUI/session work:** standalone layout, accessible viewer controls, undoable preparation, project/history management, help content, background job status/cancellation adapters, comparison/import readers, and figure export. **Scientific/API review dependencies:** exact defocus convention, effective physical output calibration after crop/resize, preservation of raw intensity for quantitative comparison, actual progress/cancellation hooks, and supported advanced settings. Until resolved, label limitations and disable unsupported claims; do not simulate capabilities through UI copy.

Acceptance for a future GUI release:

- A first-time experimentalist completes the four-step example and a personal-file workflow without Python, a terminal, or the Advanced drawer; test with representative users, including those new to simulation.
- They can distinguish orienting the specimen from zooming/panning and can explain which view is simulated. Future automated tests must verify exact-matrix provenance using asymmetric geometry, rather than only visually symmetric crystals.
- Finite particle, 2D slab, and 3D crystal workflows retain deliberate boundaries; preparation and runs preserve the original specimen.
- All non-obvious controls expose equivalent hover, focus, and click help; keyboard-only users can complete the workflow and recover from an error.
- Changing physical setup visibly marks results as belonging to previous settings; display contrast and comparison alignment leave run provenance unchanged.
- Preset application lists changes, preserves unowned values, and exposes hidden overrides in both modes.
- Long jobs remain responsive, provide truthful status, and cancel safely without presenting incomplete output as complete.
- Experiment comparison labels unknown calibration, normalized/log-transformed intensity, and alignment changes; it cannot imply unsupported quantitative agreement.
- Run/export packages identify effective values, warnings, engine versions, exact orientation, specimen source and boundary handling. Unsupported controls are visibly not applied.

Usability study tasks should include loading an uncalibrated experimental image, spotting a stale result after a tilt, restoring a preset override, resolving an invalid cell, cancelling a long run, and exporting a reproducible result. Record task completion, wrong turns, understanding of assumptions, and recovery; refine the design before claiming usability success.
