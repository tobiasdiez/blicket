import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from blicket import builder, cli, manifest
from tests.support import (
    PROJECTS,
    VALUES,
    commit_all,
    line_of,
    make_build_project,
    make_project,
    make_run,
    one_blick,
)

runner = CliRunner()

# minimal plus blicks/broken.py, run from inside the project; {prefix} is sys.prefix.
BROKEN_LIST = """\
flows  Material flows  [mfa]
  flows/steel_by_process   Steel flows by process   stacked_area   aliases: flows/steel_process
  flows/scrap              Scrap                    line
  flows/slag               Slag                     line
stocks
  stocks/in_use            In use                   line

2 groups · 4 Blicks · 1 error

errors
  blicks/broken.py:1  import failed   (-v for the traceback)
    ModuleNotFoundError: No module named 'nothere'
    is 'nothere' installed in {prefix}?
    the Blicks in this file were skipped
"""


def invoke(*args: str | Path) -> Result:
    return runner.invoke(cli.app, [str(arg) for arg in args])


@pytest.fixture
def broken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The minimal project with a module that fails to import, as the working directory."""
    root = tmp_path / "broken"
    shutil.copytree(PROJECTS / "minimal", root, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "blicks" / "broken.py").write_text("import nothere\n")
    monkeypatch.chdir(root)
    return root


def test_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(PROJECTS / "minimal")
    result = invoke("list")
    assert result.exit_code == 0, result.output
    assert result.stdout == (PROJECTS / "minimal" / "expected-list.txt").read_text()


def test_list_from_a_subdirectory_names_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(PROJECTS / "minimal" / "blicks")
    result = invoke("list")
    assert result.stdout.startswith(f"project: {(PROJECTS / 'minimal').resolve()}\nflows")


def test_list_with_errors(broken: Path) -> None:
    result = invoke("list")
    assert result.exit_code == 2
    assert result.stdout == BROKEN_LIST.replace("{prefix}", sys.prefix)


def test_list_json_with_errors(broken: Path) -> None:
    result = invoke("list", "--json")
    assert result.exit_code == 2
    assert json.loads(result.stdout)["errors"][0]["kind"] == "import"


def test_verbose_puts_the_project_traceback_before_the_message(broken: Path) -> None:
    errors = invoke("list", "-v").stdout.split("\nerrors\n")[1]
    assert "(-v for the traceback)" not in errors
    assert 'broken.py", line 1, in <module>' in errors
    assert "importlib" not in errors
    assert errors.index("Traceback") < errors.index("is 'nothere' installed")
    assert errors.rstrip().endswith("the Blicks in this file were skipped")


def test_failed_blicks_are_listed_under_their_group(tmp_path: Path) -> None:
    files = {
        "blicks/a.py": one_blick("shared/view"),
        "blicks/b.py": one_blick("shared/view") + one_blick("b/unique").partition("\n")[2],
        "blicks/c.py": "import nothere\n",
    }
    result = invoke("list", "--project", make_project(tmp_path, files))
    assert result.exit_code == 2
    listing, errors = result.stdout.split("\nerrors\n")
    assert "\na\n  shared/view   [error]   blicks/a.py:2\n" in listing
    assert "2 groups · 3 Blicks (2 with errors) · 3 errors" in listing
    assert "\nc\n  (no Blicks)\n" not in listing  # a module that failed to import has no group
    rows = [line for line in errors.splitlines() if not line.startswith("    ")]
    assert rows == [
        "  blicks/a.py:2  Blick shared/view",
        "  blicks/b.py:2  Blick shared/view",
        "  blicks/c.py:1  import failed   (-v for the traceback)",
    ]


def test_group_without_blicks_and_warnings(tmp_path: Path) -> None:
    files = {
        "blicks/a.py": one_blick("a/x"),
        "blicks/empty.py": "import blicket as bk\nbk.group('e')\n",
    }
    result = invoke("list", "--project", make_project(tmp_path, files))
    assert result.exit_code == 0
    assert "\ne\n  (no Blicks)\n" in result.stdout
    assert "\nwarnings\n  blicks/empty.py  no blicks\n    defines no Blicks" in result.stdout


def test_list_json(tmp_path: Path) -> None:
    files = {
        "blicks/a.py": "import blicket as bk\nbk.register(id='Bad', plot=None, transform=len)\n",
        "blicks/loud.py": "print('hello')\n" + one_blick("loud/x"),
    }
    result = invoke("list", "--json", "--project", make_project(tmp_path, files))
    assert result.exit_code == 2
    data = json.loads(result.stdout)  # what the module printed went to stderr
    assert "hello" in result.stderr
    assert data["blicket"] == importlib.metadata.version("blicket")
    # Built and failed Blicks alike, in the order of their definitions.
    failed, blick = data["blicks"]
    assert (failed["name"], failed["status"], failed["definition"]) == ("'Bad'", "error", None)
    assert (blick["id"], blick["status"], blick["definition"]["plot"]["type"]) == (
        "loud/x",
        "ok",
        "line",
    )
    assert blick["source"] == {"file": "blicks/loud.py", "line": 3}
    assert (data["errors"], data["warnings"]) == ([], [])
    minimal = json.loads(invoke("list", "--json", "--project", PROJECTS / "minimal").stdout)
    assert minimal["aliases"] == {"flows/steel_process": "flows/steel_by_process"}
    # A Blick lists its own tags; the group's are in the group.
    tags = (minimal["groups"][0]["tags"], minimal["blicks"][0]["definition"]["tags"])
    assert tags == (["mfa"], [])


@pytest.mark.parametrize("as_json", [[], ["--json"]])
def test_config_errors_are_one_line_on_stderr(tmp_path: Path, as_json: list[str]) -> None:
    root = make_project(tmp_path, {}, "blick = 1\n")
    result = invoke("list", "--project", root, *as_json)
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith(f"error: {root / 'pyproject.toml'}: unknown key 'blick'")
    assert result.stderr.count("\n") == 1


def test_no_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = invoke("list")
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith("error: no pyproject.toml with a [tool.blicket] section")


def _raise(exception: BaseException) -> object:
    def raise_it(*args: object) -> None:
        raise exception

    return raise_it


def test_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", _raise(RuntimeError("boom")))
    result = invoke("list", "--project", PROJECTS / "minimal")
    assert result.exit_code == 2
    assert result.stderr == (
        "error: unexpected RuntimeError: boom\n"
        "this is a bug in blicket; rerun with -v and report it\n"
    )
    verbose = invoke("list", "-v", "--project", PROJECTS / "minimal").stderr
    assert verbose.startswith("error: unexpected RuntimeError: boom\nTraceback (most recent")
    assert verbose.count("boom") == 1  # the exception line is not repeated after the traceback
    assert verbose.endswith("this is a bug in blicket; please report it\n")


def test_abort_and_click_errors_are_no_bugs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", _raise(typer.Abort()))
    aborted = invoke("list", "--project", PROJECTS / "minimal")
    assert (aborted.exit_code, aborted.stderr) == (2, "error: aborted\n")
    monkeypatch.setattr(cli, "discover", _raise(typer.BadParameter("no good")))
    bad = invoke("list", "--project", PROJECTS / "minimal")
    assert bad.exit_code == 2
    assert "no good" in bad.output
    assert "bug" not in bad.output


def test_every_command_maps_failures_to_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    arguments = {"list": [], "build": ["run"]}
    group: Any = typer.main.get_command(cli.app)
    assert set(group.commands) == set(arguments), "add the new command here"
    monkeypatch.setattr(cli, "_root", _raise(RuntimeError("boom")))
    for name, rest in arguments.items():
        result = invoke(name, *rest)
        assert result.exit_code == 2
        assert result.stderr.startswith("error: unexpected RuntimeError: boom\n")


def test_usage_error_exits_2() -> None:
    assert invoke("list", "--nope").exit_code == 2


def test_help_and_version() -> None:
    result = runner.invoke(cli.app, ["list", "--help"], terminal_width=200)
    assert "[tool.blicket]" in result.stdout
    assert "Exit codes: 0 success, 2 errors." in result.stdout
    assert invoke("--version").stdout == f"blicket {importlib.metadata.version('blicket')}\n"


# ---------------------------------------------------------------------------------------------
# build

RAISING = """

