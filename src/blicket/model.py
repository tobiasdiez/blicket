"""The data model of a project's units, its Blicks and checks: the units, groups, the registry,
and the shapes reports record them in: definitions and entries.

A Blick and a check share a base, ``Unit``, and so do their entries, ``Entry``: an id, a title, a
group, a transformation of the run, an expectation on its table and a level. A Blick adds a plot;
a check's table is the rows that offend, and its expectation is ``bk.expect.no_rows()`` unless it
names another.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, ClassVar, Literal, Self, TypedDict, Unpack

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator

from blicket.errors import Problem, Source
from blicket.expect._levels import DEFAULT_LEVEL, Level, resolve_level
from blicket.expect._outcome import Outcome
from blicket.expect._vocabulary import Expectation, ExpectationRecord, NoRows
from blicket.plots import PlotSpec, Scale
from blicket.schema import Control, ControlKind, TableSchema

type Transform = Callable[[Any], Any]

# What became of a unit in a build: it built a table, its transformation skipped the run (or, for
# a check, its level is off), or it failed.
type Status = Literal["ok", "skipped", "error"]

# The reason of a check that is not run because its level is off.
LEVEL_OFF = "its level is off"


def _inside_the_build(path: str) -> str:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\0" in path:
        raise ValueError(f"must be a path inside the build directory, got {path!r}")
    return path


# A path relative to a build directory that stays inside it: not absolute, without "..".
BuildPath = Annotated[str, AfterValidator(_inside_the_build)]


class Group(BaseModel):
    """A group of Blicks and checks, named by ``bk.group()`` or after its module; ``level`` is the
    level its units have unless they give their own."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str | None = None
    tags: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    level: Level | None = None


class PlotDefinition(BaseModel):
    """A Blick's plot as recorded: the plot type's name, the mapping of channels to columns, and
    the scales of the channels whose axis is not linear, such as ``{"y": "log"}``.

    ``scales`` is left out of the dump when empty, so a plot with linear axes is recorded as one
    of a plot type without scales.
    """

    model_config = ConfigDict(frozen=True)

    type: str
    mapping: dict[str, str]
    scales: dict[str, Scale] = Field(default={}, exclude_if=lambda scales: not scales)


class BlickDefinition(BaseModel):
    """How a Blick is defined, apart from its id, aliases and transformation: the options of
    ``@bk.blick``, with the plot as a ``PlotDefinition`` and the expectation as its record.
    ``tags`` are the Blick's own; ``controls`` are the control kinds the author asked for, not the
    controls a build derives; ``level`` is the level the Blick gives itself, if any."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str | None
    unit: str | None
    tags: tuple[str, ...]
    plot: PlotDefinition
    independent_y: bool
    controls: dict[str, ControlKind]
    defaults: dict[str, Any]
    tolerance: float | None
    dims: tuple[str, ...] | None
    measures: tuple[str, ...] | None
    order: dict[str, tuple[Any, ...]]
    level: Level | None = None
    expect: ExpectationRecord | None = None


class CheckDefinition(BaseModel):
    """How a check is defined, apart from its id, aliases and transformation: the options of
    ``@bk.check``, with its expectation as its record, ``no_rows`` unless it names another."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str | None
    tags: tuple[str, ...]
    level: Level | None
    expect: ExpectationRecord
    dims: tuple[str, ...] | None
    measures: tuple[str, ...] | None


class Entry(BaseModel):
    """A defined unit, a Blick or a check, as a report records it: what defines it, its table,
    the outcome of its expectation, and its problems.

    ``id`` is ``None`` when no usable id was given or derived; ``name`` is the id if there is
    one, else the function's name, else the id as given. ``definition`` is ``None`` when the
    unit's arguments were invalid. ``level`` is the level the unit has, its own, its group's or
    the project's. ``data``, ``hash``, ``rows`` and ``columns`` describe the table a build wrote,
    ``data`` as a relative path that stays inside the build directory. ``outcome`` is what the
    evaluation of its expectation gave, ``None`` for a unit without an expectation, at level
    ``off``, without a table, or skipped. ``skipped`` is the reason a transformation gave when it
    skipped the run with ``bk.Skip``; an entry with a reason has no table, no outcome and no
    problems. ``status`` is ``skipped`` when ``skipped`` is set, else ``error`` when a problem is
    an error, else ``ok``: an outcome stands beside the status and never changes it.
    """

    model_config = ConfigDict(frozen=True)

    # How reports name the kind, "Blick" or "check", and what a skipped one has none of.
    kind: ClassVar[str]
    _run_parts: ClassVar[str] = "table, outcome or problems"

    id: str | None
    name: str
    aliases: tuple[str, ...] = ()
    group: str
    module: str | None = None
    source: Source | None = None
    definition: BlickDefinition | CheckDefinition | None = None
    level: Level | None = None
    data: BuildPath | None = None
    hash: str | None = None
    rows: int | None = None
    columns: TableSchema | None = None
    outcome: Outcome | None = None
    timing_ms: float | None = None
    skipped: str | None = None
    problems: tuple[Problem, ...] = ()

    @computed_field
    @property
    def status(self) -> Status:
        if self.skipped is not None:
            return "skipped"
        return "error" if any(p.severity == "error" for p in self.problems) else "ok"

    @property
    def expectation(self) -> ExpectationRecord | None:
        """The expectation as declared, ``None`` without one or without a definition."""
        return self.definition.expect if self.definition is not None else None

    def _without_a_run(self) -> bool:
        """Whether nothing of what a run gives is recorded: no table, outcome or problems."""
        table = (self.data, self.hash, self.rows, self.columns, self.outcome)
        return all(part is None for part in table) and not self.problems

    @model_validator(mode="after")
    def _skipped_has_nothing(self) -> Self:
        if self.skipped is not None and not self._without_a_run():
            raise ValueError(f"a skipped {self.kind} has no {self._run_parts}")
        return self


