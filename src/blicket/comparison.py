"""The comparison of two builds, Blick by Blick, as pydantic models that are its file format.

A current Blick is matched to the baseline Blick of its id that has a table, else to the first of
its aliases that has one, and the two tables are compared by the plot type's ``diff``. The flags
are those of ``Flag``: ``schema`` from the plot type, ``value`` when the magnitude exceeds the
Blick's tolerance, ``new`` for a Blick without a baseline table, ``removed`` for a baseline Blick
with a table that no current Blick claims, and ``error`` for a Blick that has no table or cannot
be compared. A Blick whose transformation skipped the run has no table and is no error. Skipped
in the current build, it is ``removed`` when the baseline has a table for it, and otherwise has no
flag and counts as skipped, not as unchanged, since nothing was compared; skipped in the baseline
only, it is ``new``.

The outcomes of the expectations are related too, for Blicks and checks alike, checks matched by
id and alias among the checks as Blicks among the Blicks; a check's table is not compared. The
results are ordered met < warning < failed. An expectation not met now is ``broken`` when it is
worse than the baseline's outcome of the same expectation and ``still_failing`` otherwise, and
``new`` when the baseline has no outcome of it: the unit or the expectation is new or changed, or
was off, skipped or in error there. One met now that was not met there is ``fixed``. One not met
in the baseline without an outcome now, since the unit or the expectation is gone, off, skipped or
in error, is ``dropped``, so that silencing a failing check shows. An outcome ``error`` is no
outcome to relate. Whether the expectation is the same is read from its record in the two
manifests. The transitions flag no Blick.

``write`` puts a comparison into the current build directory, under ``compare/<baseline id>/``:
``comparison.json`` and the baseline tables of the Blicks flagged ``value`` or ``schema`` as
``blicks/<current id>.parquet``. ``compare/index.json`` lists the baseline ids of the comparisons
there, since a directory cannot be listed over HTTP; nothing in blicket reads it.
"""

import importlib.metadata
import json
import os
import secrets
import shutil
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict

from blicket import manifest
from blicket.errors import BlicketError, Kind, os_reason
from blicket.expect._outcome import Outcome, rank
from blicket.manifest import Manifest, Repository
from blicket.model import BlickEntry, BuildPath, Entry
from blicket.plots import builtin
from blicket.schema import Change, Flag

type Transition = Literal["broken", "new", "fixed", "still_failing", "dropped"]
# The transitions in the order reports count them.
TRANSITIONS: tuple[Transition, ...] = ("broken", "new", "fixed", "still_failing", "dropped")

COMPARE = "compare"
COMPARISON = "comparison.json"
INDEX = "index.json"


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


class ExpectationComparison(BaseModel):
    """The outcome of a unit's expectation now and in the baseline, and the transition between.

    ``current`` is the outcome now, one that cannot be evaluated included; ``baseline`` the
    baseline's outcome of the same expectation, or, when there is no outcome now or one that
    cannot be evaluated, of the expectation the baseline had. ``transition`` is ``None`` when
    nothing changed that a report names: met in both, met now and without an outcome there, or
    without an outcome on either side; an outcome that cannot be evaluated counts as none for it.
    ``message`` says why a side has no outcome, or that the expectation changed.
    """

    model_config = ConfigDict(frozen=True)

    transition: Transition | None
    current: Outcome | None
    baseline: Outcome | None
    message: str | None = None


class UnitComparison(BaseModel):
    """What a comparison records of a Blick or a check.

    ``id`` is the current id, the baseline id for a unit of the baseline that no current unit
    claims, and ``None`` for a current unit without a usable id; ``name`` is the entry's name.
    ``matched`` is the id of the baseline unit matched when it differs from the current one, as
    for a unit matched through an alias. ``expectation`` relates the outcomes of the unit's
    expectation, ``None`` when neither build gives the unit one. ``message`` is the cause of a unit
    in error, and for a Blick also why it has no table or was not compared.
    """

    model_config = ConfigDict(frozen=True)

    # How reports name the kind: "Blick" or "check".
    kind: ClassVar[str]

    id: str | None
    name: str
    matched: str | None = None
    expectation: ExpectationComparison | None = None
    message: str | None = None

    @property
    def error(self) -> bool:
        """Whether the unit is in error in the current build."""
        raise NotImplementedError


