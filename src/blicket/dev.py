"""``blicket dev``: the session the server answers the viewer and the Blick builder from, which
keeps the run in memory and builds its Blicks while the viewer is open.

Started without a run, the session serves none until the viewer picks one of the folders that
``runs`` in ``[tool.blicket]`` matches, or the project itself when ``runs`` has ``.``. A run
picked while another is served is loaded in its place. Every run is served at once, as an
``OnDemandRun``, whose Blicks the session's one ``Worker`` builds, the cheap ones in the
background and a Blick a page asks for before them; nothing is written to disk.
"""

import contextlib
import dataclasses
import glob
import json
import secrets
import stat
import sys
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from blicket import builder, dataset, jobs, tables
from blicket.builder import Prepared
from blicket.dataset import Found
from blicket.discovery import discover
from blicket.errors import BlicketError, DatasetError, Kind, LoadRefused
from blicket.jobs import OnDemandRun, RunLock, Terminal, Worker
from blicket.model import BlickEntry, Registry
from blicket.query import Options, Query, run_query
from blicket.serve import NO_RUN, BuildState, Info, RunFolder, RunList, Served

KEPT_TABLES = 50
PROJECT = "This project"
_NO_BLICK_YET = frozenset({Kind.NO_MATCH, Kind.NO_BLICKS})
_NOTHING_TO_SERVE = (
    'no run to serve; pass one (blicket RUN_PATH), or set runs = ["output/*"] in [tool.blicket] '
    'to pick one in the viewer, or "." for the project itself'
)
_NO_OUT = "--out is not used: blicket dev writes no build directory"
_BUSY = "{}; load the run once it is built"


def _new_id() -> str:
    """A session's id: 16 random hex digits, the shape of a build id."""
    return secrets.token_hex(8)


