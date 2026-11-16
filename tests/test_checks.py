"""Checks and expectations as a project defines and builds them: ``@bk.check``,
``bk.register_check``, ``expect=`` and ``level=``, the check's table rules, the outcomes a build
records in its manifest, and the store's copies of the checks' tables."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd
import polars as pl
import pytest

import blicket as bk
from blicket import definitions, manifest, report, tables
from blicket._validation import CheckOptions
from blicket.assembly import assemble
from blicket.builder import NothingToBuild
from blicket.model import CheckDefinition
from blicket.store import Store
from tests.support import make_build_project, make_project, make_run

# ---------------------------------------------------------------------------------------------
# Definitions, used directly from this module, outside discovery


def assembled() -> bk.Registry:
    """The registry made of what this module defined."""
    record = definitions.module_record(__name__)
    assert record is not None, "nothing was recorded for this module"
    return assemble([record])


def test_a_bare_check_takes_its_id_title_description_and_no_rows() -> None:
    @bk.check
    def stock_balance(run: Any) -> Any:
        """The stock's change equals inflow minus outflow."""
        return run

    assert stock_balance(1) == 1
    group = __name__.rpartition(".")[2]
    check = assembled().checks[f"{group}/stock_balance"]
    assert (check.title, check.description) == (
        "Stock balance",
        "The stock's change equals inflow minus outflow.",
    )
    assert check.definition().expect == bk.expect.no_rows().record()
    assert check.entry().definition == check.definition()


def test_a_check_with_options() -> None:
    expectation = bk.expect.no_rows(by="relative", warn_within=1e-9)

    @bk.check(
        id="checks/flows",
        title="Flows are not negative",
        tags=["mfa"],
        aliases=["checks/negative_flows"],
        expect=expectation,
        level="warn",
        dims=["Flow"],
        measures=["relative"],
    )
    def flows(run: Any) -> Any:
        return run

    check = assembled().checks["checks/flows"]
    assert (check.expect, check.level, check.tags, check.aliases) == (
        expectation,
        "warn",
        ("mfa",),
        ("checks/negative_flows",),
    )
    assert check.definition().model_dump() == {
        "title": "Flows are not negative",
        "description": None,
        "tags": ("mfa",),
        "level": "warn",
        "expect": {"kind": "no_rows", "rows": None, "by": "relative", "warn_within": 1e-9},
        "dims": ("Flow",),
        "measures": ("relative",),
    }


def test_the_options_of_a_check_are_its_definition_fields_plus_the_identity() -> None:
    identity = {"id", "aliases"}
    assert CheckOptions.__optional_keys__ == CheckDefinition.model_fields.keys() | identity


def test_register_check_in_a_loop() -> None:
    def balance(run: Any, model: str) -> Any:
        return [model]

    for model in ("plastics", "steel"):
        bk.register_check(
            id=f"balance/{model}",
            title=f"Mass balance of {model}",
            transform=lambda r, m=model: balance(r, m),
        )
    checks = assembled().checks
    assert list(checks) == ["balance/plastics", "balance/steel"]
    assert checks["balance/steel"].transform(None) == ["steel"]
    assert checks["balance/plastics"].title == "Mass balance of plastics"


def identity(run: Any) -> Any:
    return run


class Mine(bk.expect._vocabulary.NoRows):
    """An expectation of its own, which blicket cannot evaluate."""


