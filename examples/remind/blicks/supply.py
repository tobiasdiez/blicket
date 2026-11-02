import polars as pl
from blicks._iamc import EJ, select
from remind import WORLD, Run

import blicket as bk

bk.group("supply", title="Electricity and primary energy")

ELECTRICITY = [
    "SE|Electricity|Hydrogen",
    "SE|Electricity|Solar|CSP",
    "SE|Electricity|Solar|PV",
    "SE|Electricity|Wind|Onshore",
    "SE|Electricity|Wind|Offshore",
    "SE|Electricity|Hydro",
    "SE|Electricity|Nuclear",
    "SE|Electricity|Geothermal",
    "SE|Electricity|Biomass|w/ CC",
    "SE|Electricity|Biomass|w/o CC",
    "SE|Electricity|Gas|w/ CC",
    "SE|Electricity|Gas|w/o CC",
    "SE|Electricity|Oil",
    "SE|Electricity|Coal|w/ CC",
    "SE|Electricity|Coal|w/o CC",
]
PRIMARY_ENERGY = [
    "PE|Solar",
    "PE|Wind",
    "PE|Hydro",
    "PE|Nuclear",
    "PE|Geothermal",
    "PE|Biomass",
    "PE|Gas",
    "PE|Oil",
    "PE|Coal",
]


@bk.blick(
    title="Electricity generation by carrier",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Carrier"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def electricity_by_carrier(run: Run) -> pl.DataFrame:
    """Secondary energy electricity by carrier, in EJ per year, power plants with and without
    carbon capture (w/ CC, w/o CC) apart.

    The layers sum to SE|Electricity. REMIND's compareScenarios report lists
    SE|Electricity|Net Imports too, which these runs do not report.
    """
    return select(run, ELECTRICITY, EJ, "Carrier")


@bk.blick(
    title="Primary energy by carrier",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Carrier"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def primary_energy_by_carrier(run: Run) -> pl.DataFrame:
    """Primary energy by carrier, in EJ per year, renewables first, then the fossil fuels; the
    layers sum to PE."""
    return select(run, PRIMARY_ENERGY, EJ, "Carrier")
