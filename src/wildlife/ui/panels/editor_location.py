"""The sighting editor's exact position: typing it, choosing it on a map, and the note
under it saying what it means (a grid reference, how precise, which place)."""

from __future__ import annotations

from wildlife.domain import geo
from wildlife.domain.codes import (
    LocationMethod,
)


class EditorLocation:
    """Mixed into SightingEditor, whose ctx, theme, location, f_location, _lat, _lon,
    _unc, _method, _place_id and _place_chosen it uses."""

    def _on_location_edited(self, _text: str) -> None:
        self._location_edited = True
        self._mark_dirty()
        self._loc_timer.start()

    def _choose_on_map(self) -> None:
        """Open the map on the position typed or found so far (or the place's centre), and
        use the spot you click."""
        from wildlife.ui.map_picker import MapPicker  # loads the browser engine: only now

        start, zoom = self._map_start()
        picker = MapPicker(self.ctx, self.theme, start, zoom, parent=self.window())
        try:
            if picker.exec() == MapPicker.DialogCode.Accepted and picker.position:
                self.use_map_position(*picker.position)
        finally:
            picker.deleteLater()

    def _map_start(self) -> tuple[tuple[float, float] | None, float]:
        """Where the map opens: the position in the box, else the chosen place."""
        if self._location_edited:
            parsed = self._parsed_location()
            if parsed is not None and not parsed.looks_swapped:
                return (parsed.latitude, parsed.longitude), 15
        elif self._lat is not None:
            return (self._lat, self._lon), 15
        if self._place_id:
            place = self.ctx.places.get(self._place_id)
            zoom = 15 if place.radius_m <= 250 else 13 if place.radius_m <= 2_000 else 11
            return (place.latitude, place.longitude), zoom
        return None, 15

    def use_map_position(self, lat: float, lon: float, uncertainty_m: int) -> None:
        """Fill in a position chosen on the map. Like a photo's position, it also picks
        the place it's in, unless you chose a place yourself."""
        self._lat, self._lon, self._unc = lat, lon, uncertainty_m
        self._method = LocationMethod.MAP
        self._location_edited = False
        self.location.setText(geo.grid_ref_for(lat, lon, uncertainty_m) or f"{lat:.5f}, {lon:.5f}")
        self._mark_dirty()
        if not self._place_chosen:
            near = self.ctx.places.nearest(lat, lon)
            self._set_place(near.id if near else None)
        self._update_location_note()

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