# For calls that are wrong on purpose, which the type checker would reject.
check: Any = bk.check
register_check: Any = bk.register_check
register: Any = bk.register
group: Any = bk.group


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda: register_check(transform=identity), "pass id=; there is no function name"),
        (lambda: register_check(id="checks/x"), "transform= is missing"),
        (
            lambda: register_check(
                id="checks/x", transform=identity, plot=bk.plots.line(x="a", y="b")
            ),
            "plot= is an option of Blicks, which a check does not take: a check has no chart, and "
            "its table is not compared; the options of a check are id, title, description, tags, "
            "aliases, expect, level, dims, measures",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, unit="t"),
            "unit= is an option of Blicks, which a check does not take: a check has no chart",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expct=1),
            "did you mean expect=?",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=bk.expect),
            "expect must be an expectation made by bk.expect.no_rows(), at_most(), at_least() or "
            "between(), got <module",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=bk.expect.at_least),
            "bk.expect.at_least is not called: call it, bk.expect.at_least(...)",
        ),
        (
            lambda: register_check(
                id="checks/x", transform=identity, expect=[bk.expect.no_rows(), bk.expect.no_rows()]
            ),
            "a Blick or check takes one expectation, got [bk.expect.no_rows(), "
            "bk.expect.no_rows()]",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=identity),
            "a function that picks the offending rows goes into one: bk.expect.no_rows(identity)",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=bk.Expectation()),
            "got Expectation(), which bk.expect does not make",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=Mine(by="value")),
            "got Mine(by='value'), which bk.expect does not make",
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, expect=bk.Expectation),
            "between(), not the class Expectation",
        ),
        (
            lambda: register_check(
                id="checks/x",
                transform=identity,
                measures=["value"],
                expect=bk.expect.at_most(1, on="share"),
            ),
            "expect names 'share' with on=, which measures= leaves out; the measures are value",
        ),
        (
            lambda: register_check(
                id="checks/x",
                transform=identity,
                dims=["count"],
                expect=bk.expect.no_rows(by="count"),
            ),
            "expect names 'count' with by=, which dims= makes a dimension; name a measure",
        ),
        (lambda: check("title"), "@bk.check got 'title' as its argument; use @bk.check bare"),
        (
            lambda: check(bk.expect.no_rows()),
            "@bk.check got bk.expect.no_rows() as its argument; use @bk.check bare, or with "
            'keyword options: @bk.check(title="...", expect=bk.expect.no_rows(...))',
        ),
        (
            lambda: register_check(id="checks/x", transform=identity, level="loud"),
            'level must be "off", "warn" or "error", got \'loud\'',
        ),
        (
            lambda: check(transform=identity)(identity),
            "transform= belongs to bk.register_check(); with @bk.check the decorated function is "
            "the transform",
        ),
        (lambda: check(identity, title="x"), "use @bk.check(...) with options, or @bk.check alone"),
        (lambda: check()(lambda run, extra: run), "must take exactly one positional parameter"),
        (
            lambda: register(
                id="defs/x", plot=bk.plots.line(x="a", y="b"), transform=identity, level="always"
            ),
            'level must be "off", "warn" or "error", got \'always\'',
        ),
        (lambda: group("defs", level="loud"), 'level must be "off", "warn" or "error"'),
    ],
)
def test_invalid_check_definitions_say_what_to_do(make: Any, expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        make()
    assert expected in str(info.value)


def test_an_invalid_check_is_named_a_check() -> None:
    with pytest.raises(bk.DefinitionError) as info:
        register_check(id="checks/x", transform=identity, level=1)
    assert str(info.value).splitlines()[0].endswith("  check checks/x")


# ---------------------------------------------------------------------------------------------
# Discovery: groups, levels and one namespace of ids


def test_a_module_with_checks_only_defines_something(tmp_path: Path) -> None:
    root = make_project(
        tmp_path,
        {"blicks/checks.py": "import blicket as bk\n\n@bk.check\ndef none(run):\n    return run\n"},
    )
    registry = bk.discover(root)
    assert (list(registry.checks), registry.blicks, registry.problems) == (["checks/none"], {}, ())


SHARED = """\
import blicket as bk

bk.register(id="a/x", plot=bk.plots.line(x="year", y="value"), transform=lambda r: r)
bk.register_check(id="a/x", transform=lambda r: r)
bk.register_check(id="a/y", aliases=["a/z"], transform=lambda r: r)
bk.register(
    id="a/w", aliases=["a/y"], plot=bk.plots.line(x="year", y="value"), transform=lambda r: r
)
"""


def test_a_blick_and_a_check_share_one_namespace_of_ids_and_aliases(tmp_path: Path) -> None:
    registry = bk.discover(make_project(tmp_path, {"blicks/a.py": SHARED}))
    assert (registry.blicks, registry.checks) == ({}, {})
    failed = {
        (entry.kind, entry.name): [p.message for p in entry.problems] for entry in registry.failed
    }
    assert failed == {
        ("Blick", "a/x"): [
            "id a/x is also defined at blicks/a.py:4; give one of them a different id"
        ],
        ("check", "a/x"): [
            "id a/x is also defined at blicks/a.py:3; give one of them a different id"
        ],
        ("check", "a/y"): [
            "its id is listed as an alias by a/w (blicks/a.py:6); remove that alias"
        ],
        ("Blick", "a/w"): ["alias 'a/y' is the current id of a/y (blicks/a.py:5); remove it"],
    }
    assert isinstance(next(e for e in registry.failed if e.kind == "check"), bk.CheckEntry)


LEVELS = {
    "blicks/a.py": """\
import polars as pl

import blicket as bk

bk.group("shared", level="warn")

@bk.check
def inherits(run):
    return pl.DataFrame()

@bk.check(level="off")
def own(run):
    return pl.DataFrame()
""",
    "blicks/b.py": """\
import polars as pl

import blicket as bk

bk.group("shared", level="error")

@bk.check
def also_inherits(run):
    return pl.DataFrame()
""",
    "blicks/c.py": """\
import polars as pl

import blicket as bk

@bk.check
def from_the_project(run):
    return pl.DataFrame()
""",
}


def test_levels_come_from_the_unit_its_group_and_the_project(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, LEVELS, 'level = "warn"\n')
    registry = bk.discover(root)
    assert registry.groups["shared"].level == "warn"
    (warning,) = registry.warnings
    assert warning.message == (
        "group 'shared' gets a level in blicks/a.py:5 ('warn') and here ('error'); the first is "
        "used, give the level in one module only"
    )
    make_run(root / "runs" / "a")
    built = bk.build(root, [root / "runs" / "a"]).manifest
    levels = {entry.name: (entry.level, entry.status) for entry in built.checks}
    assert levels == {
        "shared/inherits": ("warn", "ok"),
        "shared/own": ("off", "skipped"),
        "shared/also_inherits": ("warn", "ok"),
        "c/from_the_project": ("warn", "ok"),
    }
    assert built.config.level == "warn"
    (off,) = [entry for entry in built.checks if entry.level == "off"]
    assert (off.skipped, off.outcome) == ("its level is off", None)


def test_the_project_level_is_checked(tmp_path: Path) -> None:
    root = make_project(tmp_path, {}, 'level = "loud"\n')
    with pytest.raises(
        bk.ConfigError, match='level must be "off", "warn" or "error", got \'loud\''
    ):
        bk.load_config(root)


# ---------------------------------------------------------------------------------------------
# The table of a check


def as_check(transform: Any, **options: Any) -> bk.Check:
    return bk.Check(id="checks/x", title="X", group="checks", transform=transform, **options)


def computed(frame: Any, **options: Any) -> tables.Checked:
    return tables.compute(as_check(lambda run: frame, **options), None, Path())


def test_a_check_table_may_hold_nulls_in_its_dimensions_and_several_measures() -> None:
    frame = pl.DataFrame(
        {
            "Flow": ["a", "a", "b"],
            "Region": [None, "EUR", "EUR"],
            "value": [-1.0, -2.0, -0.5],
            "relative": [-0.1, -0.2, -0.05],
        }
    )
    found = computed(frame, expect=bk.expect.no_rows(by="relative"))
    assert found.problems == ()
    assert found.frame is not None
    assert found.schema is not None
    assert found.frame.rows() == [
        ("a", "EUR", -2.0, -0.2),
        ("a", None, -1.0, -0.1),
        ("b", "EUR", -0.5, -0.05),
    ]
    assert [d.values for d in found.schema.dimensions] == [["a", "b"], ["EUR"]]
    assert [m.name for m in found.schema.measures] == ["value", "relative"]
    assert found.outcome == bk.Outcome(
        result="failed",
        expectation="no rows, by relative",
        offending=3,
        worst=-0.2,
        distance=0.2,
        where={"Flow": "a", "Region": "EUR"},
    )


def test_rows_of_a_check_stay_unique_with_nulls_equal() -> None:
    frame = pl.DataFrame({"Flow": ["a", "a"], "Region": [None, None], "value": [1.0, 2.0]})
    (problem,) = computed(frame).problems
    assert problem.message.startswith("2 rows repeat the dimension values of another row")


@pytest.mark.parametrize(
    "frame",
    [
        pl.DataFrame(),
        pl.DataFrame({"Flow": [], "value": []}),
        pl.DataFrame({"Flow": ["a"]}).clear(),
    ],
    ids=["without columns", "of nulls", "typed"],
)
def test_an_empty_check_table_is_met_without_a_warning(frame: pl.DataFrame) -> None:
    found = computed(frame)
    assert (found.problems, found.outcome) == ((), bk.Outcome(result="met", expectation="no rows"))
    assert found.frame is not None
    assert found.frame.height == 0


def above_maximum(table: pl.DataFrame) -> pl.DataFrame:
    """The rows above the maximum of their year, with a measure the table does not have."""
    return table.with_columns(excess=pl.col("value") - 1.0).filter(pl.col("excess") > 0)


def empty_unit(kind: str, frame: pl.DataFrame, expect: Any) -> bk.Blick | bk.Check:
    if kind == "check":
        return as_check(lambda run: frame, expect=expect)
    return bk.Blick(
        id="units/x",
        title="X",
        group="units",
        plot=bk.plots.line(x="year", y="value"),
        expect=expect,
        transform=lambda run: frame,
    )


@pytest.mark.parametrize("kind", ["Blick", "check"])
def test_a_rows_function_is_met_on_an_empty_table_without_checking_its_columns(kind: str) -> None:
    empty = pl.DataFrame({"year": [2020], "value": [1.0]}).clear()
    expect = bk.expect.no_rows(above_maximum, by="excess")
    found = tables.compute(empty_unit(kind, empty, expect), None, Path())
    assert found.outcome == bk.Outcome(
        result="met", expectation="no rows of above_maximum, by excess"
    )


@pytest.mark.parametrize(
    ("expect", "words"),
    [
        (bk.expect.no_rows(by="value"), "no rows, by value"),
        (bk.expect.at_most(0, on="value"), "value at most 0"),
    ],
)
def test_an_empty_check_table_is_checked_only_for_the_column_named(expect: Any, words: str) -> None:
    """A column without values, as an untyped empty frame has, is a dimension in a check's table
    (a Blick's table rejects it); the measure named is found among the columns whatever their
    roles."""
    found = computed(pl.DataFrame({"Flow": [], "value": []}), expect=expect)
    assert found.problems == ()
    assert found.outcome is not None
    assert (found.outcome.result, found.outcome.expectation) == ("met", words)


def test_an_empty_blick_table_is_checked_only_for_the_column_named() -> None:
    empty = pl.DataFrame({"year": [2020], "value": [1.0]}).clear()
    unit = empty_unit("Blick", empty, bk.expect.at_most(0, on="year"))
    found = tables.compute(unit, None, Path())
    assert found.outcome == bk.Outcome(result="met", expectation="year at most 0", evaluated=0)


def test_an_untyped_empty_check_table_is_met_by_a_bound_without_on() -> None:
    found = computed(pl.DataFrame({"Flow": [], "value": []}), expect=bk.expect.at_most(0))
    assert found.outcome == bk.Outcome(result="met", expectation="at most 0", evaluated=0)


def test_a_typo_in_by_shows_on_an_empty_table() -> None:
    found = computed(pl.DataFrame({"Flow": [], "value": []}), expect=bk.expect.no_rows(by="valeu"))
    assert found.outcome is not None
    assert (found.outcome.result, found.outcome.message) == (
        "error",
        "by= names 'valeu', which is no column of the table; its columns are Flow, value",
    )


def test_none_is_an_error_since_a_forgotten_return_would_pass() -> None:
    (problem,) = computed(None).problems
    assert problem.message == (
        "the check returned None; did it forget return? A check returns the rows that offend as a "
        "table, an empty one when the property holds"
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "the check returned a list; wrap it in pl.DataFrame(...); a check returns the rows"),
        (False, "the check returned bool; return a polars or pandas frame"),
    ],
)
def test_what_a_check_returns_is_said_in_its_words(value: object, message: str) -> None:
    (problem,) = computed(value).problems
    assert problem.message.startswith(message)
    assert problem.message.endswith("an empty one when the property holds")


