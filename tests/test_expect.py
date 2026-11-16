"""``bk.expect``: the vocabulary, its records and words, and the evaluation of a table."""

import functools
import math
import random
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl
import pytest

import blicket as bk
from blicket.expect._evaluation import evaluate
from blicket.expect._levels import LEVELS, Level, level_problem, resolve_level
from blicket.expect._vocabulary import Unevaluable

TABLE = pl.DataFrame(
    {
        "Region": ["EUR", "EUR", "SSA", "SSA", "USA"],
        "Time": [2020, 2050, 2020, 2050, 2050],
        "value": [0.5, 1.0, -0.2, 1.07, None],
    }
)
DIMS = ["Region", "Time"]
# For calls that are wrong on purpose, which the type checker would reject.
loose: Any = bk.expect


def outcome(expectation: bk.Expectation, frame: pl.DataFrame = TABLE, level: Level = "error"):
    measures = [c for c in frame.columns if c not in DIMS]
    return evaluate(expectation, frame, DIMS, measures, level).outcome


def test_a_bound_counts_the_rows_with_a_value_and_names_the_worst() -> None:
    found = outcome(bk.expect.between(0, 1))
    assert found.distance == pytest.approx(0.2)
    assert found.model_copy(update={"distance": None}) == bk.Outcome(
        result="failed",
        expectation="value between 0 and 1",
        evaluated=4,
        offending=2,
        within=0,
        worst=-0.2,
        where={"Region": "SSA", "Time": 2020},
    )


def test_the_bounds_are_inclusive_and_nulls_never_offend() -> None:
    assert outcome(bk.expect.at_most(1.07)).result == "met"
    assert outcome(bk.expect.at_least(-0.2)).result == "met"
    assert outcome(bk.expect.at_most(1.0)).offending == 1


def test_rows_within_warn_within_are_a_warning() -> None:
    within = outcome(bk.expect.at_most(1, warn_within=0.1))
    assert (within.result, within.offending, within.within) == ("warning", 1, 1)
    beyond = outcome(bk.expect.between(0, 1, warn_within=0.1))
    assert (beyond.result, beyond.offending, beyond.within) == ("failed", 2, 1)
    assert beyond.expectation == "value between 0 and 1, a warning within 0.1"


def test_level_warn_makes_every_offending_row_a_warning() -> None:
    assert outcome(bk.expect.between(0, 1), level="warn").result == "warning"


def test_no_rows_lets_every_row_offend_ranked_by_its_measure() -> None:
    found = outcome(bk.expect.no_rows())
    assert (found.result, found.evaluated, found.offending) == ("failed", None, 5)
    assert (found.worst, found.where, found.expectation) == (
        1.07,
        {"Region": "SSA", "Time": 2050},
        "no rows, by value",
    )


def test_no_rows_without_a_measure_to_rank_by_names_the_first_row() -> None:
    frame = TABLE.with_columns(other=pl.lit(1.0))
    found = outcome(bk.expect.no_rows(), frame)
    assert (found.worst, found.where, found.expectation) == (
        None,
        {"Region": "EUR", "Time": 2020},
        "no rows",
    )


def test_a_row_without_a_distance_is_not_within_and_ranks_last() -> None:
    evaluated = evaluate(
        bk.expect.no_rows(by="value", warn_within=2), TABLE, DIMS, ["value"], "error"
    )
    assert (evaluated.outcome.result, evaluated.outcome.within) == ("failed", 4)
    assert evaluated.offending["Region"].to_list()[-1] == "USA"


def test_an_empty_table_meets_every_expectation_that_names_one_of_its_measures() -> None:
    empty = TABLE.clear()
    assert outcome(bk.expect.between(0, 1), empty) == bk.Outcome(
        result="met", expectation="value between 0 and 1", evaluated=0
    )
    # A typo in on= shows on a clean run too, whose table has its columns and no rows.
    with pytest.raises(Unevaluable, match="on= names 'nothing', which is no column of the table"):
        outcome(bk.expect.at_most(1, on="nothing"), empty)
    # Only a table without any column cannot be checked against the measure named.
    found = evaluate(bk.expect.at_most(1, on="nothing"), pl.DataFrame(), [], [], "error")
    assert (found.outcome.result, found.outcome.expectation) == ("met", "nothing at most 1")


