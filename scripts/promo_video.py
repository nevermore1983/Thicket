"""Film a short tour of Thicket for the website (docs/19-promo-video-plan.md).

    uv run --with imageio-ffmpeg python scripts/promo_video.py
    uv run --with imageio-ffmpeg python scripts/promo_video.py --scenes add map --out local_data/video/try.mp4

For the website, with the birdsong (which stays out of git: its licence forbids sharing
the file itself). --site copies the video into site/video and remakes its poster:

    uv run --with imageio-ffmpeg python scripts/promo_video.py --site --sound local_data/video/mixkit-forest-birds-ambience-1210.wav

Opens Thicket off-screen on a fresh copy of the demo library (local_data/demo9, never your
own data) and plays each scene as the steps a person would take: real clicks and key
presses. The window is grabbed 30 times a second and piped to ffmpeg (a current build,
from the imageio-ffmpeg package) to make an H.264 MP4. There's no real mouse pointer
off-screen, so one is drawn, with a ripple where it clicks.

The window is 1440x810 and each frame is scaled to 1280x720: big enough that nothing
needs a scrollbar, small enough that the text stays readable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QScrollArea, QWidget

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "local_data" / "demo9"
COPY = ("wildlife.db", "photos", "thumbnails", "maps")  # everything but the backups
WINDOW = QSize(1440, 810)  # what Thicket draws
SIZE = QSize(1280, 720)  # the video
SCALE = SIZE.width() / WINDOW.width()
FPS = 30
FADE = round(0.35 * FPS)  # frames of cross-fade between scenes
WEBSITE = "nevermore1983.github.io/Thicket"
SITE_VIDEO = ROOT / "site" / "video" / "thicket-tour.mp4"
SITE_POSTER = ROOT / "site" / "images" / "tour-poster.webp"
SITE_CAPTIONS = ROOT / "site" / "video" / "thicket-tour.vtt"
POSTER_FRAME = 200  # "gold" typed, the suggestions showing


def ease(t: float) -> float:
    """Slow, fast, slow: how a hand moves a mouse."""
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Recorder:
    """Runs the app in real time and records a frame every 1/30 s, with the pointer and
    captions drawn on top."""

    def __init__(self, app: QApplication, window: QWidget, out: Path, tokens) -> None:
        import imageio_ffmpeg

        self.app, self.window, self.t = app, window, tokens
        self.pointer = QPointF(WINDOW.width() * 0.62, WINDOW.height() * 0.62)  # window coords
        self.pointer_shown = False
        self.ripple: tuple[QPointF, int] | None = None  # where, and frames since the click
        self.caption: tuple[str, int, int] | None = None  # text, first frame, last frame
        self.fade: tuple[QImage, int] | None = None  # the frame we're fading from, frames left
        self.previous: QImage | None = None
        self.frames = 0
        out.parent.mkdir(parents=True, exist_ok=True)
        self.out = out
        size = f"{SIZE.width()}x{SIZE.height()}"
        frames_in = ("-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(FPS), "-i", "-")
        h264_out = ("-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p")
        self.ffmpeg = subprocess.Popen(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                *frames_in,
                *h264_out,
                "-movflags",
                "+faststart",
                str(out),
            ],
            stdin=subprocess.PIPE,
        )
        self.start = time.monotonic()
        self.late = 0  # frames grabbed after they were due (the video then runs fast there)

    # ---- frames ----------------------------------------------------------------------
    def tick(self, still: QImage | None = None) -> None:
        """Let the app run until the next frame is due, then record it (or `still`)."""
        due = self.start + self.frames / FPS
        if time.monotonic() > due + 1 / FPS:
            self.late += 1
        while True:
            self.app.processEvents()
            left = due - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(left, 0.004))
        if still is not None:
            image = still.copy()
        else:
            grabbed = self.window.grab().toImage().convertToFormat(QImage.Format.Format_RGB888)
            image = grabbed.scaled(
                SIZE,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._overlay(image, app_frame=still is None)
        assert image.bytesPerLine() == SIZE.width() * 3  # rows packed, as ffmpeg expects
        self.ffmpeg.stdin.write(bytes(image.constBits()))
        self.previous = image
        self.frames += 1

    def hold(self, seconds: float, still: QImage | None = None) -> None:
        for _ in range(round(seconds * FPS)):
            self.tick(still)

    def wait(self, done: Callable[[], bool], seconds: float) -> None:
        """Let the app get ready (a page loading) without recording; the video doesn't
        jump, it just carries on from the last frame."""
        began = time.monotonic()
        while time.monotonic() - began < seconds and not done():
            self.app.processEvents()
            time.sleep(0.01)
        self.start += time.monotonic() - began

    def cut(self) -> None:
        """The next frames fade in over the last one."""
        if self.previous is not None:
            self.fade = (self.previous.copy(), FADE)

    def close(self) -> None:
        self.ffmpeg.stdin.close()
        self.ffmpeg.wait()
        took = time.monotonic() - self.start
        print(
            f"{self.out}: {self.frames} frames ({self.frames / FPS:.1f} s of video) in "
            f"{took:.1f} s of filming; {self.late} frames late; "
            f"{self.out.stat().st_size / 1e6:.1f} MB"
        )

    # ---- what a person does --------------------------------------------------------------
    def where(self, widget: QWidget, pos: QPoint | None = None) -> QPointF:
        return QPointF(
            widget.mapTo(self.window, pos if pos is not None else widget.rect().center())
        )

    def reveal(self, widget: QWidget) -> None:
        """Scroll the panel or page so `widget` is in view, as a person would."""
        parent = widget.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            parent.ensureWidgetVisible(widget, 0, 60)

    def move(self, widget: QWidget, pos: QPoint | None = None, seconds: float = 0.55) -> None:
        self.pointer_shown = True
        start, end = QPointF(self.pointer), self.where(widget, pos)
        steps = max(1, round(seconds * FPS))
        for i in range(1, steps + 1):
            self.pointer = start + (end - start) * ease(i / steps)
            self.tick()

    def click(self, widget: QWidget, pos: QPoint | None = None) -> None:
        self.reveal(widget)
        self.move(widget, pos)
        self.hold(0.08)
        self.ripple = (QPointF(self.pointer), 0)
        QTest.mouseClick(
            widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos if pos is not None else widget.rect().center(),
        )
        self.hold(0.25)

    def type(
        self, widget: QWidget, text: str, per_key: float = 0.11, replace: bool = False
    ) -> None:
        if replace:  # Ctrl+A first, so the text replaces what's there
            QTest.keyClick(widget, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            self.hold(0.15)
        for ch in text:
            QTest.keyClicks(widget, ch)
            self.hold(per_key)

    def scroll(self, area: QScrollArea, to: int, seconds: float) -> None:
        """Scroll smoothly, like a mouse wheel."""
        bar = area.verticalScrollBar()
        start, end = bar.value(), min(to, bar.maximum())
        steps = round(seconds * FPS)
        for i in range(1, steps + 1):
            bar.setValue(round(start + (end - start) * ease(i / steps)))
            self.tick()

    def say(self, text: str, seconds: float) -> None:
        """Show a caption for the next `seconds` (it fades in and out)."""
        self.caption = (text, self.frames, self.frames + round(seconds * FPS))

    # ---- cards (the title and the end) -------------------------------------------------
    def card(self, title: str, lines: list[str], link: str = "") -> QImage:
        t = self.t
        image = QImage(SIZE, QImage.Format.Format_RGB888)
        image.fill(QColor(t.bg))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        logo = 104
        top = SIZE.height() // 2 - 150
        QSvgRenderer(str(ROOT / "site" / "images" / "logo.svg")).render(
            p, QRectF((SIZE.width() - logo) / 2, top, logo, logo)
        )
        p.setPen(QColor(t.text))
        p.setFont(font(54, QFont.Weight.Bold))
        y = top + logo + 26
        p.drawText(QRectF(0, y, SIZE.width(), 70), Qt.AlignmentFlag.AlignCenter, title)
        y += 78
        p.setPen(QColor(t.text_2))
        p.setFont(font(25, QFont.Weight.Normal, display=False))
        for line in lines:
            p.drawText(QRectF(0, y, SIZE.width(), 40), Qt.AlignmentFlag.AlignCenter, line)
            y += 42
        if link:
            p.setPen(QColor(t.accent))
            p.setFont(font(25, QFont.Weight.DemiBold, display=False))
            p.drawText(QRectF(0, y + 14, SIZE.width(), 40), Qt.AlignmentFlag.AlignCenter, link)
        p.end()
        return image

    def show_card(self, image: QImage, seconds: float) -> None:
        self.pointer_shown = False
        self.caption = None
        self.cut()
        self.hold(seconds, still=image)

    # ---- drawing ---------------------------------------------------------------------
    def _overlay(self, image: QImage, app_frame: bool) -> None:
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if app_frame:
            self._draw_caption(p)
            self._draw_ripple(p)
            if self.pointer_shown:
                self._draw_pointer(p)
        if self.fade is not None:
            old, left = self.fade
            p.setOpacity(left / (FADE + 1))
            p.drawImage(0, 0, old)
            self.fade = (old, left - 1) if left > 1 else None
        p.end()

    def _draw_caption(self, p: QPainter) -> None:
        if self.caption is None:
            return
        text, first, last = self.caption
        if not first <= self.frames <= last:
            return
        fade = round(0.35 * FPS)
        p.setOpacity(min(1.0, (self.frames - first) / fade, (last - self.frames) / fade))
        p.setFont(font(21, QFont.Weight.DemiBold))
        box = p.fontMetrics().boundingRect(text).adjusted(-22, -13, 22, 13)
        box.moveBottomLeft(QPoint(32, SIZE.height() - 32))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(23, 32, 26, 228))
        p.drawRoundedRect(QRectF(box), 12, 12)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        p.setOpacity(1.0)

    def _draw_ripple(self, p: QPainter) -> None:
        if self.ripple is None:
            return
        where, age = self.ripple
        life = round(0.45 * FPS)
        if age > life:
            self.ripple = None
            return
        t = age / life
        colour = QColor(self.t.accent)
        colour.setAlphaF(0.55 * (1 - t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        radius = 6 + 18 * t
        p.drawEllipse(where * SCALE, radius, radius)
        self.ripple = (where, age + 1)

    def _draw_pointer(self, p: QPainter) -> None:
        # The classic arrow, 1.25x the usual size so it reads in a small video
        shape = [(0, 0), (0, 17), (4.2, 13.2), (7, 19.5), (9.8, 18.3), (7.1, 12.2), (12.5, 12.2)]
        path = QPainterPath()
        path.moveTo(*shape[0])
        for x, y in shape[1:]:
            path.lineTo(x, y)
        path.closeSubpath()
        p.save()
        p.translate(self.pointer * SCALE)
        p.scale(1.25, 1.25)
        p.translate(1.2, 1.6)
        p.fillPath(path, QColor(0, 0, 0, 70))  # soft shadow
        p.translate(-1.2, -1.6)
        p.setPen(QPen(QColor("#17201a"), 1.2))
        p.setBrush(QColor("#ffffff"))
        p.drawPath(path)
        p.restore()


def font(size: int, weight: QFont.Weight, display: bool = True) -> QFont:
    f = QFont("Segoe UI Variable Display" if display else "Segoe UI Variable Text", size)
    f.setWeight(weight)
    return f


def start_fresh(window) -> None:
    """Each scene starts clean: no side panel open, no message from the last scene."""
    from wildlife.ui.components.toast import Toast

    window.panel.close_panel()
    for toast in window.findChildren(Toast):
        toast.dismiss()


def button(parent: QWidget, text: str) -> QAbstractButton:
    return next(b for b in parent.findChildren(QAbstractButton) if b.text() == text)


def missing_hooks(window) -> list[str]:
    """The parts of the app the scenes below rely on that no longer exist.

    Several are private (their names start with _), so an app change can rename them
    without warning. tests/ui/test_promo_video.py runs this on a real window, so such a
    change fails the tests instead of breaking the next re-film. Keep it in step with the
    scenes: anything a scene reaches into belongs here."""
    from wildlife.ui.components.toast import Toast

    calendar, map_page = window.calendar_page, window.map_page
    stats, species = window.statistics_page, window.species_page
    checks: list[tuple[str, Callable[[], object]]] = [
        ("window.add_button", lambda: window.add_button),
        ("window.go", lambda: window.go),
        (
            "window.panel.close_panel / current",
            lambda: (window.panel.close_panel, window.panel.current),
        ),
        ("window.ctx.sightings._today()", lambda: window.ctx.sightings._today()),
        ("Toast.dismiss", lambda: Toast.dismiss),
        ("calendar_page.go_to", lambda: calendar.go_to),
        ("calendar month_view.days", lambda: calendar.month_view.days is not None),
        ("calendar month_view.first_cell()", lambda: calendar.month_view.first_cell()),
        ("calendar month_view._cell_rect()", lambda: calendar.month_view._cell_rect(0)),
        ("map_page.ready / failed", lambda: (map_page.ready, map_page.failed) is not None),
        ("map_page._bounds", lambda: hasattr(map_page, "_bounds") or None),
        (
            "map_page.set_mode / fit / view",
            lambda: (map_page.set_mode, map_page.fit, map_page.view),
        ),
        ("map_page._send", lambda: map_page._send),
        ("map_page.modes._buttons['heat']", lambda: map_page.modes._buttons["heat"]),
        ("statistics_page.data", lambda: hasattr(stats, "data") or None),
        ("statistics_page PageScroll", lambda: stats.findChild(QScrollArea, "PageScroll")),
        ("species_page._choose", lambda: species._choose),
        ("species_page.table", lambda: species.table.sortItems),
    ]
    missing = []
    for name, check in checks:
        try:
            if check() is None:
                missing.append(name)
        except (AttributeError, KeyError, TypeError) as error:
            missing.append(f"{name} ({error})")
    # The Add sighting panel only exists while it's open
    window.add_sighting()
    editor = window.panel.current()
    for name in ("picker.edit", "picker.list", "count", "save_btn", "_dirty"):
        target = editor
        for part in name.split("."):
            target = getattr(target, part, None)
        if target is None:
            missing.append(f"Add sighting panel: {name}")
    editor._dirty = False
    window.panel.close_panel()
    return missing


# ---- scenes --------------------------------------------------------------------------------
def scene_title(rec: Recorder, window) -> None:
    rec.show_card(rec.card("Thicket", ["Your wildlife journal, right on your PC"]), 3.0)


def scene_add(rec: Recorder, window) -> None:
    """Add a sighting: type 'gold', pick Goldfinch, the Garden, a rough count, save."""
    start_fresh(window)
    window.go("dashboard")
    rec.cut()
    rec.hold(0.9)
    rec.say("Record a sighting in seconds", 9.0)
    rec.click(window.add_button)
    rec.hold(0.6)
    editor = window.panel.current()
    rec.click(editor.picker.edit)
    rec.type(editor.picker.edit, "gold")
    rec.hold(0.6)
    suggestions = editor.picker.list
    goldfinch = next(
        suggestions.item(i)
        for i in range(suggestions.count())
        if getattr(suggestions.item(i).data(Qt.ItemDataRole.UserRole), "common_name", "")
        == "Goldfinch"
    )
    rec.click(suggestions.viewport(), suggestions.visualItemRect(goldfinch).center())
    rec.hold(0.4)
    rec.click(button(editor, "Garden"))
    rec.hold(0.3)
    rec.click(editor.count)
    rec.type(editor.count, "c. 40", replace=True)
    rec.hold(0.5)
    rec.click(editor.save_btn)
    rec.hold(1.8)
    if window.panel.current() is not None:
        print("warning: the Add sighting panel is still open after Save (did it save?)")


def scene_calendar(rec: Recorder, window) -> None:
    """The month, then its busiest day opens beside it."""
    start_fresh(window)
    page = window.calendar_page
    window.go("calendar")
    page.go_to(window.ctx.sightings._today(), "month")
    rec.wait(lambda: bool(page.month_view.days), 5)
    rec.cut()
    rec.say("See your year at a glance", 5.2)
    rec.hold(1.0)
    month = page.month_view
    busiest = max(month.days.values(), key=lambda s: s.sightings)
    cell = month._cell_rect((busiest.day - month.first_cell()).days)
    rec.click(month, cell.center().toPoint())
    rec.hold(3.0)


def scene_map(rec: Recorder, window) -> None:
    """All the sightings, a zoom towards the busiest area, then the heat map."""
    start_fresh(window)
    page = window.map_page
    window.go("map")
    rec.wait(lambda: page.ready or page.failed, 20)
    page.set_mode("pins")
    rec.wait(lambda: page._bounds is not None, 8)
    # Visit the zoomed-in view once first, so its map tiles are ready when filmed
    target = {"lat": 51.6, "lon": 0.35, "zoom": 8.6, "highlight": False}
    page._send("flyTo", **target)
    rec.wait(lambda: False, 3.5)
    page.fit()
    rec.wait(lambda: False, 3.0)
    rec.cut()
    rec.say("Every sighting on a map", 6.8)
    rec.hold(1.4)
    rec.move(page.view, QPoint(page.view.width() * 2 // 3, page.view.height() * 3 // 4), 0.6)
    page._send("flyTo", **target)
    rec.hold(1.8)
    rec.click(page.modes._buttons["heat"])
    rec.hold(2.6)


def scene_statistics(rec: Recorder, window) -> None:
    start_fresh(window)
    page = window.statistics_page
    window.go("statistics")
    rec.wait(lambda: page.data is not None, 10)
    rec.wait(lambda: False, 0.5)
    rec.cut()
    rec.say("Statistics that answer questions", 5.2)
    rec.hold(1.3)
    rec.scroll(page.findChild(QScrollArea, "PageScroll"), 430, 1.8)
    rec.hold(1.9)


def scene_species(rec: Recorder, window) -> None:
    start_fresh(window)
    page = window.species_page
    window.go("species")
    page._choose(date.today().year)
    page.table.sortItems(2, Qt.SortOrder.DescendingOrder)
    rec.wait(lambda: False, 0.4)
    rec.cut()
    rec.say("Your year lists and life list", 4.6)
    rec.hold(0.9)
    first = page.table.item(0, 0)
    rec.click(page.table.viewport(), page.table.visualItemRect(first).center())
    rec.hold(2.9)


def scene_end(rec: Recorder, window) -> None:
    card = rec.card(
        "Thicket",
        ["Free for Windows", "Everything stays on your PC"],
        link=WEBSITE,
    )
    rec.show_card(card, 4.0)


SCENES: dict[str, Callable[[Recorder, QWidget], None]] = {
    "title": scene_title,
    "add": scene_add,
    "calendar": scene_calendar,
    "map": scene_map,
    "statistics": scene_statistics,
    "species": scene_species,
    "end": scene_end,
}


def probe(video: Path) -> tuple[float, bool]:
    """The video's length in seconds, and whether it has sound."""
    import imageio_ffmpeg

    info = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(video)],
        capture_output=True,
        text=True,
    ).stderr  # ffmpeg describes its input on stderr (and complains there's no output)
    hours, minutes, seconds = info.split("Duration: ")[1].split(",")[0].split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds), "Audio:" in info