def test_a_check_that_raises_names_the_check() -> None:
    def raising(run: Any) -> Any:
        return run["missing"]

    (problem,) = tables.compute(as_check(raising), {}, Path()).problems
    assert problem.message.startswith("check raised KeyError: 'missing'")


def test_an_infinite_value_in_a_check_is_rejected_for_ranking() -> None:
    (problem,) = computed(pl.DataFrame({"n": [1], "value": [float("inf")]})).problems
    assert problem.message == (
        "measure column 'value' has 1 infinite value(s), which ranks no row; replace them with "
        "null or a number"
    )


def test_a_check_stores_its_worst_rows_up_to_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tables, "MAX_STORED", 3)
    frame = pl.DataFrame({"n": list(range(5)), "value": [-1.0, -5.0, -3.0, -4.0, -2.0]})
    found = computed(frame, expect=bk.expect.no_rows(by="value", warn_within=10))
    assert found.frame is not None
    assert found.frame["n"].to_list() == [1, 3, 2]
    assert found.outcome is not None
    assert (found.outcome.offending, found.outcome.within, found.outcome.result) == (
        5,
        5,
        "warning",
    )


def picking(rows: Any, **options: Any) -> bk.Blick:
    """A Blick of years and values whose expectation picks its rows with ``rows``, with the
    other ``options`` of ``no_rows``."""
    table = pl.DataFrame({"year": [2020, 2021], "value": [1.0, 2.0]})
    return bk.Blick(
        id="units/x",
        title="X",
        group="units",
        plot=bk.plots.line(x="year", y="value"),
        expect=bk.expect.no_rows(rows, **options),
        transform=lambda run: table,
    )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            lambda table: pd.DataFrame([[1.0, 2.0]], columns=["a", "a"]),
            "the rows function <lambda> returned rows that cannot be read: DuplicateError",
        ),
        (
            lambda table: pl.DataFrame({"n": pl.Series([2**63 + 1], dtype=pl.UInt64), "v": [1.0]}),
            "the rows function <lambda> returned rows that cannot be read: InvalidOperationError",
        ),
        (lambda table: None, "the rows function <lambda> returned None; did it forget return?"),
    ],
    ids=["duplicate columns", "UInt64 above 2^63", "None"],
)
def test_rows_that_cannot_be_read_are_an_outcome_error_and_keep_the_table(
    rows: Any, message: str
) -> None:
    found = tables.compute(picking(rows), None, Path())
    assert found.frame is not None
    assert found.frame.height == 2
    assert found.outcome is not None
    assert found.outcome.result == "error"
    assert found.outcome.message is not None
    assert found.outcome.message.startswith(message)


