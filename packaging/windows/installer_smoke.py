"""Installer acceptance check for disposable Windows CI accounts only."""
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
import winreg

APP_ID = "{C855732D-8F90-44C0-ACF9-66B2F2A70658}_is1"
KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"


def folder(csidl):
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer):
        raise RuntimeError("Could not resolve Windows known folder")
    return Path(buffer.value)


def installed():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return winreg.QueryValueEx(key, "DisplayVersion")[0]
    except FileNotFoundError:
        return None


def verify_installer(release, smoke):
    start = folder(2) / "Electron Microscopy Workbench.lnk"  # CSIDL_PROGRAMS
    desktop = folder(16) / "Electron Microscopy Workbench.lnk"
    if installed() or start.exists() or desktop.exists():
        raise RuntimeError("Installer smoke requires a clean disposable Windows account")
    with tempfile.TemporaryDirectory(prefix="EMW install with spaces ") as directory:
        target = Path(directory) / "Application"
        for tasks in ("", "desktopicon"):
            subprocess.run([str(release / "ElectronMicroscopyWorkbench-Setup.exe"),
                            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                            f"/DIR={target}", f"/TASKS={tasks}",
                            f"/LOG={release / ('install-' + (tasks or 'default') + '.log')}"],
                           check=True, timeout=240)
            try:
                assert start.exists(), "Start Menu shortcut missing"
                assert desktop.exists() == bool(tasks), "Desktop shortcut task incorrect"
                assert installed(), "Uninstall registration missing"
                report = release / "installed-smoke.json"
                smoke(target / "ElectronMicroscopyWorkbench.exe", report)
                paths = json.loads(report.read_text(encoding="utf-8"))["paths"]
                marker = Path(paths["data"]) / "installer-smoke-preserve.txt"
                marker.write_text("preserve user data", encoding="utf-8")
            finally:
                uninstaller = target / "unins000.exe"
                if uninstaller.exists():
                    subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                                    "/NORESTART"], check=True, timeout=240)
            assert not start.exists() and not desktop.exists(), "Shortcuts survived uninstall"
            assert installed() is None, "Uninstall registration survived uninstall"
            assert not (target / "ElectronMicroscopyWorkbench.exe").exists()
            assert marker.exists(), "Uninstall deleted user data"
            marker.unlink()
