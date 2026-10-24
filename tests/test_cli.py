import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

import blicket as bk
from blicket import builder, cli, manifest, viewer
from tests.support import (
    PROJECTS,
    VALUES,
    commit_all,
    line_of,
    make_build_project,
    make_project,
    make_run,
    make_viewer,
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
    arguments = {"list": [], "build": ["run"], "serve": [], "push": ["dir"], "diff": ["a", "b"]}
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
    assert "Show the project's Blicks and any definition problems." in result.stdout
    assert "Exit codes" not in result.stdout  # the README has them
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


def test_a_rebuild_says_when_it_refreshes_the_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_project(tmp_path, monkeypatch)
    assert build("runs/a").exit_code == 0
    monkeypatch.setenv(viewer.VIEWER_ENV, str(make_viewer(tmp_path / "two", "two")))
    assert build("runs/a").stdout.splitlines()[2].endswith("(built before, viewer refreshed)")
    assert build("runs/a").stdout.splitlines()[2].endswith("(built before, left as it was)")


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


def test_build_needs_a_viewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_project(tmp_path, monkeypatch)
    monkeypatch.delenv(viewer.VIEWER_ENV)
    result = invoke("build", "runs/a")
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith("error: no viewer found: install a blicket release")


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


# ---------------------------------------------------------------------------------------------
# push and diff

# The Blick of VALUES with a year per value of the run.
YEARS = VALUES.replace("[2020, 2021, 2022]", 'list(range(2020, 2020 + len(run["values"])))')

# Four Blicks; with FACTOR above 1, the higher their number, the more they change.
MOVERS = "import polars as pl\n\nimport blicket as bk\n\nFACTOR = 1.0\n" + "".join(
    f'\n\n@bk.blick(plot=bk.plots.line(x="year", y="value"))\ndef m{number}(run):\n'
    f"    values = [v * (1 + {number} * (FACTOR - 1)) for v in run['values']]\n"
    '    return pl.DataFrame({"year": [2020, 2021, 2022], "value": values})\n'
    for number in range(1, 5)
)


@pytest.fixture
def commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A committed project with the runs a, b (2022 moved) and c (2023 added), as the working
    directory; returns the short commit."""
    return runs_project(tmp_path, monkeypatch)


def runs_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str = "") -> str:
    root = make_build_project(tmp_path, {"blicks/a.py": YEARS}, config)
    for name, values in (("a", "1 2 3"), ("b", "1 2 3.3"), ("c", "1 2 3 4")):
        make_run(root / "runs" / name, values)
    monkeypatch.chdir(root)
    return commit_all(root)[:7]


def built(run: str) -> str:
    """The build directory of ``run``."""
    return ".blicket/build/" + invoke("build", run).stdout.splitlines()[2].split()[1]


def name(directory: str) -> str:
    return Path(directory).name


def test_push_prints_where_the_build_went(commit: str) -> None:
    a = built("runs/a")
    result = invoke("push", a)
    expected = f"build {name(a)} → .blicket/store/builds/{name(a)}\n"
    assert (result.exit_code, result.stdout) == (0, expected)


def test_push_again_says_the_build_is_in_the_store(commit: str) -> None:
    a = built("runs/a")
    invoke("push", a)
    expected = f"build {name(a)} → .blicket/store/builds/{name(a)} (in the store already)\n"
    assert invoke("push", a).stdout == expected


def test_push_uses_the_store_setting_of_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_project(tmp_path, monkeypatch, 'store = "shared"\n')
    a = Path(built("runs/a")).resolve()
    monkeypatch.chdir(tmp_path)
    result = invoke("push", a, "--project", "project")
    assert result.stdout == f"build {a.name} → project/shared/builds/{a.name}\n"


def test_diff(commit: str) -> None:
    a, b = built("runs/a"), built("runs/b")
    result = invoke("diff", a, b)
    assert (result.exit_code, result.stdout) == (
        0,
        f"baseline {name(a)} · run a · profile test · blicks at {commit}\n"
        f"current  {name(b)} · run b · profile test · blicks at {commit}\n"
        "1 Blick: 1 value\n"
        "top movers: a/values 0.091 (year=2022)\n",
    )


def test_diff_takes_ids_from_the_store(commit: str) -> None:
    a, b = built("runs/a"), built("runs/b")
    expected = invoke("diff", a, b).stdout
    invoke("push", a)
    invoke("push", b)
    shutil.rmtree(".blicket/build")
    assert invoke("diff", name(a), name(b)).stdout == expected


def test_diff_takes_a_directory_beside_an_id(commit: str) -> None:
    a, b = built("runs/a"), built("runs/b")
    invoke("push", b)
    assert invoke("diff", a, name(b)).stdout == invoke("diff", a, b).stdout


def test_diff_finds_ids_in_the_store_of_the_project_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_project(tmp_path, monkeypatch, 'store = "shared"\n')
    a = name(built("runs/a"))
    invoke("push", f".blicket/build/{a}")
    monkeypatch.chdir(tmp_path)
    result = invoke("diff", a, a, "--project", "project")
    assert (result.exit_code, result.stdout.splitlines()[2]) == (0, "1 Blick: 1 unchanged")


def test_diff_of_two_directories_needs_no_project(tmp_path: Path, commit: str) -> None:
    a, c = (Path(built(run)).resolve() for run in ("runs/a", "runs/c"))
    os.chdir(tmp_path)
    result = invoke("diff", a, c)
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[2:] == [
        "1 Blick: 1 schema",
        "",
        "schema",
        "  a/values",
        "    year added: 2023",
    ]


def test_diff_shortens_long_lists_of_values(commit: str) -> None:
    make_run(Path("runs/d"), "1 2 3 4 5 6 7 8 9 10")
    lines = invoke("diff", built("runs/a"), built("runs/d")).stdout.splitlines()
    assert lines[-1] == "    year added: 2023, 2024, 2025, 2026, 2027 … and 2 more (all in --json)"


@pytest.mark.parametrize(("direction", "line"), [(1, "added"), (-1, "removed")])
def test_diff_names_the_columns_that_appeared_or_vanished(
    commit: str, direction: int, line: str
) -> None:
    before = built("runs/a")
    with_scenario = YEARS.replace('"value":', '"scenario": ["low"] * len(run["values"]), "value":')
    Path("blicks/a.py").write_text(with_scenario)
    builds = [before, built("runs/a")][::direction]
    lines = invoke("diff", *builds).stdout.splitlines()
    assert lines[2:] == [
        "1 Blick: 1 schema",
        "",
        "schema",
        "  a/values",
        f"    columns {line}: scenario (string)",
    ]


def test_diff_names_new_and_removed_blicks(commit: str) -> None:
    before = built("runs/a")
    Path("blicks/a.py").write_text(YEARS.replace("def values(", "def renamed("))
    lines = invoke("diff", before, built("runs/a")).stdout.splitlines()
    assert lines[2:] == [
        "2 Blicks: 1 new · 1 removed",
        "",
        "new",
        "  a/renamed",
        "",
        "removed",
        "  a/values",
    ]


def test_diff_says_which_new_blicks_did_not_build_in_the_baseline(commit: str) -> None:
    Path("blicks/a.py").write_text(YEARS + RAISING)
    before = built("runs/a")
    fixed = 'pl.DataFrame({"year": [2020, 2021, 2022], "value": run["values"]})'
    Path("blicks/a.py").write_text(YEARS + RAISING.replace('run["missing"]', fixed))
    lines = invoke("diff", before, built("runs/a")).stdout.splitlines()
    assert lines[2:] == [
        "2 Blicks: 1 unchanged · 1 new",
        "",
        "new",
        "  a/missing  did not build in the baseline",
    ]


def test_diff_says_how_many_more_blicks_moved(commit: str) -> None:
    Path("blicks/a.py").write_text(MOVERS)
    before = built("runs/a")
    Path("blicks/a.py").write_text(MOVERS.replace("FACTOR = 1.0", "FACTOR = 1.01"))
    lines = invoke("diff", before, built("runs/a")).stdout.splitlines()
    assert lines[2:] == [
        "4 Blicks: 4 value",
        "top movers: a/m4 0.038 (year=2022)",
        "            a/m3 0.029 (year=2022)",
        "            a/m2 0.02 (year=2022)",
        "            … and 1 more (all in --json)",
    ]


def test_diff_json_is_the_comparison(commit: str) -> None:
    result = invoke("diff", built("runs/a"), built("runs/b"), "--json")
    assert result.exit_code == 0
    comparison = bk.Comparison.model_validate_json(result.stdout)
    assert json.loads(comparison.model_dump_json()) == json.loads(result.stdout)
    assert (comparison.baseline.run, comparison.current.run) == ("a", "b")
    assert comparison.blicks[0].change.flags == {"value"}


def test_diff_exits_2_for_a_blick_in_error(commit: str) -> None:
    before = built("runs/a")
    Path("blicks/a.py").write_text(YEARS + RAISING)
    result = invoke("diff", before, built("runs/a"))
    raised = line_of(YEARS + RAISING, 'run["missing"]')
    assert result.exit_code == 2
    assert result.stdout.splitlines()[2:] == [
        "2 Blicks: 1 unchanged · 1 error",
        "",
        "errors",
        f"  a/missing  transformation raised KeyError: 'missing' (raised at blicks/a.py:{raised})",
    ]


def test_diff_exits_2_for_an_incomplete_current_build(commit: str) -> None:
    before = built("runs/a")
    Path("blicks/broken.py").write_text("import nothere\n")
    result = invoke("diff", before, built("runs/a"))
    assert result.exit_code == 2
    lines = result.stdout.splitlines()
    assert lines[1].endswith(f"blicks at {commit} (dirty) · incomplete (Blicks missing)")
    assert lines[2:] == [
        "1 Blick: 1 unchanged · removed not judged",
        "removed not judged: blicks/broken.py failed to import",
    ]


def test_diff_exits_2_for_an_unknown_plot_type(commit: str) -> None:
    a = built("runs/a")
    shutil.copytree(a, "custom")
    data = json.loads(Path("custom/manifest.json").read_text())
    data["blicks"][0]["definition"]["plot"]["type"] = "custom"
    Path("custom/manifest.json").write_text(json.dumps(data))
    result = invoke("diff", a, "custom")
    assert result.exit_code == 2
    assert result.stdout.splitlines()[-1].startswith("  a/values  no built-in plot type 'custom'")


def test_diff_marks_an_incomplete_baseline_but_exits_0(commit: str) -> None:
    current = built("runs/a")
    Path("blicks/broken.py").write_text("import nothere\n")
    result = invoke("diff", built("runs/a"), current)
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].endswith("(dirty) · incomplete (Blicks missing)")


def test_diff_of_builds_without_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(make_build_project(tmp_path, {"blicks/a.py": YEARS}))
    a = built(str(make_run(Path("runs/a"))))
    assert invoke("diff", a, a).stdout.splitlines()[0].endswith("profile test · no git commit")


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ("runs", "error: runs has no manifest.json; pass a build directory"),
        ("results", "error: results is neither a build directory nor the id of a build in "),
        ("0123456789abcdef", "error: 0123456789abcdef is neither a build directory nor the id "),
    ],
)
def test_diff_of_a_build_that_cannot_be_found(commit: str, given: str, message: str) -> None:
    result = invoke("diff", given, built("runs/a"))
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith(message)
    assert result.stderr.count("\n") == 1


def test_diff_names_the_store_relative_to_the_working_directory(commit: str) -> None:
    result = invoke("diff", "results", "results")
    assert result.stderr == (
        "error: results is neither a build directory nor the id of a build in .blicket/store "
        "(blicket push adds one)\n"
    )


def test_diff_outside_a_project_has_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = invoke("diff", "0123456789abcdef", "x")
    assert result.stderr == (
        "error: 0123456789abcdef is neither a build directory nor a build id (no project here, so "
        "no store; run inside the project or pass --project)\n"
    )
