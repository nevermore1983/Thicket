"""Create a demo WildLife library full of realistic sample sightings.

    uv run python scripts/make_demo_data.py --data-dir local_data/demo --sightings 1500
    uv run wildlife --data-dir local_data/demo

Uses the real species catalogue and real UK places. Never point --data-dir at
your real library: the script refuses to add to a folder that already has data.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.data.repositories import sightings as sightings_repo
from wildlife.domain.codes import CountQualifier, Evidence, Identification, LocationMethod
from wildlife.domain.models import PlaceDraft, SightingDraft

PLACES = [  # name, lat, lon, radius (m), weight for outings
    ("Garden", 51.7496, -0.3387, 30, 0),
    ("Rainham Marshes", 51.4955, 0.1975, 800, 8),
    ("Titchwell Marsh", 52.9648, 0.6066, 900, 5),
    ("Minsmere", 52.2468, 1.6195, 1000, 5),
    ("Epping Forest", 51.6611, 0.0520, 1500, 6),
    ("Wicken Fen", 52.3105, 0.2918, 900, 4),
    ("Richmond Park", 51.4430, -0.2741, 1200, 5),
    ("Slimbridge", 51.7415, -2.4065, 800, 3),
    ("Bempton Cliffs", 54.1462, -0.1695, 700, 2),
    ("Loch Garten", 57.2423, -3.6930, 1000, 1),
    ("Dungeness", 50.9175, 0.9670, 1500, 3),
    ("Ashdown Forest", 51.0615, 0.0350, 2000, 2),
]
GARDEN_GROUPS = {
    "bird",
    "terrestrial mammal",
    "insect - butterfly",
    "insect - moth",
    "amphibian",
    "insect - hymenopteran",
}
SEASONAL = {
    "insect - butterfly": (3, 10),
    "insect - dragonfly (Odonata)": (5, 10),
    "insect - moth": (3, 11),
    "reptile": (3, 10),
    "amphibian": (2, 10),
    "insect - hymenopteran": (3, 10),
}
NOTES = [
    "Feeding along the edge of the reeds",
    "Pair near the old nest box",
    "Fishing from the willow",
    "Flushed from the hedge",
    "Singing from the top of the oak",
    "Carrying food",
    "Displaying over the meadow",
    "Basking on the path",
    "Came to the moth trap overnight",
    "In the garden pond",
    "Chased off by crows",
    "Juveniles with both parents",
    "Very confiding",
    "Distant views through the scope",
    "Calling at dusk",
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--sightings", type=int, default=1500)
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    started = time.perf_counter()

    ctx = AppContext.open(DataPaths(args.data_dir))
    try:
        if ctx.stats.dashboard().total_sightings:
            print("That library already has sightings; refusing to add demo data to it.")
            return 1
        if ctx.catalogue.needs_install():
            ctx.catalogue.install()
        places = [
            ctx.places.save(
                PlaceDraft(n, la, lo, r, is_favourite=n in ("Garden", "Rainham Marshes"))
            )
            for n, la, lo, r, _ in PLACES
        ]
        with ctx.db.connection() as conn:
            pool = conn.execute(
                "SELECT id, informal_group, priority FROM taxon WHERE rank = 'species' AND priority >= 7"
            ).fetchall()
        garden_pool = [r for r in pool if r["informal_group"] in GARDEN_GROUPS]
        today = date.today()
        start = today - timedelta(days=365 * args.years)

        def in_season(row, month: int) -> bool:
            lo, hi = SEASONAL.get(row["informal_group"], (1, 12))
            return lo <= month <= hi

        def pick(candidates, month: int):
            options = [r for r in candidates if in_season(r, month)] or candidates
            weights = [
                r["priority"] ** 2 * (3 if r["informal_group"] == "bird" else 1) for r in options
            ]
            return rng.choices(options, weights=weights)[0]

        drafts: list[SightingDraft] = []
        while len(drafts) < args.sightings:
            if rng.random() < 0.35:  # a garden record
                day = start + timedelta(days=rng.randrange((today - start).days + 1))
                place, row = places[0], pick(garden_pool, day.month)
                items = [row]
            else:  # an outing: several species at one place on one day
                day = start + timedelta(days=rng.randrange((today - start).days + 1))
                if rng.random() < 0.7:
                    day += timedelta(days=(5 - day.weekday()) % 7)  # mostly weekends
                    day = min(day, today)
                place = rng.choices(places[1:], weights=[w for *_, w in PLACES[1:]])[0]
                items = {pick(pool, day.month)["id"]: None for _ in range(rng.randint(5, 18))}
                items = [r for r in pool if r["id"] in items]
            minute = rng.randint(6 * 60, 11 * 60)
            for row in items:
                minute += rng.randint(2, 25)
                located = rng.random()
                lat = lon = unc = method = None
                if located < 0.55:
                    d = place.radius_m / 111_320
                    lat = round(place.latitude + rng.uniform(-d, d), 6)
                    lon = round(place.longitude + rng.uniform(-d, d) * 1.6, 6)
                    unc, method = (
                        rng.choice([10, 10, 100]),
                        rng.choice([LocationMethod.MAP, LocationMethod.PHOTO]),
                    )
                count = (
                    rng.choice([1, 1, 1, 2, 3, 5, 12, 40])
                    if row["informal_group"] == "bird"
                    else rng.choice([1, 1, 2])
                )
                drafts.append(
                    SightingDraft(
                        taxon_id=row["id"],
                        observed_date=day,
                        observed_time=f"{min(minute // 60, 23):02d}:{minute % 60:02d}"
                        if rng.random() < 0.88
                        else None,
                        place_id=None if located > 0.97 else place.id,
                        latitude=lat,
                        longitude=lon,
                        uncertainty_m=unc,
                        location_method=method
                        or (LocationMethod.PLACE if located <= 0.97 else None),
                        count=count,
                        count_qualifier=CountQualifier.APPROX
                        if count >= 40
                        else CountQualifier.EXACT,
                        evidence=rng.choices(list(Evidence), weights=[75, 10, 8, 3, 1, 3])[0],
                        identification=rng.choices(list(Identification), weights=[93, 5, 2])[0],
                        notes=rng.choice(NOTES) if rng.random() < 0.3 else None,
                    )
                )
        with ctx.db.transaction() as conn:
            for draft in drafts[: args.sightings]:
                sightings_repo.insert(conn, draft)
        n = ctx.stats.dashboard()
        print(
            f"Demo library ready in {time.perf_counter() - started:.1f} s at {args.data_dir}: "
            f"{n.total_sightings:,} sightings, {n.life_species} species, {len(places)} places"
        )
    finally:
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
