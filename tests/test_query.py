"""The dataset protocol and the builder's query: what the dataset is asked, the table and the entry
that come back, and the problems a query can have."""

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError

import blicket as bk
from blicket import query
from blicket.dataset import Contents, check, coerce, find
from blicket.errors import DatasetError
from blicket.query import Query, run_query
from tests.support import make_project

HERE = Path(__file__).parent
YEARS = [2020, 2021, 2022]
REGIONS = ["north", "south", "east"]  # the display order, which is not the sorted one
PROCESSES = ["BOF", "EAF"]
DIMENSIONS = (
    bk.Dimension(name="year", dtype="integer", values=YEARS),
    bk.Dimension(name="region", dtype="string", values=REGIONS),
    bk.Dimension(name="process", dtype="string", values=PROCESSES),
)
QUANTITIES = (
    bk.Quantity(
        name="flows/steel", unit="t", dimensions=("year", "region", "process"), group="flows"
    ),
    bk.Quantity(name="flows/scrap", dimensions=("year", "region", "process"), group="flows"),
    bk.Quantity(name="shares/eaf", dimensions=("year", "region"), additive=False, group="shares"),
)


def _steel() -> pl.DataFrame:
    combinations = [(y, r, p) for y in YEARS for r in REGIONS for p in PROCESSES]
    rows = [(*combination, float(i)) for i, combination in enumerate(combinations)]
    return pl.DataFrame(rows, schema=["year", "region", "process", "value"], orient="row")


def _frames() -> dict[str, pl.DataFrame]:
    steel = _steel()
    return {
        "flows/steel": steel,
        "flows/scrap": steel.with_columns(pl.col("value") * 10),
        "shares/eaf": steel.filter(pl.col("process") == "EAF").drop("process"),
    }


class Toy:
    """A dataset of two additive quantities and an intensive one over polars frames, which
    records what it was asked. ``careless`` ignores ``values``; ``raises`` makes ``select``
    raise; ``returns`` is returned instead of a quantity's table."""

    def __init__(
        self,
        quantities: Sequence[bk.Quantity] = QUANTITIES,
        dimensions: Sequence[bk.Dimension] = DIMENSIONS,
        frames: Mapping[str, pl.DataFrame] | None = None,
        *,
        careless: bool = False,
        raises: bool = False,
        returns: pl.DataFrame | None = None,
    ) -> None:
        self.calls: list[tuple[str, list[str], dict[str, list[Any]]]] = []
        self._quantities = quantities
        self._dimensions = dimensions
        self.frames = frames if frames is not None else _frames()
        self.careless = careless
        self.raises = raises
        self.returns = returns

    def quantities(self) -> Sequence[bk.Quantity]:
        return self._quantities

    def dimensions(self) -> Sequence[bk.Dimension]:
        return self._dimensions

    def select(
        self, quantity: str, keep: Sequence[str], values: Mapping[str, Sequence[Any]]
    ) -> Any:
        self.calls.append((quantity, list(keep), {k: list(v) for k, v in values.items()}))
        if self.raises:
            raise RuntimeError("the model has no such array")
        if self.returns is not None:
            return self.returns
        frame = self.frames[quantity]
        if not self.careless:
            for name, wanted in values.items():
                frame = frame.filter(pl.col(name).is_in(list(wanted)))
        if not keep:
            return frame.select(pl.col("value").sum())
        return frame.group_by(keep).agg(pl.col("value").sum())


def contents(toy: Toy) -> Contents:
    return check(toy, HERE)


def ask(toy: Toy, **fields: Any) -> query.Result:
    fields.setdefault("plot", "line")
    fields.setdefault("mapping", {"x": "year"})
    return run_query(contents(toy), Query(**fields), HERE)


def problem(result: query.Result) -> str:
    (found,) = result.entry.problems
    assert (result.entry.status, result.table, result.entry.data) == ("error", None, None)
    return found.message


def table(result: query.Result) -> pl.DataFrame:
    assert result.table is not None, result.entry.problems
    return pl.read_parquet(result.table)


def test_the_dataset_sums_what_is_not_kept_and_filters_by_the_values() -> None:
    toy = Toy()
    result = ask(
        toy, quantities=["flows/steel"], keep=["region"], values={"region": ["south", "north"]}
    )
    assert toy.calls == [("flows/steel", ["year", "region"], {"region": ["south", "north"]})]
    frame = table(result)
    assert frame.columns == ["year", "region", "value"]
    # summed over process: rows 2i and 2i+1 of the steel table
    assert frame.filter(year=2020, region="north")["value"].to_list() == [0.0 + 1.0]
    assert sorted(frame["region"].unique()) == ["north", "south"]


