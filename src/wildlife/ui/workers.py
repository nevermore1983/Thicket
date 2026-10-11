"""Run slow work in the background and get the result back on the UI thread.

    run_in_background(lambda: ctx.backup.backup_now(), on_done=show_result, on_error=show_error)

There is one pattern for every background task (imports, backups, the species
catalogue...), so the window never freezes while something slow happens.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)
_alive: set[_Task] = set()  # keep tasks (and their signal objects) alive until finished


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
    progress = Signal(str, float)


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], wants_progress: bool) -> None:
        super().__init__()
        self.fn, self.wants_progress = fn, wants_progress
        self.signals = _Signals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            if self.wants_progress:
                result = self.fn(lambda step, fraction: self.signals.progress.emit(step, fraction))
            else:
                result = self.fn()
        except BaseException as exc:  # reported to the UI thread, never lost
            log.exception("Background task failed")
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


def run_in_background(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> None:
    """Run `fn` on a worker thread. If `on_progress` is given, `fn` receives a
    progress(step, fraction) callback as its only argument."""
    task = _Task(fn, on_progress is not None)
    _alive.add(task)

    def finished(handler, value) -> None:
        _alive.discard(task)
        if handler:
            handler(value)
        elif isinstance(value, BaseException):
            raise value  # goes to the global error handler

    task.signals.done.connect(lambda r: finished(on_done, r))
    task.signals.failed.connect(lambda e: finished(on_error, e))
    if on_progress:
        task.signals.progress.connect(on_progress)
    QThreadPool.globalInstance().start(task)
