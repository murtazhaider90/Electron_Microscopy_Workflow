"""Distribution behavior checks; scientific calculations remain separate."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("platformdirs") is None,
                                reason="desktop extra not installed")


def test_user_paths_are_writable_outside_install_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    if sys.platform == "win32":
        import platformdirs.windows
        monkeypatch.setattr(platformdirs.windows, "get_win_folder",
                            lambda name: str(tmp_path / "local"))
    from emworkbench.runtime import user_paths
    paths = user_paths()
    for path in paths.values():
        assert path.is_dir()
        assert path.is_relative_to(tmp_path)
        (path / "probe").write_text("writable")
    assert user_paths() == paths  # stable across launches/upgrades


def test_child_command_uses_same_frozen_executable(monkeypatch):
    from emworkbench.desktop import child_command
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert child_command("--ase-workbench", "specimen with spaces.cif") == [
        sys.executable, "--ase-workbench", "specimen with spaces.cif"]


def test_core_does_not_import_qt():
    result = subprocess.run([sys.executable, "-c",
                             "import sys, abtem_ase_workbench; "
                             "assert not any(m.startswith('PySide6') for m in sys.modules)"],
                            check=True, capture_output=True)
    assert result.returncode == 0


@pytest.mark.gui
def test_source_desktop_smoke(tmp_path):
    if importlib.util.find_spec("PySide6") is None:
        pytest.skip("desktop extra not installed")
    report = tmp_path / "smoke.json"
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "config"),
               XDG_DATA_HOME=str(tmp_path / "data"), XDG_STATE_HOME=str(tmp_path / "state"), XDG_CACHE_HOME=str(tmp_path / "cache"))
    subprocess.run([sys.executable, "-m", "emworkbench.desktop", "--smoke-test", str(report)],
                   check=True, timeout=240, env=env)
    result = json.loads(report.read_text())
    assert result["status"] == "ok"
    assert result["frozen"] is False
    assert result["version"]
