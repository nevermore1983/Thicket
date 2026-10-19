# Thicket — promo video (plan)

**Date:** 19 October 2026
**Status:** Plan for your approval. No code yet.

A short video that shows Thicket working, for the website's home page (and YouTube or social media if you like). Thicket films itself: a script drives the real app on the demo library and records it, so the video is sharp, shows no personal data, and can be re-made with one command whenever the app changes.

---

## 1. The video

- **About 35 seconds**, widescreen 1280×720, light theme.
- **Short captions** on each scene, so it works with the sound off.
- **Background birdsong** (added 19 Oct, your choice): Mixkit's "Forest birds ambience" (mixkit.co, sound effect 1210), faded in and out, at a quiet, even level.
  - Its **Sound Effects Free License** allows it in videos on websites, YouTube and social media, commercial or not, with no credit needed.
  - It **forbids redistributing the sound file itself**, including "with source files". So the WAV stays in the git-ignored `local_data/video/` and is never committed. Only the finished video, with the sound mixed in, is published.
  - The command: `uv run --with imageio-ffmpeg python scripts/promo_video.py --sound local_data/video/mixkit-forest-birds-ambience-1210.wav`
- **About 3–5 MB** as an MP4 that plays everywhere.

| # | Scene | About | Caption |
|---|---|---|---|
| 1 | Title card: the leaf logo on Thicket green | 3 s | **Thicket** · Your wildlife journal, right on your PC |
| 2 | Dashboard → **Add sighting**: "gold" typed letter by letter, suggestions appear, Goldfinch picked, count "c. 40", saved | 8 s | Record a sighting in seconds |
| 3 | Calendar month → the busiest day opens with its sightings | 5 s | See your year at a glance |
| 4 | Map: clusters, zoom in towards a hotspot, switch to the heat map | 6 s | Every sighting on a map |
| 5 | Statistics: the year's totals, then the species list growing | 5 s | Statistics that answer questions |
| 6 | Species profile: a species' months and best count | 4 s | Your year lists and life list |
| 7 | End card | 4 s | Free for Windows · Everything stays on your PC · nevermore1983.github.io/Thicket |

- **A drawn mouse pointer** glides to each button and shows a small ripple when it "clicks". The recording is made off-screen, where there's no real pointer, so without one things would happen by magic.
- **No photos scene**: the demo photos are drawings (blue blobs), as on the website. If you have 5–10 wildlife photos you're happy to show publicly, a "photos become a sighting" scene could be added later.

---

## 2. How it's made

- **`scripts/promo_video.py`**, a new script built on what `scripts/screenshot.py` already does:
  1. Opens Thicket off-screen on a **fresh copy** of the demo library, so the real `demo9` library and your own data are never touched.
  2. Plays each scene as a list of steps ("move to the Add button", "type gold", "wait half a second").
  3. Grabs the window 30 times a second.
  4. Draws the captions and title cards with the app's own colours and font.
- **ffmpeg** joins the frames into an MP4. The copy on your PC is from 2013, so the script uses a current build from PyPI (the `imageio-ffmpeg` package, about 30 MB). **That's a download I'll ask you about first.**
- **Output:** `site/video/thicket-tour.mp4`, plus a still "poster" frame shown before it plays.
- **On the website:** the home page shows the video under the main screenshot, with play controls.
  - It doesn't play by itself, and it only downloads when someone presses play, so the page stays fast.
  - A text description is included for screen readers.
  - It's self-hosted, so the privacy page's "nothing loads from elsewhere" stays true.

---

## 3. Steps

Each ends with a short report and waits for your OK.

1. **Trial scene.** Only scene 2 (adding a sighting), to check it looks smooth and how big the file gets. You watch it.
2. **The whole video.** All the scenes, the title and end cards, and the pointer.
3. **On the website.** The video on the home page, a test, and a check on phones. Then publish (I'll ask first).

---

## 4. Not in this version

- Voice-over or music.
- A dark-mode cut, or square/vertical cuts for social media (easy to add later, from the same script).
- Uploading to YouTube. That's your account, so you'd do it with the MP4.
