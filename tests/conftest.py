"""Shared test fixtures: temporary data folders, databases and a tiny species list."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import MINI_CATALOGUE, TODAY
from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.data.db import Database
from wildlife.data.migrate import migrate
from wildlife.data.repositories import taxa as taxa_repo


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


@pytest.fixture
def ctx(paths: DataPaths):
    """A fully opened app context with the mini catalogue installed and a fixed 'today'."""
    context = AppContext.open(paths)
    with context.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE)
    context.set_today(TODAY)
    yield context
    _wait_for_background_work()
    context.close()


def _wait_for_background_work() -> None:
    """As the app does at exit: background jobs finish before the database closes."""
    import sys

    if "PySide6.QtCore" in sys.modules:
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(30_000)
