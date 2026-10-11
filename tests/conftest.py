"""Shared test fixtures: temporary data folders and databases."""

from __future__ import annotations

from pathlib import Path

import pytest

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.migrate import migrate


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "WildLife").ensure()


@pytest.fixture
def db(paths: DataPaths):
    """A fresh, fully migrated database in a temporary folder."""
    database = Database(paths.database)
    with database.connection() as conn:
        migrate(conn)
    yield database
    database.close()
