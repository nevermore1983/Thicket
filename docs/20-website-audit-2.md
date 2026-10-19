# Thicket website — second audit

**Date:** 19 October 2026
**Scope:** the live site (`site/`: 6 pages, stylesheet, font, 21 images, the video), the scripts that build it (`build_site_changelog.py`, `site_assets.py`, `make_icon.py --site`, `promo_video.py`), its tests (`test_site.py`, `test_site_icons.py`) and workflows (`pages.yml`, `release.yml`, `add-stable-installer.yml`). It includes everything added since the first audit (`docs/18-website-audit.md`): the 1.3.0 changes, the GPL licence, the iNaturalist guide and the video.
**Status:** Phases A and B done: M1 and L1–L5 fixed (section 6). The optional extras (O1–O4) were skipped, as you chose.

**In short:** the site is in good shape. There's nothing critical and nothing high. One medium finding, about keeping the video script working as the app changes, and a handful of small polish items.

---

## 1. How it was checked

| Check | Result |
|---|---|
| Live site against the repo, file by file | Identical |
| All 625 tests (`uv run pytest`) | **625 passed** |
| Ruff lint and format on the site scripts and tests | Clean |
| W3C HTML validator, all 6 live pages | **0 errors, 0 warnings** |
| W3C CSS validator | Valid, 0 errors |
| Strict HTML parse (html5lib), all pages | 0 errors |
| codespell (pages, changelog, docs) | No typos |
| Every outside link | All work. iNaturalist's export page blocks automated visitors (Cloudflare), so open it once yourself |
| axe accessibility checker, every page, light and dark | **0 violations**. One item for review: the video has no captions track (L1) |
| Console and failed requests, every page | None, apart from the 404 page's own expected "not found" |
| Layout at 320, 375, 640 (200% zoom), 761, 768, 1000 and 1280 px | No sideways scrolling, menu on one row, long code lines wrap |
| Keyboard: tab order, video, "What the video shows" | All reachable, visible focus ring, Enter plays and opens |
| Download button, end to end | 1.3.0's `Thicket-Setup.exe`, 152 MB ("about 150 MB" is right). Its `SHA256SUMS.txt` lists both names with Unix line endings: the release changes from the first audit worked in a real release |
| Security | HTTPS enforced (http redirects, HSTS). No secrets or personal data in `site/`. Workflows have least-privilege permissions, pinned actions, and their input is validated and passed through the environment |
| Page weight (live, light theme) | Home 149 KB, features 349 KB, help 27 KB, changelog 8 KB, privacy 7 KB. The video (2.8 MB) only loads when played |
| Every claim in the new iNaturalist guide, against the app's code | All button labels and behaviours exist |

### Not checked, and why

- **Lighthouse scores:** Google's free PageSpeed service was out of its daily allowance both days. You can run it at https://pagespeed.web.dev.
- **Firefox, Safari and real phones:** only Chromium is available here (with phone emulation). See section 5 for a quick manual check.
- **A real screen reader:** axe checks the structure, but nobody has listened to the site with Narrator or NVDA.
- **Load timings:** the browser pane was hidden, so pages don't paint. Weights were measured instead.

---

## 2. Findings

### Critical, High

None.

### Medium

**M1. The video script depends on the app's private parts, and nothing checks them**
- **What:** `scripts/promo_video.py` reaches into 7 internal names in the app (names starting with `_`, meant to be private): the calendar's `_cell_rect`, the species page's `_choose`, the map page's `_send`, `_bounds` and `modes._buttons`, `ctx.sightings._today`, and the editor's `_dirty`. No test runs the script.
- **Why it matters:** these can be renamed in any app change without warning. The video would then break the next time someone re-films it, perhaps months later, when nobody remembers why.
- **How verified:** searched the script for those names. No test file runs it (the only mention is a comment).
- **Fix:** a small UI test that builds the real window, using the existing test setup, and checks each of those hooks still exists. Then a refactor that breaks re-filming fails the normal test run straight away.
- **Effort:** small (one test file). **Risk:** none: it adds a test and changes no code.

### Low

**L1. The video has no captions track**
- **What:** axe flags `video-caption` for review on the home page.
- **Why:** the captions are drawn into the picture, so they can't be read by caption tools or screen readers.
  - Its sound is birdsong only (no speech), so the accessibility rules don't strictly require captions.
  - The "What the video shows" text already describes everything.
- **Fix:** a small WebVTT captions file (`site/video/thicket-tour.vtt`) with "[Birdsong throughout]" and the five on-screen captions at their times, added as a `<track>`. It's made by the video script, so it stays in step with re-filming.
- **Effort:** small.

**L2. The privacy page names only one map**
- **What:** the table's first row says "The map's background". Since 1.3.0, **Choose on map** also shows OpenFreeMap tiles. It follows the same rules: the same background, and plain when online features are off (verified in `ui/map_picker.py`).
- **Fix:** "Maps (the Map page and Choose on map)".
- **Effort:** a one-line wording change.

