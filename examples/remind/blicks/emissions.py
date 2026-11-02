import polars as pl
from blicks._iamc import (
    MT_CO2,
    MT_CO2_CUMULATED,
    MT_CO2EQ,
    T_CO2_PER_CAPITA,
    T_CO2EQ_PER_CAPITA,
    per_person,
    select,
)
from remind import WORLD, Run

import blicket as bk

bk.group("emissions", title="GHG and CO2 emissions")

GHG_SOURCES = [
    "Emi|CO2|Energy",
    "Emi|CO2|Industrial Processes",
    "Emi|CO2|Land-Use Change",
    "Emi|CO2|Waste",
    "Emi|CO2|non-ES CDR",  # carbon dioxide removal outside the energy system
    "Emi|GHG|CH4",
    "Emi|GHG|N2O",
    "Emi|GHG|F-Gases",
]

# Labels of the sectors by the part of the variable after Emi|GHG|, Emi|CO2| or
# Emi|CO2|Cumulated|; "gross" marks emissions before the negative emissions of carbon removal. A
# part without a label is its own label, such as Agriculture or CDR|BECCS.
_SECTOR_LABELS = {
    "Gross|Energy|Supply|Electricity": "Electricity supply (gross)",
    "Gross|Energy|Supply|Non-electric": "Non-electric supply (gross)",
    "Energy|Demand|Transport": "Transport",
    "Energy|Demand|Buildings": "Buildings",
    "Gross|Energy|Demand|Industry": "Industry (gross)",
    "Gross|Energy|Demand|CDR Sector": "CDR Sector (gross)",
    "Industrial Processes|Industry": "Processes|Industry",
    "Industrial Processes|CDR Sector": "Processes|CDR Sector",
    "Gross|Waste": "Waste (gross)",
}


def _sectors(*variables: str) -> dict[str, str]:
    """The variables of a sector chart with their labels."""
    prefixes = ("Emi|CO2|Cumulated|", "Emi|GHG|", "Emi|CO2|")  # the longest that matches first
    labels = {}
    for variable in variables:
        part = variable.removeprefix(next(p for p in prefixes if variable.startswith(p)))
        labels[variable] = _SECTOR_LABELS.get(part, part)
    return labels


# The options of carbon dioxide removal, the CDR layers: bioenergy with CCS, biochar, synthetic
# fuels with CCS, materials, direct air capture with CCS, ocean alkalinity enhancement and enhanced
# weathering.
GHG_SECTORS = _sectors(
    "Emi|GHG|Gross|Energy|Supply|Electricity",
    "Emi|GHG|Gross|Energy|Supply|Non-electric",
    "Emi|GHG|Energy|Demand|Transport",
    "Emi|GHG|Energy|Demand|Buildings",
    "Emi|GHG|Gross|Energy|Demand|Industry",
    "Emi|GHG|Gross|Energy|Demand|CDR Sector",
    "Emi|GHG|Industrial Processes",
    "Emi|GHG|Agriculture",
    "Emi|GHG|Land-Use Change",
    "Emi|GHG|Gross|Waste",
    "Emi|CO2|CDR|BECCS",
    "Emi|CO2|CDR|Biochar",
    "Emi|CO2|CDR|Synthetic Fuels CCS",
    "Emi|CO2|CDR|Materials",
    "Emi|CO2|CDR|DACCS",
    "Emi|CO2|CDR|OAE",
    "Emi|CO2|CDR|EW",
)
CO2_SECTORS = _sectors(
    "Emi|CO2|Land-Use Change",
    "Emi|CO2|Industrial Processes|Industry",
    "Emi|CO2|Industrial Processes|CDR Sector",
    "Emi|CO2|Gross|Waste",
    "Emi|CO2|Energy|Demand|Transport",
    "Emi|CO2|Gross|Energy|Demand|Industry",
    "Emi|CO2|Energy|Demand|Buildings",
    "Emi|CO2|Gross|Energy|Demand|CDR Sector",
    "Emi|CO2|Gross|Energy|Supply|Non-electric",
    "Emi|CO2|Gross|Energy|Supply|Electricity",
    "Emi|CO2|CDR|BECCS",
    "Emi|CO2|CDR|Biochar",
    "Emi|CO2|CDR|Synthetic Fuels CCS",
    "Emi|CO2|CDR|Materials",
    "Emi|CO2|CDR|DACCS",
    "Emi|CO2|CDR|OAE",
    "Emi|CO2|CDR|EW",
)
CO2_CUMULATED_SECTORS = _sectors(
    "Emi|CO2|Cumulated|Land-Use Change",
    "Emi|CO2|Cumulated|Industrial Processes",
    "Emi|CO2|Cumulated|Gross|Waste",
    "Emi|CO2|Cumulated|Energy|Demand|Transport",
    "Emi|CO2|Cumulated|Gross|Energy|Demand|Industry",
    "Emi|CO2|Cumulated|Energy|Demand|Buildings",
    "Emi|CO2|Cumulated|Gross|Energy|Demand|CDR Sector",
    "Emi|CO2|Cumulated|Gross|Energy|Supply|Non-electric",
    "Emi|CO2|Cumulated|Gross|Energy|Supply|Electricity",
    "Emi|CO2|Cumulated|CDR|BECCS",
    "Emi|CO2|Cumulated|CDR|Biochar",
    "Emi|CO2|Cumulated|CDR|Synthetic Fuels CCS",
    "Emi|CO2|Cumulated|CDR|Materials",
    "Emi|CO2|Cumulated|CDR|DACCS",
    "Emi|CO2|Cumulated|CDR|OAE",
    "Emi|CO2|Cumulated|CDR|EW",
)