def test_a_dimension_named_in_a_rows_function_result_says_where_to_cast_it() -> None:
    def crowded(table: Any) -> Any:
        return table.group_by("year").len()

    found = tables.compute(picking(crowded, by="len"), None, Path())
    assert found.outcome is not None
    assert found.outcome.message == (
        "by= names 'len', a dimension of the table, not a measure; integer and string columns are "
        "dimensions; cast it to float in the rows function"
    )


def test_a_multi_line_error_of_a_rows_function_keeps_its_first_line() -> None:
    def raising(table: Any) -> Any:
        raise ValueError("no maximum\n  in 2020\n  in 2021")

    found = tables.compute(picking(raising), None, Path())
    assert found.outcome is not None
    assert found.outcome.message is not None
    assert found.outcome.message.startswith(
        "the rows function raising raised ValueError: no maximum"
    )
    assert "\n" not in found.outcome.message


def test_a_skip_in_a_rows_function_is_an_outcome_error() -> None:
    def skipping(table: Any) -> Any:
        raise bk.Skip("no maximum")

    found = tables.compute(picking(skipping), None, Path())
    assert found.skipped is None
    assert found.outcome is not None
    assert found.outcome.message == "the rows function skipping raised Skip: no maximum"


def test_a_check_at_level_off_does_not_run() -> None:
    def fails(run: Any) -> Any:
        raise AssertionError("ran")

    assert tables.compute(as_check(fails), None, Path(), "off") == tables.Checked.skip(
        "its level is off"
    )


