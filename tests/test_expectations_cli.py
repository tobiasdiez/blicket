"""Expectations and checks on the command line: what ``build``, ``check``, ``diff`` and ``list``
print, the Markdown step summary, and the exit codes."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

import blicket as bk
from blicket import cli
from blicket.report import outcome_sentence
from tests.support import commit_all, line_of, make_build_project, make_run

runner = CliRunner()
DASH = "\N{EN DASH}"  # an empty cell

UNITS = """\
import polars as pl

import blicket as bk

bk.group("units", title="Units")


def table(run):
    years = list(range(2020, 2020 + len(run["values"])))
    return pl.DataFrame({"year": years, "value": run["values"]})


@bk.blick(plot=bk.plots.line(x="year", y="value"), expect=bk.expect.at_most(2.5))
def bounded(run):
    return table(run)


@bk.check(title="Values are not negative", expect=bk.expect.no_rows(by="value", warn_within=0.5))
def negative(run):
    return table(run).filter(pl.col("value") < 0)
"""
BOUNDED = line_of(UNITS, "def bounded") - 1
NEGATIVE = line_of(UNITS, "def negative") - 1

RAISING = """

@bk.check
def raising(run):
    return run["missing"]
"""

# The runs: met, a warned check, a failed Blick, a failed check, a changed but met Blick, and
# reruns of the met and the failed one in another file, so another build.
RUNS = {
    "met": "1 2 2",
    "warned": "1 -0.2 2",
    "failed": "1 2 3",
    "negative": "1 -2 2",
    "moved": "1 2 2.4",
    "met_again": "1 2 2\n",
    "failed_again": "1 2 3\n",
}


def invoke(*args: str | Path) -> Result:
    """``blicket`` with the load time replaced by 5 ms."""
    result = runner.invoke(cli.app, [str(arg) for arg in args])
    result.stdout_bytes = re.sub(rb"loaded in [\d.]+ m?s", b"loaded in 5 ms", result.stdout_bytes)
    result.stderr_bytes = re.sub(rb"loaded in [\d.]+ m?s", b"loaded in 5 ms", result.stderr_bytes)
    return result


@pytest.fixture
def commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A committed project with the units above and the runs of ``RUNS``, as the working
    directory; returns the short commit."""
    root = make_build_project(tmp_path, {"blicks/units.py": UNITS})
    for name, values in RUNS.items():
        make_run(root / "runs" / name, values)
    monkeypatch.chdir(root)
    return commit_all(root)[:7]


def built(result: Result) -> str:
    """The id of the build ``build`` or ``check`` made."""
    line = next(line for line in result.stdout.splitlines() if line.startswith("build "))
    return line.split()[1]


# ---------------------------------------------------------------------------------------------
# build


def test_build_reports_the_checks_and_the_outcomes_and_exits_1_for_a_failure(commit: str) -> None:
    result = invoke("build", "runs/failed")
    assert result.exit_code == 1, result.output
    build_id = built(result)
    assert result.stdout == (
        f"run failed · profile test · blicks at {commit} · loaded in 5 ms\n"
        "1 Blick: 1 built\n"
        "1 check: 1 ran\n"
        "expectations: 1 met · 1 failed\n"
        f"build {build_id} → .blicket/build/{build_id}\n"
        "\n"
        "expectations failed\n"
        f"  blicks/units.py:{BOUNDED}  Blick units/bounded\n"
        "    1 of 3 rows offends: expected value at most 2.5\n"
        "    worst 3 at year=2022\n"
    )


def test_build_reports_a_warning_and_exits_0(commit: str) -> None:
    result = invoke("build", "runs/warned")
    assert result.exit_code == 0, result.output
    assert result.stdout.endswith(
        "\n"
        "expectations warned\n"
        f"  blicks/units.py:{NEGATIVE}  check units/negative\n"
        "    1 row offends, all within warn_within: expected no rows, by value, a warning within "
        "0.5\n"
        "    worst -0.2 at year=2021\n"
    )
    assert "expectations: 1 met · 1 warning\n" in result.stdout


