"""Map: your sightings as pins, a heat map or species per grid square.

The map itself is a web page (MapLibre) in a QWebEngineView, created on the
first visit so the browser engine doesn't slow down start-up. Python works out
what to show and sends it over the bridge; the page reports clicks back.
"""

from __future__ import annotations

import base64
import logging

import shiboken6
from PySide6.QtCore import QBuffer, QIODevice, QRectF, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Category
from wildlife.services.map import SQUARE_SIZES, Bounds
from wildlife.ui.components.common import Callout, EmptyState, Segmented, button
from wildlife.ui.components.filter_bar import FilterBar
from wildlife.ui.components.visuals import category_colours, plural
from wildlife.ui.theme import icons
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import Tokens
from wildlife.ui.workers import run_in_background

log = logging.getLogger(__name__)

MODES = (("pins", "Pins"), ("heat", "Heat"), ("squares", "Grid squares"))
BASEMAPS = (
    ("auto", "Automatic"),
    ("standard", "Standard"),
    ("light", "Light"),
    ("dark", "Dark"),
    ("plain", "Plain outline"),
)
UK = {"lat": 54.4, "lon": -3.2, "zoom": 4.6}
PIN = 22  # pin diameter in logical pixels


def pin_png(category: Category, tokens: Tokens) -> str:
    """A category pin (coloured disc, icon, ring) as base64 PNG at 2x, for the map page."""
    fill, ink = category_colours(category, tokens)
    size = PIN * 2
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(tokens.surface), 4))
    p.setBrush(QColor(fill))
    p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    inner = size * 0.56
    icons.render(
        p, category.icon, ink, QRectF((size - inner) / 2, (size - inner) / 2, inner, inner), 2.2
    )
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode("ascii")


def theme_payload(ctx: AppContext, t: Tokens) -> dict:
    categories = ctx.catalogue.categories()
    pins = {str(c.id): pin_png(c, t) for c in categories}
    other = next((c for c in categories if c.is_fallback), None)  # for any unknown category
    if other is not None:
        pins["fallback"] = pins[str(other.id)]
    return {
        "pins": pins,
        "css": {
            "surface": t.surface,
            "text": t.text,
            "text-2": t.text_2,
            "border": t.border,
            "bg": t.bg,
            "icon-filter": "invert(0.85)" if t.dark else "none",  # MapLibre's black icons
        },
        "accent": t.accent,
        "accentFg": t.accent_fg,
        "surface": t.surface,
        "ramp": list(t.ramp),
        "land": t.surface,
        "water": t.surface_3,
        "coast": t.border_strong,
    }


def _bounds_dict(b: Bounds) -> dict:
    return {"west": b.west, "south": b.south, "east": b.east, "north": b.north}


