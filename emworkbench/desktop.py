"""PySide6 entry point and compatibility bridge to the existing ASE workbench.

The Qt and Tk event loops run in separate processes. No scientific calculations
or orientation state are copied into the distribution layer.
"""
import argparse
import importlib.metadata
import json
import logging
import multiprocessing
from pathlib import Path
import subprocess
import sys

from .runtime import APP_NAME, APP_ID, configure_runtime


def version():
    return importlib.metadata.version("abtem-ase-tem-tool")


def child_command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "emworkbench.desktop", *args]


def ase_workbench(files, smoke=False):
    from ase import Atoms
    from ase.gui.gui import GUI
    from ase.io import read
    from abtem_ase_workbench.launcher import register_tool
    register_tool()
    atoms = [read(filename) for filename in files] if files else [Atoms()]
    gui = GUI(images=atoms)
    # Open the scientific controls immediately, rather than requiring menu discovery.
    tool = gui.abtem_tem_window()
    if smoke:
        gui.window.win.update()
        tool.win.win.update()
        assert tool._notebook.tabs(), "Scientific workbench failed to construct"
        tool.win.close()
        gui.window.win.destroy()
    else:
        # Tk callback errors otherwise print a traceback into a nonexistent console.
        def callback_error(kind, value, tb):
            logging.error("Workbench callback failed", exc_info=(kind, value, tb))
            from tkinter import messagebox
            from .runtime import user_paths
            messagebox.showerror(APP_NAME, "This operation could not be completed. "
                                 f"Details are in {user_paths()['logs']}")
        gui.window.win.report_callback_exception = callback_error
        tool.win.win.report_callback_exception = callback_error
        gui.run()


def main(argv=None):
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--ase-workbench", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ase-smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", type=Path, metavar="REPORT")
    parser.add_argument("--version", action="version", version=version())
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    paths = configure_runtime()
    try:
        if args.ase_workbench or args.ase_smoke:
            ase_workbench(args.files, smoke=args.ase_smoke)
            return 0
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import (QApplication, QFileDialog, QLabel, QMainWindow,
                                       QMessageBox, QPushButton, QVBoxLayout, QWidget)
        app = QApplication([sys.argv[0]])
        app.setApplicationName(APP_NAME)
        app.setOrganizationName(APP_ID)
        app.setApplicationVersion(version())
        window = QMainWindow()
        window.setWindowTitle(APP_NAME)
        window.resize(620, 320)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel(f"{APP_NAME} {version()}"))
        description = QLabel("Open or build a specimen in the existing ASE workbench.\n"
                             "Orient it visually, select a microscope preset, then simulate.")
        description.setWordWrap(True)
        layout.addWidget(description)
        processes = []

        def launch(files=()):
            processes.append(subprocess.Popen(child_command("--ase-workbench", *files)))

        open_button = QPushButton("Open specimen…")
        def open_file():
            filename, _ = QFileDialog.getOpenFileName(window, "Open specimen")
            if filename:
                launch([filename])
        open_button.clicked.connect(open_file)
        layout.addWidget(open_button)
        build_button = QPushButton("Build specimen / open workbench")
        build_button.clicked.connect(lambda: launch())
        layout.addWidget(build_button)
        logs_button = QPushButton("Open diagnostic logs")
        logs_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(paths["logs"]))))
        layout.addWidget(logs_button)
        window.setCentralWidget(content)

        def error_hook(kind, value, tb):
            logging.error("Desktop operation failed", exc_info=(kind, value, tb))
            QMessageBox.critical(window, APP_NAME, "This operation could not be completed. "
                                 f"Details are in {paths['logs']}")
        sys.excepthook = error_hook
        def check_children():
            for process in processes[:]:
                code = process.poll()
                if code is not None:
                    processes.remove(process)
                    if code:
                        QMessageBox.critical(window, APP_NAME,
                                             f"The workbench closed unexpectedly. See {paths['logs']}")
        timer = QTimer(window)
        timer.timeout.connect(check_children)
        timer.start(1000)
        window.show()
        if args.smoke_test:
            # Real Qt platform/window, Tk scientific controls, native imports and data I/O.
            import abtem
            import numba
            import scipy
            if getattr(sys, "frozen", False):
                import skimage
            import zarr
            from ase import Atoms
            from ase.io import read, write
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                specimen = Path(directory) / "probe.extxyz"
                write(specimen, Atoms("Si", positions=[[0, 0, 0]], cell=[5, 5, 5]))
                assert read(specimen).symbols == "Si"
                subprocess.run(child_command("--ase-smoke", str(specimen)),
                               check=True, timeout=120)
            app.processEvents()
            report = {"status": "ok", "version": version(),
                      "frozen": bool(getattr(sys, "frozen", False)),
                      "qt_platform": app.platformName(), "abtem": abtem.__version__,
                      "paths": {key: str(path) for key, path in paths.items()}}
            args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_test.write_text(json.dumps(report, indent=2), encoding="utf-8")
            window.close()
            return 0
        if args.files:
            launch(args.files)
        return app.exec()
    except Exception:
        logging.exception("Application failed")
        if not args.smoke_test and not args.ase_smoke:
            # Works even when Qt could not import or create a QApplication.
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None, f"The application could not start. Details are in {paths['logs']}",
                    APP_NAME, 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
