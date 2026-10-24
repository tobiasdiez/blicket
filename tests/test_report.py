"""The Markdown summary of a comparison."""

from datetime import UTC, datetime

import blicket as bk
from blicket.comparison import BlickComparison, BuildRef
from blicket.manifest import Repository
from blicket.report import render_markdown

DASH = "\N{EN DASH}"  # an empty cell


def blick(name: str, message: str | None = None, **change: object) -> BlickComparison:
    return BlickComparison(
        id=name, name=name, change=bk.Change.model_validate(change), message=message
    )


def test_the_summary_has_the_builds_counts_flagged_blicks_and_sections() -> None:
    made = datetime(2026, 10, 24, tzinfo=UTC)
    baseline = BuildRef(
        id="0123456789abcdef",
        run="a",
        profile="test",
        created_at=made,
        repository=Repository(commit="0a6b8583", branch="main", dirty=False),
        incomplete=False,
    )
    current = baseline.model_copy(update={"id": "fedcba9876543210", "run": "b", "incomplete": True})
    comparison = bk.Comparison(
        spec="0.2",
        blicket="0",
        created_at=made,
        baseline=baseline,
        current=current,
        incomplete=("blicks/broken.py failed to import: ModuleNotFoundError: No module named 'x'",),
        blicks=(
            blick("a/same", magnitude=0.0),
            blick("a/schema", flags={"schema"}, magnitude=0.0, values_added={"year": [2023]}),
            blick("a/value", flags={"value"}, magnitude=0.25, where={"region": "EU|US"}),
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
        "5 Blicks: 1 unchanged · 1 value · 1 schema · 1 new · removed not judged · 1 error\n"
        "\n"
        "| Blick | flags | magnitude | where |\n"
        "|---|---|---|---|\n"
        "| `a/value` | value | 0.25 | region=EU\\|US |\n"
        f"| `a/schema` | schema | 0 | {DASH} |\n"
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
