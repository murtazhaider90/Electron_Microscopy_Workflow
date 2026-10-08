"""Cooperative jobs: callables receive (cancel_event, report_progress).

Jobs must never access widgets. Future science adapters should receive copied
specimens and the viewer's exact matrix, and call existing scientific APIs.
"""
from threading import Event
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class Cancelled(Exception):
    """A job stopped at a safe cancellation point."""


class Signals(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.cancel_event = Event()
        self.signals = Signals()

    @Slot()
    def run(self):
        try:
            result = self.operation(self.cancel_event, self.signals.progress.emit)
            if self.cancel_event.is_set():
                raise Cancelled()
            self.signals.result.emit(result)
        except Cancelled:
            self.signals.cancelled.emit()
        except Exception:
            logging.getLogger(__name__).exception("Workbench job failed")
            self.signals.failed.emit(
                "The operation could not be completed. Check the specimen and settings, then try again.")
        finally:
            self.signals.finished.emit()


class JobController(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.worker = None

    @property
    def busy(self):
        return self.worker is not None

    def start(self, operation):
        if self.busy:
            return False
        worker = Worker(operation)
        self.worker = worker
        worker.signals.progress.connect(self.progress)
        worker.signals.result.connect(self.result)
        worker.signals.failed.connect(self.failed)
        worker.signals.cancelled.connect(self.cancelled)
        worker.signals.finished.connect(self._finished)
        self.busy_changed.emit(True)
        self.pool.start(worker)
        return True

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set()

    @Slot()
    def _finished(self):
        self.worker = None
        self.busy_changed.emit(False)
