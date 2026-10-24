"""Plot types: channel declarations, the plot spec a Blick carries, and the built-ins.

A plot type declares its channels as data, so they can be listed before any mapping exists.
"""

from blicket.errors import DefinitionError
from blicket.plots._base import Channel, ChannelKind, Control, ControlKind, PlotSpec, PlotType
from blicket.plots.bar import BAR, STACKED_BAR, bar, stacked_bar
from blicket.plots.line import LINE, line
from blicket.plots.stacked_area import STACKED_AREA, stacked_area

_BUILTINS: dict[str, PlotType] = {
    plot_type.name: plot_type for plot_type in (LINE, STACKED_AREA, BAR, STACKED_BAR)
}


def builtin(name: str) -> PlotType:
    """Return the built-in plot type called ``name``."""
    try:
        return _BUILTINS[name]
    except KeyError:
        raise DefinitionError(
            f"no built-in plot type {name!r}; the built-ins are {', '.join(_BUILTINS)}"
        ) from None


__all__ = [
    "Channel",
    "ChannelKind",
    "Control",
    "ControlKind",
    "PlotSpec",
    "PlotType",
    "bar",
    "builtin",
    "line",
    "stacked_area",
    "stacked_bar",
]
