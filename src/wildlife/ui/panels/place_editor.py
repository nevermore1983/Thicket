"""Add / edit a saved place."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.codes import Habitat
from wildlife.domain.errors import ConflictError, ValidationError
from wildlife.domain.models import Place, PlaceDraft
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.panels.sighting_editor import _Field
from wildlife.ui.theme.manager import ThemeManager


class PlaceEditor(PanelView):
    saved = Signal(object)  # Place
    removed = Signal(str)  # message
    cancelled = Signal()

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        place: Place | None = None,
        at: tuple[float, float] | None = None,  # a new place's centre, e.g. from the map
    ) -> None:
        super().__init__()
        self.ctx, self.place = ctx, place
        self.title = "Edit place" if place else "New place"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget()
        body.setObjectName("PanelBody")
        form = QVBoxLayout(body)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(14)
        self.name = QLineEdit(place.name if place else "")
        self.name.setPlaceholderText("e.g. Garden, or Rainham Marshes")
        self.f_name = _Field("Name", self.name)
        self.position = QLineEdit()
        self.position.setPlaceholderText("Grid ref like TQ 308 808, or 51.50, -0.12, or a map link")
        if place:
            self.position.setText(
                geo.grid_ref_for(place.latitude, place.longitude, 10)
                or f"{place.latitude:.5f}, {place.longitude:.5f}"
            )
        if at is not None and place is None:
            self.position.setText(geo.grid_ref_for(*at, 10) or f"{at[0]:.5f}, {at[1]:.5f}")
        self.f_position = _Field("Centre", self.position, "The middle of the place")
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._update_position_note)
        self.position.textEdited.connect(lambda _: self._timer.start())
        self.radius = QSpinBox()
        self.radius.setRange(1, 100_000)
        self.radius.setSingleStep(50)
        self.radius.setSuffix(" m")
        self.radius.setValue(place.radius_m if place else 250)
        self.f_radius = _Field(
            "Radius", self.radius, "Sightings within this distance suggest this place"
        )
        self.habitat = QComboBox()
        self.habitat.addItem("Not recorded", None)
        for h in Habitat:
            self.habitat.addItem(h.label, h)
        if place and place.habitat:
            self.habitat.setCurrentIndex(self.habitat.findData(place.habitat))
        self.favourite = QCheckBox("Favourite (shown first in lists)")
        self.favourite.setChecked(bool(place and place.is_favourite))
        self.notes = QPlainTextEdit(place.notes if place and place.notes else "")
        self.notes.setFixedHeight(80)
        self.notes.setPlaceholderText("Access, parking, best seasons…")
        for w in (
            self.f_name,
            self.f_position,
            self.f_radius,
            _Field("Default habitat", self.habitat),
            self.favourite,
            _Field("Notes", self.notes),
        ):
            form.addWidget(w)
        form.addStretch(1)
        outer.addWidget(body, 1)

        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        save = QPushButton("Save")
        save.setProperty("variant", "primary")
        save.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.cancelled.emit)
        fh.addWidget(save)
        fh.addWidget(cancel)
        fh.addStretch(1)
        if place:
            archive = QPushButton("Archive")
            archive.setProperty("variant", "ghost")
            archive.setToolTip("Hide from lists; its sightings keep the place")
            archive.clicked.connect(self._archive)
            delete = QPushButton("Delete")
            delete.setProperty("variant", "ghost")
            delete.clicked.connect(self._delete)
            fh.addWidget(archive)
            fh.addWidget(delete)
        outer.addWidget(foot)
        for edit in (self.name, self.position):
            edit.returnPressed.connect(self.save)
        self._update_position_note()

    def on_shown(self) -> None:
        QTimer.singleShot(0, self.name.setFocus)

    def _update_position_note(self) -> None:
        text = self.position.text().strip()
        if not text:
            self.f_position.set_note("The middle of the place")
            return
        parsed = geo.parse_location(text)
        if parsed is None or parsed.looks_swapped:
            self.f_position.set_note(
                "That doesn't look like a grid reference or coordinates. Example: TQ 308 808",
                "error",
            )
        else:
            ref = geo.grid_ref_for(parsed.latitude, parsed.longitude, 100)
            self.f_position.set_note(
                f"{ref or 'Outside the GB grid'} · {parsed.latitude:.5f}, {parsed.longitude:.5f}",
                "ok",
            )

    def save(self) -> None:
        parsed = geo.parse_location(self.position.text())
        if parsed is None or parsed.looks_swapped:
            self.f_position.set_note(
                "Enter the centre as a grid reference or coordinates.", "error"
            )
            self.position.setFocus()
            return
        draft = PlaceDraft(
            id=self.place.id if self.place else None,
            name=self.name.text(),
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            radius_m=self.radius.value(),
            habitat=Habitat(self.habitat.currentData()) if self.habitat.currentData() else None,
            notes=self.notes.toPlainText().strip() or None,
            is_favourite=self.favourite.isChecked(),
        )
        try:
            place = self.ctx.places.save(draft)
        except ValidationError as exc:
            for key, message in exc.fields.items():
                {"name": self.f_name, "location": self.f_position, "radius": self.f_radius}.get(
                    key, self.f_name
                ).set_note(message, "error")
            return
        self.saved.emit(place)

    def _archive(self) -> None:
        self.ctx.places.archive(self.place.id)
        self.removed.emit(f"{self.place.name} archived")

    def _delete(self) -> None:
        try:
            self.ctx.places.delete(self.place.id)
        except ConflictError as exc:
            QMessageBox.information(self, "Can't delete this place", exc.user_message)
            return
        self.removed.emit(f"{self.place.name} deleted")
