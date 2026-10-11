"""Understanding typed counts: '3', 'c. 200', '~40', '50+', or blank."""

from __future__ import annotations

import re
from dataclasses import dataclass

from wildlife.domain.codes import CountQualifier

_APPROX = re.compile(r"^(?:c\.?|ca\.?|circa|about|approx\.?|~)\s*(\d+)$", re.IGNORECASE)
_AT_LEAST = re.compile(r"^(\d+)\s*\+$|^(?:at least|min\.?|>=?)\s*(\d+)$", re.IGNORECASE)
MAX_COUNT = 10_000_000


@dataclass(frozen=True, slots=True)
class Count:
    value: int | None  # None = present, not counted
    qualifier: CountQualifier

    def __str__(self) -> str:
        return format_count(self.value, self.qualifier)


class CountError(ValueError):
    pass


def parse_count(text: str) -> Count:
    text = (text or "").strip()
    if not text:
        return Count(None, CountQualifier.EXACT)
    if m := _APPROX.match(text):
        return _checked(int(m[1]), CountQualifier.APPROX)
    if m := _AT_LEAST.match(text):
        return _checked(int(m[1] or m[2]), CountQualifier.AT_LEAST)
    if text.isdigit():
        return _checked(int(text), CountQualifier.EXACT)
    raise CountError("Use a number, “c. 200” for about 200, or “50+” for at least 50")


def _checked(value: int, qualifier: CountQualifier) -> Count:
    if value < 1:
        raise CountError("The count must be 1 or more. Leave it empty if you didn't count.")
    if value > MAX_COUNT:
        raise CountError("That count looks too large.")
    return Count(value, qualifier)


def format_count(value: int | None, qualifier: CountQualifier | str = CountQualifier.EXACT) -> str:
    if value is None:
        return "Present"
    if qualifier == CountQualifier.APPROX:
        return f"c. {value:,}"
    if qualifier == CountQualifier.AT_LEAST:
        return f"{value:,}+"
    return f"{value:,}"
