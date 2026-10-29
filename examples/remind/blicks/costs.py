import polars as pl
from blicks._iamc import BILLION_USD, PERCENT, select
from remind import WORLD, Run

import blicket as bk

bk.group("costs", title="Policy costs")


@bk.blick(
    title="Policy cost: consumption loss",
    unit=BILLION_USD,
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    defaults={"Region": WORLD},
    independent_y=True,
)
def consumption_loss(run: Run) -> pl.DataFrame:
    """The policy cost as the loss of consumption against the scenario's reference,
    Policy Cost|Consumption Loss, in billion US$2017 per year."""
    return select(run, ["Policy Cost|Consumption Loss"], BILLION_USD)


@bk.blick(
    title="Policy cost: consumption loss relative to the reference",
    unit="% of reference consumption",
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    defaults={"Region": WORLD},
    independent_y=True,
)
def consumption_loss_relative(run: Run) -> pl.DataFrame:
    """The loss of consumption as a percentage of the reference's consumption,
    Policy Cost|Consumption Loss|Relative to Reference Consumption."""
    variable = "Policy Cost|Consumption Loss|Relative to Reference Consumption"
    return select(run, [variable], PERCENT)


@bk.blick(
    title="Policy cost: GDP loss",
    unit=BILLION_USD,
    plot=bk.plots.line(x="Year", y="value", color="Scenario"),
    defaults={"Region": WORLD},
    independent_y=True,
)
def gdp_loss(run: Run) -> pl.DataFrame:
    """The policy cost as the loss of GDP against the scenario's reference,
    Policy Cost|GDP Loss, in billion US$2017 per year."""
    return select(run, ["Policy Cost|GDP Loss"], BILLION_USD)
