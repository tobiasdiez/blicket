"""The plot type contract: channels, controls, the plot spec a Blick carries, the built-ins."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, Literal

import polars as pl

from blicket.errors import DefinitionError, did_you_mean
from blicket.plots._diff import compare
from blicket.schema import Change, Control, TableSchema

ChannelKind = Literal["dimension", "measure"]


@dataclass(frozen=True)
class Channel:
    """A visual channel of a plot type, such as ``x`` or ``color``."""

    name: str
    kind: ChannelKind
    required: bool = False
    doc: str = ""


class PlotType(ABC):
    """Base class of every plot type, built in or project defined.

    Subclasses set ``name`` and ``channels``, and may set ``module``, the name of a file that goes
    with the plot type.
    """

    name: ClassVar[str]
    module: ClassVar[str | None] = None
    channels: ClassVar[tuple[Channel, ...]]

    @abstractmethod
    def controls(self, schema: TableSchema, mapping: Mapping[str, str]) -> list[Control]:
        """Derive the controls of a chart from the table schema and the mapping."""

    @abstractmethod
    def diff(
        self,
        baseline: pl.DataFrame,
        current: pl.DataFrame,
        mapping: Mapping[str, str],
        panels: Sequence[str],
    ) -> Change:
        """Compare a Blick's table in two builds.

        Both tables are as a build stores them: the dimension columns first, then the measures,
        one per measure channel of the mapping, as floats with null for a missing value and no
        NaN or infinite value; every combination of dimension values once, none of them null;
        the rows sorted by the dimensions. ``mapping`` holds the channels the Blick's plot binds,
        and only those, and names columns of the current table; the baseline may lack them or
        have others, which is a ``schema`` change. ``panels`` are the dimensions whose value
        combinations each get their own scale; empty means all rows share one.

        The ``Change`` holds:

        - ``flags``: ``schema`` when columns or dimension values appeared or vanished. The caller
          sets ``value`` from the magnitude and the Blick's tolerance, and the other flags.
        - ``columns_added`` and ``columns_removed``: the columns only one table has, or whose
          dtypes differ, with their types in the words of the manifest: ``dimension_type`` of a
          dimension, ``"float"`` for a measure.
        - ``values_added`` and ``values_removed``: per dimension, the values only one table has.
        - ``magnitude``: the largest change of a row both tables have, relative to the scale of
          its panel, at most 1; ``None`` when the columns differ or no row was compared.
        - ``where``: the dimension values of the row that changed most, the first in the tables'
          order on a tie; ``None`` when nothing changed. Below the tolerance it names noise, so
          it is read with the magnitude.
        """


class BuiltinPlotType(PlotType):
    """The built-ins declare their channels and share ``controls`` and ``diff``.

    ``stacked`` says that the layers of the ``color`` channel are stacked, so ``diff`` measures
    against the height of the stacks and compares their sums as well.
    """

    stacked: ClassVar[bool] = False

    def controls(self, schema: TableSchema, mapping: Mapping[str, str]) -> list[Control]:
        """A filter at the first value in display order for every dimension the mapping leaves
        unbound."""
        bound = set(mapping.values())
        return [
            Control(dimension=d.name, kind="filter", default=d.values[0] if d.values else None)
            for d in schema.dimensions
            if d.name not in bound
        ]

    def diff(
        self,
        baseline: pl.DataFrame,
        current: pl.DataFrame,
        mapping: Mapping[str, str],
        panels: Sequence[str],
    ) -> Change:
        """Compare the measure on ``y``, as stacks of the ``color`` layers for a stacked type; the
        other channels play no part."""
        if "y" not in mapping:
            raise ValueError(f"the mapping binds no column to y, which {self.name} needs")
        stacked_by = mapping.get("color") if self.stacked else None
        return compare(baseline, current, mapping["y"], panels, stacked_by)


def _unknown_channel(plot_type: str, channel: str, known: Sequence[str]) -> str:
    close = did_you_mean(channel, known)
    hint = f" did you mean {close!r}?" if close else ""
    return (
        f"plot type {plot_type} has no channel {channel!r};{hint} channels of {plot_type}: "
        f"{', '.join(known)}"
    )


@dataclass(frozen=True)
class PlotSpec:
    """A plot type with a mapping from its channels to table columns.

    The mapping is checked against the channels on construction; the columns themselves are not
    checked here.
    """

    plot_type: PlotType
    mapping: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plot_type, PlotType):
            raise DefinitionError(f"plot_type must be a PlotType instance, got {self.plot_type!r}")
        mapping = dict(self.mapping)
        name = self.plot_type.name
        known = [channel.name for channel in self.plot_type.channels]
        for channel, column in mapping.items():
            if channel not in known:
                raise DefinitionError(_unknown_channel(name, channel, known))
            if not isinstance(column, str) or not column:
                raise DefinitionError(
                    f"channel {channel!r} of plot type {name} must name a column, got {column!r}"
                )
        missing = [c.name for c in self.plot_type.channels if c.required and c.name not in mapping]
        if missing:
            raise DefinitionError(
                f"plot type {name} needs the channel(s) {', '.join(missing)}; map them to columns"
            )
        seen: dict[str, str] = {}
        for channel, column in mapping.items():
            if column in seen:
                raise DefinitionError(
                    f"column {column!r} is bound to both {seen[column]!r} and {channel!r} in plot "
                    f"type {name}; bind each column to one channel"
                )
            seen[column] = channel
        object.__setattr__(self, "mapping", MappingProxyType(mapping))


def make_spec(plot_type: PlotType, **mapping: str | None) -> PlotSpec:
    """Build a spec from factory arguments, leaving out the channels passed as ``None``."""
    return PlotSpec(plot_type, {k: v for k, v in mapping.items() if v is not None})
