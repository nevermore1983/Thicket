"""Choose on map: pick a sighting's position by clicking a map (from the sighting editor).

The window shows the same map as the Map page, with your places for bearings. Click
where you saw it (or press Enter for the map's centre), drag the pin to adjust, then
"Use this position". How precise the position is follows the zoom, as for the Map page's
"Add sighting here": zoom in for a closer position.
"""

from __future__ import annotations

import logging

import shiboken6
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.regions import region
from wildlife.ui.components.common import Callout, EmptyState
from wildlife.ui.pages.map_page import resolve_basemap, theme_payload
from wildlife.ui.theme.manager import ThemeManager

log = logging.getLogger(__name__)

NO_MAP = (
    "The map needs graphics acceleration (WebGL 2), which isn't available here. Type a "
    "grid reference or coordinates in the position box instead."
)


class MapPicker(QDialog):
    """`position` holds (lat, lon, uncertainty in metres) once a spot has been chosen."""

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        start: tuple[float, float] | None = None,
        zoom: float = 15,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx, self.theme = ctx, theme
        self.start, self.zoom = start, zoom
        self.position: tuple[float, float, int] | None = None
        self.ready = self.failed = False
        self.view = self.bridge = None
        self.setWindowTitle("Choose the position")
        self.resize(860, 620)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        hint = QLabel(
            "Click where you saw it, then drag the pin to adjust. Zoom in first for a more "
            "precise position. Your places show as circles."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        v.addWidget(hint)
        self.banner = Callout(theme, "info", "")
        self.banner.hide()
        v.addWidget(self.banner)
        self.stack = QStackedWidget()
        loading = QLabel("Opening the map…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setProperty("role", "muted")
        self.stack.addWidget(loading)
        v.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.where = QLabel("No position chosen yet")
        self.where.setProperty("role", "muted")
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        foot.addWidget(self.where, 1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        self.use = QPushButton("Use this position")
        self.use.setProperty("variant", "primary")
        self.use.setEnabled(False)
        self.use.clicked.connect(self.accept)
        foot.addWidget(self.use)
        v.addLayout(foot)
        self._update_banner()
        self._create_view()
        theme.changed.connect(self._theme_changed)

    # ---- the map -----------------------------------------------------------------------
    def _create_view(self) -> None:
        from wildlife.ui.web.view import map_view

        self.view, self.bridge, self.handler, self.gate = map_view(
            self.ctx.paths.maps, self._online()
        )
        self.view.setAccessibleName("Map: click where you saw it")
        self.bridge.ready.connect(self._page_ready)
        self.bridge.failed.connect(self._page_failed)
        self.bridge.position_picked.connect(self._picked)
        self.stack.addWidget(self.view)

    def _theme_changed(self) -> None:
        """Windows can switch to dark (or back) while the window is open."""
        if self.ready:
            self._send("setTheme", theme=theme_payload(self.ctx, self.theme.tokens))
            self._send("setBasemap", basemap=self._basemap(), online=self._online())

    def _online(self) -> bool:
        return self.ctx.settings.current.allow_online

    def _basemap(self) -> str:
        choice = QSettings().value("map/basemap", "auto")  # as chosen on the Map page
        return resolve_basemap(choice, self._online(), self.theme.tokens.dark)

    def _camera(self) -> dict:
        """Start on the position (or place) the sighting has, else where the Map page was
        last, else on the region you record in."""
        if self.start is not None:
            return {"lat": self.start[0], "lon": self.start[1], "zoom": self.zoom}
        camera = QSettings().value("map/camera") or region(self.ctx.catalogue.region()).start_view
        return {k: float(camera[k]) for k in ("lat", "lon", "zoom")}

    def _page_ready(self, _info: dict) -> None:
        from wildlife.services.map import places_geojson

        self._send(
            "init",
            theme=theme_payload(self.ctx, self.theme.tokens),
            basemap=self._basemap(),
            online=self._online(),
            camera=self._camera(),
            layers={"mode": "pins", "weight": "sightings", "showPlaces": True},
        )
        places = self.handler.publish(
            "picker-places.geojson", places_geojson(self.ctx.places.all())
        )
        self._send("setPlaces", url=places)
        at = {"lat": self.start[0], "lon": self.start[1]} if self.start else None
        self._send("pickMode", at=at)
        self.ready = True
        self.stack.setCurrentWidget(self.view)
        self.view.setFocus()

    def _page_failed(self, code: str, message: str) -> None:
        if code == "offline":
            self.banner.set_text(
                "No internet, so the detailed map is unavailable: only a rough outline of "
                "Britain shows. Areas you've viewed before may still appear."
            )
            self.banner.show()
            return
        if code == "script" and self.ready:
            return  # logged by the bridge; the map keeps working
        self.failed = True
        text = (
            NO_MAP
            if code == "no_webgl"
            else f"The map couldn't start ({message}). "
            + ("Type a grid reference or coordinates in the position box instead.")
        )
        self.stack.addWidget(EmptyState(self.theme, "map", "The map can't be shown", text))
        self.stack.setCurrentIndex(self.stack.count() - 1)

    def _update_banner(self) -> None:
        if self._online():
            self.banner.hide()
            return
        self.banner.set_text(
            "Online maps are turned off in Settings, so only a rough outline of Britain shows. "
            "You can also type a grid reference or coordinates in the position box."
        )
        self.banner.show()

    def _send(self, command: str, **args) -> None:
        if self.bridge is not None and shiboken6.isValid(self.bridge):
            self.bridge.command(command, **args)

    # ---- choosing --------------------------------------------------------------------
    def _picked(self, lat: float, lon: float, zoom: float) -> None:
        """The pin was placed or moved: how precise it is follows the zoom."""
        lat, lon = round(lat, 6), round(lon, 6)
        unc = geo.click_uncertainty(lat, zoom)
        self.position = (lat, lon, unc)
        where = geo.grid_ref_for(lat, lon, unc) or f"{lat:.5f}, {lon:.5f}"
        text = f"{where} · ±{unc:,} m"
        if near := self.ctx.places.nearest(lat, lon):
            text += f" · inside {near.name}"
        self.where.setText(text)
        self.where.setProperty("role", "ok")
        self.where.style().unpolish(self.where)
        self.where.style().polish(self.where)
        self.use.setEnabled(True)
        self.use.setDefault(True)
