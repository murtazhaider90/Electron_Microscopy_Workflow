"""Writable per-user paths and diagnostics, independent of scientific engines."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from platformdirs import PlatformDirs

APP_NAME = "Electron Microscopy Workbench"
APP_ID = "ElectronMicroscopyWorkbench"
_crash_stream = None


def user_paths():
    # No version suffix: preferences survive upgrades. No writes to the install tree.
    dirs = PlatformDirs(APP_ID, appauthor=False, roaming=False)
    paths = {"config": Path(dirs.user_config_dir), "data": Path(dirs.user_data_dir),
             "cache": Path(dirs.user_cache_dir), "logs": Path(dirs.user_log_dir)}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def configure_runtime():
    global _crash_stream
    paths = user_paths()
    # Numba's cache must never target the read-only installed package directory.
    os.environ.setdefault("NUMBA_CACHE_DIR", str(paths["cache"] / "numba"))
    # Separate processes must not rotate the same file concurrently.
    handler = RotatingFileHandler(paths["logs"] / f"workbench-{os.getpid()}.log",
                                 maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        force=True)
    _crash_stream = (paths["logs"] / "crash.log").open("a", encoding="utf-8")
    faulthandler.enable(_crash_stream)
    # Windowed PyInstaller applications have no stdout/stderr.
    if sys.stdout is None:
        sys.stdout = _crash_stream
    if sys.stderr is None:
        sys.stderr = _crash_stream
    logging.info("Starting %s; frozen=%s", APP_NAME, getattr(sys, "frozen", False))
    return paths
