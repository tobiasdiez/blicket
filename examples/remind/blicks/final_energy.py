import polars as pl
from blicks._iamc import EJ, GJ_PER_CAPITA, per_person, select, shorten
from remind import DIMENSIONS, WORLD, Run

import blicket as bk

bk.group("final_energy", title="Final energy")

SECTORS = ["FE|CDR", "FE|Transport", "FE|Buildings", "FE|Industry"]
# REMIND's compareScenarios report leaves the small CDR sector out of its per-capita lines.
LINE_SECTORS = ["FE|Transport", "FE|Buildings", "FE|Industry"]
CARRIERS = ["FE|Electricity", "FE|Hydrogen", "FE|Heat", "FE|Gases", "FE|Liquids", "FE|Solids"]
# The carriers of each sector, the variables of the report's detailed chart and of its four
# sector charts; not every sector has every carrier. The legend and the panels follow CARRIERS
# and SECTORS.
SECTOR_CARRIERS = [
    "FE|CDR|Electricity",
    "FE|Transport|Electricity",
    "FE|Buildings|Electricity",
    "FE|Industry|Electricity",
    "FE|CDR|Hydrogen",
    "FE|Transport|Hydrogen",
    "FE|Buildings|Hydrogen",
    "FE|Industry|Hydrogen",
    "FE|CDR|Heat",
    "FE|Industry|Heat",
    "FE|Buildings|Heat",
    "FE|CDR|Gases",
    "FE|Transport|Gases",
    "FE|Buildings|Gases",
    "FE|Industry|Gases",
    "FE|CDR|Liquids",
    "FE|Transport|Liquids",
    "FE|Buildings|Liquids",
    "FE|Industry|Liquids",
    "FE|Buildings|Solids",
    "FE|Industry|Solids",
]
NON_ENERGY_USE = [
    "FE|Non-energy Use|Industry|Gases",
    "FE|Non-energy Use|Industry|Liquids",
    "FE|Non-energy Use|Industry|Solids",
]


@bk.blick(
    title="Final energy by sector",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def by_sector(run: Run) -> pl.DataFrame:
    """Final energy by sector, in EJ per year: the CDR sector, transport, buildings and industry,
    which sum to FE."""
    return select(run, SECTORS, EJ, "Sector")


@bk.blick(
    title="Final energy per capita by sector",
    unit=GJ_PER_CAPITA,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def per_capita_by_sector(run: Run) -> pl.DataFrame:
    """Final energy by sector per capita, in GJ per year.

    The sectors of "Final energy by sector", each divided by the population of its scenario,
    region and year.
    """
    return per_person(run, SECTORS, EJ, "Sector")


@bk.blick(
    title="Final energy per capita, with IEA history",
    unit=GJ_PER_CAPITA,
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    defaults={"Region": WORLD},
    independent_y=True,
)
def per_capita(run: Run) -> pl.DataFrame:
    """Final energy per capita, in GJ per year, with the IEA's history.

    FE of each scenario divided by its population, and the IEA's final energy since 1990
    divided by the World Bank's population (WDI) as the scenario historical (IEA), as in REMIND's
    compareScenarios report.
    """
    return per_person(run, ["FE"], EJ, history=("IEA",))


@bk.blick(
    title="Final energy per capita by sector, with IEA history",
    unit=GJ_PER_CAPITA,
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    controls={"Sector": "split"},
    defaults={"Region": WORLD},
    independent_y=True,
)
def per_capita_by_sector_lines(run: Run) -> pl.DataFrame:
    """Final energy per capita in transport, buildings and industry, in GJ per year, with the
    IEA's history.

    Each sector of each scenario divided by its population, and the IEA's final energy of the
    sector since 1990 divided by the World Bank's population (WDI) as the scenario
    historical (IEA), as in REMIND's compareScenarios report.
    """
    return per_person(run, LINE_SECTORS, EJ, "Sector", history=("IEA",))


@bk.blick(
    title="Final energy by carrier",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Carrier"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def by_carrier(run: Run) -> pl.DataFrame:
    """Final energy by carrier, in EJ per year: electricity, hydrogen, heat, gases, liquids and
    solids, which sum to FE."""
    return select(run, CARRIERS, EJ, "Carrier")


@bk.blick(
    title="Final energy by sector and carrier",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Carrier"),
    controls={"Sector": "split"},
    defaults={"Region": WORLD},
    # The CDR sector is orders of magnitude smaller than industry; the report draws each sector
    # as a chart of its own.
    independent_y=True,
)
def by_sector_and_carrier(run: Run) -> pl.DataFrame:
    """Final energy of each sector by carrier, in EJ per year, one scenario at a time.

    The carriers of each sector sum to the sector's final energy, such as FE|Industry. REMIND's
    compareScenarios report draws them as five charts, a detailed one stacking all 21 variables
    and one per sector.
    """
    frame = select(run, SECTOR_CARRIERS, EJ, "Item")
    item = pl.col("Item").cast(pl.String).str.split("|")
    return frame.select(
        *DIMENSIONS,
        item.list.first().cast(pl.Enum(shorten(SECTORS))).alias("Sector"),
        item.list.last().cast(pl.Enum(shorten(CARRIERS))).alias("Carrier"),
        "value",
    )


@bk.blick(
    title="Final energy for non-energy use by carrier",
    unit=EJ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Carrier"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def non_energy_use_by_carrier(run: Run) -> pl.DataFrame:
    """Final energy used as feedstock in industry, not burnt, by carrier, in EJ per year: gases,
    liquids and solids, which sum to FE|Non-energy Use."""
    return select(run, NON_ENERGY_USE, EJ, "Carrier")
