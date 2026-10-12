"""The numbers behind the Statistics page, for a period and the shared filter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from wildlife.data.db import Database
from wildlife.data.repositories import statistics as repo
from wildlife.domain.dates import add_years, fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.services.settings import SettingsService

TOP = 10


@dataclass(frozen=True, slots=True)
class Period:
    key: str  # 'year', 'last', 'all' or 'custom'
    start: date | None
    end: date | None
    label: str

    @classmethod
    def this_year(cls, today: date) -> Period:
        return cls("year", date(today.year, 1, 1), today, str(today.year))

    @classmethod
    def last_year(cls, today: date) -> Period:
        y = today.year - 1
        return cls("last", date(y, 1, 1), date(y, 12, 31), str(y))

    @classmethod
    def all_time(cls) -> Period:
        return cls("all", None, None, "All time")

    @classmethod
    def custom(cls, start: date, end: date) -> Period:
        start, end = min(start, end), max(start, end)
        return cls("custom", start, end, f"{fmt_date(start, 'medium')} – {fmt_date(end, 'medium')}")

    @property
    def is_year(self) -> bool:
        return self.key in ("year", "last")

    def applied(self, flt: SightingFilter) -> SightingFilter:
        """The filter with this period's dates (the period replaces any dates in the filter)."""
        return flt.with_(date_from=self.start, date_to=self.end)


@dataclass(frozen=True, slots=True)
class Curve:
    label: str  # '2026'
    points: list[tuple[int, int]]  # (days since 1 Jan or the period's start, species so far)


@dataclass(frozen=True, slots=True)
class Growth:
    origin: date  # day 0 of the x axis
    days: int  # length of the x axis
    curves: list[Curve]  # the period first, then the year before (when comparing)
    by_day_of_year: bool  # True when curves from different years share a Jan-Dec axis


@dataclass(frozen=True, slots=True)
class Statistics:
    period: Period
    summary: repo.Summary
    growth: Growth
    categories: list[repo.CategoryRow]
    seasons: dict[tuple[int, int], int]
    hours: list[int]
    top_by_sightings: list[repo.SpeciesRow]
    top_by_individuals: list[repo.SpeciesRow]
    places: list[repo.PlaceRow]
    months: dict[int, list[int]]  # year -> different species in each month (two years)
    firsts: list[repo.FirstRow]


def cumulative(first_dates: list[date], origin: date) -> list[tuple[int, int]]:
    """Running species total as steps: one point per day a new species appeared."""
    points: list[tuple[int, int]] = []
    for n, day in enumerate(sorted(first_dates), start=1):
        x = (day - origin).days
        if points and points[-1][0] == x:
            points[-1] = (x, n)
        else:
            points.append((x, n))
    return points


class StatisticsService:
    def __init__(
        self, db: Database, settings: SettingsService, today: Callable[[], date] = date.today
    ) -> None:
        self._db, self._settings, self.today = db, settings, today

    @property
    def _probable(self) -> bool:
        return self._settings.current.count_probable_ids

    def statistics(self, flt: SightingFilter, period: Period) -> Statistics:
        scoped = period.applied(flt)
        probable = self._probable
        with self._db.connection() as conn:
            summary = repo.summary(conn, scoped, probable)
            species = repo.species_totals(conn, scoped)
            growth = self._growth(conn, flt, period)
            end_year = (period.end or self.today()).year
            months = {
                y: repo.species_per_month(conn, flt, y, probable) for y in (end_year, end_year - 1)
            }
            return Statistics(
                period=period,
                summary=summary,
                growth=growth,
                categories=repo.by_category(conn, scoped, probable),
                seasons=repo.seasons(conn, scoped),
                hours=repo.hours(conn, scoped),
                top_by_sightings=sorted(species, key=lambda r: (-r.sightings, r.name))[:TOP],
                top_by_individuals=sorted(species, key=lambda r: (-r.individuals, r.name))[:TOP],
                places=repo.places(conn, scoped, probable),
                months=months,
                firsts=repo.firsts(conn, scoped, probable),
            )

    def _growth(self, conn, flt: SightingFilter, period: Period) -> Growth:
        probable = self._probable
        today = self.today()
        if period.is_year:
            origin = period.start
            previous = Period("custom", add_years(origin, -1), date(origin.year - 1, 12, 31), "")
            curves = [
                Curve(
                    str(origin.year),
                    cumulative(
                        repo.species_first_dates(conn, period.applied(flt), probable), origin
                    ),
                ),
                Curve(
                    str(origin.year - 1),
                    cumulative(
                        repo.species_first_dates(conn, previous.applied(flt), probable),
                        previous.start,
                    ),
                ),
            ]
            return Growth(origin, 365, curves, True)
        dates = repo.species_first_dates(conn, period.applied(flt), probable)
        origin = period.start or (dates[0] if dates else today)
        end = period.end or today
        return Growth(
            origin,
            max(1, (end - origin).days),
            [Curve(period.label, cumulative(dates, origin))],
            False,
        )

    def year_list(self, flt: SightingFilter, year: int) -> list[repo.FirstRow]:
        """A year list: the first sighting of each species that year (lifers marked)."""
        scoped = flt.with_(date_from=date(year, 1, 1), date_to=date(year, 12, 31))
        with self._db.connection() as conn:
            return list(reversed(repo.firsts(conn, scoped, self._probable)))

    def recent_firsts(self, limit: int = 8) -> list[repo.FirstRow]:
        """Newest lifers and firsts of this year (for the dashboard)."""
        today = self.today()
        with self._db.connection() as conn:
            rows = repo.firsts(
                conn, Period.this_year(today).applied(SightingFilter()), self._probable
            )
        return rows[:limit]

    def top_species(self, flt: SightingFilter, limit: int = 5) -> list[repo.SpeciesRow]:
        with self._db.connection() as conn:
            rows = repo.species_totals(conn, flt)
        return sorted(rows, key=lambda r: (-r.sightings, r.name))[:limit]

    def day_counts(self, start: date, end: date) -> dict[date, int]:
        """Sightings per day (for the dashboard's activity strip)."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT observed_date, COUNT(*) FROM sighting_v "
                "WHERE observed_date BETWEEN ? AND ? GROUP BY observed_date",
                (start.isoformat(), end.isoformat()),
            )
            return {date.fromisoformat(d): n for d, n in rows}
