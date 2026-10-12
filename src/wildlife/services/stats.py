"""Summary numbers for the dashboard, life and year lists, and species profiles."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from wildlife.data.db import Database
from wildlife.data.repositories import stats as repo
from wildlife.services.settings import SettingsService


class StatsService:
    def __init__(
        self, db: Database, settings: SettingsService, today: Callable[[], date] = date.today
    ) -> None:
        self._db, self._settings, self.today = db, settings, today

    def dashboard(self) -> repo.DashboardNumbers:
        with self._db.connection() as conn:
            return repo.dashboard(conn, self.today(), self._settings.current.count_probable_ids)

    def life_list(self, year: int | None = None) -> list[repo.LifeListRow]:
        """The life list, or a year list."""
        with self._db.connection() as conn:
            return repo.life_list(conn, self._settings.current.count_probable_ids, year)

    def years_recorded(self) -> list[int]:
        with self._db.connection() as conn:
            return repo.years_recorded(conn)

    def species_profile(self, taxon_id: int) -> repo.SpeciesProfile:
        with self._db.connection() as conn:
            return repo.species_profile(conn, taxon_id)
