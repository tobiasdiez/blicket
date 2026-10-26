"""``blicket check``: the baseline it finds, what it prints and writes, and its exit codes."""

import json
import re
from datetime import UTC
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner, Result

import blicket as bk
from blicket import cli, manifest
from blicket.baseline import FETCH_HINT
from tests.support import VALUES, commit_all, git, make_build_project, make_run

runner = CliRunner()

CHANGED = VALUES.replace('run["values"]', "[1.0, 2.0, 3.3]")

# The Blick of VALUES with a year per value of the run.
YEARS = VALUES.replace("[2020, 2021, 2022]", 'list(range(2020, 2020 + len(run["values"])))')

RAISING = """

@bk.blick(plot=bk.plots.line(x="year", y="value"))
def missing(run):
    return run["missing"]
"""


def invoke(*args: str | Path) -> Result:
    """``blicket`` with the load time replaced by 5 ms."""
    result = runner.invoke(cli.app, [str(arg) for arg in args])
    result.stdout_bytes = re.sub(rb"loaded in [\d.]+ m?s", b"loaded in 5 ms", result.stdout_bytes)
    return result


def check(*args: str | Path) -> Result:
    return invoke("check", *args)


def built(result: Result) -> str:
    """The id of the build ``check`` or ``build`` made."""
    return result.stdout.splitlines()[2].split()[1]


def made(build_id: str) -> str:
    """When the build ``build_id`` was made, as a baseline line shows it."""
    created = manifest.read(Path(".blicket/build", build_id)).created_at
    return created.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


