"""Side panel: one species at a glance - when you see it, where, and your photos."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.dates import MONTHS, MONTHS_LONG, fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.ui.components.charts import ColumnChart, Series
from wildlife.ui.components.common import button, clear_layout
from wildlife.ui.components.rows import RowButton, StatTile
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.components.species_picker import species_html
from wildlife.ui.components.visuals import plural, rounded, swatch
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "sectionTitle")
    return label


class SpeciesProfile(PanelView):
    show_sightings = Signal(object)  # SightingFilter
    show_map = Signal(object)  # SightingFilter
    view_photos = Signal(list, int)  # photo ids, index to start at

    def __init__(self, ctx: AppContext, theme: ThemeManager, taxon_id: int) -> None:
        super().__init__()
        self.ctx, self.theme, self.taxon_id = ctx, theme, taxon_id
        self.title = "Species"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("PanelBody")
        scroll.setWidget(body)
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(18, 14, 18, 20)
        self._body.setSpacing(12)
        outer.addWidget(scroll, 1)
        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        flt = SightingFilter(taxon_ids=frozenset({taxon_id}))
        fh.addWidget(
            button(
                "Show sightings", "primary", "list", theme, lambda: self.show_sightings.emit(flt)
            )
        )
        fh.addWidget(
            button("Show on map", "secondary", "map", theme, lambda: self.show_map.emit(flt))
        )
        fh.addStretch(1)
        outer.addWidget(foot)
        self.reload()
        theme.changed.connect(self.reload)

    def reload(self) -> None:
        clear_layout(self._body)
        ctx, t = self.ctx, self.theme.tokens
        taxon = ctx.catalogue.get(self.taxon_id)
        profile = ctx.stats.species_profile(self.taxon_id)
        category = ctx.catalogue.category(taxon.category_id)

        cat = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(swatch(category, t, 18))
        cat_label = QLabel(category.name)
        cat_label.setProperty("role", "muted")
        cat.addWidget(icon)
        cat.addWidget(cat_label)
        cat.addStretch(1)
        self._body.addLayout(cat)
        name = QLabel(f'<span style="font-size:21px;">{species_html(taxon, t.text_2)}</span>')
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setWordWrap(True)
        self._body.addWidget(name)

        if not profile.sightings:
            none = QLabel("You haven't recorded this species yet.")
            none.setProperty("role", "muted")
            self._body.addWidget(none)
            self._body.addStretch(1)
            return

        tiles = QGridLayout()
        tiles.setSpacing(8)
        best = f"{profile.best_count:,}" if profile.best_count else "–"
        for i, (label, value, note) in enumerate(
            (
                (
                    "Sightings",
                    f"{profile.sightings:,}",
                    plural(profile.individuals, "animal") + " counted",
                ),
                (
                    "Best count",
                    best,
                    fmt_date(profile.best_count_date, "medium") if profile.best_count_date else "",
                ),
                ("First seen", fmt_date(profile.first_seen, "medium"), ""),
                ("Last seen", fmt_date(profile.last_seen, "medium"), ""),
            )
        ):
            tiles.addWidget(StatTile(label, value, note), i // 2, i % 2)
        self._body.addLayout(tiles)

        self._body.addWidget(_section("When in the year do I see it?"))
        months = ColumnChart(
            self.theme,
            "Sightings by month",
            [m[0] for m in MONTHS],
            "sightings",
            1,
            list(MONTHS_LONG),
        )
        months.set_series([Series("Sightings", profile.by_month)])
        self._body.addWidget(months)

        if len(profile.by_year) > 1:
            self._body.addWidget(_section("Sightings each year"))
            years = list(range(min(profile.by_year), max(profile.by_year) + 1))
            per_year = ColumnChart(
                self.theme,
                "Sightings each year",
                [f"'{y % 100:02d}" for y in years],
                "sightings",
                max(1, len(years) // 8),
                [str(y) for y in years],
            )
            per_year.set_series([Series("Sightings", [profile.by_year.get(y, 0) for y in years])])
            self._body.addWidget(per_year)

        if profile.places:
            self._body.addWidget(_section("Where"))
            for place_id, place_name, n in profile.places:
                self._body.addWidget(
                    RowButton(
                        pixmap("pin", t.text_2, 18),
                        place_name,
                        plural(n, "sighting"),
                        "›",
                        lambda pid=place_id: self.show_sightings.emit(
                            SightingFilter(
                                taxon_ids=frozenset({self.taxon_id}), place_ids=frozenset({pid})
                            )
                        ),
                    )
                )

        if profile.photo_ids:
            self._body.addWidget(_section("Photos"))
            strip = QGridLayout()
            strip.setSpacing(6)
            for i, photo_id in enumerate(profile.photo_ids[:9]):
                photo = ctx.photos.get(photo_id)
                thumb = ctx.photos.thumbnail(photo, 256)
                tile = QPushButton()
                tile.setFixedSize(QSize(124, 124))
                tile.setProperty("variant", "ghost")
                tile.setToolTip(f"{photo.original_name}: click to view")
                if thumb:
                    tile.setIcon(QIcon(rounded(QPixmap(str(thumb)), 120, 10)))
                    tile.setIconSize(QSize(120, 120))
                else:
                    tile.setText("File missing")
                tile.clicked.connect(
                    lambda _=False, index=i: self.view_photos.emit(profile.photo_ids, index)
                )
                strip.addWidget(tile, i // 3, i % 3)
            self._body.addLayout(strip)
        self._body.addStretch(1)
