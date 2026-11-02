"""The plot type contract: channels, controls, the plot spec a Blick carries, the built-ins."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, Literal, get_args

import polars as pl

from blicket.errors import DefinitionError, did_you_mean
from blicket.plots._diff import compare
from blicket.schema import Change, Control, TableSchema

ChannelKind = Literal["dimension", "measure"]
# How an axis maps values to positions; ``linear`` is every axis's default.
Scale = Literal["linear", "log"]


def _close(word: object, options: Sequence[str]) -> str:
    """A " did you mean …?" for a misspelled ``word``, or nothing."""
    close = did_you_mean(word.lower(), options) if isinstance(word, str) else None
    return f" did you mean {close!r}?" if close else ""


@dataclass(frozen=True)
class Channel:
    """A visual channel of a plot type, such as ``x`` or ``color``.

    ``scales`` are the axis scales a Blick can give the channel besides ``linear``, which every
    axis has and a channel with scales takes too: ``("log",)`` for a continuous axis, empty for a
    channel that is no continuous axis, such as a colour, a line type or a bar's band. They are
    stored without ``linear`` and without repeats, as a tuple even when given as a list. A plot
    type's factory takes the scale of a channel ``x`` as the argument ``x_scale``, as
    ``bk.plots.line`` does, and messages name it so.
    """

    name: str
    kind: ChannelKind
    required: bool = False
    doc: str = ""
    scales: tuple[Scale, ...] = ()

    def __post_init__(self) -> None:
        scales: object = self.scales
        if isinstance(scales, str) or not isinstance(scales, tuple | list):
            example = f"({scales!r},)" if isinstance(scales, str) else "('log',)"
            raise DefinitionError(
                f"channel {self.name!r}: scales= takes a tuple of scale names, such as "
                f"scales={example}, not {scales!r}"
            )
        known = get_args(Scale)
        others = tuple(s for s in known if s != "linear")
        for scale in scales:
            if scale not in known:
                raise DefinitionError(
                    f"channel {self.name!r}: scales= names {scale!r}, which is no scale;"
                    f"{_close(scale, others)} write scales={others!r}; 'linear' is implied"
                )
        declared = tuple(s for s in dict.fromkeys(scales) if s != "linear")
        object.__setattr__(self, "scales", declared)


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
    return (
        f"plot type {plot_type} has no channel {channel!r};{_close(channel, known)} channels of "
        f"{plot_type}: {', '.join(known)}"
    )


def _checked_scales(
    plot_type: PlotType, mapping: Mapping[str, str], scales: Mapping[str, Scale]
) -> dict[str, Scale]:
    """``scales`` without ``linear``, once each names a scale the channel takes, and a channel the
    mapping binds unless the scale is ``linear``."""
    name = plot_type.name
    by_name = {channel.name: channel for channel in plot_type.channels}
    for channel, scale in scales.items():
        if channel not in by_name:
            raise DefinitionError(_unknown_channel(name, channel, list(by_name)))
        given = f"{channel}_scale={scale!r}"
        declared = by_name[channel].scales
        if not declared:
            raise DefinitionError(
                f"{given}: channel {channel!r} of plot type {name} takes no scale; drop the scale"
            )
        takes = ("linear", *declared)
        if scale not in takes:
            raise DefinitionError(
                f"{given} is no scale of {channel} in plot type {name};{_close(scale, takes)} it "
                f"takes {' or '.join(map(repr, takes))}"
            )
        if channel not in mapping and scale != "linear":
            raise DefinitionError(
                f"{given} needs a column on {channel}; map {channel} to a column or drop the scale"
            )
    return {channel: scale for channel, scale in scales.items() if scale != "linear"}


@dataclass(frozen=True)
class PlotSpec:
    """A plot type with a mapping from its channels to table columns, and the axis scales of the
    channels.

    The mapping and the scales are checked against the channels on construction; the columns
    themselves are not checked here. A scale names a scale the channel takes: ``linear``, or one
    of its ``scales``, which only a channel the mapping binds can have. ``linear``, every axis's
    default, is left out of ``scales``, so a spec that names it equals one that does not. Messages
    name the scale of a channel ``x`` by the factory argument ``x_scale``.
    """

    plot_type: PlotType
    mapping: Mapping[str, str] = field(default_factory=dict)
    scales: Mapping[str, Scale] = field(default_factory=dict)

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
        scales = _checked_scales(self.plot_type, mapping, self.scales)
        object.__setattr__(self, "mapping", MappingProxyType(mapping))
        object.__setattr__(self, "scales", MappingProxyType(scales))


def make_spec(
    plot_type: PlotType, *, scales: Mapping[str, Scale | None] | None = None, **mapping: str | None
) -> PlotSpec:
    """Build a spec from factory arguments, leaving out the channels and scales passed as
    ``None``."""
    return PlotSpec(
        plot_type,
        {k: v for k, v in mapping.items() if v is not None},
        {k: v for k, v in (scales or {}).items() if v is not None},
    )
