"""The builds of a ``blicket dev`` session: the run it serves, whose Blicks one worker builds one
at a time while the viewer is open, a cheap Blick in the background and again whenever its page
asks, an expensive one when its page asks.

The session writes no build directory. ``OnDemandRun`` is the run served: it starts from the
manifest of the run with every Blick ``pending``, builds a Blick and compares it when a job asks,
and swaps in each Blick built as a new snapshot, a ``serve.Served``: the manifest, the comparison
of the Blicks built so far with the baseline, which is found once, when the run is loaded, and the
tables by their sha256, those of the Blicks and of the baseline they are drawn against, which a
comparison reads and checks against the baseline's manifest. A snapshot also holds the tables of
the ``KEPT`` snapshots before it, so that a table that a manifest of a few builds ago names is
still there for the requests made from it.

``Worker`` is the session's one worker thread, for the session's lifetime. Its jobs are
``Task``s: ``Build``, in one list ranked by what asked for them: the cheap Blicks a page asked for,
then the expensive ones a page asked for, then the background, the cheap Blicks not built yet in
the order ``blicket list`` shows them, each in the order queued and each Blick in the list once at
most. A job running is never interrupted. The worker holds the session's ``RunLock`` for the whole
of a job, so that a load, which replaces the run and clears the list, comes between two jobs, and
nothing of the run before is built, printed or published after it; while a load holds or waits
for the lock, the worker takes no job. It prints a line for each
Blick a page asked for, through the session's ``Terminal``, and once every cheap Blick is built,
the counts, the build problems and the comparison of ``check``'s report of the Blicks built so
far. Whatever a build raises becomes the Blick's error, whatever comparing it raises its
comparison's error, and the worker goes on; nothing that writing a line raises costs a build.
"""

import contextlib
import dataclasses
import functools
import io
import os
import sys
import threading
import time
import traceback
from collections import ChainMap, deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TextIO

import polars as pl

from blicket import builder, check, comparison, serve, tables
from blicket.builder import LoadedRun, Prepared
from blicket.comparison import Baseline, BlickComparison
from blicket.dataset import Found
from blicket.errors import (
    NOWHERE,
    BlicketError,
    Kind,
    LoadRefused,
    NoSuchBlick,
    Refused,
    first_line,
    raised,
)
from blicket.manifest import Manifest
from blicket.model import Blick, BlickEntry, Registry
from blicket.query import TABLES
from blicket.report import render_session_build, render_session_report, render_session_start
from blicket.serve import BuildState, Served

KEPT = 8  # how many snapshots before the current one a table is kept for
STOPPED = "the worker that builds the Blicks stopped ({}); restart blicket dev"
_BUILDING = "an expensive Blick is building; run the query again when it is built"
_QUERY_LOADING = "a run is loading; run the query again once it is loaded"
_BUILD_LOADING = "a run is loading; ask for the Blick again once it is loaded"
_LOADING = "another run is loading; wait for it"
# The ranks of the jobs: what asked for them, in the order they are built.
_CHEAP, _EXPENSIVE, _BACKGROUND = 0, 1, 2

type _Holder = Literal["query", "load", "cheap", "expensive"]


