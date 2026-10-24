"""The diff routine of the built-in plot types: flags, scale, magnitude and where."""

from collections.abc import Sequence
from typing import Any

import polars as pl
import pytest

from blicket.plots._diff import compare
from blicket.schema import Change, Flag

SCHEMA: frozenset[Flag] = frozenset({"schema"})


def frame(value: Sequence[float | None], **dims: list[Any]) -> pl.DataFrame:
    """A table with the dimension columns ``dims`` and the measure ``value``."""
    return pl.DataFrame({**dims, "value": value}, schema_overrides={"value": pl.Float64})


def mixed(value: list[float]) -> pl.DataFrame:
    """Eight rows by x, color and region."""
    keys = {"x": [1] * 4 + [2] * 4, "color": list("aabb") * 2, "region": list("ns") * 4}
    return frame(value, **keys)


def test_identical_tables_are_unchanged() -> None:
    table = frame([1.0, -2.0, None], x=[1, 2, 3])
    assert compare(table, table, "value", []) == Change(magnitude=0.0)


@pytest.mark.parametrize("factor", [-1.0, 1e-30, 3.7, 1e12])
@pytest.mark.parametrize(
    ("panels", "stacked_by"), [([], None), (["region"], None), ([], "color"), (["region"], "color")]
)
def test_scaling_both_tables_keeps_the_magnitude(
    factor: float, panels: list[str], stacked_by: str | None
) -> None:
    baseline = mixed([3.0, -0.5, 120.0, 7.0, -2.0, 0.01, 45.0, -9.0])
    current = mixed([3.3, -0.4, 118.0, 7.0, -2.5, 0.02, 40.0, -9.0])
    expected = compare(baseline, current, "value", panels, stacked_by).magnitude
    assert expected is not None
    assert 0 < expected < 1
    scaled = [table.with_columns(pl.col("value") * factor) for table in (baseline, current)]
    magnitude = compare(*scaled, "value", panels, stacked_by).magnitude
    assert magnitude == pytest.approx(expected, rel=1e-9)


def test_a_change_across_zero_counts_both_sides() -> None:
    baseline, current = frame([1.0, 0.4], x=[1, 2]), frame([1.0, -0.4], x=[1, 2])
    assert compare(baseline, current, "value", []).magnitude == 0.8


def test_the_magnitude_is_at_most_1() -> None:
    change = compare(frame([1.0, 1.0], x=[1, 2]), frame([1.0, -100.0], x=[1, 2]), "value", [])
    assert change.magnitude == 1.0


def test_a_value_of_one_table_only_is_schema_and_its_rows_are_left_out() -> None:
    baseline = frame([1.0, 1.0], x=[1, 2], scenario=["A", "A"])
    current = frame([1.0, 50.0, 1.1, 50.0], x=[1, 1, 2, 2], scenario=["A", "B", "A", "B"])
    # The rows of scenario B neither count nor set the scale, though they share the panel.
    change = compare(baseline, current, "value", [])
    assert (change.flags, change.values_added, change.values_removed) == (
        SCHEMA,
        {"scenario": ["B"]},
        {},
    )
    assert change.magnitude == pytest.approx(0.1 / 1.1)
    assert change.where == {"x": 2, "scenario": "A"}


def test_values_of_one_table_only_come_sorted_for_each_dimension() -> None:
    baseline = frame([1.0, 1.0], x=[1, 1], scenario=["A", "B"])
    x = [1, 1, 1, 1, 1, 7, 3, 5, 2]
    scenario = ["A", "Z", "M", "C", "Q", "A", "A", "A", "A"]
    current = frame([1.0] * len(x), x=x, scenario=scenario)
    change = compare(baseline, current, "value", [])
    assert (change.values_added, change.values_removed) == (
        {"x": [2, 3, 5, 7], "scenario": ["C", "M", "Q", "Z"]},
        {"scenario": ["B"]},
    )
    assert change.magnitude == 0.0


def test_a_value_of_the_baseline_only_is_removed() -> None:
    baseline = frame([1.0, 1.0], x=[1, 1], scenario=["A", "B"])
    change = compare(baseline, baseline.head(1), "value", [])
    assert (change.flags, change.values_removed, change.magnitude) == (
        SCHEMA,
        {"scenario": ["B"]},
        0.0,
    )


