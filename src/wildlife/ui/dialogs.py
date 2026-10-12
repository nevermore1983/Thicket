"""Dialogs: first-run welcome (installs the species list) and the search popup."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.dates import DateQuery, parse_date_query
from wildlife.domain.filters import SightingFilter
from wildlife.ui.components.visuals import plural, swatch
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background


class FirstRunDialog(QDialog):
    """Welcome → your name → installing the species list → backups → done."""

    def __init__(self, ctx: AppContext, theme: ThemeManager, updating: bool = False) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.setWindowTitle("Welcome to WildLife" if not updating else "Updating the species list")
        self.setMinimumWidth(520)
        self.setModal(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(14)
        self.pages = QStackedWidget()
        v.addWidget(self.pages)
        foot = QHBoxLayout()
        self.step_label = QLabel()
        self.step_label.setProperty("role", "caption")
        foot.addWidget(self.step_label, 1)
        self.next_btn = QPushButton("Continue")
        self.next_btn.setProperty("variant", "primary")
        self.next_btn.clicked.connect(self._next)
        foot.addWidget(self.next_btn)
        v.addLayout(foot)
        self._installed = False

        if not updating:
            self.pages.addWidget(
                self._page(
                    "Welcome to WildLife",
                    "WildLife keeps your sightings on this PC. It works without internet, and you can export "
                    f"everything at any time.<br><br><span style='color:{theme.tokens.text_3}'>Your data folder: "
                    f"{ctx.paths.root}</span>",
                )
            )
            name_page = self._page(
                "What's your name?",
                "Optional. It's added to exports as the recorder, the way biological records "
                "are credited. You can change it later in Settings.",
            )
            self.name = QLineEdit(ctx.settings.current.recorder_name)
            self.name.setPlaceholderText("e.g. Sam Recorder")
            name_page.layout().addWidget(self.name)
            self.pages.addWidget(name_page)
        install = self._page(
            "Installing the UK species list",
            "About 106,000 names of UK animals, plants and fungi from the UK Species Inventory "
            "(Natural History Museum). "
            "This takes a few seconds and only happens once.",
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress_text = QLabel("Starting…")
        self.progress_text.setProperty("role", "muted")
        install.layout().addWidget(self.progress)
        install.layout().addWidget(self.progress_text)
        self.install_index = self.pages.addWidget(install)
        if not updating:
            self.pages.addWidget(
                self._page(
                    "Your data is backed up automatically",
                    "WildLife makes a verified backup every day and when you close it after changes. For the best "
                    "protection, choose a backup folder on another drive (or a cloud-synced folder) in "
                    "<b>Settings › Backup</b>.",
                )
            )
        self._update_step()

    def _page(self, title: str, text: str) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("EmptyStateTitle")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setProperty("role", "muted")
        v.addWidget(heading)
        v.addWidget(body)
        v.addStretch(1)
        return page

    def _update_step(self) -> None:
        i, n = self.pages.currentIndex(), self.pages.count()
        self.step_label.setText(f"Step {i + 1} of {n}" if n > 1 else "")
        self.next_btn.setText("Finish" if i == n - 1 else "Continue")
        if i == self.install_index and not self._installed:
            self.next_btn.setEnabled(False)
            self._install()

    def _next(self) -> None:
        if hasattr(self, "name") and self.pages.currentWidget() is self.name.parentWidget():
            self.ctx.settings.update(recorder_name=self.name.text().strip())
        if self.pages.currentIndex() == self.pages.count() - 1:
            self.accept()
            return
        self.pages.setCurrentIndex(self.pages.currentIndex() + 1)
        self._update_step()

    def _install(self) -> None:
        def progress(step: str, fraction: float) -> None:
            self.progress.setValue(int(fraction * 100))
            self.progress_text.setText(step + "…")

        def done(count: int) -> None:
            self._installed = True
            self.progress.setValue(100)
            self.progress_text.setText(f"Done: {count:,} names installed.")
            self.next_btn.setEnabled(True)
            if self.pages.currentIndex() == self.pages.count() - 1:
                self.next_btn.setText("Finish")

        def failed(exc: BaseException) -> None:
            self.progress_text.setText(
                "Couldn't install the species list. Details are in the log; please "
                "restart WildLife to try again."
            )
            self.progress_text.setProperty("role", "error")
            self.next_btn.setText("Close")
            self.next_btn.setEnabled(True)
            self._installed = True

        run_in_background(
            lambda report: self.ctx.catalogue.install(report),
            on_done=done,
            on_error=failed,
            on_progress=progress,
        )

    def reject(self) -> None:  # closing early is fine once the list is in
        if self._installed or self.install_index != self.pages.currentIndex():
            super().reject()


class SearchPopup(QFrame):
    """Suggestions under the global search box: a date, species, places, and 'all matching'."""

    chosen = Signal(object)  # SightingFilter
    date_chosen = Signal(object)  # DateQuery: open it in the calendar

    def __init__(self, ctx: AppContext, theme: ThemeManager, edit: QLineEdit) -> None:
        super().__init__(
            edit.window()
        )  # an overlay inside the window, so typing focus stays in the box
        self.hide()
        self.setObjectName("SearchPopup")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ctx, self.theme, self.edit = ctx, theme, edit
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        self.list = QListWidget()
        self.list.setObjectName("Suggestions")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(self._choose)
        v.addWidget(self.list)
        self._timer = QTimer(self, singleShot=True, interval=120)
        self._timer.timeout.connect(self._refresh)
        edit.textEdited.connect(lambda _: self._timer.start())
        edit.installEventFilter(self)

    def _add(self, text: str, flt: SightingFilter | DateQuery, icon=None, hint: str = "") -> None:
        item = QListWidgetItem(f"{text}{'   ' + hint if hint else ''}")
        if icon is not None:
            item.setIcon(icon)
        item.setData(Qt.ItemDataRole.UserRole, flt)
        self.list.addItem(item)

    def _refresh(self) -> None:
        text = self.edit.text().strip()
        self.list.clear()
        if not text:
            self.hide()
            return
        t = self.theme.tokens
        when = parse_date_query(text, self.ctx.sightings._today())
        if when is not None:
            self._add(
                f"Open {when.label} in the calendar", when, pixmap("calendar", t.text_2, 16), "date"
            )
        for m in [m for m in self.ctx.catalogue.search(text, 6) if m.uses][:4]:
            self._add(
                m.taxon.display_name,
                SightingFilter(taxon_ids=frozenset({m.taxon.id})),
                swatch(self.ctx.catalogue.category(m.taxon.category_id), t, 16),
                plural(m.uses, "sighting"),
            )
        for place in [p for p in self.ctx.places.all() if text.lower() in p.name.lower()][:3]:
            self._add(
                place.name,
                SightingFilter(place_ids=frozenset({place.id})),
                pixmap("pin", t.text_2, 16),
                "place",
            )
        self._add(
            f"All sightings matching “{text}”",
            SightingFilter(text=text),
            pixmap("search", t.text_2, 16),
            "Enter",
        )
        # Enter picks the date if the text is one, else "all matching"
        self.list.setCurrentRow(0 if when is not None else self.list.count() - 1)
        rows = self.list.count()
        self.list.setFixedHeight(sum(self.list.sizeHintForRow(i) for i in range(rows)) + 8)
        self.setFixedWidth(self.edit.width())
        self.move(self.edit.mapTo(self.parentWidget(), QPoint(0, self.edit.height() + 4)))
        self.adjustSize()
        self.show()
        self.raise_()

    def _choose(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.list.currentItem()
        if item is None:
            return
        self.hide()
        choice = item.data(Qt.ItemDataRole.UserRole)
        (self.date_chosen if isinstance(choice, DateQuery) else self.chosen).emit(choice)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._timer.isActive():
                    self._timer.stop()
                    self._refresh()
                if self.list.count():
                    self._choose()
                return True
            if self.isVisible() and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key == Qt.Key.Key_Escape and self.isVisible():
                self.hide()
                return True
        if event.type() == QEvent.Type.FocusOut:
            # `self` as the timer's context: Qt cancels it if the popup is destroyed first
            QTimer.singleShot(150, self, self._hide_unless_hovered)
        return super().eventFilter(obj, event)

    def _hide_unless_hovered(self) -> None:
        if not self.list.underMouse():
            self.hide()
