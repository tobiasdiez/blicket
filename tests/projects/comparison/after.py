"""The Blicks of the current build of the comparison in test_comparison.py, against before.py."""

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
    return table(run, 1.1)


@bk.blick(plot=LINE, tolerance=0.5)
def tolerant(run):
    return table(run, 1.1)


@bk.blick(plot=LINE)
def widened(run):
    return pl.DataFrame({"year": [*YEARS, 2023], "value": [*run["values"], 4.0]})


@bk.blick(plot=LINE, aliases=["a/old_name"])
def renamed(run):
    return table(run)


@bk.blick(plot=LINE)
def skipped_now(run):
    raise bk.Skip("the run has no trade module\nnor ports")


@bk.blick(plot=LINE)
def skipped_both(run):
    raise bk.Skip("the run has no trade module")


@bk.blick(plot=LINE)
def was_broken(run):
    return table(run)


@bk.blick(plot=LINE)
def broken_now(run):
    return run["missing"]


@bk.blick(plot=LINE)
def fresh(run):
    return table(run)