@dataclass(kw_only=True)
class Session:
    """What ``blicket dev`` keeps while it serves a run: the project as prepared at the start and
    the baseline asked for, the ``worker`` that builds the Blicks of the run served, and the tables
    of the builder's last ``KEPT_TABLES`` queries, by the sha256 of their Parquet bytes. ``id``
    names the session, for a client to learn of a restart; the load of another run gives the
    session another. Its lines, and its tracebacks under ``verbose``, go to ``terminal``.

    Every query, the load of a run and each job of the worker take ``lock``, so that one at a
    time works on the run. A run's own ``Prepared`` holds its paths; the session's holds what is
    the project's: the root, the config and the viewer.
    """

    prepared: Prepared
    against: str | None = None
    terminal: Terminal = field(default_factory=Terminal)
    lock: RunLock = field(default_factory=RunLock)
    id: str = field(default_factory=_new_id)
    worker: Worker = field(init=False)
    # The tables have a lock of their own, so that fetching a table never waits for a query.
    _tables: OrderedDict[str, bytes] = field(init=False, default_factory=OrderedDict)
    _tables_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.worker = Worker(self.lock, self.terminal)

    @property
    def root(self) -> Path:
        return self.prepared.root

    @property
    def verbose(self) -> bool:
        """Whether the session says tracebacks too."""
        return self.terminal.verbose

    @verbose.setter
    def verbose(self, verbose: bool) -> None:
        self.terminal.verbose = verbose

    @property
    def serving(self) -> OnDemandRun | None:
        """The run served, ``None`` until one is."""
        return self.worker.run

    def current(self) -> Served | None:
        """What the run serves now; ``None`` while no run is served yet."""
        return run.current() if (run := self.serving) is not None else None

    def begin(self) -> None:
        """Start the worker, which builds the background of the run served, if any."""
        self.worker.begin()

    def info(self) -> Info:
        """The project root, whether there is a dataset, why not, and whether because
        ``dataset(run)`` failed; the revision, the Blick building and the Blicks a page asked for
        that wait, and why the worker stopped, if it did."""
        status = self.worker.status()
        found = run.dataset if (run := self.serving) is not None else None
        return Info(
            root=str(self.root),
            dataset=found is not None and found.contents is not None,
            message=found.reason if found is not None else NO_RUN,
            failed=found is not None and found.error is not None,
            session=self.id,
            revision=status.revision,
            jobs=status.jobs,
            stopped=status.stopped,
        )

    def runs(self) -> RunList:
        """The folders that ``runs`` in ``[tool.blicket]`` matches now, the project itself first,
        then newest first, the one the run served was loaded from marked ``served``."""
        patterns = self.prepared.config.runs
        served = set(run.prepared.paths) if (run := self.serving) is not None else set()
        found = [
            folder.model_copy(update={"served": folder.path in served})
            for folder in find_runs(self.root, patterns)
        ]
        return RunList(patterns=patterns, runs=found)

    def load(self, paths: Sequence[str]) -> str:
        """Load the run at ``paths`` and serve it in place of the run served, if any; the run's
        id. The load waits for the cheap build that holds the session's lock, if one does, and
        the worker takes no job while it waits or runs. The time and the paths, the project
        itself as ``this project``, go to stdout first, then the report ``start`` gives, or the
        error to stderr, with its traceback under ``verbose``. The session drops what it built of
        the run before, takes a new id, and the worker starts on the background of the new run
        once its report is printed.

        Raises ``LoadRefused`` while another load runs or an expensive Blick builds, and once the
        worker stopped, which would build nothing of the run; and another ``BlicketError`` when a
        path does not exist, or the loader or the baseline fails, which leaves the run served as
        it was.
        """
        if (stopped := self.worker.stopped) is not None:
            raise LoadRefused(jobs.STOPPED.format(stopped))
        try:
            return self._load(paths)
        finally:
            self.worker.wake()  # it took no job while the load waited or ran

    def _load(self, paths: Sequence[str]) -> str:
        """Load the run at ``paths``, as ``load`` says."""
        say = self.terminal.say
        with self.lock.load(self._busy):
            named = ", ".join(paths)
            try:
                resolved, shown = builder.run_paths(self.root, paths)
                named = "this project" if resolved == (self.root,) else ", ".join(shown)
                say(f"{datetime.now():%H:%M:%S} loading {named}, picked in the viewer")
                prepared = dataclasses.replace(self.prepared, paths=resolved, shown=shown)
                session = _new_id()
                run, report = _serve(prepared, self, session, self.worker.revision + 1)
            except BlicketError as error:
                say(f"error: cannot load {named}: {error}", err=True)
                if self.verbose and error.traceback:
                    say(error.traceback.rstrip(), err=True)
                raise
            with self._tables_lock:
                self._tables.clear()
            self.worker.serve(run)
            self.id = session
            say(report)
            self.worker.begin()
            return run.loaded.info.id

    def build(self, blick: str, rebuild: bool = False) -> BuildState:
        """Ask the worker for the Blick ``blick``, once more with ``rebuild``; its state, as
        ``Worker.request`` gives it. Raises ``NoSuchBlick`` while no run is served and for an id
        the run cannot build, and ``Refused`` while a run loads and once the worker stopped."""
        return self.worker.request(blick, rebuild)

    def options(self) -> Options:
        """What the builder offers; raises ``DatasetError`` without a dataset."""
        return Options.of(self._contents())

    def query(self, query: Query) -> bytes:
        """Run a builder query, after the cheap build that holds the session's lock, if one does,
        and keep its table, which the entry names: the entry as JSON, its sources relative to the
        project root. Raises ``DatasetError`` without a dataset, and ``Refused`` while an
        expensive Blick builds or a run loads."""
        with self.lock.query():
            result = run_query(self._contents(), query, self.root)
        if result.table is not None and result.entry.hash is not None:
            digest = tables.digest_of(result.entry.hash)
            with self._tables_lock:
                self._tables[digest] = result.table
                self._tables.move_to_end(digest)
                while len(self._tables) > KEPT_TABLES:
                    self._tables.popitem(last=False)
        if self.verbose:
            self._log(result.entry, query)
        return result.entry.model_dump_json(context={"root": self.root}).encode()

    def table(self, digest: str) -> bytes | None:
        """The Parquet bytes of a table of the last queries, or of the run, by their sha256 in
        hex."""
        with self._tables_lock:
            found = self._tables.get(digest)
        if found is None and (served := self.current()) is not None:
            return served.tables.get(digest)
        return found

    def _contents(self) -> dataset.Contents:
        if (run := self.serving) is None:
            raise DatasetError(NO_RUN)
        if (contents := (found := run.dataset).contents) is None:
            raise DatasetError(found.reason or "this project has no dataset")
        return contents

    def _busy(self) -> str:
        """Why a load is refused while the expensive Blick builds: which one, and for how
        long."""
        building = self.worker.expensive_building()
        return _BUSY.format(building or "an expensive Blick is building")

    def _log(self, entry: BlickEntry, query: Query) -> None:
        """The problems of a query's entry on stderr, each with its traceback."""
        for problem in entry.problems:
            lines = [f"query {json.dumps(query.model_dump(mode='json'))}"]
            lines.append(f"  {problem.severity}: {problem.message}")
            if problem.traceback:
                lines.extend(f"    {line}" for line in problem.traceback.rstrip().splitlines())
            self.terminal.say("\n".join(lines), err=True)


