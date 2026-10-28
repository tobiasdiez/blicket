"""``blicket dev``: a check of a run that keeps the run in memory, and the session the server
answers the viewer and the Blick builder from."""

import contextlib
import dataclasses
import json
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from blicket import builder, check, dataset
from blicket.builder import Build, LoadedRun, Prepared
from blicket.check import Compared
from blicket.dataset import Found
from blicket.discovery import discover
from blicket.errors import DatasetError, Kind
from blicket.model import BlickEntry, Registry
from blicket.query import Options, Query, run_query
from blicket.report import render_check
from blicket.serve import Info

KEPT_TABLES = 50
_NO_BLICK_YET = frozenset({Kind.NO_MATCH, Kind.NO_BLICKS})


@dataclass(frozen=True)
class Current:
    """The build a session serves and its comparison, replaced as a whole, never changed, so
    that a request reads one build."""

    build: Build
    compared: Compared

    @property
    def directory(self) -> Path:
        """The build directory."""
        return self.build.path

    def manifest(self) -> bytes:
        """The manifest of the build as this session computed it, as JSON, its sources relative
        to the project root."""
        text = self.build.manifest.model_dump_json(indent=2, context={"root": self.build.root})
        return text.encode() + b"\n"


@dataclass(kw_only=True)
class Session:
    """What ``blicket dev`` keeps while it serves a run: the project as prepared and the baseline
    asked for, the run and its dataset, or why there is none, the build served with its
    comparison, and the tables of the builder's last ``KEPT_TABLES`` queries, by the sha256 of
    their Parquet bytes.

    Every query takes ``lock``, so that one at a time works on the run. With ``verbose``, the
    problems of a query go to stderr with their tracebacks.
    """

    prepared: Prepared
    against: str | None = None
    loaded: LoadedRun
    dataset: Found
    served: Current
    verbose: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    # The tables have a lock of their own, so that fetching a table never waits for a query.
    _tables: OrderedDict[str, bytes] = field(init=False, default_factory=OrderedDict)
    _tables_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    @property
    def root(self) -> Path:
        return self.prepared.root

    def current(self) -> Current:
        """The build served now, with its comparison."""
        return self.served

    def info(self) -> Info:
        """The project root, and whether there is a dataset, why not, and whether because
        ``dataset(run)`` failed."""
        return Info(
            root=str(self.root),
            dataset=self.dataset.contents is not None,
            message=self.dataset.reason,
            failed=self.dataset.error is not None,
        )

    def options(self) -> Options:
        """What the builder offers; raises ``DatasetError`` without a dataset."""
        return Options.of(self._contents())

    def query(self, query: Query) -> bytes:
        """Run a builder query and keep its table, which the entry names: the entry as JSON,
        its sources relative to the project root. Raises ``DatasetError`` without a dataset."""
        contents = self._contents()
        with self.lock:
            result = run_query(contents, query, self.root)
        if result.table is not None and result.entry.hash is not None:
            digest = result.entry.hash.removeprefix("parquet-sha256:")
            with self._tables_lock:
                self._tables[digest] = result.table
                self._tables.move_to_end(digest)
                while len(self._tables) > KEPT_TABLES:
                    self._tables.popitem(last=False)
        if self.verbose:
            _log(result.entry, query)
        return result.entry.model_dump_json(context={"root": self.root}).encode()

    def table(self, digest: str) -> bytes | None:
        """The Parquet bytes of a table of the last queries, by their sha256 in hex."""
        with self._tables_lock:
            return self._tables.get(digest)

    def _contents(self) -> dataset.Contents:
        if (contents := self.dataset.contents) is None:
            raise DatasetError(self.dataset.reason or "this project has no dataset")
        return contents


def _log(entry: BlickEntry, query: Query) -> None:
    """The problems of a query's entry on stderr, each with its traceback."""
    for problem in entry.problems:
        lines = [f"query {json.dumps(query.model_dump(mode='json'))}"]
        lines.append(f"  {problem.severity}: {problem.message}")
        if problem.traceback:
            lines.extend(f"    {line}" for line in problem.traceback.rstrip().splitlines())
        print("\n".join(lines), file=sys.stderr)


def _without_no_blick(registry: Registry) -> tuple[Registry, bool]:
    """``registry`` without the errors that say the project has no Blick, which in ``dev`` is a
    start, not an error; and whether it had them."""
    kept = tuple(
        p for p in registry.problems if not (p.kind in _NO_BLICK_YET and p.severity == "error")
    )
    return dataclasses.replace(registry, problems=kept), len(kept) < len(registry.problems)


def _builder_line(found: Found) -> str:
    """Whether the builder is on: the size of the dataset, or why it is off."""
    if (contents := found.contents) is not None:
        quantities, dimensions = len(contents.quantities), len(contents.dimensions)
        return (
            f"builder: {quantities} {'quantity' if quantities == 1 else 'quantities'}, "
            f"{dimensions} dimension{'' if dimensions == 1 else 's'}"
        )
    if found.error is not None:
        return "builder: off, dataset(run) failed; fix it and restart blicket dev"
    return f"builder: off, {found.reason}"


def start(
    root: Path,
    runs: list[Path],
    *,
    out: Path | None = None,
    against: str | None = None,
    verbose: bool = False,
) -> tuple[Session, str]:
    """Check the run at ``runs`` with the project at ``root`` as ``blicket check`` does, without
    pushing, and keep the run: the session, and the report to print before the viewer's URL.

    Unlike ``build``, a project without a Blick gets a build too. Raises ``BlicketError`` when
    the config, the viewer, a run path or the loader fails, the build cannot be written, or git
    cannot run to resolve the baseline.
    """
    prepared = builder.prepare(root, runs, out)
    registry, no_blick = _without_no_blick(discover(prepared.root, prepared.config))
    with contextlib.redirect_stdout(sys.stderr):
        loaded = builder.load(prepared)
        built = builder.write(prepared, registry, loaded)
        found = dataset.find(prepared.target, loaded.run, prepared.root)
    compared = check.compare(built, prepared.root, against)
    lines = [
        render_check(
            built,
            compared.resolution,
            compared.comparison,
            None,
            compared.warnings,
            verbose=verbose,
        )
    ]
    if no_blick:
        globs = ", ".join(prepared.config.blicks)
        lines.append(
            f"no Blicks yet ({globs} defines none); write one as code, or build one from the run "
            "in the viewer"
        )
    if found.error is not None:
        lines.append(f"warning: {found.error}")
        if verbose and found.error.traceback:
            lines.append(found.error.traceback.rstrip())
    lines.append(_builder_line(found))
    session = Session(
        prepared=prepared,
        against=against,
        loaded=loaded,
        dataset=found,
        served=Current(built, compared),
        verbose=verbose,
    )
    return session, "\n".join(lines)
