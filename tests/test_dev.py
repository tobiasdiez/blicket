"""``blicket dev``: the check it starts with, the session it serves, and how it starts and stops."""

import re
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from blicket import cli, dev, manifest, serve
from blicket.query import Query
from tests.support import DATASET, LOADER, VALUES, commit_all, make_build_project, make_run

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


def project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: str = COUNTING + DATASET,
    files: dict[str, str] | None = None,
) -> str:
    """A committed project with the runs a and b (2022 moved), as the working directory;
    returns the short commit."""
    blicks = {"blicks/a.py": VALUES} if files is None else files
    root = make_build_project(tmp_path, {"model_loader.py": loader, **blicks})
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
    started = session(served)
    assert started.dataset.contents is not None
    assert list(started.dataset.contents.quantities) == ["values"]
    assert served[0].directory == started.current().build.path
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
    assert session(served).current().compared.comparison is not None
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
    assert session(served).current().compared.comparison is None


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
    built = session(served).current().build
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
    started = session(served)
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
