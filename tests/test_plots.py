from typing import Any

import polars as pl
import pytest

import blicket as bk
from blicket.plots import PlotSpec, builtin
from blicket.schema import Control, Dimension, Measure, TableSchema

# For specs that are wrong on purpose, which the type checker would reject.
spec: Any = PlotSpec
line: Any = bk.plots.line
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


def test_sankey_binds_flows_from_one_dimension_to_another() -> None:
    spec = bk.plots.sankey(source="From", target="To", value="value", color="Stage")
    assert spec.plot_type is builtin("sankey")
    assert spec.mapping == {"source": "From", "target": "To", "value": "value", "color": "Stage"}
    assert bk.plots.sankey("From", "To", "value").mapping == {
        "source": "From",
        "target": "To",
        "value": "value",
    }
    channels = {c.name: (c.kind, c.required) for c in builtin("sankey").channels}
    assert channels == {
        "source": ("dimension", True),
        "target": ("dimension", True),
        "value": ("measure", True),
        "color": ("dimension", False),
    }


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
        (
            lambda: PlotSpec(builtin("sankey"), {"source": "a", "target": "b"}),
            "plot type sankey needs the channel(s) value",
        ),
        (
            lambda: bk.plots.sankey(source="Process", target="Process", value="v"),
            "bound to both 'source' and 'target'",
        ),
        (
            lambda: PlotSpec(builtin("sankey"), {"source": "a", "target": "b", "y": "v"}),
            "channels of sankey: source, target, value, color",
        ),
        (lambda: spec(builtin("line"), {"x": "a", "y": 3}), "must name a column"),
        (lambda: spec("line", {}), "must be a PlotType instance"),
        (
            lambda: line(x="t", y="v", y_scale="sqrt"),
            "y_scale='sqrt' is no scale of y in plot type line; it takes 'linear' or 'log'",
        ),
        (
            lambda: line(x="t", y="v", x_scale="Log"),
            "x_scale='Log' is no scale of x in plot type line; did you mean 'log'? it takes",
        ),
        (
            lambda: PlotSpec(builtin("bar"), {"x": "t", "y": "v"}, {"y": "log"}),
            "y_scale='log': channel 'y' of plot type bar takes no scale; drop the scale",
        ),
        (
            lambda: PlotSpec(builtin("line"), {"x": "t", "y": "v", "color": "c"}, {"color": "log"}),
            "color_scale='log': channel 'color' of plot type line takes no scale",
        ),
        (
            lambda: PlotSpec(builtin("line"), {"x": "t", "y": "v"}, {"yy": "log"}),
            "plot type line has no channel 'yy'; did you mean 'y'? channels of line: x, y, color,",
        ),
        (lambda: PlotSpec(builtin("scatter"), {"y": "value"}), "needs the channel(s) x"),
        (lambda: scatter(x="gdp", y=None), "plot type scatter needs the channel(s) y"),
        (
            lambda: scatter(x="gdp", y="value", x_scale="logarithmic"),
            "x_scale='logarithmic' is no scale of x in plot type scatter",
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
            "x_scale='ln' is no scale of x in plot type scatter; it takes 'linear' or 'log'",
        ),
        (
            lambda: PlotSpec(builtin("scatter"), {"x": "a", "y": "b"}, {"color": "log"}),
            "color_scale='log': channel 'color' of plot type scatter takes no scale; drop the "
            "scale",
        ),
    ],
)
def test_plot_spec_errors(make: Any, expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        make()
    assert expected in str(info.value)


def test_line_takes_a_scale_per_axis() -> None:
    assert bk.plots.line(x="year", y="value", y_scale="log").scales == {"y": "log"}
    both = bk.plots.line(x="year", y="value", x_scale="log", y_scale="log")
    assert both.scales == {"x": "log", "y": "log"}
    # Linear, every axis's default, is left out: naming it gives the spec of no argument.
    linear = bk.plots.line(x="year", y="value", x_scale="linear", y_scale="linear")
    assert (linear, linear.scales) == (bk.plots.line(x="year", y="value"), {})
    scales: Any = both.scales
    with pytest.raises(TypeError):
        scales["x"] = "linear"


def test_plot_type_contract() -> None:
    abstract: Any = bk.PlotType
    with pytest.raises(TypeError):
        abstract()

    class Chord(bk.PlotType):
        name = "chord"
        channels = (bk.Channel("source", "dimension", required=True),)

        def controls(self, schema: Any, mapping: Any) -> list[Any]:
            return []

        def diff(self, baseline: Any, current: Any, mapping: Any, panels: Any) -> bk.Change:
            return bk.Change()

    assert PlotSpec(Chord(), {"source": "from"}).mapping == {"source": "from"}


def test_a_plot_type_declares_the_scales_of_its_channels() -> None:
    class Bubbles(bk.PlotType):
        name = "bubbles"
        channels = (
            bk.Channel("x", "measure", required=True, scales=("linear", "log")),
            bk.Channel("size", "measure", scales=("log",)),
        )

        def controls(self, schema: Any, mapping: Any) -> list[Any]:
            return []

        def diff(self, baseline: Any, current: Any, mapping: Any, panels: Any) -> bk.Change:
            return bk.Change()

    bubbles = Bubbles()
    assert PlotSpec(bubbles, {"x": "gdp", "size": "pop"}, {"size": "log"}).scales == {"size": "log"}
    # A channel with scales takes linear too, whether it lists it or not.
    linear = PlotSpec(bubbles, {"x": "gdp", "size": "pop"}, {"x": "linear", "size": "linear"})
    assert linear.scales == {}
    assert PlotSpec(bubbles, {"x": "gdp"}, {"size": "linear"}) == PlotSpec(bubbles, {"x": "gdp"})
    with pytest.raises(bk.DefinitionError, match=r"it takes 'linear' or 'log'$"):
        spec(bubbles, {"x": "gdp"}, {"x": "sqrt"})
    with pytest.raises(bk.DefinitionError) as info:
        PlotSpec(bubbles, {"x": "gdp"}, {"size": "log"})
    assert str(info.value) == (
        "size_scale='log' needs a column on size; map size to a column or drop the scale"
    )


@pytest.mark.parametrize(
    ("scales", "expected"),
    [
        (
            "log",  # ("log") without its comma
            "channel 'x': scales= takes a tuple of scale names, such as scales=('log',), not 'log'",
        ),
        (
            ("sqrt",),
            "channel 'x': scales= names 'sqrt', which is no scale; write scales=('log',); "
            "'linear' is implied",
        ),
        (
            ("linar",),
            "channel 'x': scales= names 'linar', which is no scale; write scales=('log',); "
            "'linear' is implied",
        ),
    ],
)
def test_a_channel_declares_scales_blicket_has(scales: Any, expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        bk.Channel("x", "measure", scales=scales)
    assert str(info.value) == expected


def test_a_channel_keeps_its_scales_besides_linear_once_each() -> None:
    listed: Any = ["linear", "log", "log"]  # a list, which the type checker would reject
    assert bk.Channel("x", "measure", scales=listed).scales == ("log",)
    assert bk.Channel("x", "measure", scales=("linear",)).scales == ()


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


def test_sankey_filters_every_dimension_but_its_ends_and_its_colour() -> None:
    schema = TableSchema(
        dimensions=[
            Dimension(name="Time", dtype="integer", values=[2050, 2100]),
            Dimension(name="Region", dtype="string", values=["World", "EUR"]),
            Dimension(name="From", dtype="string", values=["Production", "Use"]),
            Dimension(name="To", dtype="string", values=["Use", "Production"]),
            Dimension(name="Stage", dtype="string", values=["Use", "Recycling"]),
        ],
        measures=[Measure(name="value", dtype="float")],
    )
    mapping = {"source": "From", "target": "To", "value": "value", "color": "Stage"}
    assert builtin("sankey").controls(schema, mapping) == [
        Control(dimension="Time", kind="filter", default=2050),
        Control(dimension="Region", kind="filter", default="World"),
    ]


# A loop of three flows in two years, the second a tenth of the first.
FLOWS = pl.DataFrame(
    {
        "Time": [2050] * 3 + [2100] * 3,
        "From": ["Production", "Use", "Recycling"] * 2,
        "To": ["Use", "Recycling", "Production"] * 2,
        "Stage": ["Use", "End of life", "Recycling"] * 2,
        "value": [100.0, 40, 20, 10, 4, 2],
    }
)
SANKEY = {"source": "From", "target": "To", "value": "value"}


def test_sankey_diff_compares_each_flow_against_the_largest_of_its_panel() -> None:
    # Recycling in 2100 grows from 2 to 3: a tenth of the largest flow that year, 10.
    current = FLOWS.with_columns(value=pl.Series([100.0, 40, 20, 10, 4, 3]))
    sankey = builtin("sankey")
    per_year = sankey.diff(FLOWS, current, SANKEY, ["Time"])
    assert per_year.magnitude == pytest.approx(0.1)
    assert per_year.where == {
        "Time": 2100,
        "From": "Recycling",
        "To": "Production",
        "Stage": "Recycling",
    }
    # Without panels the largest flow of both years sets the scale; the colour stacks nothing.
    assert sankey.diff(FLOWS, current, SANKEY, []).magnitude == pytest.approx(0.01)
    with_color = sankey.diff(FLOWS, current, {**SANKEY, "color": "Stage"}, ["Time"])
    assert with_color.magnitude == pytest.approx(0.1)
    unchanged = sankey.diff(FLOWS, FLOWS, SANKEY, ["Time"])
    assert (unchanged.magnitude, unchanged.where) == (0.0, None)


def test_sankey_diff_needs_a_measure_on_value() -> None:
    with pytest.raises(ValueError, match="binds no column to value, which sankey needs"):
        builtin("sankey").diff(FLOWS, FLOWS, {"source": "From", "target": "To"}, [])