class BlickEntry(Entry):
    """A defined Blick as a report records it, ``Entry`` with its definition and its controls:
    what the viewer offers for its table, the plot type's controls with the requests of
    ``definition.controls`` and ``definition.defaults`` applied; a skipped Blick has none."""

    kind: ClassVar[str] = "Blick"
    _run_parts: ClassVar[str] = "table, controls, outcome or problems"

    definition: BlickDefinition | None = None
    controls: tuple[Control, ...] = ()

    def _without_a_run(self) -> bool:
        return super()._without_a_run() and not self.controls

    @property
    def panels(self) -> tuple[str, ...]:
        """The dimensions whose value combinations each get their own scale in a comparison: the
        filters, and the splits when the definition sets ``independent_y``, since each facet
        then has a y axis of its own."""
        independent = self.definition is not None and self.definition.independent_y
        return tuple(c.dimension for c in self.controls if c.kind == "filter" or independent)


class CheckEntry(Entry):
    """A defined check as a report records it, ``Entry`` with its definition. Its table is the
    offending rows, worst first, at most as many as a build stores: ``rows`` counts those stored,
    the outcome all of them. A check that is met stores no table: ``data``, ``hash`` and
    ``columns`` are ``None`` and ``rows`` is 0."""

    kind: ClassVar[str] = "check"

    definition: CheckDefinition | None = None


class Identity(TypedDict):
    """The fields of an entry that name and locate its unit; see ``Entry``."""

    id: str | None
    name: str
    aliases: tuple[str, ...]
    group: str
    module: str | None
    source: Source | None


class Made(TypedDict, total=False):
    """What a build made of a unit, as its entry records it; see ``Entry``."""

    level: Level | None
    problems: tuple[Problem, ...]
    data: str | None
    hash: str | None
    rows: int | None
    columns: TableSchema | None
    outcome: Outcome | None
    timing_ms: float | None
    skipped: str | None


@dataclass(frozen=True, kw_only=True)
class Unit:
    """What a Blick and a check have in common: an id, a title, a group, a transformation of the
    run, the roles of its table's columns, an expectation on its table and a level.

    ``tags`` are the unit's own tags; its group has tags of its own. ``level`` is the level the
    unit gives itself, ``None`` to take its group's or the project's. ``module`` is ``None`` for
    units that do not come from a module.
    """

    # The directory of the unit's tables in a build.
    directory: ClassVar[str]

    id: str
    title: str
    description: str | None = None
    group: str
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    dims: tuple[str, ...] | None = None
    measures: tuple[str, ...] | None = None
    expect: Expectation | None = None
    level: Level | None = None
    transform: Transform
    module: str | None = None
    source: Source | None = None

    def entry(self, **made: Unpack[Made]) -> Entry:
        """The unit as a report records it, with its level and what a build ``made`` of it, if
        anything: its table, the outcome of its expectation, or the reason it skipped the run."""
        raise NotImplementedError

    def _identity(self) -> Identity:
        """The fields of an entry that name and locate the unit."""
        return {
            "id": self.id,
            "name": self.id,
            "aliases": self.aliases,
            "group": self.group,
            "module": self.module,
            "source": self.source,
        }

    def problem(
        self,
        kind: str,
        message: str,
        *,
        severity: Literal["error", "warning"] = "error",
        source: Source | None = None,
        traceback: str | None = None,
    ) -> Problem:
        """A problem with this unit, located at its definition unless ``source`` is given."""
        return Problem(
            kind=kind,
            severity=severity,
            source=source or self.source,
            module=self.module,
            ids=(self.id,),
            message=message,
            traceback=traceback,
        )


