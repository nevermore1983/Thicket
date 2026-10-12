"""AppContext: opens the data folder and builds the services the UI uses.

This is the one place where the pieces are wired together, so every other
module can stay small and receive exactly what it needs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from wildlife.config.paths import DataPaths
from wildlife.data import snapshot
from wildlife.data.db import Database
from wildlife.data.migrate import migrate
from wildlife.domain.errors import DatabaseError
from wildlife.services.backup import BackupService
from wildlife.services.calendar import CalendarService
from wildlife.services.events import EventHub
from wildlife.services.export import ExportService
from wildlife.services.health import HealthService
from wildlife.services.import_history import ImportHistory
from wildlife.services.inaturalist import InaturalistImporter
from wildlife.services.map import MapService
from wildlife.services.outings import OutingService
from wildlife.services.photos import PhotoService
from wildlife.services.places import PlaceService
from wildlife.services.settings import SettingsService
from wildlife.services.sightings import SightingService
from wildlife.services.species_catalogue import SpeciesCatalogue
from wildlife.services.spreadsheet_import import SpreadsheetImporter
from wildlife.services.statistics import StatisticsService
from wildlife.services.stats import StatsService
from wildlife.services.wildlife_import import WildlifeImporter

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    paths: DataPaths
    db: Database
    events: EventHub
    settings: SettingsService
    schema_version: int
    catalogue: SpeciesCatalogue = field(init=False)
    sightings: SightingService = field(init=False)
    places: PlaceService = field(init=False)
    outings: OutingService = field(init=False)
    photos: PhotoService = field(init=False)
    backup: BackupService = field(init=False)
    stats: StatsService = field(init=False)
    calendar: CalendarService = field(init=False)
    map: MapService = field(init=False)
    statistics: StatisticsService = field(init=False)
    inaturalist: InaturalistImporter = field(init=False)
    export: ExportService = field(init=False)
    spreadsheet: SpreadsheetImporter = field(init=False)
    wildlife_import: WildlifeImporter = field(init=False)
    health: HealthService = field(init=False)
    import_history: ImportHistory = field(init=False)

    def __post_init__(self) -> None:
        self.catalogue = SpeciesCatalogue(self.db, self.events)
        self.sightings = SightingService(self.db, self.events, self.settings)
        self.places = PlaceService(self.db, self.events)
        self.outings = OutingService(self.db, self.events, self.settings)
        self.photos = PhotoService(self.paths, self.db, self.events, self.settings)
        self.backup = BackupService(self.paths, self.db, self.events, self.settings)
        self.stats = StatsService(self.db, self.settings)
        self.calendar = CalendarService(self.db, self.settings)
        self.map = MapService(self.db, self.settings)
        self.statistics = StatisticsService(self.db, self.settings)
        self.inaturalist = InaturalistImporter(
            self.paths, self.db, self.events, self.settings, self.photos
        )
        self.export = ExportService(self.paths, self.db, self.settings)
        self.wildlife_import = WildlifeImporter(self.paths, self.db, self.events, self.photos)
        self.health = HealthService(self.paths, self.db, self.backup, self.catalogue)
        self.import_history = ImportHistory(self.db, self.sightings)
        self.spreadsheet = SpreadsheetImporter(
            self.paths, self.db, self.events, self.settings, self.photos
        )

    def set_today(self, today) -> None:
        """Fix 'today' (used by tests and demos so dates are predictable)."""
        self.sightings._today = lambda: today
        self.outings._today = lambda: today
        self.stats.today = lambda: today
        self.statistics.today = lambda: today
        self.inaturalist._today = lambda: today
        self.spreadsheet._today = lambda: today

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
