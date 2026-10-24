from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd
    from remind_mfa.plastics.plastics_model import PlasticsModel

bk.group("drivers", title="Drivers and scenario parameters")

RATES = (
    "collection_rate",
    "landfill_rate",
    "mechanical_recycling_rate",
    "chemical_recycling_rate",
    "bio_production_rate",
    "daccu_production_rate",
)


@bk.blick(
    title="GDP per capita",
    plot=bk.plots.line(x="Time", y="value", color="Region"),
)
def gdp_per_capita(run: PlasticsModel) -> fd.FlodymArray:
    """GDP per capita per region, in 2005 USD at purchasing power parity."""
    return run.future_mfa.parameters["gdppc"]


@bk.blick(
    title="Scenario rates",
    plot=bk.plots.line(x="Time", y="value", color="Region"),
    controls={"Parameter": "split"},  # one panel per Parameter
)
def scenario_rates(run: PlasticsModel) -> pd.DataFrame:
    """The end-of-life and production rates the scenario sets, per region, as fractions."""
    parameters = run.future_mfa.parameters
    return pd.concat({name: parameters[name].to_df() for name in RATES}, names=["Parameter"])


@bk.blick(
    title="Polymer splits",
    plot=bk.plots.stacked_bar(x="Region", y="value", color="Polymer"),
    controls={"End Use": "split"},  # one panel per End Use
)
def polymer_splits(run: PlasticsModel) -> fd.FlodymArray:
    """Polymer shares of the use-stock inflow per region and end use, last historical year."""
    mfa = run.future_mfa
    # flodym dimension letters: t Time, h Historical Time
    return mfa.parameters["polymer_shares_use_inflow"][{"t": mfa.dims["h"].items[-1]}]
