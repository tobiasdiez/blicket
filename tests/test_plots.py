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
