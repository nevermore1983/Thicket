"""Painted charts for the Statistics page and panels.

Rules (from the data-visualisation checklist in docs/04-ui-ux-design.md):
thin marks with 4 px rounded data-ends, hairline recessive gridlines, one y axis,
text in text colours (never the series colour), a hover tooltip on every mark where
the value leads, a legend whenever there are two series, keyboard access
(arrows + Enter), and a table version of every chart (`table()`).
"""

from wildlife.ui.components.charts.bars import Bar, BarChart
from wildlife.ui.components.charts.base import Chart, nice_ticks
from wildlife.ui.components.charts.columns import ColumnChart, Series
from wildlife.ui.components.charts.heat import HeatRow, HeatTable
from wildlife.ui.components.charts.lines import Line, StepLineChart

__all__ = [
    "Bar",
    "BarChart",
    "Chart",
    "ColumnChart",
    "HeatRow",
    "HeatTable",
    "Line",
    "Series",
    "StepLineChart",
    "nice_ticks",
]
