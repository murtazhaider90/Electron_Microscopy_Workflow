"""Standalone workbench shell. Demo output is never scientific output."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTabWidget, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)

from .jobs import Cancelled, JobController
from .widgets import AdvancedPanel, HelpButton, ViewerPlaceholder


PRESETS = ("General TEM · 200 kV", "Low voltage · 80 kV", "High voltage · 300 kV")


def demo_job(cancel, report):
    """Exercise job lifecycle without calculating or imitating any physics."""
    for step in range(1, 11):
        if cancel.wait(0.06):
            raise Cancelled()
        report(step * 10, "Preparing demo result…")
    return {"mode": "demo", "scientific_simulation": False,
            "note": "No TEM or diffraction calculation was performed."}


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("EMW", "QtWorkbench")
        self.setWindowTitle("Electron Microscopy Workbench · Qt Preview")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.jobs = JobController(self)
        self.specimen_path = None
        self._build_actions()
        self._build_content()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumWidth(220)
        self.progress.setValue(0)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.jobs.cancel)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self.statusBar().showMessage("Ready · Demo mode — scientific integration pending")
        self.jobs.progress.connect(self._progress)
        self.jobs.result.connect(self._result)
        self.jobs.failed.connect(self.show_error)
        self.jobs.cancelled.connect(lambda: self.statusBar().showMessage("Job cancelled safely"))
        self.jobs.busy_changed.connect(self._busy)
        self._restore()

    def _build_actions(self):
        self.open_action = QAction("Open specimen…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_specimen)
        self.demo_action = QAction("Open demo specimen", self)
        self.demo_action.triggered.connect(self.open_demo)
        self.simulate_action = QAction("Simulate demo", self)
        self.simulate_action.setEnabled(False)
        self.simulate_action.triggered.connect(self.simulate)
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.demo_action)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        view_menu = self.menuBar().addMenu("&View")
        for theme in ("light", "dark"):
            action = view_menu.addAction(f"{theme.title()} theme")
            action.triggered.connect(lambda checked=False, value=theme: self.set_theme(value))
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addAction(self.simulate_action)
        about = self.menuBar().addMenu("&Help").addAction("About this preview")
        about.triggered.connect(lambda: QMessageBox.information(
            self, "Qt Preview", "Independent Qt workbench scaffold.\n3D orientation and scientific simulation integration are pending.\nThe existing ASE / Tk application remains available."))
        toolbar = QToolBar("Workflow", self)
        toolbar.setObjectName("workflowToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.demo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.simulate_action)

    def _build_content(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        heading = QLabel("Electron Microscopy Workbench")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        workflow = QLabel("1  Open   →   2  Orient   →   3  Preset   →   4  Simulate")
        workflow.setObjectName("workflow")
        layout.addWidget(workflow)
        notice = QLabel("PREVIEW · Demo results only. 3D orientation and scientific integration are pending.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left.setMinimumWidth(240)
        left_layout = QVBoxLayout(left)
        specimen = self.specimen_panel = QGroupBox("1  Open specimen")
        specimen_layout = QVBoxLayout(specimen)
        self.specimen_label = QLabel("No specimen selected")
        self.specimen_label.setWordWrap(True)
        specimen_layout.addWidget(self.specimen_label)
        open_button = QPushButton("Open specimen…")
        open_button.clicked.connect(self.open_specimen)
        specimen_layout.addWidget(open_button)
        self.demo_button = QPushButton("Use demo specimen")
        self.demo_button.clicked.connect(self.open_demo)
        specimen_layout.addWidget(self.demo_button)
        left_layout.addWidget(specimen)
        microscope = QGroupBox("3  Microscope preset")
        preset_layout = QVBoxLayout(microscope)
        row = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        row.addWidget(self.preset, 1)
        row.addWidget(HelpButton("Accelerating voltage", "Electron energy is commonly specified in kilovolts (kV). These 80–300 kV examples are UI presets only. Voltage influences scattering and wavelength; choose values matching your microscope when scientific integration is available."))
        preset_layout.addLayout(row)
        self.preset.currentIndexChanged.connect(self._invalidate_results)
        left_layout.addWidget(microscope)
        self.advanced = AdvancedPanel()
        left_layout.addWidget(self.advanced)
        self.simulate_button = QPushButton("4  Simulate demo")
        self.simulate_button.setObjectName("primary")
        self.simulate_button.setEnabled(False)
        self.simulate_button.clicked.connect(self.simulate)
        left_layout.addWidget(self.simulate_button)
        left_layout.addStretch()
        self.viewer = ViewerPlaceholder()
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(260)
        self.tem = self._result_label("TEM result\n\nRun the demo to exercise the workflow.\nNo scientific image is generated.")
        self.diffraction = self._result_label("Diffraction result\n\nScientific integration pending")
        self.compare = self._result_label("Compare\n\nSide-by-side result comparison will be available after scientific integration.")
        self.metadata = QTextEdit()
        self.metadata.setReadOnly(True)
        self.metadata.setPlainText("No result metadata yet.")
        for title, widget in (("TEM", self.tem), ("Diffraction", self.diffraction), ("Compare", self.compare), ("Metadata", self.metadata)):
            self.tabs.addTab(widget, title)
        for widget in (left, self.viewer, self.tabs):
            self.splitter.addWidget(widget)
        self.splitter.setSizes([280, 540, 400])
        layout.addWidget(self.splitter, 1)
        self.setCentralWidget(root)

    @staticmethod
    def _result_label(text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMargin(20)
        return label

    def open_specimen(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open specimen", self.settings.value("last_directory", ""),
            "Structures (*.xyz *.extxyz *.cif *.vasp *.traj);;All files (*)")
        if path:
            self.select_specimen(path)

    def select_specimen(self, path):
        """Record a source selection only; parsing stays with future ASE adapter."""
        if not Path(path).is_file():
            self.show_error("That file is no longer available. Choose another specimen file.")
            return
        self.specimen_path = str(Path(path).resolve())
        self.settings.setValue("last_directory", str(Path(path).resolve().parent))
        self._specimen_selected(f"{Path(path).name}\nSelected source · ASE loading pending")

    def open_demo(self):
        self.specimen_path = None
        self._specimen_selected("Demo specimen\nPlaceholder · no atoms loaded")

    def _specimen_selected(self, summary):
        self.specimen_label.setText(summary)
        self.viewer.set_specimen_summary(summary)
        self.simulate_action.setEnabled(True)
        self.simulate_button.setEnabled(True)
        self._invalidate_results()
        self.statusBar().showMessage("Source selected · Choose a preset, then run the demo")

    def _invalidate_results(self):
        self.tem.setText("TEM result\n\nNo current result. Run the demo.")
        self.diffraction.setText("Diffraction result\n\nScientific integration pending")
        self.metadata.setPlainText("No result metadata yet.")

    def simulate(self):
        if not self.simulate_action.isEnabled() or self.jobs.busy:
            return
        self._request = {"source": self.specimen_path or "demo", "preset": self.preset.currentText()}
        self.progress.setValue(0)
        self.jobs.start(demo_job)

    def _progress(self, value, message):
        self.progress.setValue(value)
        self.statusBar().showMessage(message)

    def _result(self, result):
        self.tem.setText("Demo complete\n\nTEM image integration pending\nNo scientific image was generated.")
        self.diffraction.setText("Demo complete\n\nDiffraction integration pending\nNo diffraction calculation was performed.")
        self.metadata.setPlainText(json.dumps({**self._request, **result}, indent=2))
        self.statusBar().showMessage("Demo complete · No scientific calculation performed")

    def _busy(self, busy):
        self.simulate_action.setEnabled(not busy)
        self.simulate_button.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.demo_action.setEnabled(not busy)
        self.specimen_panel.setEnabled(not busy)
        self.preset.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def show_error(self, message):
        self.statusBar().showMessage("Operation could not be completed")
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Let's try again", message,
                             QMessageBox.StandardButton.Ok, self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

    def set_theme(self, theme):
        self.theme = theme if theme in ("light", "dark") else "light"
        dark = self.theme == "dark"
        background, panel, foreground, border = (
            ("#171d28", "#222c3b", "#e8edf5", "#3c4b60") if dark else
            ("#f3f6fb", "#ffffff", "#23334a", "#d5deeb"))
        palette = QPalette()
        for role, color in ((QPalette.ColorRole.Window, background),
                            (QPalette.ColorRole.Base, panel),
                            (QPalette.ColorRole.Button, panel),
                            (QPalette.ColorRole.Text, foreground),
                            (QPalette.ColorRole.WindowText, foreground),
                            (QPalette.ColorRole.ButtonText, foreground),
                            (QPalette.ColorRole.Highlight, "#2879d0"),
                            (QPalette.ColorRole.HighlightedText, "#ffffff")):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self.setStyleSheet(f"""
            QWidget {{ color: {foreground}; }}
            QMainWindow, QMenuBar, QToolBar {{ background: {background}; }}
            QGroupBox, QTabWidget::pane, QFrame#viewer {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}
            QGroupBox {{ margin-top: 14px; padding: 16px 8px 8px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; }}
            QPushButton, QToolButton, QComboBox {{ padding: 8px; border: 1px solid {border}; border-radius: 5px; background: {panel}; }}
            QPushButton:disabled, QToolButton:disabled {{ color: #8390a1; }}
            QPushButton#primary {{ background: #236dc2; color: white; font-weight: bold; }}
            QLabel#heading {{ font-size: 24px; font-weight: bold; padding: 6px; }}
            QLabel#workflow {{ font-size: 18px; font-weight: bold; padding: 12px; color: #4195ed; }}
            QLabel#sectionTitle {{ font-size: 16px; font-weight: bold; }}
        """)
        self.settings.setValue("theme", self.theme)

    def _restore(self):
        self.set_theme(self.settings.value("theme", "light"))
        preset = self.settings.value("preset", PRESETS[0])
        index = self.preset.findText(preset)
        self.preset.setCurrentIndex(max(0, index))
        self.advanced.set_expanded(self.settings.value("advanced", False, type=bool))
        for key, restore in (("geometry", self.restoreGeometry), ("window_state", self.restoreState), ("splitter", self.splitter.restoreState)):
            value = self.settings.value(key)
            if value is not None:
                restore(value)

    def closeEvent(self, event):
        if self.jobs.busy:
            self.jobs.cancel()
            self.statusBar().showMessage("Cancelling… Close again once the job has stopped.")
            event.ignore()
            return
        for key, value in (("geometry", self.saveGeometry()), ("window_state", self.saveState()),
                           ("splitter", self.splitter.saveState()), ("preset", self.preset.currentText()),
                           ("advanced", self.advanced.toggle.isChecked())):
            self.settings.setValue(key, value)
        self.settings.sync()
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Electron Microscopy Workbench")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