def captions(length: float, has_sound: bool) -> str:
    """A WebVTT captions file for the video. Its words are already drawn into the picture,
    so the captions describe the sound, for people who can't hear it."""

    def stamp(seconds: float) -> str:
        minutes, rest = divmod(seconds, 60)
        return f"00:{int(minutes):02d}:{rest:06.3f}"

    if not has_sound:
        return f"WEBVTT\n\n00:00:00.000 --> {stamp(length)}\n[No sound]\n"
    return (
        "WEBVTT\n\n"
        f"00:00:00.000 --> {stamp(min(6.0, length))}\n"
        "[Gentle forest birdsong plays throughout. No speech.]\n\n"
        f"{stamp(max(0.0, length - 3.0))} --> {stamp(length)}\n"
        "[The birdsong fades out]\n"
    )


def add_soundtrack(silent: Path, sound: Path, start: float, out: Path) -> None:
    """Lay `sound` (from `start` seconds in) under the video, fading in and out, at a steady
    background loudness. The sound file itself is never published or committed: only the
    finished video, which its licence allows (docs/19-promo-video-plan.md)."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    length, _ = probe(silent)
    sound_filter = (
        "afade=t=in:d=1.5,"
        f"afade=t=out:st={length - 2.5:.2f}:d=2.5,"
        "loudnorm=I=-23:TP=-2:LRA=11,aresample=44100"  # a quiet, even background level
    )
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(silent),
            "-ss", str(start), "-t", f"{length:.2f}", "-i", str(sound),
            "-filter_complex", f"[1:a]{sound_filter}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
            "-movflags", "+faststart", str(out),
        ],
        check=True,
    )  # fmt: skip
    print(f"{out}: with sound from {sound.name}, {out.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", nargs="+", default=list(SCENES), choices=list(SCENES))
    parser.add_argument("--out", type=Path, default=Path("local_data/video/thicket-tour.mp4"))
    parser.add_argument(
        "--sound",
        type=Path,
        help="a background sound to lay under the video, e.g. "
        "local_data/video/mixkit-forest-birds-ambience-1210.wav (keep it out of git)",
    )
    parser.add_argument("--sound-start", type=float, default=0.0, help="seconds into the sound")
    parser.add_argument(
        "--site", action="store_true", help="also put the video and its poster on the website"
    )
    parser.add_argument(
        "--site-from",
        type=Path,
        help="don't film: put this existing video (and a fresh poster and captions) on the website",
    )
    args = parser.parse_args()
    if args.site_from:
        to_website(args.site_from)
        return 0
    if args.sound and not args.sound.is_file():
        raise SystemExit(f"No sound file at {args.sound}")
    final = args.out
    if args.sound:  # film silently first, then add the sound
        args.out = final.with_name(final.stem + "-silent" + final.suffix)
    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Needs ffmpeg: run with `uv run --with imageio-ffmpeg python ...`"
        ) from None

    work = Path(
        tempfile.mkdtemp(prefix="thicket-video-")
    )  # a copy: the demo library stays as it is
    for name in COPY:
        source = DEMO / name
        if source.is_dir():
            shutil.copytree(source, work / name)
        elif source.exists():
            shutil.copy2(source, work / name)

    sys.path.insert(0, str(ROOT / "src"))
    from wildlife.config.paths import DataPaths
    from wildlife.config.settings import Theme
    from wildlife.context import AppContext
    from wildlife.logging_setup import setup_logging

    paths = DataPaths(work).ensure()
    setup_logging(paths.logs)
    QCoreApplication.setOrganizationName("Thicket-Video")  # don't touch real window state
    from wildlife.ui.web import scheme

    scheme.prepare()
    app = QApplication(sys.argv[:1])

    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.theme.manager import ThemeManager
    from wildlife.ui.theme.tokens import LIGHT

    ctx = AppContext.open(paths)
    theme = ThemeManager(app)
    theme.set_theme(Theme.LIGHT)
    window = MainWindow(ctx, theme)
    window.resize(WINDOW)
    window.show()
    # With the side panel open the dashboard is a little too wide and gains a sideways
    # scrollbar; in a short video that only looks untidy, so pages don't show one
    for area in window.findChildren(QScrollArea):
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def film() -> None:
        rec = Recorder(app, window, args.out, LIGHT)
        try:
            for name in args.scenes:
                SCENES[name](rec, window)
        finally:
            rec.close()
            if window.panel.current() is not None:
                window.panel.current()._dirty = False  # no "Discard changes?" on the way out
            app.quit()

    QTimer.singleShot(800, film)
    app.exec()
    ctx.close()
    shutil.rmtree(work, ignore_errors=True)
    if args.sound:
        add_soundtrack(args.out, args.sound, args.sound_start, final)
        args.out.unlink()
    if args.site:
        to_website(final)
    return 0


def to_website(video: Path) -> None:
    """Put the video on the website: site/video/thicket-tour.mp4, its captions (.vtt) and
    its poster (the moment 'gold' brings up suggestions) as site/images/tour-poster.webp."""
    import imageio_ffmpeg
    from PIL import Image

    written = [SITE_CAPTIONS, SITE_POSTER]
    if video.resolve() != SITE_VIDEO.resolve():
        shutil.copy2(video, SITE_VIDEO)
        written.insert(0, SITE_VIDEO)
    SITE_CAPTIONS.write_text(captions(*probe(SITE_VIDEO)), encoding="utf-8", newline="\n")
    still = Path(tempfile.mkdtemp(prefix="thicket-poster-")) / "poster.png"
    pick = f"select=eq(n\\,{POSTER_FRAME})"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(SITE_VIDEO), "-vf", pick, "-frames:v", "1", "-fps_mode", "vfr", str(still)],
        check=True,
    )  # fmt: skip
    # Quality 80: no visible difference at the size it's shown, and a third smaller (it
    # loads with every visit to the home page, even when the video isn't played)
    Image.open(still).convert("RGB").save(SITE_POSTER, "WEBP", quality=80, method=6)
    shutil.rmtree(still.parent, ignore_errors=True)
    for path in written:
        print(f"{path.relative_to(ROOT)} updated")


if __name__ == "__main__":
    sys.exit(main())
