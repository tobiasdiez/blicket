from typing import Any

import polars as pl
import pytest

import blicket as bk
from blicket.plots import PlotSpec, builtin
from blicket.schema import Control, Dimension, Measure, TableSchema

# For specs that are wrong on purpose, which the type checker would reject.
spec: Any = PlotSpec


def test_factories_bind_columns_to_channels() -> None:
    spec = bk.plots.line(x="year", y="value", color="region")
    assert spec.plot_type is builtin("line")
    assert spec.mapping == {"x": "year", "y": "value", "color": "region"}
    for factory in [bk.plots.bar, bk.plots.stacked_bar, bk.plots.stacked_area]:
        assert factory(x="year", y="v").plot_type.name == factory.__name__
    mapping: Any = spec.mapping
    with pytest.raises(TypeError):
        mapping["color"] = "scenario"


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

    class Chord(bk.PlotType):
        name = "chord"
        channels = (bk.Channel("source", "dimension", required=True),)

        def controls(self, schema: Any, mapping: Any) -> list[Any]:
            return []

        def diff(self, baseline: Any, current: Any, mapping: Any, panels: Any) -> bk.Change:
            return bk.Change()

    assert PlotSpec(Chord(), {"source": "from"}).mapping == {"source": "from"}


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