def test_blicket_filters_the_kept_dimensions_once_more() -> None:
    toy = Toy(careless=True)
    frame = table(
        ask(toy, quantities=["flows/steel"], keep=["region"], values={"region": ["east"]})
    )
    assert frame["region"].unique().to_list() == ["east"]


def test_values_are_coerced_to_the_dimension_type() -> None:
    toy = Toy()
    frame = table(ask(toy, quantities=["flows/steel"], values={"year": ["2021", 2022]}))
    assert toy.calls[0][2] == {"year": [2021, 2022]}
    assert frame["year"].to_list() == [2021, 2022]
    assert "not an integer" in problem(
        ask(toy, quantities=["flows/steel"], values={"year": ["soon"]})
    )


@pytest.mark.parametrize(
    ("value", "dtype", "expected"),
    [
        ("true", "boolean", True),
        ("false", "boolean", False),
        (True, "boolean", True),
        ("-3", "integer", -3),
        ("2020-01-02", "date", date(2020, 1, 2)),
        (date(2020, 1, 2), "date", date(2020, 1, 2)),
        ("2020-01-02T03:04:05", "datetime", datetime(2020, 1, 2, 3, 4, 5)),
        ("2020-01-02T03:04:05Z", "datetime", datetime(2020, 1, 2, 3, 4, 5)),
        ("2020-01-02T05:04:05+02:00", "datetime", datetime(2020, 1, 2, 3, 4, 5)),
        ("EAF", "string", "EAF"),
    ],
)
def test_coerce(value: Any, dtype: Any, expected: Any) -> None:
    assert coerce(value, dtype) == expected


@pytest.mark.parametrize(
    ("value", "dtype"),
    [("yes", "boolean"), (True, "integer"), ("1.5", "integer"), (3, "string"), (1, "date")],
)
def test_coerce_refuses_other_values(value: Any, dtype: Any) -> None:
    with pytest.raises(ValueError, match="is not a"):
        coerce(value, dtype)


def test_dates_datetimes_and_booleans_are_dimensions_too() -> None:
    days = [date(2020, 1, 1), date(2020, 1, 2)]
    moments = [datetime(2020, 1, 1, 12), datetime(2020, 1, 1, 18)]
    rows = [(d, m, f, 1.0) for d in days for m in moments for f in (True, False)]
    frame = pl.DataFrame(rows, schema=["day", "moment", "fresh", "value"], orient="row")
    toy = Toy(
        [bk.Quantity(name="readings", dimensions=("day", "moment", "fresh"))],
        [
            bk.Dimension(name="day", dtype="date", values=["2020-01-01", "2020-01-02"]),
            bk.Dimension(name="moment", dtype="datetime", values=moments),
            bk.Dimension(name="fresh", dtype="boolean", values=[True, False]),
        ],
        {"readings": frame},
    )
    result = ask(
        toy,
        quantities=["readings"],
        mapping={"x": "day", "color": "fresh"},
        keep=["moment"],
        values={"day": ["2020-01-02"], "moment": ["2020-01-01T18:00:00Z"], "fresh": ["true"]},
    )
    assert toy.calls[0][2] == {"day": [days[1]], "moment": [moments[1]], "fresh": [True]}
    assert table(result).rows() == [(days[1], moments[1], True, 1.0)]  # in the dataset's order
    columns = result.entry.columns
    assert columns is not None
    assert [(d.name, d.dtype) for d in columns.dimensions] == [
        ("day", "date"),
        ("moment", "datetime"),
        ("fresh", "boolean"),
    ]


def test_the_order_of_values_follows_the_dataset() -> None:
    result = ask(
        Toy(),
        quantities=["flows/steel"],
        mapping={"x": "year", "color": "region"},
        values={"region": ["east", "north"]},
    )
    columns = result.entry.columns
    assert columns is not None
    assert [d.values for d in columns.dimensions] == [YEARS, ["north", "east"]]
    assert result.entry.problems == ()  # the values left out are not reported missing


def test_the_controls_are_filters_for_the_kept_unbound_dimensions() -> None:
    result = ask(Toy(), quantities=["flows/steel"], keep=["process", "region"])
    assert [(c.dimension, c.kind, c.default) for c in result.entry.controls] == [
        ("region", "filter", "north"),
        ("process", "filter", "BOF"),
    ]
    definition = result.entry.definition
    assert definition is not None
    assert (definition.title, definition.unit, definition.plot.mapping) == (
        "steel",
        "t",
        {"x": "year", "y": "value"},
    )
    assert (result.entry.id, result.entry.group) == ("builder/query", "builder")


