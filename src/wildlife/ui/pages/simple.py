"""Pages that are just an empty state for now: each is filled in by a later phase."""

from __future__ import annotations

from collections.abc import Callable

from wildlife.ui.components.common import EmptyState, Page, button
from wildlife.ui.theme.manager import ThemeManager


def coming_soon(
    theme: ThemeManager,
    title: str,
    icon_name: str,
    heading: str,
    text: str,
    on_add: Callable[[], None] | None = None,
) -> Page:
    page = Page(title)
    actions = [button("Add sighting", "primary", "plus", theme, on_add)] if on_add else []
    page.add(EmptyState(theme, icon_name, heading, text, actions))
    page.finish()
    return page


def dashboard(
    theme: ThemeManager,
    on_add: Callable[[], None],
    on_import_photos: Callable[[], None],
    on_import_records: Callable[[], None],
) -> Page:
    page = Page("Welcome to WildLife")
    page.add(
        EmptyState(
            theme,
            "leaf",
            "Start your wildlife journal",
            "Record what you see in a few seconds, then explore it on the calendar, map and charts. "
            "Everything stays on this PC.",
            [
                button("Add your first sighting", "primary", "plus", theme, on_add),
                button("Import photos", "secondary", "camera", theme, on_import_photos),
                button("Import existing records", "secondary", "upload", theme, on_import_records),
            ],
        )
    )
    page.finish()
    return page
