"""The comparison of two builds, Blick by Blick, as pydantic models that are its file format.

A current Blick is matched to the baseline Blick of its id that has a table, else to the first of
its aliases that has one, and the two tables are compared by the plot type's ``diff``. The flags
are those of ``Flag``: ``schema`` from the plot type, ``value`` when the magnitude exceeds the
Blick's tolerance, ``new`` for a Blick without a baseline table, ``removed`` for a baseline Blick
with a table that no current Blick claims, and ``error`` for a Blick that has no table or cannot
be compared.
"""

import importlib.metadata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

from blicket import manifest
from blicket.errors import BlicketError, Kind
from blicket.manifest import Manifest, Repository
from blicket.model import BlickEntry
from blicket.plots import builtin
from blicket.schema import Change, Flag


class BuildRef(BaseModel):
    """What a comparison records of a build: its id, run, profile and time, the state of the
    repository holding the Blicks, if recorded, and whether a Blick module failed to import."""

    model_config = ConfigDict(frozen=True)

    id: str
    run: str
    profile: str
    created_at: datetime
    repository: Repository | None
    incomplete: bool


class BlickComparison(BaseModel):
    """A Blick of a comparison.

    ``id`` is the current id, the baseline id for a removed Blick, and ``None`` for a current
    Blick without a usable id; ``name`` is the entry's name. ``matched`` is the id of the baseline
    Blick whose table was compared when it differs from the current one, as for a Blick matched
    through an alias. ``message`` says why an ``error`` Blick has no table or was not compared.
    """

    model_config = ConfigDict(frozen=True)

    id: str | None
    name: str
    matched: str | None = None
    change: Change
    message: str | None = None


class Comparison(BaseModel):
    """The comparison of a current build with a baseline.

    ``spec`` is the current manifest's, ``blicket`` the version that compared, which names the
    formula of the magnitude. ``blicks`` lists the current Blicks in the current manifest's order,
    then the removed ones. ``incomplete`` holds the reasons why removed Blicks were not judged: a
    file of the current build that failed, a current Blick without a usable id; it is empty when
    they were.
    """

    model_config = ConfigDict(frozen=True)

    spec: str
    blicket: str
    created_at: datetime
    baseline: BuildRef
    current: BuildRef
    incomplete: tuple[str, ...]
    blicks: tuple[BlickComparison, ...]

    @property
    def counts(self) -> Counter[Flag]:
        """How many Blicks carry each flag."""
        return Counter(flag for blick in self.blicks for flag in blick.change.flags)

    @property
    def has_errors(self) -> bool:
        """Whether removed Blicks were not judged or a Blick is flagged ``error``."""
        return bool(self.incomplete) or self.counts["error"] > 0

    def movers(self, n: int) -> list[BlickComparison]:
        """The ``n`` Blicks flagged ``value`` with the largest magnitudes, the first on a tie."""
        flagged = [blick for blick in self.blicks if "value" in blick.change.flags]
        return sorted(flagged, key=lambda blick: blick.change.magnitude or 0.0, reverse=True)[:n]


def compare_builds(baseline: Path, current: Path) -> Comparison:
    """Compare the build in the directory ``current`` with the one in ``baseline``.

    Every current Blick claims the baseline Blicks of its id and its aliases, whether or not it
    has a table, so a Blick that failed is never also removed. A baseline Blick with a table that
    no current Blick claims is removed, unless ``incomplete`` names a reason. A new Blick whose
    baseline Blick had no table says so in its ``message``. A plot type that this blicket does not
    know, or whose ``diff`` rejects the tables, makes the Blick ``error``. Raises
    ``BlicketError`` when a manifest or a table cannot be read.
    """
    before, after = manifest.read(baseline), manifest.read(current)
    tables = {e.id: e.data for e in before.blicks if e.id is not None and e.data is not None}
    defined = {e.id for e in before.blicks}
    claimed: set[str] = set()
    blicks: list[BlickComparison] = []
    for entry in after.blicks:
        claimed.update(name for name in (entry.id, *entry.aliases) if name is not None)
        if entry.id is None or entry.definition is None or entry.data is None:
            blicks.append(_flagged(entry, "error", _cause(entry)))
            continue
        match = next((name for name in (entry.id, *entry.aliases) if name in tables), None)
        if match is None:
            failed = not defined.isdisjoint((entry.id, *entry.aliases))
            blicks.append(
                _flagged(entry, "new", "did not build in the baseline" if failed else None)
            )
            continue
        plot = entry.definition.plot
        try:
            change = builtin(plot.type).diff(
                _table(baseline, tables[match]),
                _table(current, entry.data),
                plot.mapping,
                entry.panels,
            )
        except (ValueError, TypeError) as error:  # DefinitionError for an unknown plot type
            blicks.append(_flagged(entry, "error", str(error)))
            continue
        tolerance = entry.definition.tolerance
        if tolerance is None:
            tolerance = after.config.tolerance
        if change.magnitude is not None and change.magnitude > tolerance:
            change = change.model_copy(update={"flags": change.flags | {"value"}})
        matched = match if match != entry.id else None
        blicks.append(BlickComparison(id=entry.id, name=entry.name, matched=matched, change=change))
    incomplete = _incomplete(after)
    if not incomplete:
        blicks.extend(
            _flagged(entry, "removed")
            for entry in before.blicks
            if entry.data is not None and entry.id not in claimed
        )
    return Comparison(
        spec=after.spec,
        blicket=importlib.metadata.version("blicket"),
        created_at=datetime.now(UTC),
        baseline=_reference(before),
        current=_reference(after),
        incomplete=incomplete,
        blicks=tuple(blicks),
    )


def _flagged(entry: BlickEntry, flag: Flag, message: str | None = None) -> BlickComparison:
    change = Change(flags=frozenset({flag}))
    return BlickComparison(id=entry.id, name=entry.name, change=change, message=message)


def _cause(entry: BlickEntry) -> str | None:
    """The first line of the entry's first error."""
    errors = [p for p in entry.problems if p.severity == "error"]
    return errors[0].message.splitlines()[0] if errors else None


def _incomplete(built: Manifest) -> tuple[str, ...]:
    """Why the Blicks missing from ``built`` cannot be judged removed: the files that failed and
    the Blicks without a usable id."""
    reasons: list[str] = []
    for problem in built.problems:
        if problem.severity == "error":
            where = problem.source.file.as_posix() if problem.source else "the project"
            first = problem.message.splitlines()[0]
            reasons.append(
                f"{where} failed to import" if problem.kind == Kind.IMPORT else f"{where}: {first}"
            )
    reasons += [f"{entry.name} has no usable id" for entry in built.blicks if entry.id is None]
    return tuple(reasons)


def _table(directory: Path, data: str) -> pl.DataFrame:
    try:
        return pl.read_parquet(directory / data)
    except (OSError, pl.exceptions.PolarsError) as error:
        reason = "file missing" if isinstance(error, FileNotFoundError) else str(error)
        raise BlicketError(f"cannot read {data} in {directory}: {reason}") from error


def _reference(built: Manifest) -> BuildRef:
    return BuildRef(
        id=built.build.id,
        run=built.run.id,
        profile=built.run.profile,
        created_at=built.created_at,
        repository=built.repository,
        incomplete=built.build.incomplete,
    )