def test_the_table_is_named_by_the_hash_of_its_parquet_bytes() -> None:
    result = ask(Toy(), quantities=["flows/steel"])
    digest = hashlib.sha256(result.table or b"").hexdigest()
    assert result.entry.hash == f"parquet-sha256:{digest}"
    assert (result.entry.data, result.entry.rows) == (f"dev/tables/{digest}.parquet", 3)


def test_an_intensive_quantity_is_never_summed() -> None:
    toy = Toy()
    assert problem(ask(toy, quantities=["shares/eaf"])) == (
        "eaf is not additive, so it cannot be summed over region; keep it as a filter or on a "
        "channel"
    )
    assert toy.calls == []
    frame = table(ask(toy, quantities=["shares/eaf"], keep=["region"]))
    assert frame.height == 9


def test_several_quantities_make_a_quantity_dimension() -> None:
    toy = Toy()
    both = ["flows/scrap", "flows/steel"]
    result = ask(toy, quantities=both, mapping={"x": "year", "color": "Quantity"})
    frame = table(result)
    assert frame.columns == ["Quantity", "year", "value"]
    columns = result.entry.columns
    assert columns is not None
    assert columns.dimensions[0].values == ["scrap", "steel"]  # in the order picked
    definition = result.entry.definition
    assert definition is not None
    assert (definition.title, definition.unit) == ("scrap, steel", "t")  # the one unit known
    assert [call[:2] for call in toy.calls] == [
        ("flows/scrap", ["year"]),
        ("flows/steel", ["year"]),
    ]
    summed = table(ask(Toy(), quantities=both, keep=["region"]))
    assert summed.columns == ["year", "region", "value"]
    steel = table(ask(Toy(), quantities=["flows/steel"], keep=["region"]))
    assert summed.sort("year", "region")["value"].to_list() == [
        11 * value for value in steel.sort("year", "region")["value"].to_list()
    ]
    only = ask(Toy(), quantities=both, keep=["Quantity"], values={"Quantity": ["steel"]})
    assert table(only)["Quantity"].unique().to_list() == ["steel"]


@pytest.mark.parametrize(
    ("quantities", "fields", "message"),
    [
        (
            ["flows/steel", "shares/eaf"],
            {"mapping": {"x": "year", "color": "process"}},
            "process is on the colour channel, but eaf has no dimension process",
        ),
        (
            ["flows/steel", "shares/eaf"],
            {"keep": ["region"]},
            "Quantity is summed, but eaf is not additive; keep Quantity as a filter, on panels or "
            "on a channel",
        ),
        (
            ["flows/steel", "shares/eaf"],
            {"keep": ["process"]},
            "process is a filter or on panels, but eaf has no dimension process",
        ),
        (["flows/steel", "nope"], {}, "the dataset has no quantity 'nope'"),
        (
            ["flows/steel"],
            {"plot": "pie"},
            "no plot type 'pie' in the builder; it offers line, stacked_area, bar, stacked_bar",
        ),
        (
            ["flows/steel"],
            {"mapping": {"color": "year"}},
            "the x channel needs a dimension; give one the role x",
        ),
        (
            ["flows/steel"],
            {"mapping": {"x": "year", "y": "region"}},
            "plot type line has no dimension channel 'y'; its dimension channels are x, color, "
            "linetype",
        ),
        (["flows/steel"], {"keep": ["scenario"]}, "the dataset has no dimension 'scenario'"),
        (
            ["flows/steel"],
            {"values": {"scenario": ["a"]}},
            "values are given for 'scenario', which is no dimension here",
        ),
        (
            ["flows/steel"],
            {"mapping": {"x": "year", "color": "year"}},
            "column 'year' is bound to both 'x' and 'color' in plot type line; bind each column "
            "to one channel",
        ),
    ],
)
def test_queries_that_cannot_be_made_into_a_blick(
    quantities: list[str], fields: dict[str, Any], message: str
) -> None:
    result = ask(Toy(), quantities=quantities, **fields)
    assert problem(result) == message
    assert (result.entry.definition, result.entry.problems[0].kind) == (None, "query")


