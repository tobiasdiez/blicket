"""Comparing two builds: matching their Blicks, the flags, the reasons, and the movers."""

import shutil
import tempfile
from pathlib import Path

import polars as pl
import pytest

import blicket as bk
from blicket import manifest
from blicket.comparison import compare_builds
from blicket.errors import BlicketError, Problem, Source
from blicket.model import BlickEntry, PlotDefinition
from blicket.schema import Flag
from tests.support import VALUES, make_build_project, make_run

SCALED = """\
import polars as pl

import blicket as bk

LINE = bk.plots.line(x="year", y="value")
FACTOR = 1.0


def table(run, factor):
    return pl.DataFrame({"year": [2020, 2021, 2022], "value": [factor * v for v in run["values"]]})


@bk.blick(plot=LINE)
def plain(run):
    return table(run, FACTOR)


@bk.blick(plot=LINE, tolerance=1e-7)
def strict(run):
    return table(run, FACTOR)


@bk.blick(plot=LINE)
def big(run):
    return table(run, 1 + 1e5 * (FACTOR - 1))
"""


def builds(tmp_path: Path, before: str, after: str) -> tuple[Path, Path]:
    """The build directories of one run with the Blick module ``before``, then ``after``."""
    root = make_build_project(tmp_path, {"blicks/a.py": before})
    run = make_run(tmp_path / "run")
    first = bk.build(root, [run]).path
    (root / "blicks" / "a.py").write_text(after)
    return first, bk.build(root, [run]).path


def flags(comparison: bk.Comparison) -> list[tuple[str | None, list[Flag]]]:
    return [(blick.id, sorted(blick.change.flags)) for blick in comparison.blicks]


def test_a_changed_transformation_is_value(tmp_path: Path) -> None:
    after = VALUES.replace('run["values"]', "[1.0, 2.0, 3.3]")
    (blick,) = compare_builds(*builds(tmp_path, VALUES, after)).blicks
    assert (blick.change.flags, blick.change.where) == ({"value"}, {"year": 2022})
    assert blick.change.magnitude == pytest.approx(0.3 / 3.3)


def test_a_new_dimension_value_is_schema(tmp_path: Path) -> None:
    after = VALUES.replace("2022]", "2022, 2023]").replace('run["values"]', "[1.0, 2.0, 3.0, 4.0]")
    (blick,) = compare_builds(*builds(tmp_path, VALUES, after)).blicks
    assert (blick.change.flags, blick.change.values_added) == ({"schema"}, {"year": [2023]})
    assert blick.change.magnitude == 0.0


@pytest.fixture
def scaled(tmp_path: Path) -> bk.Comparison:
    """Three Blicks scaled by 1 + 1e-6, the last by 1.1; the second has a tolerance of 1e-7."""
    return compare_builds(*builds(tmp_path, SCALED, SCALED.replace("1.0", "1.000001")))


def test_the_tolerance_of_a_blick_decides_value(scaled: bk.Comparison) -> None:
    assert flags(scaled) == [("a/plain", []), ("a/strict", ["value"]), ("a/big", ["value"])]
    assert scaled.blicks[0].change.magnitude == pytest.approx(1e-6, rel=1e-5)  # below 1e-5


def test_the_movers_are_the_largest_values_first(scaled: bk.Comparison) -> None:
    _, strict, big = scaled.blicks
    assert (scaled.movers(3), scaled.movers(1)) == ([big, strict], [big])


# Cases on a copy of a build whose manifest is edited; the comparison checks neither the id nor
# the hashes.


@pytest.fixture
def build(tmp_path: Path) -> Path:
    """A build with the one Blick ``a/values``."""
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    return bk.build(root, [make_run(tmp_path / "run")]).path


def edited(build: Path, *blicks: BlickEntry, problems: tuple[Problem, ...] = ()) -> Path:
    """A copy of ``build`` whose manifest holds ``blicks`` and the file-level ``problems``, and is
    incomplete when one of them is an error."""
    copy = Path(tempfile.mkdtemp(dir=build.parent))
    shutil.copytree(build, copy, dirs_exist_ok=True)
    built = manifest.read(build)
    incomplete = any(problem.severity == "error" for problem in problems)
    info = built.build.model_copy(update={"incomplete": incomplete})
    updated = built.model_copy(update={"blicks": blicks, "build": info, "problems": problems})
    (copy / manifest.MANIFEST).write_text(updated.model_dump_json())
    return copy


def entry(build: Path, **update: object) -> BlickEntry:
    return manifest.read(build).blicks[0].model_copy(update=update)


def failed(build: Path, **update: object) -> BlickEntry:
    """The entry of a Blick whose transformation raised."""
    problem = Problem(kind="transformation", message="transformation raised KeyError\nmore")
    nothing = {"data": None, "hash": None, "rows": None, "columns": None, "controls": ()}
    return entry(build, **nothing, problems=(problem,), **update)


IMPORT_FAILED = Problem(
    kind="import", source=Source(Path("blicks/broken.py"), 1), message="ModuleNotFoundError\nmore"
)


def test_a_build_against_itself_is_unchanged(build: Path) -> None:
    comparison = compare_builds(build, build)
    assert flags(comparison) == [("a/values", [])]
    assert comparison.blicks[0].change.magnitude == 0.0
    assert (comparison.counts, comparison.incomplete, comparison.has_errors) == ({}, (), False)
    assert comparison.current.id == manifest.read(build).build.id


