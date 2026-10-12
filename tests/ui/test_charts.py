"""The painted chart components: ticks, hit-testing, tooltips, table versions and clicks."""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from wildlife.config.settings import Theme
from wildlife.ui.components.charts import (
    Bar,
    BarChart,
    ColumnChart,
    HeatRow,
    HeatTable,
    Line,
    Series,
    StepLineChart,
    nice_ticks,
)
from wildlife.ui.theme.manager import ThemeManager


@pytest.mark.parametrize(
    ("top", "ticks"),
    [
        (0, [0, 1]),
        (7, [0, 2, 4, 6, 8]),
        (19, [0, 5, 10, 15, 20]),
        (258, [0, 100, 200, 300]),
        (3300, [0, 1000, 2000, 3000, 4000]),
    ],
)
def test_nice_ticks(top, ticks):
    assert nice_ticks(top) == ticks


@pytest.fixture
def theme(qapp):
    t = ThemeManager(QApplication.instance(), Theme.LIGHT)
    t.apply()
    return t


def shown(qtbot, widget, width=600):
    widget.resize(width, widget.height())
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_bar_chart(qtbot, theme):
    chart = BarChart(theme, "Top species")
    chart.set_bars(
        [Bar("Robin", 12, 1), Bar("Wren", 4, 2), Bar("Gull", 1)], extra=("Species", [3, 2, 1])
    )
    shown(qtbot, chart)
    assert chart.height() == 3 * BarChart.ROW
    assert chart.mark_at(QPointF(10, BarChart.ROW * 1.5)) == 1
    assert chart.tooltip(0).startswith("<b>12</b> sightings")
    assert chart.table() == (
        ["", "Sightings", "Species"],
        [["Robin", "12", "3"], ["Wren", "4", "2"], ["Gull", "1", "1"]],
    )
    opened = []
    chart.clicked.connect(opened.append)
    qtbot.mouseClick(
        chart, Qt.MouseButton.LeftButton, pos=QPointF(10, BarChart.ROW * 0.5).toPoint()
    )
    qtbot.mouseClick(
        chart, Qt.MouseButton.LeftButton, pos=QPointF(10, BarChart.ROW * 2.5).toPoint()
    )
    assert opened == [1]  # 'Gull' has no key, so it isn't clickable
    longest = chart._bar_rect(0).width()
    assert chart._bar_rect(1).width() == pytest.approx(longest * 4 / 12)


def test_bar_chart_keyboard(qtbot, theme):
    chart = shown(qtbot, BarChart(theme, "Bars"))
    chart.set_bars([Bar("A", 2, "a"), Bar("B", 1, "b")])
    opened = []
    chart.clicked.connect(opened.append)
    chart.setFocus()
    qtbot.keyClick(chart, Qt.Key.Key_Down)
    qtbot.keyClick(chart, Qt.Key.Key_Down)
    qtbot.keyClick(chart, Qt.Key.Key_Return)
    assert opened == ["b"]


def test_column_chart_two_series(qtbot, theme):
    chart = ColumnChart(
        theme, "Months", list("JFM"), "species", 1, ["January", "February", "March"]
    )
    chart.set_series(
        [Series("2026", [5, 9, 0]), Series("2025", [7, 3, 4], emphasis=False)], keys=["j", "f", "m"]
    )
    shown(qtbot, chart)
    assert chart.height() == ColumnChart.PLOT_H + ColumnChart.AXIS_H + 8 + ColumnChart.LEGEND_H
    slot = chart._slot(1)
    assert chart.mark_at(slot.center()) == 1
    assert (
        chart.tooltip(1) == "<b>9</b> 2026<br><b>3</b> 2025<br>February<br><i>Click to see them</i>"
    )
    assert chart.table() == (
        ["", "2026", "2025"],
        [["January", "5", "7"], ["February", "9", "3"], ["March", "0", "4"]],
    )
    a, b = chart._column(0, 0), chart._column(0, 1)
    assert b.left() - a.right() == pytest.approx(2)  # a 2 px gap between grouped columns
    assert a.width() <= 16


def test_step_line_values_and_table(qtbot, theme):
    chart = shown(qtbot, StepLineChart(theme, "Growth"), 700)
    chart.set_lines(
        [Line("2026", [(10, 2), (40, 5)], end=50), Line("2025", [(5, 1), (60, 6)], emphasis=False)],
        365,
        [(0, "Jan")],
        lambda x: f"day {x}",
    )
    this = chart.lines[0]
    assert [this.value_at(x) for x in (0, 10, 39, 40, 300)] == [0, 2, 2, 5, 5]
    assert chart.tooltip(45) == "<b>5</b> species · 2026<br><b>1</b> species · 2025<br>day 45"
    assert "2026" not in chart.tooltip(55)  # this year's line stops at 'today'
    headers, rows = chart.table()
    assert headers == ["Date", "2026", "2025"] and rows[0] == ["day 5", "0", "1"]
    plot = chart._plot()
    assert chart.mark_at(QPointF(plot.left(), plot.center().y())) == 0
    assert chart.mark_at(QPointF(plot.right(), plot.center().y())) == 365


def test_heat_table(qtbot, theme):
    table = HeatTable(theme, "Seasons", ["J", "F"], ["January", "February"])
    table.set_rows([HeatRow("Bird", [10, 0], key=1), HeatRow("Moth", [1, 5], key=4)])
    shown(qtbot, table)
    assert table._level(0) == 0 and table._level(10) == 6 and 1 <= table._level(1) < 6
    cell = table._cell(3).center()  # Moth, February
    assert table.mark_at(cell) == 3 and table.key(3) == (4, 2)
    assert table.key(1) is None  # an empty cell opens nothing
    assert table.tooltip(3).startswith("<b>5</b> sightings<br>Moth, February")
    assert table.table() == (["", "January", "February"], [["Bird", "10", "0"], ["Moth", "1", "5"]])
