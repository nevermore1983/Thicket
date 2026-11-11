"""Past imports: what each brought in, with a way to remove one later."""

from __future__ import annotations

from wildlife.data.db import Database
from wildlife.data.repositories import imports as repo
from wildlife.data.repositories import outings as outings_repo
from wildlife.services.events import EventHub
from wildlife.services.sightings import SightingService, Undo

SOURCE_NAMES = {
    "inaturalist": "iNaturalist",
    "ebird": "eBird",
    "csv": "Spreadsheet",
    "wildlife": "Thicket export",
}


class ImportHistory:
    def __init__(self, db: Database, sightings: SightingService, events: EventHub) -> None:
        self._db, self._sightings, self._events = db, sightings, events

    def batches(self) -> list[repo.Batch]:
        with self._db.connection() as conn:
            return repo.batches(conn)

    def remove(self, batch_id: int) -> Undo | None:
        """Move an import's sightings to the recycle bin (Undo puts them back), and the
        outings it made for them (eBird checklists) once they're left empty. Updates it
        made to sightings already here are kept."""
        with self._db.connection() as conn:
            ids = repo.batch_sightings(conn, batch_id)
        if not ids:
            return None
        sightings_undo = self._sightings.delete(ids)
        with self._db.transaction() as conn:
            emptied = outings_repo.emptied_by_batch(conn, batch_id)
            for outing_id in emptied:
                outings_repo.soft_delete(conn, outing_id)
        if emptied:
            self._events.publish("outings", tuple(emptied))

        def undo() -> None:
            with self._db.transaction() as conn:
                for outing_id in emptied:
                    outings_repo.restore(conn, outing_id)
            sightings_undo.run()
            if emptied:
                self._events.publish("outings", tuple(emptied))

        return Undo(sightings_undo.description, undo)
