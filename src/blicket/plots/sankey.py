"""The ``sankey`` plot type."""

from collections.abc import Mapping, Sequence

import polars as pl

from blicket.plots._base import BuiltinPlotType, Channel, PlotSpec, make_spec
from blicket.plots._diff import compare
from blicket.schema import Change


class Sankey(BuiltinPlotType):
    """Flows between nodes, one link per row, from the node of its ``source`` value to that of
    its ``target`` value, coloured by ``color``. A value of both dimensions is one node, so flows
    may loop."""

    name = "sankey"
    channels = (
        Channel("source", "dimension", required=True, doc="The node a flow leaves."),
        Channel("target", "dimension", required=True, doc="The node a flow enters."),
        Channel("value", "measure", required=True, doc="The width of a flow."),
        Channel("color", "dimension", doc="Flows told apart by colour, one per value."),
    )

    def diff(
        self,
        baseline: pl.DataFrame,
        current: pl.DataFrame,
        mapping: Mapping[str, str],
        panels: Sequence[str],
    ) -> Change:
        """Compare the measure on ``value`` per row, against the largest flow of its panel."""
        if "value" not in mapping:
            raise ValueError(f"the mapping binds no column to value, which {self.name} needs")
        return compare(baseline, current, mapping["value"], panels)


SANKEY = Sankey()


def sankey(source: str, target: str, value: str, color: str | None = None) -> PlotSpec:
    """A Sankey diagram of the flows ``value`` from ``source`` to ``target``, coloured by
    ``color``."""
    return make_spec(SANKEY, source=source, target=target, value=value, color=color)
