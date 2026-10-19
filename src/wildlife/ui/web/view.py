"""A map web view: MapLibre's page (assets/map.html) in a QWebEngineView, connected to
Python through a MapBridge. The Map page and the "Choose on map" window each make one;
they share the app's single browser profile (scheme.profile), so its map cache too.

Import this module only when a map is about to be shown: loading the browser engine
takes a moment, and start-up shouldn't wait for it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from wildlife.ui.web import scheme
from wildlife.ui.web.map_bridge import MapBridge

log = logging.getLogger(__name__)


class _Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        log.info("Map console: %s (%s:%s)", message, source.rsplit("/", 1)[-1], line)


def map_view(
    cache_dir: Path, online_allowed: bool
) -> tuple[QWebEngineView, MapBridge, scheme.WebHandler, scheme.NetworkGate]:
    """A new view loading the map page. Connect to the bridge's signals straight away:
    `ready` (or `failed`) follows once the page has loaded."""
    profile, handler, gate = scheme.profile(cache_dir, online_allowed)
    view = QWebEngineView()
    view.setPage(_Page(profile, view))
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)  # ours comes from the page
    bridge = MapBridge(view)
    channel = QWebChannel(view.page())
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)
    view.loadFinished.connect(
        lambda ok: None if ok else bridge.failed.emit("script", "The map page didn't load")
    )
    view.load(QUrl("wildlife://app/map.html"))
    return view, bridge, handler, gate
