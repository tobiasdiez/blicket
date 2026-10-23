"""The plot type contract: channels, the plot spec a Blick carries, the built-ins' base."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from blicket.errors import DefinitionError, did_you_mean

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
    def controls(self, schema: Any, mapping: Mapping[str, str]) -> Sequence[Any]:
        """Derive the controls of a chart from the table schema and the mapping."""

    @abstractmethod
    def diff(
        self, baseline: Any, current: Any, mapping: Mapping[str, str], controls: Sequence[Any]
    ) -> Any:
        """Compare two tables and return the flags, magnitude and diagnostics."""


class BuiltinPlotType(PlotType):
    """The built-ins declare their channels; they do not implement ``controls`` or ``diff``."""

    def controls(self, schema: Any, mapping: Mapping[str, str]) -> Sequence[Any]:
        raise NotImplementedError("the built-in plot types do not implement controls")

    def diff(
        self, baseline: Any, current: Any, mapping: Mapping[str, str], controls: Sequence[Any]
    ) -> Any:
        raise NotImplementedError("the built-in plot types do not implement diff")


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

    def to_json(self) -> dict[str, Any]:
        """The JSON form, as ``blicket list --json`` prints it."""
        return {"type": self.plot_type.name, "mapping": dict(self.mapping)}


def make_spec(plot_type: PlotType, **mapping: str | None) -> PlotSpec:
    """Build a spec from factory arguments, leaving out the channels passed as ``None``."""
    return PlotSpec(plot_type, {k: v for k, v in mapping.items() if v is not None})
