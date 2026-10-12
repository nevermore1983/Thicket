"""Importing sightings from a spreadsheet (CSV): read → map columns → preview → import.

The rows go through the shared import pipeline (`services.importer`), so names are
matched the same way as for iNaturalist, duplicates of sightings you already have are
left out, and the whole import can be undone in one go.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wildlife.domain.csv_import import SOURCE, Table, read_table, to_records
from wildlife.services.importer import ImportPlan, RecordImporter


class SpreadsheetImporter(RecordImporter):
    def read(self, path: Path) -> Table:
        return read_table(path)

    def preview(
        self,
        table: Table,
        mapping: dict[str, int],
        progress: Callable[[int, int], None] = lambda d, t: None,
    ) -> ImportPlan:
        return self.preview_records(to_records(table, mapping), table.name, SOURCE, progress)
