import blicket as bk

bk.group("flows", title="Material flows", tags=["mfa"])


@bk.blick(
    title="Steel flows by process",
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
    controls={"region": "split"},
    aliases=["flows/steel_process"],
)
def steel_by_process(run):
    """Steel flows split by production process."""
    return run


for flow in ["scrap", "slag"]:
    bk.register(
        id=f"flows/{bk.slug(flow)}",
        title=flow.capitalize(),
        plot=bk.plots.line(x="year", y="value", color="region"),
        transform=lambda run, f=flow: (run, f),
    )