def find_runs(root: Path, patterns: Sequence[str]) -> list[RunFolder]:
    """The folders the globs ``patterns`` match, relative to ``root`` (``..`` allowed): the
    project itself first, when a glob matches ``root``, such as ``.``, then the others newest
    change first, then by name, each named as it was matched, a link by its own name; files and
    hidden folders are left out, and a folder matched twice, by two patterns or through a link,
    is listed once."""
    found: dict[Path, RunFolder] = {}
    for pattern in patterns:
        for match in glob.glob(pattern, root_dir=root, recursive=True):
            name, path = Path(match).name, (root / match).resolve()
            if path in found:
                continue
            if path == root:
                found[path] = RunFolder(path=path, name=PROJECT, modified=None, project=True)
                continue
            if not name or name.startswith("."):
                continue
            try:
                status = path.stat()
            except OSError:  # gone since the glob
                continue
            if stat.S_ISDIR(status.st_mode):
                modified = datetime.fromtimestamp(status.st_mtime, UTC).replace(microsecond=0)
                found[path] = RunFolder(path=path, name=name, modified=modified)
    return sorted(
        found.values(),
        key=lambda run: (
            not run.project,
            -run.modified.timestamp() if run.modified else 0,
            run.name,
        ),
    )


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
    """Load the run at ``runs`` with the project at ``root``, find its baseline and serve it,
    building nothing yet: the session, and the report to print before the viewer's URL, after
    which ``Session.begin`` starts the worker on the background. ``out`` is not used, since
    nothing is written, which a line on stderr says.

    A project without a Blick gets a session too. Without ``runs``, the session serves no run
    until one is picked in the viewer, and the report says how many folders ``runs`` in
    ``[tool.blicket]`` matches. Raises ``BlicketError`` when the config, the viewer, a run path
    or the loader fails, or git cannot run to resolve the baseline, and without ``runs`` when
    ``[tool.blicket]`` has no ``runs`` either.
    """
    prepared = builder.prepare(root, runs, out)
    session = Session(prepared=prepared, against=against, terminal=Terminal(verbose=verbose))
    if out is not None:
        session.terminal.say(_NO_OUT, err=True)
    if runs:
        run, report = _serve(prepared, session, session.id, 0)
        session.worker.serve(run)
        return session, report
    if not (patterns := prepared.config.runs):
        raise BlicketError(_NOTHING_TO_SERVE)
    count = len(session.runs().runs)
    return session, f"runs: {count or 'none yet'} in {', '.join(patterns)}"


def _serve(
    prepared: Prepared, session: Session, session_id: str, revision: int
) -> tuple[OnDemandRun, str]:
    """Load the run ``prepared`` names and find its baseline: the run ``session`` serves of it,
    as the session ``session_id`` at ``revision``, and the report. What project code prints goes
    to stderr."""
    registry, no_blick = _without_no_blick(discover(prepared.root, prepared.config))
    with contextlib.redirect_stdout(sys.stderr):
        loaded = builder.load(prepared)
        found = dataset.find(prepared.target, loaded.run, prepared.root)
    run, report = jobs.start(
        prepared,
        registry,
        loaded,
        found,
        session=session_id,
        terminal=session.terminal,
        revision=revision,
        against=session.against,
    )
    lines = [report]
    if no_blick:
        globs = ", ".join(prepared.config.blicks)
        lines.append(
            f"no Blicks yet ({globs} defines none); write one as code, or build one from the run "
            "in the viewer"
        )
    return run, "\n".join([*lines, *_dataset_lines(found, session.verbose)])


def _dataset_lines(found: Found, verbose: bool) -> list[str]:
    """The lines of the report about the dataset: the failure of ``dataset(run)``, with its
    traceback under ``verbose``, and whether the builder is on."""
    lines: list[str] = []
    if found.error is not None:
        lines.append(f"warning: {found.error}")
        if verbose and found.error.traceback:
            lines.append(found.error.traceback.rstrip())
    return [*lines, _builder_line(found)]
