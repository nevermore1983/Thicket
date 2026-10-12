"""Automatic checks for slips that crept in during development (see the self-review list).

Each of these was found in a new file at least once before it was committed."""

import re
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "wildlife"
FILES = sorted(SRC.rglob("*.py"))


def offending(pattern: str) -> list[str]:
    rx = re.compile(pattern, re.MULTILINE)
    return [
        f"{f.relative_to(SRC)}:{text[: m.start()].count(chr(10)) + 1}"
        for f in FILES
        for text in [f.read_text(encoding="utf-8")]
        for m in rx.finditer(text)
    ]


def test_no_placeholder_functions():
    assert offending(r"^\s*def _?unused\w*\(") == []


def test_no_sql_alias_string_hacks():
    assert offending(r"""\.replace\(["']\w+\.["']""") == []


def test_no_dataclass_on_qt_classes():
    assert offending(r"^@dataclass[^\n]*\nclass \w+\(Q\w+") == []
