"""Where Thicket keeps its data on disk.

The program and the user's data live in different places, so reinstalling or
upgrading the app never touches the data. Default data folder:
%LOCALAPPDATA%\\WildLife. For tests and demos, set WILDLIFE_DATA_DIR.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "WildLife"  # Thicket's first name: the data folder keeps it, so upgrades find it


def default_data_root() -> Path:
    if override := os.environ.get("WILDLIFE_DATA_DIR"):
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "wildlife.db"

    @property
    def photos(self) -> Path:
        return self.root / "photos"

    @property
    def thumbnails(self) -> Path:
        return self.root / "thumbnails"

    @property
    def maps(self) -> Path:
        return self.root / "maps"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def internal_backups(self) -> Path:
        """Safety copies made before upgrades/restores (separate from user backups)."""
        return self.root / "safety-copies"

    def ensure(self) -> DataPaths:
        for folder in (
            self.root,
            self.photos,
            self.thumbnails,
            self.maps,
            self.logs,
            self.internal_backups,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        return self

    def is_cloud_synced(self) -> bool:
        """True if the live data sits inside OneDrive/Dropbox/Google Drive (a risk for SQLite)."""
        markers = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")
        text = str(self.root).lower()
        if any(m in text for m in markers):
            return True
        onedrive = os.environ.get("ONEDRIVE")  # Windows env names are case-insensitive
        return bool(onedrive) and str(self.root).lower().startswith(onedrive.lower())