class MapPage(QWidget):
    open_sighting = Signal(int)
    show_ids = Signal(list)  # several sightings in one spot
    add_at = Signal(float, float, int)  # lat, lon, uncertainty (m)
    new_place_at = Signal(float, float)
    show_sightings = Signal(object)  # SightingFilter, e.g. those without a location

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.ctx, self.theme = ctx, theme
        settings = QSettings()
        self.mode = settings.value("map/mode", "pins")
        self.weight = settings.value("map/weight", "sightings")
        self.basemap = settings.value("map/basemap", "auto")
        self.show_places = settings.value("map/places", False, type=bool)
        self.filter = SightingFilter()
        self.view = None  # the QWebEngineView, made on first visit
        self.bridge = None
        self.ready = False
        self.failed = False
        self.offline = False
        self._bounds: Bounds | None = None
        self._generation = 0  # ignore background results from an older filter
        self._fit_after_load = settings.value("map/camera") is None
        self._pending_fly: dict | None = None

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 16)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("Map")
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addSpacing(8)
        self.modes = Segmented(MODES, self.mode if self.mode in dict(MODES) else "pins")
        self.modes.changed.connect(self.set_mode)
        top.addWidget(self.modes)
        self.weight_box = QComboBox()
        self.weight_box.addItem("Weight: sightings", "sightings")
        self.weight_box.addItem("Weight: animals counted", "animals")
        self.weight_box.setCurrentIndex(max(0, self.weight_box.findData(self.weight)))
        self.weight_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.weight_box.setToolTip("Heat by number of sightings, or by number of animals counted")
        self.weight_box.currentIndexChanged.connect(self._weight_changed)
        top.addWidget(self.weight_box)
        top.addStretch(1)
        self.places_box = QCheckBox("Places")
        self.places_box.setToolTip("Show your saved places and their radius")
        self.places_box.setChecked(self.show_places)
        self.places_box.toggled.connect(self._places_toggled)
        top.addWidget(self.places_box)
        self.basemap_box = QComboBox()
        for key, label in BASEMAPS:
            self.basemap_box.addItem(label, key)
        self.basemap_box.setCurrentIndex(max(0, self.basemap_box.findData(self.basemap)))
        self.basemap_box.setToolTip("Background map")
        self.basemap_box.currentIndexChanged.connect(self._basemap_changed)
        top.addWidget(self.basemap_box)
        self.fit_button = button("Fit all", "secondary", None, theme, self.fit)
        self.fit_button.setToolTip("Zoom to show every sighting on the map")
        top.addWidget(self.fit_button)
        v.addLayout(top)

        row = QHBoxLayout()
        self.filter_bar = FilterBar(ctx, theme)
        self.filter_bar.changed.connect(self._filter_changed)
        row.addWidget(self.filter_bar, 1)
        self.status = QLabel()
        self.status.setProperty("role", "muted")
        row.addWidget(self.status)
        self.missing = QPushButton()
        self.missing.setProperty("variant", "link")
        self.missing.setToolTip("List the sightings that have no place or position yet")
        self.missing.clicked.connect(
            lambda: self.show_sightings.emit(self.filter.with_(needs_location=True))
        )
        row.addWidget(self.missing)
        v.addLayout(row)
        self.banner = Callout(theme, "info", "")
        self.banner.hide()
        v.addWidget(self.banner)

        self.stack = QStackedWidget()
        loading = QLabel("Opening the map…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setProperty("role", "muted")
        self.stack.addWidget(loading)
        v.addWidget(self.stack, 1)
        self.squares_note = QLabel()
        self.squares_note.setProperty("role", "caption")
        self.squares_note.setWordWrap(True)
        v.addWidget(self.squares_note)
        self._sync_controls()
        theme.changed.connect(self._theme_changed)

    # ---- the web view, made on first visit -------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.view is None and not self.failed:
            self._create_view()

    def _create_view(self) -> None:
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from wildlife.ui.web import scheme
        from wildlife.ui.web.map_bridge import MapBridge

        profile, self.handler, self.gate = scheme.profile(
            self.ctx.paths.maps, self._online_allowed()
        )

        class Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source) -> None:
                log.info("Map console: %s (%s:%s)", message, source.rsplit("/", 1)[-1], line)

        self.view = QWebEngineView()
        self.view.setPage(Page(profile, self.view))
        self.view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.NoContextMenu
        )  # ours comes from the page
        self.bridge = MapBridge(self.view)
        channel = QWebChannel(self.view.page())
        channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(channel)
        self.bridge.ready.connect(self._page_ready)
        self.bridge.failed.connect(self._page_failed)
        self.bridge.sighting_clicked.connect(self.open_sighting)
        self.bridge.cluster_picked.connect(self.show_ids)
        self.bridge.context_menu.connect(self._context_menu)
        self.bridge.view_changed.connect(lambda cam: QSettings().setValue("map/camera", cam))
        self.view.loadFinished.connect(
            lambda ok: None if ok else self._page_failed("script", "The map page didn't load")
        )
        self.stack.addWidget(self.view)
        self.view.load(QUrl("wildlife://app/map.html"))

    def _page_ready(self, info: dict) -> None:
        log.info("Map ready: MapLibre %s", info.get("maplibre"))
        camera = QSettings().value("map/camera") or UK
        self._send(
            "init",
            theme=theme_payload(self.ctx, self.theme.tokens),
            basemap=self._resolved_basemap(),
            online=self._online_allowed(),
            camera={k: float(camera[k]) for k in ("lat", "lon", "zoom")},
            layers={"mode": self.mode, "weight": self.weight, "showPlaces": self.show_places},
        )
        self.ready = True
        self.stack.setCurrentWidget(self.view)
        self._update_banner()
        self.refresh()
        self._send_places()
        if self._pending_fly:
            self._send("flyTo", **self._pending_fly)
            self._pending_fly = None

    def _page_failed(self, code: str, message: str) -> None:
        if code == "offline":
            self.offline = True
            self._update_banner()
            return
        if code == "script" and self.ready:
            return  # logged by the bridge; the map keeps working
        self.failed = True
        if code == "no_webgl":
            text = (
                "The map needs graphics acceleration (WebGL 2), which isn't available here. "
                "This can happen over Remote Desktop, in some virtual machines, or with old "
                "graphics drivers. Everything else in WildLife works normally."
            )
        else:
            text = (
                f"The map couldn't start ({message}). Everything else in WildLife works normally."
            )
        self.stack.addWidget(EmptyState(self.theme, "map", "The map can't be shown", text))
        self.stack.setCurrentIndex(self.stack.count() - 1)

    def _send(self, command: str, **args) -> None:
        """Send a command to the page, unless it has gone (results from background work can
        arrive after the window closed, when the bridge no longer exists)."""
        if self.bridge is not None and shiboken6.isValid(self.bridge):
            self.bridge.command(command, **args)

    # ---- data ------------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the sightings (and squares, if shown) for the current filter."""
        self._update_banner()
        if not self.ready:
            return
        self._generation += 1
        generation, flt = self._generation, self.filter
        run_in_background(
            lambda: self.ctx.map.sightings(flt),
            on_done=lambda layer: self._sightings_loaded(generation, layer),
        )
        if self.mode == "squares":
            self._load_squares()

    def _sightings_loaded(self, generation: int, layer) -> None:
        if not shiboken6.isValid(self) or generation != self._generation:
            return  # the page closed, or a newer filter's results are on the way
        url = self.handler.publish("sightings.geojson", layer.geojson)
        heat = self.handler.publish("heat.geojson", layer.heat)
        self._send("setSightings", url=url, heat=heat)
        self._bounds = layer.bounds
        self.status.setText(
            f"{plural(layer.shown, 'sighting')} on the map" if layer.shown else "Nothing to show"
        )
        self.missing.setText(f"{layer.without_location:,} without a location")
        self.missing.setVisible(layer.without_location > 0)
        if self._fit_after_load and layer.bounds:
            self._fit_after_load = False
            self._send("fit", bounds=_bounds_dict(layer.bounds), animate=False)

    def _load_squares(self) -> None:
        generation, flt = self._generation, self.filter
        self.squares_note.setText("Counting species per square…")
        run_in_background(
            lambda: [self.ctx.map.squares(flt, size) for size in SQUARE_SIZES],
            on_done=lambda layers: self._squares_loaded(generation, layers),
        )

    def _squares_loaded(self, generation: int, layers) -> None:
        if not shiboken6.isValid(self) or generation != self._generation:
            return  # the page closed, or a newer filter's results are on the way
        sizes = {
            str(layer.size_m): {
                "url": self.handler.publish(f"squares-{layer.size_m}.geojson", layer.geojson),
                "max": layer.most_species,
            }
            for layer in layers
        }
        self._send("setSquares", sizes=sizes)
        one_km = next(layer for layer in layers if layer.size_m == 1_000)
        notes = [
            "Colour shows how many species you've recorded in each square: 10 km squares "
            "when zoomed out, then 2 km, then 1 km as you zoom in."
        ]
        if one_km.too_imprecise:
            notes.append(
                f"{plural(one_km.too_imprecise, 'sighting')} with a rough location "
                "(e.g. a large place) only count in the bigger squares."
            )
        if one_km.outside_grid:
            notes.append(
                f"{plural(one_km.outside_grid, 'sighting')} outside Great Britain "
                "(where the British grid doesn't apply) aren't in any square."
            )
        self.squares_note.setText(" ".join(notes))

    def _send_places(self) -> None:
        if not self.ready:
            return
        from wildlife.services.map import places_geojson

        url = self.handler.publish("places.geojson", places_geojson(self.ctx.places.all()))
        self._send("setPlaces", url=url)

    def places_changed(self) -> None:
        self._send_places()

    # ---- controls --------------------------------------------------------------------
    def set_filter(self, flt: SightingFilter) -> None:
        self.filter_bar.set_filter(flt)

    def _filter_changed(self, flt: SightingFilter) -> None:
        self.filter = flt
        self._fit_after_load = True  # show what the new filter found
        self.refresh()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        QSettings().setValue("map/mode", mode)
        self.modes.set_current(mode)
        self._sync_controls()
        self._send_layers()
        if mode == "squares":
            self._load_squares()

    def _weight_changed(self, _index: int) -> None:
        self.weight = self.weight_box.currentData()
        QSettings().setValue("map/weight", self.weight)
        self._send_layers()

    def _places_toggled(self, on: bool) -> None:
        self.show_places = on
        QSettings().setValue("map/places", on)
        self._send_layers()

    def _send_layers(self) -> None:
        if self.ready:
            self._send("setLayers", mode=self.mode, weight=self.weight, showPlaces=self.show_places)

    def _sync_controls(self) -> None:
        self.weight_box.setVisible(self.mode == "heat")
        self.squares_note.setVisible(self.mode == "squares")

    def _online_allowed(self) -> bool:
        return self.ctx.settings.current.allow_online

    def _resolved_basemap(self) -> str:
        if not self._online_allowed():
            return "plain"
        if self.basemap == "auto":
            return "dark" if self.theme.tokens.dark else "standard"
        return self.basemap

    def _basemap_changed(self, _index: int) -> None:
        self.basemap = self.basemap_box.currentData()
        QSettings().setValue("map/basemap", self.basemap)
        self._apply_basemap()

    def _apply_basemap(self) -> None:
        self.offline = False
        self._update_banner()
        if self.ready:
            self.gate.online_allowed = self._online_allowed()
            self._send(
                "setBasemap", basemap=self._resolved_basemap(), online=self._online_allowed()
            )

    def settings_changed(self) -> None:
        """'Allow online features' may have changed."""
        self._apply_basemap()

    def _theme_changed(self) -> None:
        if self.ready:
            self._send("setTheme", **{"theme": theme_payload(self.ctx, self.theme.tokens)})
            if self.basemap == "auto":
                self._apply_basemap()

    def _update_banner(self) -> None:
        if not self._online_allowed():
            text = (
                "Online maps are turned off in Settings, so the background is a plain outline. "
                "Your sightings still show."
            )
        elif self.offline and self._resolved_basemap() != "plain":
            text = (
                "No internet, so the detailed background map is unavailable. Your sightings "
                "still show on a plain outline. Areas you've viewed before may still appear."
            )
        else:
            self.banner.hide()
            return
        self.banner.set_text(text)
        self.banner.show()

    def fit(self) -> None:
        if self.ready and self._bounds:
            self._send("fit", bounds=_bounds_dict(self._bounds), animate=True)

    def show_location(self, lat: float, lon: float, zoom: float = 15) -> None:
        """Centre on a sighting and ring it (used by 'Show on map')."""
        args = {"lat": lat, "lon": lon, "zoom": zoom, "highlight": True}
        self._fit_after_load = False
        if self.ready:
            self._send("flyTo", **args)
        else:
            self._pending_fly = args

    # ---- right-click menu ------------------------------------------------------------
    def _context_menu(self, lat: float, lon: float, zoom: float) -> None:
        unc = geo.click_uncertainty(lat, zoom)
        where = geo.grid_ref_for(lat, lon, unc) or f"{lat:.5f}, {lon:.5f}"
        menu = QMenu(self)
        heading = menu.addAction(f"{where}  (±{unc:,} m)")
        heading.setEnabled(False)
        menu.addAction(
            icons.icon("plus", self.theme.tokens.text_2),
            "Add sighting here",
            lambda: self.add_at.emit(lat, lon, unc),
        )
        menu.addAction(
            icons.icon("pin", self.theme.tokens.text_2),
            "Create place here",
            lambda: self.new_place_at.emit(lat, lon),
        )
        menu.addSeparator()
        menu.addAction(
            "Copy position",
            lambda: QGuiApplication.clipboard().setText(f"{where} ({lat:.5f}, {lon:.5f})"),
        )
        menu.exec(QCursor.pos())
