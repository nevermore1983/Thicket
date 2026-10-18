"""UK date formatting, UK clock time, and understanding dates typed into search ("May 2025")."""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAYS_LONG = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_LONG = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def fmt_date(d: date, style: str = "short") -> str:
    """short 'Sun 11 Oct 2026' · medium '11 Oct 2026' · day '11 Oct' · full 'Sunday 11 October 2026'."""
    if style == "medium":
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    if style == "day":
        return f"{d.day} {MONTHS[d.month - 1]}"
    if style == "full":
        return f"{DAYS_LONG[d.weekday()]} {d.day} {MONTHS_LONG[d.month - 1]} {d.year}"
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, months: int) -> date:
    """Same day in another month, clamped (31 Jan + 1 month = 28/29 Feb)."""
    index = d.year * 12 + d.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(d.day, calendar.monthrange(year, month + 1)[1]))


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


def week_start(d: date) -> date:
    """The Monday of d's week (UK weeks start on Monday)."""
    return d - timedelta(days=d.weekday())


def week_label(d: date) -> str:
    """'5 – 11 Oct 2026', '28 Sep – 4 Oct 2026' or '29 Dec 2025 – 4 Jan 2026'."""
    a = week_start(d)
    b = a + timedelta(days=6)
    if a.year != b.year:
        return f"{fmt_date(a, 'medium')} – {fmt_date(b, 'medium')}"
    if a.month != b.month:
        return f"{fmt_date(a, 'day')} – {fmt_date(b, 'medium')}"
    return f"{a.day} – {fmt_date(b, 'medium')}"


# ---- UK clock time -----------------------------------------------------------
def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - 6) % 7)


def uk_local(moment: datetime) -> datetime:
    """The UK wall-clock time of a moment (an aware datetime, or a naive one in UTC).

    British Summer Time (UTC+1) runs from 01:00 UTC on the last Sunday of March to
    01:00 UTC on the last Sunday of October; the rest of the year is GMT (UTC+0).
    That rule has held since 1996 and is used for every year here. Writing it out
    avoids depending on a time-zone database, which Windows' Python doesn't include.
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    summer_starts = datetime.combine(_last_sunday(moment.year, 3), time(1))
    summer_ends = datetime.combine(_last_sunday(moment.year, 10), time(1))
    return moment + timedelta(hours=1) if summer_starts <= moment < summer_ends else moment


def pc_local(moment: datetime) -> datetime:
    """This computer's wall-clock time of a moment (aware, or naive in UTC), using the
    time zone Windows is set to. For regions other than the UK (a US state can span
    two time zones; your PC knows which one you're in)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone().replace(tzinfo=None)


def local_clock(region: str) -> Callable[[datetime], datetime]:
    """How to turn a UTC moment into the clock time you saw, for a region: UK rules in
    the UK (exact whatever the PC's setting), the PC's own time zone elsewhere."""
    return uk_local if region == "uk" else pc_local


# ---- search ------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DateQuery:
    kind: Literal["day", "month", "year"]
    day: date  # the day itself, or the first day of the month/year
    label: str  # e.g. "May 2025"


_MONTH_NAMES = {name.lower(): i + 1 for i, name in enumerate(MONTHS_LONG)}
_MONTH_NAMES |= {name.lower(): i + 1 for i, name in enumerate(MONTHS)}
_MONTH_NAMES["sept"] = 9
_MONTH = "|".join(sorted(_MONTH_NAMES, key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(rf"^(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?\s+(\d{{4}})$")
_MONTH_YEAR = re.compile(rf"^({_MONTH})\.?\s+(\d{{4}})$")
_MONTH_ONLY = re.compile(rf"^({_MONTH})\.?$")
_NUMERIC = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")  # UK order: day/month/year
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_YEAR = re.compile(r"^(19\d{2}|20\d{2})$")


def parse_date_query(text: str, today: date) -> DateQuery | None:
    """'May 2025', '2025', '12 May 2025', '12/5/2025', '2025-05-12', or 'May' (the most recent May)."""
    t = " ".join(text.lower().replace(",", " ").split())
    try:
        if m := _DAY_MONTH_YEAR.match(t):
            d = date(int(m[3]), _MONTH_NAMES[m[2]], int(m[1]))
        elif m := _NUMERIC.match(t):
            d = date(int(m[3]), int(m[2]), int(m[1]))
        elif m := _ISO.match(t):
            d = date(int(m[1]), int(m[2]), int(m[3]))
        else:
            d = None
    except ValueError:
        return None  # e.g. 31 February
    if d is not None:
        return DateQuery("day", d, fmt_date(d, "full"))
    if m := _MONTH_YEAR.match(t):
        month = _MONTH_NAMES[m[1]]
        return DateQuery("month", date(int(m[2]), month, 1), f"{MONTHS_LONG[month - 1]} {m[2]}")
    if m := _MONTH_ONLY.match(t):
        month = _MONTH_NAMES[m[1]]
        year = today.year if month <= today.month else today.year - 1  # the most recent one
        return DateQuery("month", date(year, month, 1), f"{MONTHS_LONG[month - 1]} {year}")
    if m := _YEAR.match(t):
        return DateQuery("year", date(int(m[1]), 1, 1), m[1])
    return None
