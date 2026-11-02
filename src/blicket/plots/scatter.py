"""The ``scatter`` plot type."""

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, make_spec
from blicket.plots._scales import Scale


class Scatter(BuiltinPlotType):
    """Points of one measure against another, one series per combination of the colour and line
    type values; with ``along``, the points of a series are connected in the display order of
    that dimension's values."""

    name = "scatter"
    channels = (
        Channel("x", "measure", required=True, doc="Horizontal axis."),
        Channel("y", "measure", required=True, doc="Vertical axis."),
        Channel("color", "dimension", doc="One series per value, told apart by colour."),
        Channel(
            "linetype",
            "dimension",
            doc="One series per value, told apart by dash pattern, or without along by shape.",
        ),
        Channel("along", "dimension", doc="Connects the points of a series in its value order."),
    )


SCATTER = Scatter()


def scatter(
    x: str,
    y: str,
    color: str | None = None,
    linetype: str | None = None,
    along: str | None = None,
    x_scale: Scale | None = None,
    y_scale: Scale | None = None,
) -> PlotSpec:
    """A scatter plot of the measure ``y`` against the measure ``x``, both float columns.

    Without ``along``, each row is a point, coloured by ``color`` and shaped by ``linetype``. With
    ``along`` naming a dimension, the points of each series of ``color`` and ``linetype`` are
    connected in the display order of its values instead, a line dashed by ``linetype``. Rows with
    a null ``x`` or ``y`` are left out of the chart. ``x_scale`` and ``y_scale`` give an axis its
    scale, ``linear`` (the default) or ``log``. A comparison of two builds compares ``y`` row by
    row; a change of ``x`` alone is not flagged.
    """
    scales = {"x": x_scale, "y": y_scale}
    return make_spec(SCATTER, scales=scales, x=x, y=y, color=color, linetype=linetype, along=along)
