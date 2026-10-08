@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Electron Microscopy Workbench - Windows EXE builder
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher "py" was not found.
  echo Install Python 3.11 or 3.12 from python.org, then run this file again.
  pause
  exit /b 1
)

if not exist .build-venv (
  echo [1/5] Creating build environment...
  py -3 -m venv .build-venv
  if errorlevel 1 goto :fail
) else (
  echo [1/5] Build environment already exists.
)

call .build-venv\Scripts\activate.bat
if errorlevel 1 goto :fail

echo [2/5] Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [3/5] Installing Workbench + PyInstaller...
pip install . pyinstaller
if errorlevel 1 goto :fail

echo [4/5] Building portable Windows application...
pyinstaller --noconfirm --clean ElectronMicroscopyWorkbench.spec
if errorlevel 1 goto :fail

echo [5/5] Build complete.
echo.
echo Your executable is:
echo   %CD%\dist\ElectronMicroscopyWorkbench\ElectronMicroscopyWorkbench.exe
echo.
echo Double-click that EXE to open the Workbench. No PowerShell is needed.
echo You can also drag a CIF/XYZ/POSCAR/etc. file onto the EXE to open it.
explorer "%CD%\dist\ElectronMicroscopyWorkbench"
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above, then send it to me if you want help.
pause
exit /b 1
