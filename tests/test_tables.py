"""Tables: conversion to polars, column roles, checks, schema and output order."""

import datetime as dt
import io
import subprocess
import sys
import textwrap
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pytest
import xarray as xr

import blicket as bk
from blicket.plots._base import BuiltinPlotType
from blicket.tables import Checked, TableError, check, to_polars

LINE = bk.plots.line(x="year", y="value")
FRAME = pl.DataFrame({"year": [2020, 2021], "region": ["a", "b"], "value": [1.0, 2.0]})


def blick(plot: bk.PlotSpec = LINE, **options: Any) -> bk.Blick:
    return bk.Blick(id="t/x", title="X", group="t", plot=plot, transform=lambda run: run, **options)


def checked(frame: pl.DataFrame, **options: Any) -> pl.DataFrame:
    """The output frame of a table that passes every check."""
    result = check(frame, blick(**options))
    assert result.problems == ()
    assert result.frame is not None
    return result.frame


def messages(result: Checked, severity: str = "error") -> list[str]:
    return [p.message for p in result.problems if p.severity == severity]


def errors(frame: pl.DataFrame, plot: bk.PlotSpec = LINE, **options: Any) -> list[str]:
    result = check(frame, blick(plot, **options))
    assert result.frame is None
    return messages(result)


# ---------------------------------------------------------------------------------------------
# Conversion


class FlodymLike:
    """Has ``to_df()``, as flodym arrays do."""

    def to_df(self) -> pd.DataFrame:
        index = pd.MultiIndex.from_tuples([(2020, "EUR"), (2020, "USA")], names=["Time", "Region"])
        return pd.DataFrame({"value": [1.0, 2.0]}, index=index)


def test_polars_frames_pass_and_lazy_frames_are_collected() -> None:
    frame = pl.DataFrame({"year": [2020], "value": [1.0]})
    assert to_polars(frame) == (frame, False)
    assert to_polars(frame.lazy())[0].equals(frame)


@pytest.mark.parametrize(
    ("value", "columns"),
    [
        (FlodymLike().to_df(), ["Time", "Region", "value"]),
        (FlodymLike(), ["Time", "Region", "value"]),
        (pd.DataFrame({"a": [1, 2, 3], "v": [0.1, 0.2, 0.3]}), ["a", "v"]),
        (pa.table({"a": ["x"], "v": [1.0]}), ["a", "v"]),
        (
            xr.DataArray([[1.0, 2.0]], dims=["x", "y"], coords={"x": ["a"], "y": [1, 2]}, name="v"),
            ["x", "y", "v"],
        ),
    ],
    ids=["pandas-multiindex", "to_df", "pandas-row-numbers", "pyarrow", "xarray"],
)
def test_conversions(value: object, columns: list[str]) -> None:
    frame, index_dropped = to_polars(value)
    assert (frame.columns, index_dropped) == (columns, False)


def test_pandas_columns_through_numpy() -> None:
    frame = pd.DataFrame(
        {
            "level": pd.Categorical(["low", "high", "low"], ["low", "high"], ordered=True),
            "rank": pd.Categorical([2, 1, 2], [2, 1], ordered=True),
            "region": pd.Categorical(["b", "a", None]),
            "name": pd.Series(["x", None, "z"], dtype="str"),
            "count": pd.Series([1, None, 3], dtype="Int64"),
            "value": [1.0, np.nan, 3.0],
        }
    )
    converted, _ = to_polars(frame)
    assert converted.schema == pl.Schema(
        {
            "level": pl.Enum(["low", "high"]),
            "rank": pl.Enum(["2", "1"]),
            "region": pl.String,
            "name": pl.String,
            "count": pl.Int64,
            "value": pl.Float64,
        }
    )
    assert converted["region"].to_list() == ["b", "a", None]