@pytest.mark.parametrize(
    ("expectation", "measures", "message"),
    [
        (
            bk.expect.between(0, 1, on="share"),
            ["value"],
            "on= names 'share', which is no column of the table; its measures are value",
        ),
        (
            bk.expect.no_rows(by="share"),
            [],
            "by= names 'share', which is no column of the table; it has no measure",
        ),
        (
            bk.expect.no_rows(by="Time"),
            [],
            "by= names 'Time', a dimension of the table, not a measure; integer and string "
            "columns are dimensions; cast it to float, or name it in measures=",
        ),
        (
            bk.expect.at_most(1),
            ["value", "other"],
            "the table has the measures value, other; name the one to bound with on=",
        ),
        (
            bk.expect.at_least(0),
            [],
            "the table has no measure to bound; integer and string columns are dimensions; cast "
            "it to float, or name it in measures=",
        ),
    ],
)
def test_a_measure_that_cannot_be_found_is_unevaluable(
    expectation: bk.Expectation, measures: list[str], message: str
) -> None:
    frame = TABLE.select(*DIMS).with_columns(*(pl.lit(1.0).alias(m) for m in measures))
    with pytest.raises(Unevaluable, match=f"^{message}$"):
        evaluate(expectation, frame, DIMS, measures, "error")


def above_maximum(table: pl.DataFrame) -> pl.DataFrame:
    return table


@pytest.mark.parametrize(
    ("expectation", "record", "words"),
    [
        (bk.expect.no_rows(), {"kind": "no_rows", "rows": None, "by": None}, "no rows"),
        (
            bk.expect.no_rows(above_maximum, by="excess"),
            {"kind": "no_rows", "rows": "above_maximum", "by": "excess"},
            "no rows of above_maximum, by excess",
        ),
        (
            bk.expect.no_rows(functools.partial(above_maximum)),
            {"kind": "no_rows", "rows": "above_maximum", "by": None},
            "no rows of above_maximum",
        ),
        (
            bk.expect.at_most(5, on="x", warn_within=1e-9),
            {"kind": "at_most", "on": "x", "bound": 5.0, "warn_within": 1e-9},
            "x at most 5, a warning within 1e-09",
        ),
        (bk.expect.at_least(0), {"kind": "at_least", "bound": 0.0}, "at least 0"),
        (
            bk.expect.between(0.123456789, 1),
            {"kind": "between", "low": 0.123456789, "high": 1.0},
            "between 0.123456789 and 1",
        ),
    ],
)
def test_records_and_words(expectation: bk.Expectation, record: dict[str, Any], words: str) -> None:
    recorded = expectation.record().model_dump()
    assert {key: recorded[key] for key in record} == record
    assert expectation.words(expectation.measure) == words


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (
            lambda: bk.expect.between(1, 0),
            "bk.expect.between(1, 0): low is above high; pass bk.expect.between(0, 1)",
        ),
        (
            lambda: bk.expect.at_most(math.inf),
            "bk.expect.at_most(inf): the bound must be a finite number, got inf",
        ),
        (
            lambda: bk.expect.at_least(True),
            "bk.expect.at_least(True): the bound must be a finite number, got True",
        ),
        (
            lambda: loose.at_least("0"),
            "bk.expect.at_least('0'): the bound must be a finite number, got '0'",
        ),
        (
            lambda: bk.expect.at_most(1, warn_within=-1),
            "bk.expect.at_most(1): warn_within must be 0 or more, an absolute distance in the "
            "units of the measure, got -1",
        ),
        (
            lambda: bk.expect.no_rows(warn_within=1e-9),
            "bk.expect.no_rows(): warn_within= needs by=, the measure whose distance it bounds: "
            'bk.expect.no_rows(by="relative", warn_within=1e-09)',
        ),
        (
            lambda: loose.no_rows(lambda table, other: table),
            "bk.expect.no_rows(): rows must be a function of the table that returns its "
            "offending rows, taking exactly one positional parameter, the table; its signature "
            "is (table, other)",
        ),
        (
            lambda: loose.no_rows("excess"),
            "bk.expect.no_rows(): rows must be a function of the table that returns its "
            "offending rows, got 'excess'",
        ),
        (
            lambda: bk.expect.between(0, 1, on=""),
            "bk.expect.between(0, 1): on= must name a measure column, got ''",
        ),
    ],
)
def test_the_vocabulary_says_what_to_write_instead(make: Any, message: str) -> None:
    with pytest.raises(bk.DefinitionError) as raised:
        make()
    assert str(raised.value) == message


def test_numbers_of_any_real_type_are_bounds() -> None:
    assert bk.expect.at_most(np.int64(1), warn_within=np.float32(0.5)).record().bound == 1.0
    assert bk.expect.between(np.int32(0), 1).record().model_dump()["low"] == 0.0
    with pytest.raises(bk.DefinitionError, match="the bound must be a finite number"):
        bk.expect.at_least(np.float64("nan"))
    assert bk.expect.at_most(Decimal("1.5"), warn_within=Decimal("0.1")).record().bound == 1.5
    with pytest.raises(bk.DefinitionError, match="the bound must be a finite number, got Decimal"):
        bk.expect.at_most(Decimal("NaN"))
    with pytest.raises(bk.DefinitionError, match="warn_within must be a finite number, got Dec"):
        bk.expect.at_most(1, warn_within=Decimal("sNaN"))
    with pytest.raises(bk.DefinitionError, match="got one beyond the range of a float"):
        bk.expect.at_most(10**400)


