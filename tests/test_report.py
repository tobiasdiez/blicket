"""The Markdown summary of a comparison, and the lines a session of ``dev`` prints."""

from datetime import UTC, datetime

import pytest

import blicket as bk
from blicket.comparison import BlickComparison, BuildRef
from blicket.errors import Problem
from blicket.manifest import Repository
from blicket.report import duration, render_markdown, render_session_build

DASH = "\N{EN DASH}"  # an empty cell


def blick(
    name: str, message: str | None = None, *, skipped: bool = False, **change: object
) -> BlickComparison:
    return BlickComparison(
        id=name,
        name=name,
        change=bk.Change.model_validate(change),
        skipped=skipped,
        message=message,
    )


MADE = datetime(2026, 10, 24, tzinfo=UTC)
BASELINE = BuildRef(
    id="0123456789abcdef",
    run="a",
    profile="test",
    created_at=MADE,
    repository=Repository(commit="0a6b8583", branch="main", dirty=False),
    incomplete=False,
)
CURRENT = BASELINE.model_copy(update={"id": "fedcba9876543210", "run": "b"})


def test_the_summary_has_the_builds_counts_flagged_blicks_and_sections() -> None:
    comparison = bk.Comparison(
        spec="0.2",
        blicket="0",
        created_at=MADE,
        baseline=BASELINE,
        current=CURRENT.model_copy(update={"incomplete": True}),
        incomplete=("blicks/broken.py failed to import: ModuleNotFoundError: No module named 'x'",),
        blicks=(
            blick("a/same", magnitude=0.0),
            blick("a/schema", flags={"schema"}, magnitude=0.0, values_added={"year": [2023]}),
            blick("a/value", flags={"value"}, magnitude=0.25, where={"region": "EU|US"}),
            blick("a/all", flags={"value"}, magnitude=1.0),
            blick("a/tiny", flags={"value"}, magnitude=0.00012),
            blick("a/missing", "did not build in the baseline", flags={"new"}),
            blick("a/odd", "no built-in plot type 'custom'", flags={"error"}),
        ),
    )
    assert render_markdown(comparison) == (
        "### blicket: run b (`fedcba98`) against run a (`01234567`)\n"
        "\n"
        "- baseline `0123456789abcdef` · run a · profile test · blicks at 0a6b858\n"
        "- current `fedcba9876543210` · run b · profile test · blicks at 0a6b858 · incomplete "
        "(Blicks missing)\n"
        "\n"
        "7 Blicks: 1 unchanged · 3 value · 1 schema · 1 new · removed not judged · 1 error\n"
        "\n"
        "| Blick | flags | largest change (of the chart's scale) | where |\n"
        "|---|---|---|---|\n"
        f"| `a/all` | value | 100% | {DASH} |\n"
        "| `a/value` | value | 25% | region=EU\\|US |\n"
        f"| `a/tiny` | value | 0.012% | {DASH} |\n"
        f"| `a/schema` | schema | 0% | {DASH} |\n"
        f"| `a/missing` | new | {DASH} | {DASH} |\n"
        f"| `a/odd` | error | {DASH} | {DASH} |\n"
        "\n"
        "#### schema\n"
        "\n"
        "- `a/schema`\n"
        "  - year added: 2023\n"
        "\n"
        "#### new\n"
        "\n"
        "- `a/missing`: did not build in the baseline\n"
        "\n"
        "#### errors\n"
        "\n"
        "- blicks/broken.py failed to import: ModuleNotFoundError: No module named 'x'\n"
        "- `a/odd`: no built-in plot type 'custom'\n"
    )


def test_the_summary_counts_the_skipped_blicks_and_says_why_they_have_no_table() -> None:
    comparison = bk.Comparison(
        spec="0.2",
        blicket="0",
        created_at=MADE,
        baseline=BASELINE,
        current=CURRENT,
        incomplete=(),
        blicks=(
            blick("a/same", magnitude=0.0),
            blick("a/idle", "skipped: no trade (skipped in the baseline: no trade)", skipped=True),
            blick("a/back", "skipped in the baseline: no trade", flags={"new"}),
            blick("a/trade", "skipped: no trade", skipped=True, flags={"removed"}),
            blick("a/gone", flags={"removed"}),
        ),
    )
    summary = render_markdown(comparison)
    assert "\n5 Blicks: 1 unchanged · 2 skipped · 1 new · 2 removed\n" in summary
    assert "\n| `a/trade` | removed (skipped) | " in summary
    assert "\n| `a/gone` | removed | " in summary
    assert summary.endswith(
        "\n"
        "#### new\n"
        "\n"
        "- `a/back`: skipped in the baseline: no trade\n"
        "\n"
        "#### removed\n"
        "\n"
        "- `a/trade`: skipped: no trade\n"
    )


