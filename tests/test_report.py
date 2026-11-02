"""The Markdown summary of a comparison."""

from datetime import UTC, datetime

import blicket as bk
from blicket.comparison import BlickComparison, BuildRef
from blicket.manifest import Repository
from blicket.report import render_markdown

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
