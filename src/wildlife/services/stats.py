"""Summary numbers for the dashboard and the life list."""

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

    def life_list(self) -> list[repo.LifeListRow]:
        with self._db.connection() as conn:
            return repo.life_list(conn, self._settings.current.count_probable_ids)
