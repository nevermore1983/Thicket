# Thicket website — audit

**Date:** 18 October 2026
**Scope:** the live site at https://nevermore1983.github.io/Thicket/ (all 5 pages, the stylesheet, images and font), its publish workflow, and every claim it makes about the app.
**Status:** A1–A13, B1–B14 and C3 fixed (section 6). Left: B15 (your step), B16 (later), C1 and C2 (app work, proposed as their own sessions).

**How it was done:**
- Read every page and the stylesheet again.
- **W3C validators** (the official HTML and CSS checkers) on the live pages. I first fed the HTML validator deliberately broken code, to be sure a clean result means something.
- **axe-core** (a widely used accessibility checker) on every page, in light and in dark.
- Contrast worked out for every text and background colour pair in `style.css`.
- Keyboard-only use, plus layouts at 1280, 375 and 320 pixels wide.
- Every outside link opened. Download sizes measured on the live site. Smaller image and font versions made and measured.
- Every sentence about the app checked against its code.

---

## 1. Already good

- **Valid code:** 0 HTML errors on all 5 pages, and 0 CSS errors.
- **Accessibility:** axe found 0 problems on every page, in both themes. Every piece of text passes the WCAG AA contrast minimum (4.5:1) in both themes, so it's readable for people with low vision.
- **Keyboard:** the tab order is logical (skip link, logo, pages, Download, content), with a clear focus ring at every stop.
- **The privacy promise holds.** The pages load nothing from any other website. The app's code only connects to the services the privacy page lists.
- **Links:** every link works. The one exception, iNaturalist's export page, blocks automated visitors with a "Just a moment…" check, so open it once yourself to confirm.
- **No jumping:** nothing moves while pages load, because every image has its size set.
- **Light pages:** Help, Privacy and Changelog are about 6 KB each.
- **Spelling:** no mistakes found, and British spelling throughout.

---

## 2. Mistakes

| # | Severity | What's wrong | Where |
|---|---|---|---|
| A1 | **Medium** | **"Privacy" is cut off on small phones.** At 320 px wide, the four page links need 318 px but only have 288 px, so you have to swipe the menu sideways to find Privacy, and nothing hints that you can. Bigger phones with large text set have the same problem. 320 px is the width the accessibility guidelines test for ("reflow"). | `style.css` narrow-screen nav |
| A2 | **Medium** | **"You match its columns once" is wrong.** Thicket doesn't save spreadsheet column choices. It guesses them from the column names each time, and you correct any it gets wrong. | `features.html:135` |
| A3 | **Medium** | **"Everything works from the keyboard" overclaims.** On the map, opening a pin and right-click "Add sighting here" need a mouse. | `features.html:177` |
| A4 | Medium‑low | **The map section oversells for US users.** Grid squares are UK-only since 1.1.0, but the page doesn't say so. "Offline … a plain outline map": that outline only covers Britain and Ireland, so a US user offline sees their sightings on a blank background (see C2). | `features.html:81`, `:84` |
| A5 | Low | **"Tick Also download the photos".** It's already ticked, and it only works with **Allow online features** on. It should say "untick it if you don't want them". | `help.html:115` |
| A6 | Low | **"Click a bar or a day"** on the statistics charts. The app says bars, cells and rows; there are no days. | `features.html:102` |
| A7 | Low | **"Restoring one takes a click"** is really pick, confirm, then a restart: a few clicks. | `features.html:161` |
| A8 | Low | **Checksum help:** <ul><li>It says "the checksum of each file", but there's only the installer's.</li><li>It doesn't say how to check one. (On Windows: `Get-FileHash .\Thicket-Setup-1.2.1.exe`.)</li></ul> | `help.html:72` |
| A9 | Low | **"Certificates cost hundreds of pounds a year"**: the packaging notes say £120–250. "Over £100 a year" is accurate. | `help.html:70` |
| A10 | Low | **Windows 10:** <ul><li>The uninstall steps name the Windows 11 menu only ("Installed apps"; Windows 10 calls it "Apps & features").</li><li>"Needs Windows 10 or 11" matches the release notes, but Thicket has only been tested on Windows 11.</li></ul> | `help.html:65`, `:127` |
| A11 | Low | **"Group a day out into an outing, with its weather"** sounds as if the weather fills itself in. You type it in. | `features.html:65` |
| A12 | Low | **The map screenshot's description leaves out London**, its biggest cluster (8.8k). | `features.html:91` |
| A13 | Low | **The header has no fallback colour.** `color-mix()` is a newer CSS feature. In a browser too old for it (roughly pre-2023), the header turns see-through and page text scrolls visibly behind it. Safari before version 18 also needs `-webkit-backdrop-filter` for the blur. | `style.css:221–222` |

