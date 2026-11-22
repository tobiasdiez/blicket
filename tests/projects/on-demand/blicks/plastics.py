import blicket as bk

bk.group("plastics", title="Plastics")


@bk.blick(title="Plastics validation", plot=bk.plots.line(x="year", y="value"), expensive=True)
def validation(run):
    if not (run.path / "validation.mif").exists():
        raise bk.Skip("the run has no validation.mif")
    return run.table("trade")


@bk.blick(
    title="Plastics invalid",
    plot=bk.plots.line(x="year", y="value"),
    tolerance=2.0,  # above 1: an invalid definition
)
def invalid(run):
    return run.table("trade")