class Terminal:
    """Where a session of ``blicket dev`` writes its lines: ``out``, the stdout the session
    started with, and ``err``, stderr, where what project code prints goes too; with ``verbose``,
    the tracebacks as well. Nothing about these lines costs a build or a load: a stream that fails
    gets nothing more, and a line that cannot be written is left out (see ``say``)."""

    def __init__(
        self, out: TextIO | None = None, err: TextIO | None = None, *, verbose: bool = False
    ) -> None:
        self.out = sys.stdout if out is None else out
        self.err: TextIO | None = sys.stderr if err is None else err
        self.verbose = verbose
        # The streams that failed otherwise than by an OSError, which was said once.
        self._failed: set[str] = set()

    def say(self, line: str | Callable[[], str], *, err: bool = False) -> None:
        """Write the line ``line`` is, or renders, to ``out``, or with ``err`` to ``err``, so that
        nothing about it raises (see ``_write``); a line that cannot be rendered is said on
        ``err`` with its traceback, if it can be, and left out."""
        try:
            text = line if isinstance(line, str) else line()
        except Exception:
            self._complain("cannot render a line of the session")
            return
        self._write(text, err=err)

    def _write(self, text: str, *, err: bool) -> None:
        """Write ``text`` as a line to ``out``, or with ``err`` to ``err``. A stream that raises
        an ``OSError``, a reader that went away, as ``head`` does, or a full disk, gets nothing
        more, and the file descriptor under it, if it has one, writes to /dev/null from then on,
        so that what project code prints there and the exit do not fail on it either. Anything
        else, such as a line the stream cannot encode, leaves that line out and the stream in
        use, and is said once per stream."""
        stream = self.err if err else self.out
        if stream is None:
            return
        try:
            print(text, file=stream, flush=True)
        except OSError:
            if err:
                self.err = None
            else:
                self.out = None
            _to_null(stream)
        except Exception:
            name = "stderr" if err else "stdout"
            if name not in self._failed:
                self._failed.add(name)
                self._complain(f"cannot write a line of the session to {name}")

    def _complain(self, what: str) -> None:
        """Say on ``err`` that blicket ``what``, with the traceback being handled, if it can."""
        details = traceback.format_exc().rstrip()
        with contextlib.suppress(Exception):
            if self.err is not None:
                print(f"error: blicket {what}\n{details}", file=self.err, flush=True)


def _to_null(stream: TextIO) -> None:
    """Point the file descriptor under ``stream``, if it has one, at /dev/null."""
    with contextlib.suppress(OSError, ValueError):
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, stream.fileno())
        finally:
            os.close(null)


class _Busy(Exception):
    """What holds the lock refuses what waits for it: an expensive build, or a load."""

    def __init__(self, holder: _Holder) -> None:
        super().__init__(holder)
        self.holder = holder


class RunLock:
    """The lock on the run of a ``blicket dev`` session: one builder query, load or job works on
    the run at a time, since blicket does not ask a run object to be thread-safe.

    A query or a load waits while another one or a cheap build holds the lock, and is refused
    while an expensive build holds it, which may take minutes, rather than wait in the request; a
    query is refused while a load holds or waits for the lock too, since the loader may take
    minutes as well, and replaces the dataset. A job takes the lock once nothing holds it and no
    query or load waits for it, so that a query that waits goes before the next job and the
    builder answers while the background builds."""

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._holder: _Holder | None = None
        self._waiting = 0  # the queries and loads that wait for the lock
        self._loading = False  # a load holds the lock or waits for it

    @property
    def loading(self) -> bool:
        """Whether a load holds the lock or waits for it."""
        # Lock order: the worker takes its condition before this one; this lock never calls the
        # worker, so that the two cannot deadlock.
        with self._changed:
            return self._loading

    @contextlib.contextmanager
    def query(self) -> Generator[None]:
        """Hold the lock for a builder query; raises ``Refused`` while an expensive build or a
        load holds it, also once the query waited for another, and while a load waits for it."""
        with self._changed:
            if self._loading:
                raise Refused(_QUERY_LOADING)
        try:
            with self._hold("query"):
                yield
        except _Busy as busy:
            raise Refused(_QUERY_LOADING if busy.holder == "load" else _BUILDING) from None

    @contextlib.contextmanager
    def load(self, busy: Callable[[], str]) -> Generator[None]:
        """Hold the lock for the load of a run; raises ``LoadRefused`` while another load holds
        or waits for it, and, with the message ``busy`` gives, while an expensive build holds
        it."""
        with self._changed:
            if self._loading:
                raise LoadRefused(_LOADING)
            self._loading = True
        try:
            with self._hold("load"):
                yield
        except _Busy:
            raise LoadRefused(busy()) from None
        finally:
            with self._changed:
                self._loading = False

    @contextlib.contextmanager
    def build(self, expensive: bool) -> Generator[None]:
        """Hold the lock for a job, once nothing holds it and no query or load waits for it."""
        with self._changed:
            while self._holder is not None or self._waiting:
                self._changed.wait()
            self._holder = "expensive" if expensive else "cheap"
        try:
            yield
        finally:
            self._release()

    @contextlib.contextmanager
    def _hold(self, holder: _Holder) -> Generator[None]:
        """Hold the lock for ``holder``, a query or a load, after what holds it; raises ``_Busy``
        while an expensive build holds it, and, for a query, while a load does."""
        with self._changed:
            self._waiting += 1
            try:
                while (held := self._holder) is not None:
                    if held == "expensive" or (holder == "query" and held == "load"):
                        raise _Busy(held)
                    self._changed.wait()
                self._holder = holder
            finally:
                self._waiting -= 1
                self._changed.notify_all()  # a job that waits for the queries looks again
        try:
            yield
        finally:
            self._release()

    def _release(self) -> None:
        with self._changed:
            self._holder = None
            self._changed.notify_all()