class BlickComparison(UnitComparison):
    """A Blick of a comparison, ``UnitComparison`` with the change of its table.

    ``skipped`` says that the current Blick's transformation
    skipped the run, so that no tables were compared: such a Blick is ``removed`` when the
    baseline has a table for it, and otherwise has no flag and is not unchanged.

    ``message`` says why a Blick has no table or was not compared. For an ``error`` Blick, it is
    the cause. For a ``new`` one whose Blick in the baseline has no table, it says that the Blick
    did not build in the baseline, or that it was skipped there, with the first line of the
    reason. For a skipped one, it is ``skipped:`` and the first line of the reason; without a
    flag, what the baseline holds of the Blick follows in parentheses: that it was skipped there
    too, with the first line of that reason, that it did not build there, or that it is not there.

    ``baseline_data`` is the copy of the baseline table that ``write`` makes for a Blick flagged
    ``value`` or ``schema``, relative to the build directory, and ``baseline_hash`` that table's
    hash in the baseline manifest; both are ``None`` for the other Blicks and before ``write``.
    """

    kind: ClassVar[str] = "Blick"

    change: Change
    skipped: bool = False
    baseline_data: BuildPath | None = None
    baseline_hash: str | None = None

    @property
    def error(self) -> bool:
        return "error" in self.change.flags


class CheckComparison(UnitComparison):
    """A check of a comparison: a current check, or a baseline check that no current check claims
    and whose expectation is dropped. Its table is not compared. ``message`` is the cause of a
    current check in error, its first error's first line, as a Blick's is, and ``None`` for any
    other."""

    kind: ClassVar[str] = "check"

    @property
    def error(self) -> bool:
        return self.message is not None


class Comparison(BaseModel):
    """The comparison of a current build with a baseline.

    ``spec`` is the current manifest's, ``blicket`` the version that compared, which names the
    formula of the magnitude. ``blicks`` lists the current Blicks in the current manifest's order,
    the skipped ones among them, then the removed ones that no current Blick claims; ``checks``
    the current checks, then the baseline checks whose expectation is dropped.
    ``incomplete`` holds the reasons why removed Blicks were not judged, and dropped checks: a
    file of the current build that failed, a current unit without a usable id; it is empty when
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
    checks: tuple[CheckComparison, ...] = ()

    @property
    def units(self) -> tuple[UnitComparison, ...]:
        """The units of both kinds, the Blicks first, each kind in the comparison's order."""
        return (*self.blicks, *self.checks)

    def errors(self) -> Iterator[UnitComparison]:
        """The units in error in the current build, Blicks flagged ``error`` and checks in error,
        in the order of ``units``; each has its cause as ``message``."""
        return (unit for unit in self.units if unit.error)

    def unevaluable(self) -> Iterator[tuple[UnitComparison, Outcome]]:
        """The units whose expectation cannot be evaluated now, and that outcome."""
        for unit, related in self.expectations():
            if related.current is not None and related.current.result == "error":
                yield unit, related.current

    def expectations(self) -> Iterator[tuple[UnitComparison, ExpectationComparison]]:
        """Every unit with an expectation, and the expectation, in the order of ``units``."""
        for unit in self.units:
            if unit.expectation is not None:
                yield unit, unit.expectation

    @property
    def transitions(self) -> Counter[Transition]:
        """How many expectations of both kinds have each transition."""
        return Counter(
            related.transition
            for _, related in self.expectations()
            if related.transition is not None
        )

    @property
    def counts(self) -> Counter[Flag]:
        """How many Blicks carry each flag."""
        return Counter(flag for blick in self.blicks for flag in blick.change.flags)

    @property
    def flagged(self) -> int:
        """How many Blicks carry a flag."""
        return sum(bool(blick.change.flags) for blick in self.blicks)

    @property
    def skipped(self) -> int:
        """How many current Blicks were skipped, flagged ``removed`` or not."""
        return sum(blick.skipped for blick in self.blicks)

    @property
    def has_errors(self) -> bool:
        """Whether the comparison holds an error of any kind: removed Blicks and dropped checks not
        judged, a unit in error, an expectation that cannot be evaluated."""
        return bool(self.incomplete) or any(self.errors()) or any(True for _ in self.unevaluable())

    def movers(self, n: int) -> list[BlickComparison]:
        """The ``n`` Blicks flagged ``value`` with the largest magnitudes, by name when they are
        equal to two significant digits, as reports show them."""
        flagged = [blick for blick in self.blicks if "value" in blick.change.flags]
        return sorted(flagged, key=lambda b: (-float(f"{b.change.magnitude or 0:.2g}"), b.name))[:n]


