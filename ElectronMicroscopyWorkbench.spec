"""Windows x64 onedir bundle. Build only in a clean, desktop-only environment."""
from pathlib import Path
import tomllib
from PyInstaller.utils.hooks import collect_all, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo,
    VarStruct, VSVersionInfo,
)

root = Path(SPECPATH)
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
version_tuple = tuple(int(part) for part in version.split(".")) + (0,)
info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                      mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("CompanyName", "Electron Microscopy Workbench contributors"),
        StringStruct("FileDescription", "Electron Microscopy Workbench"),
        StringStruct("FileVersion", version), StringStruct("ProductVersion", version),
        StringStruct("ProductName", "Electron Microscopy Workbench"),
        StringStruct("OriginalFilename", "ElectronMicroscopyWorkbench.exe"),
    ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
)
datas = copy_metadata("abtem-ase-tem-tool")
binaries, hiddenimports = [], []
# Deliberately retain dynamic scientific imports, parameter tables and native DLLs.
# Fail collection errors instead of silently producing an incomplete application.
for package in ("ase", "abtem", "matplotlib", "scipy", "dask", "distributed",
                "zarr", "numba", "llvmlite", "skimage", "pyfftw"):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
hiddenimports += ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
                  "tkinter", "tkinter.ttk", "matplotlib.backends.backend_tkagg"]
# Qt is collected by the official PyInstaller hooks (including qwindows).
# Other Qt bindings must not coexist in the build environment.
a = Analysis([str(root / "windows_app.py")], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["PyQt5", "PyQt6", "PySide2"], noarchive=False)
pyz = PYZ(a.pure)
icon = root / "packaging/windows/app.ico"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="ElectronMicroscopyWorkbench", console=False, debug=False,
          strip=False, upx=False, disable_windowed_traceback=True,
          version=info, icon=str(icon) if icon.exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="ElectronMicroscopyWorkbench")
