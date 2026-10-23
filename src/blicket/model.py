"""The data model of a project's Blicks: Blicks, failed Blicks, groups and the registry."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from blicket.errors import Problem, Source
from blicket.plots import PlotSpec

ControlKind = Literal["filter", "split"]
type Transform = Callable[[Any], Any]


@dataclass(frozen=True)
class Group:
    """A group of Blicks, named by ``bk.group()`` or after its module."""

    name: str
    title: str | None = None
    tags: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The JSON form, as ``blicket list --json`` prints it."""
        return {
            "name": self.name,
            "title": self.title,
            "tags": list(self.tags),
            "modules": list(self.modules),
        }


@dataclass(frozen=True, kw_only=True)
class Blick:
    """A named view on a model run: a transformation of the run and how to plot its table.

    ``tags`` are the Blick's own tags; ``Registry.tags_of`` adds the group's. ``dims``,
    ``measures`` and ``order`` are stored as given. ``module`` is ``None`` for Blicks that do not
    come from a module.
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

    def to_json(
        self, root: Path | None = None, tags: Iterable[str] | None = None
    ) -> dict[str, Any]:
        """The JSON form, as ``blicket list --json`` prints it.

        ``tags`` overrides the Blick's own tags, so the registry can pass the group's as well.
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "group": self.group,
            "tags": list(self.tags if tags is None else tags),
            "plot": self.plot.to_json(),
            "controls": dict(self.controls),
            "defaults": dict(self.defaults),
            "tolerance": self.tolerance,
            "aliases": list(self.aliases),
            "dims": None if self.dims is None else list(self.dims),
            "measures": None if self.measures is None else list(self.measures),
            "order": {key: list(values) for key, values in self.order.items()},
            "module": self.module,
            "source": self.source.to_json(root) if self.source else None,
        }


@dataclass(frozen=True, kw_only=True)
class FailedBlick:
    """A Blick that was defined but cannot be built, with the problems that say why.

    ``id`` is ``None`` when no usable id was given or derived; ``name`` is the id if there is
    one, else the function's name, else the id as given.
    """

    id: str | None
    name: str
    group: str
    module: str | None = None
    source: Source | None = None
    problems: tuple[Problem, ...]

    def to_json(self, root: Path | None = None) -> dict[str, Any]:
        """The JSON form, as ``blicket list --json`` prints it."""
        return {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "module": self.module,
            "source": self.source.to_json(root) if self.source else None,
            "problems": [problem.to_json(root) for problem in self.problems],
        }


@dataclass(frozen=True)
class Registry:
    """The Blicks, groups and problems of one project, assembled by ``discover``.

    ``blicks`` holds exactly the Blicks that can be built, in discovery order. Every Blick with
    a problem (an invalid definition, an id claimed twice, an alias collision, a tolerance finer
    than the project's digits) is in ``failed`` instead, so that nothing defined vanishes.
    ``problems`` are those that concern a file or the project rather than one Blick, errors and
    warnings alike. ``aliases`` maps each former id to its current id.
    """

    root: Path | None = None
    blicks: Mapping[str, Blick] = field(default_factory=dict)
    failed: tuple[FailedBlick, ...] = ()
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

    def tags_of(self, blick_id: str) -> tuple[str, ...]:
        """The tags of a Blick: its group's followed by its own, without repetitions."""
        blick = self.blicks[blick_id]
        group = self.groups.get(blick.group)
        group_tags = group.tags if group is not None else ()
        return tuple(dict.fromkeys((*group_tags, *blick.tags)))

    def to_json(self) -> dict[str, Any]:
        """The definitions and problems in the form ``blicket list --json`` prints."""
        return {
            "root": None if self.root is None else str(self.root),
            "groups": [group.to_json() for group in self.groups.values()],
            "blicks": [
                blick.to_json(self.root, tags=self.tags_of(blick.id))
                for blick in self.blicks.values()
            ],
            "failed": [blick.to_json(self.root) for blick in self.failed],
            "aliases": dict(self.aliases),
            "errors": [error.to_json(self.root) for error in self.errors],
            "warnings": [warning.to_json(self.root) for warning in self.warnings],
        }
