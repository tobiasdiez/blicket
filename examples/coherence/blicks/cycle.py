"""The Blicks of the steel cycle, each with an expectation on its table."""

import polars as pl

import blicket as bk

bk.group("cycle", title="Steel cycle")


@bk.blick(
    title="Flows of the cycle",
    unit="Mt per year",
    plot=bk.plots.sankey(source="From", target="To", value="value"),
    defaults={"Region": "North", "Year": 2030},
    # A flow is not negative. A solver leaves a zero slightly below it: within a billionth of a
    # Mt that is a warning, below it a failure.
    expect=bk.expect.at_least(0, warn_within=1e-9),
)
def flows(run):
    """Steel from ore and from collected scrap goes into use; the scrap that leaves use is
    recycled or goes to landfill."""
    return run["flows"]


@bk.blick(
    title="End-use split",
    plot=bk.plots.stacked_area(x="Year", y="value", color="End use"),
    # Every share lies between 0 and 1, the bounds included.
    expect=bk.expect.between(0, 1),
)
def end_use_split(run):
    """The share of each end use in the steel that goes into use."""
    return run["end_use"]


def above_maximum(table: pl.DataFrame) -> pl.DataFrame:
    """The rows of the recycling rate that lie above the maximum of their region and year, with
    ``excess``, by how much."""
    rate = table.filter(pl.col("Series") == "Recycling rate")
    maximum = table.filter(pl.col("Series") == "Maximum").select("Region", "Year", maximum="value")
    return (
        rate.join(maximum, on=["Region", "Year"])
        .with_columns(excess=pl.col("value") - pl.col("maximum"))
        .filter(pl.col("excess") > 0)
    )


@bk.blick(
    title="Recycling rate against its maximum",
    plot=bk.plots.line(x="Year", y="value", color="Region", linetype="Series"),
    # The property relates rows of the table to each other, so a function names the rows that
    # offend. At level warn it never fails the build.
    expect=bk.expect.no_rows(above_maximum, by="excess"),
    level="warn",
)
def recycling_rate(run):
    """The share of the collected scrap that is recycled, and the most it may be."""
    return run["recycling"]
