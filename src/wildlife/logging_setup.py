"""Logging: full details go to rotating UTF-8 log files, never to the user."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, debug: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # Explicit UTF-8: the Windows default (cp1252) can't write many characters.
    file_handler = RotatingFileHandler(
        log_dir / "wildlife.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if sys.stderr is not None and not getattr(sys, "frozen", False):  # console only when developing
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    logging.captureWarnings(True)
