"""Importing sightings from a spreadsheet (CSV): read → map columns → preview → import.

The rows go through the shared import pipeline (`services.importer`), so names are
matched the same way as for iNaturalist, duplicates of sightings you already have are
left out, and the whole import can be undone in one go.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wildlife.domain.csv_import import SOURCE, Table, read_table, to_records
from wildlife.domain.regions import region
from wildlife.services.importer import ImportPlan, RecordImporter


class SpreadsheetImporter(RecordImporter):
    def read(self, path: Path) -> Table:
        return read_table(path)

    def preview(
        self,
        table: Table,
        mapping: dict[str, int],
        progress: Callable[[int, int], None] = lambda d, t: None,
        month_first: bool | None = None,
    ) -> ImportPlan:
        """month_first: how numeric dates are written (None: the region's way; US
        month/day, UK day/month)."""
        if month_first is None:
            month_first = region(self.region()).month_first
        records = to_records(table, mapping, month_first)
        return self.preview_records(records, table.name, SOURCE, progress)