def test_named_index_levels_are_kept_and_unnamed_ones_dropped() -> None:
    half_named = FlodymLike().to_df().rename_axis(["Time", None])
    frame, index_dropped = to_polars(half_named)
    assert (frame.columns, index_dropped) == (["Time", "value"], True)
    filtered = pd.DataFrame({"year": [2020, 2021], "value": [1.0, 2.0]}).iloc[[1]]
    assert to_polars(filtered)[0].columns == ["year", "value"]  # silent unless a check fails


def test_a_missing_column_mentions_a_dropped_index() -> None:
    years = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index([2020, 2021]))
    frame, index_dropped = to_polars(years)
    error = messages(check(frame, blick(), index_dropped))[0]
    assert error.endswith(
        "(an unnamed pandas index level was dropped; if it holds data, name it, df.index.name = "
        '"year" or df.index.names = [...]; if it is only row numbers, call reset_index(drop=True))'
    )
    assert "dropped" not in errors(FRAME.drop("year"))[0]


@pytest.mark.parametrize(
    ("value", "phrase"),
    [
        ({"year": [2020]}, "returned a dict; wrap it in pl.DataFrame(...)"),
        (None, "returned None; did it forget return?"),
        (pd.Series([1.0], name="value"), 'a pandas Series; return series.to_frame("value")'),
        (pl.Series("value", [1.0]), 'a polars Series; return series.to_frame("value")'),
        (3, "returned int; return a polars or pandas frame"),
        ((1, 2), "returned tuple; return"),
        (
            FlodymLike().to_df().rename_axis(["value", "Region"]),
            "the pandas index level 'value' is also a column (or appears twice)",
        ),
        (
            FlodymLike().to_df().rename_axis(["Time", "Time"]),
            "the pandas index level 'Time' is also a column (or appears twice)",
        ),
    ],
)
def test_unsupported_values(value: object, phrase: str) -> None:
    with pytest.raises(TableError) as info:
        to_polars(value)
    assert phrase in str(info.value)


def test_to_df_must_give_a_pandas_frame() -> None:
    class Wrong:
        def to_df(self) -> list[int]:
            return []

    with pytest.raises(
        TableError, match=r"returned tests\.test_tables\.Wrong, whose to_df\(\) gives list"
    ):
        to_polars(Wrong())


