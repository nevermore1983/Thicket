# WildLife — Phase 8: Map

**Date:** 11 October 2026
**Status:** Complete, awaiting review

Your sightings are now on a map: as pins, as a heat map, or as species per grid square. The shared filter applies, and you can add sightings or places straight from the map. The map works offline too, with a plainer background.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Pins** | Category-coloured pins with the category icon. Nearby sightings group into clusters showing a count ("2.1k"); click a cluster to zoom in. Sightings that never separate (same spot) open as a list in the side panel. Hover for name and date, click to open the sighting. |
| **Heat** | Where you've recorded most, weighted by sightings or by animals counted (square-rooted, so one flock of 500 doesn't outweigh a year of visits). The busiest area always reaches the darkest colour. Zoomed in to street level, it hands over to pins. |
| **Grid squares** | Species per British National Grid square: 10 km squares when zoomed out, then 2 km, then 1 km. Hover shows e.g. "TQ57 · 42 species · 310 sightings". A record only counts in squares at least as big as its location uncertainty, and the page says how many were left out and why (rough location, or outside Great Britain). |
| **Places** | A "Places" switch shows your saved places as dashed circles with their radius. |
| **Right-click** | "Add sighting here" (position and a sensible uncertainty from the zoom, e.g. ±25 m at street level), "Create place here", "Copy position". |
| **Background map** | Automatic (follows light/dark theme), Standard, Light, Dark, or Plain outline. Online maps come from OpenFreeMap. Tiles you've seen are cached (up to 300 MB), so they load faster and may still appear offline. |
| **Offline / online off** | With no internet, or with **Settings › Online features** turned off, the map shows a plain UK outline with your pins and a banner explaining why. |
| **Privacy** | A network gate lets the map page talk only to `tiles.openfreemap.org` over HTTPS, and to nothing when online features are off. Only map areas are requested; sightings never leave the PC. |
| **Show on map** | From a sighting (centres and rings it), an outing, or a calendar day (the map filtered to that day). |
| **Status line** | "19,364 sightings on the map · 636 without a location" (the second part lists them). |
| **No WebGL** | A clear explanation instead of a blank panel (e.g. over Remote Desktop). |
| **Remembered** | Last view, mode, weighting, places switch and background. |

How it fits together: the map is a web page (`ui/web/assets/map.js`) using the bundled MapLibre 6.11.2. Python works out what to show (`services/map.py`), publishes it at a private `wildlife://app/data/…` address, and sends commands over the bridge (`ui/web/map_bridge.py`); the page reports clicks back. No local web server and no open ports.

---

## 2. Research

| Question | Finding | Decision |
|---|---|---|
| Is MapLibre 6.11.2 still right? | The 6.x line is current and actively released | Kept. The bundled files match the official npm release byte for byte (checked against jsDelivr's published SHA-256 hashes); a test re-checks them every run |
| Online background | OpenFreeMap: Liberty, Positron and Dark styles, no key, terms fine for an app, served via Cloudflare | Standard / Light / Dark backgrounds, only while "Allow online features" is on |
| Offline UK map pack | Needs the Go `pmtiles` tool to cut a UK extract (no Python equivalent), pmtiles.js, a separate style and font files | **Deferred to Phase 12.** For now: plain outline + tile cache |
| Labels without downloads | Map text needs font files | Pin icons are drawn by Python and cluster numbers by the page on a canvas, so nothing extra is downloaded |

---

## 3. Checks

- **Tests:** 252 automated (37 new), passing in about 33 s. The UI suite was repeated six times for flakiness. New tests cover:
  - map data: points, place centres, filters, bounds, heat cells, species per square, imprecise and out-of-grid records, square and circle geometry;
  - the bundled files' checksums and the network rules;
  - the real map page (loaded offline in tests): sightings drawn by MapLibre itself, squares, clicks, clusters, add/create here, show on map, remembered settings, no-WebGL, and late results after closing. Every map test fails if the page reports a JavaScript error.
- **Performance** with 20,000 sightings (plain background, so internet speed doesn't count):

  | Action | Time |
  |---|---|
  | First visit: page ready | 0.5 s |
  | First visit: pins drawn | **1.0 s** (target ≤ 2 s) |
  | Switch to heat / back to pins | instant |
  | Switch to grid squares (3 sizes, in the background) | 0.4 s |
  | Change filter (birds only) | 0.14 s |
  | Map data in Python (sightings / squares per size) | 97 ms / 110 ms |

- **Packaged build:** the smoke test now opens the map in the packaged app and requires it to report ready. The app folder grew from 111 MB to **516 MB**: that's the Chromium browser engine, as predicted in Phase 1. The installer (Phase 14) compresses it.
- **Visual checks:** all three modes at country, city and reserve zoom, dark theme, places, and offline.

---

## 4. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| The map loaded but stayed empty: "URL scheme wildlife is not supported" | MapLibre's background worker uses the Fetch API, which needs the scheme flag `FetchApiAllowed`. The Phase 5 spike never fetched data, so it didn't hit this |
| "Image could not be loaded" for every pin | MapLibre 6 replaced the `styleimagemissing` event with `setMissingStyleImageResolver()`; found by reading the library rather than guessing |
| Heat was a solid blob, then (after scaling) invisible | Reading MapLibre's shader showed it *throws away* any point worth less than ~1/4000. Sightings are now added up in ~200 m cells in Python, each worth its share of the busiest area |
| The demo data put 4,000 sightings in a perfect square | `make_demo_data.py` now scatters records naturally around a few spots per place (new library `local_data/demo8`) |
| The sidebar stopped collapsing (caught by a test) | At full width the sidebar (228 px) + map page (674 px) passed the 900 px collapse point. "Fit to sightings" became "Fit all", and a new test keeps every page ≤ 671 px |
| A rare error after a test ended: "Signal source has been deleted" | Background results arrived after the window (and bridge) were gone. All page commands now go through one guarded `_send()`, with a test that recreates the situation on purpose |
| The background-work helper crashed if the app closed mid-task | It now notes it in the log instead |
| The packaged app could fail to create the map later | The browser engine needs OpenGL context sharing set *before* the app starts; `scheme.prepare()` does that and registers the scheme |

---

## 5. Deferred (deliberately)

| Item | Where |
|---|---|
| Offline UK map pack (download in Settings) | Phase 12, if wanted (the tile cache already helps) |
| Mini maps inside panels (sighting, day, outing) | Phase 12: "Show on map" covers it for now without a second browser engine |
| "Visits vs richness" view (Could in the spec) | Phase 10, alongside statistics |
| Irish Grid squares for Northern Ireland | Later, if you record there (those sightings still show as pins and heat) |
| Dragging a place's centre / radius on the map | Phase 12 (places can be created from the map now) |
| Pins fanning out at the same spot | Replaced by the "Sightings here" list, which is easier to use with many records |
| Shrinking the 516 MB app folder | Phase 14 packaging |
