"""The shared filter bar: Category · Date · Place, plus chips for species and search text."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.filters import SightingFilter
from wildlife.ui.components.common import clear_layout
from wildlife.ui.components.visuals import MONTHS_LONG, fmt_date, swatch
from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager


class FilterBar(QWidget):
    changed = Signal(object)  # SightingFilter

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        show_place: bool = True,
        show_date: bool = True,
    ) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.show_place, self.show_date = show_place, show_date
        self.filter = SightingFilter()
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._rebuild()
        theme.changed.connect(self._rebuild)

    def set_filter(self, flt: SightingFilter, emit: bool = True) -> None:
        self.filter = flt
        self._rebuild()
        if emit:
            self.changed.emit(flt)

    # ---- chips --------------------------------------------------------------
    def _chip(
        self, text: str, active: bool, icon_name: str, on_click=None, on_clear=None
    ) -> QPushButton:
        t = self.theme.tokens
        btn = QPushButton(text)
        btn.setProperty("filterChip", "active" if active else "idle")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(icon(icon_name, t.accent_subtle_text if active else t.text_2, 15))
        if on_clear and active:
            btn.setToolTip("Click to change · right-click to remove")
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _: on_clear())
        if on_click:
            btn.clicked.connect(lambda: on_click(btn))
        return btn

    def _rebuild(self) -> None:
        clear_layout(self._layout)
        f = self.filter
        cats = self.ctx.catalogue.categories()
        if not f.category_ids:
            cat_text = "Category"
        elif len(f.category_ids) == 1:
            cat_text = next(c.name for c in cats if c.id in f.category_ids)
        else:
            cat_text = f"{len(f.category_ids)} categories"
        self._layout.addWidget(
            self._chip(
                cat_text,
                bool(f.category_ids),
                "dots",
                self._category_menu,
                lambda: self.set_filter(f.with_(category_ids=frozenset())),
            )
        )
        if self.show_date:
            self._layout.addWidget(
                self._chip(
                    self._date_text(),
                    bool(f.date_from or f.date_to),
                    "calendar",
                    self._date_menu,
                    lambda: self.set_filter(f.with_(date_from=None, date_to=None)),
                )
            )
        if self.show_place:
            place_text = "Any place"
            if f.place_ids:
                names = [
                    p.name
                    for p in self.ctx.places.all(include_archived=True)
                    if p.id in f.place_ids
                ]
                place_text = names[0] if len(names) == 1 else f"{len(names)} places"
            self._layout.addWidget(
                self._chip(
                    place_text,
                    bool(f.place_ids),
                    "pin",
                    self._place_menu,
                    lambda: self.set_filter(f.with_(place_ids=frozenset())),
                )
            )
        if f.taxon_ids:
            names = [t.display_name for i in f.taxon_ids if (t := self.ctx.catalogue.get(i))]
            chip = self._chip(
                f"{', '.join(names)}  ✕",
                True,
                "leaf",
                lambda _: self.set_filter(f.with_(taxon_ids=frozenset())),
            )
            chip.setToolTip("Remove this filter")
            self._layout.addWidget(chip)
        if f.months:  # e.g. from a Statistics heat cell: "In May"
            names = ", ".join(MONTHS_LONG[m - 1] for m in sorted(f.months))
            chip = self._chip(
                f"In {names}  ✕",
                True,
                "calendar",
                lambda _: self.set_filter(f.with_(months=frozenset())),
            )
            chip.setToolTip("Sightings in this month of any year · click to remove")
            self._layout.addWidget(chip)
        if f.hours:  # e.g. from the time-of-day chart
            names = ", ".join(f"{h:02d}:00–{(h + 1) % 24:02d}:00" for h in sorted(f.hours))
            chip = self._chip(
                f"{names}  ✕", True, "clock", lambda _: self.set_filter(f.with_(hours=frozenset()))
            )
            chip.setToolTip("Sightings recorded in this hour · click to remove")
            self._layout.addWidget(chip)
        if f.needs_location:
            chip = self._chip(
                "No location  ✕",
                True,
                "pin",
                lambda _: self.set_filter(f.with_(needs_location=False)),
            )
            self._layout.addWidget(chip)
        if f.text:
            chip = self._chip(
                f"“{f.text}”  ✕", True, "search", lambda _: self.set_filter(f.with_(text=""))
            )
            chip.setToolTip("Remove this search")
            self._layout.addWidget(chip)
        if not f.is_empty:
            clear = QPushButton("Clear all")
            clear.setProperty("variant", "link")
            clear.clicked.connect(lambda: self.set_filter(SightingFilter()))
            self._layout.addWidget(clear)
        self._layout.addStretch(1)

    def _date_text(self) -> str:
        f = self.filter
        if not (f.date_from or f.date_to):
            return "Any date"
        if (
            f.date_from
            and f.date_to
            and (f.date_from.month, f.date_from.day, f.date_to.month, f.date_to.day)
            == (1, 1, 12, 31)
            and f.date_from.year == f.date_to.year
        ):
            return str(f.date_from.year)
        if f.date_from and not f.date_to:
            return f"Since {fmt_date(f.date_from, 'medium')}"
        if f.date_to and not f.date_from:
            return f"Until {fmt_date(f.date_to, 'medium')}"
        return f"{fmt_date(f.date_from, 'medium')} – {fmt_date(f.date_to, 'medium')}"

    # ---- menus ----------------------------------------------------------------
    def _category_menu(self, anchor: QPushButton) -> None:
        menu = QMenu(self)
        for cat in self.ctx.catalogue.categories():
            action = menu.addAction(swatch(cat, self.theme.tokens, 16), cat.name)
            action.setCheckable(True)
            action.setChecked(cat.id in self.filter.category_ids)
            action.toggled.connect(lambda on, cid=cat.id: self._toggle_category(cid, on))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _toggle_category(self, category_id: int, on: bool) -> None:
        ids = set(self.filter.category_ids)
        (ids.add if on else ids.discard)(category_id)
        self.set_filter(self.filter.with_(category_ids=frozenset(ids)))

    def _date_menu(self, anchor: QPushButton) -> None:
        today = self.ctx.sightings._today()
        menu = QMenu(self)
        presets = [
            ("This year", date(today.year, 1, 1), today),
            ("Last 12 months", today - timedelta(days=365), today),
            ("Last 30 days", today - timedelta(days=30), today),
            (str(today.year - 1), date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)),
            (str(today.year - 2), date(today.year - 2, 1, 1), date(today.year - 2, 12, 31)),
            ("Any date", None, None),
        ]
        for label, start, end in presets:
            menu.addAction(
                label,
                lambda s=start, e=end: self.set_filter(self.filter.with_(date_from=s, date_to=e)),
            )
        menu.addSeparator()
        menu.addAction("Choose dates…", self._custom_dates)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _custom_dates(self) -> None:
        today = self.ctx.sightings._today()
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose dates")
        form = QFormLayout(dialog)
        start, end = QDateEdit(), QDateEdit()
        for w, value in (
            (start, self.filter.date_from or date(today.year, 1, 1)),
            (end, self.filter.date_to or today),
        ):
            w.setCalendarPopup(True)
            w.setDisplayFormat("d MMM yyyy")
            w.setDate(QDate(value.year, value.month, value.day))
        form.addRow("From", start)
        form.addRow("To", end)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            a, b = start.date().toPython(), end.date().toPython()
            self.set_filter(self.filter.with_(date_from=min(a, b), date_to=max(a, b)))

    def _place_menu(self, anchor: QPushButton) -> None:
        menu = QMenu(self)
        places = self.ctx.places.all()
        if not places:
            menu.addAction("No saved places yet").setEnabled(False)
        for place in places:
            action = menu.addAction(place.name)
            action.setCheckable(True)
            action.setChecked(place.id in self.filter.place_ids)
            action.triggered.connect(
                lambda _=False, pid=place.id: self.set_filter(
                    self.filter.with_(place_ids=frozenset({pid}))
                )
            )
        if self.filter.place_ids:
            menu.addSeparator()
            menu.addAction(
                "Any place", lambda: self.set_filter(self.filter.with_(place_ids=frozenset()))
            )
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
