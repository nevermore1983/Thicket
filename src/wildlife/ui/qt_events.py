"""Turns service events (plain Python) into Qt signals delivered on the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from wildlife.services.events import Event, EventHub


class QtEvents(QObject):
    # Emitting from a worker thread is safe: Qt queues delivery to the receiver's thread.
    changed = Signal(str, tuple)  # topic, ids

    def __init__(self, hub: EventHub, parent: QObject | None = None) -> None:
        super().__init__(parent)
        hub.subscribe(self._forward)

    def _forward(self, event: Event) -> None:
        self.changed.emit(event.topic, event.ids)
