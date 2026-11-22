"""The builds of a ``blicket dev`` session: nothing built before it begins, then the cheap Blicks
in the background and a Blick a page asks for before them, one at a time, the cheap ones asked
for before the expensive ones, rebuilt on request, compared with the baseline as they are built,
and a run loaded in place of the one served."""

import dataclasses
import io
import json
import threading
from pathlib import Path
from typing import Any

import jsonschema
import polars as pl
import pytest

from blicket import builder, check, comparison, dev, jobs, manifest
from blicket.comparison import Comparison
from blicket.errors import LoaderError, LoadRefused, NoSuchBlick, Refused
from blicket.jobs import OnDemandRun
from blicket.query import Query
from blicket.serve import RunFolder
from tests.support import (
    CHEAP,
    ON_DEMAND_RAISES,
    WITH_DATASET,
    git,
    normalised,
    on_demand_project,
    push_whole,
)

VALIDATION, INVALID = "plastics/validation", "plastics/invalid"
PRODUCTION, TRADE, SCRAP, SHARES = "steel/production", "steel/trade", "steel/scrap", "steel/shares"
SCRAP_LINE = (
    "12:00:00 steel/scrap failed in 5 ms · transformation raised KeyError: 'scrap' (raised at "
    f"blicketconf.py:{ON_DEMAND_RAISES})"
)
INVALID_LINES = [
    "",
    "errors",
    "  blicks/plastics.py:13  Blick plastics/invalid",
    "    tolerance must be a positive number below 1, got 2.0",
]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed copy of the on-demand project, as the working directory."""
    project = on_demand_project(tmp_path)
    monkeypatch.chdir(project)
    return project


@pytest.fixture
def cheap(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runs of the on-demand project with cheap Blicks, but those that say otherwise."""
    monkeypatch.setenv(CHEAP, "1")


def start(run: str = "runs/b", **options: Any) -> tuple[dev.Session, OnDemandRun, str]:
    """A dev session on the run ``run`` of the project in the working directory, its worker not
    begun: the session, the run it serves and the report."""
    session, report = dev.start(Path.cwd(), [Path(run)], **options)
    assert isinstance(session.serving, OnDemandRun)
    return session, session.serving, report


def built(session: dev.Session, *blicks: str, rebuild: bool = False) -> None:
    """Ask for ``blicks`` and wait until they, and the background, are built."""
    for blick in blicks:
        session.build(blick, rebuild)
    assert session.worker.wait_idle(10)


def begun(session: dev.Session) -> None:
    """Begin the worker and wait until the background is built."""
    session.begin()
    assert session.worker.wait_idle(10)


def entry(run: OnDemandRun, blick: str) -> manifest.BlickEntry:
    """The entry of ``blick`` in what the run serves now."""
    return next(e for e in run.current().manifest.blicks if e.id == blick)


def statuses(run: OnDemandRun) -> dict[str | None, str]:
    return {e.id: e.status for e in run.current().manifest.blicks}


def compared(run: OnDemandRun) -> Comparison:
    found = run.current().comparison
    assert found is not None
    return found


def flags(run: OnDemandRun) -> dict[str, list[str]]:
    return {b.name: sorted(b.change.flags) for b in compared(run).blicks}


def jobs_of(session: dev.Session) -> list[tuple[str, str, bool]]:
    """The jobs ``dev/info`` lists: each Blick, its state, and whether a page asked for it."""
    return [(job.id, job.state, job.asked) for job in session.worker.status().jobs]


def table(run: OnDemandRun, hashed: str | None) -> bytes:
    """The bytes the run serves for the table of hash ``hashed``."""
    assert hashed is not None
    found = run.current().tables.get(hashed.removeprefix("parquet-sha256:"))
    assert found is not None
    return found


# ---------------------------------------------------------------------------------------------
# The start: nothing built, the Blicks cheap or expensive


def test_a_session_builds_nothing_before_it_begins(root: Path) -> None:
    session, run, report = start()
    assert run.loaded.run.asked == []
    assert not (root / ".blicket").exists()
    assert statuses(run) == {
        VALIDATION: "pending",
        INVALID: "error",  # its definition, which needs no build
        PRODUCTION: "pending",
        TRADE: "pending",
        SCRAP: "pending",
        SHARES: "pending",
    }
    served = run.current()
    assert served.manifest.build.id == session.id == session.info().session  # names the session
    assert manifest.BUILD_ID.fullmatch(served.manifest.build.id)
    assert (served.manifest.run.id, served.manifest.run.paths) == ("b", ["runs/b"])
    assert session.current() is served
    assert report.splitlines()[1] == (
        "6 Blicks: 1 built in the background, 4 when opened in the viewer (expensive) · 1 error"
    )
    assert (served.revision, session.worker.status()) == (0, jobs.Progress())
    assert run.expensive == {VALIDATION, PRODUCTION, TRADE, SCRAP}


def test_the_background_builds_the_cheap_blicks_once_the_session_begins(root: Path) -> None:
    session, run, _ = start()
    session.begin()
    assert session.worker.wait_idle(10)
    assert run.loaded.run.asked == ["shares"]  # the one cheap Blick, which says so itself
    assert (statuses(run)[SHARES], statuses(run)[TRADE]) == ("ok", "pending")
    assert run.current().revision == 1
    assert not (root / ".blicket").exists()  # nothing written


# What a test changes of the project: no Blick says that it is cheap, and plastics.py keeps only
# its Blick that says that it is expensive.
NONE_CHEAP = ("steel.py", ", expensive=False", "")
ONE_EXPENSIVE = ("plastics.py", "@bk.blick(\n    title=", "")