**L3. The video's poster loads on every home visit**
- **What:** `tour-poster.webp` is 90 KB, the biggest thing on the home page, and is fetched even if the video is never played.
- **Fix:** quality 80 instead of 90 makes it 60 KB with no visible change at its display size. That means one setting in `promo_video.py` and remaking the poster from the existing video (no re-filming). The home page goes from 149 KB to about 120 KB.
- **Effort:** tiny.

**L4. Re-filming grows the repository for good**
- **What:** each new version of the video adds about 2.8 MB to the git history permanently. The repo is 6.3 MB packed today.
- **Fix:** a note in `docs/17-website-plan.md`: re-film only when the app *looks* different.
- **Rejected alternatives:**
  - Git LFS adds tooling to learn.
  - Publishing the video as a release file would serve it from another domain, which breaks the privacy page's "nothing loads from elsewhere".
- **Effort:** tiny (docs).

**L5. Which browsers the site supports isn't written down**
- **What:** WebP screenshots and a few modern CSS features need browsers from 2020 or later (Safari and iOS 14+). On older iPhones the screenshots wouldn't show.
- **Fix:** this is fine for today's visitors, so no code change: just record it in `docs/17-website-plan.md`.
- **Effort:** tiny (docs).

### Optional enhancements (not needed)

| # | What | Worth it? |
|---|---|---|
| O1 | A `sitemap.xml`, plus registering the site in Google Search Console (a step only you can do). The domain-level `robots.txt` can't exist on a project site; its absence means "crawl everything", which is fine | Only if you want search traffic |
| O2 | A "Watch the 40-second tour" link from the Features page to the video | Nice, tiny |
| O3 | Search-engine "structured data" describing Thicket as free Windows software (inline, loads nothing) | Small benefit |
| O4 | A Content-Security-Policy tag: browsers would refuse anything loaded from elsewhere | Little benefit: the site has no scripts or forms. Skip unless you want the belt-and-braces |

---

## 3. Already good (leave alone)

- Valid, accessible pages in both themes and at every width tested, with no outside requests: the privacy promise holds.
- The tests catch broken links, missing alt text, outside loads, header and footer drift, stale changelog, wrong download links, broken previews and the video's rules. They run before every publish.
- Download buttons, release files and checksums work end to end, as the 1.3.0 release proved.
- Plain HTML and CSS with no build step suits the site's size. The repeated header and footer are guarded by a test, so there's no case for a site generator.

---

## 4. Roadmap

Each phase ends with a short report and waits for your OK.

| Phase | Items | Purpose | Effort | Risks |
|---|---|---|---|---|
| **A. Protect the video** | M1 | Keeps re-filming working as the app changes | ~30 min | None: test only |
| **B. Polish** | L1, L2, L3, L4, L5 | A captions track, accurate privacy wording, a lighter home page, documented limits | ~45 min | L1 and L3 touch `promo_video.py`'s website step. Checked by re-running it on the existing video, and the site test |
| **C. Optional** | Any of O1–O4 you pick | Search visibility, a small UX link | 15–30 min each | O1 needs your Google account |

Dependencies: none between A and B; C is independent.

---

## 5. Manual checks for you (5 minutes)

1. Open the site on your phone. Play the video with sound, open **What the video shows**, and press a Download button (you don't have to install).
2. If you have Firefox, or a Mac or iPhone, glance at the home and features pages there.
3. Optional: run https://pagespeed.web.dev on the home page and note the scores.
4. Click the iNaturalist **Export observations** link on the Help page once, to confirm it opens.

---

## 6. Fixed (19 October 2026)

- **M1:** `scripts/promo_video.py` has `missing_hooks()`, which lists every part of the app the scenes use (18 checks, plus the Add sighting panel's fields). `tests/ui/test_promo_video.py` runs it on a real window. A second test takes one part away on purpose and checks that exactly that part is reported.
- **L1:** a captions file, `site/video/thicket-tour.vtt`, describes the sound ("[Gentle forest birdsong plays throughout. No speech.]" and the fade-out). The video script writes it whenever it updates the website. The browser loads both lines, and axe's `video-caption` item is gone.
- **L2:** the privacy page now says "Map backgrounds (the Map page and Choose on map)".
- **L3:** the poster is 65 KB (was 90), with no visible change.
  - `--site-from site/video/thicket-tour.mp4` refreshes the poster and captions without re-filming.
  - The video file itself didn't change.
- **L4, L5:** `docs/17-website-plan.md` says to re-film only for visible changes (repository size), and which browsers the site supports.
- **Tests:** the site test also checks every video has a captions track with a real WebVTT file. Removing the track on purpose made it fail.
