"""The ``line`` plot type."""

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, make_spec


class Line(BuiltinPlotType):
    """Lines over a dimension, one per combination of the colour and line type values."""

    name = "line"
    channels = (
        Channel("x", "dimension", required=True, doc="Horizontal axis, usually time."),
        Channel("y", "measure", required=True, doc="Vertical axis."),
        Channel("color", "dimension", doc="One line per value, told apart by colour."),
        Channel("linetype", "dimension", doc="One line per value, told apart by dash pattern."),
    )


LINE = Line()


def line(x: str, y: str, color: str | None = None, linetype: str | None = None) -> PlotSpec:
    """A line chart of ``y`` over ``x``, split into lines by ``color`` and ``linetype``."""
    return make_spec(LINE, x=x, y=y, color=color, linetype=linetype)