@dataclass(frozen=True)
class Progress:
    """What ``dev/info`` says of the jobs of a session: the revision of what it serves, the Blick
    building and the Blicks a page asked for that wait, and why the worker that builds them
    stopped, if it did."""

    revision: int = 0
    jobs: tuple[serve.Job, ...] = ()
    stopped: str | None = None


@dataclass(frozen=True)
class Build:
    """A job of the worker: build the Blick ``blick`` of the run served."""

    blick: str


# What the worker can be asked to do.
type Task = Build


@dataclass(frozen=True, eq=False)
class _Queued:
    """A job in the worker's list: its task, the run it is for, its rank (see ``_CHEAP``), and
    when it was queued, or, once it runs, when it started."""

    task: Task
    run: OnDemandRun
    rank: int
    since: datetime

    @property
    def asked(self) -> bool:
        """Whether a page asked for it, not the background."""
        return self.rank != _BACKGROUND

    @property
    def expensive(self) -> bool:
        return self.task.blick in self.run.expensive


@dataclass(frozen=True)
class _Built:
    """A Blick built: its entry, its comparison with the baseline, ``None`` without one, and the
    tables it serves by their sha256 in hex, its own and the baseline's it is drawn against."""

    entry: BlickEntry
    compared: BlickComparison | None
    tables: tuple[tuple[str, bytes], ...] = ()


def _served_at(digest: str) -> str:
    """Where a session serves a table: by its content, as the builder's tables are."""
    return f"{TABLES}/{digest}.parquet"


def _in_session(blick: Blick, digest: str) -> str:
    """Where a session serves the table of ``blick``."""
    return _served_at(digest)


def _baseline_at(blick: BlickComparison, counterpart: BlickEntry) -> str:
    """Where a session serves the baseline's table of a Blick flagged ``value`` or ``schema``."""
    return _served_at(tables.digest_of(counterpart.hash or ""))


def stamped(entry: BlickEntry, expensive: frozenset[str], *, pending: bool = False) -> BlickEntry:
    """``entry`` with what only the manifest of a session says of it: whether it is ``pending``,
    and whether it is among the ``expensive`` Blicks."""
    costly = entry.id is not None and entry.id in expensive
    return entry.model_copy(update={"pending": pending, "expensive": costly})