@pytest.mark.parametrize(
    ("cheap_run", "removed", "edits", "summary"),
    [
        (
            True,
            (),
            (),
            "6 Blicks: 4 built in the background, 1 when opened in the viewer (expensive) "
            "· 1 error",
        ),
        (True, ("plastics.py",), (), "4 Blicks, built in the background"),
        (
            False,
            ("plastics.py",),
            (),
            "4 Blicks: 1 built in the background, 3 when opened in the viewer (expensive)",
        ),
        (
            False,
            ("plastics.py",),
            (NONE_CHEAP,),
            "4 Blicks, each built when it is opened in the viewer (expensive)",
        ),
        (
            False,
            ("steel.py",),
            (),
            "2 Blicks: 1 built when opened in the viewer (expensive) · 1 error",
        ),
        (
            True,
            ("steel.py",),
            (ONE_EXPENSIVE,),
            "1 Blick, built when it is opened in the viewer (expensive)",
        ),
    ],
)
def test_the_start_says_how_the_blicks_are_built(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    cheap_run: bool,
    removed: tuple[str, ...],
    edits: tuple[tuple[str, str, str], ...],
    summary: str,
) -> None:
    if cheap_run:
        monkeypatch.setenv(CHEAP, "1")
    for module in removed:
        (root / "blicks" / module).unlink()
    for module, cut, kept in edits:
        path = root / "blicks" / module
        text = path.read_text()
        path.write_text(
            text.split(cut)[0] if not kept and cut.startswith("@") else text.replace(cut, kept)
        )
    _, _, report = start()
    assert report.splitlines()[1] == summary


def test_a_blick_says_whether_it_is_expensive_and_the_run_decides_the_rest(
    root: Path, cheap: None
) -> None:
    _, run, _ = start()
    assert run.expensive == {VALIDATION}  # it says so, whatever the run says
    assert jobs.expensive_blicks(run.registry, run.loaded) == {VALIDATION}
    expensive = dataclasses.replace(
        run.loaded, info=run.loaded.info.model_copy(update={"expensive": True})
    )
    assert jobs.expensive_blicks(run.registry, expensive) == {VALIDATION, PRODUCTION, TRADE, SCRAP}


def test_the_manifest_of_a_session_says_pending_and_expensive_and_reads_back(root: Path) -> None:
    session, run, _ = start()
    data = json.loads(run.current().manifest_json())
    pending = next(e for e in data["blicks"] if e["id"] == TRADE)
    assert (pending["status"], pending["pending"], pending["expensive"], pending["data"]) == (
        "pending",
        True,
        True,
        None,
    )
    assert pending["source"]["file"] == "blicks/steel.py"  # relative to the root
    shares = next(e for e in data["blicks"] if e["id"] == SHARES)
    assert ("expensive" in shares, shares["pending"]) == (False, True)  # cheap: left out
    invalid = next(e for e in data["blicks"] if e["id"] == INVALID)
    assert "expensive" not in invalid  # it cannot be built
    assert "expensive" not in data["run"]
    assert manifest.Manifest.model_validate(data).statuses["pending"] == 5
    schema = manifest.Manifest.model_json_schema(mode="serialization")
    jsonschema.validate(data, schema)
    built(session, TRADE)
    data = json.loads(run.current().manifest_json())
    ok = next(e for e in data["blicks"] if e["id"] == TRADE)
    assert (ok["status"], "pending" in ok, ok["expensive"]) == ("ok", False, True)
    jsonschema.validate(data, schema)


# ---------------------------------------------------------------------------------------------
# Builds asked for, and the order of the queues


def test_a_blick_asked_for_is_built_and_served_by_its_content(root: Path) -> None:
    session, run, _ = start()
    assert session.build(TRADE) == "building"
    assert session.worker.wait_idle(10)
    trade = entry(run, TRADE)
    assert trade.status == "ok"
    assert trade.hash is not None
    digest = trade.hash.removeprefix("parquet-sha256:")
    assert trade.data == f"dev/tables/{digest}.parquet"
    assert pl.read_parquet(io.BytesIO(table(run, trade.hash)))["value"].to_list() == [3.3, 2, 1]
    assert run.loaded.run.asked == ["trade", "shares"]  # the Blick asked for, then the background
    assert run.current().revision == 2
    assert session.build(TRADE) == "done"  # nothing to do
    assert run.current().revision == 2


def test_blicks_asked_for_are_built_one_at_a_time_in_the_order_asked(root: Path) -> None:
    session, run, _ = start()
    production = run.loaded.run.hold("production")
    trade = run.loaded.run.hold("trade")
    assert session.build(PRODUCTION) == "building"
    assert session.build(TRADE) == "queued"
    assert session.build(VALIDATION) == "queued"
    assert (session.build(PRODUCTION), session.build(TRADE)) == ("building", "queued")  # once each
    assert production.reached.wait(10)
    assert not trade.reached.wait(0.2)  # the second waits for the first
    assert jobs_of(session) == [  # the background, steel/shares, is not listed
        (PRODUCTION, "building", True),
        (TRADE, "queued", True),
        (VALIDATION, "queued", True),
    ]
    assert all(job.seconds >= 0 for job in session.worker.status().jobs)
    assert statuses(run)[PRODUCTION] == "pending"  # until it is built
    production.open()
    assert trade.reached.wait(10)
    trade.open()
    assert session.worker.wait_idle(10)
    assert run.loaded.run.asked == ["production", "trade", "shares"]
    assert [statuses(run)[blick] for blick in (PRODUCTION, TRADE, VALIDATION, SHARES)] == [
        "ok",
        "ok",
        "skipped",
        "ok",
    ]
    assert (run.current().revision, session.worker.status().jobs) == (4, ())