def compare_builds(baseline: Path, current: Path) -> Comparison:
    """Compare the build in the directory ``current`` with the one in ``baseline``.

    Every current Blick claims the baseline Blicks of its id and its aliases, whether or not it
    has a table, so a Blick that failed or was skipped is never also removed. Its counterpart in
    the baseline is the first of those Blicks with a table, else the first of them. A baseline
    Blick with a table that no current Blick claims is removed, unless ``incomplete`` names a
    reason. A skipped current Blick is removed when its counterpart has a table, and has no flag
    otherwise. A new Blick whose counterpart has no table says why in its ``message``. A plot type
    that this blicket does not know, or whose ``diff`` rejects the tables, makes the Blick
    ``error``. Raises ``BlicketError`` when a manifest or a table cannot be read.

    The checks are matched as the Blicks are, among the checks, a check that ran preferred; each
    current check is listed, and a baseline check that no current check claims when its
    expectation is dropped, unless ``incomplete`` names a reason. Every expectation is related as
    the module says.
    """
    before, after = manifest.read(baseline), manifest.read(current)
    # Only Blicks that failed share an id; one with a table is the one to compare with.
    find = _Counterparts(before.blicks, lambda entry: entry.data is not None)
    blicks: list[BlickComparison] = []
    for entry in after.blicks:
        counterpart = find(entry)
        compared = _blick_comparison(entry, counterpart, baseline, current, after.config.tolerance)
        blicks.append(compared.model_copy(update={"expectation": relate(entry, counterpart)}))
    checks: list[CheckComparison] = []
    find_check = _Counterparts(before.checks, lambda entry: entry.status == "ok")
    for entry in after.checks:
        counterpart = find_check(entry)
        checks.append(
            CheckComparison(
                id=entry.id,
                name=entry.name,
                matched=counterpart.id if counterpart and counterpart.id != entry.id else None,
                expectation=relate(entry, counterpart),
                message=_cause(entry) if entry.status == "error" else None,
            )
        )
    incomplete = _incomplete(after)
    if not incomplete:
        blicks.extend(
            _flagged(entry, "removed").model_copy(update={"expectation": relate(None, entry)})
            for entry in find.unclaimed()
            if entry.data is not None
        )
        for entry in find_check.unclaimed():
            related = relate(None, entry)
            if related is not None and related.transition == "dropped":
                checks.append(CheckComparison(id=entry.id, name=entry.name, expectation=related))
    return Comparison(
        spec=after.spec,
        blicket=importlib.metadata.version("blicket"),
        created_at=datetime.now(UTC),
        baseline=_reference(before),
        current=_reference(after),
        incomplete=incomplete,
        blicks=tuple(blicks),
        checks=tuple(checks),
    )


def _blick_comparison(
    entry: BlickEntry,
    counterpart: BlickEntry | None,
    baseline: Path,
    current: Path,
    tolerance: float,
) -> BlickComparison:
    """A current Blick of the build in ``current`` compared with its ``counterpart`` in the
    build in ``baseline``, without its expectation; ``tolerance`` is the project's."""
    table = counterpart.data if counterpart else None
    matched = counterpart.id if counterpart and counterpart.id != entry.id else None
    if entry.status == "skipped":
        message = _absence(entry)
        if table is not None:
            return _flagged(entry, "removed", message, skipped=True, matched=matched)
        there = _absence(counterpart, "in the baseline") if counterpart else "not in the baseline"
        return BlickComparison(
            id=entry.id,
            name=entry.name,
            change=Change(),
            skipped=True,
            message=f"{message} ({there})",
        )
    if entry.id is None or entry.definition is None or entry.data is None:
        return _flagged(entry, "error", _cause(entry))
    if table is None:
        message = _absence(counterpart, "in the baseline") if counterpart else None
        return _flagged(entry, "new", message)
    plot = entry.definition.plot
    try:
        change = builtin(plot.type).diff(
            _table(baseline, table),
            _table(current, entry.data),
            plot.mapping,
            entry.panels,
        )
    except (ValueError, TypeError) as error:  # DefinitionError for an unknown plot type
        return _flagged(entry, "error", str(error))
    if entry.definition.tolerance is not None:
        tolerance = entry.definition.tolerance
    if change.magnitude is not None and change.magnitude > tolerance:
        change = change.model_copy(update={"flags": change.flags | {"value"}})
    return BlickComparison(id=entry.id, name=entry.name, matched=matched, change=change)