@bk.blick(plot=bk.plots.line(x="year", y="value"))
def missing(run):
    return run["missing"]
"""


def build_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str] | None = None
) -> str:
    """A committed project with one run, as the working directory; returns the short commit."""
    root = make_build_project(tmp_path, files or {"blicks/a.py": VALUES})
    make_run(root / "runs" / "a")
    monkeypatch.chdir(root)
    return commit_all(root)[:7]


def build(*args: str | Path) -> Result:
    """``blicket build`` with the load time replaced by 5 ms."""
    result = invoke("build", *args)
    result.stdout_bytes = re.sub(rb"loaded in [\d.]+ m?s", b"loaded in 5 ms", result.stdout_bytes)
    return result


def build_ids() -> list[str]:
    return [path.name for path in Path(".blicket/build").iterdir()]


def test_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit = build_project(tmp_path, monkeypatch)
    result = build("runs/a")
    assert result.exit_code == 0, result.output
    (build_id,) = build_ids()
    assert result.stdout == (
        f"run a · profile test · blicks at {commit} · loaded in 5 ms\n"
        "1 Blick: 1 built\n"
        f"build {build_id} → .blicket/build/{build_id}\n"
    )
    again = build("runs/a").stdout.splitlines()[2]
    assert again == f"build {build_id} → .blicket/build/{build_id} (built before, left as it was)"


def test_a_rebuild_prints_its_own_load_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_project(tmp_path, monkeypatch)
    assert invoke("build", "runs/a").exit_code == 0
    (build_id,) = build_ids()
    stored = manifest.read(Path(".blicket/build", build_id)).build.loader_ms
    load = builder.load
    monkeypatch.setattr(builder, "load", lambda *args: (*load(*args)[:2], 2500.0))
    lines = invoke("build", "runs/a").stdout.splitlines()
    assert lines[0].endswith("· loaded in 2.5 s")
    assert lines[2].endswith("(built before, left as it was)")
    assert manifest.read(Path(".blicket/build", build_id)).build.loader_ms == stored


def test_build_with_errors_and_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = VALUES.replace("@bk.blick(plot", '@bk.blick(order={"year": [1999]}, plot') + RAISING
    files = {"blicks/a.py": source, "blicks/broken.py": "import nothere\n"}
    commit = build_project(tmp_path, monkeypatch, files)
    Path("notes.txt").write_text("not committed")
    result = build("runs/a")
    assert result.exit_code == 2
    lines = result.stdout.splitlines()
    assert lines[0] == f"run a · profile test · blicks at {commit} (dirty) · loaded in 5 ms"
    assert lines[1] == (
        "2 Blicks: 1 built · 1 error · 1 import error · 1 warning · incomplete (Blicks missing)"
    )
    where, raised = line_of(source, "def missing") - 1, line_of(source, 'run["missing"]')
    assert lines[3:] == [
        "",
        "warnings",
        f"  blicks/a.py:{line_of(source, '@bk.blick(order')}  Blick a/values",
        "    order['year'] names 1999, which this run's table does not contain",
        "",
        "errors",
        f"  blicks/a.py:{where}  Blick a/missing",
        f"    transformation raised KeyError: 'missing' (raised at blicks/a.py:{raised})   "
        "(-v for the traceback)",
        "  blicks/broken.py:1  import failed   (-v for the traceback)",
        "    ModuleNotFoundError: No module named 'nothere'",
        f"    is 'nothere' installed in {sys.prefix}?",
        "    the Blicks in this file were skipped",
    ]
    verbose = invoke("build", "runs/a", "-v").stdout
    assert f'blicks/a.py", line {raised}, in missing' in verbose


def test_build_names_the_project_outside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_project(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    result = build("project/runs/a", "--project", "project")
    assert result.stdout.startswith(f"project: {(tmp_path / 'project').resolve()}\nrun a")
    assert "→ project/.blicket/build/" in result.stdout


def test_build_json_prints_the_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_project(tmp_path, monkeypatch)
    loader = Path("model_loader.py")
    loader.write_text("print('importing the loader')\n" + loader.read_text())
    result = invoke("build", "runs/a", "--json", "--out", "elsewhere")
    assert result.exit_code == 0
    assert "importing the loader" in result.stderr  # not before the JSON on stdout
    (build_id,) = [path.name for path in Path("elsewhere").iterdir()]
    assert result.stdout == Path("elsewhere", build_id, "manifest.json").read_text()


def test_build_without_a_buildable_blick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_project(tmp_path, monkeypatch, {"blicks/a.py": "import nothere\n"})
    result = invoke("build", "runs/a")
    assert result.exit_code == 2
    assert "\nerrors\n  blicks/a.py:1  import failed" in result.stdout
    assert result.stderr == "error: no Blick can be built, so no build was written\n"
    assert not Path(".blicket").exists()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["runs/nope"], "error: run path runs/nope does not exist\n"),
        (["runs/a", "--out", "pyproject.toml/x"], "error: cannot write the build to "),
    ],
)
def test_build_failures_are_one_line_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], message: str
) -> None:
    build_project(tmp_path, monkeypatch)
    result = invoke("build", *args)
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith(message)
    assert result.stderr.count("\n") == 1


def test_loader_failure_is_one_line_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = "def load_run(selection):\n    raise RuntimeError('no run here')\n"
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES, "model_loader.py": loader})
    make_run(tmp_path / "run")
    for as_json in ([], ["--json"]):
        result = invoke("build", tmp_path / "run", "--project", root, *as_json)
        assert (result.exit_code, result.stdout) == (2, "")
        assert result.stderr.startswith("error: loader ")
        assert result.stderr.count("\n") == 1
    verbose = invoke("build", tmp_path / "run", "--project", root, "-v").stderr
    assert verbose.splitlines()[1:3] == [
        "Traceback (most recent call last):",
        f'  File "{root / "model_loader.py"}", line 2, in load_run',
    ]


def test_a_closed_pipe_ends_quietly() -> None:
    script = Path(sys.executable).parent / "blicket"
    command = [script, "list", "--project", PROJECTS / "minimal"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        assert process.stdout is not None
        process.stdout.close()  # before blicket writes, as `blicket list | head -c0` does
        _, stderr = process.communicate()
    assert (process.returncode, stderr) == (0, b"")
