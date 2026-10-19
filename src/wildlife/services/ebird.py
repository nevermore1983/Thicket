"""Importing an eBird export: the full "Download My Data" or a life/year list.

The file is read into ordinary import records (see `domain.ebird`) and goes through the
shared import pipeline (`services.importer`): preview, then import as one batch that
can be undone. Each record keeps its checklist and species, so importing a newer
export later only adds what's new.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wildlife.domain.ebird import SOURCE, read_file
from wildlife.services.importer import ImportPlan, RecordImporter


class EbirdImporter(RecordImporter):
    def preview(
        self, path: Path, progress: Callable[[int, int], None] = lambda d, t: None
    ) -> ImportPlan:
        return self.preview_records(read_file(path), path.name, SOURCE, progress)
