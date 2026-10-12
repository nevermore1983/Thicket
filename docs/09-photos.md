# WildLife — Phase 9: Photos

**Date:** 12 October 2026
**Status:** Complete, awaiting review

Photos now have their own page. Import a folder from your Pixel and the photos land in the **Inbox**, grouped by encounter. Select the photos of one animal, choose **Create sighting**, and the date, time, position and place are filled in from them. **RAW + JPEG** pairs become one photo, with the RAW kept beside it. The **Library** shows every photo on a sighting, and a full-screen **viewer** lets you browse, rotate, caption and zoom.

---

## 1. What was built

| Area | What you get |
|---|---|
| **RAW + JPEG (Pixel)** | `PXL_….RAW-01.COVER.jpg` + `PXL_….RAW-02.ORIGINAL.dng` (and the older same-name `.jpg` + `.dng`, or a camera's `IMG_0001.JPG` + `.CR3`) import as **one photo**: the JPEG is shown and the RAW is kept beside it as its original, never changed, and backed up. A RAW imported on its own is rendered with LibRaw. A RAW that arrives later joins its photo. Supported RAW types: DNG, CR2, CR3, NEF, ARW, ORF, RW2, RAF, PEF, SRW. |
| **Import** | "Import photos…" → choose photos **or a whole folder** (sub-folders too), or drag and drop onto the page. Runs in the background with a progress bar. Summary: "38 imported · 12 RAW originals kept · 2 already in your library". Videos and other files in a folder are skipped. |
| **Dates** | From the photo's EXIF. If a photo has lost it (e.g. sent through a messaging app), the date in a Pixel file name is used, converted from UTC to UK time, and marked "(from the file name)". |
| **Inbox** | Photos not yet on a sighting, grouped into encounters (within 10 min and 200 m), each headed like "Sun 11 Oct 2026 · 07:40–07:43 · near Rainham Marshes · 6 photos". Select by click, Shift-click, "Select group", or keys (arrows, Space, Ctrl+A). Then: **Create sighting** · **Add to existing sighting…** (that day's sightings listed first) · **View** · **Delete** (recycle bin, with Undo). |
| **Create sighting from photos** | The add panel opens with the photos attached; date and time come from the earliest, position from the first with GPS, and the **place from where the photos were taken** (only a place you pick overrides it). |
| **Library** | Every photo on a sighting, newest first, using the shared filter, with a size slider. A "RAW" badge marks photos with a RAW original. Missing files show as "File missing", and a note says how many. |
| **Viewer** | Full screen and dark. ← → move, R rotate (saved, original untouched), I info (file, date and its source, camera, size, RAW original, grid reference), Z zoom to 100% (drag to pan), caption, **Make cover** (from a sighting), Open sighting, Esc. The next photo is prepared while you look. |
| **Missing files** | The viewer offers **Locate…** (it only accepts the very same photo, checked by its content) or **Remove photo**. |
| **Recycle bin** | Deleted photos are listed in Settings › Recycle bin and can be restored. After 30 days they're removed **with their files**: the only time WildLife deletes a photo file. When a sighting is finally purged, its photos go too, unless another sighting uses them. |
| **Elsewhere** | Clicking a photo in a sighting's panel opens the viewer; the dashboard's "photos in your Inbox" row opens the Inbox; the add panel's photo strip wraps. |
| **Demo photos** | `scripts/make_demo_photos.py` adds painted pictures with real EXIF (Pixel camera, sighting's date and GPS), and an Inbox with Pixel-named RAW + JPEG pairs. |

---

## 2. Research

| Question | Finding | Decision |
|---|---|---|
| How does the Pixel name RAW + JPEG? | Since late 2023: `PXL_…242.RAW-01.COVER.jpg` + `PXL_…242.RAW-02.ORIGINAL.dng`; earlier, the same name with `.jpg` / `.dng` | Pair by folder + name with the `.RAW-0n.…` part removed |
| What's inside a Pixel 10 Pro DNG? | Only a small preview (about 1,800 px) | Show the JPEG; keep the DNG as the original; render lone RAWs with LibRaw |
| Reading RAW in Python | `rawpy` 0.27 (MIT, LibRaw 0.22) has Windows wheels for Python 3.13 | Added (with numpy, which it needs) |
| Google Photos "storage saver" | Can return a JPEG still named `.dng` | Files are judged by contents, not name |
| Motion Photos | A JPEG with a short video appended | Files are copied byte for byte, so the video is kept |
| Pixel file-name times | UTC, not local time | Converted to UK time; only used when EXIF has no date |

---

## 3. Checks

- **Tests:** 299 automated (47 new), passing in about 48 s, run repeatedly. RAW tests use a tiny DNG written by `tests/fixtures/photos/make_dng.py` (no one's real photo). New tests cover:
  - file rules: Pixel pairing, folders, RAW types, file-name dates;
  - encounter grouping and pre-filling a sighting;
  - import: RAW pairs, lone RAW, RAW arriving later, storage-saver JPEGs, folders, file-name dates;
  - backups including RAW originals;
  - Inbox and Library rules, cover, rotation, captions;
  - delete, Undo, purge (files removed), sighting purge, missing files and Locate;
  - the UI: folder import, drag and drop, create from photos (place from GPS), add to existing, delete and the recycle bin, Library filter, viewer keys, cover, Locate, grid clicks and keys.
- **Performance** (Pixel-sized 4080 × 3072 photos, ~2.3 MB each):

  | Action | Time | Target |
  |---|---|---|
  | Import | **21 photos/second** | ≥ 5 |
  | First thumbnail | 34 ms | |
  | Cached thumbnail | 0.1 ms | "instant" |
  | Viewer picture, first look (was 419 ms) | **33 ms** | |
  | Grid of 4,800 photos: fill / each scroll step | 16 ms / 4.4 ms | smooth (≤ 16 ms) |

- **Packaged build:** smoke test checks the bundled RAW libraries load, plus the catalogue and map; the app folder is 570 MB (+54 MB for numpy and LibRaw).
- **Visual checks:** Library, Inbox, selection, viewer with info, and create-from-photos, in light and dark.

---

## 4. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| "Create sighting" chose the wrong place (the one remembered from earlier) | A photo's GPS now sets the place; only a place *you* pick wins. Found from a screenshot, now tested |
| With 6 photos attached, the add panel grew wider than the side panel | The photo strip wraps (like the place chips) |
| The selection bar's buttons were clipped beside the side panel | They wrap onto two lines |
| Double-clicking an Inbox photo to open it also selected it | Double-click restores the selection from before the click pair, whatever order Qt sends the mouse events in |
| Photos of a sighting in the recycle bin could appear in the Inbox; purging a sighting would have left its photos there | The Inbox only shows unlinked photos; purging a sighting marks its no-longer-used photos for removal |
| The viewer took 0.4 s to show a new photo | Two causes, found by timing each step: WebP took 0.6 s to save at 2048 px (now JPEG: 7 ms), and fast half-size JPEG decoding never applied because Pillow needs *both* sides big enough (now asked in the photo's own shape) |
| A smoke-test error opened a dialog and waited forever | In smoke mode any error is logged and the app exits with a failure code |
| Text written by my helper scripts kept getting real line breaks / NUL characters | Found the cause: a double backslash in a shell command reaches Python as a single one. Edits with backslashes now go through the editor |
| Demo RAW copies were identical, so only one was kept | Correct behaviour (same file = same RAW); the demo makes each copy unique, like real RAWs |

---

## 5. Deferred (deliberately)

| Item | Where |
|---|---|
| Camera clock correction for a batch ("camera was 1 h behind"), a Could | Phase 12 (a Pixel's clock is set by the network) |
| Missing photo files in the dashboard's "Needs attention" (checking 5,000 files takes ~0.6 s) | Phase 11 health check, run in the background |
| Dragging photos to reorder within a sighting (Make cover covers the main need) | Phase 12 |
| Playing a Motion Photo's video | Later, if wanted (the video is kept) |
| Exporting or opening the RAW original in an editor | Phase 11 (export) |
