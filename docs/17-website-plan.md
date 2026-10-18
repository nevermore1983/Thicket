# Thicket — website (plan)

**Date:** 18 October 2026
**Status:** Done. Live at https://nevermore1983.github.io/Thicket/ since 18 October 2026 (first published by the Website workflow, run 39148807393).

A small public website for Thicket while testers try the app: what it is, what it looks like, and a big download button.

**Your choices (18 Oct):**
- hosted free on **GitHub Pages**, at `https://nevermore1983.github.io/Thicket/`;
- **plain HTML + CSS**, no build tools;
- pages: **home + download, features tour, help / FAQ, changelog, privacy**;
- the look **matches the app**: its colours and the Source Serif 4 font.

---

## 1. What visitors will see

| Page | What's on it |
|---|---|
| **Home** (`index.html`) | One line on what Thicket is, a large screenshot, the **Download for Windows** button, three short "why" points (fast to record, everything on your PC, works offline). |
| **Features** (`features.html`) | One section per area, each with a screenshot: recording a sighting, calendar, map, statistics, photos, importing from iNaturalist and spreadsheets, backups, regions (UK and US states). |
| **Help** (`help.html`) | Installing, the "Windows protected your PC" warning, upgrading, where your data lives, backups and restore, choosing a region, uninstalling. Short questions and answers. |
| **Changelog** (`changelog.html`) | Every version's notes, the same text as `CHANGELOG.md`. |
| **Privacy** (`privacy.html`) | Thicket keeps everything on your PC. What it connects to and when (maps, species packs, iNaturalist photos), and that the website itself has no tracking or cookies. |

Every page shares one header (logo, page links, Download button) and one footer (GitHub link, version, credits).

- **Download buttons** download the newest installer directly: `releases/latest/download/Thicket-Setup.exe`. Every release carries the installer under that unchanging name as well as its versioned one (`release.yml`), so the link never needs updating.
- **Light and dark** follow the visitor's Windows/phone setting, like the app.
- **Works on phones** too, even though Thicket is a Windows app (people find links on their phone).

---

## 2. How it's built

```
site/
  index.html  features.html  help.html  changelog.html  privacy.html
  style.css            one stylesheet for every page
  fonts/               Source Serif 4, served from the site itself
  images/              screenshots, logo, favicon
```

- **Plain files.** You can open `site/index.html` straight in a browser to see it. No Node, no npm, nothing to install.
- **Colours** come from the app's own theme (`src/wildlife/ui/theme/tokens.py`), written once as CSS variables at the top of `style.css`.
- **Fonts match the app.** Text uses Segoe UI Variable, the app's own font, which every Windows PC already has (phones and Macs use their system font). Scientific names use Source Serif 4 italic, as in the app: a 10 KB copy (one weight, basic Latin letters, made from the app's bundled file by `scripts/site_assets.py font`) sits in `site/fonts/` with its OFL licence. Nothing loads from Google Fonts or any other website, which keeps the privacy page honest.
- **Preview** with the `website` entry in `.claude/launch.json` (a local web server on port 8090). Opening the file directly also works, but only a server shows dark mode.
- **Screenshots** come from `scripts/screenshot.py` on the demo library (`local_data/demo9`), never your real sightings, turned into small WebP files by `scripts/site_assets.py`. Light and dark versions; the page shows the one matching the visitor's setting, and tapping one opens it full size.
- **Icons** (header logo, browser tab, phone home screen) are drawn by `scripts/make_icon.py --site` from the same recipe as the app icon.
- **Changelog:** a small script (`scripts/build_site_changelog.py`) turns `CHANGELOG.md` into `changelog.html`, and a test fails if they drift apart. This is the one generated page, so you only ever edit `CHANGELOG.md`.
- **Publishing:** a GitHub Actions workflow (`.github/workflows/pages.yml`) uploads `site/` to GitHub Pages whenever a push to `main` changes it. You switch Pages on once in the repo settings (Settings › Pages › Source: GitHub Actions); I'll walk you through it.
- **A test** checks every page: links between pages and to images work, every image has alt text, and nothing loads from another website.

---

## 3. Steps

Each step ends with a short report and waits for your OK.

1. **Look and home page.** `style.css` with the app's colours and font, the shared header/footer, and the home page with a placeholder screenshot. You preview it in the browser.
2. **Screenshots and features page.** Take the screenshots from the demo library, write the features tour.
3. **Help, privacy and changelog.** The three text pages, the changelog script and the site test.
4. **Publish.** The Pages workflow, a link from `README.md`, then push (I'll ask first: the site is public). You switch Pages on, and we check the live site together.

---

## 4. Keeping the site up to date

| When | Do this |
|---|---|
| You release a new version | Add its notes to `CHANGELOG.md` as usual, then run `uv run python scripts/build_site_changelog.py`. The test fails until you do. The Download buttons need nothing: the release carries `Thicket-Setup.exe`, and the buttons always fetch the latest. |
| A screen in the app changes | Re-take its screenshots, then make them small: `uv run python scripts/screenshot.py --data-dir local_data/demo9 --pages <name> --out local_data/shots`, then `uv run python scripts/site_assets.py screenshots local_data/shots/<name>-light.png local_data/shots/<name>-dark.png`. Re-doing `dashboard` also remakes the link-preview picture. |
| The app icon's design changes | `uv run python scripts/make_icon.py` (app and website icons together). |
| A release is ever published without `Thicket-Setup.exe` (the buttons would lead nowhere) | Actions tab › **Add Thicket-Setup.exe to a release** › Run workflow, with that release's tag. It copies the installer already on the release (after checking its checksum). 1.2.1 got its copy this way. |
| You edit a page | Preview with the `website` launch entry, run `uv run pytest tests/unit/test_site.py`, commit and push. (`404.html` shows unstyled in the preview: it uses the live site's `/Thicket/` address so it works for any missing page.) |

Every push to `main` that changes `site/` (or `CHANGELOG.md`) runs `.github/workflows/pages.yml`: it runs the site test, then publishes. If the test fails, the live site stays as it was.

**Things found while building:**
- Switching theme while Thicket was open turned the map black (fixed in commit 3bac5f1, with a test). It belongs in the next version's changelog.
- The demo photos are drawings, so there's no Photos screenshot yet.
- The header and footer are copied into each page (plain HTML has no "include"); the site test fails if the copies differ.

---

## 5. Not in this version

- A custom domain (can be added later without changing the pages).
- Analytics, newsletter or contact form.
- Showing the latest version number on the button (the link already always points at the latest release).
- A Mac or Linux download (Thicket is Windows-only).
