"""The ``line`` plot type."""

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, Scale, make_spec


class Line(BuiltinPlotType):
    """Lines over a dimension, one per combination of the colour and line type values."""

    name = "line"
    channels = (
        Channel(
            "x", "dimension", required=True, doc="Horizontal axis, usually time.", scales=("log",)
        ),
        Channel("y", "measure", required=True, doc="Vertical axis.", scales=("log",)),
        Channel("color", "dimension", doc="One line per value, told apart by colour."),
        Channel("linetype", "dimension", doc="One line per value, told apart by dash pattern."),
    )


LINE = Line()


def line(
    x: str,
    y: str,
    color: str | None = None,
    linetype: str | None = None,
    x_scale: Scale | None = None,
    y_scale: Scale | None = None,
) -> PlotSpec:
    """A line chart of ``y`` over ``x``, split into lines by ``color`` and ``linetype``.

    ``x_scale`` and ``y_scale`` give an axis its scale, ``linear`` (the default) or ``log``; a log
    scale on ``x`` needs an integer dimension.
    """
    scales = {"x": x_scale, "y": y_scale}
    return make_spec(LINE, scales=scales, x=x, y=y, color=color, linetype=linetype)