# ---------------------------------------------------------------------------------------------
# Builds: outcomes in the manifest, files, ids

BLICKS = """\
import polars as pl

import blicket as bk


def table(run):
    years = list(range(2020, 2020 + len(run["values"])))
    return pl.DataFrame({"year": years, "value": run["values"]})


@bk.blick(plot=bk.plots.line(x="year", y="value"), expect=bk.expect.at_most(2.5))
def bounded(run):
    return table(run)


def above_two(frame):
    return frame.filter(pl.col("value") > 2).with_columns(excess=pl.col("value") - 2)


@bk.blick(
    plot=bk.plots.line(x="year", y="value"),
    expect=bk.expect.no_rows(above_two, by="excess"),
    level="warn",
)
def picked(run):
    return table(run)


@bk.blick(plot=bk.plots.line(x="year", y="value"), expect=bk.expect.at_most(1, on="other"))
def unevaluable(run):
    return table(run)


def raises(frame):
    raise KeyError("maximum")


@bk.blick(plot=bk.plots.line(x="year", y="value"), expect=bk.expect.no_rows(raises))
def rows_raise(run):
    return table(run)


@bk.blick(plot=bk.plots.line(x="year", y="value"))
def plain(run):
    return table(run)


@bk.check(expect=bk.expect.no_rows(by="value", warn_within=0.5))
def negative(run):
    return table(run).filter(pl.col("value") < 0)


@bk.check
def nothing(run):
    return pl.DataFrame()


@bk.check
def skipping(run):
    raise bk.Skip("the run has no stocks")


@bk.check
def raising(run):
    return run["missing"]
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with the units above and the runs a (1 2 3) and b (1 -0.2 2), outside git."""
    root = make_build_project(tmp_path, {"blicks/units.py": BLICKS})
    make_run(tmp_path / "runs" / "a")
    make_run(tmp_path / "runs" / "b", "1 -0.2 2")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return root


