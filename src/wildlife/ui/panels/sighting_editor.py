"""Add / edit a sighting. Only the species is required; everything else has a default."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import shiboken6
from PySide6.QtCore import QDate, QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    LocationMethod,
    Sex,
)
from wildlife.domain.counting import CountError, format_count, parse_count
from wildlife.domain.errors import NotFoundError, ValidationError
from wildlife.domain.models import Photo, Sighting, SightingDraft
from wildlife.domain.photo_groups import draft_from_photos
from wildlife.services.photos import SUPPORTED, ImportSummary
from wildlife.services.sightings import SaveResult, Undo
from wildlife.ui.components.common import clear_layout
from wildlife.ui.components.flow_layout import flow_box
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.components.species_picker import SpeciesPicker
from wildlife.ui.components.visuals import plural, rounded
from wildlife.ui.theme.icons import icon, pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

log = logging.getLogger(__name__)

_TIME = re.compile(r"^\s*(\d{1,2})[:.]?(\d{2})\s*$")


def normalise_time(text: str) -> str | None:
    """'930' / '9:30' / '09.30' -> '09:30'; '' -> None; anything else is returned as typed."""
    text = text.strip()
    if not text:
        return None
    if m := _TIME.match(text):
        return f"{int(m[1]):02d}:{m[2]}"
    return text


TIME_PROBLEM = "Use 24-hour time like 09:30, or leave it empty if you don't know."


def check_time_field(edit: QLineEdit, field: _Field) -> None:
    """When you leave a time box: tidy what you typed ('930' becomes '09:30'), or say
    straight away if it can't be read, rather than waiting for Save."""
    fixed = normalise_time(edit.text())
    if fixed is None:
        field.reset_note()
        return
    hour, _, minute = fixed.partition(":")
    if not (minute and hour.isdigit() and minute.isdigit() and int(hour) < 24 and int(minute) < 60):
        field.set_note(TIME_PROBLEM, "error")
        return
    if fixed != edit.text():
        edit.setText(fixed)
    field.reset_note()


_INPUTS = (QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QAbstractButton)


def _input_of(control: QWidget) -> QWidget:
    """The part of a control that takes keyboard input (the text box of the species
    picker, the first input inside a row of controls), or the control itself."""
    if isinstance(control, _INPUTS):
        return control
    if isinstance(getattr(control, "edit", None), QWidget):
        return control.edit
    return next((w for w in control.findChildren(QWidget) if isinstance(w, _INPUTS)), control)


class _Field(QWidget):
    """Label above a control, with a help/error line below it."""

    def __init__(self, label: str, control: QWidget, help_text: str = "") -> None:
        super().__init__()
        self.control = control
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        self.label = QLabel(label)
        self.label.setProperty("role", "fieldLabel")
        v.addWidget(self.label)
        v.addWidget(control)
        # Link the label to the field, so screen readers say "Date, edit" rather than "edit"
        target = _input_of(control)
        self.label.setBuddy(target)
        if not target.accessibleName() and not isinstance(target, QAbstractButton):
            target.setAccessibleName(label)  # a button keeps its own words ("Garden")
        if help_text:
            target.setAccessibleDescription(help_text)
        self.note = QLabel(help_text)
        self.note.setWordWrap(True)
        self.note.setProperty("role", "help")
        self.note.setVisible(bool(help_text))
        self._help = help_text
        v.addWidget(self.note)

    def set_note(self, text: str, tone: str = "help") -> None:
        self.note.setText(text)
        self.note.setProperty("role", tone)
        self.note.setVisible(bool(text))
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)
        self.control.setProperty("invalid", tone == "error")
        self.control.style().unpolish(self.control)
        self.control.style().polish(self.control)

    def reset_note(self) -> None:
        self.set_note(self._help)


def _maybe(enum, value):
    return None if value is None else enum(value)