---

## 3. Improvements

| # | Worth it? | What |
|---|---|---|
| B1 | **Yes** | **Smaller screenshots.** The 14 PNGs total 1,960 KB. As WebP they'd be about 690 KB: lossless (pixel-perfect) for app screens, high-quality lossy for the two maps. WebP works in every current browser. With B2, the features page drops from **1.1 MB to about 0.36 MB**. |
| B2 | **Yes** | **Smaller italic font.** It's 161 KB, 59% of the home page, for two words. Keeping one weight and only basic letters makes it **29 KB**. The home page drops from 275 KB to about 80 KB. |
| B3 | **Yes** | **Download straight away.** The button opens GitHub's release page, where visitors must pick the right file from four (installer, checksum, two source archives). A stable file name on each release (`Thicket-Setup.exe`, added by the release workflow) lets the button download the installer directly, and it always points to the newest. It takes effect from the next release: 1.2.1 doesn't have that file, so the button must keep opening the release page until then. If you'd rather not change the release workflow, add a line under the button saying which file to choose. |
| B4 | **Yes** | **Warn about the warnings.** <ul><li>Add a small line under the download button: "Windows may warn you the first time: here's why", linking to Help.</li><li>Help should also cover the browser's own warning ("isn't commonly downloaded"; in Edge: **…** › **Keep**), not just the blue Windows box.</li></ul> |
| B5 | **Yes** | **Link previews and a phone icon.** <ul><li>Tags so shared links show a picture and summary (on WhatsApp, Discord and Facebook).</li><li>An icon for phones that add the site to their home screen.</li></ul> |
| B6 | **Yes** (small) | **The logo, made from the app icon's own recipe.** My hand-drawn `logo.svg` differs from the app icon: a straight vein instead of the app's curved one. `scripts/make_icon.py` could write the site logo too, from the same leaf, so they can never drift apart. It also makes a solid leaf for tiny sizes, which suits the 16 px browser-tab icon better. |
| B7 | Nice | **A Thicket "page not found" page.** A broken link currently shows GitHub's generic 404, with no way back. A `404.html` in `site/` fixes that. |
| B8 | Nice | **A slimmer header on phones.** It's 106 px tall and stays on screen: 13% of a phone's height on every page. It could scroll away on phones. |
| B9 | Nice | **Tap a screenshot to see it full size.** On phones the screenshots are too small to read. Each could link to its full-size image. |
| B10 | Nice | **Privacy table on phones.** Its column headings are hidden there, so "OpenFreeMap" sits on its own without a label. Show a small label before each value instead. |
| B11 | Nice | **More Help answers:** <ul><li>"Moving to a new PC" (Restore › **Choose a backup file…** from your backup drive).</li><li>"Is there a Mac or phone version?" (No; take photos on your phone and add them to Thicket.)</li><li>Reporting on GitHub needs a free account.</li></ul> |
| B12 | Nice | **Trim two page descriptions.** Google shows about 155–160 characters: the home page's is 185, Features' is 167. |
| B13 | Nice | **Workflow pins.** <ul><li>The publish workflow downloads whatever pytest is newest. It could use the 9.1.1 the project already has locked, as the release workflow pins everything.</li><li>`ubuntu-latest` moves to Ubuntu 26 from 19 October; naming `ubuntu-24.04` keeps it steady.</li></ul> |
| B14 | Nice | **The site test** compares headers across pages but not footers. It could also check the B5 tags once they're added. |
| B15 | Your step | **Link the site from GitHub:** repo page › About (the cog) › Website. Then people browsing the code find the website. |
| B16 | Later | **The 1.0.1 changelog entry** mentions `docs/15-code-audit.md`, which doesn't exist on the website. Making it a link to GitHub would help. |

