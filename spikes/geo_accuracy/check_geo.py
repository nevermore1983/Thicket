"""Spike 2: how accurate is wildlife.domain.geo against the survey-grade OSTN15?

pyproj is used here only as a reference (it is NOT an app dependency). With
network access enabled, PROJ downloads Ordnance Survey's OSTN15 grid, which is
the official, centimetre-level WGS84 <-> National Grid transformation.

Run:  uv run --with pyproj python spikes/geo_accuracy/check_geo.py
"""

import math
import random
import statistics
import sys

import pyproj
from pyproj.transformer import TransformerGroup

sys.path.insert(0, "src")
from wildlife.domain import geo  # noqa: E402

pyproj.network.set_network_enabled(True)
group = TransformerGroup("EPSG:4326", "EPSG:27700", always_xy=True)
best = group.transformers[0]  # PROJ lists the most accurate first
grids = [g.short_name for op in best.operations or [] for g in getattr(op, "grids", [])]
print("Reference:", best.description, "| accuracy", best.accuracy, "m | grids", grids or "(see below)")
assert best.accuracy is not None and best.accuracy <= 1, "OSTN15 grid not available"

rng = random.Random(1)
# Random points on land-ish areas across GB (England, Wales, Scotland incl. islands)
boxes = [(50.0, 52.8, -5.7, 1.7), (52.8, 55.8, -4.5, -0.2), (55.8, 58.6, -6.3, -2.0), (58.0, 60.8, -3.5, -0.8)]
errors = []
worst = (0, None)
for _ in range(2000):
    la0, la1, lo0, lo1 = rng.choice(boxes)
    lat, lon = rng.uniform(la0, la1), rng.uniform(lo0, lo1)
    e_ref, n_ref = best.transform(lon, lat)
    e, n = geo.wgs84_to_grid(lat, lon)
    err = math.hypot(e - e_ref, n - n_ref)
    errors.append(err)
    if err > worst[0]:
        worst = (err, (round(lat, 4), round(lon, 4)))

errors.sort()
print(f"Helmert vs OSTN15 over {len(errors)} points:")
print(f"  median {statistics.median(errors):.2f} m · 95th pct {errors[int(.95 * len(errors))]:.2f} m · max {worst[0]:.2f} m at {worst[1]}")

# Round trip: WGS84 -> grid -> WGS84 should return to the same place
rt = []
for _ in range(500):
    lat, lon = rng.uniform(50, 58.5), rng.uniform(-5.5, 1.5)
    lat2, lon2 = geo.grid_to_wgs84(*geo.wgs84_to_grid(lat, lon))
    rt.append(geo.distance_m(lat, lon, lat2, lon2))
print(f"Round trip error: max {max(rt) * 1000:.3f} mm")

ok = worst[0] < 10 and max(rt) < 0.01
print("RESULT:", "PASS (well inside a 10 m grid square)" if ok else "FAIL")
sys.exit(0 if ok else 1)
