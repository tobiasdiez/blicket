"""``blicket dev``: a check of a run that keeps the run in memory, and the session the server
answers the viewer and the Blick builder from.

Started without a run, the session serves none until the viewer picks one of the folders that
``runs`` in ``[tool.blicket]`` matches; the run is then loaded, built and checked as at the start,
once per session."""

import contextlib
import dataclasses
import glob
import json
import stat
import sys
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from blicket import builder, check, dataset
from blicket.builder import Build, LoadedRun, Prepared
from blicket.check import Compared
from blicket.dataset import Found
from blicket.discovery import discover
from blicket.errors import BlicketError, DatasetError, Kind, LoadRefused
from blicket.model import BlickEntry, Registry
from blicket.query import Options, Query, run_query
from blicket.report import render_check
from blicket.serve import NO_RUN, Info, RunFolder, RunList

KEPT_TABLES = 50
_LOADING = "another run is loading; wait for it"
_SERVED = "a run is served already; reload the viewer, or restart blicket dev to pick another"
_NO_BLICK_YET = frozenset({Kind.NO_MATCH, Kind.NO_BLICKS})
_NOTHING_TO_SERVE = (
    'no run to serve; pass one (blicket RUN_PATH), or set runs = ["output/*"] in [tool.blicket] '
    "to pick one in the viewer"
)


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


@dataclass(frozen=True)
class Serving:
    """What a session serves once a run is loaded: the project as prepared for the run, the run,
    its dataset or why there is none, and the build served with its comparison, replaced as a
    whole."""

    prepared: Prepared
    loaded: LoadedRun
    dataset: Found
    served: Current


@dataclass(kw_only=True)
class Session:
    """What ``blicket dev`` keeps while it serves a run: the project as prepared at the start and
    the baseline asked for, what it serves once a run is loaded (``None`` until then), and the
    tables of the builder's last ``KEPT_TABLES`` queries, by the sha256 of their Parquet bytes.

    Every query and the load of a run picked in the viewer take ``lock``, so that one at a time
    works on the run. With ``verbose``, the problems of a query and of a run picked in the viewer
    go to stderr with their tracebacks.
    """

    prepared: Prepared
    against: str | None = None
    serving: Serving | None = None
    verbose: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    # The tables have a lock of their own, so that fetching a table never waits for a query.
    _tables: OrderedDict[str, bytes] = field(init=False, default_factory=OrderedDict)
    _tables_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    @property
    def root(self) -> Path:
        return self.prepared.root

    def current(self) -> Current | None:
        """The build served now, with its comparison; ``None`` while no run is served yet."""
        serving = self.serving
        return serving.served if serving is not None else None

    def info(self) -> Info:
        """The project root, and whether there is a dataset, why not, and whether because
        ``dataset(run)`` failed."""
        if (serving := self.serving) is None:
            return Info(root=str(self.root), dataset=False, message=NO_RUN)
        return Info(
            root=str(self.root),
            dataset=serving.dataset.contents is not None,
            message=serving.dataset.reason,
            failed=serving.dataset.error is not None,
        )

    def runs(self) -> RunList:
        """The folders that ``runs`` in ``[tool.blicket]`` matches now, newest first."""
        patterns = self.prepared.config.runs
        return RunList(patterns=patterns, runs=find_runs(self.root, patterns))

    def load(self, paths: Sequence[str]) -> str:
        """Load the run at ``paths``, build and check it as ``start`` does, and serve it; the
        run's id. The time and the paths go to stdout first, then the report ``start`` gives,
        or the error to stderr, with its traceback under ``verbose``.

        Raises ``LoadRefused`` while another load runs and once a run is served, and another
        ``BlicketError`` when a path does not exist, or the loader, the build or the baseline
        fails.
        """
        if not self.lock.acquire(blocking=False):
            raise LoadRefused(_SERVED if self.serving is not None else _LOADING)
        try:
            if self.serving is not None:
                raise LoadRefused(_SERVED)
            named = ", ".join(paths)
            try:
                resolved, shown = builder.run_paths(self.root, paths)
                named = ", ".join(shown)
                print(
                    f"{datetime.now():%H:%M:%S} loading {named}, picked in the viewer", flush=True
                )
                prepared = dataclasses.replace(self.prepared, paths=resolved, shown=shown)
                serving, report = _serve(prepared, self.against, self.verbose)
            except BlicketError as error:
                print(f"error: cannot load {named}: {error}", file=sys.stderr, flush=True)
                if self.verbose and error.traceback:
                    print(error.traceback.rstrip(), file=sys.stderr, flush=True)
                raise
            self.serving = serving
            print(report, flush=True)
            return serving.served.build.manifest.run.id
        finally:
            self.lock.release()

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
        if (serving := self.serving) is None:
            raise DatasetError(NO_RUN)
        if (contents := serving.dataset.contents) is None:
            raise DatasetError(serving.dataset.reason or "this project has no dataset")
        return contents


def find_runs(root: Path, patterns: Sequence[str]) -> list[RunFolder]:
    """The folders the globs ``patterns`` match, relative to ``root`` (``..`` allowed), newest
    change first, then by name, each named as it was matched, a link by its own name; files and
    hidden folders are left out, and a folder matched twice, by two patterns or through a link,
    is listed once."""
    found: dict[Path, RunFolder] = {}
    for pattern in patterns:
        for match in glob.glob(pattern, root_dir=root, recursive=True):
            name, path = Path(match).name, (root / match).resolve()
            if not name or name.startswith(".") or path in found:
                continue
            try:
                status = path.stat()
            except OSError:  # gone since the glob
                continue
            if stat.S_ISDIR(status.st_mode):
                modified = datetime.fromtimestamp(status.st_mtime, UTC).replace(microsecond=0)
                found[path] = RunFolder(path=path, name=name, modified=modified)
    return sorted(found.values(), key=lambda run: (-run.modified.timestamp(), run.name))


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

    Unlike ``build``, a project without a Blick gets a build too. Without ``runs``, the session
    serves no run until one is picked in the viewer, and the report says how many folders
    ``runs`` in ``[tool.blicket]`` matches. Raises ``BlicketError`` when the config, the viewer, a
    run path or the loader fails, the build cannot be written, or git cannot run to resolve the
    baseline, and without ``runs`` when ``[tool.blicket]`` has no ``runs`` either.
    """
    prepared = builder.prepare(root, runs, out)
    session = Session(prepared=prepared, against=against, verbose=verbose)
    if runs:
        session.serving, report = _serve(prepared, against, verbose)
        return session, report
    if not (patterns := prepared.config.runs):
        raise BlicketError(_NOTHING_TO_SERVE)
    count = len(session.runs().runs)
    return session, f"runs: {count or 'none yet'} in {', '.join(patterns)}"


def _serve(prepared: Prepared, against: str | None, verbose: bool) -> tuple[Serving, str]:
    """Load, build and check the run ``prepared`` names: what a session serves of it, and the
    report. What project code prints goes to stderr."""
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
    return Serving(prepared, loaded, found, Current(built, compared)), "\n".join(lines)
