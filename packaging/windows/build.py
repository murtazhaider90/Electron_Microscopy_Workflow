"""Developer/CI build driver; never required on an end user's machine."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def smoke(executable, report):
    report.unlink(missing_ok=True)
    subprocess.run([str(executable), "--smoke-test", str(report)],
                   cwd=report.parent, check=True, timeout=240)
    result = json.loads(report.read_text(encoding="utf-8"))
    if result["status"] != "ok" or not result["frozen"] or result["qt_platform"] != "windows":
        raise RuntimeError(f"Packaged smoke test failed: {result}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", default=shutil.which("ISCC") or
                        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build on Windows x64; PyInstaller does not cross-compile")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    release = ROOT / "release" / version
    release.mkdir(parents=True, exist_ok=True)
    run(sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "ElectronMicroscopyWorkbench.spec")
    bundle = ROOT / "dist" / "ElectronMicroscopyWorkbench"
    smoke(bundle / "ElectronMicroscopyWorkbench.exe", release / "bundle-smoke.json")
    run(args.iscc, f"/DAppVersion={version}", f"/DBundleDir={bundle}",
        f"/DOutputDir={release}", str(ROOT / "packaging/windows/installer.iss"))
    # Verify the installed copy, optional shortcut, uninstall registration and removal.
    from installer_smoke import verify_installer
    verify_installer(release, smoke)
    shutil.make_archive(str(release / f"ElectronMicroscopyWorkbench-{version}-windows-x64"),
                        "zip", bundle.parent, bundle.name)
    with (release / "dependencies.txt").open("w", encoding="utf-8") as output:
        subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"],
                       stdout=output, check=True)
    files = sorted(path for path in release.iterdir() if path.suffix in (".exe", ".zip"))
    checksums = []
    for path in files:
        with path.open("rb") as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}\n")
    (release / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")


if __name__ == "__main__":
    main()
