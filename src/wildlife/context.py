"""AppContext: opens the data folder and builds the services the UI uses.

This is the one place where the pieces are wired together, so every other
module can stay small and receive exactly what it needs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from wildlife.config.paths import DataPaths
from wildlife.data import snapshot
from wildlife.data.db import Database
from wildlife.data.migrate import migrate
from wildlife.domain.errors import DatabaseError
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    paths: DataPaths
    db: Database
    events: EventHub
    settings: SettingsService
    schema_version: int

    @classmethod
    def open(cls, paths: DataPaths) -> AppContext:
        paths.ensure()
        db = Database(paths.database)
        try:
            with db.connection() as conn:
                check = conn.execute("PRAGMA quick_check").fetchone()[0]
                if check != "ok":
                    raise DatabaseError(
                        "Your WildLife data file looks damaged. You can restore it from a backup.",
                        detail=f"quick_check: {check}",
                    )

                def safety_copy(old: int, new: int) -> None:
                    dest = paths.internal_backups / snapshot.timestamped_name(
                        f"before-upgrade-v{old}-to-v{new}"
                    )
                    snapshot.take_snapshot(conn, dest)
                    result = snapshot.verify(dest)
                    if not result.ok:
                        raise DatabaseError(
                            "Couldn't make a safety copy before upgrading, so nothing was changed.",
                            detail=str(result),
                        )
                    log.info("Safety copy before upgrade: %s", dest)

                version = migrate(conn, backup=safety_copy)
        except Exception:
            db.close()
            raise
        events = EventHub()
        log.info("Opened %s (schema v%s)", paths.database, version)
        return cls(paths, db, events, SettingsService(db, events), version)

    def close(self) -> None:
        self.db.close()
