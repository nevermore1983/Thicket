"""Every user setting, with its default, in one place.

Only settings the user has *changed* are stored (in the database's `setting`
table, so they travel with backups). If a future version changes a default,
everyone who never touched that setting gets the new default.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class Settings:
    theme: Theme = Theme.SYSTEM
    recorder_name: str = ""
    start_page: str = "dashboard"
    remember_place_hours: int = 3
    count_probable_ids: bool = False
    show_grid_refs: bool = True
    recycle_bin_days: int = 30
    allow_online: bool = True
    backup_folder: str = ""  # empty = <data folder>\backups (same drive: choose another!)
    auto_backup: bool = True

    @classmethod
    def from_stored(cls, stored: dict[str, Any]) -> Settings:
        """Build from stored overrides, ignoring unknown or invalid values."""
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in stored:
                continue
            raw, default = stored[f.name], getattr(cls(), f.name)
            try:
                if isinstance(default, StrEnum):
                    values[f.name] = type(default)(raw)
                elif isinstance(default, bool):
                    if isinstance(raw, bool):
                        values[f.name] = raw
                elif isinstance(default, int):
                    values[f.name] = int(raw)
                elif isinstance(default, str):
                    values[f.name] = str(raw)
            except (ValueError, TypeError):
                continue  # a bad stored value falls back to the default
        return cls(**values)