@pytest.fixture
def commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A committed project with the runs a, rerun (the values of a in another file) and b (2022
    moved), as the working directory; returns the short commit."""
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    for name, values in (("a", "1 2 3"), ("rerun", "1 2 3\n"), ("b", "1 2 3.3")):
        make_run(root / "runs" / name, values)
    monkeypatch.chdir(root)
    return commit_all(root)[:7]


def test_without_a_baseline(commit: str) -> None:
    result = check("runs/a")
    assert result.exit_code == 0, result.output
    a = built(result)
    assert result.stdout == (
        f"run a · profile test · blicks at {commit} · loaded in 5 ms\n"
        "1 Blick: 1 built\n"
        f"build {a} → .blicket/build/{a}\n"
        "\n"
        "baseline: none (no other pushed build of profile test)\n"
    )
    assert not Path(".blicket/build", a, "compare").exists()


def test_json_without_a_baseline_prints_null(commit: str) -> None:
    result = check("runs/a", "--json")
    assert (result.exit_code, result.stdout) == (0, "null\n")
    assert result.stderr.endswith("baseline: none (no other pushed build of profile test)\n")


def test_json_keeps_the_report_on_stderr(commit: str) -> None:
    result = check("runs/a", "--against", "nonsense", "--json")
    assert (result.exit_code, result.stdout) == (2, "null\n")
    assert result.stderr.splitlines()[-1] == (
        "error: no baseline: nonsense is neither a build directory, a build in the store, nor a "
        "git ref"
    )


def test_json_prints_null_when_nothing_builds(commit: str) -> None:
    Path("blicks/a.py").write_text("import nothere\n")
    result = check("runs/a", "--json")
    assert (result.exit_code, result.stdout) == (2, "null\n")
    assert "\nerrors\n  blicks/a.py:1  import failed" in result.stderr


def test_an_unchanged_rerun(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    result = check("runs/rerun", "--push")
    assert result.exit_code == 0, result.output
    rerun = built(result)
    assert result.stdout.splitlines()[4:] == [
        f"baseline {a} · run a · blicks at {commit} · built {made(a)}",
        "vs baseline: 1 unchanged",
        "nothing flagged",
        f"comparison → .blicket/build/{rerun}/compare/{a}",
        f"build {rerun} → .blicket/store/builds/{rerun} (with the comparisons against {a})",
    ]


def test_a_retry_finds_the_same_baseline_not_its_own_build(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    check("runs/rerun", "--push")
    lines = check("runs/rerun", "--push").stdout.splitlines()
    assert lines[4].startswith(f"baseline {a} · ")
    assert lines[-1].endswith(
        "(in the store already, left as it was; comparisons are not added to a stored build)"
    )


def test_a_changed_transformation_is_flagged(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    Path("blicks/a.py").write_text(CHANGED)
    result = check("runs/a")
    assert result.exit_code == 1
    current = built(result)
    lines = result.stdout.splitlines()
    assert lines[0] == f"run a · profile test · blicks at {commit} (dirty) · loaded in 5 ms"
    assert lines[4:] == [
        f"baseline {a} · run a · blicks at {commit} · built {made(a)}",
        "vs baseline: 1 value",
        "top movers: a/values 9.1% of scale (year=2022)",
        "flagged: 1 of 1 Blick",
        f"comparison → .blicket/build/{current}/compare/{a}",
    ]
    written = Path(".blicket/build", current, "compare", a, "comparison.json").read_text()
    (blick,) = bk.Comparison.model_validate_json(written).blicks
    assert (blick.change.flags, blick.baseline_data) == (
        {"value"},
        f"compare/{a}/blicks/a/values.parquet",
    )


def test_json_prints_the_comparison_written(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    result = check("runs/b", "--json")
    assert result.exit_code == 1
    b = result.stderr.splitlines()[2].split()[1]
    written = Path(".blicket/build", b, "compare", a, "comparison.json").read_text()
    assert json.loads(result.stdout) == json.loads(written)
    assert "\nflagged: 1 of 1 Blick\n" in result.stderr


def test_long_lists_of_values_are_shortened_without_a_pointer(commit: str) -> None:
    Path("blicks/a.py").write_text(YEARS)
    a = built(check("runs/a", "--push"))
    make_run(Path("runs/d"), "1 2 3 4 5 6 7 8 9 10")
    result = check("runs/d")
    assert result.exit_code == 1
    assert result.stdout.splitlines()[-1] == (
        "    year added: 2023, 2024, 2025, 2026, 2027 … and 2 more"
    )
    assert result.stdout.splitlines()[4].startswith(f"baseline {a}")


def test_a_failing_blick_exits_2_and_its_error_is_listed_once(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    Path("blicks/a.py").write_text(VALUES + RAISING)
    result = check("runs/a")
    assert result.exit_code == 2
    assert result.stdout.count("transformation raised KeyError") == 1
    current = built(result)
    assert result.stdout.endswith(
        "\n\n"
        f"baseline {a} · run a · blicks at {commit} · built {made(a)}\n"
        "vs baseline: 1 unchanged · 1 error\n"
        "flagged: 1 of 2 Blicks\n"
        f"comparison → .blicket/build/{current}/compare/{a}\n"
    )


def test_an_incomplete_build_with_nothing_flagged_says_so(commit: str) -> None:
    check("runs/a", "--push")
    Path("blicks/broken.py").write_text("import nothere\n")
    result = check("runs/a")
    assert result.exit_code == 2
    assert "\nnothing flagged, but the build is incomplete\n" in result.stdout


def test_an_error_only_the_comparison_finds_is_listed(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    repeated = pl.DataFrame({"year": [2020, 2020], "value": [1.0, 2.0]})
    repeated.write_parquet(Path(".blicket/store/builds", a, "blicks", "a", "values.parquet"))
    result = check("runs/b")
    assert result.exit_code == 2
    assert result.stdout.splitlines()[5:] == [
        "vs baseline: 1 error",
        "flagged: 1 of 1 Blick",
        f"comparison → .blicket/build/{built(result)}/compare/{a}",
        "",
        "errors",
        "  a/values  dimension values must be unique in each table",
    ]


def unknown_commit(build_id: str) -> None:
    """Make the stored build ``build_id`` record a commit no repository has."""
    stored = Path(".blicket/store/builds", build_id, "manifest.json")
    data = json.loads(stored.read_text())
    data["repository"]["commit"] = "f" * 40
    stored.write_text(json.dumps(data))


def test_builds_only_at_commits_unknown_to_the_clone_exit_2(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    unknown_commit(a)
    result = check("runs/b")
    assert result.exit_code == 2
    assert result.stdout.splitlines()[4:] == [
        f"error: no baseline: 1 pushed build of profile test at a commit this clone lacks: {a} "
        f"(fffffff); {FETCH_HINT}"
    ]


def test_newer_builds_at_unknown_commits_are_a_warning(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    rerun = built(check("runs/rerun", "--push"))
    unknown_commit(rerun)
    result = check("runs/b")
    assert result.exit_code == 1
    assert result.stdout.splitlines()[4:6] == [
        f"warning: 1 newer build at a commit this clone lacks was skipped: {rerun} (fffffff); "
        f"{FETCH_HINT}",
        f"baseline {a} · run a · blicks at {commit} · built {made(a)}",
    ]


def test_push_on_exit_1_takes_the_comparison_along(commit: str) -> None:
    a = built(check("runs/a", "--push"))
    result = check("runs/b", "--push")
    assert result.exit_code == 1
    b = built(result)
    assert result.stdout.splitlines()[-1] == (
        f"build {b} → .blicket/store/builds/{b} (with the comparisons against {a})"
    )
    compare = Path(".blicket/store/builds", b, "compare")
    assert sorted(p.relative_to(compare).as_posix() for p in compare.rglob("*") if p.is_file()) == [
        f"{a}/blicks/a/values.parquet",
        f"{a}/comparison.json",
        "index.json",
    ]


def test_the_step_summary_receives_the_markdown(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("before\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    a = built(check("runs/a", "--push"))
    b = built(check("runs/b"))
    entries = summary.read_text().split("### ")
    assert entries[:2] == [
        "before\n",
        f"blicket: run a (`{a[:8]}`)\n\nbaseline: none (no other pushed build of profile test)\n",
    ]
    assert entries[2].startswith(f"blicket: run b (`{b[:8]}`) against run a (`{a[:8]}`)\n")
    assert entries[2].endswith("| `a/values` | value | 9.1% | year=2022 |\n")


def test_the_step_summary_receives_a_failed_resolution(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    a = built(check("runs/a", "--against", "nonsense"))
    assert summary.read_text() == (
        f"### blicket: run a (`{a[:8]}`)\n\nerror: no baseline: nonsense is neither a build "
        "directory, a build in the store, nor a git ref\n"
    )


def test_an_unwritable_step_summary_is_a_warning_at_the_end(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))
    check("runs/a", "--push")
    result = check("runs/b", "--push")
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[-2].startswith(f"build {built(result)} → .blicket/store/builds/")
    assert lines[-1] == f"warning: cannot append to GITHUB_STEP_SUMMARY {tmp_path}: Is a directory"


def test_a_damaged_build_in_the_store_is_a_warning(commit: str) -> None:
    damaged = Path(".blicket/store/builds/1111111111111111")
    damaged.mkdir(parents=True)
    (damaged / "manifest.json").write_text("not json")
    result = check("runs/a")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[4:] == [
        f"warning: skipped a build in the store: build directory {damaged.resolve()} has no "
        "readable manifest.json (not valid JSON); delete it and rebuild",
        "baseline: none (no other pushed build of profile test)",
    ]


def test_the_baseline_line_names_another_profile(commit: str) -> None:
    make_run(Path("runs/policy"), profile="policy")
    policy = built(invoke("build", "runs/policy"))
    result = check("runs/a", "--against", f".blicket/build/{policy}")
    assert result.stdout.splitlines()[4] == (
        f"baseline {policy} · run policy · profile policy · blicks at {commit} (dirty) · "
        f"built {made(policy)}"
    )


def test_the_baseline_line_marks_an_incomplete_build(commit: str) -> None:
    Path("blicks/broken.py").write_text("import nothere\n")
    incomplete = built(invoke("build", "runs/a"))
    Path("blicks/broken.py").unlink()
    result = check("runs/a", "--against", f".blicket/build/{incomplete}")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[4] == (
        f"baseline {incomplete} · run a · blicks at {commit} (dirty) · incomplete (Blicks "
        f"missing) · built {made(incomplete)}"
    )


@pytest.fixture
def outside_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A project outside git with the runs a and b, as the working directory."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(make_build_project(tmp_path, {"blicks/a.py": VALUES}))
    make_run(Path("runs/a"))
    make_run(Path("runs/b"), "1 2 3.3")


def test_outside_git_without_pushed_builds_there_is_no_baseline(outside_git: None) -> None:
    result = check("runs/a")
    assert result.exit_code == 0
    assert result.stdout.endswith("\n\nbaseline: none (no other pushed build of profile test)\n")


def test_outside_git_pushed_builds_must_be_named(outside_git: None) -> None:
    a = built(check("runs/a", "--push"))
    result = check("runs/b")
    assert result.exit_code == 2
    assert result.stdout.endswith(
        "\n\nerror: no baseline: the build records no git commit; 1 pushed build of profile "
        f"test: {a}; pass it as --against\n"
    )


def test_outside_git_a_named_baseline_is_compared(outside_git: None) -> None:
    a = built(check("runs/a"))
    result = check("runs/a", "--against", f".blicket/build/{a}")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[-4:] == [
        f"baseline {a} · run a · no git commit · built {made(a)}",
        "vs baseline: 1 unchanged",
        "nothing flagged",
        f"comparison → .blicket/build/{a}/compare/{a}",
    ]


def feature_branch() -> None:
    """Check out a new branch ``feature`` and commit a changed transformation on it."""
    git(Path(), "checkout", "-q", "-b", "feature")
    Path("blicks/a.py").write_text(CHANGED)
    git(Path(), "commit", "-q", "-am", "feature")


def baseline_of(result: Result) -> str:
    return result.stdout.splitlines()[4].split()[1]


def test_a_feature_branch_compares_with_mains_build(commit: str) -> None:
    main = built(check("runs/a", "--push"))
    feature_branch()
    result = check("runs/a")
    assert (result.exit_code, baseline_of(result)) == (1, main)


@pytest.fixture
def branched(commit: str) -> tuple[str, str]:
    """main's build of run a pushed, then the build of run a on ``feature`` pushed too; returns
    the two build ids."""
    main = built(check("runs/a", "--push"))
    feature_branch()
    return main, built(check("runs/a", "--push"))


def test_at_the_next_commit_the_branchs_build_is_the_baseline(branched: tuple[str, str]) -> None:
    main, feature = branched
    git(Path(), "commit", "-q", "--allow-empty", "-m", "more")
    result = check("runs/a")
    assert (result.exit_code, baseline_of(result)) == (0, feature)
    against = check("runs/a", "--against", "main")
    assert (against.exit_code, baseline_of(against)) == (1, main)


def test_after_the_merge_main_compares_with_the_branchs_build(branched: tuple[str, str]) -> None:
    _, feature = branched
    git(Path(), "checkout", "-q", "main")
    git(Path(), "merge", "-q", "--no-ff", "-m", "merge", "feature")
    result = check("runs/a")
    assert (result.exit_code, baseline_of(result)) == (0, feature)
    assert result.stdout.splitlines()[5] == "vs baseline: 1 unchanged"
