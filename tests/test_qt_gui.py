"""Optional Qt tests, isolated from Tk and the scientific core."""
import json
from threading import Event

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QMessageBox

from emw_qt.app import MainWindow
from emw_qt.jobs import Cancelled, JobController
from emw_qt.widgets import HelpButton

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings)
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    qtbot.waitUntil(win.isActiveWindow)
    return win


def test_workflow_and_results(window, qtbot):
    assert not window.simulate_button.isEnabled()
    assert [window.tabs.tabText(i) for i in range(4)] == ["TEM", "Diffraction", "Compare", "Metadata"]
    qtbot.mouseClick(window.demo_button, Qt.MouseButton.LeftButton)
    assert window.simulate_button.isEnabled()
    ticks = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    qtbot.mouseClick(window.simulate_button, Qt.MouseButton.LeftButton)
    assert not window.open_action.isEnabled()
    qtbot.waitUntil(lambda: not window.jobs.busy)
    timer.stop()
    assert len(ticks) > 5
    assert window.progress.value() == 100
    data = json.loads(window.metadata.toPlainText())
    assert data["scientific_simulation"] is False
    assert data["preset"] == window.preset.currentText()
    assert "No scientific image" in window.tem.text()
    window.preset.setCurrentIndex(1)
    assert window.metadata.toPlainText() == "No result metadata yet."


def test_advanced_help_and_themes(window, qtbot):
    assert window.advanced.content.isHidden()
    qtbot.mouseClick(window.advanced.toggle, Qt.MouseButton.LeftButton)
    assert window.advanced.content.isVisible()
    help_button = window.viewer.findChild(HelpButton)
    help_button.setFocus()
    qtbot.waitUntil(lambda: help_button.popover.isVisible())
    assert help_button.toolTip()
    window.simulate_button.setFocus()
    qtbot.mouseClick(help_button, Qt.MouseButton.LeftButton)
    assert help_button.popover.isVisible()
    window.set_theme("dark")
    assert window.theme == "dark"
    window.set_theme("light")
    assert window.theme == "light"


def test_persistent_state(window, qtbot):
    window.set_theme("dark")
    window.preset.setCurrentIndex(2)
    window.advanced.set_expanded(True)
    window.resize(900, 600)
    window.close()
    restored = MainWindow(window.settings)
    qtbot.addWidget(restored)
    assert restored.theme == "dark"
    assert restored.preset.currentIndex() == 2
    assert restored.advanced.toggle.isChecked()
    assert restored.size() == window.size()


def test_source_selection_and_friendly_error(window, tmp_path, qtbot):
    source = tmp_path / "specimen.xyz"
    source.write_text("not parsed by this scaffold")
    window.select_specimen(str(source))
    assert window.specimen_path == str(source)
    assert "ASE loading pending" in window.specimen_label.text()
    window.select_specimen(str(tmp_path / "missing.xyz"))
    dialog = window.findChild(QMessageBox)
    assert dialog is not None and dialog.isVisible()
    assert "Choose another" in dialog.text()
    assert "Traceback" not in dialog.text()
    dialog.accept()


def test_job_cancel_and_duplicate_guard(qtbot):
    jobs = JobController()
    started = Event()
    def operation(cancel, report):
        started.set()
        cancel.wait(2)
        raise Cancelled()
    with qtbot.waitSignal(jobs.cancelled):
        assert jobs.start(operation)
        assert not jobs.start(operation)
        qtbot.waitUntil(started.is_set)
        jobs.cancel()
    qtbot.waitUntil(lambda: not jobs.busy)


def test_worker_failure_is_friendly(window, qtbot):
    def fail(cancel, report):
        raise ValueError("private diagnostic")
    window.jobs.start(fail)
    qtbot.waitUntil(lambda: window.findChild(QMessageBox) is not None)
    qtbot.waitUntil(lambda: not window.jobs.busy)
    dialog = window.findChild(QMessageBox)
    assert "private diagnostic" not in dialog.text()
    assert "try again" in dialog.text()
    dialog.accept()


def test_close_requests_safe_cancel(window, qtbot):
    window.open_demo()
    window.simulate()
    window.close()
    assert window.isVisible()
    qtbot.waitUntil(lambda: not window.jobs.busy)
    window.close()
    assert not window.isVisible()