@pytest.mark.parametrize(
    ("expectation", "shown"),
    [
        (bk.expect.no_rows(), "bk.expect.no_rows()"),
        (
            bk.expect.no_rows(by="relative", warn_within=1e-9),
            "bk.expect.no_rows(by='relative', warn_within=1e-09)",
        ),
        (
            bk.expect.no_rows(above_maximum, by="excess"),
            "bk.expect.no_rows(above_maximum, by='excess')",
        ),
        (bk.expect.at_most(5, on="x"), "bk.expect.at_most(5, on='x')"),
        (bk.expect.between(0, 1), "bk.expect.between(0, 1)"),
    ],
)
def test_an_expectation_reads_as_the_call_that_makes_it(
    expectation: bk.Expectation, shown: str
) -> None:
    assert repr(expectation) == shown


def test_levels() -> None:
    assert LEVELS == ("off", "warn", "error")
    assert resolve_level(None, None, "error") == "error"
    assert resolve_level(None, "warn", "error") == "warn"
    assert resolve_level("off", "warn", "error") == "off"
    assert level_problem("warn") is None
    assert level_problem("loud") == 'level must be "off", "warn" or "error", got \'loud\''


# ---------------------------------------------------------------------------------------------
# Properties of the evaluation, over random tables


def random_table(rng: random.Random) -> pl.DataFrame:
    """A table of unique rows over Region and Time, nulls among Region and among the values."""
    regions = ["EUR", "SSA", "USA", None]
    keys = [(r, t) for r in regions for t in range(2020, 2020 + rng.randint(1, 6))]
    rows = rng.sample(keys, rng.randint(0, len(keys)))
    values = [
        None if rng.random() < 0.15 else rng.choice([0.0, 1.0, rng.uniform(-2, 3)]) for _ in rows
    ]
    return pl.DataFrame(
        {"Region": [r for r, _ in rows], "Time": [t for _, t in rows], "value": values},
        schema={"Region": pl.String, "Time": pl.Int64, "value": pl.Float64},
    )


def distance(expectation: bk.Expectation, value: float | None) -> float | None:
    if value is None:
        return None
    record = expectation.record()
    if record.kind == "no_rows":
        return abs(value)
    if record.kind == "at_most":
        return value - record.bound
    if record.kind == "at_least":
        return record.bound - value
    return max(record.low - value, value - record.high)


EXPECTATIONS = [
    bk.expect.between(0, 1),
    bk.expect.between(0, 1, warn_within=0.5),
    bk.expect.at_most(1),
    bk.expect.at_least(0, warn_within=0.25),
    bk.expect.no_rows(),
    bk.expect.no_rows(by="value", warn_within=1),
]


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("level", ["warn", "error"])
def test_the_evaluation_of_a_random_table(seed: int, level: Level) -> None:
    rng = random.Random(seed)
    table = random_table(rng)
    for expectation in EXPECTATIONS:
        evaluated = evaluate(expectation, table, DIMS, ["value"], level)
        found, rows = evaluated.outcome, evaluated.offending
        bound = expectation.record().kind != "no_rows"
        distances = [distance(expectation, v) for v in rows["value"].to_list()]
        # Bounds are inclusive and nulls never offend; no_rows lets every row offend.
        if bound:
            assert all(d is not None and d > 0 for d in distances)
            assert found.evaluated == table["value"].count()
            expected = sum(
                1 for v in table["value"].to_list() if (d := distance(expectation, v)) and d > 0
            )
            assert found.offending == expected
        else:
            assert (found.evaluated, found.offending) == (None, table.height)
        assert found.offending == rows.height
        assert 0 <= found.within <= found.offending
        # The worst has the largest distance, and the rows are worst first, nulls last.
        known = [d for d in distances if d is not None]
        if known:
            assert distances[0] == max(known)
            assert found.worst == rows["value"][0]
            assert found.distance == pytest.approx(distances[0])
            assert known == sorted(known, reverse=True)
            assert distances[: len(known)] == known
        # The order is total: the same rows in another order give the same offending rows.
        shuffled = table.sample(fraction=1.0, shuffle=True, seed=seed)
        again = evaluate(expectation, shuffled, DIMS, ["value"], level)
        assert again.offending.equals(rows)
        assert again.outcome == found
        # The result follows from the rows, the level and warn_within.
        if not found.offending:
            assert found.result == "met"
        elif level == "warn" or found.within == found.offending:
            assert found.result == "warning"
        else:
            assert found.result == "failed"
