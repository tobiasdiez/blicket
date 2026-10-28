"""``bk.Frames``, the dataset over tables: what it reads from the tables, how it selects, and what
it refuses."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import pytest

import blicket as bk
from blicket.dataset import check
from blicket.query import Query, run_query

HERE = Path(__file__).parent
YEAR = bk.Dimension(name="year", dtype="integer", values=[2020, 2021])
REGION = bk.Dimension(name="region", dtype="string", values=["north", "south"])
PROCESS = bk.Dimension(name="process", dtype="string", values=["BOF", "EAF"])


def steel() -> pl.DataFrame:
    """Steel flows over two years (the later one first), two regions and two processes."""
    combinations = [
        (y, r, p) for y in (2021, 2020) for r in ("north", "south") for p in ("BOF", "EAF")
    ]
    rows = [(*combination, float(i)) for i, combination in enumerate(combinations)]
    return pl.DataFrame(rows, schema=["year", "region", "process", "value"], orient="row")


def test_a_quantity_from_a_table_takes_its_dimensions_from_the_columns() -> None:
    frames = bk.Frames()
    quantity = frames.add("flows/steel", steel(), unit="t", group="flows")
    assert quantity == bk.Quantity(
        name="flows/steel", unit="t", dimensions=("year", "region", "process"), group="flows"
    )
    assert frames.quantities() == [quantity]
    # integers sorted, strings in order of appearance
    assert frames.dimensions() == [YEAR, REGION, PROCESS]
    assert list(check(frames, HERE).quantities) == ["flows/steel"]


def test_dimensions_given_ahead_come_first_and_the_unused_are_left_out() -> None:
    process = bk.Dimension(name="process", dtype="string", values=["EAF", "BOF"])
    scenario = bk.Dimension(name="scenario", dtype="string", values=["baseline"])
    frames = bk.Frames(dimensions=[process, scenario])
    frames.add("flows/steel", steel())
    assert frames.dimensions() == [process, YEAR, REGION]


def test_the_values_of_a_dimension_are_the_union_over_the_tables() -> None:
    frames = bk.Frames()
    frames.add(
        "a",
        pl.DataFrame(
            {
                "year": pl.Series([2022, 2020], dtype=pl.Int32),
                "region": pl.Series(["east", "west"], dtype=pl.Categorical),
                "value": [1.0, 2.0],
            }
        ),
    )
    frames.add(
        "b", pl.DataFrame({"year": [2021, 2021], "region": ["west", "north"], "v": [3.0, 4.0]})
    )
    assert frames.dimensions() == [
        bk.Dimension(name="year", dtype="integer", values=[2020, 2021, 2022]),
        bk.Dimension(name="region", dtype="string", values=["east", "west", "north"]),
    ]


def test_dates_and_datetimes_are_read_as_such() -> None:
    noon = datetime(2026, 1, 1, 12)
    frames = bk.Frames()
    frames.add(
        "x",
        pl.DataFrame(
            {
                "day": [date(2026, 1, 2), date(2026, 1, 1)],
                "at": pl.Series([noon, datetime(2026, 1, 1, 6)]).dt.replace_time_zone(
                    "Europe/Berlin"
                ),
                "value": [1.0, 2.0],
            }
        ),
    )
    assert frames.dimensions() == [
        bk.Dimension(name="day", dtype="date", values=[date(2026, 1, 1), date(2026, 1, 2)]),
        bk.Dimension(
            name="at", dtype="datetime", values=[datetime(2026, 1, 1, 5), datetime(2026, 1, 1, 11)]
        ),
    ]


def test_select_filters_by_the_values_and_sums_over_the_dimensions_not_kept() -> None:
    frames = bk.Frames()
    frames.add("flows/steel", steel())
    frame = frames.select("flows/steel", ["year"], {"region": ["north"]})
    expected = (
        steel()
        .filter(region="north")
        .group_by("year", maintain_order=True)
        .agg(pl.col("value").sum())
    )
    assert frame.equals(expected)
    total = frames.select("flows/steel", [], {})
    assert total.to_dicts() == [{"value": steel()["value"].sum()}]
    nothing = frames.select("flows/steel", ["year"], {"region": ["west"]})
    assert nothing.columns == ["year", "value"]
    assert nothing.is_empty()


def test_a_sum_of_nulls_only_stays_null() -> None:
    frames = bk.Frames()
    frames.add("x", pl.DataFrame({"year": [2020, 2020, 2021], "value": [None, None, 1.0]}))
    assert frames.select("x", ["year"], {})["value"].to_list() == [None, 1.0]
    assert frames.select("x", [], {"year": [2020]})["value"].to_list() == [None]


def test_the_measure_need_not_be_the_last_column_when_the_dimensions_are_named() -> None:
    frames = bk.Frames()
    frames.add("x", pl.DataFrame({"value": [1.0, 2.0], "year": [2020, 2021]}), dimensions=["year"])
    assert frames.select("x", ["year"], {}).to_dicts() == [
        {"year": 2020, "value": 1.0},
        {"year": 2021, "value": 2.0},
    ]


def test_tables_may_be_pandas_frames_or_objects_with_to_df() -> None:
    class Array:
        """Like a flodym array: callable, with ``to_df()`` giving the dimensions as the index."""

        def __call__(self) -> None:
            raise AssertionError("a table is not called")

        def to_df(self) -> pd.DataFrame:
            return pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index([2020, 2021], name="year"))

    frames = bk.Frames()
    frames.add("a", Array())
    frames.add("b", pd.DataFrame({"year": [2020], "value": [3.0]}))
    assert [q.dimensions for q in frames.quantities()] == [("year",), ("year",)]
    assert frames.select("a", ["year"], {})["value"].to_list() == [1.0, 2.0]
    assert frames.dimensions() == [YEAR]


def test_a_function_is_called_once_the_table_is_first_needed() -> None:
    calls = 0

    def table() -> pl.DataFrame:
        nonlocal calls
        calls += 1
        return steel()

    frames = bk.Frames()
    frames.add("flows/steel", table, dimensions=["year", "region", "process"])
    assert calls == 0
    frames.select("flows/steel", ["year"], {})
    frames.select("flows/steel", [], {})
    frames.dimensions()
    assert calls == 1
    # Without the dimensions, the table is read at once: they are its columns.
    frames.add("flows/scrap", table)
    assert calls == 2


def test_the_last_eight_tables_read_stay_converted() -> None:
    calls: dict[str, int] = {}
    frames = bk.Frames()
    for i in range(9):
        name = f"q{i}"

        def table(name: str = name) -> pl.DataFrame:
            calls[name] = calls.get(name, 0) + 1
            return pl.DataFrame({"year": [2020], "value": [1.0]})

        frames.add(name, table, dimensions=["year"])
    for i in range(9):
        frames.select(f"q{i}", [], {})
    frames.select("q8", [], {})
    frames.select("q0", [], {})
    assert (calls["q8"], calls["q0"]) == (1, 2)


def test_a_subclass_aggregates_its_own_way() -> None:
    class Means(bk.Frames):
        def select(
            self, quantity: str, keep: Sequence[str], values: Mapping[str, Sequence[Any]]
        ) -> pl.DataFrame:
            frame = self.frame(quantity)
            return frame.group_by(keep, maintain_order=True).agg(pl.col("value").mean())

    frames = Means()
    frames.add("flows/steel", steel())
    frame = frames.select("flows/steel", ["year"], {})
    assert frame["value"].to_list() == [1.5, 5.5]
    assert list(check(frames, HERE).quantities) == ["flows/steel"]


def test_a_query_runs_over_frames() -> None:
    frames = bk.Frames()
    frames.add("flows/steel", steel(), unit="t", group="flows")
    frames.add("flows/scrap", steel().with_columns(pl.col("value") * 10), unit="t", group="flows")
    query = Query(
        quantities=("flows/steel", "flows/scrap"),
        plot="line",
        mapping={"x": "year"},
        values={"region": ("south",)},
    )
    result = run_query(check(frames, HERE), query, HERE)
    assert result.table is not None, result.entry.problems
    table = pl.read_parquet(result.table)
    south = steel().filter(region="south").group_by("year").agg(pl.col("value").sum() * 11)
    assert table.sort("year").to_dicts() == south.sort("year").to_dicts()


def test_what_frames_refuse() -> None:
    with pytest.raises(ValueError, match="the dimension 'year' is given twice"):
        bk.Frames(dimensions=[YEAR, YEAR])
    frames = bk.Frames()
    frames.add("x", steel())
    with pytest.raises(ValueError, match="'x' was added twice"):
        frames.add("x", steel())
    with pytest.raises(ValueError, match="the table of 'empty' has no columns"):
        frames.add("empty", pl.DataFrame())
    with pytest.raises(ValueError, match=r"the table of 'd': the transformation returned a dict"):
        frames.add("d", {"year": [2020]})


def test_a_table_whose_columns_are_not_the_dimensions_and_a_measure() -> None:
    frames = bk.Frames()
    frames.add("x", pl.DataFrame({"year": [2020], "value": [1.0]}), dimensions=["year", "region"])
    with pytest.raises(
        ValueError,
        match=r"the table of 'x' has the columns year, value; expected its dimensions "
        r"\(year, region\) and one measure column",
    ):
        frames.select("x", ["year"], {})
    frames = bk.Frames()
    frames.add("y", pl.DataFrame({"year": [2020], "a": [1.0], "b": [2.0]}), dimensions=["year"])
    with pytest.raises(ValueError, match="the table of 'y' has the columns year, a, b"):
        frames.dimensions()


def test_a_dimension_column_of_another_type() -> None:
    frames = bk.Frames()
    frames.add("x", pl.DataFrame({"share": [0.5], "value": [1.0]}))
    with pytest.raises(
        ValueError,
        match="the column 'share' of 'x' is Float64; dimensions are strings, integers, booleans, "
        "dates or datetimes",
    ):
        frames.dimensions()
    frames = bk.Frames()
    frames.add("a", pl.DataFrame({"year": [2020], "value": [1.0]}))
    frames.add("b", pl.DataFrame({"year": ["2020"], "value": [1.0]}))
    with pytest.raises(
        ValueError, match="the column 'year' is an integer in 'a' but a string in 'b'"
    ):
        frames.dimensions()
