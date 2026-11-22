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

``compare_builds`` compares two build directories, ``compare`` a build directory with a
``Baseline`` read before; ``compare_blick`` compares one Blick and ``assemble`` puts the
comparisons of Blicks together with the removed ones, which a session of ``blicket dev`` uses as
its Blicks are built. ``place_baseline`` decides which baseline table a Blick flagged ``value`` or
``schema`` is drawn against, and names it where the caller puts it.

``write`` puts a comparison into the current build directory, under ``compare/<baseline id>/``:
``comparison.json`` and the baseline tables of the Blicks flagged ``value`` or ``schema`` as
``blicks/<current id>.parquet``. ``compare/index.json`` lists the baseline ids of the comparisons
there, since a directory cannot be listed over HTTP; nothing in blicket reads it.
"""

import functools
import hashlib
import importlib.metadata
import io
import json
import os
import secrets
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

from blicket import manifest, tables
from blicket.errors import BlicketError, Kind, first_line, os_reason
from blicket.manifest import Manifest, Repository
from blicket.model import BlickEntry, BuildPath
from blicket.plots import builtin
from blicket.schema import Change, Flag

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


class BlickComparison(BaseModel):
    """A Blick of a comparison.

    ``id`` is the current id, the baseline id for a removed Blick that no current Blick claims,
    and ``None`` for a current Blick without a usable id; ``name`` is the entry's name.
    ``matched`` is the id of the baseline Blick matched when it differs from the current one, as
    for a Blick matched through an alias. ``skipped`` says that the current Blick's transformation
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

    model_config = ConfigDict(frozen=True)

    id: str | None
    name: str
    matched: str | None = None
    change: Change
    skipped: bool = False
    message: str | None = None
    baseline_data: BuildPath | None = None
    baseline_hash: str | None = None


class Comparison(BaseModel):
    """The comparison of a current build with a baseline.

    ``spec`` is the current manifest's, ``blicket`` the version that compared, which names the
    formula of the magnitude. ``blicks`` lists the current Blicks in the current manifest's order,
    the skipped ones among them, then the removed ones that no current Blick claims.
    ``incomplete`` holds the reasons why removed Blicks were not judged: a file of the current
    build that failed, a current Blick without a usable id; it is empty when they were.
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
    def flagged(self) -> int:
        """How many Blicks carry a flag."""
        return sum(bool(blick.change.flags) for blick in self.blicks)

    @property
    def skipped(self) -> int:
        """How many current Blicks were skipped, flagged ``removed`` or not."""
        return sum(blick.skipped for blick in self.blicks)

    @property
    def has_errors(self) -> bool:
        """Whether removed Blicks were not judged or a Blick is flagged ``error``."""
        return bool(self.incomplete) or self.counts["error"] > 0

    def movers(self, n: int) -> list[BlickComparison]:
        """The ``n`` Blicks flagged ``value`` with the largest magnitudes, by name when they are
        equal to two significant digits, as reports show them."""
        flagged = [blick for blick in self.blicks if "value" in blick.change.flags]
        return sorted(flagged, key=lambda b: (-float(f"{b.change.magnitude or 0:.2g}"), b.name))[:n]


@dataclass(frozen=True)
class Baseline:
    """A baseline build as a comparison reads it: its directory, its manifest, and its Blicks by
    id, of the Blicks that share an id, which only failed ones do, the one with a table.

    ``kept`` holds the Parquet bytes of the tables read, by their path in the manifest, when the
    baseline keeps them (see ``keeping``), ``None`` when it reads each table from its file."""

    directory: Path
    manifest: Manifest
    by_id: Mapping[str, BlickEntry]
    kept: dict[str, bytes] | None = None

    @classmethod
    def read(cls, directory: Path) -> Baseline:
        """The baseline build in ``directory``; raises ``BlicketError`` when its manifest cannot
        be read."""
        return cls.of(directory, manifest.read(directory))

    @classmethod
    def of(cls, directory: Path, built: Manifest) -> Baseline:
        """The baseline build in ``directory`` with the manifest ``built``."""
        by_id: dict[str, BlickEntry] = {}
        for entry in built.blicks:
            # Only Blicks that failed share an id; one with a table is the one to compare with.
            if entry.id is not None and (entry.id not in by_id or entry.data is not None):
                by_id[entry.id] = entry
        return cls(directory, built, by_id)

    def keeping(self) -> Baseline:
        """This baseline, keeping the bytes of each table it reads, checked against their hash in
        its manifest, as a session that serves them does: each file is read once, and
        ``content`` gives the bytes that ``table`` read."""
        return replace(self, kept={})

    def table(self, data: str) -> pl.DataFrame:
        """The baseline's table at ``data``; raises ``BlicketError`` when it cannot be read, or,
        when the baseline keeps its tables, does not match its hash."""
        if self.kept is None:
            return _table(self.directory, data)
        try:
            return pl.read_parquet(io.BytesIO(self._content(data)))
        except pl.exceptions.PolarsError as error:
            raise BlicketError(
                f"cannot read {data} in {self.directory}: {error}{_DAMAGED}"
            ) from error

    def content(self, entry: BlickEntry) -> bytes:
        """The Parquet bytes of the table of the baseline Blick ``entry``, checked against its
        hash in the baseline's manifest; raises ``BlicketError`` when it has no table, the file
        cannot be read, or its bytes do not match the hash."""
        if entry.data is None or entry.hash is None:
            build = self.manifest.build.id
            raise BlicketError(f"{entry.name} has no table in the baseline {build}")
        return self._content(entry.data)

    def _content(self, data: str) -> bytes:
        """The bytes of the table at ``data``, read once when the baseline keeps them, and checked
        against the hash that the manifest gives that path."""
        if self.kept is not None and (known := self.kept.get(data)) is not None:
            return known
        try:
            content = (self.directory / data).read_bytes()
        except OSError as error:
            raise BlicketError(
                f"cannot read {data} in {self.directory}: {os_reason(error)}{_DAMAGED}"
            ) from error
        hashed = next((e.hash for e in self.manifest.blicks if e.data == data), None)
        if tables.content_hash(hashlib.sha256(content).hexdigest()) != hashed:
            raise BlicketError(
                f"{data} in {self.directory} does not match its hash in the baseline's manifest"
                f"{_DAMAGED}"
            )
        if self.kept is not None:
            self.kept[data] = content
        return content


# What to do about a baseline whose files are missing or damaged.
_DAMAGED = "; the baseline is damaged: push it again, or name another with --against"


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
    """
    return compare(Baseline.read(baseline), current)


