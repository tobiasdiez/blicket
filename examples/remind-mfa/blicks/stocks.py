from typing import TYPE_CHECKING

import blicket as bk

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd
    from remind_mfa.plastics.plastics_model import PlasticsModel

bk.group("stocks", title="In-use stocks")


@bk.blick(
    title="In-use stock by region",
    unit="t",
    plot=bk.plots.line(x="Time", y="value", color="Region"),
)
def use_by_region(run: PlasticsModel) -> fd.FlodymArray:
    """Plastics in use per region, in t.

    Summed over elements, polymers and end uses.
    """
    # flodym dimension letters: t Time, r Region, u End Use
    return run.future_mfa.stocks["use"].stock.sum_to(("t", "r"))


@bk.blick(
    title="Global in-use stock by end use",
    unit="t",
    plot=bk.plots.stacked_area(x="Time", y="value", color="End Use"),
)
def use_by_end_use(run: PlasticsModel) -> fd.FlodymArray:
    """Plastics in use worldwide per end use, in t.

    Summed over regions, elements and polymers.
    """
    return run.future_mfa.stocks["use"].stock.sum_to(("t", "u"))
