"""The ``bar`` (grouped) and ``stacked_bar`` plot types.

Two plot types rather than an option, because ``controls`` and ``diff`` receive the mapping and
no options.
"""

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, make_spec

_CHANNELS = (
    Channel("x", "dimension", required=True, doc="One bar position per value."),
    Channel("y", "measure", required=True, doc="Bar height."),
    Channel("color", "dimension", doc="One bar per value at each position."),
)


class Bar(BuiltinPlotType):
    """Bars side by side at each ``x`` value, one per colour value."""

    name = "bar"
    channels = _CHANNELS


class StackedBar(BuiltinPlotType):
    """Bars stacked at each ``x`` value, one segment per colour value."""

    name = "stacked_bar"
    channels = _CHANNELS


BAR = Bar()
STACKED_BAR = StackedBar()


def bar(x: str, y: str, color: str | None = None) -> PlotSpec:
    """Grouped bars of ``y`` at each ``x``, one bar per value of ``color``."""
    return make_spec(BAR, x=x, y=y, color=color)


def stacked_bar(x: str, y: str, color: str | None = None) -> PlotSpec:
    """Stacked bars of ``y`` at each ``x``, one segment per value of ``color``."""
    return make_spec(STACKED_BAR, x=x, y=y, color=color)