def _combo(options: list[tuple[str, object]], current: object) -> QComboBox:
    box = QComboBox()
    for label, value in options:
        box.addItem(label, value)
        if explanation := getattr(value, "explanation", ""):
            box.setItemData(box.count() - 1, explanation, Qt.ItemDataRole.ToolTipRole)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


class SightingEditor(PanelView):
    saved = Signal(object, bool)  # SaveResult, add another?
    cancelled = Signal()

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        existing: Sighting | None = None,
        prefill: SightingDraft | None = None,
        photo_ids: list[int] | None = None,
    ) -> None:
        super().__init__()
        self.ctx, self.theme, self.existing = ctx, theme, existing
        self.title = "Edit sighting" if existing else "Add sighting"
        draft = (
            existing.to_draft()
            if existing
            else (prefill or SightingDraft(taxon_id=None, observed_date=None))
        )
        self._dirty = False
        self._done = False  # saved: a second save (e.g. one Enter seen twice) does nothing
        self._location_edited = False
        self._date_touched = existing is not None or (
            prefill is not None and prefill.observed_date is not None
        )
        self._original = draft
        self._photos: list[Photo] = ctx.photos.for_sighting(existing.id) if existing else []
        self._photos_before = [p.id for p in self._photos]  # for Undo, and what was removed
        self._adding_photos = 0  # imports still running (Save waits for them)

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

        self._photo_note = QLabel()
        self._photo_note.setWordWrap(True)
        self._photo_note.setProperty("role", "callout")
        self._photo_note.hide()
        form.addWidget(self._photo_note)

        # species
        self.picker = SpeciesPicker(ctx.catalogue, theme)
        if draft.taxon_id:
            self.picker.set_taxon(ctx.catalogue.get(draft.taxon_id))
        self.picker.chosen.connect(self._species_chosen)
        self.f_species = _Field("Species", self.picker)
        form.addWidget(self.f_species)

        # date + time
        today = ctx.sightings._today()
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.date.setMaximumDate(QDate(today.year, today.month, today.day))
        self.date.setMinimumDate(QDate(1900, 1, 1))
        d = draft.observed_date or today
        self.date.setDate(QDate(d.year, d.month, d.day))
        self.date.dateChanged.connect(self._on_date_changed)
        self.time = QLineEdit(
            draft.observed_time if (existing or prefill) else datetime.now().strftime("%H:%M")
        )
        if prefill and prefill.observed_time is None and prefill.observed_date not in (None, today):
            self.time.clear()
        self.time.setPlaceholderText("HH:MM")
        self.time.setMaxLength(5)
        self.time.textEdited.connect(self._mark_dirty)
        self.f_date = _Field("Date", self.date)
        self.f_time = _Field("Time", self.time, "Leave empty if you don't know")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.f_date, 3, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.f_time, 2, Qt.AlignmentFlag.AlignTop)
        form.addLayout(row)

        # outing: only shown when the date has outings; picks the obvious one by itself
        self._outing_touched = draft.outing_id is not None
        self.outing = QComboBox()
        self.outing.activated.connect(self._outing_chosen)
        self.f_outing = _Field("Outing", self.outing)
        form.addWidget(self.f_outing)
        self._fill_outings(draft.outing_id)
        self.time.editingFinished.connect(lambda: self._fill_outings())
        self.time.editingFinished.connect(self._check_time)

        # place
        self._place_id = draft.place_id if (existing or prefill) else ctx.sightings.default_place()
        # A place you (or the sighting) chose beats one worked out from a photo's GPS;
        # 'remember the last place' is only a guess, so a photo's position replaces it
        self._place_chosen = existing is not None or (
            prefill is not None and prefill.place_id is not None
        )
        self._place_box, self._place_flow = flow_box(6)
        self._build_place_chips()
        self.f_place = _Field("Place", self._place_box)
        form.addWidget(self.f_place)

        # exact position
        self.location = QLineEdit()
        self.location.setPlaceholderText(
            "Grid ref like TQ 308 808, or 51.50, -0.12, or paste a map link"
        )
        self._lat, self._lon, self._unc = draft.latitude, draft.longitude, draft.uncertainty_m
        self._method = draft.location_method
        if draft.latitude is not None:
            self.location.setText(
                geo.grid_ref_for(draft.latitude, draft.longitude, draft.uncertainty_m)
                or f"{draft.latitude:.5f}, {draft.longitude:.5f}"
            )
        self.location.textEdited.connect(self._on_location_edited)
        self._loc_timer = QTimer(self, singleShot=True, interval=250)
        self._loc_timer.timeout.connect(self._update_location_note)
        self.f_location = _Field("Exact position (optional)", self.location)
        form.addWidget(self.f_location)

        # count + evidence
        self.count = QLineEdit(
            format_count(draft.count, draft.count_qualifier).replace(",", "")
            if draft.count is not None
            else ""
        )
        if not existing and not prefill:
            self.count.setText("1")
        self.count.installEventFilter(self)  # select-all on focus, so typing replaces the default
        self.count.textEdited.connect(lambda _: (self._mark_dirty(), self._update_count_note()))
        self.evidence = _combo([(e.label, e) for e in Evidence], draft.evidence)
        self.evidence.currentIndexChanged.connect(self._mark_dirty)
        self.f_count = _Field("Count", self.count)
        self.f_evidence = _Field("Evidence", self.evidence)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.f_count, 1, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.f_evidence, 1, Qt.AlignmentFlag.AlignTop)
        form.addLayout(row)

        # photos
        self._photo_zone = _DropZone(theme, self._add_photo_files, self._browse_photos)
        # thumbnails wrap onto new rows, so many photos never widen the panel
        self._photo_strip_box, self._photo_strip = flow_box(8)
        photos_box = QWidget()
        pv = QVBoxLayout(photos_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        pv.addWidget(self._photo_zone)
        pv.addWidget(self._photo_strip_box)
        self.f_photos = _Field("Photos", photos_box)
        form.addWidget(self.f_photos)

        # notes
        self.notes = QPlainTextEdit(draft.notes or "")
        self.notes.setPlaceholderText("Behaviour, plumage, anything you want to remember")
        self.notes.setFixedHeight(84)
        self.notes.setTabChangesFocus(True)
        self.notes.textChanged.connect(self._mark_dirty)
        self.f_notes = _Field("Notes", self.notes)
        form.addWidget(self.f_notes)

        # more details
        self._more_btn = QPushButton("More details")
        self._more_btn.setProperty("variant", "ghost")
        self._more_btn.setCheckable(True)
        self._more_btn.setStyleSheet("text-align: left;")
        self._more = QWidget()
        grid = QGridLayout(self._more)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.identification = _combo([(i.label, i) for i in Identification], draft.identification)
        self.sex = _combo([("Not recorded", None)] + [(s.label, s) for s in Sex], draft.sex)
        self.life_stage = _combo(
            [("Not recorded", None)] + [(s.label, s) for s in LifeStage], draft.life_stage
        )
        self.habitat = _combo(
            [("Not recorded", None)] + [(h.label, h) for h in Habitat], draft.habitat
        )
        self.not_wild = QCheckBox("Not wild (captive, escaped or released: left out of your lists)")
        self.not_wild.setChecked(draft.is_not_wild)
        grid.addWidget(_Field("Identification", self.identification), 0, 0)
        grid.addWidget(_Field("Sex", self.sex), 0, 1)
        grid.addWidget(_Field("Life stage", self.life_stage), 1, 0)
        grid.addWidget(_Field("Habitat", self.habitat), 1, 1)
        grid.addWidget(self.not_wild, 2, 0, 1, 2)
        for w in (self.identification, self.sex, self.life_stage, self.habitat):
            w.currentIndexChanged.connect(self._mark_dirty)
        self.not_wild.toggled.connect(self._mark_dirty)
        has_details = any(
            [
                draft.sex,
                draft.life_stage,
                draft.habitat,
                draft.is_not_wild,
                draft.identification is not Identification.CERTAIN,
            ]
        )
        self._more_btn.setChecked(has_details)
        self._more.setVisible(has_details)
        self._more_btn.toggled.connect(self._toggle_more)
        form.addWidget(self._more_btn)
        form.addWidget(self._more)
        form.addStretch(1)

        # footer
        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        fh.setSpacing(8)
        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("variant", "primary")
        self.save_btn.setToolTip("Save (Enter or Ctrl+S)")
        self.save_btn.clicked.connect(lambda: self.save(another=False))
        fh.addWidget(self.save_btn)
        if not existing:
            self.another_btn = QPushButton("Save && add another")
            self.another_btn.setToolTip(
                "Save and start another with the same date and place (Ctrl+Enter)"
            )
            self.another_btn.clicked.connect(lambda: self.save(another=True))
            fh.addWidget(self.another_btn)
        fh.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.cancelled.emit)
        fh.addWidget(cancel)
        outer.addWidget(foot)

        for edit in (self.time, self.location, self.count):
            edit.returnPressed.connect(lambda: self.save(another=False))
        self._paint()
        theme.changed.connect(self._paint)
        self._update_location_note()
        self._update_count_note()
        self._refresh_photo_strip()
        if photo_ids:
            with ctx.db.connection() as conn:
                from wildlife.data.repositories import photos as photos_repo

                self._photos += [p for i in photo_ids if (p := photos_repo.get(conn, i))]
            self._refresh_photo_strip()
            self._autofill_from_photos(self._photos)

    # ---- PanelView ----------------------------------------------------------
    def on_shown(self) -> None:
        QTimer.singleShot(
            0, self.picker.focus if self.picker.taxon is None else self.count.setFocus
        )

    def can_close(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Discard changes?",
            "This sighting has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    # ---- building helpers -----------------------------------------------------
    def _paint(self) -> None:
        t = self.theme.tokens
        self._more_btn.setIcon(
            icon("chevron-down" if self._more_btn.isChecked() else "chevron-right", t.text_2, 16)
        )
        self.save_btn.setIcon(icon("check", t.accent_fg, 16))

    def _build_place_chips(self) -> None:
        layout = self._place_flow
        clear_layout(layout)
        recent = self.ctx.places.recent(3)
        if self._place_id and self._place_id not in [p.id for p in recent]:
            try:
                recent.insert(0, self.ctx.places.get(self._place_id))
            except Exception:
                self._place_id = None
        self._chips = QButtonGroup(self)
        self._chips.setExclusive(True)
        for place in recent[:4]:
            chip = QPushButton(place.name)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.setChecked(place.id == self._place_id)
            chip.clicked.connect(lambda _=False, pid=place.id: self._choose_place(pid))
            self._chips.addButton(chip)
            layout.addWidget(chip)
        other = QComboBox()
        other.setProperty("chip", True)
        other.setAccessibleName("Other place")
        other.addItem("Other place…", None)
        for place in self.ctx.places.all():
            other.addItem(place.name, place.id)
        other.activated.connect(
            lambda i: self._choose_place(other.itemData(i)) if other.itemData(i) else None
        )
        layout.addWidget(other)
        if self._place_id:
            none = QPushButton("No place")
            none.setProperty("chip", True)
            none.clicked.connect(lambda: self._choose_place(None))
            layout.addWidget(none)

    def _choose_place(self, place_id: int | None) -> None:
        """You picked a place (or 'No place'): photos won't change it any more."""
        self._place_chosen = True
        self._set_place(place_id)

    def _set_place(self, place_id: int | None) -> None:
        self._place_id = place_id
        self._mark_dirty()
        self._build_place_chips()
        self._update_location_note()

    def _toggle_more(self, on: bool) -> None:
        self._more.setVisible(on)
        self._paint()

    # ---- reactions ----------------------------------------------------------
    def _mark_dirty(self, *_) -> None:
        self._dirty = True

    def _species_chosen(self, taxon) -> None:
        self._mark_dirty()
        self.f_species.reset_note()
        if taxon is not None:
            QTimer.singleShot(0, self.count.setFocus)

    def _check_time(self) -> None:
        """Say if the time can't be read; gently point out a time later than now today
        (allowed: you may be adding it in advance, or the clock may be out)."""
        check_time_field(self.time, self.f_time)
        if self.f_time.note.property("role") == "error":
            return
        qd = self.date.date()
        text = normalise_time(self.time.text())
        today = self.ctx.sightings._today()
        if (
            text
            and date(qd.year(), qd.month(), qd.day()) == today
            and text > f"{datetime.now():%H:%M}"
        ):
            self.f_time.set_note("That's later than now. Is the time right?", "help")

    def _on_date_changed(self, _qdate) -> None:
        self._date_touched = True
        self._mark_dirty()
        self._fill_outings()

    def _fill_outings(self, selected: int | None = None) -> None:
        """List the outings on the chosen date. Until you pick one, follow the default."""
        qd = self.date.date()
        day = date(qd.year(), qd.month(), qd.day())
        if selected is None and self._outing_touched:
            selected = self.outing.currentData()
        elif selected is None:
            default = self.ctx.outings.default_for(day, normalise_time(self.time.text()))
            selected = default.id if default else None
        outings = self.ctx.outings.on_date(day)
        self.outing.blockSignals(True)
        self.outing.clear()
        self.outing.addItem("No outing", None)
        for o in outings:
            times = f" ({o.start_time}–{o.end_time or 'now'})" if o.start_time else ""
            self.outing.addItem(f"{o.display_title}{times}", o.id)
        if selected is not None and self.outing.findData(selected) < 0:
            try:  # keep an existing link to an outing on another date
                self.outing.addItem(self.ctx.outings.get(selected).display_title, selected)
            except NotFoundError:
                selected = None
        self.outing.setCurrentIndex(max(0, self.outing.findData(selected)))
        self.outing.blockSignals(False)
        self.f_outing.setVisible(self.outing.count() > 1)

    def _outing_chosen(self, _index: int) -> None:
        self._outing_touched = True
        self._mark_dirty()

    def _on_location_edited(self, _text: str) -> None:
        self._location_edited = True
        self._mark_dirty()
        self._loc_timer.start()

    def _parsed_location(self) -> geo.ParsedLocation | None:
        return geo.parse_location(self.location.text())

    def _update_location_note(self) -> None:
        text = self.location.text().strip()
        if not text:
            if self._place_id:
                place = self.ctx.places.get(self._place_id)
                self.f_location.set_note(
                    f"Without one, the sighting uses the centre of {place.name} "
                    f"(±{place.radius_m:,} m)."
                )
            else:
                self.f_location.set_note(
                    "Add a place or a position when you can; you can save without one."
                )
            return
        if not self._location_edited and self._lat is not None:
            unc = f"±{self._unc:,} m" if self._unc else ""
            self.f_location.set_note(f"{self._lat:.5f}, {self._lon:.5f} {unc}".strip(), "ok")
            return
        parsed = self._parsed_location()
        if parsed is None:
            self.f_location.set_note(
                "That doesn't look like a grid reference or coordinates. "
                "Example: TQ 308 808, or 51.50, -0.12",
                "error",
            )
        elif parsed.looks_swapped:
            self.f_location.set_note(
                f"Latitude and longitude look swapped. Did you mean "
                f"{parsed.longitude}, {parsed.latitude}?",
                "error",
            )
        else:
            # Show the position the other way round from how it was typed: a grid reference
            # for coordinates in Great Britain, coordinates otherwise (anywhere else: the US)
            ref = geo.grid_ref_for(parsed.latitude, parsed.longitude, parsed.uncertainty_m)
            coords = f"{parsed.latitude:.5f}, {parsed.longitude:.5f}"
            where = ref if ref and parsed.method != "grid_ref" else coords
            note = f"{where} · ±{parsed.uncertainty_m:,} m"
            if self._place_id is None and (
                near := self.ctx.places.nearest(parsed.latitude, parsed.longitude)
            ):
                note += f" · inside {near.name}"
            self.f_location.set_note(note, "ok")

    def _update_count_note(self) -> None:
        try:
            count = parse_count(self.count.text())
        except CountError as exc:
            self.f_count.set_note(str(exc), "error")
            return
        if count.value is None:
            self.f_count.set_note("Empty means present, not counted")
        elif count.qualifier is CountQualifier.APPROX:
            self.f_count.set_note(f"About {count.value:,}")
        elif count.qualifier is CountQualifier.AT_LEAST:
            self.f_count.set_note(f"At least {count.value:,}")
        else:
            self.f_count.set_note("“c. 200” for about 200 or “50+” for at least 50 also work")

    # ---- photos ----------------------------------------------------------------
    def _browse_photos(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED))
        files, _ = QFileDialog.getOpenFileNames(self, "Add photos", "", f"Photos ({patterns})")
        if files:
            self._add_photo_files([Path(f) for f in files])

    def _add_photo_files(self, files: list[Path]) -> None:
        self._set_adding(+1)

        def done(summary: ImportSummary) -> None:
            if not shiboken6.isValid(self) or self._done:
                log.info("Photos finished importing after the form closed: left in the Inbox")
                return
            self._set_adding(-1)
            new = [p for p in summary.photos if p.id not in {x.id for x in self._photos}]
            self._photos += new
            self._mark_dirty()
            self._refresh_photo_strip()
            self._autofill_from_photos(new)
            if summary.failed:
                names = ", ".join(name for name, _ in summary.failed[:3])
                self.f_photos.set_note(
                    f"Couldn't add {plural(len(summary.failed), 'file')}: {names}", "error"
                )

        def failed(exc: BaseException) -> None:
            if shiboken6.isValid(self):
                self._set_adding(-1)
            raise exc  # to the error reporter

        run_in_background(
            lambda: self.ctx.photos.import_files(files), on_done=done, on_error=failed
        )

    def _set_adding(self, change: int) -> None:
        """Photos being added: Save waits until they're in, so none are left out."""
        self._adding_photos += change
        busy = self._adding_photos > 0
        self._photo_zone.set_busy(busy)
        for b in (self.save_btn, getattr(self, "another_btn", None)):
            if b is not None:
                b.setEnabled(not busy)
        if not busy and self.f_photos.note.text().startswith("Still adding photos"):
            self.f_photos.reset_note()

    def _autofill_from_photos(self, photos: list[Photo]) -> None:
        """Fill empty date, time and position from the photos (rules in domain.photo_groups)."""
        filled = []
        draft = draft_from_photos(photos, self.ctx.sightings._today())
        if draft.observed_time is not None and not self._date_touched:
            day = draft.observed_date
            self.date.blockSignals(True)
            self.date.setDate(QDate(day.year, day.month, day.day))
            self.date.blockSignals(False)
            self._date_touched = True
            self.time.setText(draft.observed_time)
            from_name = any(p.taken_source == "file_name" for p in photos if p.taken_at)
            filled.append("date and time" + (" (from the file name)" if from_name else ""))
            self._fill_outings()
        if draft.latitude is not None and not self.location.text().strip():
            self._lat, self._lon, self._unc = draft.latitude, draft.longitude, draft.uncertainty_m
            self._method = draft.location_method
            self._location_edited = False
            self.location.setText(
                geo.grid_ref_for(self._lat, self._lon, self._unc)
                or f"{self._lat:.5f}, {self._lon:.5f}"
            )
            filled.append("position")
            if not self._place_chosen:
                near = self.ctx.places.nearest(self._lat, self._lon)
                self._set_place(near.id if near else None)
        if filled:
            noun = "photo" if len(photos) == 1 else "photos"
            self._photo_note.setText(f"Filled in the {' and '.join(filled)} from your {noun}.")
            self._photo_note.show()
            self._update_location_note()

    def _refresh_photo_strip(self) -> None:
        clear_layout(self._photo_strip)
        for photo in self._photos:
            thumb = self.ctx.photos.thumbnail(photo, 256)
            tile = QLabel()
            tile.setFixedSize(84, 64)
            tile.setToolTip(photo.original_name)
            if thumb:
                tile.setPixmap(
                    rounded(QPixmap(str(thumb)), 64, 8).scaled(
                        84, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding
                    )
                )
            else:
                tile.setText("Missing")
                tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            holder = QWidget()
            hv = QVBoxLayout(holder)
            hv.setContentsMargins(0, 0, 0, 0)
            hv.setSpacing(2)
            hv.addWidget(tile)
            controls = QHBoxLayout()
            controls.setSpacing(2)
            at = self._photos.index(photo)
            for text, name, step in (("‹", "Move earlier", -1), ("›", "Move later", 1)):
                move = QPushButton(text)
                move.setProperty("variant", "ghost")
                move.setFixedWidth(24)
                move.setToolTip(f"{name} (the first photo is the cover)")
                move.setAccessibleName(f"{name}: {photo.original_name}")
                move.setEnabled(0 <= at + step < len(self._photos))
                move.clicked.connect(lambda _=False, p=photo, d=step: self._move_photo(p, d))
                controls.addWidget(move)
            remove = QPushButton("Remove")
            remove.setProperty("variant", "link")
            remove.setAccessibleName(f"Remove {photo.original_name}")
            remove.clicked.connect(lambda _=False, p=photo: self._remove_photo(p))
            controls.addWidget(remove)
            hv.addLayout(controls)
            self._photo_strip.addWidget(holder)
        self._photo_zone.set_count(len(self._photos))

    def _move_photo(self, photo: Photo, step: int) -> None:
        i = self._photos.index(photo)
        j = i + step
        if 0 <= j < len(self._photos):
            self._photos[i], self._photos[j] = self._photos[j], self._photos[i]
            self._mark_dirty()
            self._refresh_photo_strip()

    def _remove_photo(self, photo: Photo) -> None:
        self._photos = [p for p in self._photos if p.id != photo.id]
        self._mark_dirty()
        self._refresh_photo_strip()

    # ---- saving -----------------------------------------------------------------
    def build_draft(self) -> tuple[SightingDraft | None, dict[str, str]]:
        errors: dict[str, str] = {}
        try:
            count = parse_count(self.count.text())
        except CountError as exc:
            errors["count"] = str(exc)
            count = None
        lat, lon, unc, method = self._lat, self._lon, self._unc, self._method
        if self._location_edited:
            text = self.location.text().strip()
            if not text:
                lat = lon = unc = method = None
            else:
                parsed = self._parsed_location()
                if parsed is None or parsed.looks_swapped:
                    errors["location"] = "Fix the position, or clear it to save without one."
                else:
                    lat, lon, unc = parsed.latitude, parsed.longitude, parsed.uncertainty_m
                    method = (
                        LocationMethod.GRID_REF
                        if parsed.method == "grid_ref"
                        else LocationMethod.TYPED
                    )
        elif lat is None and self._place_id:
            method = LocationMethod.PLACE
        qd = self.date.date()
        draft = SightingDraft(
            id=self.existing.id if self.existing else None,
            taxon_id=self.picker.taxon.id if self.picker.taxon else None,
            observed_date=date(qd.year(), qd.month(), qd.day()),
            observed_time=normalise_time(self.time.text()),
            place_id=self._place_id,
            latitude=lat,
            longitude=lon,
            uncertainty_m=unc,
            location_method=method,
            location_text=self.existing.location_text if self.existing else None,
            count=count.value if count else None,
            count_qualifier=count.qualifier if count else CountQualifier.EXACT,
            # QComboBox returns enum data as plain strings, so convert back to the codes
            evidence=Evidence(self.evidence.currentData()),
            identification=Identification(self.identification.currentData()),
            sex=_maybe(Sex, self.sex.currentData()),
            life_stage=_maybe(LifeStage, self.life_stage.currentData()),
            habitat=_maybe(Habitat, self.habitat.currentData()),
            is_not_wild=self.not_wild.isChecked(),
            outing_id=self.outing.currentData(),
            notes=self.notes.toPlainText().strip() or None,
        )
        return (None if errors else draft), errors

    def save(self, another: bool = False) -> SaveResult | None:
        if self._done:
            return None
        if self._adding_photos:
            self.f_photos.set_note("Still adding photos… Save again in a moment.", "error")
            return None
        for field in (self.f_species, self.f_date, self.f_time, self.f_place, self.f_notes):
            field.reset_note()
        self._update_location_note()
        self._update_count_note()
        draft, errors = self.build_draft()
        if draft is not None:
            try:
                result = self.ctx.sightings.save(draft)
            except ValidationError as exc:
                errors = exc.fields
            else:
                result = self._save_photos(result)
                self._dirty = False
                self._done = True  # this form has done its job (another save gets a new form)
                self.saved.emit(result, another and self.existing is None)
                return result
        targets = {
            "species": self.f_species,
            "date": self.f_date,
            "time": self.f_time,
            "location": self.f_location,
            "count": self.f_count,
            "place": self.f_place,
            "notes": self.f_notes,
        }
        first = None
        for key, message in errors.items():
            field = targets.get(key, self.f_notes)
            field.set_note(message, "error")
            first = first or field
        if first is self.f_species:
            self.picker.focus()
        elif first is not None:
            first.control.setFocus()
        return None

    def _save_photos(self, result: SaveResult) -> SaveResult:
        """Put the photos shown here on the sighting, in this order. For an edit, Undo
        then puts back the photos it had before, as well as its details."""
        sid, ids, before = result.sighting.id, [p.id for p in self._photos], self._photos_before
        removed = [i for i in before if i not in ids]
        self.ctx.photos.set_sighting_photos(sid, ids, removed)
        if not self.existing or ids == before:
            return result
        details, photos = result.undo, self.ctx.photos

        def undo() -> None:
            details.run()
            photos.set_sighting_photos(sid, before, [i for i in ids if i not in before])

        return replace(result, undo=Undo(details.description, undo))

    def keyPressEvent(self, event) -> None:
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ctrl:
            self.save(another=self.existing is None)
            return
        if event.key() == Qt.Key.Key_S and ctrl:
            self.save()
            return
        # Enter in the date box saves. Only when it truly has focus: Enter pressed in a
        # text box saves there and then reaches this form too, and must not save twice.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.date.hasFocus():
            self.save()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.count and event.type() == QEvent.Type.FocusIn:
            QTimer.singleShot(0, self.count.selectAll)  # typing replaces the default "1"
        return super().eventFilter(obj, event)


class _DropZone(QFrame):
    """'Drop photos here or click to choose' box."""

    def __init__(self, theme: ThemeManager, on_files, on_click) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme, self._on_files, self._on_click = theme, on_files, on_click
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(10)
        self._icon = QLabel()
        self._text = QLabel("Drop photos here or click to choose")
        self._text.setProperty("role", "muted")
        h.addWidget(self._icon)
        h.addWidget(self._text, 1)
        self._count = 0
        theme.changed.connect(self._paint)
        self._paint()

    def _paint(self) -> None:
        self._icon.setPixmap(pixmap("camera", self._theme.tokens.text_2, 20))

    def set_count(self, n: int) -> None:
        self._count = n
        self._text.setText(
            f"{plural(n, 'photo')} attached. Drop or click to add more."
            if n
            else "Drop photos here or click to choose"
        )

    def set_busy(self, busy: bool) -> None:
        self._text.setText("Adding photos…" if busy else self._text.text())
        if not busy:
            self.set_count(self._count)

    def mousePressEvent(self, event) -> None:
        self._on_click()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("over", True)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("over", False)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("over", False)
        self.style().polish(self)
        files = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            self._on_files(files)
