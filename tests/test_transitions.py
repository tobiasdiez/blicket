"""The comparison of the expectations' outcomes with the baseline's: each transition, a changed
expectation, a unit skipped or gone on a side, a check matched through an alias, and a baseline
of spec 0.2."""

import json
import sys
from pathlib import Path

import pytest

import blicket as bk
from blicket.comparison import compare_builds
from tests.support import make_build_project, make_run


def units(
    *,
    expect: str | None = "bk.expect.at_most(2.5)",
    level: str | None = None,
    check: str = "negative",
    check_options: str = "",
    skip: bool = False,
) -> str:
    """A Blick module: the Blick ``bounded`` of the run's values with ``expect`` at ``level``, and
    a check of the negative values named ``check``, which raises ``bk.Skip`` with ``skip``."""
    options = "".join(
        [
            *([f", expect={expect}"] if expect else []),
            *([f", level={level!r}"] if level else []),
        ]
    )
    raising = '    raise bk.Skip("the run has no stocks")\n' if skip else ""
    return f"""\
import polars as pl

import blicket as bk


def table(run):
    years = list(range(2020, 2020 + len(run["values"])))
    return pl.DataFrame({{"year": years, "value": run["values"]}})


@bk.blick(plot=bk.plots.line(x="year", y="value"){options})
def bounded(run):
    return table(run)


@bk.check({check_options})
def {check}(run):
{raising}    return table(run).filter(pl.col("value") < 0)
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project outside git, without bytecode, so that a module rewritten within a second runs
    as rewritten."""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return make_build_project(tmp_path, {"blicks/units.py": units()})


def compared(
    project: Path, before: str, after: str, run_before: str, run_after: str
) -> bk.Comparison:
    """The comparison of a build of ``run_after`` with ``after`` against one of ``run_before`` with
    ``before``, the Blick module's sources."""
    builds = []
    runs = project.parent / "runs"
    for code, values in ((before, run_before), (after, run_after)):
        (project / "blicks" / "units.py").write_text(code)
        run = make_run(runs / str(len(list(runs.glob("*"))) if runs.exists() else 0), values)
        builds.append(bk.build(project, [run]).path)
    return compare_builds(*builds)


def expectation_of(comparison: bk.Comparison, name: str) -> dict[str, object]:
    """The transition, the results now and in the baseline and the message of ``name``."""
    (related,) = [r for unit, r in comparison.expectations() if unit.name == name]
    return {
        "transition": related.transition,
        "now": related.current.result if related.current else None,
        "then": related.baseline.result if related.baseline else None,
        "message": related.message,
    }


# The runs: the Blick is met with 2 2 2 and failed with 1 2 3; the check is met without a
# negative value and failed with one.
MET, FAILED, NEGATIVE = "2 2 2", "1 2 3", "1 -1 2"


@pytest.mark.parametrize(
    ("before", "after", "transition", "now", "then"),
    [
        (MET, FAILED, "broken", "failed", "met"),
        (FAILED, FAILED, "still_failing", "failed", "failed"),
        (FAILED, MET, "fixed", "met", "failed"),
        (MET, MET, None, "met", "met"),
    ],
)
def test_the_transitions_between_two_outcomes(
    project: Path, before: str, after: str, transition: str | None, now: str, then: str
) -> None:
    found = compared(project, units(), units(), before, after)
    assert expectation_of(found, "units/bounded") == {
        "transition": transition,
        "now": now,
        "then": then,
        "message": None,
    }
    assert found.flagged == (0 if before == after else 1)  # the change flags, not the transition


def test_a_warning_that_became_a_failure_is_broken(project: Path) -> None:
    found = compared(project, units(level="warn"), units(), FAILED, FAILED)
    assert expectation_of(found, "units/bounded")["transition"] == "broken"
    found = compared(project, units(), units(level="warn"), FAILED, FAILED)
    assert expectation_of(found, "units/bounded")["transition"] == "still_failing"


def test_an_expectation_just_added_is_new(project: Path) -> None:
    found = compared(project, units(expect=None), units(), FAILED, FAILED)
    assert expectation_of(found, "units/bounded") == {
        "transition": "new",
        "now": "failed",
        "then": None,
        "message": "no expectation in the baseline",
    }


def test_a_changed_expectation_is_new(project: Path) -> None:
    found = compared(project, units(), units(expect="bk.expect.at_most(2.25)"), FAILED, FAILED)
    assert expectation_of(found, "units/bounded") == {
        "transition": "new",
        "now": "failed",
        "then": None,
        "message": "the expectation changed since the baseline",
    }