def test_stacks_leave_out_the_rows_of_a_value_of_one_table_only() -> None:
    baseline = frame([1.0, 1.0], x=[1, 1], color=["a", "b"])
    current = frame([1.0, 1.5, 10.0], x=[1, 1, 1], color=["a", "b", "c"])
    change = compare(baseline, current, "value", [], "color")
    assert change.values_added == {"color": ["c"]}
    assert change.magnitude == pytest.approx(0.5 / 2.5)
    assert change.where == {"x": 1, "color": "b"}


def test_a_dropped_row_counts_as_0() -> None:
    baseline = frame([2.0, 1.0, 4.0, 0.5], x=[1, 1, 2, 2], color=["a", "b", "a", "b"])
    change = compare(baseline, baseline.head(3), "value", [])
    assert (change.flags, change.magnitude, change.where) == (
        frozenset(),
        0.125,
        {"x": 2, "color": "b"},
    )


def test_nulls_count_on_one_side_only() -> None:
    baseline = frame([2.0, None, None], x=[1, 2, 3])
    current = frame([2.0, None, 1.0], x=[1, 2, 3])
    assert compare(baseline, current, "value", []).magnitude == 0.5


def test_nan_counts_as_null() -> None:
    baseline = frame([2.0, float("nan")], x=[1, 2])
    current = frame([2.0, 1.0], x=[1, 2])
    assert compare(baseline, current, "value", []).magnitude == 0.5


def test_the_scale_of_a_zero_panel_is_floored() -> None:
    baseline = frame([0.0, 0.0, 1.0, 1.0], x=[1, 2, 1, 2], region=["a", "a", "b", "b"])
    current = frame([0.0, 1e-9, 1.0, 1.0], x=[1, 2, 1, 2], region=["a", "a", "b", "b"])
    assert compare(baseline, current, "value", ["region"]).magnitude == pytest.approx(1e-3)


def test_the_scale_of_a_zero_stack_is_floored() -> None:
    baseline = frame([0.0, 0.0, 1.0, 1.0], x=[1, 1, 2, 2], color=["a", "b", "a", "b"])
    current = frame([1e-9, 0.0, 1.0, 1.0], x=[1, 1, 2, 2], color=["a", "b", "a", "b"])
    change = compare(baseline, current, "value", ["x"], "color")
    assert change.magnitude == pytest.approx(1e-3)


def test_huge_stacks_do_not_overflow() -> None:
    baseline = frame([1e308] * 3, x=[1] * 3, color=list("abc"))
    current = frame([1e308, 5e307, 1e308], x=[1] * 3, color=list("abc"))
    change = compare(baseline, current, "value", [], "color")
    assert (change.magnitude, change.where) == (pytest.approx(0.5 / 3), {"x": 1, "color": "b"})


def test_the_tiniest_value_against_null_is_total() -> None:
    baseline = frame([None], x=[1])
    assert compare(baseline, frame([5e-324], x=[1]), "value", []).magnitude == 1.0


def test_tables_of_zeros_are_unchanged() -> None:
    zeros = frame([0.0, 0.0], x=[1, 2])
    assert compare(zeros, zeros, "value", ["x"]) == Change(magnitude=0.0)


def test_empty_tables_compare_no_row() -> None:
    empty = frame([1.0], x=[1]).head(0)
    assert compare(empty, empty, "value", []) == Change()


def test_the_scale_of_a_stack_keeps_positive_and_negative_layers_apart() -> None:
    baseline = frame([5.0, -5.0], x=[1, 1], color=["a", "b"])
    current = frame([5.0, -4.0], x=[1, 1], color=["a", "b"])
    assert compare(baseline, current, "value", [], "color").magnitude == pytest.approx(0.2)


def test_a_sign_flip_of_a_stack_is_total_and_names_the_stack() -> None:
    baseline = frame([1.0] * 4, x=[1] * 4, color=list("abcd"))
    current = baseline.with_columns(-pl.col("value"))
    change = compare(baseline, current, "value", [], "color")
    assert (change.magnitude, change.where) == (1.0, {"x": 1})


def test_a_changed_layer_names_its_row_though_its_stack_differs_by_rounding() -> None:
    baseline = frame([1.1, 2.2, 3.3], x=[1] * 3, color=list("abc"))
    current = frame([1.1 * 1.1, 2.2, 3.3], x=[1] * 3, color=list("abc"))
    change = compare(baseline, current, "value", [], "color")
    assert change.where == {"x": 1, "color": "a"}


