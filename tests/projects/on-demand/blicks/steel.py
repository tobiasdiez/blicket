import blicket as bk

bk.group("steel", title="Steel")


@bk.blick(
    title="Steel production",
    description="Primary production by region.",
    unit="t per year",
    plot=bk.plots.line(x="year", y="value"),
)
def production(run):
    return run.table("production")


@bk.blick(title="Steel trade", unit="t per year", plot=bk.plots.line(x="year", y="value"))
def trade(run):
    return run.table("trade")


@bk.blick(title="Steel scrap", plot=bk.plots.line(x="year", y="value"))
def scrap(run):
    return run.table("scrap")  # the run has no such table: KeyError


@bk.blick(title="Steel shares", plot=bk.plots.line(x="year", y="value"), expensive=False)
def shares(run):
    """The shares of the years, quick to compute on any run."""
    return run.table("shares")