def test_a_blick_renamed_with_an_alias_is_matched(build: Path) -> None:
    renamed = entry(build, id="a/renamed", name="a/renamed", aliases=("a/old", "a/values"))
    (blick,) = compare_builds(build, edited(build, renamed)).blicks
    assert (blick.id, blick.matched, blick.change.flags) == ("a/renamed", "a/values", set())


def test_an_alias_with_a_table_comes_before_the_id_without_one(build: Path) -> None:
    baseline = edited(build, failed(build, id="a/b", name="a/b"), entry(build))
    current = entry(build, id="a/b", name="a/b", aliases=("a/values",))
    (blick,) = compare_builds(baseline, edited(build, current)).blicks
    assert (blick.matched, blick.change.flags) == ("a/values", set())


def test_a_new_blick(build: Path) -> None:
    extra = entry(build, id="a/extra", name="a/extra")
    comparison = compare_builds(build, edited(build, entry(build), extra))
    assert flags(comparison) == [("a/values", []), ("a/extra", ["new"])]


def test_a_blick_whose_baseline_failed_is_new_and_says_so(build: Path) -> None:
    (blick,) = compare_builds(edited(build, failed(build)), build).blicks
    assert (blick.change.flags, blick.message) == ({"new"}, "did not build in the baseline")


def test_a_blick_without_a_baseline_is_new_without_a_message(build: Path) -> None:
    (blick,) = compare_builds(edited(build), build).blicks
    assert (blick.change.flags, blick.message) == ({"new"}, None)


def test_a_removed_blick(build: Path) -> None:
    comparison = compare_builds(build, edited(build))
    assert (flags(comparison), comparison.incomplete) == ([("a/values", ["removed"])], ())


def test_a_baseline_blick_without_a_table_is_not_removed(build: Path) -> None:
    assert compare_builds(edited(build, failed(build)), edited(build)).blicks == ()


def test_nothing_is_removed_from_an_incomplete_build(build: Path) -> None:
    comparison = compare_builds(build, edited(build, problems=(IMPORT_FAILED,)))
    assert (comparison.blicks, comparison.incomplete) == (
        (),
        ("blicks/broken.py failed to import",),
    )
    assert comparison.current.incomplete
    assert comparison.has_errors


def test_another_file_level_error_names_its_message(build: Path) -> None:
    clash = Problem(kind="name_clash", message="two modules are called a\nmore")
    comparison = compare_builds(build, edited(build, entry(build), problems=(clash,)))
    assert comparison.incomplete == ("the project: two modules are called a",)


def test_a_failed_blick_is_error_with_its_cause_and_not_removed(build: Path) -> None:
    (blick,) = compare_builds(build, edited(build, failed(build))).blicks
    assert (blick.change.flags, blick.message) == ({"error"}, "transformation raised KeyError")


def test_two_failed_blicks_may_share_an_id(build: Path) -> None:
    twice = edited(build, failed(build), failed(build))
    assert flags(compare_builds(build, twice)) == [("a/values", ["error"])] * 2


def test_a_blick_without_an_id_disables_removed(build: Path) -> None:
    nameless = failed(build, id=None, name="'Bad'", definition=None)
    comparison = compare_builds(build, edited(build, nameless, problems=(IMPORT_FAILED,)))
    assert flags(comparison) == [(None, ["error"])]
    assert comparison.incomplete == ("blicks/broken.py failed to import", "'Bad' has no usable id")


def test_an_unknown_plot_type_is_error_with_a_message(build: Path) -> None:
    definition = entry(build).definition
    assert definition is not None
    plot = PlotDefinition(type="custom", mapping=definition.plot.mapping)
    custom = entry(build, definition=definition.model_copy(update={"plot": plot}))
    (blick,) = compare_builds(build, edited(build, custom)).blicks
    assert (blick.change.flags, blick.message) == (
        {"error"},
        "no built-in plot type 'custom'; the built-ins are line, stacked_area, bar, stacked_bar",
    )


def test_tables_the_plot_type_rejects_are_error_with_its_message(build: Path) -> None:
    baseline = edited(build, entry(build))
    repeated = pl.DataFrame({"year": [2020, 2020], "value": [1.0, 2.0]})
    repeated.write_parquet(baseline / "blicks" / "a" / "values.parquet")
    (blick,) = compare_builds(baseline, build).blicks
    assert (blick.change.flags, blick.message) == (
        {"error"},
        "dimension values must be unique in each table",
    )


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_an_unreadable_table_is_an_error(build: Path, side: str) -> None:
    copy = edited(build, entry(build))
    (copy / "blicks" / "a" / "values.parquet").write_text("not parquet")
    pair = (copy, build) if side == "baseline" else (build, copy)
    with pytest.raises(BlicketError, match=r"^cannot read blicks/a/values\.parquet in .*: parquet"):
        compare_builds(*pair)


def test_a_missing_table_is_an_error(build: Path) -> None:
    copy = edited(build, entry(build))
    (copy / "blicks" / "a" / "values.parquet").unlink()
    with pytest.raises(BlicketError, match=r": file missing$"):
        compare_builds(build, copy)