def test_several_quantities_need_one_unit_and_distinct_titles() -> None:
    def quantity(name: str, **fields: Any) -> bk.Quantity:
        return bk.Quantity(name=name, dimensions=("year", "region", "process"), **fields)

    units = Toy([quantity("flows/steel", unit="t"), quantity("flows/scrap", unit="Mt")])
    assert problem(ask(units, quantities=["flows/steel", "flows/scrap"])) == (
        "the quantities have different units (t, Mt); pick quantities of one unit"
    )
    titles = Toy([quantity("flows/steel", title="steel"), quantity("flows/scrap", title="steel")])
    assert "several quantities have the title 'steel'" in problem(
        ask(titles, quantities=["flows/steel", "flows/scrap"])
    )


def test_a_dimension_called_quantity_allows_one_quantity_only() -> None:
    toy = Toy(dimensions=[*DIMENSIONS, bk.Dimension(name="Quantity", dtype="string", values=[])])
    assert problem(ask(toy, quantities=["flows/steel", "flows/scrap"])).startswith(
        "the dataset has a dimension called Quantity, so several quantities cannot be told apart"
    )


def test_a_table_over_the_row_cap_is_a_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query, "MAX_ROWS", 5)
    message = problem(ask(Toy(), quantities=["flows/steel"], keep=["region"]))
    assert message == (
        "the table has 9 rows, more than the 5 the builder draws (year 3 \N{MULTIPLICATION SIGN} "
        "region 3); sum a dimension or keep fewer of its values"
    )


def test_the_row_cap_of_an_intensive_quantity_suggests_no_sum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query, "MAX_ROWS", 5)
    assert problem(ask(Toy(), quantities=["shares/eaf"], keep=["region"])).endswith(
        "; keep fewer values of a dimension with its Values list"
    )


def test_a_select_that_raises_is_a_problem_with_the_traceback() -> None:
    result = ask(Toy(raises=True), quantities=["flows/steel"])
    (found,) = result.entry.problems
    assert found.message.startswith(
        "select('flows/steel') of the dataset raised RuntimeError: the model has no such array "
        "(raised at test_query.py:"
    )
    assert found.traceback is not None
    assert 'test_query.py", line' in found.traceback
    assert "blicket/query.py" not in found.traceback
    assert result.table is None


def test_a_select_returning_other_columns_is_a_problem() -> None:
    toy = Toy(returns=pl.DataFrame({"year": [2020], "other": [1.0], "value": [1.0]}))
    assert problem(ask(toy, quantities=["flows/steel"])) == (
        "select('flows/steel', ...) returned the columns year, other, value; a dataset returns "
        "the dimensions kept (year) and one measure column"
    )


def test_the_options_list_the_plot_types_of_one_measure() -> None:
    options = query.Options.of(contents(Toy()))
    assert [p.name for p in options.plots] == ["line", "stacked_area", "bar", "stacked_bar"]
    dumped = options.model_dump(mode="json")
    assert dumped["plots"][0]["channels"][0] == {
        "name": "x",
        "kind": "dimension",
        "required": True,
        "doc": "Horizontal axis, usually time.",
    }
    assert dumped["quantities"][0]["title"] == "steel"


def test_a_select_returning_values_of_another_type_names_the_column() -> None:
    toy = Toy(returns=pl.DataFrame({"year": ["soon"], "value": [1.0]}))
    message = problem(ask(toy, quantities=["flows/steel"]))
    assert message.startswith(
        "select('flows/steel') returned a 'year' column that cannot be read as integers: "
    )
    toy = Toy(returns=pl.DataFrame({"year": [2020], "value": ["much"]}))
    assert "a 'value' column that cannot be read as numbers" in problem(
        ask(toy, quantities=["flows/steel"])
    )


def test_quantities_summed_over_different_dimensions_share_a_chart() -> None:
    imports = bk.Quantity(name="flows/imports", unit="t", dimensions=("year", "region"))
    frames = {**_frames(), "flows/imports": _frames()["shares/eaf"]}
    toy = Toy([*QUANTITIES, imports], frames=frames)
    result = ask(
        toy, quantities=["flows/steel", "flows/imports"], mapping={"x": "year", "color": "Quantity"}
    )
    assert [call[:2] for call in toy.calls] == [
        ("flows/steel", ["year"]),
        ("flows/imports", ["year"]),
    ]
    assert table(result).height == 6


def test_a_query_with_unknown_fields_is_not_a_query() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Query.model_validate({"quantities": ["flows/steel"], "plot": "line", "split": ["region"]})


def test_a_dimension_called_value_is_not_kept() -> None:
    toy = Toy(
        [bk.Quantity(name="odd", dimensions=("year", "value"))],
        [*DIMENSIONS, bk.Dimension(name="value", dtype="string", values=["a"])],
    )
    assert problem(ask(toy, quantities=["odd"], keep=["value"])) == (
        "a dimension called 'value' cannot be kept: it is the measure"
    )


