# WildLife — Phase 5: Foundation and Spikes

**Date:** 11 October 2026
**Status:** Complete, awaiting review

This phase answered the five risky technical questions with small experiments ("spikes"), then built the foundation every later phase stands on.

---

## 1. Spike results

| # | Question | Result | Decision |
|---|---|---|---|
| 1 | Does MapLibre run inside Qt's web engine on this PC? | **Pass.** WebGL 2 on the RTX 3070 (via ANGLE/Direct3D 11). MapLibre 6.11.2 loaded, OpenFreeMap tiles drew, 2,000 clustered points plus a heat layer were ready in about 1.7 s, and JavaScript → Python messages worked. | Use MapLibre **6.x**. It ships only as JavaScript modules, which Chromium won't load from plain files, so the app serves its web assets through its own `wildlife://` URL scheme, as planned for offline tiles anyway. Phase 8 must bundle map fonts ("glyphs") for offline cluster labels. |
| 2 | Is our grid-reference maths accurate enough? | **Pass.** Compared with Ordnance Survey's survey-grade OSTN15 over 2,000 points: median error 1.6 m, worst 4.3 m. Converting there and back loses only 3 mm. It also matches OS's own published worked example to the millimetre. | Keep our small `domain/geo.py` and skip `pyproj`, so no extra 6 MB dependency. |
| 3 | What does the real UK Species Inventory look like? | **Partial.** The NBN download refuses automated requests (HTTP 403). GBIF's copy works but dates from 2023, gets very slow for deep pages, and doesn't say which common name is preferred. Only about 8% of the first 6,400 species had any English name. Some insect orders (e.g. Odonata) appear in the "class" field. | **Source:** the Natural History Museum's *UKSI Simplified Copy* (11 Aug 2026 release, CC BY). It's behind a bot check, so it is downloaded once by hand and the import script reads the file. **Category rules** now match a group name anywhere in a species' lineage, not at a fixed rank. Real UKSI fish classes were added. |
| 4 | Can we read iPhone HEIC photos (rotation, date, GPS)? | **Pass** on generated test photos: correct rotation, date and UTC offset, GPS to 5 decimal places, GPS accuracy, camera model, and thumbnails. A file with no EXIF works fine; a corrupt file is rejected cleanly. | Use `pi-heif` + Pillow. HEIC comes out of the decoder already rotated while JPEG doesn't; applying `exif_transpose` to both handles each correctly. **Still to confirm with real iPhone photos.** |
| 5 | Can we package Qt + the web engine as a Windows program? | **Pass.** A PyInstaller folder build runs the map spike unaltered, and Windows Defender finds no threats. Size is 566 MB untrimmed: Chromium alone is about 300 MB, plus about 100 MB we can remove. | **PyInstaller** for now (fast, works). Revisit Nuitka in Phase 14 only if antivirus false alarms appear. The real app currently packages to 90 MB and starts in about 1.5 s. |

**Recurring lesson:** the Windows console can't print many Unicode characters (→, ·). It crashed two spikes before they finished. The app's own logs are written as UTF-8 for this reason.

---

## 2. What the foundation contains

```
src/wildlife/
├─ app.py                startup: logging → data folder → database → theme → window
├─ context.py            opens the data folder, safety copy, migrations, builds services
├─ logging_setup.py      rotating UTF-8 log files
├─ config/  paths.py     data folder locations; OneDrive/Dropbox detection
│           settings.py  every setting + default in one place
├─ domain/  geo.py       grid references, coordinate parsing, distances (fully tested)
│           errors.py    friendly error types
├─ data/    db.py        per-thread connections, PRAGMAs, transaction()
│           migrate.py   numbered SQL migrations, atomic, backup first
│           snapshot.py  consistent copies + verification
│           migrations/0001_initial.sql   the schema
│           repositories/settings.py
├─ services/events.py    "something changed" announcements
│           settings.py  read/change settings
└─ ui/      main_window.py   sidebar, top bar, pages, shortcuts, narrow-window rail
            theme/           tokens, generated stylesheet, SVG icons, light/dark/system
            components/      Button, Segmented, EmptyState, Callout, Page, Toast
            pages/           Dashboard welcome, Settings, empty states for later pages
            error_handler.py friendly dialogs; full details only in the log
            single_instance.py  a second launch brings the first window forward
scripts/  screenshot.py  capture the real UI in light/dark (used to check every change)
          build_exe.py   PyInstaller build → trim → automatic smoke test
tests/    56 tests: geo (unit), database/migrations/snapshots/settings (integration), UI smoke
```

**Checks passed at the end of the phase:**
- `ruff` lint and format: clean.
- `pytest`: 56 passed in about 2 s.
- Schema stress test: 26/26.
- Packaged `.exe`: smoke test passes.

---

## 3. Changes to earlier decisions

| Area | Before | Now | Why |
|---|---|---|---|
| Map library | MapLibre 5.x | **MapLibre 6.11.2** | 6.x is current. It's module-only, which the `wildlife://` scheme handles. |
| Category rules | Match at a given rank | **Match the name anywhere in the lineage** | UKSI files some orders under "class" |
| Species source | NBN download | **NHM UKSI Simplified Copy (manual download)** | NBN refuses automated requests, and the GBIF copy is from 2023 with no preferred names |
| Packaging | PyInstaller or Nuitka | **PyInstaller** | Works with the web engine; Defender clean |
| Schema file | `docs/design/schema_v1.sql` | `src/wildlife/data/migrations/0001_initial.sql` | It is now the real migration |

---

## 4. Moved to Phase 6

- **Species catalogue import script**, which needs the manually downloaded UKSI file.
- **Demo-data generator** (from the Phase 3 spike), most useful once sightings can be shown.
- **Bundling the Source Serif 4 font** for scientific names, which first appear in Phase 6.