def test_cheap_blicks_asked_for_go_first_then_expensive_ones_then_the_background(
    root: Path, cheap: None, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    capsys.readouterr()
    gate = run.loaded.run.hold("production")
    session.begin()  # the background: production, trade, scrap, shares
    assert gate.reached.wait(10)
    assert jobs_of(session) == [(PRODUCTION, "building", False)]
    assert session.build(VALIDATION) == "queued"  # expensive
    assert session.build(SHARES) == "queued"  # cheap, moved out of the background
    assert session.build(SCRAP) == "queued"
    assert jobs_of(session) == [
        (PRODUCTION, "building", False),  # a build running is never interrupted
        (SHARES, "queued", True),
        (SCRAP, "queued", True),
        (VALIDATION, "queued", True),
    ]
    gate.open()
    assert session.worker.wait_idle(10)
    assert run.loaded.run.asked == ["production", "shares", "scrap", "trade"]
    printed = normalised(capsys.readouterr().out)
    # A line for each Blick a page asked for, none for the background, which reports once done.
    assert printed[:3] == [
        "12:00:00 steel/shares built in 5 ms",
        f"{SCRAP_LINE}   (-v for the traceback)",
        "12:00:00 plastics/validation skipped in 5 ms · the run has no validation.mif",
    ]
    assert printed[3] == "12:00:00 6 Blicks: 3 built · 1 skipped · 2 errors"


def test_an_expensive_blick_asked_while_the_background_builds_is_built_next(
    root: Path, cheap: None
) -> None:
    session, run, _ = start()
    production = run.loaded.run.hold("production")
    trade = run.loaded.run.hold("trade")
    session.begin()
    assert production.reached.wait(10)
    assert session.build(VALIDATION) == "queued"
    production.open()
    assert trade.reached.wait(10)  # the background goes on, after the Blick asked for
    assert statuses(run)[VALIDATION] == "skipped"
    trade.open()
    assert session.worker.wait_idle(10)


def test_a_failing_and_a_skipping_blick_are_built_and_not_built_again(root: Path) -> None:
    session, run, _ = start()
    built(session, SCRAP, VALIDATION)
    scrap = entry(run, SCRAP)
    assert scrap.status == "error"
    assert scrap.problems[0].message.startswith("transformation raised KeyError: 'scrap'")
    assert entry(run, VALIDATION).skipped == "the run has no validation.mif"
    assert (session.build(SCRAP), session.build(VALIDATION)) == ("done", "done")


def test_a_rebuild_builds_again_on_the_same_run(root: Path) -> None:
    session, run, _ = start()
    begun(session)
    built(session, TRADE)
    first = entry(run, TRADE)
    (root / "runs" / "b" / "values.txt").write_text("1 2 4\n")  # the model changed
    assert session.build(TRADE, rebuild=True) == "building"
    assert session.worker.wait_idle(10)
    second = entry(run, TRADE)
    assert (run.loaded.run.asked, run.current().revision) == (["shares", "trade", "trade"], 3)
    assert second.hash != first.hash
    assert pl.read_parquet(io.BytesIO(table(run, second.hash)))["value"].to_list() == [4, 2, 1]
    assert table(run, first.hash)  # a fetch made from the manifest before still finds it


def test_a_cheap_blick_is_built_again_when_its_page_asks(
    root: Path, cheap: None, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    begun(session)
    capsys.readouterr()
    assert session.build(TRADE) == "done"  # built in the background
    (root / "runs" / "b" / "values.txt").write_text("1 2 4\n")
    assert session.build(TRADE, rebuild=True) == "building"  # as its page asks at each visit
    assert session.worker.wait_idle(10)
    assert entry(run, TRADE).rows == 3
    assert pl.read_parquet(io.BytesIO(table(run, entry(run, TRADE).hash)))["value"][0] == 4
    assert normalised(capsys.readouterr().out) == ["12:00:00 steel/trade rebuilt in 5 ms"]


def test_a_replaced_table_is_kept_for_the_snapshots_after(root: Path) -> None:
    session, run, _ = start()
    built(session, TRADE)  # and steel/shares in the background
    old = entry(run, TRADE).hash
    assert old is not None
    (root / "runs" / "b" / "values.txt").write_text("1 2 4\n")
    built(session, TRADE, rebuild=True)
    for _ in range(jobs.KEPT - 1):  # the rebuild and KEPT - 1 more snapshots after it
        built(session, VALIDATION, rebuild=True)
    assert table(run, old)
    built(session, VALIDATION, rebuild=True)
    assert run.current().tables.get(old.removeprefix("parquet-sha256:")) is None


def test_a_rebuild_asked_while_the_blick_builds_follows_once(root: Path) -> None:
    session, run, _ = start()
    gate = run.loaded.run.hold("trade")
    assert session.build(TRADE) == "building"
    assert session.build(TRADE, rebuild=True) == "queued"
    assert session.build(TRADE, rebuild=True) == "queued"  # at most one waits
    assert jobs_of(session) == [(TRADE, "building", True), (TRADE, "queued", True)]
    gate.open()
    assert session.worker.wait_idle(10)
    assert run.loaded.run.asked == ["trade", "trade", "shares"]
    assert run.current().revision == 3


def test_a_rebuild_from_a_table_to_a_failure_without_a_baseline(root: Path) -> None:
    session, run, _ = start()
    built(session, TRADE)
    (root / "runs" / "b" / "values.txt").write_text("1 2\n")  # a year short
    built(session, TRADE, rebuild=True)
    trade = entry(run, TRADE)
    assert (trade.status, trade.data, trade.expensive, run.current().comparison) == (
        "error",
        None,
        True,
        None,
    )


def test_the_session_builds_only_blicks_it_has(root: Path) -> None:
    session, _, _ = start()
    with pytest.raises(NoSuchBlick, match=r"^no Blick 'steel/none' to build: the ids are those"):
        session.build("steel/none")
    with pytest.raises(NoSuchBlick, match=": its definition is invalid; fix it and restart"):
        session.build(INVALID)


# ---------------------------------------------------------------------------------------------
# What a build raises, and the lines it prints


def test_whatever_a_build_raises_is_the_blicks_error(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    push_whole()
    session, run, _ = start()

    def broken(*args: object) -> object:
        raise RuntimeError("a bug")

    with monkeypatch.context() as patched:  # the build raises outside the transformation
        patched.setattr(builder, "run_blick", broken)
        built(session, TRADE)
    trade = entry(run, TRADE)
    assert (trade.status, trade.expensive) == ("error", True)
    assert trade.timing_ms is not None  # which tells it apart from an invalid definition
    (problem,) = trade.problems
    assert (problem.kind, problem.message) == (
        "build",
        "building the Blick raised RuntimeError: a bug",
    )
    assert problem.traceback is not None
    assert "RuntimeError: a bug" in problem.traceback
    assert flags(run)[TRADE] == ["error"]
    built(session, PRODUCTION)  # and the worker goes on
    assert entry(run, PRODUCTION).status == "ok"
    assert session.worker.status().stopped is None
    assert "failed in" in capsys.readouterr().out


def test_what_comparing_raises_is_an_error_of_the_comparison_only(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    push_whole()
    session, run, _ = start()
    begun(session)
    capsys.readouterr()

    class Broken:
        def diff(self, *args: object) -> object:
            raise RuntimeError("a bug")

    with monkeypatch.context() as patched:  # a plot type's diff raises what nobody expects
        patched.setattr(comparison, "builtin", lambda name: Broken())
        built(session, TRADE)
    trade = entry(run, TRADE)
    assert (trade.status, trade.problems) == ("ok", ())  # built, and its table kept
    assert table(run, trade.hash)
    (compared_trade,) = [b for b in compared(run).blicks if b.name == TRADE]
    assert sorted(compared_trade.change.flags) == ["error"]
    assert compared_trade.message == "comparing raised RuntimeError: a bug"
    assert normalised(capsys.readouterr().out) == [
        "12:00:00 steel/trade built in 5 ms · error: comparing raised RuntimeError: a bug"
    ]
    built(session, PRODUCTION)  # and the worker goes on
    assert flags(run)[PRODUCTION] == ["value"]


class Cancelled(BaseException):
    """What a model's bridge may raise, as ``asyncio.CancelledError``: no ``Exception``."""


def test_a_base_exception_of_a_transformation_is_its_error_too(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, run, _ = start()

    def cancelled(self: object, name: str) -> object:
        raise Cancelled("the model went away")

    with monkeypatch.context() as patched:
        patched.setattr(type(run.loaded.run), "table", cancelled)
        built(session, TRADE)
    assert entry(run, TRADE).problems[0].message == (
        "building the Blick raised Cancelled: the model went away"
    )
    assert session.worker.status().stopped is None
    built(session, TRADE, rebuild=True)  # the worker goes on
    assert entry(run, TRADE).status == "ok"


def test_an_exception_that_says_nothing_is_named_alone(root: Path) -> None:
    session, run, _ = start()

    def cancelled(self: object, name: str) -> object:
        raise Cancelled

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(type(run.loaded.run), "table", cancelled)
        built(session, TRADE)
    assert entry(run, TRADE).problems[0].message == "building the Blick raised Cancelled"


def test_a_table_built_again_unchanged_is_kept_once(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    push_whole()
    session, run, _ = start()
    reads: list[str] = []
    read_bytes = Path.read_bytes

    def counted(path: Path) -> bytes:
        reads.append(path.name)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted)
    built(session, TRADE)
    for _ in range(3):
        built(session, TRADE, rebuild=True)
    (trade,) = [b for b in compared(run).blicks if b.name == TRADE]
    assert trade.baseline_hash is not None  # flagged, so drawn against the baseline's table
    for hashed in (entry(run, TRADE).hash, trade.baseline_hash):
        assert hashed is not None
        digest = hashed.removeprefix("parquet-sha256:")
        kept = [tables[digest] for tables in run._kept if digest in tables]
        assert len(kept) == 5  # four builds of steel/trade and one of steel/shares
        assert all(content is kept[0] for content in kept)  # one object, not a copy per build
    assert reads.count("trade.parquet") == 1  # the baseline's file, read once


def test_a_worker_that_stops_says_so(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    built(session, TRADE)

    def broken(built: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(run, "publish", broken)
    session.build(PRODUCTION)
    assert session.worker.wait_idle(10)
    assert session.worker.status().stopped == "RuntimeError: a bug"
    assert session.info().stopped == "RuntimeError: a bug"
    assert session.build(TRADE) == "done"  # nothing to do, whatever the worker does
    with pytest.raises(Refused, match=r"the worker .* stopped \(RuntimeError: a bug\); restart"):
        session.build(SCRAP)
    assert session.worker._thread is not None
    session.worker._thread.join(10)  # it says so last, once it recorded it
    assert "error: the worker that builds the Blicks stopped" in capsys.readouterr().err


class Gone(io.StringIO):
    """A stream whose reader went away, as after ``| head``: writing raises ``OSError``."""

    def write(self, text: str) -> int:
        raise BrokenPipeError("the reader went away")


def closed() -> io.StringIO:
    """A stream closed: writing raises ``ValueError``."""
    stream = io.StringIO()
    stream.close()
    return stream


def test_a_reader_of_stdout_that_goes_away_ends_the_lines_not_the_builds(root: Path) -> None:
    session, run, _ = start()
    session.terminal.out = Gone()
    built(session, TRADE, PRODUCTION)
    assert (statuses(run)[TRADE], statuses(run)[PRODUCTION]) == ("ok", "ok")
    assert (session.worker.status().stopped, session.terminal.out) == (None, None)


def test_a_stderr_whose_reader_goes_away_costs_no_build(root: Path) -> None:
    session, run, _ = start()
    session.terminal.err = Gone()  # the line that a build starts goes there
    built(session, TRADE, PRODUCTION)
    assert (statuses(run)[TRADE], statuses(run)[PRODUCTION]) == ("ok", "ok")
    assert (session.worker.status().stopped, session.terminal.err) == (None, None)  # silenced


def test_a_closed_stderr_costs_no_build(root: Path) -> None:
    session, run, _ = start()
    stream = session.terminal.err = closed()
    built(session, TRADE, PRODUCTION)
    assert (statuses(run)[TRADE], statuses(run)[PRODUCTION]) == ("ok", "ok")
    assert (session.worker.status().stopped, session.terminal.err) == (
        None,
        stream,
    )  # not an OSError: still in use


def test_a_full_stderr_costs_no_build(root: Path, tmp_path: Path) -> None:
    if not Path("/dev/full").exists():
        pytest.skip("no /dev/full here")
    session, run, _ = start()
    with open("/dev/full", "w") as full:  # as the shell opens it for 2>/dev/full
        session.terminal.err = full
        built(session, TRADE)
    assert (statuses(run)[TRADE], session.worker.status().stopped, session.terminal.err) == (
        "ok",
        None,
        None,
    )


def test_a_closed_stdout_costs_no_build(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session, run, _ = start()
    session.terminal.out = closed()
    built(session, TRADE, PRODUCTION)
    assert (statuses(run)[TRADE], statuses(run)[PRODUCTION]) == ("ok", "ok")
    assert session.worker.status().stopped is None
    said = capsys.readouterr().err
    assert said.count("error: blicket cannot write a line of the session to stdout") == 1
    assert "ValueError: I/O operation on closed file" in said


def test_a_line_that_stdout_cannot_encode_leaves_stdout_in_use(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, _, _ = start()
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii")
    session.terminal.out = stream
    built(session, SCRAP)  # its line has a ·, which ascii has not, as has the background's report
    built(session, VALIDATION, SCRAP, rebuild=True)
    built(session, TRADE)  # without a baseline, its line is ascii
    assert session.terminal.out is stream
    stream.flush()
    written = raw.getvalue().decode()
    assert "steel/trade built in" in written
    assert "steel/scrap" not in written
    said = capsys.readouterr().err
    assert said.count("error: blicket cannot write a line of the session to stdout") == 1
    assert "UnicodeEncodeError" in said


def test_a_line_that_cannot_be_rendered_costs_no_build(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()

    def broken(*args: object, **options: object) -> str:
        raise RuntimeError("a bug in the line")

    monkeypatch.setattr(jobs, "render_session_build", broken)
    monkeypatch.setattr(jobs, "render_session_report", broken)
    built(session, TRADE, PRODUCTION)
    assert (statuses(run)[TRADE], statuses(run)[PRODUCTION], statuses(run)[SHARES]) == (
        "ok",
        "ok",
        "ok",
    )
    assert session.worker.status().stopped is None
    assert capsys.readouterr().err.count("RuntimeError: a bug in the line") == 3  # and the report


def test_a_worker_that_stops_says_so_also_without_stderr(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, run, _ = start()
    session.terminal.err = Gone()

    def broken(built: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(run, "publish", broken)
    session.build(TRADE)
    assert session.worker.wait_idle(10)
    assert session.worker.status() == jobs.Progress(stopped="RuntimeError: a bug")


def test_a_line_per_build_asked_for_on_the_stdout_the_session_started_with(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    push_whole()
    session, _, _ = start()
    begun(session)
    capsys.readouterr()
    built(session, PRODUCTION, TRADE, SCRAP, VALIDATION)
    printed = capsys.readouterr()
    assert normalised(printed.out) == [
        "12:00:00 steel/production built in 5 ms · value, 9.1% of scale (region=CN, year=2022)",
        "12:00:00 steel/trade built in 5 ms · value, 9.1% of scale (year=2020)",
        f"{SCRAP_LINE}   (-v for the traceback)",
        "12:00:00 plastics/validation skipped in 5 ms · the run has no validation.mif",
    ]
    assert normalised(printed.err) == [
        f"12:00:00 building {blick}" for blick in (PRODUCTION, TRADE, SCRAP, VALIDATION)
    ]
    (root / "runs" / "b" / "values.txt").write_text("1 2 3\n")
    built(session, TRADE, rebuild=True)
    assert normalised(capsys.readouterr().out) == [
        "12:00:00 steel/trade rebuilt in 5 ms · unchanged"
    ]


def test_the_background_prints_no_line_and_reports_once_it_is_done(
    root: Path, cheap: None, capsys: pytest.CaptureFixture[str]
) -> None:
    push_whole()
    session, _, _ = start()
    capsys.readouterr()
    session.begin()
    assert session.worker.wait_idle(10)
    printed = capsys.readouterr()
    assert printed.err == ""  # no line of a build's start
    # check's report of the Blicks built so far, but what the start said and where a
    # comparison went; plastics/validation, expensive, is not built yet.
    assert normalised(printed.out) == [
        "12:00:00 6 Blicks: 3 built · 1 not built yet · 2 errors",
        "",  # not plastics/invalid, whose definition the start report named
        "errors",
        "  blicks/steel.py:21  Blick steel/scrap",
        f"    {SCRAP_LINE.split(' · ')[1]}   (-v for the traceback)",
        "",
        "vs baseline: 3 value · 2 errors",
        "top movers: steel/production 9.1% of scale (region=CN, year=2022)",
        "            steel/trade 9.1% of scale (year=2020)",
        "            steel/shares 4.5% of scale (year=2022)",
        "flagged: 5 of 5 Blicks",
    ]
    built(session, VALIDATION, TRADE, rebuild=True)  # builds a page asks for print their lines
    assert normalised(capsys.readouterr().out) == [
        "12:00:00 plastics/validation skipped in 5 ms · the run has no validation.mif",
        "12:00:00 steel/trade rebuilt in 5 ms · value, 9.1% of scale (year=2020)",
    ]


def test_the_report_of_the_background_waits_for_a_cheap_blick_moved_out_of_it(
    root: Path, cheap: None, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    gate = run.loaded.run.hold("production")
    session.begin()
    assert gate.reached.wait(10)
    session.build(SHARES)
    gate.open()
    assert session.worker.wait_idle(10)
    out = normalised(capsys.readouterr().out)
    report = [line for line in out if " 6 Blicks: " in line]
    assert report == ["12:00:00 6 Blicks: 3 built · 1 not built yet · 2 errors"]  # once
    assert out.index("12:00:00 steel/shares built in 5 ms") < out.index(report[0])


def test_a_line_names_the_first_warning(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (root / "blicks" / "empty.py").write_text(
        "import polars as pl\n\nimport blicket as bk\n\n\n"
        '@bk.blick(plot=bk.plots.line(x="year", y="value"))\n'
        "def nothing(run):\n"
        '    schema = {"year": pl.Int64, "value": pl.Float64}\n'
        '    return pl.DataFrame({"year": [], "value": []}, schema=schema)\n'
    )
    session, _, _ = start()
    begun(session)
    capsys.readouterr()
    built(session, "empty/nothing")
    assert normalised(capsys.readouterr().out) == [
        "12:00:00 empty/nothing built in 5 ms · 1 warning: the table has no rows"
    ]


def test_verbose_puts_the_traceback_of_a_failure_under_its_line(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, _, _ = start(verbose=True)
    begun(session)
    capsys.readouterr()
    built(session, SCRAP)
    printed = normalised(capsys.readouterr().out)
    assert printed[0] == SCRAP_LINE
    assert printed[1] == "      Traceback (most recent call last):"
    assert any(f'blicketconf.py", line {ON_DEMAND_RAISES}' in line for line in printed)


def test_what_project_code_prints_goes_to_stderr(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    steel = root / "blicks" / "steel.py"
    talking = 'print("R says hello")\n    return run.table("trade")'
    steel.write_text(steel.read_text().replace('return run.table("trade")', talking))
    session, _, _ = start()
    capsys.readouterr()
    built(session, TRADE)
    printed = capsys.readouterr()
    assert "R says hello" in printed.err
    assert "R says hello" not in printed.out


# ---------------------------------------------------------------------------------------------
# The comparison with the baseline


def test_the_comparison_fills_in_as_blicks_are_built(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = root / "blicks" / "old.py"
    old.write_text(
        'import blicket as bk\n\n\n@bk.blick(plot=bk.plots.line(x="year", y="value"))\n'
        'def gone(run):\n    return run.table("trade")\n'
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "a Blick that goes")
    baseline = push_whole()
    old.unlink()
    git(root, "commit", "-q", "-am", "gone")
    session, run, report = start()
    lines = report.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("baseline "))
    assert lines[at].startswith(f"baseline {baseline} · run a · ")
    assert lines[at + 1] == "vs baseline: 1 removed (old/gone)"
    # From the start: the removed Blick, which no Blick claims, and the invalid definition; the
    # pending ones are not in it.
    assert flags(run) == {INVALID: ["error"], "old/gone": ["removed"]}
    built(session, PRODUCTION)  # and steel/shares in the background
    assert flags(run) == {
        INVALID: ["error"],
        PRODUCTION: ["value"],
        SHARES: ["value"],
        "old/gone": ["removed"],
    }
    (production,) = [b for b in compared(run).blicks if b.name == PRODUCTION]
    store = root / ".blicket" / "store" / "builds" / baseline
    (counterpart,) = [e for e in manifest.read(store).blicks if e.id == PRODUCTION]
    assert counterpart.hash is not None
    assert counterpart.data is not None
    digest = counterpart.hash.removeprefix("parquet-sha256:")
    assert (production.baseline_data, production.baseline_hash) == (
        f"dev/tables/{digest}.parquet",
        counterpart.hash,
    )
    assert table(run, counterpart.hash) == (store / counterpart.data).read_bytes()
    (store / counterpart.data).unlink()  # the store cleaned meanwhile
    assert table(run, counterpart.hash)  # served from memory
    (store / counterpart.data).write_bytes(table(run, counterpart.hash))
    built(session, TRADE, SCRAP, VALIDATION)
    # Once every Blick is built, the comparison is the one check makes of the whole build.
    whole = builder.build(root, ["runs/b"])
    written = check.compare(whole, root).comparison
    assert written is not None
    session_blicks = json.loads(compared(run).model_dump_json())["blicks"]
    whole_blicks = json.loads(written.model_dump_json())["blicks"]
    for blick in (*session_blicks, *whole_blicks):
        blick.pop("baseline_data")  # where each serves the baseline's table
    assert session_blicks == whole_blicks


def test_a_blick_that_claims_the_baselines_old_id_is_not_removed(root: Path) -> None:
    push_whole()
    steel = root / "blicks" / "steel.py"
    renamed = steel.read_text().replace(
        '@bk.blick(title="Steel trade",', '@bk.blick(aliases=["steel/trade"], title="Steel trade",'
    )
    steel.write_text(renamed.replace("def trade(run):", "def exchange(run):"))
    session, run, _ = start()
    assert "steel/trade" not in flags(run)  # pending, it claims its old id all the same
    built(session, "steel/exchange")
    (exchange,) = [b for b in compared(run).blicks if b.name == "steel/exchange"]
    assert (exchange.matched, exchange.change.flags) == ("steel/trade", frozenset({"value"}))


def test_a_baseline_table_that_cannot_be_read_flags_the_blick(root: Path) -> None:
    baseline = push_whole()
    store = root / ".blicket" / "store" / "builds" / baseline
    (counterpart,) = [e for e in manifest.read(store).blicks if e.id == TRADE]
    assert counterpart.data is not None
    (store / counterpart.data).unlink()  # a store cleaned by hand
    session, run, _ = start()
    built(session, TRADE)
    (trade,) = [b for b in compared(run).blicks if b.name == TRADE]
    assert trade.change.flags == frozenset({"error"})
    assert trade.message is not None
    assert trade.message.startswith(f"cannot read {counterpart.data} in ")
    assert trade.message.endswith(
        "; the baseline is damaged: push it again, or name another with --against"
    )
    assert entry(run, TRADE).status == "ok"  # the Blick built; its comparison failed


def test_a_baseline_table_that_does_not_match_its_hash_flags_the_blick(root: Path) -> None:
    baseline = push_whole()
    store = root / ".blicket" / "store" / "builds" / baseline
    (counterpart,) = [e for e in manifest.read(store).blicks if e.id == TRADE]
    assert counterpart.data is not None
    other = pl.DataFrame({"year": [2020, 2021, 2022], "value": [3.0, 2.0, 0.5]})
    other.write_parquet(store / counterpart.data)
    session, run, _ = start()
    built(session, TRADE)
    (trade,) = [b for b in compared(run).blicks if b.name == TRADE]
    assert trade.change.flags == frozenset({"error"})
    assert trade.message is not None
    assert "does not match its hash in the baseline's manifest" in trade.message


def test_a_session_without_a_baseline_says_why_and_has_no_comparison(root: Path) -> None:
    session, run, report = start()
    assert "baseline: none (no other pushed build of profile test)" in report.splitlines()
    built(session, TRADE)
    assert (run.current().comparison, run.current().index_json()) == (None, b"[]\n")


def test_the_start_report_follows_checks_order(root: Path) -> None:
    _, _, report = start()
    assert report.splitlines()[2:] == [
        *INVALID_LINES,
        "",
        "baseline: none (no other pushed build of profile test)",
        "builder: off, dataset(run) returned None",
    ]


# ---------------------------------------------------------------------------------------------
# Builder queries and the lock


def test_a_query_is_refused_while_an_expensive_blick_builds(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(WITH_DATASET, "1")
    session, run, report = start()
    assert report.splitlines()[-1] == "builder: 1 quantity, 1 dimension"
    query = Query(quantities=("trade",), plot="line", mapping={"x": "year"})
    gate = run.loaded.run.hold("production")
    session.build(PRODUCTION)
    assert gate.reached.wait(10)
    with pytest.raises(
        Refused, match="an expensive Blick is building; run the query again when it is built"
    ):
        session.query(query)
    gate.open()
    assert session.worker.wait_idle(10)
    assert json.loads(session.query(query))["status"] == "ok"


def test_a_query_waits_for_a_cheap_build_and_goes_before_the_next(
    root: Path, monkeypatch: pytest.MonkeyPatch, cheap: None
) -> None:
    monkeypatch.setenv(WITH_DATASET, "1")
    session, run, _ = start()
    query = Query(quantities=("trade",), plot="line", mapping={"x": "year"})
    production = run.loaded.run.hold("production")
    trade = run.loaded.run.hold("trade")  # which the query asks for too
    session.begin()  # the background: production, trade, scrap, shares
    assert production.reached.wait(10)
    answers: list[Any] = []
    asking = threading.Thread(target=lambda: answers.append(json.loads(session.query(query))))
    asking.start()
    assert not trade.reached.wait(0.2)  # the query waits for the cheap build
    production.open()
    assert trade.reached.wait(10)  # the query took the lock before the next build
    assert jobs_of(session) == [(TRADE, "building", False)]  # which waits for it
    trade.open()
    asking.join(10)
    assert answers[0]["status"] == "ok"
    assert session.worker.wait_idle(10)
    assert run.loaded.run.asked == ["production", "trade", "trade", "scrap", "shares"]


def test_a_query_that_waits_goes_before_a_build_that_asks_for_the_lock() -> None:
    lock = jobs.RunLock()
    answers: list[str] = []
    building = threading.Event()
    release = threading.Event()

    def ask() -> None:
        try:
            with lock.query():
                answers.append("ran")
        except Refused:
            answers.append("refused")

    def build() -> None:
        with lock.build(expensive=True):
            answers.append("built")
            building.set()
            release.wait(5)

    with lock.query():
        waiting = threading.Thread(target=ask)
        waiting.start()
        builder_thread = threading.Thread(target=build)
        builder_thread.start()
        assert not building.wait(0.2)  # the build waits for both queries
    waiting.join(5)
    assert building.wait(5)
    assert answers == ["ran", "built"]
    ask()  # while the expensive build holds the lock
    assert answers == ["ran", "built", "refused"]
    release.set()
    builder_thread.join(5)
    ask()
    assert answers[-1] == "ran"


# ---------------------------------------------------------------------------------------------
# A run picked in the viewer, and a load in place of the run served


def test_a_run_picked_in_the_viewer_is_served_at_once(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, report = dev.start(root, [])
    assert report == "runs: 3 in ., runs/*"
    assert session.load([str(root / "runs" / "b")]) == "b"
    run = session.serving
    assert isinstance(run, OnDemandRun)
    assert session.worker.wait_idle(10)  # the background began once the report was printed
    assert run.loaded.run.asked == ["shares"]
    printed = normalised(capsys.readouterr().out)
    assert printed[0] == "12:00:00 loading runs/b, picked in the viewer"
    assert printed[2] == (
        "6 Blicks: 1 built in the background, 4 when opened in the viewer (expensive) · 1 error"
    )
    assert "12:00:00 6 Blicks: 1 built · 4 not built yet · 1 error" in printed
    assert session.build(TRADE) == "building"
    assert session.worker.wait_idle(10)
    assert statuses(run)[TRADE] == "ok"


def test_the_project_itself_is_listed_first_and_loaded_as_the_project_root(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, _ = dev.start(root, [])
    listed = session.runs().runs
    assert listed[0] == RunFolder(path=root, name="This project", modified=None, project=True)
    assert {(run.name, run.project) for run in listed[1:]} == {("a", False), ("b", False)}
    assert session.load([str(root)]) == "checkout"
    run = session.serving
    assert isinstance(run, OnDemandRun)
    assert run.loaded.run.path == root  # the loader gets the project root as its one path
    assert run.current().manifest.run.paths == ["."]
    printed = normalised(capsys.readouterr().out)
    assert printed[0] == "12:00:00 loading this project, picked in the viewer"
    assert printed[1].startswith("run checkout · profile test · ")


def test_the_folder_of_the_run_served_is_marked_also_through_a_link(root: Path) -> None:
    (root / "runs" / "latest").symlink_to(root / "runs" / "b")
    session, _, _ = start("runs/latest")
    served = [(run.name, run.served) for run in session.runs().runs if run.served]
    assert len(served) == 1
    assert served[0][0] in ("b", "latest")  # the folder, listed once, under one of its names


def test_a_load_replaces_the_run_served(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session, run, _ = start()
    begun(session)
    built(session, TRADE)
    before = session.id
    assert session.load([str(root / "runs" / "a")]) == "a"
    loaded = session.serving
    assert isinstance(loaded, OnDemandRun)
    assert loaded is not run
    assert session.id != before  # a new session for the viewer
    assert loaded.current().manifest.build.id == session.id
    assert (loaded.current().manifest.run.id, statuses(loaded)[TRADE]) == ("a", "pending")
    assert session.worker.wait_idle(10)
    assert statuses(loaded)[SHARES] == "ok"  # its own background
    trade = entry(run, TRADE).hash
    assert trade is not None
    assert session.table(trade.removeprefix("parquet-sha256:")) is None  # the old run's tables go
    assert session.build(TRADE) == "building"  # of the run served now
    assert session.worker.wait_idle(10)
    printed = normalised(capsys.readouterr().out)
    assert "12:00:00 loading runs/a, picked in the viewer" in printed


def test_nothing_of_the_run_before_is_built_printed_or_published_after_a_load(
    root: Path, cheap: None, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    shares = run.loaded.run.hold("shares")
    production = run.loaded.run.hold("production")
    assert session.build(SHARES) == "building"  # a page asks for the last cheap Blick
    assert shares.reached.wait(10)
    capsys.readouterr()
    answers: list[str] = []
    loading = threading.Thread(target=lambda: answers.append(session.load(["runs/a"])))
    loading.start()
    loading.join(0.2)
    assert answers == []  # it waits for the cheap build
    shares.open()
    loading.join(10)
    assert answers == ["a"]
    assert session.worker.wait_idle(10)
    out = normalised(capsys.readouterr().out)
    loaded = out.index("12:00:00 loading runs/a, picked in the viewer")
    assert out.index("12:00:00 steel/shares built in 5 ms") < loaded  # the job ran to its end
    assert not any(line == "12:00:00 steel/shares built in 5 ms" for line in out[loaded:])
    # The background of the run before stops at the load: production, its next job, was never
    # built, not even the job the worker had picked while the load waited.
    assert not production.reached.is_set()
    assert run.loaded.run.asked == ["shares"]
    revision = run.current().revision
    built(session, SCRAP)
    assert (run.current().revision, statuses(run)[PRODUCTION]) == (revision, "pending")
    assert session.serving is not run


def test_the_revision_keeps_rising_across_loads(root: Path) -> None:
    session, run, _ = start()
    begun(session)
    first = session.info().revision
    assert first == run.current().revision == 1  # steel/shares in the background
    session.load(["runs/a"])
    assert session.info().revision == first + 1  # the new run, nothing built yet
    assert session.worker.wait_idle(10)
    assert session.info().revision == first + 2
    session.load(["runs/b"])
    assert session.info().revision == first + 3
    assert session.worker.wait_idle(10)


def test_a_query_is_refused_while_a_run_loads(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WITH_DATASET, "1")
    session, _, _ = start()
    entered, release = slow_loader(monkeypatch)
    loading = threading.Thread(target=lambda: session.load(["runs/a"]))
    loading.start()
    query = Query(quantities=("trade",), plot="line", mapping={"x": "year"})
    try:
        assert entered.wait(10)
        with pytest.raises(Refused, match=r"^a run is loading; run the query again once it is"):
            session.query(query)
    finally:
        release.set()
        loading.join(10)
    assert json.loads(session.query(query))["status"] == "ok"


def slow_loader(monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, threading.Event]:
    """Make the loader wait: the event it sets once it was called, and the one it waits for."""
    entered, release = threading.Event(), threading.Event()
    load = builder.load

    def slow(prepared: builder.Prepared) -> builder.LoadedRun:
        entered.set()
        release.wait(10)
        return load(prepared)

    monkeypatch.setattr(builder, "load", slow)
    return entered, release


def test_the_worker_takes_no_job_and_a_page_none_while_a_run_loads(
    root: Path, monkeypatch: pytest.MonkeyPatch, cheap: None
) -> None:
    session, run, _ = start()
    production = run.loaded.run.hold("production")
    session.begin()  # the background: production, trade, scrap, shares
    assert production.reached.wait(10)
    entered, release = slow_loader(monkeypatch)
    loading = threading.Thread(target=lambda: session.load(["runs/a"]))
    loading.start()
    try:
        loading.join(0.2)
        assert jobs_of(session) == [(PRODUCTION, "building", False)]  # the load waits for it
        with pytest.raises(Refused, match=r"^a run is loading; ask for the Blick again once"):
            session.build(TRADE)
        production.open()
        assert entered.wait(10)
        assert jobs_of(session) == []  # the background of the run before waits, and is dropped
        with pytest.raises(Refused, match=r"^a run is loading; ask for the Blick again once"):
            session.build(SHARES)
    finally:
        release.set()
        loading.join(10)
    assert run.loaded.run.asked == ["production"]
    assert session.worker.wait_idle(10)  # the worker goes on with the run loaded
    loaded = session.serving
    assert loaded is not None
    assert statuses(loaded)[SHARES] == "ok"


def test_a_load_is_refused_once_the_worker_stopped(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, run, _ = start()

    def broken(built: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(run, "publish", broken)
    session.build(TRADE)
    assert session.worker.wait_idle(10)
    with pytest.raises(LoadRefused, match=r"stopped \(RuntimeError: a bug\); restart blicket"):
        session.load(["runs/a"])
    assert session.serving is run


def test_a_load_whose_lines_cannot_be_written_still_fails_as_it_fails(root: Path) -> None:
    session, run, _ = start()
    session.terminal.err = Gone()  # as stderr on /dev/full
    (root / "runs" / "broken").mkdir()
    with pytest.raises(LoaderError, match="raised FileNotFoundError"):
        session.load(["runs/broken"])
    assert (session.serving, session.terminal.err) == (run, None)


def test_a_load_waits_for_a_cheap_build(root: Path, cheap: None) -> None:
    session, run, _ = start()
    gate = run.loaded.run.hold("production")
    session.begin()
    assert gate.reached.wait(10)
    answers: list[str] = []
    loading = threading.Thread(
        target=lambda: answers.append(session.load([str(root / "runs" / "a")]))
    )
    loading.start()
    loading.join(0.2)
    assert answers == []  # it waits for the build running
    gate.open()
    loading.join(10)
    assert answers == ["a"]
    assert statuses(run)[PRODUCTION] == "ok"  # the build ran to its end
    assert statuses(run)[TRADE] == "pending"  # and the old run's background stopped there
    assert session.serving is not run


def test_a_load_is_refused_while_an_expensive_blick_builds(root: Path) -> None:
    session, run, _ = start()
    gate = run.loaded.run.hold("production")
    before = session.id
    assert session.build(PRODUCTION) == "building"
    assert gate.reached.wait(10)
    with pytest.raises(LoadRefused, match=r"^Steel production is building \(0:0\d\); load the run"):
        session.load([str(root / "runs" / "a")])
    assert (session.serving, session.id) == (run, before)
    gate.open()
    assert session.worker.wait_idle(10)
    assert session.load([str(root / "runs" / "a")]) == "a"


def test_a_load_that_fails_keeps_the_run_served(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, run, _ = start()
    begun(session)
    (root / "runs" / "broken").mkdir()  # without values.txt: the loader raises
    before = session.id
    with pytest.raises(LoaderError, match="loader blicketconf:load_run raised FileNotFoundError"):
        session.load([str(root / "runs" / "broken")])
    assert (session.serving, session.id) == (run, before)
    assert "error: cannot load runs/broken: loader blicketconf:load_run raised" in (
        capsys.readouterr().err
    )
    assert session.build(TRADE) == "building"  # its worker goes on
    assert session.worker.wait_idle(10)
    assert statuses(run)[TRADE] == "ok"


def test_out_is_not_used(root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    start(out=tmp_path / "builds")
    assert "--out is not used: blicket dev writes no build directory\n" in capsys.readouterr().err
    assert not (tmp_path / "builds").exists()


def test_a_session_without_blicks_is_served_empty(root: Path) -> None:
    for module in (root / "blicks").glob("*.py"):
        module.unlink()
    git(root, "commit", "-qam", "no Blicks")
    session, run, report = start()
    assert report.splitlines()[1] == "0 Blicks"
    assert "no Blicks yet (blicks/**/*.py defines none)" in report
    assert run.current().manifest.blicks == ()
    session.begin()
    assert session.worker.wait_idle(10)
