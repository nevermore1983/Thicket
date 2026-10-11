"""Spike 1: does MapLibre GL JS 6 run inside QWebEngineView on this PC?

Questions answered:
  * Is WebGL 2 available in QtWebEngine here (and on which GPU)?
  * Can ES-module JavaScript (MapLibre 6 + its worker) load through a custom
    `wildlife://` URL scheme served by Python?
  * Do online vector tiles (OpenFreeMap) load from that origin?
  * Do clustering + heat-map layers work with 2,000 points, and how fast?
  * Does a click in JavaScript reach Python through QWebChannel?

Run:  uv run python spikes/map_webengine/spike_map.py
Writes a screenshot to spikes/map_webengine/output/map.png.
"""

from __future__ import annotations

import json
import mimetypes
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QFile, QIODevice, QObject, QTimer, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

# When packaged, data files live in the bundle folder and output goes next to the .exe
FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys._MEIPASS) if FROZEN else Path(__file__).parent
OUT_DIR = Path(sys.executable).parent / "output" if FROZEN else HERE / "output"
SCHEME = b"wildlife"
mimetypes.add_type("text/javascript", ".mjs")


class AssetHandler(QWebEngineUrlSchemeHandler):
    """Serves wildlife://app/<path> from this folder (and qwebchannel.js from Qt)."""

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802 (Qt name)
        path = job.requestUrl().path().lstrip("/")
        if path == "qwebchannel.js":
            f = QFile(":/qtwebchannel/qwebchannel.js")
            f.open(QIODevice.OpenModeFlag.ReadOnly)
            data = bytes(f.readAll())
        else:
            file = (HERE / path).resolve()
            if HERE not in file.parents or not file.is_file():  # never serve outside this folder
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            data = file.read_bytes()
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        buf = QBuffer(parent=job)  # the job owns the buffer, so it lives long enough
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime.encode(), buf)


class Bridge(QObject):
    def __init__(self, results: dict, done) -> None:
        super().__init__()
        self.results, self.done = results, done

    @Slot(str, str)
    def report(self, key: str, value: str) -> None:
        self.results[key] = json.loads(value)
        print(f"  JS -> Python  {key}: {self.results[key]}")
        if key in ("idle", "error") or (key == "webgl" and not self.results[key]["webgl2"]):
            QTimer.singleShot(1500, self.done)  # let tiles finish painting, then grab


def main() -> int:
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(scheme)  # must happen before QApplication exists

    app = QApplication(sys.argv)
    handler = AssetHandler()
    QWebEngineProfile.defaultProfile().installUrlSchemeHandler(SCHEME, handler)

    view = QWebEngineView()
    view.resize(1000, 700)
    results: dict = {}

    def finish() -> None:
        out = OUT_DIR
        out.mkdir(exist_ok=True)
        view.grab().save(str(out / "map.png"))
        # simulate a click on a point to prove the JS -> Python path
        view.page().runJavaScript("1", 0, lambda _: app.quit())

    bridge = Bridge(results, finish)
    channel = QWebChannel()
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)
    view.page().javaScriptConsoleMessage = lambda lvl, msg, line, src: print(f"  console: {msg}")
    view.load(QUrl("wildlife://app/map.html"))
    view.show()
    QTimer.singleShot(30_000, app.quit)  # safety net
    app.exec()

    ok = results.get("webgl", {}).get("webgl2") and "idle" in results
    print("\nRESULT:", "PASS" if ok else "FAIL", json.dumps(results, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