def by_name(built: bk.Manifest) -> dict[str, bk.BlickEntry | bk.CheckEntry]:
    return {entry.name: entry for entry in built.entries}


def test_a_build_records_the_outcomes_beside_the_statuses(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    entries = by_name(built.manifest)
    summary = {
        name: (entry.status, entry.outcome.result if entry.outcome else None)
        for name, entry in entries.items()
    }
    assert summary == {
        "units/bounded": ("ok", "failed"),
        "units/picked": ("ok", "warning"),
        "units/unevaluable": ("ok", "error"),
        "units/rows_raise": ("ok", "error"),
        "units/plain": ("ok", None),
        "units/negative": ("ok", "met"),
        "units/nothing": ("ok", "met"),
        "units/skipping": ("skipped", None),
        "units/raising": ("error", None),
    }
    bounded = entries["units/bounded"].outcome
    assert bounded == bk.Outcome(
        result="failed",
        expectation="value at most 2.5",
        evaluated=3,
        offending=1,
        worst=3.0,
        distance=0.5,
        where={"year": 2022},
    )
    picked = entries["units/picked"].outcome
    assert picked is not None
    assert (picked.expectation, picked.offending, picked.worst, picked.where) == (
        "no rows of above_two, by excess",
        1,
        1.0,
        {"year": 2022},
    )
    # An expectation that cannot be evaluated keeps the Blick's table and is an error.
    unevaluable = entries["units/unevaluable"]
    assert unevaluable.data == "blicks/units/unevaluable.parquet"
    assert unevaluable.outcome is not None
    assert unevaluable.outcome.message == (
        "on= names 'other', which is no column of the table; its measures are value"
    )
    raised = entries["units/rows_raise"].outcome
    assert raised is not None
    assert raised.message is not None
    assert raised.message.startswith(
        "the rows function raises raised KeyError: 'maximum' (raised at blicks/units.py:"
    )
    assert entries["units/rows_raise"].data is not None
    assert built.manifest.has_errors
    assert (built.manifest.failed_expectations, built.manifest.results["met"]) == (1, 2)


def test_a_met_check_writes_no_table(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    met = by_name(built.manifest)["units/negative"]
    assert (met.data, met.hash, met.columns, met.rows) == (None, None, None, 0)
    files = sorted(p.relative_to(built.path).as_posix() for p in built.path.rglob("*.parquet"))
    assert [f for f in files if f.startswith("checks/")] == []


def test_a_check_that_finds_rows_stores_them(project: Path) -> None:
    built = bk.build(project, ["runs/b"])
    warned = by_name(built.manifest)["units/negative"]
    assert (warned.data, warned.rows) == ("checks/units/negative.parquet", 1)
    assert warned.outcome is not None
    assert warned.outcome.result == "warning"
    stored = pl.read_parquet(built.path / "checks" / "units" / "negative.parquet")
    assert stored.rows() == [(2021, -0.2)]
    assert warned.columns is not None
    assert [d.name for d in warned.columns.dimensions] == ["year"]


def test_the_manifest_is_spec_0_3_and_validates_against_its_schema(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    data = json.loads((built.path / "manifest.json").read_text())
    assert data["spec"] == "0.3"
    assert [entry["id"] for entry in data["checks"]][:2] == ["units/negative", "units/nothing"]
    jsonschema.validate(data, bk.Manifest.model_json_schema(mode="serialization"))
    assert bk.Manifest.model_validate(data) == built.manifest


def test_a_manifest_of_spec_0_2_reads_with_the_defaults(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    data = json.loads((built.path / "manifest.json").read_text())
    data["spec"] = "0.2"
    del data["checks"]
    del data["config"]["level"]
    for group in data["groups"]:
        del group["level"]
    for entry in data["blicks"]:
        for key in ("level", "outcome"):
            del entry[key]
        if entry["definition"]:
            del entry["definition"]["level"]
            del entry["definition"]["expect"]
    (built.path / "manifest.json").write_text(json.dumps(data))
    read = manifest.read(built.path)
    assert (read.spec, read.checks, read.config.level) == ("0.2", (), "error")
    assert all(entry.outcome is None and entry.expectation is None for entry in read.blicks)


def build_id(project: Path, run: str = "runs/a") -> str:
    return bk.build(project, [run]).manifest.build.id


def test_the_same_run_gives_the_same_id(project: Path) -> None:
    assert build_id(project) == build_id(project)


@pytest.mark.parametrize(
    "edit",
    [
        ("bk.expect.at_most(2.5)", "bk.expect.at_most(2.75)"),  # the expectation and the outcome
        ('level="warn",', 'level="error",'),  # the declared level and the result
        ("@bk.check\ndef nothing", '@bk.check(level="warn")\ndef nothing'),  # the declared level
    ],
    ids=["expectation", "level and result", "declared level"],
)
def test_the_id_covers_the_expectation_the_declared_level_and_the_outcome(
    project: Path, edit: tuple[str, str]
) -> None:
    before = build_id(project)
    path = project / "blicks" / "units.py"
    path.write_text(path.read_text().replace(*edit))
    assert build_id(project) != before


def test_the_id_leaves_out_the_resolved_level_the_wording_and_the_timings(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = bk.build(project, ["runs/a"]).manifest
    edited = built.model_copy(
        update={
            "checks": tuple(
                entry.model_copy(update={"level": "warn", "timing_ms": 1e6})
                for entry in built.checks
            ),
            "blicks": tuple(
                entry.model_copy(
                    update={
                        "outcome": entry.outcome.model_copy(update={"expectation": "reworded"})
                        if entry.outcome
                        else None
                    }
                )
                for entry in built.blicks
            ),
        }
    )
    assert edited.content_id(project) == built.content_id(project)


def test_push_copies_the_tables_of_both_kinds(project: Path, tmp_path: Path) -> None:
    built = bk.build(project, ["runs/b"])
    pushed = Store(tmp_path / "store").push(built.path)
    files = sorted(p.relative_to(pushed.path).as_posix() for p in pushed.path.rglob("*.parquet"))
    assert "checks/units/negative.parquet" in files
    assert "blicks/units/bounded.parquet" in files


ONLY_A_CHECK = """\
import polars as pl

import blicket as bk


@bk.check
def c(run):
    return pl.DataFrame()
"""


def test_a_project_with_checks_and_no_blick_builds(tmp_path: Path) -> None:
    root = make_build_project(
        tmp_path,
        {"blicks/a.py": ONLY_A_CHECK},
    )
    make_run(root / "runs" / "a")
    built = bk.build(root, [root / "runs" / "a"]).manifest
    assert (built.blicks, [entry.name for entry in built.checks]) == ((), ["a/c"])


def test_a_project_with_checks_says_that_checks_may_be_missing_too(tmp_path: Path) -> None:
    root = make_build_project(
        tmp_path, {"blicks/a.py": ONLY_A_CHECK, "blicks/b.py": "import nothere\n"}
    )
    registry = bk.discover(root)
    (problem,) = registry.errors
    assert problem.message.endswith("the Blicks and checks in this file are missing")
    make_run(root / "runs" / "a")
    built = bk.build(root, [root / "runs" / "a"])
    assert report.render_build(built).splitlines()[2] == (
        "1 check: 1 ran · 1 import error · 1 warning · incomplete (Blicks and checks missing)"
    )


@pytest.mark.parametrize(
    ("definition", "said"),
    [
        (
            "@bk.check(expect=bk.expect.no_rows(by='value', warn_within=-1))",
            "warn_within must be 0 or more",
        ),
        ('@bk.check("Flows are not negative")', "@bk.check got 'Flows are not negative'"),
        ("@bk.check(len, title='Lengths')", "use @bk.check(...) with options, or @bk.check alone"),
        ("@bk.check(expect=bk.expect.between(1, 0))", "low is above high"),
        ("@bk.check(expect=bk.expect.at_most(float('nan')))", "got nan"),
        ("@bk.check(expect=bk.expect.at_most(10**400))", "got one beyond the range of a float"),
        ("@bk.check(expect=bk.expect.at_most(1, on=3))", "on= must name a measure column"),
        ("@bk.check(expect=bk.expect.no_rows(3))", "rows must be a function of the table"),
        ("@bk.check(expect=bk.expect.no_rows(lambda: None))", "taking exactly one positional"),
        ("@bk.check(expect=bk.expect.no_rows(len, warn_within=1))", "warn_within= needs by="),
    ],
    ids=[
        "warn_within below 0",
        "title as argument",
        "function and options",
        "between",
        "nan",
        "beyond a float",
        "on not a name",
        "rows not a function",
        "rows without a parameter",
        "warn_within without by",
    ],
)
def test_a_file_lost_on_a_check_says_its_checks_are_missing(
    tmp_path: Path, definition: str, said: str
) -> None:
    module = f"import blicket as bk\n\n\n{definition}\ndef negative(run):\n    return run\n"
    root = make_build_project(tmp_path, {"blicks/a.py": module})
    (problem,) = bk.discover(root).errors
    assert said in problem.message
    assert problem.message.endswith("\nthe Blicks and checks in this file are missing")
    make_run(root / "runs" / "a")
    with pytest.raises(NothingToBuild, match=r"^no Blick or check can be built, so no build"):
        bk.build(root, [root / "runs" / "a"])


def test_nothing_to_build_names_the_checks_of_a_project_with_checks(tmp_path: Path) -> None:
    broken = 'import blicket as bk\n\nbk.register_check(id="a/x", transform=1)\n'
    root = make_build_project(tmp_path, {"blicks/a.py": broken})
    make_run(root / "runs" / "a")
    with pytest.raises(NothingToBuild, match=r"^no Blick or check can be built, so no build"):
        bk.build(root, [root / "runs" / "a"])
