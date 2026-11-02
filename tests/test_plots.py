from typing import Any

import polars as pl
import pytest

import blicket as bk
from blicket.plots import PlotSpec, builtin
from blicket.schema import Control, Dimension, Measure, TableSchema

# For specs that are wrong on purpose, which the type checker would reject.
spec: Any = PlotSpec
scatter: Any = bk.plots.scatter


def test_factories_bind_columns_to_channels() -> None:
    spec = bk.plots.line(x="year", y="value", color="region")
    assert spec.plot_type is builtin("line")
    assert spec.mapping == {"x": "year", "y": "value", "color": "region"}
    for factory in [bk.plots.bar, bk.plots.stacked_bar, bk.plots.stacked_area]:
        assert factory(x="year", y="v").plot_type.name == factory.__name__
    mapping: Any = spec.mapping
    with pytest.raises(TypeError):
        mapping["color"] = "scenario"


def test_scatter_binds_two_measures_and_records_its_scales() -> None:
    spec = bk.plots.scatter(
        x="GDP per capita", y="value", color="Region", along="Time", x_scale="log"
    )
    assert spec.plot_type is builtin("scatter")
    assert spec.mapping == {"x": "GDP per capita", "y": "value", "color": "Region", "along": "Time"}
    assert spec.scales == {"x": "log"}
    kinds = {channel.name: channel.kind for channel in spec.plot_type.channels}
    assert kinds == {
        "x": "measure",
        "y": "measure",
        "color": "dimension",
        "linetype": "dimension",
        "along": "dimension",
    }
    # Linear, every axis's default, is left out: naming it gives the spec of no argument.
    linear = bk.plots.scatter(x="a", y="b", x_scale="linear", y_scale=None)
    assert (linear, linear.scales) == (bk.plots.scatter(x="a", y="b"), {})
    assert bk.plots.line(x="year", y="value").scales == {}
    scales: Any = spec.scales
    with pytest.raises(TypeError):
        scales["y"] = "log"


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (
            lambda: PlotSpec(builtin("line"), {"x": "a", "y": "b", "colour": "c"}),
            "did you mean 'color'?",
        ),
        (lambda: PlotSpec(builtin("line"), {"x": "a", "y": "b", "size": "c"}), "channels of line:"),
        (lambda: PlotSpec(builtin("stacked_area"), {"x": "year"}), "needs the channel(s) y"),
        (lambda: bk.plots.line(x="year", y="value", color="year"), "bound to both 'x' and 'color'"),
        (lambda: builtin("pie"), "no built-in plot type 'pie'"),
        (lambda: spec(builtin("line"), {"x": "a", "y": 3}), "must name a column"),
        (lambda: spec("line", {}), "must be a PlotType instance"),
        (lambda: PlotSpec(builtin("scatter"), {"y": "value"}), "needs the channel(s) x"),
        (lambda: scatter(x="gdp", y=None), "plot type scatter needs the channel(s) y"),
        (
            lambda: scatter(x="gdp", y="value", x_scale="logarithmic"),
            "x_scale='logarithmic' is no scale of x in plot type scatter; it takes linear or log",
        ),
        (lambda: scatter(x="gdp", y="value", y_scale=10), "y_scale=10 is no scale of y in plot"),
        (
            lambda: bk.plots.scatter(x="gdp", y="value", along="gdp"),
            "column 'gdp' is bound to both 'x' and 'along' in plot type scatter",
        ),
        (
            lambda: PlotSpec(builtin("scatter"), {"x": "a", "y": "b", "alongside": "t"}),
            "did you mean 'along'?",
        ),
        (
            lambda: PlotSpec(builtin("scatter"), {"x": "a", "y": "b"}, {"z": "log"}),
            "plot type scatter has no channel 'z'",
        ),
        (
            lambda: spec(builtin("scatter"), {"x": "a", "y": "b"}, {"x": "ln"}),
            "x_scale='ln' is no scale of x in plot type scatter; it takes linear or log",
        ),
        (
            lambda: PlotSpec(builtin("scatter"), {"x": "a", "y": "b"}, {"color": "log"}),
            "channel 'color' of plot type scatter has a scale but no column; map it to a column "
            "or drop the scale",
        ),
    ],
)
def test_plot_spec_errors(make: Any, expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        make()
    assert expected in str(info.value)


def test_plot_type_contract() -> None:
    abstract: Any = bk.PlotType
    with pytest.raises(TypeError):
        abstract()

    class Sankey(bk.PlotType):
        name = "sankey"
        channels = (bk.Channel("source", "dimension", required=True),)

        def controls(self, schema: Any, mapping: Any) -> list[Any]:
            return []

        def diff(self, baseline: Any, current: Any, mapping: Any, panels: Any) -> bk.Change:
            return bk.Change()

    assert PlotSpec(Sankey(), {"source": "from"}).mapping == {"source": "from"}


def test_builtin_controls_filter_every_unbound_dimension() -> None:
    schema = TableSchema(
        dimensions=[
            Dimension(name="year", dtype="integer", values=[2020, 2021]),
            Dimension(name="region", dtype="string", values=["USA", "EUR"]),
            Dimension(name="empty", dtype="string", values=[]),
        ],
        measures=[Measure(name="value", dtype="float")],
    )
    for name in ("line", "stacked_area", "bar", "stacked_bar"):
        assert builtin(name).controls(schema, {"x": "year", "y": "value"}) == [
            Control(dimension="region", kind="filter", default="USA"),
            Control(dimension="empty", kind="filter", default=None),
        ]
    # The dimension along which a scatter connects its points is bound, so it has no filter.
    along = {"x": "gdp", "y": "value", "along": "year"}
    assert builtin("scatter").controls(schema, along) == [
        Control(dimension="region", kind="filter", default="USA"),
        Control(dimension="empty", kind="filter", default=None),
    ]


def test_builtin_diff_compares_the_stacks_of_the_stacked_types() -> None:
    # A large layer and two small ones that grow by 1 each: the stack grows by 2 to 14.
    baseline = pl.DataFrame({"year": [2020] * 3, "kind": ["a", "b", "c"], "value": [10.0, 1, 1]})
    current = baseline.with_columns(value=pl.Series([10.0, 2, 2]))
    mapping = {"x": "year", "y": "value", "color": "kind"}
    magnitudes = {
        name: builtin(name).diff(baseline, current, mapping, []).magnitude
        for name in ("line", "bar", "stacked_area", "stacked_bar")
    }
    stacked = pytest.approx(2 / 14)
    assert magnitudes == {"line": 0.1, "bar": 0.1, "stacked_area": stacked, "stacked_bar": stacked}


def test_a_stacked_type_without_a_colour_compares_rows_only() -> None:
    baseline = pl.DataFrame({"year": [2020] * 3, "kind": ["a", "b", "c"], "value": [10.0, 1, 1]})
    current = baseline.with_columns(value=pl.Series([10.0, 2, 2]))
    unstacked = builtin("stacked_area").diff(baseline, current, {"x": "year", "y": "value"}, [])
    assert unstacked.magnitude == 0.1


def test_builtin_diff_needs_a_measure_on_y() -> None:
    table = pl.DataFrame({"year": [2020], "value": [1.0]})
    with pytest.raises(ValueError, match="the mapping binds no column to y, which line needs"):
        builtin("line").diff(table, table, {"x": "year"}, [])


def scattered(gdp: list[float | None], value: list[float]) -> pl.DataFrame:
    """A scatter's table: two years of one region, GDP per capita on x, the value on y."""
    return pl.DataFrame(
        {"year": [2020, 2021], "region": ["EUR"] * 2, "gdp": gdp, "value": value},
        schema_overrides={"gdp": pl.Float64},
    )


SCATTERED = {"x": "gdp", "y": "value", "color": "region", "along": "year"}


def test_scatter_diff_compares_y_and_not_x() -> None:
    baseline = scattered([1e4, 2e4], [1.0, 2.0])
    plot_type = builtin("scatter")
    # x moves, y does not: unchanged; the rows are matched by their dimensions, not by x.
    moved = scattered([1.5e4, None], [1.0, 2.0])
    assert plot_type.diff(baseline, moved, SCATTERED, []) == bk.Change(magnitude=0.0)
    changed = scattered([1e4, 2e4], [1.0, 1.5])
    change = plot_type.diff(baseline, changed, SCATTERED, [])
    assert (change.flags, change.magnitude, change.where) == (
        frozenset(),
        0.25,
        {"year": 2021, "region": "EUR"},
    )


def test_a_vanished_x_column_is_a_schema_change() -> None:
    baseline = scattered([1e4, 2e4], [1.0, 2.0])
    current = baseline.rename({"gdp": "GDP"})
    mapping = {**SCATTERED, "x": "GDP"}
    assert builtin("scatter").diff(baseline, current, mapping, []) == bk.Change(
        flags=frozenset({"schema"}),
        columns_added={"GDP": "float"},
        columns_removed={"gdp": "float"},
    )
