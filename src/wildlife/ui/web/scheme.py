"""Serving the app's web pages through its own `wildlife://` address scheme.

Why not open files directly? MapLibre 6 is made of JavaScript *modules*, and
the browser engine refuses to load modules from plain files. A custom scheme
also lets Python hand the page data (GeoJSON) without a local web server and
without opening any network port.

    wildlife://app/map.html          a file from ui/web/assets/
    wildlife://app/qwebchannel.js    Qt's bridge script
    wildlife://app/data/<name>?v=3   data Python published with WebHandler.publish()

A request interceptor (NetworkGate) keeps the pages away from the internet,
except for the online map host while "Allow online features" is on.
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from importlib import resources
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QFile,
    QIODevice,
    QObject,
    Qt,
    QUrl,
)
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

log = logging.getLogger(__name__)
SCHEME = b"wildlife"
ONLINE_HOSTS = frozenset({"tiles.openfreemap.org"})
ASSETS = Path(str(resources.files("wildlife.ui.web") / "assets"))
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/geo+json", ".geojson")


def prepare() -> None:
    """Run before the QApplication is created: Qt reads URL schemes once, at start-up, and
    the web engine needs shared OpenGL contexts to be created later (on first map visit)."""
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    if QWebEngineUrlScheme.schemeByName(SCHEME).name() == SCHEME:
        return
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.FetchApiAllowed  # MapLibre's worker fetches our GeoJSON
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class WebHandler(QWebEngineUrlSchemeHandler):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._data: dict[str, tuple[bytes, str]] = {}
        self._versions: dict[str, int] = {}
        self._lock = threading.Lock()

    def publish(self, name: str, data: bytes, mime: str = "application/geo+json") -> str:
        """Make `data` available to pages; returns its URL (new each time, so nothing is cached)."""
        with self._lock:
            self._data[name] = (data, mime)
            self._versions[name] = self._versions.get(name, 0) + 1
            return f"wildlife://app/data/{name}?v={self._versions[name]}"

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        path = job.requestUrl().path().lstrip("/")
        if path == "qwebchannel.js":
            f = QFile(":/qtwebchannel/qwebchannel.js")
            f.open(QIODevice.OpenModeFlag.ReadOnly)
            self._reply(job, bytes(f.readAll()), "text/javascript")
        elif path.startswith("data/"):
            with self._lock:
                found = self._data.get(path[5:])
            if found is None:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            else:
                self._reply(job, *found)
        else:
            file = (ASSETS / path).resolve()
            if ASSETS.resolve() not in file.parents or not file.is_file():  # never outside assets
                log.warning("Web page asked for a missing file: %s", path)
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._reply(job, file.read_bytes(), mime)

    @staticmethod
    def _reply(job: QWebEngineUrlRequestJob, data: bytes, mime: str) -> None:
        buf = QBuffer(parent=job)  # the job owns the buffer, so it lives long enough
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime.encode(), buf)


class NetworkGate(QWebEngineUrlRequestInterceptor):
    """Blocks every internet request except the online map host, and that only when allowed."""

    def __init__(self, online_allowed: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.online_allowed = online_allowed

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url: QUrl = info.requestUrl()
        if not is_allowed(url.scheme(), url.host(), self.online_allowed):
            log.debug("Blocked %s", url.toString())
            info.block(True)


def is_allowed(scheme: str, host: str, online_allowed: bool) -> bool:
    """The page may load its own files, and the online map host over HTTPS when allowed."""
    if scheme in ("wildlife", "data", "blob", "qrc"):
        return True
    return online_allowed and scheme == "https" and host in ONLINE_HOSTS


_profile: QWebEngineProfile | None = None
_handler: WebHandler | None = None
_gate: NetworkGate | None = None


def profile(
    cache_dir: Path, online_allowed: bool
) -> tuple[QWebEngineProfile, WebHandler, NetworkGate]:
    """The app's one browser profile (created on first use). Map tiles are cached on disk
    in cache_dir, so areas you've looked at load faster and partly work offline."""
    global _profile, _handler, _gate
    if _profile is None:
        _profile = QWebEngineProfile("wildlife")
        _profile.setCachePath(str(cache_dir / "cache"))
        _profile.setPersistentStoragePath(str(cache_dir / "storage"))
        _profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        _profile.setHttpCacheMaximumSize(300 * 1024 * 1024)
        _profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        _handler = WebHandler(_profile)
        _profile.installUrlSchemeHandler(SCHEME, _handler)
        _gate = NetworkGate(online_allowed, _profile)
        _profile.setUrlRequestInterceptor(_gate)
    _gate.online_allowed = online_allowed
    return _profile, _handler, _gate