def test_panels_have_scales_of_their_own() -> None:
    baseline = frame([1.0, 100.0], x=[1, 1], region=["a", "b"])
    current = frame([1.1, 100.0], x=[1, 1], region=["a", "b"])
    assert compare(baseline, current, "value", []).magnitude == pytest.approx(0.1 / 100)
    assert compare(baseline, current, "value", ["region"]).magnitude == pytest.approx(0.1 / 1.1)


def test_where_names_the_first_row_of_a_tie() -> None:
    baseline = frame([None, -1.0, -1.0], x=[3, 3, 4], color=["a", "b", "b"])
    current = frame([6.0, None], x=[4, 4], color=["a", "b"])
    assert compare(baseline, current, "value", ["color"]).where == {"x": 4, "color": "a"}


def test_where_follows_the_sort_order_for_a_row_of_the_current_table_only() -> None:
    baseline = frame([1.0, 1.0, 1.0], x=[1, 2, 2], color=["a", "a", "b"])
    current = frame([1.0, 1.0, 2.0, 1.0], x=[1, 1, 2, 2], color=["a", "b", "a", "b"])
    assert compare(baseline, current, "value", []).where == {"x": 1, "color": "b"}


def test_changed_columns_are_schema_without_magnitude() -> None:
    baseline = frame([1.0], x=[1])
    added = baseline.with_columns(other=pl.lit(2.0))
    assert compare(baseline, added, "value", []) == Change(
        flags=SCHEMA, columns_added={"other": "float"}
    )
    retyped = baseline.with_columns(pl.col("x").cast(pl.String))
    assert compare(baseline, retyped, "value", []) == Change(
        flags=SCHEMA, columns_added={"x": "string"}, columns_removed={"x": "integer"}
    )


def test_a_narrower_integer_key_is_schema() -> None:
    baseline = frame([1.0], x=[1])
    narrow = baseline.with_columns(pl.col("x").cast(pl.Int32))
    assert compare(baseline, narrow, "value", []) == Change(
        flags=SCHEMA, columns_added={"x": "integer"}, columns_removed={"x": "integer"}
    )


def test_the_order_of_the_columns_does_not_matter() -> None:
    table = frame([1.0, 2.0], x=[1, 2], color=["a", "b"])
    reordered = table.select("color", "value", "x")
    assert compare(table, reordered, "value", []) == Change(magnitude=0.0)


@pytest.mark.parametrize("which", ["baseline", "current"])
def test_repeated_dimension_values_are_an_error(which: str) -> None:
    table, repeated = frame([1.0], x=[1]), frame([1.0, 2.0], x=[1, 1])
    tables = {"baseline": table, "current": table, which: repeated}
    with pytest.raises(ValueError, match="dimension values must be unique in each table"):
        compare(tables["baseline"], tables["current"], "value", [])


@pytest.mark.parametrize(
    ("arguments", "error", "message"),
    [
        (
            {"baseline": frame([1.0], x=[1]).lazy()},
            TypeError,
            "the baseline table must be a polars DataFrame, got LazyFrame",
        ),
        ({"panels": "x"}, TypeError, "panels is a list of column names, got the string 'x'"),
        ({"y": "x"}, ValueError, "y='x' holds Int64 values, not floats"),
        ({"y": "valeu"}, ValueError, "y='valeu' is not a column of the current table; did you"),
        (
            {"panels": ["nope"]},
            ValueError,
            "panels name 'nope', which is not a dimension of the current table (dimensions: x, "
            "color)",
        ),
        (
            {"stacked_by": "colour"},
            ValueError,
            "color='colour' is not a dimension of the current table; did you mean 'color'?",
        ),
        ({"stacked_by": "color", "panels": ["color"]}, ValueError, "color='color' is also in"),
        (
            {"baseline": frame([1.0]), "current": frame([1.0])},
            ValueError,
            "the current table has no dimension column beside y='value'",
        ),
    ],
)
def test_arguments_that_do_not_fit(
    arguments: dict[str, Any], error: type[Exception], message: str
) -> None:
    table = frame([1.0], x=[1], color=["a"])
    given: dict[str, Any] = {"baseline": table, "current": table, "y": "value", "panels": []}
    given.update(arguments)
    with pytest.raises(error) as info:
        compare(**given)
    assert message in str(info.value)
