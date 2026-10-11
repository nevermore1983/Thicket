"""Read-only view of one sighting, with Edit and Delete."""

from __future__ import annotations

import html

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
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
from wildlife.domain import geo
from wildlife.domain.codes import Identification
from wildlife.domain.counting import format_count
from wildlife.domain.models import Sighting
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.components.species_picker import species_html
from wildlife.ui.components.visuals import fmt_date, rounded, swatch
from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager


def location_text(s: Sighting) -> str:
    if s.eff_latitude is None:
        return "No location yet"
    ref = geo.grid_ref_for(s.eff_latitude, s.eff_longitude, s.eff_uncertainty_m)
    where = ref or f"{s.eff_latitude:.5f}, {s.eff_longitude:.5f}"
    unc = f" (±{s.eff_uncertainty_m:,} m)" if s.eff_uncertainty_m else ""
    centre = f" · centre of {s.place_name}" if s.latitude is None and s.place_name else ""
    return f"{where}{unc}{centre}"


class SightingDetail(PanelView):
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, ctx: AppContext, theme: ThemeManager, sighting_id: int) -> None:
        super().__init__()
        self.ctx, self.theme, self.sighting_id = ctx, theme, sighting_id
        self.title = "Sighting"
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._content: QWidget | None = None
        self.reload()
        theme.changed.connect(self.reload)

    def reload(self) -> None:
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
        s = self.ctx.sightings.get(self.sighting_id)
        t = self.theme.tokens
        category = self.ctx.catalogue.category(s.category_id)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("PanelBody")
        scroll.setWidget(body)
        b = QVBoxLayout(body)
        b.setContentsMargins(18, 14, 18, 20)
        b.setSpacing(14)

        cat = QHBoxLayout()
        sw = QLabel()
        sw.setPixmap(swatch(category, t, 18))
        cat_label = QLabel(category.name)
        cat_label.setProperty("role", "muted")
        cat.addWidget(sw)
        cat.addWidget(cat_label)
        cat.addStretch(1)
        b.addLayout(cat)
        name = QLabel(
            f'<span style="font-size:21px;">{species_html(self.ctx.catalogue.get(s.taxon_id), t.text_2)}</span>'
        )
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setWordWrap(True)
        b.addWidget(name)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        if self.ctx.sightings.is_lifer(s):
            badges.addWidget(self._badge("★ Lifer: your first record of this species", "lifer"))
        if s.identification is not Identification.CERTAIN:
            badges.addWidget(self._badge(f"{s.identification.label} identification", "warn"))
        if s.is_not_wild:
            badges.addWidget(self._badge("Not wild", "plain"))
        badges.addStretch(1)
        b.addLayout(badges)

        photos = self.ctx.photos.for_sighting(s.id)
        if photos:
            strip = QHBoxLayout()
            strip.setSpacing(8)
            for photo in photos[:6]:
                thumb = self.ctx.photos.thumbnail(photo, 256)
                btn = QPushButton()
                btn.setFixedSize(98, 98)
                btn.setProperty("variant", "ghost")
                btn.setToolTip(f"{photo.original_name}: click to open")
                if thumb:
                    btn.setIcon(QIcon(rounded(QPixmap(str(thumb)), 94, 10)))
                    btn.setIconSize(QSize(94, 94))
                else:
                    btn.setText("File missing")
                btn.clicked.connect(
                    lambda _=False, p=photo: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(self.ctx.photos.path_of(p)))
                    )
                )
                strip.addWidget(btn)
            strip.addStretch(1)
            b.addLayout(strip)

        facts = QGridLayout()
        facts.setHorizontalSpacing(16)
        facts.setVerticalSpacing(10)
        rows = [
            (
                "Date",
                fmt_date(s.observed_date, "full")
                + (f", {s.observed_time}" if s.observed_time else " (time unknown)"),
            ),
            ("Place", s.place_name or "None"),
            ("Location", location_text(s)),
            ("Count", format_count(s.count, s.count_qualifier)),
            ("Evidence", s.evidence.label),
            ("Identification", s.identification.label),
        ]
        rows += [
            (label, value.label)
            for label, value in (
                ("Sex", s.sex),
                ("Life stage", s.life_stage),
                ("Habitat", s.habitat),
            )
            if value
        ]
        if s.notes:
            rows.append(("Notes", s.notes))
        for i, (label, value) in enumerate(rows):
            key = QLabel(label)
            key.setProperty("role", "muted")
            key.setAlignment(Qt.AlignmentFlag.AlignTop)
            val = QLabel(html.escape(value))
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if label == "Location" and s.eff_latitude is None:
                val.setProperty("role", "warning")
            facts.addWidget(key, i, 0)
            facts.addWidget(val, i, 1)
        facts.setColumnStretch(1, 1)
        b.addLayout(facts)
        added = QLabel(
            f"Added {s.created_at[:10]}"
            + (f" · edited {s.updated_at[:10]}" if s.updated_at[:16] != s.created_at[:16] else "")
        )
        added.setProperty("role", "caption")
        b.addWidget(added)
        b.addStretch(1)
        v.addWidget(scroll, 1)

        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        edit = QPushButton("Edit")
        edit.setProperty("variant", "primary")
        edit.setIcon(icon("edit", t.accent_fg, 16))
        edit.setToolTip("Edit (E)")
        edit.clicked.connect(lambda: self.edit_requested.emit(s.id))
        delete = QPushButton("Delete")
        delete.setProperty("variant", "ghost")
        delete.setIcon(icon("trash", t.danger, 16))
        delete.setToolTip("Move to the recycle bin (Delete)")
        delete.clicked.connect(lambda: self.delete_requested.emit(s.id))
        fh.addWidget(edit)
        fh.addStretch(1)
        fh.addWidget(delete)
        v.addWidget(foot)
        self._layout.addWidget(content)
        self._content = content

    def _badge(self, text: str, kind: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("badge", kind)
        return label

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_E and not event.modifiers():
            self.edit_requested.emit(self.sighting_id)
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit(self.sighting_id)
            return
        super().keyPressEvent(event)