@dataclass(kw_only=True, eq=False)
class OnDemandRun:
    """The run a ``blicket dev`` session serves: the project as prepared for it, the Blicks, the
    run, its dataset or why there is none, the manifest with every Blick ``pending``, ``initial``,
    the baseline found when it was loaded, ``None`` without one, and the ids of its expensive
    Blicks; and the Blicks built so far, which ``current`` serves, at first as the snapshot
    ``first_revision``, then one revision higher at each Blick published. ``build`` builds and
    compares one Blick, ``publish`` serves it; the session's worker calls both, holding the
    session's lock. With the terminal's ``verbose``, what comparing a Blick raised is said on its
    stderr with the traceback."""

    prepared: Prepared
    registry: Registry
    loaded: LoadedRun
    dataset: Found
    initial: Manifest
    baseline: Baseline | None
    expensive: frozenset[str] = frozenset()
    terminal: Terminal = field(default_factory=Terminal)
    first_revision: int = 0
    # The Blicks built, by id; and the comparisons of the Blicks the session does not build,
    # whose definitions are invalid, by their place in the manifest.
    _built: dict[str, _Built] = field(init=False, default_factory=dict)
    _fixed: dict[int, BlickComparison] = field(init=False, default_factory=dict)
    # The tables of the last snapshots, the current one's first.
    _kept: deque[dict[str, bytes]] = field(
        init=False, default_factory=lambda: deque(maxlen=KEPT + 1)
    )
    _served: Served = field(init=False)

    def __post_init__(self) -> None:
        if (baseline := self.baseline) is not None:
            tolerance = self.prepared.config.tolerance
            self._fixed = {
                place: comparison.compare_blick(entry, baseline, tolerance, None)
                for place, entry in enumerate(self.initial.blicks)
                if entry.status != "pending"
            }
        self._serve(self.first_revision)

    @property
    def cheap(self) -> list[str]:
        """The ids of the cheap Blicks, in the order ``blicket list`` shows them."""
        groups = {name: place for place, name in enumerate(self.registry.groups)}
        listed = sorted(
            self.registry.blicks.values(),
            key=lambda blick: (groups.get(blick.group, len(groups)), blick.source or NOWHERE),
        )
        return [blick.id for blick in listed if blick.id not in self.expensive]

    def current(self) -> Served:
        """What the run serves now."""
        return self._served

    def is_built(self, blick: str) -> bool:
        """Whether the Blick ``blick`` was built, whether it failed or skipped the run."""
        return blick in self._built

    def build(self, blick_id: str) -> _Built:
        """Build the Blick ``blick_id`` and compare it, what project code prints going to stderr.
        Whatever raises, a ``BaseException`` that a transformation lets through too, makes the
        entry an error."""
        blick = self.registry.blicks[blick_id]
        started = time.perf_counter()
        try:
            with contextlib.redirect_stdout(sys.stderr):
                entry, table = builder.run_blick(
                    blick, self.loaded.run, self.prepared.root, _in_session
                )
        except BaseException as error:
            message = f"building the Blick raised {raised(error)}"
            problem = blick.problem(Kind.BUILD, message, traceback=traceback.format_exc())
            milliseconds = round((time.perf_counter() - started) * 1000, 1)
            entry = stamped(
                blick.entry(problems=(problem,), timing_ms=milliseconds), self.expensive
            )
            # As compare_blick flags a Blick in error, without asking it, which may have raised.
            failed = comparison.flagged(entry, "error", first_line(message))
            return _Built(entry, failed if self.baseline is not None else None)
        return self._compare(stamped(entry, self.expensive), table)

    def publish(self, built: _Built) -> None:
        """Serve ``built`` in place of what its Blick was, as the next snapshot; only the
        session's worker calls it."""
        self._built[built.entry.id or ""] = built
        self._serve(self._served.revision + 1)

    def _compare(self, entry: BlickEntry, table: bytes | None) -> _Built:
        """``entry`` with its ``table`` built, compared with the baseline as ``compare_builds``
        compares it, with the baseline's table of a Blick flagged ``value`` or ``schema``, read
        from the store once and checked against its hash; flagged ``error`` when a table cannot
        be read, or comparing raises, which leaves the entry and its table as they were built.
        Bytes the run keeps already are kept once."""
        own: tuple[tuple[str, bytes], ...] = ()
        if table and entry.hash:
            digest = tables.digest_of(entry.hash)
            own = ((digest, self._kept_once(digest, table)),)
        if (baseline := self.baseline) is None:
            return _Built(entry, None, own)

        def read() -> pl.DataFrame:
            return pl.read_parquet(io.BytesIO(table or b""))

        try:
            compared = comparison.compare_blick(
                entry, baseline, self.prepared.config.tolerance, read if table else None
            )
            compared, counterpart = comparison.place_baseline(compared, baseline, _baseline_at)
            if counterpart is None or counterpart.hash is None:
                return _Built(entry, compared, own)
            content = baseline.content(counterpart)
        except BlicketError as error:
            return _Built(entry, comparison.flagged(entry, "error", str(error)), own)
        except Exception as error:  # a bug in a plot type's diff, or in what reads the tables
            message = first_line(f"comparing raised {raised(error)}")
            if self.terminal.verbose:
                details = traceback.format_exc().rstrip()
                self.terminal.say(f"comparing {entry.name} raised\n{details}", err=True)
            return _Built(entry, comparison.flagged(entry, "error", message), own)
        return _Built(entry, compared, (*own, (tables.digest_of(counterpart.hash), content)))

    def _kept_once(self, digest: str, content: bytes) -> bytes:
        """``content``, or the bytes of the same digest that a snapshot keeps already, so that a
        table built again unchanged is kept once; only the worker changes what is kept."""
        for kept in self._kept:
            if (same := kept.get(digest)) is not None:
                return same
        return content

    def _serve(self, revision: int) -> None:
        """Serve the Blicks built now as the snapshot ``revision``, with the tables of the
        ``KEPT`` snapshots before."""
        blicks = tuple(
            self._built[entry.id].entry
            if entry.status == "pending" and entry.id in self._built
            else entry
            for entry in self.initial.blicks
        )
        built = self.initial.model_copy(update={"blicks": blicks})
        compared = None
        if self.baseline is not None:
            judged: list[BlickComparison] = []
            for place, entry in enumerate(blicks):
                if place in self._fixed:
                    judged.append(self._fixed[place])
                elif entry.id in self._built and (done := self._built[entry.id].compared):
                    judged.append(done)
            compared = comparison.assemble(self.baseline, built, judged)
        self._kept.appendleft(
            {digest: content for done in self._built.values() for digest, content in done.tables}
        )
        root = self.prepared.root
        self._served = Served(built, root, compared, ChainMap(*self._kept), revision)