@pytest.mark.parametrize(
    ("after", "message"),
    [
        (units(skip=True), "skipped now: the run has no stocks"),
        (units(check_options='level="off"'), "skipped now: its level is off"),
    ],
    ids=["skipped", "off"],
)
def test_a_failing_check_silenced_now_is_dropped(project: Path, after: str, message: str) -> None:
    found = compared(project, units(), after, NEGATIVE, NEGATIVE)
    assert expectation_of(found, "units/negative") == {
        "transition": "dropped",
        "now": None,
        "then": "failed",
        "message": message,
    }


def test_a_failing_check_removed_now_is_dropped(project: Path) -> None:
    after = units().split("@bk.check")[0]
    found = compared(project, units(), after, NEGATIVE, NEGATIVE)
    (dropped,) = found.checks
    assert (dropped.id, dropped.expectation and dropped.expectation.transition) == (
        "units/negative",
        "dropped",
    )
    assert dropped.expectation is not None
    assert dropped.expectation.message == "not in the current build"


def test_an_expectation_removed_from_a_blick_is_dropped(project: Path) -> None:
    found = compared(project, units(), units(expect=None), FAILED, FAILED)
    assert expectation_of(found, "units/bounded") == {
        "transition": "dropped",
        "now": None,
        "then": "failed",
        "message": "no expectation now",
    }


def test_a_check_skipped_in_the_baseline_and_failing_now_is_new(project: Path) -> None:
    found = compared(project, units(skip=True), units(), NEGATIVE, NEGATIVE)
    assert expectation_of(found, "units/negative") == {
        "transition": "new",
        "now": "failed",
        "then": None,
        "message": "skipped in the baseline: the run has no stocks",
    }


def test_a_check_is_matched_through_its_aliases(project: Path) -> None:
    after = units(check="negative_values", check_options='aliases=["units/negative"]')
    found = compared(project, units(), after, NEGATIVE, MET)
    (check,) = found.checks
    assert (check.name, check.matched) == ("units/negative_values", "units/negative")
    assert expectation_of(found, "units/negative_values")["transition"] == "fixed"


def test_the_comparison_file_holds_the_expectations_and_counts_them(project: Path) -> None:
    found = compared(project, units(), units(), "2 -1 2", FAILED)
    assert found.transitions == {"broken": 1, "fixed": 1}
    data = json.loads(found.model_dump_json())
    (check,) = data["checks"]
    assert check["expectation"]["transition"] == "fixed"
    assert data["blicks"][0]["expectation"]["current"]["result"] == "failed"
    assert bk.Comparison.model_validate(data) == found


def test_a_baseline_of_spec_0_2_reads_every_expectation_as_new(project: Path) -> None:
    (project / "blicks" / "units.py").write_text(units())
    baseline = bk.build(project, [make_run(project.parent / "runs" / "a", NEGATIVE)]).path
    data = json.loads((baseline / "manifest.json").read_text())
    data["spec"] = "0.2"
    del data["checks"]
    for entry in data["blicks"]:
        del entry["outcome"], entry["level"], entry["definition"]["expect"]
    (baseline / "manifest.json").write_text(json.dumps(data))
    current = bk.build(project, [make_run(project.parent / "runs" / "b", "1 -1 3")]).path
    found = compare_builds(baseline, current)
    assert expectation_of(found, "units/bounded")["transition"] == "new"
    assert expectation_of(found, "units/negative") == {
        "transition": "new",
        "now": "failed",
        "then": None,
        "message": "not in the baseline",
    }


def test_a_check_in_error_and_an_unevaluable_outcome_are_recorded(project: Path) -> None:
    raising = units(check_options="").replace(
        '    return table(run).filter(pl.col("value") < 0)', '    return run["missing"]'
    )
    unevaluable = raising.replace("bk.expect.at_most(2.5)", 'bk.expect.at_most(2.5, on="share")')
    found = compared(project, units(), unevaluable, FAILED, FAILED)
    (check,) = found.checks
    assert check.message == "check raised KeyError: 'missing' (raised at blicks/units.py:18)"
    bounded = expectation_of(found, "units/bounded")
    # The outcome that cannot be evaluated is recorded, and counts as none for the transition.
    assert (bounded["transition"], bounded["now"], bounded["then"]) == (
        "dropped",
        "error",
        "failed",
    )
    assert expectation_of(found, "units/negative") == {
        "transition": None,
        "now": None,
        "then": "met",
        "message": "in error now",
    }
