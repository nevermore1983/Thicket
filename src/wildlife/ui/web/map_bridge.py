"""The two-way connection between Python and the map page (through QWebChannel).

Python → page: `send(command, json_args)`; map.js listens and runs the command.
Page → Python: the slots below; each becomes a Qt signal the map page uses.
Everything crossing the bridge is plain text or numbers, so it's easy to log and test.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, Signal, Slot

log = logging.getLogger(__name__)


class MapBridge(QObject):
    # to the page
    send = Signal(str, str)  # command, JSON arguments

    # from the page
    ready = Signal(dict)  # {"webgl": ..., "maplibre": version}
    failed = Signal(str, str)  # code ("no_webgl", "offline", "script"), message
    sighting_clicked = Signal(int)
    cluster_picked = Signal(list)  # sighting ids under a cluster that can't be split further
    context_menu = Signal(float, float, float)  # lat, lon, zoom
    view_changed = Signal(dict)  # {"lat", "lon", "zoom"}

    def command(self, name: str, **args) -> None:
        self.send.emit(name, json.dumps(args))

    @Slot(str)
    def pageReady(self, info: str) -> None:
        self.ready.emit(json.loads(info))

    @Slot(str, str)
    def pageError(self, code: str, message: str) -> None:
        log.warning("Map page: %s %s", code, message)
        self.failed.emit(code, message)

    @Slot(int)
    def sightingClicked(self, sighting_id: int) -> None:
        self.sighting_clicked.emit(sighting_id)

    @Slot(str)
    def clusterPicked(self, ids: str) -> None:
        self.cluster_picked.emit([int(i) for i in json.loads(ids)])

    @Slot(float, float, float)
    def contextMenu(self, lat: float, lon: float, zoom: float) -> None:
        self.context_menu.emit(lat, lon, zoom)

    @Slot(str)
    def viewChanged(self, camera: str) -> None:
        self.view_changed.emit(json.loads(camera))

    @Slot(str)
    def note(self, message: str) -> None:
        log.info("Map page: %s", message)
