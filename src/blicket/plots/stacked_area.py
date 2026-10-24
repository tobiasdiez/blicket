"""The ``stacked_area`` plot type."""

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, make_spec


class StackedArea(BuiltinPlotType):
    """Areas stacked over a dimension, one layer per colour value."""

    name = "stacked_area"
    stacked = True
    channels = (
        Channel("x", "dimension", required=True, doc="Horizontal axis, usually time."),
        Channel("y", "measure", required=True, doc="Height of each layer."),
        Channel("color", "dimension", doc="One stacked layer per value."),
    )


STACKED_AREA = StackedArea()


def stacked_area(x: str, y: str, color: str | None = None) -> PlotSpec:
    """A stacked area chart of ``y`` over ``x`` with one layer per value of ``color``."""
    return make_spec(STACKED_AREA, x=x, y=y, color=color)
