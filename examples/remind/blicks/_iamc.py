"""What the Blicks share: tables of REMIND variables with short labels, values per capita, and
the units.

``select`` with its labels and ``shorten`` hold for any IAMC-style run; ``per_person``, with the
factors and populations of REMIND's report, and history as the scenario ``historical
(<source>)`` are REMIND's.
"""

import sys
from collections.abc import Iterable, Mapping, Sequence

import polars as pl
from remind import DIMENSIONS, Run

type Items = Sequence[str] | Mapping[str, str]

MT_CO2EQ = "Mt CO2eq/yr"
MT_CO2 = "Mt CO2/yr"
MT_CO2_CUMULATED = "Mt CO2"
EJ = "EJ/yr"
MILLION = "million"
USD_PER_T_CO2 = "US$2017/t CO2"
BILLION_USD = "billion US$2017/yr"
PERCENT = "%"
T_CO2EQ_PER_CAPITA = "t CO2eq/yr per capita"
T_CO2_PER_CAPITA = "t CO2/yr per capita"
GJ_PER_CAPITA = "GJ/yr per capita"

# remind2's preprocessing.R divides by the population in persons and multiplies by 1e6 for
# emissions and 1e9 for energy; with the population in millions that is 1 from Mt to t per
# capita and 1e3 from EJ to GJ per capita.
_PER_PERSON = {MT_CO2EQ: 1.0, MT_CO2: 1.0, EJ: 1e3}
# The variables named as missing already, with where they were looked for, so that each is named
# once per process, not once per Blick.
_warned: set[tuple[str, str]] = set()


def select(
    run: Run,
    items: Items,
    unit: str,
    dimension: str | None = None,
    *,
    equivalent: Iterable[str] = (),
    source: str | None = None,
) -> pl.DataFrame:
    """The rows of the variables ``items``: ``Scenario``, ``Region``, ``Year``, ``dimension``
    with the label of each variable, and ``value``.

    ``items`` is a list of variables, labelled by what remains of each after the longest prefix
    of ``|``-separated segments they share, or a dict of variable to label. ``dimension`` is an
    Enum in the order of ``items``, which the legend keeps; without one, ``items`` is a single
    variable. With a ``source``, such as ``IEA``, the rows are that source's in
    ``historical.mif``, under the scenario ``historical (<source>)``, in the run's regions.
    ``Scenario`` is an Enum of the run's titles, then the historical sources; ``Region`` one in the
    run's order, World first.

    Every row must be in ``unit`` or one of ``equivalent``, units that are numerically the same;
    the table has no unit column. A variable without rows is named on stderr. Raises
    ``ValueError`` for a row in another unit, and when none of the variables has rows.
    """
    if source is None:
        rows, where = run.rows(items), "the run"
    else:
        rows = run.historical.filter(
            pl.col("Model") == source,
            pl.col("Variable").is_in(list(items)),
            pl.col("Region").is_in(run.regions),
        ).with_columns(Scenario=pl.lit(_historical(source)))
        where = f"the {source} data of historical.mif"
    if isinstance(items, Mapping):
        labels = dict(items)
    else:
        labels = dict(zip(items, shorten(items), strict=True))
    present = set(rows["Variable"].unique().to_list())
    if not present:
        raise ValueError(f"{where} has none of {', '.join(labels)}")
    missing = [v for v in labels if v not in present and (where, v) not in _warned]
    if missing:
        _warned.update((where, variable) for variable in missing)
        print(f"warning: {where} has no {', '.join(missing)}", file=sys.stderr)
    allowed = [unit, *equivalent]
    other = rows.filter(~pl.col("Unit").is_in(allowed).fill_null(False))
    if not other.is_empty():
        found_units = other.select("Variable", "Unit").unique(maintain_order=True).rows()
        shown = ", ".join(f"{variable} in {found!r}" for variable, found in found_units)
        raise ValueError(f"expected {' or '.join(map(repr, allowed))}, found {shown}")
    columns = [
        pl.col("Scenario").cast(_scenarios(run)),
        pl.col("Region").cast(pl.Enum(run.regions)),
        pl.col("Year"),
    ]
    if dimension is not None:
        order = pl.Enum(list(labels.values()))
        label = pl.col("Variable").replace_strict(labels, return_dtype=order)
        columns.append(label.alias(dimension))
    return rows.select(*columns, "value")


def per_person(
    run: Run,
    items: Items,
    unit: str,
    dimension: str | None = None,
    *,
    equivalent: Iterable[str] = (),
    history: Iterable[str] = (),
) -> pl.DataFrame:
    """The rows of ``items`` as ``select`` gives them, then those of each source in ``history``,
    each divided by the population of its scenario, region and year, as REMIND's report computes
    it: REMIND's ``Population`` for a scenario, WDI's for a historical source.

    Mt CO2eq/yr and Mt CO2/yr become t per capita, EJ/yr GJ per capita. Raises ``ValueError``
    for another unit and for a scenario row without a population; a historical row without one
    is left out, with a warning.
    """
    if unit not in _PER_PERSON:
        raise ValueError(f"no per-capita factor for {unit}; known are {', '.join(_PER_PERSON)}")
    sources = list(history)
    frame = pl.concat(
        [
            select(run, items, unit, dimension, equivalent=equivalent, source=source)
            for source in [None, *sources]
        ]
    )
    populations = [select(run, ["Population"], MILLION)]
    if sources:
        wdi = select(run, ["Population"], MILLION, source="WDI")
        scenarios = _scenarios(run)
        for source in sources:
            scenario = pl.lit(_historical(source)).cast(scenarios).alias("Scenario")
            populations.append(wdi.with_columns(scenario))
    population = pl.concat(populations).rename({"value": "population"})
    joined = frame.join(population, on=DIMENSIONS, how="left", validate="m:1")
    lacking = joined.filter(pl.col("population").is_null())
    modelled = lacking.filter(pl.col("Scenario").cast(pl.String).is_in(run.titles))
    if not modelled.is_empty():
        years = modelled.group_by("Scenario").agg(pl.col("Year").unique().sort())
        shown = "; ".join(f"{s}: {', '.join(map(str, y))}" for s, y in years.rows())
        raise ValueError(f"no Population for {shown}")
    if not lacking.is_empty():
        print(f"warning: {lacking.height} historical rows have no WDI population", file=sys.stderr)
    value = pl.col("value") / pl.col("population") * _PER_PERSON[unit]
    return joined.drop_nulls("population").with_columns(value).drop("population")


def shorten(variables: Sequence[str]) -> list[str]:
    """The variables without the longest prefix of whole ``|``-separated segments they share, as
    mip's ``shorten_legend`` does; each keeps at least its last segment."""
    parts = [variable.split("|") for variable in variables]
    shared = 0
    while all(len(p) > shared + 1 for p in parts) and len({p[shared] for p in parts}) == 1:
        shared += 1
    return ["|".join(p[shared:]) for p in parts]


def _historical(source: str) -> str:
    return f"historical ({source})"


def _scenarios(run: Run) -> pl.Enum:
    """The scenarios in display order: the run's titles, then each source of ``historical.mif``
    as ``historical (<source>)``."""
    return pl.Enum([*run.titles, *map(_historical, run.sources)])
