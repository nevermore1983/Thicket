"""Past imports: what each brought in, with a way to remove one later."""

from __future__ import annotations

from wildlife.data.db import Database
from wildlife.data.repositories import imports as repo
from wildlife.services.sightings import SightingService, Undo

SOURCE_NAMES = {
    "inaturalist": "iNaturalist",
    "csv": "Spreadsheet",
    "wildlife": "WildLife export",
}


class ImportHistory:
    def __init__(self, db: Database, sightings: SightingService) -> None:
        self._db, self._sightings = db, sightings

    def batches(self) -> list[repo.Batch]:
        with self._db.connection() as conn:
            return repo.batches(conn)

    def remove(self, batch_id: int) -> Undo | None:
        """Move an import's sightings to the recycle bin (Undo puts them back).
        Updates it made to sightings already here are kept."""
        with self._db.connection() as conn:
            ids = repo.batch_sightings(conn, batch_id)
        return self._sightings.delete(ids) if ids else None
