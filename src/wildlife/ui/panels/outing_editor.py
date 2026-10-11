"""Add / edit an outing: when and where, the weather, and whether it was a complete list."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.codes import Visibility, Weather, Wind
from wildlife.domain.errors import ValidationError
from wildlife.domain.models import Outing, OutingDraft
from wildlife.domain.validation import validate_outing
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.panels.sighting_editor import _combo, _Field, _maybe, normalise_time
from wildlife.ui.theme.manager import ThemeManager


def parse_temperature(text: str) -> float | None:
    """'12', '12.5', '-3', '12 °C', '12c' -> number; '' -> None. Raises ValueError otherwise."""
    cleaned = text.strip().lower().replace("°", "").replace("c", "").replace("−", "-").strip()
    return float(cleaned) if cleaned else None


class OutingEditor(PanelView):
    saved = Signal(object, object)  # Outing, Undo
    cancelled = Signal()

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        existing: Outing | None = None,
        on_date: date | None = None,
    ) -> None:
        super().__init__()
        self.ctx, self.theme, self.existing = ctx, theme, existing
        self.title = "Edit outing" if existing else "New outing"
        today = ctx.sightings._today()
        draft = existing.to_draft() if existing else OutingDraft(outing_date=on_date or today)
        self._dirty = False

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
        outer.addWidget(scroll, 1)
        form = QVBoxLayout(body)
        form.setContentsMargins(18, 16, 18, 24)
        form.setSpacing(14)

        self.title_edit = QLineEdit(draft.title or "")
        self.title_edit.setPlaceholderText("Optional, e.g. Dawn chorus walk")
        self.f_title = _Field("Title", self.title_edit, "Left empty, the place and date are used")
        form.addWidget(self.f_title)

        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.date.setMaximumDate(QDate(today.year, today.month, today.day))
        self.date.setMinimumDate(QDate(1900, 1, 1))
        d = draft.outing_date or today
        self.date.setDate(QDate(d.year, d.month, d.day))
        self.start = QLineEdit(draft.start_time or "")
        self.end = QLineEdit(draft.end_time or "")
        for edit in (self.start, self.end):
            edit.setPlaceholderText("HH:MM")
            edit.setMaxLength(5)
        self.f_date = _Field("Date", self.date)
        self.f_start = _Field("Start", self.start)
        self.f_end = _Field("End", self.end)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.f_date, 2, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.f_start, 1, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.f_end, 1, Qt.AlignmentFlag.AlignTop)
        form.addLayout(row)

        self.place = QComboBox()
        self.place.addItem("No place", None)
        for place in ctx.places.all():
            self.place.addItem(place.name, place.id)
        self.place.setCurrentIndex(max(0, self.place.findData(draft.place_id)))
        self.f_place = _Field("Place", self.place)
        form.addWidget(self.f_place)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.weather = _combo(
            [("Not recorded", None)] + [(w.label, w) for w in Weather], draft.weather
        )
        self.temperature = QLineEdit(
            "" if draft.temperature_c is None else f"{draft.temperature_c:g}"
        )
        self.temperature.setPlaceholderText("°C")
        self.wind = _combo([("Not recorded", None)] + [(w.label, w) for w in Wind], draft.wind)
        self.visibility = _combo(
            [("Not recorded", None)] + [(v.label, v) for v in Visibility], draft.visibility
        )
        self.f_weather = _Field("Weather", self.weather)
        self.f_temperature = _Field("Temperature (°C)", self.temperature)
        grid.addWidget(self.f_weather, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.f_temperature, 0, 1, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(_Field("Wind", self.wind), 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(_Field("Visibility", self.visibility), 1, 1, Qt.AlignmentFlag.AlignTop)
        form.addLayout(grid)

        self.complete = QCheckBox("Complete list: I recorded every species I identified")
        self.complete.setToolTip(
            "Complete lists show what was absent as well as present, which makes them "
            "more useful for surveys."
        )
        self.complete.setChecked(draft.is_complete_list)
        form.addWidget(self.complete)
        self.notes = QPlainTextEdit(draft.notes or "")
        self.notes.setFixedHeight(80)
        self.notes.setPlaceholderText("Route, conditions, who you were with…")
        self.f_notes = _Field("Notes", self.notes)
        form.addWidget(self.f_notes)
        form.addStretch(1)

        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("variant", "primary")
        self.save_btn.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.cancelled.emit)
        fh.addWidget(self.save_btn)
        fh.addStretch(1)
        fh.addWidget(cancel)
        outer.addWidget(foot)

        for edit in (self.title_edit, self.start, self.end, self.temperature):
            edit.textEdited.connect(self._mark_dirty)
            edit.returnPressed.connect(self.save)
        for box in (self.place, self.weather, self.wind, self.visibility):
            box.currentIndexChanged.connect(self._mark_dirty)
        self.date.dateChanged.connect(self._mark_dirty)
        self.complete.toggled.connect(self._mark_dirty)
        self.notes.textChanged.connect(self._mark_dirty)

    # ---- PanelView -------------------------------------------------------------------
    def on_shown(self) -> None:
        QTimer.singleShot(0, self.title_edit.setFocus)

    def can_close(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Discard changes?",
            "This outing has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _mark_dirty(self, *_) -> None:
        self._dirty = True

    # ---- saving --------------------------------------------------------------------------
    def build_draft(self) -> tuple[OutingDraft, dict[str, str]]:
        """The form as a draft, plus problems found while reading it (an unreadable
        temperature is left out of the draft so the other rules can still be checked)."""
        errors: dict[str, str] = {}
        try:
            temperature = parse_temperature(self.temperature.text())
        except ValueError:
            errors["temperature"] = "Enter a number, like 12 or -2.5, or leave it empty."
            temperature = None
        qd = self.date.date()
        draft = OutingDraft(
            id=self.existing.id if self.existing else None,
            outing_date=date(qd.year(), qd.month(), qd.day()),
            start_time=normalise_time(self.start.text()),
            end_time=normalise_time(self.end.text()),
            place_id=self.place.currentData(),
            title=self.title_edit.text().strip() or None,
            # QComboBox returns enum data as plain strings, so convert back to the codes
            weather=_maybe(Weather, self.weather.currentData()),
            temperature_c=temperature,
            wind=_maybe(Wind, self.wind.currentData()),
            visibility=_maybe(Visibility, self.visibility.currentData()),
            is_complete_list=self.complete.isChecked(),
            notes=self.notes.toPlainText().strip() or None,
        )
        return draft, errors

    def save(self) -> None:
        fields = {
            "title": self.f_title,
            "date": self.f_date,
            "start": self.f_start,
            "end": self.f_end,
            "place": self.f_place,
            "temperature": self.f_temperature,
        }
        for f in fields.values():
            f.reset_note()
        draft, errors = self.build_draft()
        if errors:  # report every problem at once, not one per attempt
            errors = validate_outing(draft, self.ctx.sightings._today()) | errors
        else:
            try:
                outing, undo = self.ctx.outings.save(draft)
            except ValidationError as exc:
                errors = exc.fields
            else:
                self._dirty = False
                self.saved.emit(outing, undo)
                return
        first = None
        for key, message in errors.items():
            target = fields.get(key, self.f_notes)
            target.set_note(message, "error")
            first = first or target
        if first is not None:
            first.control.setFocus()
