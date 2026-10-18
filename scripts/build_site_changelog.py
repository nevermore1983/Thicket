"""Write the website's changelog page (site/changelog.html) from CHANGELOG.md.

    uv run python scripts/build_site_changelog.py

Only the part between the changelog markers is replaced; the rest of the page is
hand-written like every other page. tests/unit/test_site.py fails if the page is out of
date, so after editing CHANGELOG.md, run this.

Understands the little Markdown the changelog uses: '## <version>' headings, paragraphs,
'- ' bullets, **bold**, `code` and [links](url).
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PAGE = ROOT / "site" / "changelog.html"
START, END = "<!-- changelog:start -->", "<!-- changelog:end -->"
INDENT = " " * 8  # the page's indent inside <div class="prose">


def inline(text: str) -> str:
    """Escape the text, then turn `code`, **bold** and [links](url) into HTML."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>',
        out,
    )


def blocks(body: str) -> list[str]:
    """One version's text as HTML paragraphs and lists."""
    out: list[str] = []
    items: list[str] = []
    for chunk in re.split(r"\n\s*\n", body.strip()):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if all(line.startswith("- ") for line in lines):
            items += [f"  <li>{inline(line[2:])}</li>" for line in lines]
            continue
        if items:
            out += ["<ul>", *items, "</ul>"]
            items = []
        out.append(f"<p>{inline(' '.join(lines))}</p>")
    if items:
        out += ["<ul>", *items, "</ul>"]
    return out


def render(changelog: str) -> str:
    """Every version, newest first as in the file, as <section>s. Text before the first
    version (a note for developers) is left out."""
    sections = re.findall(r"^## (.+?)\s*$(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    if not sections:
        raise SystemExit("CHANGELOG.md has no '## <version>' headings")
    lines: list[str] = []
    for i, (version, body) in enumerate(sections):
        anchor = "v" + re.sub(r"[^0-9A-Za-z]+", "-", version).strip("-")
        tag = ' <span class="version-tag">Latest</span>' if i == 0 else ""
        lines += [f'<section id="{anchor}">', f"  <h2>{html.escape(version)}{tag}</h2>"]
        lines += [f"  {line}" for line in blocks(body)]
        lines.append("</section>")
    return "\n".join(INDENT + line for line in lines)


def updated(page: str, changelog: str) -> str:
    """The page with the text between the markers replaced by the rendered changelog."""
    start, end = page.index(START) + len(START), page.index(END)
    return f"{page[:start]}\n{render(changelog)}\n{INDENT}{page[end:]}"


def main() -> None:
    page = PAGE.read_text(encoding="utf-8")
    new = updated(page, CHANGELOG.read_text(encoding="utf-8"))
    if new == page:
        print(f"{PAGE.relative_to(ROOT)} is already up to date")
    else:
        PAGE.write_text(new, encoding="utf-8", newline="\n")
        print(f"Updated {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
