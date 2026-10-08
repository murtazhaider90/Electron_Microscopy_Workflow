# Permanent development rules

## PRODUCT GOAL

Electron Microscopy Workbench is a standalone desktop application intended primarily for experimental electron microscopists who may have little or no programming experience.

## SCIENTIFIC ENGINES

- ASE remains the canonical atomic-structure engine.
- abTEM remains the canonical electron-microscopy simulation engine.
- Do not reimplement ASE or abTEM physics unnecessarily.
- Preserve the useful structure-building, editing, file I/O, periodic-cell and particle capabilities provided by ASE.

## SCIENTIFIC INVARIANTS

- The exact specimen orientation visible in the 3D viewer must be the exact orientation simulated by abTEM.
- Use one canonical 3x3 orientation/view matrix.
- Never reconstruct the simulation orientation from displayed Euler angles when the exact matrix is available.
- Never mutate the user's original ASE Atoms object during simulation.
- Finite particles must never become accidentally periodic.
- Treat finite, 2D-periodic and 3D-periodic structures deliberately and separately.
- Keep physical structure transforms separate from 2D image-presentation transforms.
- Never modify scientific behavior merely to make an image look visually correct.
- Preserve reproducibility metadata.

## USER EXPERIENCE

The default user workflow must be extremely simple:

Open or build specimen
→ orient specimen visually
→ select microscope/preset
→ Simulate

The normal interface should expose only the controls most experimentalists commonly need.

Advanced or specialist simulation controls must use progressive disclosure, such as an Advanced drawer/panel.

Every non-obvious scientific control must have contextual help available by mouse hover, keyboard focus and click.

Help should explain, where scientifically defensible:

- plain-English meaning
- units
- typical/useful range
- physical effect
- important warnings

Users must never need to write Python to perform normal workflows.

Do not expose raw Python tracebacks to normal users.

## LONG OPERATIONS

- Simulations must run without freezing the GUI.
- Show meaningful progress/status.
- Allow safe cancellation where possible.

## NEW GUI ARCHITECTURE

- Build the new standalone GUI using PySide6 / Qt 6.
- Use a high-performance scientific 3D viewer suitable for ASE Atoms; VisPy is the current preferred candidate but may be evaluated against better-supported alternatives.
- Do not make the scientific core depend on PySide6.
- GUI code calls documented scientific-core APIs.
- The scientific backend must remain independently scriptable/testable.

## TARGET APPLICATION

The final program should install and launch like a normal Windows application:
ElectronMicroscopyWorkbench-Setup.exe
→ install
→ Start Menu/Desktop
→ Electron Microscopy Workbench

End users should not need PowerShell, terminals, Python, pip or batch files.

## ASE FEATURE RETENTION

Retain or recreate access to the practically useful ASE functionality, including:

- atomic structure loading and saving
- common structure formats
- atom selection
- add/delete/move/change atoms
- unit cell display/editing
- PBC controls
- repeat/supercell
- wrapping
- centering/vacuum
- common crystal builders
- surfaces/slabs
- nanoparticles/clusters
- nanotubes where supported
- view/orientation controls
- zone-axis and plane-normal workflows
- undo/redo where appropriate

Do not reproduce obsolete ASE GUI appearance just for compatibility.

## TESTING RULES

- Existing passing scientific tests are the regression baseline.
- Never remove or weaken a scientific assertion just to make tests pass.
- Every scientific bug fix requires a regression test.
- Every orientation bug requires an asymmetric/non-symmetric geometric test.
- GUI tests should be automated where practical.
- Scientific-core tests must not depend on the GUI.
- Compare important results against direct ASE/abTEM calculations.
- Keep tests for finite particles, 2D materials and 3D crystals.

## CURRENT CLEAN BASELINE

Before next-generation development:

- pytest: 44 passed, 0 failed
- pytest --run-slow: 53 passed, 0 failed
- xvfb-run -a pytest --run-slow --run-gui: 67 passed, 0 failed
- all six backend physics tests passed
- all fourteen GUI tests passed

## DEVELOPMENT SAFETY

- Do not push development work directly to main.
- Work in isolated task branches/worktrees.
- Do not automatically merge major changes.
- Keep commits focused.
- Report test failures instead of hiding them.
- If scientific intent is unclear, preserve existing behavior and document the uncertainty.
