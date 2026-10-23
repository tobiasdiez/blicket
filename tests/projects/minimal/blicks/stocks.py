import blicket as bk


@bk.blick(plot=bk.plots.line(x="year", y="value", color="region"))
def in_use(run):
    return run
