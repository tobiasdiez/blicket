"""The checks of the steel cycle: properties of a run that no chart shows.

A check returns the rows that offend, none when the property holds. Its expectation is
``bk.expect.no_rows()`` unless it names another, and its level ``error``, so a check that returns
rows fails the build.
"""

import functools

import polars as pl

import blicket as bk

bk.group("checks", title="Coherence checks")

# Below this, in Mt, a gap in a balance is the round-off of adding the flows up.
TOLERANCE = 1e-9


@bk.check
def stock_balance(run):
    """The steel in use changes from one year to the next by what flows into use minus what
    leaves it; the gap is the flows' difference minus the change."""
    into = _total(run["flows"], pl.col("To") == "use", "into")
    out = _total(run["flows"], pl.col("From") == "use", "out")
    change = run["stock"].select(
        "Region", "Year", change=pl.col("value").diff().over("Region", order_by="Year")
    )
    return (
        change.join(into, on=["Region", "Year"])
        .join(out, on=["Region", "Year"])
        .with_columns(gap=pl.col("into") - pl.col("out") - pl.col("change"))
        .filter(pl.col("gap").abs() > TOLERANCE)  # the first year has no change, so no gap
        .select("Region", "Year", "gap")
    )


def process_balance(run, process: str) -> pl.DataFrame:
    """The regions and years in which ``process``, which keeps no stock, takes in more or less
    than it gives off; the gap is what it takes in minus what it gives off."""
    into = _total(run["flows"], pl.col("To") == process, "into")
    out = _total(run["flows"], pl.col("From") == process, "out")
    return (
        into.join(out, on=["Region", "Year"])
        .with_columns(gap=pl.col("into") - pl.col("out"))
        .filter(pl.col("gap").abs() > TOLERANCE)
        .select("Region", "Year", "gap")
    )


# A family of checks, one per process without a stock, declared in a loop.
for process in ["steelmaking", "collection"]:
    bk.register_check(
        id=f"checks/{process}_balance",
        title=f"{process.capitalize()} balance",
        description=f"What flows into {process} flows out of it again.",
        transform=functools.partial(process_balance, process=process),
    )


def _total(flows: pl.DataFrame, which: pl.Expr, name: str) -> pl.DataFrame:
    """The sum of the flows that ``which`` picks, per region and year, as the column ``name``."""
    return flows.filter(which).group_by("Region", "Year").agg(pl.col("value").sum().alias(name))