Contrast notes (no action needed):
- **Small grey text** (4.66:1) and **links** (4.60:1) pass, but only just; the minimum is 4.5.
- **The secondary button's edge** is faint (1.5:1). That's allowed, because its label already says it's a button.

---

## 4. Outside the website (found while checking it)

| # | What | Where |
|---|---|---|
| C1 | **App: unticked checkboxes are nearly invisible in dark mode.** For example, the map's "Places" box: a 1.1:1 box with no border. The guideline asks for 3:1. Nothing in the app's stylesheet styles the checkbox, so Qt draws it from the palette. | `ui/theme/stylesheet.py` |
| C2 | **App: the offline map outline only covers Britain and Ireland.** US users with online maps off, or offline, see a blank background. | `ui/web/assets/uk-outline.geojson`, `map.js` `plainStyle` |
| C3 | **Release: `SHA256SUMS.txt` has Windows line endings**, so the standard Mac and Linux check (`sha256sum -c`) refuses it. Windows' `Get-FileHash` is fine. A one-line fix in the workflow. | `.github/workflows/release.yml` |

---

## 5. Not checked

- **Lighthouse scores:** Google's free PageSpeed service had used up its daily allowance. You can run it yourself at https://pagespeed.web.dev with the site's address.
- **Load timings:** the browser pane was hidden, and hidden pages don't paint. Page weights were measured instead (section 3).
- **Safari and Firefox:** checked in Chromium only.

---

## 6. Fixed (18 October 2026)

- **Wording (A2–A12):** every claim now matches the app. The Privacy page got the same corrections: the offline map is a plain background, the photo box is ticked automatically, and iNaturalist's photos are stored with Amazon.
- **Layout (A1, A13, B8, B10):**
  - All four page links fit on one row of a 320 px phone, and wrap rather than hide when the text is large.
  - The header has a fallback colour for older browsers.
  - On phones the header scrolls away with the page.
  - The privacy table labels each value on phones.
- **Speed (B1, B2):** screenshots are WebP, made by `scripts/site_assets.py`: lossless for app screens, lossy for the maps. The italic font is down to 10 KB. **The home page is 59 KB (was 275 KB) and the features page 349 KB (was 1,142 KB).**
- **Icons and previews (B5, B6, B12):**
  - `scripts/make_icon.py --site` draws the header logo, tab icons and phone icon from the app icon's own recipe. They match it pixel for pixel, and `tests/unit/test_site_icons.py` keeps them in step.
  - Every page has link-preview tags with a 1200×630 picture.
  - The two long descriptions are trimmed.
- **Downloading (B3, B4):**
  - The home page links to the warnings help. Help now covers the browser's warning as well as Windows'.
  - **Every Download button downloads `Thicket-Setup.exe` directly**, always the newest version. Releases carry it automatically (`release.yml`). 1.2.1 got its copy from the new "Add Thicket-Setup.exe to a release" workflow: byte-identical to the original installer, checked on 18 Oct.
- **Pages (B7, B9, B11):**
  - A Thicket "page not found" page.
  - Tapping a screenshot opens it full size, in the visitor's theme.
  - Help answers "Moving to a new PC" and "Mac or phone?", and notes that reporting needs a free GitHub account.
- **Workflows (B13, C3):** the website workflow uses pytest 9.1.1 and Ubuntu 24.04. `SHA256SUMS.txt` gets Unix line endings: tested with a dummy file, and `sha256sum -c` passes.
- **Tests (B14):** the site test now has 40 checks, up from 27: link previews, identical footers, the 404 page, every download button the same, and full-size links matching their screenshots. The whole suite is 617 tests.
