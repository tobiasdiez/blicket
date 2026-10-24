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
    unit="2005 USD PPP per person",
    plot=bk.plots.line(x="Time", y="value", color="Region"),
)
def gdp_per_capita(run: PlasticsModel) -> fd.FlodymArray:
    """GDP per capita per region, in 2005 USD at purchasing power parity."""
    return run.future_mfa.parameters["gdppc"]


@bk.blick(
    title="Scenario rates",
    unit="fraction",
    plot=bk.plots.line(x="Time", y="value", color="Region"),
    # The rates differ by orders of magnitude, so split into panels each gets its own axis.
    independent_y=True,
    defaults={"Parameter": "collection_rate"},  # Parameter is a filter: one rate at a time
)
def scenario_rates(run: PlasticsModel) -> pd.DataFrame:
    """Six rates the scenario sets per region and year, each a fraction.

    Collection is the share of end-of-life plastics collected; landfill, mechanical recycling and
    chemical recycling are shares of the collected waste; the bio-based and DACCU rates are the
    shares of primary high-value chemicals production made from biomass and from carbon captured
    from the air.
    """
    parameters = run.future_mfa.parameters
    return pd.concat({name: parameters[name].to_df() for name in RATES}, names=["Parameter"])


@bk.blick(
    title="Polymer splits",
    unit="fraction",
    plot=bk.plots.stacked_bar(x="Region", y="value", color="Polymer"),
    controls={"End Use": "split"},  # one panel per End Use
)
def polymer_splits(run: PlasticsModel) -> fd.FlodymArray:
    """Each polymer's share of the plastics entering use, per region and end use.

    The shares sum to 1 over polymers. They are those of the last historical year, which the
    scenario holds constant afterwards.
    """
    mfa = run.future_mfa
    # flodym dimension letters: t Time, h Historical Time
    return mfa.parameters["polymer_shares_use_inflow"][{"t": mfa.dims["h"].items[-1]}]