# The lines of the builds of a session.

AT = datetime(2026, 11, 11, 12, 1, 47)


def built(status: str = "ok", *problems: Problem, skipped: str | None = None) -> bk.BlickEntry:
    table = {"data": "dev/tables/x.parquet", "hash": "parquet-sha256:x"} if status == "ok" else {}
    fields = {"problems": problems, "skipped": skipped, **table}
    return bk.BlickEntry.model_validate({"id": "c/trade", "name": "c/trade", "group": "c"} | fields)


def problem(
    message: str, severity: str = "error", traceback: str | None = "Traceback\n"
) -> Problem:
    return Problem.model_validate(
        {"kind": "transformation", "severity": severity, "message": message, "traceback": traceback}
    )


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (
            {"flags": ["value"], "magnitude": 0.021, "where": {"Region": "CHA"}},
            "value, 2.1% of scale (Region=CHA)",
        ),
        ({"flags": ["schema", "value"], "magnitude": 0.5}, "value, 50% of scale · schema"),
        ({"flags": ["new"]}, "new"),
        ({}, "unchanged"),
    ],
)
def test_a_build_line_says_what_the_comparison_found(change: dict, said: str) -> None:
    line = render_session_build(built(), blick("c/trade", **change), 42.1, AT)
    assert line == f"12:01:47 c/trade built in 42.1 s · {said}"


def test_a_build_line_of_a_rebuild_a_failure_and_a_skip() -> None:
    assert render_session_build(built(), None, 3.0, AT, rebuilt=True) == (
        "12:01:47 c/trade rebuilt in 3.0 s"
    )
    removed = blick("c/trade", "skipped: no trade", skipped=True, flags=["removed"])
    assert render_session_build(
        built("skipped", skipped="no trade\nnor ports"), removed, 0.1, AT
    ) == ("12:01:47 c/trade skipped in 100 ms · no trade · removed")
    error = blick("c/trade", "the plot type rejects the tables", flags=["error"])
    assert render_session_build(built(), error, 0.1, AT) == (
        "12:01:47 c/trade built in 100 ms · error: the plot type rejects the tables"
    )


def test_a_failure_says_where_it_was_raised_and_its_further_errors() -> None:
    failed = built(
        "error",
        problem("transformation raised ValueError: two\nlines (raised at blicks/c.py:3)"),
        problem("the table has no x", traceback=None),
    )
    assert render_session_build(failed, None, 0.4, AT).splitlines() == [
        "12:01:47 c/trade failed in 400 ms · transformation raised ValueError: two (raised at "
        "blicks/c.py:3)   (-v for the traceback)",
        "    the table has no x",
    ]
    verbose = render_session_build(failed, None, 0.4, AT, verbose=True).splitlines()
    assert verbose[1:] == ["    the table has no x", "      Traceback"]


def test_a_build_line_names_the_first_of_its_warnings() -> None:
    warned = built(
        "ok",
        problem("the table has no rows", "warning", None),
        problem("another", "warning", None),
    )
    assert render_session_build(warned, None, 0.1, AT) == (
        "12:01:47 c/trade built in 100 ms · 2 warnings: the table has no rows …"
    )


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0.0123, "12 ms"),
        (0.9994, "999 ms"),
        (0.9996, "1.0 s"),  # rounded, not 1000 ms
        (1.0, "1.0 s"),
        (42.14, "42.1 s"),
        (59.96, "1 min 0 s"),  # not 60.0 s
        (75.9, "1 min 16 s"),
        (3725.3, "1 h 2 min 5 s"),
    ],
)
def test_durations(seconds: float, said: str) -> None:
    assert duration(seconds) == said
