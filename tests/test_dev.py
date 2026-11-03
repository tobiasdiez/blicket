"""``blicket dev``: the check it starts with, the session it serves, and how it starts and stops."""

import os
import re
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from blicket import cli, dev, manifest, serve
from blicket.query import Query
from tests.support import (
    DATASET,
    LOADER,
    VALUES,
    commit_all,
    make_build_project,
    make_project,
    make_run,
)

runner = CliRunner()

# LOADER, counting its calls in loads.txt next to the project, outside its repository.
COUNTING = LOADER.replace(
    "    path = selection.paths[0]\n",
    "    path = selection.paths[0]\n"
    '    with (path.parents[2] / "loads.txt").open("a") as file:\n'
    '        file.write("load\\n")\n',
)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[serve.Server]:
    """The servers ``dev`` would serve, which stop at once as on Ctrl-C."""
    servers: list[serve.Server] = []

    def stop(server: serve.Server) -> None:
        servers.append(server)
        server.server_close()

    monkeypatch.setattr(serve, "run", stop)
    return servers


@pytest.fixture
def any_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every server on a free port, also for a command that takes the default port, which then
    counts as the default, so that no line says the default port is taken."""
    make = serve.make_server

    def free(
        directory: Path | None = None, host: str = serve.DEFAULT_HOST, port: int | None = None
    ) -> serve.Server:
        server = make(directory, host, 0)
        monkeypatch.setattr(serve, "DEFAULT_PORT", server.server_address[1])
        return server

    monkeypatch.setattr(serve, "make_server", free)


def project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: str = COUNTING + DATASET,
    files: dict[str, str] | None = None,
    config: str = "",
) -> str:
    """A committed project with the runs a and b (2022 moved), as the working directory, and
    the ``[tool.blicket]`` lines ``config``; returns the short commit."""
    blicks = {"blicks/a.py": VALUES} if files is None else files
    root = make_build_project(tmp_path, {"model_loader.py": loader, **blicks}, config)
    make_run(root / "runs" / "a")
    make_run(root / "runs" / "b", "1 2 3.3")
    monkeypatch.chdir(root)
    return commit_all(root)[:7]


def invoke(*args: str) -> Result:
    """``blicket`` with the load time replaced by 5 ms."""
    result = runner.invoke(cli.app, list(args))
    result.stdout_bytes = re.sub(rb"loaded in [\d.]+ m?s", b"loaded in 5 ms", result.stdout_bytes)
    return result


def dev_run(*args: str) -> Result:
    return invoke("dev", *args, "--port", "0")


def session(served: list[serve.Server]) -> dev.Session:
    """The session of the server ``dev`` served last."""
    assert isinstance(served[-1].session, dev.Session)
    return served[-1].session


def serving(served: list[serve.Server]) -> dev.Serving:
    """What the session of the server ``dev`` served last serves."""
    found = session(served).serving
    assert found is not None
    return found


def build_id(result: Result) -> str:
    """The id of the build a ``dev`` report names."""
    return result.stdout.splitlines()[2].split()[1]


def test_dev_prints_the_check_and_the_viewer_and_stops_on_ctrl_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = project(tmp_path, monkeypatch)

    def interrupt(self: serve.Server) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(serve.Server, "serve_forever", interrupt)
    result = dev_run("runs/a")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    built = build_id(result)
    assert lines[:-1] == [
        f"run a · profile test · blicks at {commit} · loaded in 5 ms",
        "1 Blick: 1 built",
        f"build {built} → .blicket/build/{built}",
        "",
        "baseline: none (no other pushed build of profile test)",
        "builder: 1 quantity, 1 dimension",
    ]
    assert re.fullmatch(r"viewer: http://127\.0\.0\.1:\d+/#/   \(Ctrl-C stops\)", lines[-1])
    assert Path(".blicket/build", built, "manifest.json").is_file()


def test_dev_loads_the_run_once_and_serves_its_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch)
    assert dev_run("runs/a").exit_code == 0
    assert (tmp_path / "loads.txt").read_text() == "load\n"
    started = serving(served)
    assert started.dataset.contents is not None
    assert list(started.dataset.contents.quantities) == ["values"]
    assert served[0].directory == started.served.build.path
    assert started.loaded.run == {"values": [1.0, 2.0, 3.0]}


def test_dev_binds_the_port_before_it_loads_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = str(taken.getsockname()[1])
        result = invoke("dev", "runs/a", "--port", port)
    assert result.exit_code == 2
    assert "the port is in use" in result.stderr
    assert not (tmp_path / "loads.txt").exists()


def test_dev_leaves_the_store_alone_and_compares_with_the_pushed_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch)
    result = dev_run("runs/a")
    assert not Path(".blicket/store").exists()  # nothing pushed
    a = build_id(result)
    assert invoke("push", f".blicket/build/{a}").exit_code == 0
    result = dev_run("runs/b")
    assert result.exit_code == 0, result.output  # flagged, which dev does not exit for
    b = build_id(result)
    assert f"baseline {a} · run a" in result.stdout
    assert "vs baseline: 1 value" in result.stdout
    assert Path(".blicket/build", b, "compare", a, "comparison.json").is_file()
    assert serving(served).served.compared.comparison is not None
    assert [path.name for path in Path(".blicket/store/builds").glob("[0-9a-f]*")] == [a]
    named = dev_run("runs/b", "--against", f".blicket/build/{b}")
    assert f"baseline {b} · run b" in named.stdout


def test_dev_goes_on_without_the_baseline_against_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch)
    result = dev_run("runs/a", "--against", "nonsense")
    assert result.exit_code == 0, result.output
    assert (
        "error: no baseline: nonsense is neither a build directory, a build in the store, nor a "
        "git ref"
    ) in result.stdout.splitlines()
    assert serving(served).served.compared.comparison is None


@pytest.mark.parametrize(
    "files",
    [
        {},  # no module matches: no_match
        {"blicks/a.py": "import blicket as bk\n"},  # a module without a Blick: no_blicks
    ],
)
def test_dev_starts_a_project_without_blicks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    served: list[serve.Server],
    files: dict[str, str],
) -> None:
    project(tmp_path, monkeypatch, files=files)
    result = dev_run("runs/a")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[1] == "0 Blicks: 0 built"
    assert (
        "no Blicks yet (blicks/**/*.py defines none); write one as code, or build one from the run "
        "in the viewer"
    ) in lines
    built = serving(served).served.build
    assert (built.manifest.blicks, built.manifest.build.incomplete) == ((), False)
    assert manifest.read(built.path).problems == ()


def test_dev_warns_on_a_dataset_that_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    raising = LOADER + DATASET.replace("return Values(run)", "raise KeyError('flows')")
    project(tmp_path, monkeypatch, raising)
    result = dev_run("runs/a")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    (warning,) = [line for line in lines if line.startswith("warning:")]
    assert warning.startswith(
        "warning: dataset(run) in model_loader raised KeyError: 'flows' (raised at model_loader.py:"
    )
    assert lines[-2] == "builder: off, dataset(run) failed; fix it and restart blicket dev"
    started = serving(served)
    assert started.dataset.contents is None
    assert started.dataset.reason == warning.removeprefix("warning: ")
    verbose = dev_run("runs/a", "-v").stdout
    assert "Traceback (most recent call last):" in verbose
    assert 'model_loader.py", line' in verbose


def test_dev_without_a_dataset_says_the_builder_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch, LOADER)
    result = dev_run("runs/a")
    assert (result.exit_code, "warning" in result.stdout) == (0, False)
    assert result.stdout.splitlines()[-2].startswith(
        "builder: off, no dataset(run) next to load_run in model_loader; add one"
    )


def test_dev_exits_2_when_the_loader_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch, "def load_run(selection):\n    raise RuntimeError('no run')\n")
    result = dev_run("runs/a")
    assert (result.exit_code, result.stdout, served) == (2, "", [])
    assert result.stderr.startswith("error: loader model_loader:load_run raised RuntimeError")


def test_verbose_logs_the_problems_of_a_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path, monkeypatch)
    raising = DATASET.replace("values):\n", "values):\n        1 / 0\n")
    Path("model_loader.py").write_text(LOADER + raising)
    started, _ = dev.start(Path.cwd(), [Path("runs/a")], verbose=True)
    capsys.readouterr()
    started.query(Query(quantities=("values",), plot="line", mapping={"x": "year"}))
    logged = capsys.readouterr().err
    assert "error: select('values') of the dataset raised ZeroDivisionError" in logged
    assert 'model_loader.py", line' in logged


# ---------------------------------------------------------------------------------------------
# Without a run: the run picker

RUNS = 'runs = ["runs/*"]\n'
PICK = "pick a run in the viewer, or pass one: blicket RUN_PATH"


def test_dev_without_a_run_serves_none_and_says_how_many_folders_runs_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch, config='runs = ["runs/*", "../elsewhere/*"]\n')
    result = dev_run()
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "runs: 2 in runs/*, ../elsewhere/*"
    assert re.fullmatch(r"viewer: http://127\.0\.0\.1:\d+/#/   \(Ctrl-C stops\)", lines[1])
    assert lines[2:] == [PICK]
    assert (session(served).current(), session(served).serving) == (None, None)
    assert not (tmp_path / "loads.txt").exists()
    assert not Path(".blicket/build").exists()


def test_dev_without_a_run_waits_for_runs_to_match_a_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch, config='runs = ["output/*"]\n')
    result = dev_run()
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0] == "runs: none yet in output/*"
    assert session(served).runs().runs == []


def test_dev_without_a_run_needs_runs_in_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch)
    result = dev_run()
    assert (result.exit_code, result.stdout, served) == (2, "", [])
    assert result.stderr == (
        'error: no run to serve; pass one (blicket RUN_PATH), or set runs = ["output/*"] in '
        "[tool.blicket] to pick one in the viewer\n"
    )


def test_blicket_alone_is_dev_without_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server], any_port: None
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    result = invoke()
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("runs: 2 in runs/*\nviewer: http://127.0.0.1:")
    assert result.stdout.endswith(f"\n{PICK}\n")
    assert session(served).current() is None


@pytest.mark.parametrize(
    ("where", "given"),
    [
        (".", "runs/a"),  # not a command, and with a slash
        ("runs", "a"),  # not a command, and an existing path
    ],
)
def test_blicket_before_a_run_path_is_dev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    served: list[serve.Server],
    any_port: None,
    where: str,
    given: str,
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    monkeypatch.chdir(where)
    result = invoke(given)
    assert result.exit_code == 0, result.output
    assert "run a · profile test · " in result.stdout
    assert serving(served).loaded.run == {"values": [1.0, 2.0, 3.0]}


def test_blicket_before_a_missing_path_with_a_slash_is_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server], any_port: None
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    result = invoke("runs/x")
    assert (result.exit_code, result.stdout, served) == (2, "", [])
    assert result.stderr == "error: run path runs/x does not exist\n"


@pytest.mark.parametrize("args", [["--out", "build", "runs/a"], ["--against", "push", "runs/a"]])
def test_option_values_named_like_commands_are_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    served: list[serve.Server],
    any_port: None,
    args: list[str],
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    assert "run a · profile test · " in result.stdout


def test_after_a_double_dash_a_command_name_is_a_run_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server], any_port: None
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    result = invoke("-v", "--", "list")
    assert (result.exit_code, result.stderr) == (2, "error: run path list does not exist\n")


@pytest.mark.parametrize(
    ("files", "config", "error"),
    [
        ({}, 'runs = ["runs/*"]\n', "project: no loader; add blicketconf.py"),  # no blicketconf.py
        ({"blicketconf.py": LOADER}, "blick = 1\n", "unknown key 'blick'"),
    ],
)
def test_blicket_alone_in_a_broken_project_says_what_is_broken(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    served: list[serve.Server],
    any_port: None,
    files: dict[str, str],
    config: str,
    error: str,
) -> None:
    monkeypatch.chdir(make_project(tmp_path, files, config))
    result = invoke()
    assert (result.exit_code, served) == (2, [])
    assert error in result.stderr
    assert "--help" not in result.stderr  # the project is there; the help is no hint


def test_blicket_before_an_option_of_dev_is_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server], any_port: None
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    result = invoke("--open")
    assert result.exit_code == 0, result.output
    assert opened == [result.stdout.splitlines()[1].split()[1].removesuffix("#/")]
    assert session(served).current() is None


def test_a_command_wins_over_a_folder_of_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: list[serve.Server]
) -> None:
    project(tmp_path, monkeypatch, config=RUNS)
    Path("list").mkdir()
    listed = invoke("list")
    assert (listed.exit_code, served) == (0, [])
    assert "1 group · 1 Blick" in listed.stdout


def test_find_runs(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    data = tmp_path / "data"
    now = 1_700_000_000
    for name, age in (("old", 300), ("new", 100), ("tie-b", 200), ("tie-a", 200), (".hidden", 0)):
        (data / name).mkdir(parents=True)
        os.utime(data / name, (now - age, now - age))
    (data / "values.txt").write_text("1 2 3")
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "latest").symlink_to(data / "new")
    patterns = ["../data/*", "../data/new", "../data/.*", "../data/*.txt", "../links/*", "no/*"]
    found = dev.find_runs(root, patterns)
    assert [run.name for run in found] == ["new", "tie-a", "tie-b", "old"]
    assert found[0].path == (data / "new").resolve()
    assert found[0].modified == datetime.fromtimestamp(now - 100, UTC)
    assert dev.find_runs(root, []) == []
    (linked,) = dev.find_runs(root, ["../links/*"])  # named by the link, the folder resolved
    assert (linked.name, linked.path) == ("latest", (data / "new").resolve())
