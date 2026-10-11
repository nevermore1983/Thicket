"""A tiny publish/subscribe hub so services can announce "X changed".

Services are plain Python and know nothing about Qt. The UI subscribes once
(ui/qt_events.py) and turns these into Qt signals, which Qt delivers safely
on the UI thread even when a background worker published them.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    topic: str  # e.g. "sightings", "settings", "photos"
    ids: tuple[int, ...] = field(default_factory=tuple)


Listener = Callable[[Event], None]


class EventHub:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def publish(self, topic: str, ids: tuple[int, ...] = ()) -> None:
        event = Event(topic, ids)
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # one broken listener must not stop the others
                log.exception("Event listener failed for %s", topic)