@dataclass(frozen=True, kw_only=True)
class Blick(Unit):
    """A named view on a model run: a transformation of the run and how to plot its table, with
    an optional expectation on the table."""

    directory: ClassVar[str] = "blicks"

    unit: str | None = None
    plot: PlotSpec
    independent_y: bool = False
    controls: Mapping[str, ControlKind] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)
    tolerance: float | None = None
    order: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)

    def definition(self) -> BlickDefinition:
        """Everything that defines the Blick except its transformation."""
        return BlickDefinition(
            title=self.title,
            description=self.description,
            unit=self.unit,
            tags=self.tags,
            plot=PlotDefinition(
                type=self.plot.plot_type.name,
                mapping=dict(self.plot.mapping),
                scales=dict(self.plot.scales),
            ),
            independent_y=self.independent_y,
            controls=dict(self.controls),
            defaults=dict(self.defaults),
            tolerance=self.tolerance,
            dims=self.dims,
            measures=self.measures,
            order=dict(self.order),
            level=self.level,
            expect=self.expect.record() if self.expect is not None else None,
        )

    def _controls_for(self, schema: TableSchema) -> tuple[Control, ...]:
        """The plot type's controls for a table of ``schema``, with this Blick's requests applied.

        ``controls={dim: "split"}`` or ``"filter"`` sets a control's kind; a value in ``defaults``
        becomes its default when the table holds it, and of a list the first element does.
        """
        values = {dimension.name: dimension.values for dimension in schema.dimensions}
        derived: list[Control] = []
        for control in self.plot.plot_type.controls(schema, self.plot.mapping):
            update: dict[str, Any] = {}
            if (kind := self.controls.get(control.dimension)) is not None:
                update["kind"] = kind
            if control.dimension in self.defaults:
                wanted = self.defaults[control.dimension]
                if isinstance(wanted, list | tuple):
                    wanted = wanted[0] if wanted else None
                if wanted in values.get(control.dimension, ()):
                    update["default"] = wanted
            derived.append(control.model_copy(update=update))
        return tuple(derived)

    def entry(self, **made: Unpack[Made]) -> BlickEntry:
        """The Blick as a report records it, with what a build made of it, if anything, and the
        controls derived for its table's schema ``columns``."""
        columns = made.get("columns")
        controls = self._controls_for(columns) if columns is not None else ()
        return BlickEntry(
            **self._identity(), definition=self.definition(), controls=controls, **made
        )


@dataclass(frozen=True, kw_only=True)
class Check(Unit):
    """A property of a model run that must hold: a transformation of the run that returns the
    offending rows as a long table, and the expectation on them, by default that there are none.
    A check has no plot; its table may have any number of measures, nulls in its dimensions, and
    no rows, which is the normal case."""

    directory: ClassVar[str] = "checks"

    # bk.expect.no_rows() unless the check names another.
    expect: Expectation = field(default_factory=NoRows)

    def definition(self) -> CheckDefinition:
        """Everything that defines the check except its transformation."""
        return CheckDefinition(
            title=self.title,
            description=self.description,
            tags=self.tags,
            level=self.level,
            expect=self.expect.record(),
            dims=self.dims,
            measures=self.measures,
        )

    def entry(self, **made: Unpack[Made]) -> CheckEntry:
        """The check as a report records it, with what a build made of it, if anything."""
        return CheckEntry(**self._identity(), definition=self.definition(), **made)


@dataclass(frozen=True)
class Registry:
    """The Blicks, checks, groups and problems of one project, assembled by ``discover``.

    ``blicks`` and ``checks`` hold exactly the units that can be built, in discovery order. Every
    unit with a problem (an invalid definition, an id claimed twice, an alias collision) is in
    ``failed`` instead, a ``BlickEntry`` or a ``CheckEntry``, so that nothing defined vanishes.
    ``problems`` are those that concern a file or the project rather than one unit, errors and
    warnings alike. ``aliases`` maps each former id to its current id; Blicks and checks share
    one namespace of ids and aliases. ``level`` is the project's, ``level`` in ``[tool.blicket]``.
    ``with_checks`` says that the project defines checks, or that a file failed on the API of
    checks, so that messages name them.
    """

    root: Path | None = None
    level: Level = DEFAULT_LEVEL
    with_checks: bool = False
    blicks: Mapping[str, Blick] = field(default_factory=dict)
    checks: Mapping[str, Check] = field(default_factory=dict)
    failed: tuple[BlickEntry | CheckEntry, ...] = ()
    groups: Mapping[str, Group] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)
    problems: tuple[Problem, ...] = ()

    @property
    def units(self) -> tuple[Unit, ...]:
        """The units that can be built: the Blicks, then the checks."""
        return (*self.blicks.values(), *self.checks.values())

    def level_of(self, unit: Unit) -> Level:
        """The level ``unit`` has: its own, else its group's, else the project's."""
        group = self.groups.get(unit.group)
        return resolve_level(unit.level, group.level if group else None, self.level)

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
