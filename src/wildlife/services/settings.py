"""Reading and changing user settings."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from wildlife.config.settings import Settings
from wildlife.data.db import Database
from wildlife.data.repositories import settings as repo
from wildlife.services.events import EventHub


class SettingsService:
    def __init__(self, db: Database, events: EventHub) -> None:
        self._db, self._events = db, events
        with db.connection() as conn:
            self._current = Settings.from_stored(repo.load_all(conn))

    @property
    def current(self) -> Settings:
        return self._current

    def update(self, **changes: Any) -> Settings:
        """Change one or more settings; values equal to the default are stored as 'unset'."""
        new = replace(self._current, **changes)  # raises TypeError for unknown names
        defaults = Settings()
        with self._db.transaction() as conn:
            for key in changes:
                value = getattr(new, key)
                if value == getattr(defaults, key):
                    repo.reset(conn, key)
                else:
                    repo.save(conn, key, value)
        self._current = new
        self._events.publish("settings")
        return new
