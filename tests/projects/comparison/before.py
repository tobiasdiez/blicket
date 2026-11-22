"""The Blicks of the baseline build of the comparison in test_comparison.py; after.py holds the
current ones, and expected.json their comparison."""

import polars as pl

import blicket as bk

LINE = bk.plots.line(x="year", y="value")
YEARS = [2020, 2021, 2022]


def table(run, scale=1.0):
    return pl.DataFrame({"year": YEARS, "value": [scale * v for v in run["values"]]})


@bk.blick(plot=LINE)
def same(run):
    return table(run)


@bk.blick(plot=LINE)
def moved(run):
    return table(run)


@bk.blick(plot=LINE, tolerance=0.5)
def tolerant(run):
    return table(run)


@bk.blick(plot=LINE)
def widened(run):
    return table(run)


@bk.blick(plot=LINE)
def old_name(run):
    return table(run)


@bk.blick(plot=LINE)
def skipped_now(run):
    return table(run)


@bk.blick(plot=LINE)
def skipped_both(run):
    raise bk.Skip("the run has no trade module")


@bk.blick(plot=LINE)
def was_broken(run):
    return run["missing"]


@bk.blick(plot=LINE)
def broken_now(run):
    return table(run)


@bk.blick(plot=LINE)
def gone(run):
    return table(run)