# ---------------------------------------------------------------------------------------------
# Finding the dataset

LOAD = """
import blicket as bk


def load_run(selection):
    return {}, bk.RunInfo(id="r", fingerprint="f")
"""

PROTOCOL = """

class Data:
    def quantities(self):
        return QUANTITIES

    def dimensions(self):
        return DIMENSIONS

    def select(self, quantity, keep, values):
        return None


QUANTITIES = [bk.Quantity(name="flows/a", dimensions=["year"], group="flows")]
DIMENSIONS = [bk.Dimension(name="year", dtype="integer", values=["2020", 2021])]


def dataset(run):
    return Data()
"""


def find_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str], target: str):
    root = make_project(tmp_path, files)
    monkeypatch.syspath_prepend(str(root))
    return find(target, {}, root)


def test_dataset_in_blicketconf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = {"blicketconf.py": LOAD + PROTOCOL}
    found = find_in(tmp_path, monkeypatch, files, "blicketconf:load_run").contents
    assert found is not None
    assert list(found.quantities) == ["flows/a"]
    assert found.quantities["flows/a"].title == "a"
    assert found.dimensions["year"].values == [2020, 2021]  # coerced


def test_dataset_in_the_module_the_loader_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"model/__init__.py": "", "model/adapter.py": LOAD + PROTOCOL}
    assert find_in(tmp_path, monkeypatch, files, "model.adapter:load_run").contents is not None


def test_no_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    found = find_in(tmp_path, monkeypatch, {"blicketconf.py": LOAD}, "blicketconf:load_run")
    assert (found.contents, found.error) == (None, None)
    assert found.reason == (
        "no dataset(run) next to load_run in blicketconf.py; add one that returns the quantities "
        'and dimensions of a run (see "The Blick builder" in the README)'
    )


def test_no_dataset_in_the_module_the_loader_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"model/__init__.py": "", "model/adapter.py": LOAD}
    reason = find_in(tmp_path, monkeypatch, files, "model.adapter:load_run").reason
    assert reason is not None
    assert reason.startswith("no dataset(run) next to load_run in model.adapter; add one")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            ("return Data()", "raise RuntimeError('no')"),
            "dataset(run) in blicketconf raised RuntimeError: no (raised at blicketconf.py:",
        ),
        (
            ("def dataset(run):\n    return Data()", "dataset = 1"),
            "dataset in blicketconf is not a function",
        ),
        (
            ("    def select(", "    def choose("),
            "dataset(run) in blicketconf returned a Data, which has no select(); a dataset has "
            "quantities(), dimensions() and select(quantity, keep, values)",
        ),
        (
            ('dimensions=["year"]', 'dimensions=["year", "region"]'),
            "dataset(run) in blicketconf: quantity 'flows/a' has the dimension(s) region, which "
            "dimensions() lacks",
        ),
        (
            ('dimensions=["year"]', 'dimensions=["year", "year"]'),
            "dataset(run) in blicketconf: quantity 'flows/a' names a dimension twice",
        ),
        (
            ('group="flows")]', 'group="flows")] * 2'),
            "dataset(run) in blicketconf: quantities() names 'flows/a' twice",
        ),
        (
            ('values=["2020", 2021])]', 'values=["2020", 2021])] * 2'),
            "dataset(run) in blicketconf: dimensions() names 'year' twice",
        ),
        (
            ('values=["2020", 2021]', 'values=["2020", "soon"]'),
            "dataset(run) in blicketconf: dimension 'year': 'soon' is not an integer",
        ),
        (
            ('bk.Quantity(name="flows/a"', 'dict(name=""'),
            "dataset(run) in blicketconf: a Quantity is invalid: name: String should have at "
            "least 1 character",
        ),
        (
            ("        return QUANTITIES", "        return 1 / 0"),
            "quantities() of the dataset of dataset(run) in blicketconf raised ZeroDivisionError",
        ),
        (
            ("        return DIMENSIONS", "        raise KeyError('Time')"),
            "dimensions() of the dataset of dataset(run) in blicketconf raised KeyError: 'Time'",
        ),
    ],
)
def test_a_dataset_that_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: tuple[str, str], message: str
) -> None:
    source = (LOAD + PROTOCOL).replace(*change)
    assert source != LOAD + PROTOCOL
    found = find_in(tmp_path, monkeypatch, {"blicketconf.py": source}, "blicketconf:load_run")
    assert found.contents is None
    assert isinstance(found.error, DatasetError)
    assert found.reason == str(found.error)
    assert found.reason.startswith(message)