@bk.blick(
    title="GHG emissions by source",
    unit=MT_CO2EQ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Source"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def ghg(run: Run) -> pl.DataFrame:
    """Greenhouse gas emissions in Mt CO2eq per year: CO2 from energy, industrial processes,
    land-use change and waste, the carbon removal outside the energy system, CH4, N2O and
    F-gases.

    The layers sum to Emi|GHG. REMIND reports the CO2 layers in Mt CO2/yr, the other gases in
    Mt CO2eq/yr, which are numerically the same.
    """
    return select(run, GHG_SOURCES, MT_CO2EQ, "Source", equivalent=(MT_CO2,))


@bk.blick(
    title="GHG emissions by sector",
    unit=MT_CO2EQ,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def ghg_by_sector(run: Run) -> pl.DataFrame:
    """Greenhouse gas emissions by sector, in Mt CO2eq per year.

    Energy supply, industry, the CDR sector and waste are gross, before the negative emissions
    of carbon dioxide removal, which are layers of their own, one per option. The layers sum to
    Emi|GHG.
    """
    return select(run, GHG_SECTORS, MT_CO2EQ, "Sector", equivalent=(MT_CO2,))


@bk.blick(
    title="GHG emissions per capita by sector",
    unit=T_CO2EQ_PER_CAPITA,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def ghg_per_capita_by_sector(run: Run) -> pl.DataFrame:
    """Greenhouse gas emissions by sector per capita, in t CO2eq per year.

    The sectors of "GHG emissions by sector", each divided by the population of its scenario,
    region and year. REMIND's compareScenarios report divides only some of them, so its chart has
    fewer layers.
    """
    return per_person(run, GHG_SECTORS, MT_CO2EQ, "Sector", equivalent=(MT_CO2,))


@bk.blick(
    title="CO2 emissions by sector",
    unit=MT_CO2,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def co2_by_sector(run: Run) -> pl.DataFrame:
    """CO2 emissions by sector, in Mt CO2 per year.

    Energy supply, industry, the CDR sector and waste are gross, before the negative emissions
    of carbon dioxide removal, which are layers of their own. The layers sum to Emi|CO2.
    """
    return select(run, CO2_SECTORS, MT_CO2, "Sector")


@bk.blick(
    title="CO2 emissions per capita by sector",
    unit=T_CO2_PER_CAPITA,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def co2_per_capita_by_sector(run: Run) -> pl.DataFrame:
    """CO2 emissions by sector per capita, in t CO2 per year.

    The sectors of "CO2 emissions by sector", each divided by the population of its scenario,
    region and year. REMIND's compareScenarios report divides only some of them, so its chart has
    fewer layers.
    """
    return per_person(run, CO2_SECTORS, MT_CO2, "Sector")


@bk.blick(
    title="Cumulated CO2 emissions by sector",
    unit=MT_CO2_CUMULATED,
    plot=bk.plots.stacked_area(x="Year", y="value", color="Sector"),
    controls={"Scenario": "split"},
    defaults={"Region": WORLD},
)
def co2_cumulated_by_sector(run: Run) -> pl.DataFrame:
    """CO2 emissions by sector, cumulated over the years, in Mt CO2.

    The sectors of "CO2 emissions by sector", with industrial processes as one layer. The layers
    sum to Emi|CO2|Cumulated.
    """
    return select(run, CO2_CUMULATED_SECTORS, MT_CO2_CUMULATED, "Sector")
