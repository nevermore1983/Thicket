"""The sighting editor's photos: adding them (in the background), filling in the date,
time and position from them, the strip of thumbnails, and saving which are attached."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import shiboken6
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wildlife.domain import geo
from wildlife.domain.models import Photo
from wildlife.domain.photo_groups import draft_from_photos
from wildlife.services.photos import SUPPORTED, ImportSummary
from wildlife.services.sightings import SaveResult, Undo
from wildlife.ui.components.common import clear_layout
from wildlife.ui.components.visuals import plural, rounded
from wildlife.ui.workers import run_in_background

log = logging.getLogger(__name__)


class EditorPhotos:
    """Mixed into SightingEditor, whose ctx, f_photos, _photos, _photo_strip,
    _photo_zone, save buttons and date/time/location fields it uses."""

    # ---- adding and showing ----------------------------------------------------------------
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
