"""Phase 12 audit: open every page, panel and window, and check each control.

For every visible control it asks:
  * Name: can a screen reader say what it is? (button text, an accessible name, or a
    label that points at it). Icon-only buttons without a name are the classic miss.
  * Keyboard: can it be reached with Tab?  Then it walks the real Tab order of each
    screen to find controls Tab never reaches.
  * Words: does visible text use the agreed words (Sighting, Place, Species)?

    uv run python scripts/audit_ui.py --data-dir local_data/demo9 --out local_data/audit

Writes audit.md (findings by screen) and prints a summary. Nothing is saved to the library.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

from wildlife.ui.accessibility import check, describe
from wildlife.ui.accessibility import controls as a11y_controls

WORDS = re.compile(r"\b(records?|observations?|entr(y|ies)|locations?)\b", re.IGNORECASE)


def audit_screen(name: str, root: QWidget, app: QApplication) -> list[tuple[str, str, str]]:
    """[(severity, screen, message)]"""
    out = [(f.severity, "", f.message) for f in check(root)]
    controls = a11y_controls(root)
    # Walk the Tab order and see which controls are never reached
    tab_ready = [w for w in controls if w.focusPolicy() & Qt.FocusPolicy.TabFocus]
    if tab_ready:
        start = tab_ready[0]
        start.setFocus(Qt.FocusReason.TabFocusReason)
        app.processEvents()
        seen, current = set(), app.focusWidget()
        for _ in range(len(tab_ready) * 3 + 20):
            if current is None:
                break
            seen.add(id(current))
            root.focusNextChild() if not isinstance(root, QDialog) else root.focusNextPrevChild(
                True
            )
            app.processEvents()
            current = app.focusWidget()
        for w in tab_ready:
            if id(w) not in seen:
                out.append(("low", "", f"Tab never reaches {describe(w)}"))
    # Words
    for lbl in root.findChildren(QLabel):
        if lbl.isVisibleTo(root) and (m := WORDS.search(re.sub(r"<[^>]+>", "", lbl.text()))):
            out.append(
                ("review", "", f"Wording: “{m[0]}” in “{re.sub(r'<[^>]+>', '', lbl.text())[:90]}”")
            )
    return [(s, name, msg) for s, _, msg in out]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("local_data/audit"))
    args = parser.parse_args()

    from wildlife.config.paths import DataPaths
    from wildlife.context import AppContext
    from wildlife.logging_setup import setup_logging

    data_dir = args.data_dir or Path(tempfile.mkdtemp(prefix="wildlife-audit-"))
    paths = DataPaths(data_dir).ensure()
    setup_logging(paths.logs)
    QCoreApplication.setOrganizationName("Thicket-Audit")
    from wildlife.ui.web import scheme

    scheme.prepare()
    app = QApplication(sys.argv[:1])
    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.theme.manager import ThemeManager

    ctx = AppContext.open(paths)
    theme = ThemeManager(app)
    theme.apply()
    window = MainWindow(ctx, theme)
    window.resize(1280, 820)
    window.show()
    findings: dict[str, list] = defaultdict(list)

    def run() -> None:
        from datetime import date

        from wildlife.domain.filters import SightingFilter

        first = ctx.sightings.page(SightingFilter(), limit=1)
        panels = [("panel: add sighting", lambda: window.add_sighting())]
        if first:
            s = first[0]
            panels += [
                ("panel: sighting details", lambda: window.open_sighting(s.id)),
                ("panel: edit sighting", lambda: window.edit_sighting(s.id)),
                ("panel: species profile", lambda: window.open_species(s.taxon_id)),
                ("panel: day", lambda: window.open_day(s.observed_date, SightingFilter())),
            ]
        panels += [
            ("panel: new place", lambda: window.edit_place(None)),
            ("panel: new outing", lambda: window.new_outing(date.today())),
        ]
        for name, opener in panels:
            window.go("sightings")
            try:
                opener()
            except Exception as exc:  # report, keep auditing
                findings[name].append(("error", "", f"couldn't open: {exc}"))
                continue
            for _ in range(5):
                app.processEvents()
            view = window.panel.current()
            if view is not None:
                findings[name] += audit_screen(name, window.panel, app)
                view._dirty = False
            window.panel.close_panel()
        dialogs = [
            ("window: import iNaturalist", lambda: window.import_data("inaturalist")),
            ("window: import spreadsheet", lambda: window.import_data("csv")),
            ("window: export", lambda: window.export_data(None)),
            ("window: health check", lambda: window.health_check()),
            ("window: restore", lambda: window.restore_backup()),
        ]
        for name, opener in dialogs:
            dialog = opener()
            for _ in range(10):
                app.processEvents()
            findings[name] += audit_screen(name, dialog, app)
            dialog.reject()
        for key in (
            "dashboard",
            "sightings",
            "calendar",
            "map",
            "photos",
            "statistics",
            "species",
            "places",
            "settings",
        ):
            window.go(key)
            for _ in range(5):
                app.processEvents()
            page = window.pages.currentWidget()
            findings[f"page: {key}"] += audit_screen(key, page, app)
        if sidebar := window.findChild(QWidget, "Sidebar"):
            findings["sidebar"] += audit_screen("sidebar", sidebar, app)
        app.quit()

    QTimer.singleShot(800, run)
    app.exec()
    ctx.close()

    args.out.mkdir(parents=True, exist_ok=True)
    lines = ["# UI audit (automated part)", ""]
    totals: dict[str, int] = defaultdict(int)
    for screen, items in findings.items():
        if not items:
            continue
        lines += [f"## {screen}", ""]
        for severity, _, message in sorted(set(items)):
            totals[severity] += 1
            lines.append(f"- **{severity}**: {message}")
        lines.append("")
    (args.out / "audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(dict(totals))
    print(args.out / "audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