def test_build_exits_0_when_every_expectation_is_met(commit: str) -> None:
    result = invoke("build", "runs/met")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[1:4] == [
        "1 Blick: 1 built",
        "1 check: 1 ran",
        "expectations: 2 met",
    ]


def test_build_exits_2_on_errors_even_with_a_failed_expectation(commit: str) -> None:
    Path("blicks/units.py").write_text(UNITS + RAISING)
    result = invoke("build", "runs/failed")
    assert result.exit_code == 2
    assert "2 checks: 1 ran · 1 error\n" in result.stdout
    assert result.stdout.endswith(
        "\nerrors\n"
        f"  blicks/units.py:{line_of(UNITS + RAISING, 'def raising') - 1}  check units/raising\n"
        "    check raised KeyError: 'missing' (raised at blicks/units.py:"
        f"{line_of(UNITS + RAISING, 'run["missing"]')})   (-v for the traceback)\n"
    )


def test_an_expectation_that_cannot_be_evaluated_is_an_error(commit: str) -> None:
    Path("blicks/units.py").write_text(UNITS.replace("at_most(2.5)", 'at_most(2.5, on="share")'))
    result = invoke("build", "runs/met")
    assert result.exit_code == 2
    assert result.stdout.endswith(
        "\nerrors\n"
        f"  blicks/units.py:{BOUNDED}  Blick units/bounded\n"
        "    cannot evaluate share at most 2.5: on= names 'share', which is no column of the "
        "table; its measures are value\n"
    )
    assert "expectations: 1 met · 1 cannot be evaluated\n" in result.stdout


def test_a_level_off_check_is_skipped_and_a_warn_level_keeps_exit_0(commit: str) -> None:
    Path("pyproject.toml").write_text(Path("pyproject.toml").read_text() + 'level = "warn"\n')
    Path("blicks/units.py").write_text(UNITS.replace("@bk.check(", '@bk.check(level="off", '))
    result = invoke("build", "runs/failed")
    assert result.exit_code == 0, result.output
    assert "1 check: 0 ran · 1 skipped\nexpectations: 1 warning\n" in result.stdout
    assert "\nskipped\n  its level is off\n    units/negative\n" in result.stdout


def test_build_json_holds_the_outcomes(commit: str) -> None:
    result = invoke("build", "runs/negative", "--json")
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    (check,) = data["checks"]
    assert (check["outcome"]["result"], check["data"]) == (
        "failed",
        "checks/units/negative.parquet",
    )


# ---------------------------------------------------------------------------------------------
# check


def test_check_without_a_baseline_exits_1_for_a_failed_expectation(commit: str) -> None:
    result = invoke("check", "runs/negative")
    assert result.exit_code == 1
    assert result.stdout.endswith("\n\nbaseline: none (no other pushed build of profile test)\n")
    json_result = invoke("check", "runs/negative", "--json")
    assert (json_result.exit_code, json_result.stdout) == (1, "null\n")


def test_check_reports_the_transitions_and_the_verdict(commit: str) -> None:
    invoke("check", "runs/met", "--push")
    result = invoke("check", "runs/failed")
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[lines.index("vs baseline: 1 value") + 1] == "expectations vs baseline: 1 broken"
    assert "flagged: 1 of 1 Blick · failed: 1 expectation" in lines
    assert lines[-2:] == ["expectations broken", "  Blick units/bounded  failed, was met"]


def test_check_names_the_units_of_each_transition_but_still_failing(commit: str) -> None:
    invoke("check", "runs/negative", "--push")
    result = invoke("check", "runs/failed")
    assert result.exit_code == 1
    assert "expectations vs baseline: 1 broken · 1 fixed\n" in result.stdout
    assert result.stdout.endswith(
        "\n\nexpectations fixed\n  check units/negative  met, was failed\n"
        "\nexpectations broken\n  Blick units/bounded  failed, was met\n"
    )


