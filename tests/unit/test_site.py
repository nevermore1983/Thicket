"""The website (site/): links work, images have alt text, and nothing loads from elsewhere."""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import build_site_changelog

SITE = build_site_changelog.ROOT / "site"
PAGES = sorted(SITE.glob("*.html"))


class Page(HTMLParser):
    """The parts of a page the checks need."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.ids: set[str] = set()
        self.title = ""
        self._in_title = False
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        self.tags.append((tag, a))
        if "id" in a:
            self.ids.add(a["id"])
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def all(self, tag: str) -> list[dict[str, str]]:
        return [a for t, a in self.tags if t == tag]

    def header(self) -> str:
        """The shared header's markup, without the 'this page' marker."""
        text = self.path.read_text(encoding="utf-8")
        found = re.search(r'<header class="site-header">.*?</header>', text, re.S)
        assert found, f"{self.path.name} has no site header"
        return found.group(0).replace(' aria-current="page"', "")


def is_external(url: str) -> bool:
    return bool(urlsplit(url).scheme) or url.startswith("//")


def loaded_urls(page: Page) -> list[str]:
    """Everything the browser fetches by itself when the page opens (not links you click)."""
    urls = [a["href"] for a in page.all("link")]
    urls += [a["src"] for t in ("img", "script", "iframe") for a in page.all(t) if "src" in a]
    urls += [a["srcset"].split()[0] for a in page.all("source")]
    return urls


@pytest.fixture(scope="module")
def pages() -> dict[str, Page]:
    return {p.name: Page(p) for p in PAGES}


def test_the_site_has_its_pages():
    names = {p.name for p in PAGES}
    assert {"index.html", "features.html", "help.html", "changelog.html", "privacy.html"} <= names


def test_changelog_page_is_up_to_date():
    """After editing CHANGELOG.md, run scripts/build_site_changelog.py."""
    page = build_site_changelog.PAGE.read_text(encoding="utf-8")
    changelog = build_site_changelog.CHANGELOG.read_text(encoding="utf-8")
    assert build_site_changelog.updated(page, changelog) == page


def test_changelog_markdown():
    html = build_site_changelog.render(
        "Notes for developers.\n\n## 2.0.0\n\nIntro with **bold**, `a<b` and [a link](https://x.org).\n\n"
        "- one\n- two\n\nAfter.\n\n## 1.9.0\n\n- only\n"
    )
    assert "Notes for developers" not in html
    assert '<section id="v2-0-0">' in html and '<span class="version-tag">Latest</span>' in html
    assert "<strong>bold</strong>, <code>a&lt;b</code>" in html
    assert '<a href="https://x.org">a link</a>' in html
    assert re.search(r"<ul>\s*<li>one</li>\s*<li>two</li>\s*</ul>\s*<p>After.</p>", html)
    assert html.count("Latest") == 1


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_page_basics(path, pages):
    page = pages[path.name]
    assert page.all("html")[0].get("lang") == "en-GB"
    assert page.title.strip()
    metas = {a.get("name"): a.get("content", "") for a in page.all("meta")}
    assert "width=device-width" in metas.get("viewport", "")
    assert metas.get("description")
    assert len(page.all("h1")) == 1
    assert page.all("main") and "main" in page.ids  # the skip link's target


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_links_and_images_on_the_site_exist(path, pages):
    page = pages[path.name]
    urls = [a["href"] for a in page.all("a") + page.all("link") if "href" in a]
    urls += loaded_urls(page)
    for url in urls:
        if is_external(url):
            assert url.startswith("https://"), f"{path.name}: not https: {url}"
            continue
        target, _, fragment = url.partition("#")
        file = (SITE / target) if target else path
        assert file.is_file(), f"{path.name}: {url} doesn't exist"
        if fragment:
            assert fragment in pages[file.name].ids, f"{path.name}: no #{fragment} in {file.name}"


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_images_have_alt_text_and_a_size(path, pages):
    """alt="" is right for decoration (the logo next to the name); screenshots need words."""
    for img in pages[path.name].all("img"):
        assert "alt" in img, f"{path.name}: {img['src']} has no alt"
        assert img.get("width") and img.get("height"), f"{path.name}: {img['src']} has no size"
        if img["src"].endswith(".png"):
            assert len(img["alt"]) > 20, f"{path.name}: {img['src']} needs a real description"


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_nothing_loads_from_another_website(path, pages):
    """The privacy page promises no outside fonts, scripts or trackers."""
    assert [u for u in loaded_urls(pages[path.name]) if is_external(u)] == []


def test_the_stylesheet_loads_nothing_from_another_website():
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert "@import" not in css
    for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
        if not url.startswith("data:"):
            assert not is_external(url), url
            assert (SITE / url).is_file(), f"style.css: {url} doesn't exist"


def test_every_page_has_the_same_header_and_marks_itself(pages):
    headers = {name: page.header() for name, page in pages.items()}
    assert len(set(headers.values())) == 1, "the pages' headers differ"
    for name, page in pages.items():
        current = [a["href"] for a in page.all("a") if a.get("aria-current") == "page"]
        assert current == ([] if name == "index.html" else [name])


def test_every_image_file_is_used(pages):
    """No forgotten screenshots: each file in site/images appears on some page."""
    used = {Path(u).name for page in pages.values() for u in loaded_urls(page)}
    unused = [p.name for p in (SITE / "images").iterdir() if p.name not in used]
    assert unused == []


def test_screenshots_come_in_light_and_dark():
    names = {p.name for p in (SITE / "images").glob("*.png")}
    for name in names:
        other = (
            name.replace("-light", "-dark") if "-light" in name else name.replace("-dark", "-light")
        )
        assert other in names, f"{name} has no {other}"
