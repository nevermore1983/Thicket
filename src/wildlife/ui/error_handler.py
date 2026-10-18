"""Catches anything unexpected, logs it in full, and shows a calm, friendly message.

The user never sees a Python traceback. Errors raised on background threads
are routed to the UI thread with a Qt signal before any dialog is shown.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from types import TracebackType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox, QWidget

from wildlife.domain.errors import WildlifeError

log = logging.getLogger("wildlife.errors")


class ErrorReporter(QObject):
    report = Signal(str, str, bool)  # user message, technical details, expected?

    def __init__(self, parent_window: QWidget | None = None) -> None:
        super().__init__()
        self._window = parent_window
        self._showing = False
        self.report.connect(self._show)

    def set_window(self, window: QWidget) -> None:
        self._window = window

    def handle(
        self, exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        if isinstance(exc, WildlifeError):
            log.warning("%s\n%s", exc.user_message, details)
            self.report.emit(exc.user_message, details, True)
        else:
            log.critical("Unexpected error\n%s", details)
            self.report.emit(
                "Something went wrong. Your data is safe: any change in progress was undone.",
                details,
                False,
            )

    def _show(self, message: str, details: str, expected: bool) -> None:
        if self._showing:  # never stack error dialogs
            return
        self._showing = True
        try:
            box = QMessageBox(self._window)
            box.setWindowTitle("Thicket")
            box.setIcon(QMessageBox.Icon.Warning if expected else QMessageBox.Icon.Critical)
            box.setText(message)
            if not expected:
                box.setInformativeText("The details have been saved to the log file.")
            copy = box.addButton("Copy details", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() is copy:
                QGuiApplication.clipboard().setText(details)
        finally:
            self._showing = False


def install(reporter: ErrorReporter) -> None:
    """Route uncaught exceptions (main thread and worker threads) to the reporter."""

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        reporter.handle(exc_type, exc, tb)

    sys.excepthook = hook
    threading.excepthook = lambda args: hook(args.exc_type, args.exc_value, args.exc_traceback)