class _Counterparts[E: Entry]:
    """Finds the counterpart of a current entry among the baseline's entries of its kind.

    A current entry claims the baseline entries of its id and its aliases, whether or not they
    built; its counterpart is the first of them that ``preferred`` accepts, else the first of
    them. ``unclaimed`` are the baseline entries with an id that no current entry claimed.
    """

    def __init__(self, entries: Sequence[E], preferred: Callable[[E], bool]) -> None:
        self._entries = entries
        self._preferred = preferred
        self._by_id: dict[str, E] = {}
        for entry in entries:
            if entry.id is not None and (entry.id not in self._by_id or preferred(entry)):
                self._by_id[entry.id] = entry
        self._claimed: set[str] = set()

    def __call__(self, entry: Entry) -> E | None:
        names = [name for name in (entry.id, *entry.aliases) if name is not None]
        self._claimed.update(names)
        found = [self._by_id[name] for name in names if name in self._by_id]
        return next((e for e in found if self._preferred(e)), found[0] if found else None)

    def unclaimed(self) -> list[E]:
        return [e for e in self._entries if e.id is not None and e.id not in self._claimed]


def _usable(outcome: Outcome | None) -> Outcome | None:
    """``outcome`` as the transitions take it: none for an outcome ``error``."""
    return None if outcome is None or outcome.result == "error" else outcome


def _no_outcome(entry: Entry | None, place: str, missing: str) -> str | None:
    """Why ``entry`` has no outcome, ``None`` when it has one; ``place`` names the build, such as
    ``in the baseline``, and ``missing`` says that the build lacks the unit."""
    if entry is None:
        return missing
    if entry.outcome is not None:
        return None
    if entry.status == "skipped":
        return f"skipped {place}: {_first(entry.skipped or '')}"
    if entry.status == "error":
        return f"in error {place}"
    if entry.expectation is None:
        return f"no expectation {place}"
    if entry.level == "off":
        return f"level off {place}"
    return f"no outcome {place}"


def relate(current: Entry | None, baseline: Entry | None) -> ExpectationComparison | None:
    """The outcomes of the expectation of a current unit and its baseline counterpart, either of
    which may be missing, related as the module says; ``None`` when neither declares an
    expectation."""
    declared_now = current.expectation if current is not None else None
    declared_then = baseline.expectation if baseline is not None else None
    if declared_now is None and declared_then is None:
        return None
    now_any = current.outcome if current is not None else None
    then_any = baseline.outcome if baseline is not None else None
    now, then = _usable(now_any), _usable(then_any)
    changed = (
        declared_now is not None and declared_then is not None and declared_now != declared_then
    )
    same = None if changed or declared_now is None else then
    transition: Transition | None = None
    if now is not None and now.offends:
        if same is None:
            transition = "new"
        elif rank(now.result) > rank(same.result):
            transition = "broken"
        else:
            transition = "still_failing"
    elif now is not None:
        transition = "fixed" if same is not None and same.offends else None
    elif then is not None and then.offends:
        transition = "dropped"
    reasons = [
        _no_outcome(current, "now", "not in the current build"),
        _no_outcome(baseline, "in the baseline", "not in the baseline"),
        *(["the expectation changed since the baseline"] if changed else []),
    ]
    message = "; ".join(reason for reason in reasons if reason) or None
    return ExpectationComparison(
        transition=transition,
        current=now_any,
        baseline=then_any if now is None or not changed else None,
        message=message,
    )


