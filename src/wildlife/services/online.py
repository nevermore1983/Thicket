"""The only way WildLife's Python code talks to the internet.

Requests go out only over HTTPS, only to hosts on the allow-list, only while
"Allow online features" is on (the caller checks that), and with a size limit.
Redirects are followed only to other allowed hosts. Tests swap in a fake `Fetch`.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

from wildlife import __version__
from wildlife.domain.errors import OnlineServiceError

log = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset(
    {
        "api.inaturalist.org",  # which photos an observation has
        "inaturalist-open-data.s3.amazonaws.com",  # openly licensed photos
        "static.inaturalist.org",  # other photos
        "github.com",  # species packs: WildLife's own GitHub releases (services/species_packs.py)
        "release-assets.githubusercontent.com",  # ...where GitHub keeps release files
    }
)
USER_AGENT = f"WildLife/{__version__} (UK wildlife recording desktop app)"
MAX_BYTES = 40 * 1024 * 1024  # an original photo is a few MB

Fetch = Callable[[str], bytes]


def is_allowed(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "") in ALLOWED_HOSTS


class _AllowListRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "Redirect to a host not allowed", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_AllowListRedirects)


def fetch(url: str, timeout: float = 30.0, max_bytes: int = MAX_BYTES) -> bytes:
    """Download `url`. Raises OnlineServiceError (with a plain message) on any failure."""
    if not is_allowed(url):
        raise OnlineServiceError(
            "WildLife only connects to the services it knows.", detail=f"blocked: {url}"
        )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _opener.open(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise OnlineServiceError(
            f"The website said no ({exc.code}).", detail=f"{url}: {exc}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OnlineServiceError(
            "Couldn't connect. Check your internet connection and try again.",
            detail=f"{url}: {exc}",
        ) from exc
    if len(data) > max_bytes:
        raise OnlineServiceError("The download was larger than expected.", detail=url)
    return data
