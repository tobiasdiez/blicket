import polars as pl
from blicks._iamc import USD_PER_T_CO2, select
from remind import WORLD, Run

import blicket as bk

bk.group("prices", title="CO2 prices")


@bk.blick(
    title="CO2 price",
    unit=USD_PER_T_CO2,
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    defaults={"Region": WORLD},
    independent_y=True,
)
def co2(run: Run) -> pl.DataFrame:
    """The carbon price, Price|Carbon, of each scenario, in US$2017 per t CO2."""
    return select(run, ["Price|Carbon"], USD_PER_T_CO2)


@bk.blick(
    title="CO2 price by region",
    unit=USD_PER_T_CO2,
    plot=bk.plots.line(x="Year", y="value", color="Region"),
    controls={"Scenario": "split"},
    independent_y=True,
)
def co2_by_region(run: Run) -> pl.DataFrame:
    """The carbon price, Price|Carbon, of each region, World left out, in US$2017 per t CO2,
    one panel per scenario."""
    return select(run, ["Price|Carbon"], USD_PER_T_CO2).filter(pl.col("Region") != WORLD)
