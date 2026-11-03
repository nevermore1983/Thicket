"""The main window's side panels: opening a sighting, an outing, a species or a
place, adding and editing them, and what happens after a save. Mixed into
MainWindow (ui/main_window.py)."""

from __future__ import annotations

import logging
from datetime import date

from wildlife.domain.codes import LocationMethod
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Outing, SightingDraft
from wildlife.services.sightings import SaveResult
from wildlife.ui.panels.outing_detail import OutingDetail
from wildlife.ui.panels.outing_editor import OutingEditor
from wildlife.ui.panels.place_editor import PlaceEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor
from wildlife.ui.panels.sighting_list import SightingListPanel
from wildlife.ui.panels.species_profile import SpeciesProfile
from wildlife.ui.photos.viewer import PhotoViewer

log = logging.getLogger(__name__)


class PanelActions:
    """Mixed into MainWindow, whose ctx, theme, panel, pages and toasts it uses."""

    # ---- sightings ------------------------------------------------------------
    def add_sighting(self, prefill: SightingDraft | None = None) -> None:
        editor = SightingEditor(
            self.ctx, self.theme, prefill=prefill if isinstance(prefill, SightingDraft) else None
        )
        self._wire_editor(editor)
        self.panel.show_view(editor)

    def open_sighting(self, sighting_id: int, push: bool = False) -> None:
        detail = SightingDetail(self.ctx, self.theme, sighting_id)
        detail.edit_requested.connect(self.edit_sighting)
        detail.delete_requested.connect(self.delete_sighting)
        detail.show_on_map.connect(self.show_sighting_on_map)
        detail.view_photo.connect(self.view_sighting_photos)
        self.panel.show_view(detail, push=push and self.panel.isVisible())

    def edit_sighting(self, sighting_id: int) -> None:
        editor = SightingEditor(self.ctx, self.theme, existing=self.ctx.sightings.get(sighting_id))
        self._wire_editor(editor)
        self.panel.show_view(editor, push=isinstance(self.panel.current(), SightingDetail))

    def _wire_editor(self, editor: SightingEditor) -> None:
        editor.saved.connect(lambda result, another: self._saved(editor, result, another))
        editor.cancelled.connect(self._close_or_back)

    def _saved(self, editor: SightingEditor, result: SaveResult, another: bool) -> None:
        s = result.sighting
        verb = "saved" if result.created else "updated"
        message = f"{s.display_name} {verb}" + (
            " · ★ new species for your life list!" if result.is_lifer else ""
        )
        self._toast(
            message,
            result.undo.run,
            open_=(lambda: self.open_sighting(s.id)) if result.created else None,
        )
        if another:
            prefill = SightingDraft(
                taxon_id=None,
                observed_date=s.observed_date,
                observed_time=s.observed_time,
                place_id=s.place_id,
                outing_id=s.outing_id,
            )
            fresh = SightingEditor(self.ctx, self.theme, prefill=prefill)
            self._wire_editor(fresh)
            self.panel.replace_top(fresh)
        else:
            self._close_or_back()

    def _close_or_back(self) -> None:
        view = self.panel.current()
        if view is not None:
            view._dirty = False  # already saved or deliberately cancelled
        self.panel.back()

    def delete_sighting(self, sighting_id: int) -> None:
        s = self.ctx.sightings.get(sighting_id)
        undo = self.ctx.sightings.delete([sighting_id])
        self.panel.close_panel()
        self._toast(f"{s.display_name} moved to the recycle bin", undo.run)

    # ---- outings ------------------------------------------------------------------
    def open_outing(self, outing_id: int, push: bool = False) -> None:
        detail = OutingDetail(self.ctx, self.theme, outing_id)
        detail.open_sighting.connect(lambda sid: self.open_sighting(sid, push=True))
        detail.edit_requested.connect(self.edit_outing)
        detail.delete_requested.connect(self.delete_outing)
        detail.end_requested.connect(self.end_outing)
        detail.add_requested.connect(self.add_to_outing)
        detail.show_list.connect(lambda flt: (self.panel.close_panel(), self.show_sightings(flt)))
        detail.show_map.connect(lambda flt: (self.panel.close_panel(), self.show_map(flt)))
        self.panel.show_view(detail, push=push and self.panel.isVisible())

    def new_outing(self, day: date | None) -> None:
        editor = OutingEditor(self.ctx, self.theme, on_date=day)
        self._wire_outing_editor(editor)
        self.panel.show_view(editor)

    def edit_outing(self, outing_id: int) -> None:
        editor = OutingEditor(self.ctx, self.theme, existing=self.ctx.outings.get(outing_id))
        self._wire_outing_editor(editor)
        self.panel.show_view(editor, push=isinstance(self.panel.current(), OutingDetail))

    def _wire_outing_editor(self, editor: OutingEditor) -> None:
        def saved(outing: Outing, undo) -> None:
            created = editor.existing is None
            self._toast(f"{outing.display_title} {'saved' if created else 'updated'}", undo.run)
            if created:
                self.panel.close_panel()
                self.open_outing(outing.id)
            else:
                self._close_or_back()

        editor.saved.connect(saved)
        editor.cancelled.connect(self._close_or_back)

    def start_outing(self) -> None:
        place = self.ctx.sightings.default_place()
        outing = self.ctx.outings.start(place_id=place)
        self._toast(f"Outing started at {outing.start_time}. New sightings today join it.", None)
        self.open_outing(outing.id)

    def end_outing(self, outing_id: int) -> None:
        outing = self.ctx.outings.end(outing_id)
        self._toast(f"{outing.display_title} ended at {outing.end_time}", None)
        self.panel.close_panel()

    def add_to_outing(self, outing: Outing) -> None:
        self.add_sighting(
            SightingDraft(
                taxon_id=None,
                observed_date=outing.outing_date,
                place_id=outing.place_id,
                outing_id=outing.id,
            )
        )

    def delete_outing(self, outing_id: int) -> None:
        title = self.ctx.outings.get(outing_id).display_title
        undo = self.ctx.outings.delete(outing_id)
        self.panel.close_panel()
        self._toast(f"{title} deleted · its sightings are kept", undo.run)

    def _update_outing_chip(self) -> None:
        live = self.ctx.outings.in_progress()
        self._live_outing = live.id if live else None
        self.outing_chip.setVisible(live is not None)
        if live:
            where = live.place_name or live.title or "Outing"
            self.outing_chip.setText(
                f"●  {where} · since {live.start_time} · {live.sightings:,} seen"
            )

    # ---- species -----------------------------------------------------------------
    def open_species(self, taxon_id: int) -> None:
        profile = SpeciesProfile(self.ctx, self.theme, taxon_id)
        profile.show_sightings.connect(
            lambda flt: (self.panel.close_panel(), self.show_sightings(flt))
        )
        profile.show_map.connect(lambda flt: (self.panel.close_panel(), self.show_map(flt)))
        profile.view_photos.connect(self._view_photos)
        self.panel.show_view(profile)

    def _view_photos(self, photo_ids: list[int], index: int) -> None:
        photos = [self.ctx.photos.get(i) for i in photo_ids]
        PhotoViewer(self.ctx, self.theme, photos, index, parent=self).open_full()

    # ---- photos ------------------------------------------------------------------
    def add_from_photos(self, photo_ids: list[int]) -> None:
        """'Create sighting' from Inbox photos: date, time and position come from them."""
        editor = SightingEditor(self.ctx, self.theme, photo_ids=photo_ids)
        self._wire_editor(editor)
        self.panel.show_view(editor)

    def view_sighting_photos(self, sighting_id: int, index: int) -> None:
        s = self.ctx.sightings.get(sighting_id)
        photos = self.ctx.photos.for_sighting(sighting_id)
        viewer = PhotoViewer(
            self.ctx,
            self.theme,
            photos,
            index,
            sighting_id=sighting_id,
            titles=[s.display_name] * len(photos),
            parent=self,
        )
        viewer.open_full()

    # ---- map ---------------------------------------------------------------------
    def show_map(self, flt: SightingFilter) -> None:
        """Open the map showing these sightings (e.g. one day or one outing)."""
        self.go("map")
        self.map_page.set_filter(flt)

    def show_sighting_on_map(self, s) -> None:
        self.panel.close_panel()
        self.go("map")
        self.map_page.show_location(s.eff_latitude, s.eff_longitude)

    def show_sighting_list(self, ids: list[int]) -> None:
        panel = SightingListPanel(self.ctx, self.theme, ids, "Sightings here")
        panel.open_sighting.connect(lambda sid: self.open_sighting(sid, push=True))
        self.panel.show_view(panel)

    def add_at(self, lat: float, lon: float, uncertainty_m: int) -> None:
        self.add_sighting(
            SightingDraft(
                taxon_id=None,
                observed_date=None,
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                uncertainty_m=uncertainty_m,
                location_method=LocationMethod.MAP,
            )
        )

    # ---- places -----------------------------------------------------------------
    def edit_place(self, place_id: int | None, at: tuple[float, float] | None = None) -> None:
        editor = PlaceEditor(
            self.ctx, self.theme, self.ctx.places.get(place_id) if place_id else None, at=at
        )
        editor.saved.connect(
            lambda place: (self._toast(f"{place.name} saved", None), self.panel.close_panel())
        )
        editor.removed.connect(
            lambda message: (self._toast(message, None), self.panel.close_panel())
        )
        editor.cancelled.connect(self.panel.close_panel)
        self.panel.show_view(editor)
