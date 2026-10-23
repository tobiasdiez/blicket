import importlib.metadata
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from blicket import cli
from tests.support import PROJECTS, make_project, one_blick

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
    root = make_project(tmp_path, {"blicks/loud.py": "print('hello')\n" + one_blick("loud/x")})
    result = invoke("list", "--json", "--project", root)
    assert result.exit_code == 0
    data = json.loads(result.stdout)  # what the module printed went to stderr
    assert "hello" in result.stderr
    assert data["blicket"] == importlib.metadata.version("blicket")
    (blick,) = data["blicks"]
    assert (blick["id"], blick["plot"]["type"]) == ("loud/x", "line")
    assert blick["source"] == {"file": "blicks/loud.py", "line": 3}
    assert (data["failed"], data["errors"], data["warnings"]) == ([], [], [])
    minimal = json.loads(invoke("list", "--json", "--project", PROJECTS / "minimal").stdout)
    assert minimal["aliases"] == {"flows/steel_process": "flows/steel_by_process"}


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


def test_every_command_maps_failures_to_exit_2() -> None:
    group: Any = typer.main.get_command(cli.app)
    assert all(isinstance(command, cli._Command) for command in group.commands.values())


def test_usage_error_exits_2() -> None:
    assert invoke("list", "--nope").exit_code == 2


def test_help_and_version() -> None:
    result = runner.invoke(cli.app, ["list", "--help"], terminal_width=200)
    assert "[tool.blicket]" in result.stdout
    assert "Exit codes: 0 success, 2 errors." in result.stdout
    assert invoke("--version").stdout == f"blicket {importlib.metadata.version('blicket')}\n"