def write(comparison: Comparison, baseline: Path, current: Path) -> Comparison:
    """Write ``comparison`` of the build directory ``current`` with the one in ``baseline`` into
    ``current/compare/<baseline id>/`` and return it as written, with ``baseline_data`` and
    ``baseline_hash`` set for the copied tables.

    The directory is assembled next to its destination and replaces what an earlier write put
    there. ``compare/index.json`` is then regenerated from the directories in ``compare/`` that
    hold a ``comparison.json``, ordered by that file's modification time, the newest last.
    Raises ``BlicketError`` when a build id of the comparison is not shaped like one, the baseline
    manifest cannot be read, or writing fails.
    """
    for build in (comparison.baseline, comparison.current):
        if not manifest.BUILD_ID.fullmatch(build.id):
            raise BlicketError(f"build {build.run} has an invalid build id {build.id!r}")
    compare = current / COMPARE
    baseline_id = comparison.baseline.id
    built = manifest.read(baseline).blicks
    tables = {e.id: (e.data, e.hash) for e in built if e.id is not None and e.data is not None}
    temporary = compare / f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
    blicks: list[BlickComparison] = []
    try:
        temporary.mkdir(parents=True)
        for blick in comparison.blicks:
            if blick.id is not None and blick.change.flags & {"value", "schema"}:
                data, digest = tables[blick.matched or blick.id]
                name = f"blicks/{blick.id}.parquet"
                (temporary / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(baseline / data, temporary / name)
                relative = f"{COMPARE}/{baseline_id}/{name}"
                blick = blick.model_copy(
                    update={"baseline_data": relative, "baseline_hash": digest}
                )
            blicks.append(blick)
        written = comparison.model_copy(update={"blicks": tuple(blicks)})
        (temporary / COMPARISON).write_text(written.model_dump_json(indent=2) + "\n")
        final = compare / baseline_id
        if final.exists():
            shutil.rmtree(final)
        temporary.rename(final)
        modified = {
            path.name: (path / COMPARISON).stat().st_mtime_ns
            for path in compare.iterdir()
            if manifest.BUILD_ID.fullmatch(path.name) and (path / COMPARISON).is_file()
        }
        ordered = sorted(modified, key=lambda name: (modified[name], name))
        (compare / INDEX).write_text(json.dumps(ordered) + "\n")
    except OSError as error:
        raise BlicketError(
            f"cannot write the comparison into {compare}: {os_reason(error)}"
        ) from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return written


def _flagged(
    entry: BlickEntry,
    flag: Flag,
    message: str | None = None,
    *,
    skipped: bool = False,
    matched: str | None = None,
) -> BlickComparison:
    change = Change(flags=frozenset({flag}))
    return BlickComparison(
        id=entry.id,
        name=entry.name,
        matched=matched,
        change=change,
        skipped=skipped,
        message=message,
    )


def _first(text: str) -> str:
    """The first line of ``text``, empty for an empty text."""
    return next(iter(text.splitlines()), "")


def _cause(entry: Entry) -> str | None:
    """The first line of the entry's first error."""
    errors = [p for p in entry.problems if p.severity == "error"]
    return _first(errors[0].message) if errors else None


def _absence(entry: BlickEntry, where: str = "") -> str:
    """Why ``entry`` has no table: skipped, with the first line of its reason, or did not build;
    ``where`` follows the verb, such as ``in the baseline``."""
    place = f" {where}" if where else ""
    if entry.status == "skipped":
        return f"skipped{place}: {_first(entry.skipped or '')}"
    return f"did not build{place}"


def _incomplete(built: Manifest) -> tuple[str, ...]:
    """Why the Blicks missing from ``built`` cannot be judged removed, nor the checks missing
    from it dropped: the files that failed and the units without a usable id."""
    reasons: list[str] = []
    for problem in built.problems:
        if problem.severity == "error":
            where = problem.source.file.as_posix() if problem.source else "the project"
            first = _first(problem.message)
            reasons.append(
                f"{where} failed to import: {first}"
                if problem.kind == Kind.IMPORT
                else f"{where}: {first}"
            )
    reasons += [f"{entry.name} has no usable id" for entry in built.entries if entry.id is None]
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
