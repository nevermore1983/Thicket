"""Saved filters and species notes."""

from datetime import date

import pytest

from helpers import taxon_id
from wildlife.domain.codes import Evidence
from wildlife.domain.errors import ValidationError
from wildlife.domain.filters import SightingFilter, filter_from_dict, filter_to_dict

EVERYTHING = SightingFilter(
    text="moth",
    category_ids=frozenset({4}),
    taxon_ids=frozenset({1, 2}),
    date_from=date(2026, 5, 1),
    date_to=date(2026, 9, 30),
    place_ids=frozenset({3}),
    outing_id=7,
    evidence=frozenset({Evidence.TRAPPED}),
    has_photos=True,
    needs_location=True,
    months=frozenset({6, 7}),
    hours=frozenset({22, 23}),
    import_batch_id=5,
)


def test_every_filter_option_survives_saving():
    # a new filter option must be added here and to filter_to_dict: this test lists them all
    assert set(filter_to_dict(EVERYTHING)) == set(SightingFilter.__dataclass_fields__)
    assert filter_from_dict(filter_to_dict(EVERYTHING)) == EVERYTHING
    assert filter_to_dict(SightingFilter()) == {}
    assert filter_from_dict({"months": [5], "from_a_newer_wildlife": 1}) == SightingFilter(
        months=frozenset({5})
    )


def test_saved_filters(ctx):
    moth_nights = SightingFilter(evidence=frozenset({Evidence.TRAPPED}), hours=frozenset({22}))
    ctx.saved_filters.save("  Moth-trap   nights ", moth_nights)
    (saved,) = ctx.saved_filters.all()
    assert (saved.name, saved.filter) == ("Moth-trap nights", moth_nights)
    ctx.saved_filters.save("moth-trap nights", SightingFilter(months=frozenset({6})))
    assert [f.filter.months for f in ctx.saved_filters.all()] == [frozenset({6})]  # replaced
    with pytest.raises(ValidationError):
        ctx.saved_filters.save("Nothing", SightingFilter())
    ctx.saved_filters.delete(saved.id)
    assert ctx.saved_filters.all() == []


def test_species_notes(ctx):
    robin = taxon_id(ctx, "Erithacus rubecula")
    assert ctx.species_notes.get(robin) == ""
    ctx.species_notes.set(robin, "Nests in the ivy by the shed.")
    assert ctx.species_notes.get(robin) == "Nests in the ivy by the shed."
    ctx.species_notes.set(robin, "   ")
    assert ctx.species_notes.get(robin) == ""


def test_saved_filters_in_the_filter_bar(ctx, qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton

    from wildlife.config.settings import Theme
    from wildlife.ui.components.filter_bar import FilterBar
    from wildlife.ui.theme.manager import ThemeManager

    theme = ThemeManager(QApplication.instance(), Theme.LIGHT)
    bar = FilterBar(ctx, theme)
    qtbot.addWidget(bar)

    def chips() -> list[str]:
        QApplication.processEvents()  # new chips are shown on the next turn of the event loop
        return [b.text() for b in bar.findChildren(QPushButton) if b.isVisibleTo(bar)]

    bar.show()
    assert "Saved" not in chips()  # nothing saved and no filter: no clutter
    june = SightingFilter(months=frozenset({6}))
    bar.set_filter(june)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("June", True))
    bar._save_current()
    assert "June" in chips()  # the chip names the saved filter in use
    bar.set_filter(SightingFilter())
    assert "Saved" in chips()