def compare(baseline: Baseline, current: Path) -> Comparison:
    """Compare the build in the directory ``current`` with ``baseline``, as ``compare_builds``
    does. Raises ``BlicketError`` when the manifest or a table cannot be read."""
    after = manifest.read(current)
    tolerance = after.config.tolerance
    blicks = [
        compare_blick(entry, baseline, tolerance, _reader(current, entry.data))
        for entry in after.blicks
    ]
    return assemble(baseline, after, blicks)


def _reader(directory: Path, data: str | None) -> Callable[[], pl.DataFrame] | None:
    """What reads the table at ``data`` in ``directory``, when there is one."""
    return functools.partial(_table, directory, data) if data is not None else None


def compare_blick(
    entry: BlickEntry,
    baseline: Baseline,
    tolerance: float,
    read: Callable[[], pl.DataFrame] | None,
) -> BlickComparison:
    """Compare the current Blick ``entry`` with its counterpart in ``baseline``, as
    ``compare_builds`` does; ``read`` gives the entry's table, ``None`` when it has none, and
    ``tolerance`` is the current build's, for a Blick without one of its own. Raises
    ``BlicketError`` when a table cannot be read."""
    names = [name for name in (entry.id, *entry.aliases) if name is not None]
    found = [baseline.by_id[name] for name in names if name in baseline.by_id]
    counterpart = next((e for e in found if e.data is not None), found[0] if found else None)
    table = counterpart.data if counterpart else None
    matched = counterpart.id if counterpart and counterpart.id != entry.id else None
    if entry.status == "skipped":
        message = _absence(entry)
        if table is not None:
            return flagged(entry, "removed", message, skipped=True, matched=matched)
        there = _absence(counterpart, "in the baseline") if counterpart else "not in the baseline"
        return BlickComparison(
            id=entry.id,
            name=entry.name,
            change=Change(),
            skipped=True,
            message=f"{message} ({there})",
        )
    if entry.id is None or entry.definition is None or entry.data is None or read is None:
        return flagged(entry, "error", _cause(entry))
    if table is None:
        message = _absence(counterpart, "in the baseline") if counterpart else None
        return flagged(entry, "new", message)
    plot = entry.definition.plot
    try:
        change = builtin(plot.type).diff(baseline.table(table), read(), plot.mapping, entry.panels)
    except (ValueError, TypeError) as error:  # DefinitionError for an unknown plot type
        return flagged(entry, "error", str(error))
    if entry.definition.tolerance is not None:
        tolerance = entry.definition.tolerance
    if change.magnitude is not None and change.magnitude > tolerance:
        change = change.model_copy(update={"flags": change.flags | {"value"}})
    return BlickComparison(id=entry.id, name=entry.name, matched=matched, change=change)


def assemble(
    baseline: Baseline, current: Manifest, blicks: Sequence[BlickComparison]
) -> Comparison:
    """The comparison of the build ``current`` with ``baseline``: the comparisons of its Blicks,
    ``blicks``, then the baseline Blicks with a table that no Blick of ``current`` claims by its
    id or aliases, whatever its status, as removed, unless ``current`` is incomplete."""
    incomplete = _incomplete(current)
    removed: list[BlickComparison] = []
    if not incomplete:
        claimed = {
            name
            for entry in current.blicks
            for name in (entry.id, *entry.aliases)
            if name is not None
        }
        removed = [
            flagged(entry, "removed")
            for entry in baseline.manifest.blicks
            if entry.data is not None and entry.id not in claimed
        ]
    return Comparison(
        spec=current.spec,
        blicket=importlib.metadata.version("blicket"),
        created_at=datetime.now(UTC),
        baseline=reference(baseline.manifest),
        current=reference(current),
        incomplete=incomplete,
        blicks=(*blicks, *removed),
    )