@pytest.mark.parametrize(
    ("baseline", "current", "codes"),
    [
        ("met", "met_again", (0, 0)),
        ("met", "moved", (1, 0)),  # flagged only
        ("failed", "failed_again", (1, 1)),  # a failed expectation, still failing
        ("met", "failed", (1, 1)),  # flagged and failed
    ],
)
def test_check_exits_1_for_flagged_blicks_unless_exit_zero_on_changes(
    commit: str, baseline: str, current: str, codes: tuple[int, int]
) -> None:
    invoke("check", f"runs/{baseline}", "--push")
    plain = invoke("check", f"runs/{current}")
    zero = invoke("check", f"runs/{current}", "--exit-zero-on-changes")
    assert (plain.exit_code, zero.exit_code) == codes, plain.output
    assert "\nbaseline: none" not in plain.stdout
    # The second build of the run is the first's, which its report says.
    assert zero.stdout.replace(" (built before, left as it was)", "") == plain.stdout


def test_check_exits_2_on_errors_with_exit_zero_on_changes_too(commit: str) -> None:
    invoke("check", "runs/met", "--push")
    Path("blicks/units.py").write_text(UNITS + RAISING)
    assert invoke("check", "runs/moved", "--exit-zero-on-changes").exit_code == 2


def test_the_step_summary_lists_the_expectations(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    first = built(invoke("check", "runs/negative", "--push"))
    assert summary.read_text() == (
        f"### blicket: run negative (`{first[:8]}`)\n\n"
        "baseline: none (no other pushed build of profile test)\n"
        "\n"
        "#### expectations\n"
        "\n"
        "| Blick or check | result | rows | worst | where |\n"
        "|---|---|---|---|---|\n"
        "| check `units/negative` | failed | 1 row offends | -2 | year=2021 |\n"
    )
    summary.write_text("")
    invoke("check", "runs/failed")
    assert summary.read_text().endswith(
        "\n#### expectations\n"
        "\n"
        "| Blick or check | result | rows | worst | where | against the baseline |\n"
        "|---|---|---|---|---|---|\n"
        "| Blick `units/bounded` | failed | 1 of 3 rows offends | 3 | year=2022 | broken (was met) "
        "|\n"
        f"| check `units/negative` | met | {DASH} | {DASH} | {DASH} | fixed (was failed) |\n"
    )


# ---------------------------------------------------------------------------------------------
# diff and list


def test_diff_reports_the_transitions_and_exits_0(commit: str) -> None:
    met = built(invoke("build", "runs/met"))
    failed = built(invoke("build", "runs/failed"))
    result = invoke("diff", f".blicket/build/{met}", f".blicket/build/{failed}")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[2:4] == ["1 Blick: 1 value", "expectations vs baseline: 1 broken"]
    assert lines[-2:] == ["expectations broken", "  Blick units/bounded  failed, was met"]


def test_list_shows_the_checks_their_expectations_and_levels(commit: str) -> None:
    result = invoke("list")
    assert result.exit_code == 0, result.output
    assert result.stdout == (
        "units  Units\n"
        "  units/bounded    Bounded                   line    expect: at most 2.5\n"
        "  units/negative   Values are not negative   check   expect: no rows, by value, a "
        "warning within 0.5\n"
        "\n"
        "1 group · 1 Blick · 1 check\n"
    )


def test_list_shows_a_level_that_is_not_error(commit: str) -> None:
    Path("pyproject.toml").write_text(Path("pyproject.toml").read_text() + 'level = "warn"\n')
    Path("blicks/units.py").write_text(
        UNITS.replace(
            'bk.group("units", title="Units")', 'bk.group("units", title="Units", level="off")'
        ).replace("@bk.check(", '@bk.check(level="error", ')
    )
    lines = invoke("list").stdout.splitlines()
    assert lines[0] == "units  Units  level: off"
    assert lines[1].endswith("expect: at most 2.5   level: off")
    assert lines[2].endswith("a warning within 0.5")


def test_list_json_has_the_checks_with_their_levels(commit: str) -> None:
    data = json.loads(invoke("list", "--json").stdout)
    (check,) = data["checks"]
    assert (check["id"], check["level"], check["definition"]["expect"]["by"]) == (
        "units/negative",
        "error",
        "value",
    )
    assert [blick["id"] for blick in data["blicks"]] == ["units/bounded"]
    assert data["blicks"][0]["definition"]["expect"]["kind"] == "at_most"


def test_list_counts_the_checks_with_errors(commit: str) -> None:
    Path("blicks/units.py").write_text(UNITS + '\nbk.register_check(id="units/bad", transform=1)\n')
    result = invoke("list")
    assert result.exit_code == 2
    assert "1 group · 1 Blick · 2 checks (1 with errors) · 1 error\n" in result.stdout
    assert "\nerrors\n  blicks/units.py:" in result.stdout
    assert (
        "  check units/bad\n    transform must be a function of the run, got 1\n" in result.stdout
    )


# ---------------------------------------------------------------------------------------------
# Errors of checks and expectations in the summaries and in diff

UNEVALUABLE = UNITS.replace("at_most(2.5)", 'at_most(2.5, on="share")') + RAISING
RAISED = (
    f"check raised KeyError: 'missing' (raised at blicks/units.py:"
    f"{line_of(UNEVALUABLE, 'run["missing"]')})"
)
CANNOT = (
    "cannot evaluate share at most 2.5: on= names 'share', which is no column of the table; its "
    "measures are value"
)


def test_the_step_summary_names_errors_of_checks_and_expectations_without_a_baseline(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Path("blicks/units.py").write_text(UNEVALUABLE)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert invoke("check", "runs/met").exit_code == 2
    assert summary.read_text().endswith(
        f"\n#### errors\n\n- `units/bounded`: {CANNOT}\n- `units/raising`: {RAISED}\n"
    )


def test_the_step_summary_and_diff_name_errors_of_checks_and_expectations(
    commit: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    met = built(invoke("check", "runs/met", "--push"))
    Path("blicks/units.py").write_text(UNEVALUABLE)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    result = invoke("check", "runs/met_again")
    assert result.exit_code == 2
    assert summary.read_text().endswith(
        f"\n#### errors\n\n- `units/raising`: {RAISED}\n- `units/bounded`: {CANNOT}\n"
    )
    # check lists them once, in the build's report; diff, which has no build report, lists them,
    # and exits 2 for them as for a Blick in error.
    assert result.stdout.count("cannot evaluate share") == 1
    diff = invoke("diff", f".blicket/build/{met}", f".blicket/build/{built(result)}")
    assert diff.exit_code == 2
    assert diff.stdout.endswith(f"\nerrors\n  units/raising  {RAISED}\n  units/bounded  {CANNOT}\n")


@pytest.mark.parametrize(
    ("module", "error"),
    [
        (UNITS + RAISING, "units/raising  check raised KeyError: 'missing'"),
        (UNITS.replace("at_most(2.5)", 'at_most(2.5, on="share")'), "units/bounded  cannot"),
    ],
    ids=["a check that raised", "an expectation that cannot be evaluated"],
)
def test_diff_exits_2_for_any_error_and_check_does_not_call_it_incomplete(
    commit: str, module: str, error: str
) -> None:
    met = built(invoke("check", "runs/met", "--push"))
    Path("blicks/units.py").write_text(module)
    result = invoke("check", "runs/met_again")
    assert result.exit_code == 2
    assert "\nnothing flagged\n" in result.stdout
    diff = invoke("diff", f".blicket/build/{met}", f".blicket/build/{built(result)}")
    assert diff.exit_code == 2
    assert f"\nerrors\n  {error}" in diff.stdout


# ---------------------------------------------------------------------------------------------
# What an outcome says


def test_the_worst_value_never_reads_as_the_bound_it_violates(commit: str) -> None:
    Path("blicks/units.py").write_text(UNITS.replace("at_most(2.5)", "at_most(2)"))
    make_run(Path("runs/near"), "1 2 2.0004")
    lines = invoke("build", "runs/near").stdout.splitlines()
    assert lines[-2:] == [
        "    1 of 3 rows offends: expected value at most 2",
        "    worst 2.0004 at year=2022",
    ]


def test_a_warning_by_level_says_so_and_a_vacuous_met_says_why(commit: str) -> None:
    Path("blicks/units.py").write_text(UNITS.replace("at_most(2.5)", 'at_most(2.5), level="warn"'))
    lines = invoke("build", "runs/failed").stdout.splitlines()
    assert "    1 of 3 rows offends, a warning at level warn: expected value at most 2.5" in lines


NULLS = """\
import polars as pl

import blicket as bk


@bk.blick(plot=bk.plots.line(x="year", y="value"), expect=bk.expect.at_most(2.5))
def nulls(run):
    values = pl.Series("value", [None, None], dtype=pl.Float64)
    return pl.DataFrame({"year": [2020, 2021]}).with_columns(values)
"""


def test_an_expectation_met_since_no_row_has_a_value_says_so(commit: str) -> None:
    Path("blicks/units.py").write_text(NULLS)
    result = invoke("build", "runs/met", "--json")
    (blick,) = json.loads(result.stdout)["blicks"]
    assert (blick["outcome"]["result"], blick["outcome"]["evaluated"]) == ("met", 0)
    assert outcome_sentence(bk.Outcome.model_validate(blick["outcome"])) == (
        "no row offends, as no row has a value: expected value at most 2.5"
    )


def test_list_shows_the_level_only_where_there_is_an_expectation(commit: str) -> None:
    Path("pyproject.toml").write_text(Path("pyproject.toml").read_text() + 'level = "warn"\n')
    Path("blicks/units.py").write_text(UNITS.replace(", expect=bk.expect.at_most(2.5)", ""))
    lines = invoke("list").stdout.splitlines()
    assert lines[1] == "  units/bounded    Bounded                   line"
    assert lines[2].endswith("expect: no rows, by value, a warning within 0.5   level: warn")


CHECKS_ONLY = UNITS[: UNITS.index("@bk.blick(")] + UNITS[UNITS.index("@bk.check(") :]


def test_a_project_with_checks_only_reports_no_blick_lines(
    commit: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    Path("blicks/units.py").write_text(CHECKS_ONLY)
    first = invoke("check", "runs/met", "--push")
    assert first.stdout.splitlines()[1:3] == ["1 check: 1 ran", "expectations: 1 met"]
    summary = Path("summary.md")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary.absolute()))
    second = invoke("check", "runs/negative")
    lines = second.stdout.splitlines()
    assert "vs baseline: no Blicks" in lines
    assert "expectations vs baseline: 1 broken" in lines
    # diff and the step summary say it as check does.
    assert "\nno Blicks\n" in summary.read_text()
    diff = invoke("diff", f".blicket/build/{built(first)}", f".blicket/build/{built(second)}")
    assert diff.stdout.splitlines()[2] == "no Blicks"


def test_a_line_break_in_a_dimension_value_stays_on_the_worst_line(commit: str) -> None:
    Path("blicks/units.py").write_text(
        CHECKS_ONLY.replace(
            'table(run).filter(pl.col("value") < 0)',
            'table(run).filter(pl.col("value") < 0).with_columns(place=pl.lit("North\\nSea"))',
        )
    )
    lines = invoke("build", "runs/negative").stdout.splitlines()
    assert "    worst -2 at year=2021, place=North Sea" in lines


@pytest.mark.parametrize("command", ["build", "check"])
def test_help_names_where_the_level_is_set(command: str) -> None:
    """The help of ``build`` and ``check`` names the table of the project's level, which Rich
    would take for markup unless it is escaped."""
    result = runner.invoke(cli.app, [command, "--help"], terminal_width=200)
    assert result.exit_code == 0
    assert "else level in [tool.blicket]." in result.output
