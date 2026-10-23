from typing import Any

import pytest

import blicket as bk
from blicket.plots import PlotSpec, builtin

# For specs that are wrong on purpose, which the type checker would reject.
spec: Any = PlotSpec


def test_factories_bind_columns_to_channels() -> None:
    spec = bk.plots.line(x="year", y="value", color="region")
    assert spec.plot_type is builtin("line")
    assert spec.to_json() == {
        "type": "line",
        "mapping": {"x": "year", "y": "value", "color": "region"},
    }
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
    with pytest.raises(NotImplementedError, match="do not implement controls"):
        builtin("line").controls(None, {})
    with pytest.raises(NotImplementedError, match="do not implement diff"):
        builtin("line").diff(None, None, {}, [])

    class Sankey(bk.PlotType):
        name = "sankey"
        channels = (bk.Channel("source", "dimension", required=True),)

        def controls(self, schema: Any, mapping: Any) -> list[Any]:
            return []

        def diff(self, baseline: Any, current: Any, mapping: Any, controls: Any) -> Any:
            return None

    assert PlotSpec(Sankey(), {"source": "from"}).to_json()["type"] == "sankey"
