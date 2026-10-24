from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd
    from remind_mfa.plastics.plastics_model import PlasticsModel

bk.group("flows", title="Plastics flows")


def _production_sources(run: PlasticsModel) -> dict[str, fd.FlodymArray]:
    """Primary and mechanically recycled polymers reaching the primary market."""
    flows = run.future_mfa.flows
    return {
        "Primary": flows["polymerization => primary_market"],
        "Recycled": flows["aux_recyclate_market => primary_market"],
    }


def _production(run: PlasticsModel) -> fd.FlodymArray:
    """All polymers reaching the primary market, primary and recycled."""
    sources = _production_sources(run)
    return sources["Primary"] + sources["Recycled"]


def _by_flow(arrays: dict[str, fd.FlodymArray]) -> pd.DataFrame:
    """The arrays summed to Time and Region, in one table with a Flow column naming each."""
    # flodym dimension letters: t Time, e Element, r Region, p Polymer, u End Use
    return pd.concat(
        {name: array.sum_to(("t", "r")).to_df() for name, array in arrays.items()}, names=["Flow"]
    )


@bk.blick(
    title="Consumption by end use",
    plot=bk.plots.stacked_area(x="Time", y="value", color="End Use"),
    controls={"Region": "split"},  # one panel per Region
)
def consumption_by_end_use(run: PlasticsModel) -> fd.FlodymArray:
    """The inflow into the use stock per region and end use, in t per year."""
    return run.future_mfa.stocks["use"].inflow.sum_to(("t", "r", "u"))


@bk.blick(
    title="Production by polymer",
    plot=bk.plots.stacked_area(x="Time", y="value", color="Polymer"),
    controls={"Region": "split"},  # one panel per Region
)
def production_by_polymer(run: PlasticsModel) -> fd.FlodymArray:
    """Primary and mechanically recycled production per region and polymer, in t per year."""
    return _production(run).sum_to(("t", "r", "p"))


@bk.blick(
    title="Production by source",
    plot=bk.plots.stacked_area(x="Time", y="value", color="Flow"),
    controls={"Region": "split"},  # one panel per Region
)
def production_by_source(run: PlasticsModel) -> pd.DataFrame:
    """Primary production and mechanically recycled polymers per region, in t per year."""
    return _by_flow(_production_sources(run))


@bk.blick(
    title="Production, net imports and consumption",
    plot=bk.plots.line(x="Time", y="value", color="Flow"),
    controls={"Region": "split"},  # one panel per Region
)
def production_trade_consumption(run: PlasticsModel) -> pd.DataFrame:
    """Production, net imports of primary plastics and products, and consumption, in t per year."""
    mfa = run.future_mfa
    flows = mfa.flows
    return _by_flow(
        {
            "Production": _production(run),
            "Primary net imports": (
                flows["imports => primary_market"] - flows["primary_market => exports"]
            ),
            "Manufactured products net imports": (
                flows["imports => manufactured_products_market"]
                - flows["manufactured_products_market => exports"]
            ),
            "Consumption": mfa.stocks["use"].inflow,
        }
    )


@bk.blick(
    title="End-use split",
    plot=bk.plots.stacked_area(x="Time", y="value", color="End Use"),
    controls={"Region": "split"},  # one panel per Region
)
def end_use_split(run: PlasticsModel) -> fd.FlodymArray:
    """Each end use's share of consumption per region, as a fraction."""
    return consumption_by_end_use(run).get_shares_over("u")