def test_conversion_needs_no_pyarrow() -> None:
    # None in sys.modules makes a module look absent: importing it raises ModuleNotFoundError.
    code = textwrap.dedent(
        """
        import sys

        sys.modules["pyarrow"] = None
        import pandas as pd
        from blicket.tables import to_polars

        index = pd.MultiIndex.from_tuples([(2020, "EUR")], names=["Time", "Region"])
        frame, _ = to_polars(pd.DataFrame({"value": [1.0]}, index=index))
        assert frame.columns == ["Time", "Region", "value"], frame.columns
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------------------------
# Roles, types and output


def test_roles_are_inferred_from_types_and_the_plot() -> None:
    frame = pl.DataFrame(
        {"value": [2.0, 1.0], "region": ["b", "a"], "year": [2021, 2020], "flag": [True, False]}
    )
    plot = bk.plots.line(x="year", y="value", color="region", linetype="flag")
    result = check(frame, blick(plot))
    assert result.frame is not None
    assert result.frame.columns == ["region", "year", "flag", "value"]
    assert result.frame["year"].to_list() == [2020, 2021]  # sorted by the dimensions
    assert result.schema is not None
    dimensions = [(d.name, d.dtype) for d in result.schema.dimensions]
    assert dimensions == [("region", "string"), ("year", "integer"), ("flag", "boolean")]
    assert [(m.name, m.dtype) for m in result.schema.measures] == [("value", "float")]


def test_dims_and_measures_override_inference() -> None:
    frame = pl.DataFrame({"count": [3, 4], "year": [2020, 2021], "region": ["a", "a"]})
    output = checked(frame, plot=bk.plots.line(x="year", y="count"), measures=("count",))
    assert output.columns == ["year", "region", "count"]
    assert output.schema["count"] == pl.Float64
    by_dims = checked(frame, plot=bk.plots.line(x="year", y="count"), dims=("region", "year"))
    assert by_dims.columns == ["region", "year", "count"]


@pytest.mark.parametrize(
    ("options", "where"), [({}, " (bound to x=)"), ({"dims": ("year",)}, " (in dims=)")]
)
def test_float_dimensions_are_rejected(options: dict[str, Any], where: str) -> None:
    frame = pl.DataFrame({"year": [2020.0, 2021.0], "value": [1.0, 2.0]})
    assert errors(frame, **options) == [
        f"column 'year'{where} is Float64; dimensions are strings, integers, booleans, dates or "
        "datetimes, because their values are keys; round and cast it, e.g. .astype(int) in pandas, "
        ".cast(pl.Int64) in polars"
    ]


def test_dates_and_datetimes_are_dimensions() -> None:
    frame = pl.DataFrame(
        {
            "day": [dt.date(2020, 1, 2), dt.date(2020, 1, 1)],
            "at": [dt.datetime(2020, 1, 1, 12), dt.datetime(2020, 1, 1, 6)],
            "value": [1.0, 2.0],
        }
    )
    result = check(frame, blick(bk.plots.line(x="day", y="value", color="at")))
    assert result.schema is not None
    assert [(d.dtype, d.values[0]) for d in result.schema.dimensions] == [
        ("date", dt.date(2020, 1, 1)),
        ("datetime", dt.datetime(2020, 1, 1, 6)),
    ]


def test_categorical_becomes_string_and_nan_becomes_null() -> None:
    frame = pl.DataFrame(
        {"year": pl.Series(["a", "b"], dtype=pl.Categorical), "value": [float("nan"), 1.0]}
    )
    output = checked(frame)
    assert output.schema["year"] == pl.String
    assert output["value"].to_list() == [None, 1.0]


def test_pandas_and_polars_give_the_same_parquet() -> None:
    times = pd.to_datetime(["2020-01-01 13:00", "2020-01-02 13:00"])
    from_pandas = pd.DataFrame(
        {
            "year": [2021, 2020],
            "at": times.astype("datetime64[ns]"),
            "zoned": times.tz_localize("Europe/Berlin"),
            "value": [np.nan, 1.0],
        }
    ).set_index(["year", "at", "zoned"])
    from_polars = pl.DataFrame(
        {
            "year": [2020, 2021],
            "at": [dt.datetime(2020, 1, 2, 13), dt.datetime(2020, 1, 1, 13)],
            "zoned": [dt.datetime(2020, 1, 2, 12), dt.datetime(2020, 1, 1, 12)],
            "value": [1.0, None],
        }
    )
    plot = bk.plots.line(x="year", y="value", color="at", linetype="zoned")
    files = []
    for value in (from_pandas, from_polars):
        result = check(to_polars(value)[0], blick(plot))
        assert result.frame is not None
        buffer = io.BytesIO()
        result.frame.write_parquet(buffer)
        files.append(buffer.getvalue())
    assert files[0] == files[1]


def test_schema_values_follow_order_then_enum_then_sorting() -> None:
    frame = pl.DataFrame(
        {
            "year": [2021, 2020, 2021, 2020],
            "scenario": ["low", "high", "high", "low"],
            "level": pl.Series(["b", "a", "a", "b"], dtype=pl.Enum(["b", "a"])),
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    plot = bk.plots.line(x="year", y="value", color="scenario", linetype="level")
    result = check(frame, blick(plot, order={"scenario": ("low",)}))
    assert result.schema is not None
    values = {d.name: d.values for d in result.schema.dimensions}
    assert values == {"year": [2020, 2021], "scenario": ["low", "high"], "level": ["b", "a"]}
    # The Enum gives its order to the values and becomes a string column, sorted by value.
    assert result.schema.dimensions[2].dtype == "string"
    assert result.frame is not None
    assert result.frame["level"].to_list() == ["a", "b", "a", "b"]


def test_output_is_deterministic() -> None:
    frame = pl.DataFrame({"year": [2020, 2021, 2022], "value": [1.0, 2.0, 3.0]})
    assert checked(frame).equals(checked(frame.reverse()))


class Number(BuiltinPlotType):
    """A plot type without dimension channels."""

    name = "number"
    channels = (bk.Channel("value", "measure", required=True),)


def test_a_table_without_dimensions_has_at_most_one_row() -> None:
    plot = bk.PlotSpec(Number(), {"value": "value"})
    assert checked(pl.DataFrame({"value": [1.0]}), plot=plot).height == 1
    assert errors(pl.DataFrame({"value": [1.0, 2.0]}), plot) == [
        "the table has 2 rows but no dimension column to tell them apart"
    ]


def test_dimension_types_are_normalised() -> None:
    frame = pl.DataFrame(
        {
            "small": pl.Series([1, 2], dtype=pl.Int8),
            "nanos": pl.Series([dt.datetime(2020, 1, 1)] * 2, dtype=pl.Datetime("ns")),
            "zoned": pl.Series(
                [dt.datetime(2020, 1, 1, 12), dt.datetime(2020, 1, 1, 13)]
            ).dt.replace_time_zone("Europe/Berlin"),
            "value": [1.0, 2.0],
        }
    )
    plot = bk.plots.line(x="small", y="value", color="nanos", linetype="zoned")
    result = check(frame, blick(plot))
    assert result.frame is not None
    assert dict(result.frame.schema) == {
        "small": pl.Int64,
        "nanos": pl.Datetime("us"),
        "zoned": pl.Datetime("us"),
        "value": pl.Float64,
    }
    assert result.frame["zoned"][0] == dt.datetime(2020, 1, 1, 11)
    assert messages(result, "warning") == [
        "'zoned' in time zone Europe/Berlin was converted to UTC"
    ]


def test_an_empty_table_is_a_warning() -> None:
    result = check(FRAME.head(0), blick())
    assert result.frame is not None
    assert messages(result, "warning") == ["the table has no rows"]
    assert errors(pl.DataFrame()) == ["the table has no columns"]


# ---------------------------------------------------------------------------------------------
# Checks


@pytest.mark.parametrize(
    ("frame", "options", "phrase"),
    [
        (FRAME, {"plot": bk.plots.line(x="time", y="value")}, "maps x= to the column 'time'"),
        (FRAME, {"plot": bk.plots.line(x="year", y="region")}, "'region' on y= is a string col"),
        (
            FRAME.with_columns(count=pl.lit(1)),
            {"plot": bk.plots.line(x="year", y="count", color="region"), "measures": ("value",)},
            "integer column and so counts as a dimension; add 'count' to measures=",
        ),
        (
            FRAME,
            {"plot": bk.plots.line(x="year", y="value"), "measures": ("value", "year")},
            "x= needs a dimension, but measures= names 'year'",
        ),
        (
            pl.DataFrame({"year": [2020, 2021], "count": [1, 2]}),
            {"plot": bk.plots.line(x="year", y="count"), "dims": ("year", "count")},
            "y= needs a measure, but dims= names 'count'",
        ),
        (
            FRAME.with_columns(count=pl.lit(1)),
            {
                "plot": bk.plots.line(x="year", y="value", color="count"),
                "dims": ("year", "region"),
            },
            "color= needs a dimension, but dims= leaves out 'count'",
        ),
        (
            FRAME.with_columns(count=pl.lit(1)),
            {"plot": bk.plots.line(x="year", y="count", color="region")},
            'integer column and so counts as a dimension; add measures=["count"]',
        ),
        (
            FRAME,
            {"dims": ("year",)},
            "'region' is a string column; with dims= given, every other column is a measure, so "
            "add it to dims=",
        ),
        (FRAME.with_columns(extra=pl.lit(1.0)), {}, "'extra' are bound to no plot channel"),
        (
            pl.DataFrame({"year": [2020, 2020], "value": [1.0, 2.0]}),
            {},
            "2 rows repeat the dimension values of another row, such as {'year': 2020}",
        ),
        (
            pl.DataFrame({"year": [2020, None], "value": [1.0, 2.0]}),
            {},
            "dimension column 'year' has 1 null value(s)",
        ),
        (FRAME, {"controls": {"year": "split"}}, "the plot binds 'year' to x="),
        (FRAME, {"controls": {"scenario": "split"}}, "has no dimension 'scenario'"),
        (FRAME, {"order": {"value": (1.0,)}}, "order['value']: the table has no dimension"),
        (FRAME, {"defaults": {"nope": "a"}}, "defaults['nope']: the table has no dimension"),
        (FRAME, {"dims": ("year", "nope")}, "names the column 'nope', which the table lacks; its"),
        (FRAME, {"dims": ("year", "region"), "measures": ("value", "year")}, "in both dims="),
        (FRAME, {"dims": ("year",), "measures": ("value",)}, "'region' are in neither dims="),
        (FRAME, {"measures": ("value", "region")}, "'region' is a string column and cannot be a"),
        (FRAME.with_columns(region=pl.lit([1, 2])), {}, "column 'region' is List(Int64);"),
        (FRAME.with_columns(region=pl.lit({"a": 1})), {}, "column 'region' is Struct"),
        (FRAME.with_columns(region=pl.lit(None)), {}, "column 'region' is Null;"),
        (
            FRAME.with_columns(region=pl.Series([object(), object()], dtype=pl.Object)),
            {},
            "column 'region' is Object;",
        ),
    ],
)
def test_checks(frame: pl.DataFrame, options: dict[str, Any], phrase: str) -> None:
    found = errors(frame, **options)
    assert any(phrase in error for error in found), found


@pytest.mark.parametrize(
    "options",
    [
        {"measures": ("nope",)},
        {"dims": ("year", "nope")},
        {"dims": ("year", "nope"), "measures": ("value",)},  # region is in neither, unsaid
    ],
)
def test_an_absent_column_in_dims_or_measures_is_the_only_error(options: dict[str, Any]) -> None:
    plot = bk.plots.line(x="year", y="value", color="region")
    (error,) = errors(FRAME, plot, **options)
    assert "names the column 'nope', which the table lacks" in error


def test_a_column_of_a_rejected_type_is_reported_once() -> None:
    (error,) = errors(FRAME.with_columns(value=pl.Series([1, 2], dtype=pl.Decimal(10, 2))))
    assert error.startswith("column 'value' (bound to y=) is Decimal")


def test_a_float_left_out_of_measures_is_named() -> None:
    plot = bk.plots.line(x="year", y="value", color="region")
    found = errors(FRAME.with_columns(a=pl.lit(1.0)), plot, measures=("a",))
    assert (
        "'value' on y= is a float column that measures= leaves out, so it counts as a dimension; "
        "add 'value' to measures="
    ) in found
    assert not any(".astype(int)" in error for error in found)


def test_every_problem_is_collected() -> None:
    frame = pl.DataFrame({"year": [2020, 2020], "value": [1.0, 2.0], "extra": [0.0, 0.0]})
    found = errors(frame, controls={"nope": "filter"}, order={"nada": ("a",)})
    assert len(found) == 4  # unbound measure, duplicates, controls, order


def test_problems_name_the_blick() -> None:
    (problem,) = check(FRAME.with_columns(extra=pl.lit(1.0)), blick()).problems
    assert (problem.kind, problem.ids) == ("table", ("t/x",))


def test_order_and_default_values_missing_from_the_run_are_warnings() -> None:
    plot = bk.plots.line(x="year", y="value", color="region")
    result = check(FRAME, blick(plot, order={"region": ("c", "a")}, defaults={"region": ["d"]}))
    assert result.frame is not None
    assert messages(result, "warning") == [
        "order['region'] names 'c', which this run's table does not contain",
        "defaults['region'] names 'd', which this run's table does not contain",
    ]