class Worker:
    """The one worker thread of a ``blicket dev`` session, for the session's lifetime, and its
    jobs: the run served, ``None`` until one is, whose snapshot says the revision of what is
    served, the list of jobs, ranked, the job running, and why the thread stopped, if it did.
    ``serve`` replaces the run, its jobs and the job waiting for the lock with those of another,
    the background queued; ``begin`` starts the thread, as the first request does. Each job holds
    ``lock``, the session's, from before its first line to after its last; while a load holds or
    waits for that lock, the thread takes no job, and a request is refused. The lines go to
    ``terminal``."""

    def __init__(self, lock: RunLock, terminal: Terminal) -> None:
        self.lock = lock
        self.terminal = terminal
        self._changed = threading.Condition()
        self._run: OnDemandRun | None = None
        self._queue: list[_Queued] = []
        self._building: _Queued | None = None
        # Whether the report of the background is printed, or is to be; and whether it is being.
        self._reported = True
        self._reporting = False
        self._thread: threading.Thread | None = None
        self._stopped: str | None = None

    @property
    def run(self) -> OnDemandRun | None:
        """The run served, ``None`` until one is."""
        with self._changed:
            return self._run

    @property
    def revision(self) -> int:
        """The revision of what is served now, as the run's snapshot says it; 0 before a run is
        served."""
        with self._changed:
            return self._revision_now()

    @property
    def stopped(self) -> str | None:
        """Why the thread stopped, if it did."""
        with self._changed:
            return self._stopped

    def serve(self, run: OnDemandRun) -> None:
        """Serve ``run`` in place of the run served, if any, with its cheap Blicks queued as the
        background; the jobs of the run before, the one waiting for the lock too, are dropped.
        The run's first snapshot is above any served before. Called by a load holding the
        session's lock, or before the worker begins."""
        with self._changed:
            now = datetime.now(UTC)
            self._run = run
            self._queue = [_Queued(Build(blick), run, _BACKGROUND, now) for blick in run.cheap]
            self._building = None
            self._reported, self._reporting = not self._queue, False
            self._changed.notify_all()

    def wake(self) -> None:
        """Look again for a job, as once a load ended."""
        with self._changed:
            self._changed.notify_all()

    def begin(self) -> None:
        """Start the thread unless it runs."""
        with self._changed:
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, name="blicket-jobs", daemon=True)
                self._thread.start()

    def status(self) -> Progress:
        """The revision of what is served, the Blick building, then those a page asked for that
        wait, in the order they are built, and why the worker stopped, if it did, read at one
        moment."""
        with self._changed:
            now = datetime.now(UTC)
            jobs: list[tuple[_Queued, Literal["building", "queued"]]] = []
            if self._building is not None:
                jobs.append((self._building, "building"))
            jobs += [(job, "queued") for job in self._queue if job.asked]
            return Progress(
                revision=self._revision_now(),
                jobs=tuple(
                    serve.Job(
                        id=job.task.blick,
                        state=state,
                        asked=job.asked,
                        since=job.since,
                        seconds=round((now - job.since).total_seconds(), 1),
                    )
                    for job, state in jobs
                ),
                stopped=self._stopped,
            )

    def expensive_building(self) -> str | None:
        """That an expensive Blick builds, by its title, and for how long, as ``Cement trade is
        building (12:03)``; ``None`` while none builds."""
        with self._changed:
            job = self._building
        if job is None or not job.expensive:
            return None
        whole = max(0, int((datetime.now(UTC) - job.since).total_seconds()))
        hours, minutes, seconds = whole // 3600, whole // 60 % 60, whole % 60
        took = f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
        return f"{job.run.registry.blicks[job.task.blick].title} is building ({took})"

    def request(self, blick: str, rebuild: bool = False) -> BuildState:
        """Ask for the Blick ``blick`` of the run served to be built, and say what it is: ``done``
        when it is built already, whether it failed or skipped the run, ``building`` while it
        builds; otherwise it is queued, before the background, and ``queued``, or ``building``
        when nothing builds and no Blick a page asked for waits, since it starts at once. With
        ``rebuild``, a Blick built or building is queued for one more build. A Blick a page asked
        for waits once at most, so asking again while it waits changes nothing.

        Raises ``NoSuchBlick`` while no run is served and for an id that names no Blick the run
        can build, such as one whose definition is invalid, and ``Refused`` while a load holds or
        waits for the session's lock, which drops what the run before had queued, and once the
        worker has stopped, unless there is nothing to do.
        """
        with self._changed:
            if (run := self._run) is None:
                raise NoSuchBlick(f"{serve.NO_RUN}; pick one in the viewer")
            if self.lock.loading:
                raise Refused(_BUILD_LOADING)
            if blick not in run.registry.blicks:
                if any(entry.id == blick for entry in run.registry.failed):
                    why = "its definition is invalid; fix it and restart blicket dev"
                else:
                    why = "the ids are those of the Blicks in manifest.json"
                raise NoSuchBlick(f"no Blick {blick!r} to build: {why}")
            waiting = [job for job in self._queue if job.task.blick == blick]
            if any(job.asked for job in waiting):
                return "queued"
            building = self._building is not None and self._building.task.blick == blick
            if not rebuild and building:
                return "building"
            if not rebuild and run.is_built(blick):
                return "done"
            if self._stopped is not None:
                raise Refused(STOPPED.format(self._stopped))
            rank = _EXPENSIVE if blick in run.expensive else _CHEAP
            job = _Queued(Build(blick), run, rank, datetime.now(UTC))
            self._queue = [other for other in self._queue if other not in waiting]
            self._queue.append(job)
            self._queue.sort(key=lambda queued: queued.rank)  # stable: in the order queued
            self._changed.notify_all()
            if self._building is None:
                self._pick()
            state: BuildState = "queued" if job in self._queue else "building"
        self.begin()
        return state

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait until no job runs or waits, the lines of the last one printed; whether that
        happened within ``timeout`` seconds."""
        with self._changed:
            return self._changed.wait_for(
                lambda: self._building is None and not self._queue and not self._reporting,
                timeout,
            )

    def _revision_now(self) -> int:
        """The revision of the run served; called with ``_changed`` held."""
        return self._run.current().revision if self._run is not None else 0

    def _pick(self) -> None:
        """Mark the first job of the list running; called with ``_changed`` held."""
        first = self._queue.pop(0)
        self._building = dataclasses.replace(first, since=datetime.now(UTC))

    def _work(self) -> None:
        """Do the jobs, one at a time, in order, until the process ends."""
        try:
            while True:
                with self._changed:
                    while self._building is None:
                        if self._queue and not self.lock.loading:
                            self._pick()
                        else:
                            self._changed.wait()
                    job = self._building
                self._do(job)
        except BaseException as error:  # a bug: no Blick can be built any more
            stopped = raised(error)
            with self._changed:
                self._stopped = stopped
                self._building = None
                self._reporting = False
                self._queue.clear()
                self._changed.notify_all()
            details = traceback.format_exc().rstrip()
            self.terminal.say(lambda: f"error: {STOPPED.format(stopped)}\n{details}", err=True)

    def _do(self, job: _Queued) -> None:
        """Do ``job`` holding the session's lock, unless a load replaced its run meanwhile: build
        its Blick, say so when a page asked for it, publish it, and once every cheap Blick of
        the run is built, print the report of the background."""
        run, blick = job.run, job.task.blick
        with self.lock.build(job.expensive):
            with self._changed:
                if self._building is not job:  # dropped by a load while it waited
                    return
            if job.asked:
                self.terminal.say(lambda: f"{datetime.now():%H:%M:%S} building {blick}", err=True)
            rebuilt = run.is_built(blick)
            started = time.perf_counter()
            built = run.build(blick)
            if job.asked:
                line = functools.partial(
                    render_session_build,
                    built.entry,
                    built.compared,
                    time.perf_counter() - started,
                    datetime.now(),
                    rebuilt=rebuilt,
                    verbose=self.terminal.verbose,
                )
                self.terminal.say(line)
            with self._changed:
                run.publish(built)
                # Guards a job that would replace the run itself, and with it the job running.
                if self._building is job:
                    self._building = None
                due = not self._reported and all(run.is_built(cheap) for cheap in run.cheap)
                if due:
                    self._reported = self._reporting = True
                self._changed.notify_all()
            if due:
                report = functools.partial(
                    render_session_report,
                    run.current().manifest,
                    run.current().comparison,
                    run.prepared.root,
                    datetime.now(),
                    run.registry.blicks.keys(),
                    verbose=self.terminal.verbose,
                )
                self.terminal.say(report)
                with self._changed:
                    self._reporting = False
                    self._changed.notify_all()


def expensive_blicks(registry: Registry, loaded: LoadedRun) -> frozenset[str]:
    """The ids of the Blicks of ``registry`` that are expensive on the run ``loaded``: those whose
    definition says so, and, when the run says that its Blicks are, those whose definition says
    nothing of it."""
    default = loaded.info.expensive
    return frozenset(
        blick.id
        for blick in registry.blicks.values()
        if (default if blick.expensive is None else blick.expensive)
    )


def start(
    prepared: Prepared,
    registry: Registry,
    loaded: LoadedRun,
    found: Found,
    *,
    session: str,
    terminal: Terminal,
    revision: int = 0,
    against: str | None = None,
) -> tuple[OnDemandRun, str]:
    """Make the run ``loaded`` to serve, building nothing yet, as the snapshot ``revision``: the
    run, and the report to print, which says how many Blicks there are and how they are built,
    which baseline they are compared with as they are built, and which of its Blicks no Blick
    claims. ``session`` names the session, as the manifest's id; ``against`` names the baseline
    or a git ref, as ``blicket check --against`` does. Raises ``BlicketError`` when git cannot
    run to resolve the baseline."""
    expensive = expensive_blicks(registry, loaded)
    pending = [
        stamped(blick.entry(), expensive, pending=True) for blick in registry.blicks.values()
    ]
    repository = builder.read_repository(prepared.root)
    started = datetime.now(UTC)
    initial = builder.assemble(prepared, registry, loaded, pending, repository, started, session)
    lookup = check.find(initial, prepared.root, against)
    run = OnDemandRun(
        prepared=prepared,
        registry=registry,
        loaded=loaded,
        dataset=found,
        initial=initial,
        baseline=lookup.baseline.keeping() if lookup.baseline else None,
        expensive=expensive,
        terminal=terminal,
        first_revision=revision,
    )
    current = run.current().comparison
    removed = [b.name for b in current.blicks if "removed" in b.change.flags] if current else []
    reference = comparison.reference(lookup.baseline.manifest) if lookup.baseline else None
    report = render_session_start(
        initial,
        prepared.root,
        lookup.resolution,
        reference,
        removed,
        lookup.warnings,
        verbose=terminal.verbose,
    )
    return run, report
