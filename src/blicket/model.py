"""The data model of a project's Blicks: Blicks, groups, the registry, and the shapes reports
record them in: definitions, entries and table schemas."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from blicket.errors import Problem, Source
from blicket.plots import PlotSpec

ControlKind = Literal["filter", "split"]
type Transform = Callable[[Any], Any]


class Group(BaseModel):
    """A group of Blicks, named by ``bk.group()`` or after its module."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str | None = None
    tags: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()


class PlotDefinition(BaseModel):
    """A Blick's plot as recorded: the plot type's name and the mapping of channels to columns."""

    model_config = ConfigDict(frozen=True)

    type: str
    mapping: dict[str, str]


class BlickDefinition(BaseModel):
    """How a Blick is defined, apart from its id, aliases and transformation: the options of
    ``@bk.blick``, with the plot as a ``PlotDefinition``. ``tags`` are the Blick's own."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str | None
    tags: tuple[str, ...]
    plot: PlotDefinition
    controls: dict[str, ControlKind]
    defaults: dict[str, Any]
    tolerance: float | None
    dims: tuple[str, ...] | None
    measures: tuple[str, ...] | None
    order: dict[str, tuple[Any, ...]]


type DimensionType = Literal["string", "integer", "boolean", "date", "datetime"]


class Dimension(BaseModel):
    """A dimension column of a Blick's table: its name, type and values in display order."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: DimensionType
    values: list[Any]


class Measure(BaseModel):
    """A measure column of a Blick's table: its name and type."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: Literal["float"]


class TableSchema(BaseModel):
    """The columns of a Blick's table, dimensions first."""

    model_config = ConfigDict(frozen=True)

    dimensions: list[Dimension]
    measures: list[Measure]


class BlickEntry(BaseModel):
    """A defined Blick as a report records it: what defines it, its table, and its problems.

    ``id`` is ``None`` when no usable id was given or derived; ``name`` is the id if there is
    one, else the function's name, else the id as given. ``definition`` is ``None`` when the
    Blick's arguments were invalid. ``data``, ``hash``, ``rows`` and ``columns`` describe the
    table a build wrote; ``status`` is ``error`` when a problem is an error.
    """

    model_config = ConfigDict(frozen=True)

    id: str | None
    name: str
    aliases: tuple[str, ...] = ()
    group: str
    module: str | None = None
    source: Source | None = None
    definition: BlickDefinition | None = None
    data: str | None = None
    hash: str | None = None
    rows: int | None = None
    columns: TableSchema | None = None
    timing_ms: float | None = None
    problems: tuple[Problem, ...] = ()

    @computed_field
    @property
    def status(self) -> Literal["ok", "error"]:
        return "error" if any(p.severity == "error" for p in self.problems) else "ok"


@dataclass(frozen=True, kw_only=True)
class Blick:
    """A named view on a model run: a transformation of the run and how to plot its table.

    ``tags`` are the Blick's own tags; its group has tags of its own. ``module`` is ``None`` for
    Blicks that do not come from a module.
    """

    id: str
    title: str
    description: str | None = None
    group: str
    tags: tuple[str, ...] = ()
    plot: PlotSpec
    controls: Mapping[str, ControlKind] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)
    tolerance: float | None = None
    aliases: tuple[str, ...] = ()
    dims: tuple[str, ...] | None = None
    measures: tuple[str, ...] | None = None
    order: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    transform: Transform
    module: str | None = None
    source: Source | None = None

    def definition(self) -> BlickDefinition:
        """Everything that defines the Blick except its transformation."""
        return BlickDefinition(
            title=self.title,
            description=self.description,
            tags=self.tags,
            plot=PlotDefinition(type=self.plot.plot_type.name, mapping=dict(self.plot.mapping)),
            controls=dict(self.controls),
            defaults=dict(self.defaults),
            tolerance=self.tolerance,
            dims=self.dims,
            measures=self.measures,
            order=dict(self.order),
        )

    def entry(
        self,
        *,
        problems: tuple[Problem, ...] = (),
        data: str | None = None,
        hash: str | None = None,
        rows: int | None = None,
        columns: TableSchema | None = None,
        timing_ms: float | None = None,
    ) -> BlickEntry:
        """The Blick as a report records it, with what a build made of it, if anything."""
        return BlickEntry(
            id=self.id,
            name=self.id,
            aliases=self.aliases,
            group=self.group,
            module=self.module,
            source=self.source,
            definition=self.definition(),
            data=data,
            hash=hash,
            rows=rows,
            columns=columns,
            timing_ms=timing_ms,
            problems=problems,
        )

    def problem(
        self,
        kind: str,
        message: str,
        *,
        severity: Literal["error", "warning"] = "error",
        source: Source | None = None,
        traceback: str | None = None,
    ) -> Problem:
        """A problem with this Blick, located at its definition unless ``source`` is given."""
        return Problem(
            kind=kind,
            severity=severity,
            source=source or self.source,
            module=self.module,
            ids=(self.id,),
            message=message,
            traceback=traceback,
        )


@dataclass(frozen=True)
class Registry:
    """The Blicks, groups and problems of one project, assembled by ``discover``.

    ``blicks`` holds exactly the Blicks that can be built, in discovery order. Every Blick with
    a problem (an invalid definition, an id claimed twice, an alias collision) is in ``failed``
    instead, so that nothing defined vanishes.
    ``problems`` are those that concern a file or the project rather than one Blick, errors and
    warnings alike. ``aliases`` maps each former id to its current id.
    """

    root: Path | None = None
    blicks: Mapping[str, Blick] = field(default_factory=dict)
    failed: tuple[BlickEntry, ...] = ()
    groups: Mapping[str, Group] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)
    problems: tuple[Problem, ...] = ()

    @property
    def errors(self) -> tuple[Problem, ...]:
        return tuple(problem for problem in self.problems if problem.severity == "error")

    @property
    def warnings(self) -> tuple[Problem, ...]:
        return tuple(problem for problem in self.problems if problem.severity == "warning")

    @property
    def has_errors(self) -> bool:
        return bool(self.errors or self.failed)

    @property
    def incomplete(self) -> bool:
        """Whether a file or the project failed, so that Blicks may be missing, not just failed.

        Blick-level problems live in ``failed``; every error here concerns a file or the project.
        """
        return bool(self.errors)
