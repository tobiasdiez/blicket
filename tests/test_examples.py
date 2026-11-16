"""The example project ``examples/coherence``, which needs no data from elsewhere: its two runs
give the outcomes its README states."""

import importlib.util
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blicket import cli
from tests.support import commit_all

runner = CliRunner()
EXAMPLE = Path(__file__).parent.parent / "examples" / "coherence"
FILES = ["pyproject.toml", "blicketconf.py", "make_runs.py", "blicks", "runs"]


@pytest.fixture
def example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed copy of the example as the working directory."""
    root = tmp_path / "coherence"
    root.mkdir()
    for name in FILES:
        source = EXAMPLE / name
        if source.is_dir():
            shutil.copytree(source, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, root / name)
    commit_all(root)
    monkeypatch.chdir(root)
    return root


def results(output: str) -> dict[str, str]:
    """The result of each expectation not met, by the unit's id, from a report's sections."""
    found = {}
    section = None
    for line in output.splitlines():
        if line in ("expectations warned", "expectations failed"):
            section = line.split()[1]
        elif not line.strip():
            section = None
        elif section and line.startswith("  blicks/"):
            found[line.split()[-1]] = section
    return found


def test_the_baseline_run_is_coherent_up_to_round_off(example: Path) -> None:
    result = runner.invoke(cli.app, ["check", "runs/baseline"])
    assert result.exit_code == 0, result.output
    assert "3 Blicks: 3 built\n3 checks: 3 ran\nexpectations: 5 met · 1 warning\n" in result.stdout
    assert results(result.stdout) == {"cycle/flows": "warned"}


def test_the_changed_run_fails_two_expectations_and_breaks_three(example: Path) -> None:
    pushed = runner.invoke(cli.app, ["check", "runs/baseline", "--push"])
    assert pushed.exit_code == 0, pushed.output
    result = runner.invoke(cli.app, ["check", "runs/changed", "--exit-zero-on-changes"])
    assert result.exit_code == 1, result.output
    assert "expectations: 2 met · 2 warnings · 2 failed\n" in result.stdout
    assert results(result.stdout) == {
        "cycle/flows": "warned",
        "cycle/recycling_rate": "warned",
        "checks/stock_balance": "failed",
        "cycle/end_use_split": "failed",
    }
    assert "expectations vs baseline: 3 broken · 1 still failing\n" in result.stdout
    assert "flagged: 3 of 3 Blicks · failed: 2 expectations\n" in result.stdout


def test_make_runs_writes_the_runs_of_the_repository(example: Path, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("make_runs", example / "make_runs.py")
    assert spec is not None
    assert spec.loader is not None
    make_runs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_runs)
    for name, changed in (("baseline", False), ("changed", True)):
        make_runs.write(tmp_path / name, make_runs.run(changed=changed))
        written = {file.name: file.read_text() for file in (tmp_path / name).iterdir()}
        kept = {file.name: file.read_text() for file in (EXAMPLE / "runs" / name).iterdir()}
        assert written == kept