def place_baseline(
    blick: BlickComparison,
    baseline: Baseline,
    place: Callable[[BlickComparison, BlickEntry], str],
) -> tuple[BlickComparison, BlickEntry | None]:
    """``blick`` with the baseline table it is drawn against, when it is flagged ``value`` or
    ``schema``: the table of the baseline Blick it was compared with, its ``baseline_data`` named
    by ``place``, given the Blick and that baseline Blick, its ``baseline_hash`` the table's hash
    in the baseline's manifest; and that baseline Blick, so that the caller can copy or keep its
    table. Any other Blick comes back as it is, without a baseline Blick."""
    counterpart = baseline.by_id.get(blick.matched or blick.id or "")
    if not blick.change.flags & {"value", "schema"} or counterpart is None:
        return blick, None
    if counterpart.data is None or blick.id is None:
        return blick, None
    update = {"baseline_data": place(blick, counterpart), "baseline_hash": counterpart.hash}
    return blick.model_copy(update=update), counterpart


def write(comparison: Comparison, baseline: Baseline, current: Path) -> Comparison:
    """Write ``comparison`` of the build directory ``current`` with ``baseline`` into
    ``current/compare/<baseline id>/`` and return it as written, with ``baseline_data`` and
    ``baseline_hash`` set for the copied tables, as ``place_baseline`` sets them.

    The directory is assembled next to its destination and replaces what an earlier write put
    there. ``compare/index.json`` is then regenerated from the directories in ``compare/`` that
    hold a ``comparison.json``, ordered by that file's modification time, the newest last.
    Raises ``BlicketError`` when a build id of the comparison is not shaped like one, or writing
    fails.
    """
    for build in (comparison.baseline, comparison.current):
        if not manifest.BUILD_ID.fullmatch(build.id):
            raise BlicketError(f"build {build.run} has an invalid build id {build.id!r}")
    compare = current / COMPARE
    baseline_id = comparison.baseline.id

    def copied(blick: BlickComparison) -> str:
        """Where the copy of the baseline's table of ``blick`` goes, in the comparison's
        directory."""
        return f"blicks/{blick.id}.parquet"

    def place(blick: BlickComparison, counterpart: BlickEntry) -> str:
        return f"{COMPARE}/{baseline_id}/{copied(blick)}"

    temporary = compare / f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
    blicks: list[BlickComparison] = []
    try:
        temporary.mkdir(parents=True)
        for given in comparison.blicks:
            blick, counterpart = place_baseline(given, baseline, place)
            if counterpart is not None and counterpart.data and blick.baseline_data:
                copy = temporary / copied(blick)
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(baseline.directory / counterpart.data, copy)
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


def flagged(
    entry: BlickEntry,
    flag: Flag,
    message: str | None = None,
    *,
    skipped: bool = False,
    matched: str | None = None,
) -> BlickComparison:
    """The Blick ``entry`` in a comparison, with the one flag ``flag`` and ``message``."""
    change = Change(flags=frozenset({flag}))
    return BlickComparison(
        id=entry.id,
        name=entry.name,
        matched=matched,
        change=change,
        skipped=skipped,
        message=message,
    )


def _cause(entry: BlickEntry) -> str | None:
    """The first line of the entry's first error."""
    errors = [p for p in entry.problems if p.severity == "error"]
    return first_line(errors[0].message) if errors else None


def _absence(entry: BlickEntry, where: str = "") -> str:
    """Why ``entry`` has no table: skipped, with the first line of its reason, or did not build;
    ``where`` follows the verb, such as ``in the baseline``."""
    place = f" {where}" if where else ""
    if entry.status == "skipped":
        return f"skipped{place}: {first_line(entry.skipped or '')}"
    return f"did not build{place}"


def _incomplete(built: Manifest) -> tuple[str, ...]:
    """Why the Blicks missing from ``built`` cannot be judged removed: the files that failed and
    the Blicks without a usable id."""
    reasons: list[str] = []
    for problem in built.problems:
        if problem.severity == "error":
            where = problem.source.file.as_posix() if problem.source else "the project"
            first = first_line(problem.message)
            reasons.append(
                f"{where} failed to import: {first}"
                if problem.kind == Kind.IMPORT
                else f"{where}: {first}"
            )
    reasons += [f"{entry.name} has no usable id" for entry in built.blicks if entry.id is None]
    return tuple(reasons)


def _table(directory: Path, data: str) -> pl.DataFrame:
    try:
        return pl.read_parquet(directory / data)
    except (OSError, pl.exceptions.PolarsError) as error:
        reason = "file missing" if isinstance(error, FileNotFoundError) else str(error)
        raise BlicketError(f"cannot read {data} in {directory}: {reason}") from error


def reference(built: Manifest) -> BuildRef:
    """What a comparison records of the build ``built``."""
    return BuildRef(
        id=built.build.id,
        run=built.run.id,
        profile=built.run.profile,
        created_at=built.created_at,
        repository=built.repository,
        incomplete=built.build.incomplete,
    )
