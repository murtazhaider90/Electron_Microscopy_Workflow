# Windows distribution

End users download `ElectronMicroscopyWorkbench-Setup.exe`, run the normal
installer, and launch **Electron Microscopy Workbench** from Start Menu. The
installer offers an unchecked Desktop shortcut option and a launch checkbox on
completion. Python, pip, terminals and batch files are not required. Windows
Settings → Apps includes an uninstall entry. Installation is per user without
administrator privileges; Windows x64 on an Intel/AMD CPU is the supported target.

## Current UI boundary

This repository contains an ASE/Tk scientific workbench, not a completed Qt
scientific editor. The new PySide6 desktop entry offers **Open specimen**,
**Build specimen / open workbench**, and **Open diagnostic logs**. It opens the
existing ASE editor and scientific controls in a separate process. This preserves
all existing ASE capabilities and scientific orientation/physics behavior while
avoiding competing Qt/Tk event loops. It is a distribution foundation for the
future PySide6 scientific UI, not a claim that the scientific editor has been
migrated. `abtem-ase-gui` and the scriptable scientific APIs continue to work.

## Packaging decision

Use **PyInstaller 6 onedir + Inno Setup 6**. The installer embeds the complete
folder, including Python, PySide6/Qt platform plugins, Tk, ASE data, abTEM
parameter tables, NumPy/SciPy, Numba/LLVM, FFTW and other native libraries.
Conservative scientific collection and no UPX favor reliability over size.
Errors are not silently swallowed during dependency collection. Build only in a
clean Windows environment containing PySide6 as the sole Qt binding. Official
PyInstaller Qt hooks collect the Windows platform plugin.

A onefile bundle would extract a large scientific runtime on every start and
complicate native DLL/cache diagnosis. Nuitka and `pyside6-deploy` can be evaluated
later, but compilation adds build complexity without removing the need for native
scientific dependencies and data. A system Python/Conda installation is unsuitable
for the intended user experience. The initial distribution is CPU-only; GPU/CUDA
and optional pymatgen are not included.

## Versions, metadata and branding

`pyproject.toml` supplies the application version to executable ProductVersion /
FileVersion, Qt metadata, installer and artifact folder. Use numeric `X.Y.Z`
versions and matching `vX.Y.Z` release tags. The executable has a stable filename
`ElectronMicroscopyWorkbench.exe`; its Windows version resource is versioned.
A stable installer AppId makes Windows recognize upgrades and uninstall records.

The publisher string is a contributor placeholder. Add a licensed multi-resolution
`packaging/windows/app.ico` (16–256 px) to replace the default executable/installer
icon. No invented institutional branding is included. Review metadata, licenses
and bundled dependency notices before public release.

## Data and diagnostics

`platformdirs` chooses writable per-user directories with no version suffix. On
Windows they are below `%LOCALAPPDATA%\ElectronMicroscopyWorkbench`:

- configuration and data: application root (platformdirs' Windows convention)
- cache: `Cache`, with Numba cache in `Cache\numba`
- logs: `Logs\workbench-PID.log` (per process, 2 MB, three backups) and `Logs\crash.log`

The installed application lives separately under
`%LOCALAPPDATA%\Programs\ElectronMicroscopyWorkbench`. Application startup never
writes into the installation directory. Uninstall deliberately retains user data,
preferences and diagnostics. Users can delete these explicitly after uninstall.
The launch window opens the log folder. Startup errors and Tk/Qt callback errors
log technical details and show a plain message rather than a raw traceback.
`faulthandler` captures supported native faults; it cannot diagnose every Windows
crash or failures before Python starts. Crash output appends; old process logs and crash output may need manual
cleanup. Logs may contain specimen paths; inspect them before sharing.

## Source development

Core development does not require Qt or a packaging tool:

```text
python -m pip install -e ".[dev]"
python -m pytest
abtem-ase-gui
```

For the desktop shell, install `.[desktop]` and run
`python -m emworkbench.desktop` or `electron-microscopy-workbench`.
These commands are developer instructions, not end-user setup steps.

## Windows build and verification

The `Windows distribution` GitHub Actions workflow runs on Windows Server 2022
with CPython 3.11 x64. It installs the constrained CPU stack, checks dependency
consistency and runs scientific regression tests. The constraint set is a
controlled initial candidate; Windows CI must pass before treating it as a
validated release stack. Transitive dependencies are recorded in
`dependencies.txt`; this is not yet a hash-locked dependency graph.

To build locally in a **disposable Windows account**:

```text
py -3.11 -m venv .build-venv
.build-venv\Scripts\python -m pip install -c packaging/windows/constraints.txt ".[desktop,windows-build,dev]"
.build-venv\Scripts\python packaging/windows/build.py
```

Install Inno Setup 6.4.3 first, or pass `--iscc` with its compiler path.
The build driver performs acceptance installs/uninstalls and refuses an account
with an existing Workbench installation/shortcut. It is intended for CI, not a
user's normal account. The older `build_windows_exe.bat` is a developer convenience
for building only a portable folder; it is not the release process.

Packaged smoke checks run from a directory outside the source tree. They require
successful exit and an explicit JSON report from the windowed executable. They
construct a real Qt window using `qwindows`, import the native scientific stack,
round-trip a specimen through ASE, and construct the existing Tk scientific
controls in a child executable. Timeouts prevent a broken GUI from hanging CI.
They do not replace scientific validation and do not yet exercise every ASE
format/plugin, OpenGL driver, simulation or distributed worker operation.

Installer acceptance checks install into a path containing spaces, verify Start
Menu and default/optional Desktop shortcuts and uninstall registration, run the
installed executable, uninstall, and check that shortcuts/binaries/registration
are removed while user data remains. A manual release check on a clean Windows
10/11 machine with no Python should also launch through the shortcut, open a real
specimen, run a small simulation, upgrade an existing install, and uninstall.

Artifacts in `release/X.Y.Z/` include:

- `ElectronMicroscopyWorkbench-Setup.exe`
- `ElectronMicroscopyWorkbench-X.Y.Z-windows-x64.zip` (portable diagnostic alternative)
- SHA-256 checksums, exact resolved dependencies and acceptance reports

PR/main builds upload artifacts. Matching tags generate a **draft** GitHub release
only after build and smoke gates pass. Publication remains a reviewed action.
Build and test Windows executables on Windows; Linux cannot validate them.

## Release limitations

The initial installer and executable are unsigned. SmartScreen reputation and
publisher trust require an organization's Authenticode signing certificate and a
secure signing service. Do not put signing keys in the repository. Before public
release, sign the executable before bundling, sign the resulting installer, then
repeat installed smoke checks and regenerate checksums. No signing credentials
or certificate identity are assumed in this workflow. Clean-machine testing,
upgrade testing, dependency license review and successful Windows CI are release
requirements; a Linux test pass alone is insufficient.
