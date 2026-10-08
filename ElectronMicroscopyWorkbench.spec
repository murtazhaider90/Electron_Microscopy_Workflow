# PyInstaller spec for a portable Windows folder containing
# ElectronMicroscopyWorkbench.exe and all Python/scientific dependencies.
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# Conservative collection is intentional: abTEM/ASE and the scientific stack
# use dynamic imports/plugins. The result is larger but more reliable.
for package in [
    "ase",
    "abtem",
    "matplotlib",
    "scipy",
    "dask",
    "zarr",
    "numba",
    "skimage",
]:
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        try:
            hiddenimports += collect_submodules(package)
            datas += collect_data_files(package)
        except Exception:
            pass

hiddenimports += [
    "abtem_ase_workbench",
    "abtem_ase_workbench.backend",
    "abtem_ase_workbench.database_2d",
    "abtem_ase_workbench.export",
    "abtem_ase_workbench.gui",
    "abtem_ase_workbench.launcher",
    "abtem_ase_workbench.orientation",
    "abtem_ase_workbench.presets",
    "abtem_ase_workbench.validators",
    "abtem_ase_workbench.widgets",
    "abtem_tem",
    "abtem_tem_backend",
    "abtem_2d_database",
    "tkinter",
    "tkinter.ttk",
    "matplotlib.backends.backend_tkagg",
]

a = Analysis(
    ["windows_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ElectronMicroscopyWorkbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ElectronMicroscopyWorkbench",
)
