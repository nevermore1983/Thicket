"""Shared test fixtures: temporary data folders, databases and a tiny species list."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.data.db import Database
from wildlife.data.migrate import migrate
from wildlife.data.repositories import taxa as taxa_repo

TODAY = date(2026, 10, 11)

# A miniature catalogue in the same format as the bundled UKSI file.
_L_BIRD = ["Animalia", "Chordata", "Aves", "Passeriformes"]
MINI_CATALOGUE = [
    {"k": "K1", "r": "kingdom", "s": "Animalia", "l": ["Animalia"]},
    {
        "k": "B0",
        "p": "K1",
        "r": "genus",
        "s": "Larus",
        "c": "Gull",
        "en": ["Seagull"],
        "l": ["Animalia", "Chordata", "Aves", "Charadriiformes", "Laridae"],
        "pr": 3,
    },
    {
        "k": "B1",
        "p": "B0",
        "r": "species",
        "s": "Larus argentatus",
        "c": "Herring Gull",
        "l": ["Animalia", "Chordata", "Aves", "Charadriiformes", "Laridae"],
        "pr": 9,
    },
    {
        "k": "R1",
        "p": "K1",
        "r": "species",
        "s": "Erithacus rubecula",
        "c": "Robin",
        "en": ["Redbreast", "European Robin"],
        "l": [*_L_BIRD, "Muscicapidae"],
        "pr": 10,
    },
    {
        "k": "R2",
        "p": "K1",
        "r": "species",
        "s": "Turdus migratorius",
        "c": "American Robin",
        "l": [*_L_BIRD, "Turdidae"],
        "pr": 6,
    },
    {
        "k": "W1",
        "p": "K1",
        "r": "species",
        "s": "Motacilla alba",
        "c": "Pied Wagtail",
        "l": [*_L_BIRD, "Motacillidae"],
        "pr": 10,
    },
    {
        "k": "W2",
        "p": "W1",
        "r": "subspecies",
        "s": "Motacilla alba yarrellii",
        "c": "Pied Wagtail (yarrellii)",
        "l": [*_L_BIRD, "Motacillidae"],
        "pr": 5,
    },
    {
        "k": "D1",
        "p": "K1",
        "r": "species",
        "s": "Sympetrum striolatum",
        "c": "Common Darter",
        "l": ["Animalia", "Arthropoda", "Insecta", "Odonata", "Libellulidae"],
        "pr": 10,
    },
    {
        "k": "P1",
        "p": "K1",
        "r": "species",
        "s": "Aglais io",
        "c": "Peacock",
        "l": ["Animalia", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae"],
        "pr": 10,
    },
    {
        "k": "M1",
        "p": "K1",
        "r": "species",
        "s": "Vulpes vulpes",
        "c": "Red Fox",
        "l": ["Animalia", "Chordata", "Mammalia", "Carnivora", "Canidae"],
        "pr": 10,
    },
    {
        "k": "X1",
        "p": "K1",
        "r": "species",
        "s": "Beetlus obscurus",
        "l": ["Animalia", "Arthropoda", "Insecta", "Coleoptera", "Carabidae"],
        "pr": 0,
    },
]


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
    context.sightings._today = lambda: TODAY
    yield context
    context.close()


def taxon_id(ctx: AppContext, scientific_name: str) -> int:
    with ctx.db.connection() as conn:
        return conn.execute(
            "SELECT id FROM taxon WHERE scientific_name = ?", (scientific_name,)
        ).fetchone()[0]
