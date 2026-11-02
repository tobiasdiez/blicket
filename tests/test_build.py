"""The headless build: entries and files, build ids, repository state, the manifest's schema."""

import json
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import polars as pl
import pytest
from pydantic import ValidationError

import blicket as bk
from blicket import loader, manifest, viewer
from blicket.builder import Build, NothingToBuild
from blicket.errors import BlicketError
from blicket.manifest import Manifest
from blicket.model import PlotDefinition
from blicket.schema import Control, Dimension, Measure, TableSchema
from tests.support import (
    SKIPPING_VALUES,
    VALUES,
    commit_all,
    git,
    line_of,
    make_build_project,
    make_run,
    one_blick,
)

BLICKS = """\
import pandas as pd
import polars as pl

import blicket as bk

LINE = bk.plots.line(x="year", y="value")
YEARS = [2020, 2021, 2022]
FACTOR = 1


@bk.blick(plot=LINE)
def from_polars(run):
    return pl.DataFrame({"year": YEARS, "value": [FACTOR * v for v in run["values"]]})


@bk.blick(plot=LINE, controls={"year": "facet"})
def invalid(run):
    return run


@bk.blick(plot=LINE)
def from_pandas(run):
    return pd.DataFrame({"year": YEARS, "value": run["values"]}).set_index("year")


@bk.blick(plot=LINE)
def raising(run):
    return run["missing"]


class Broken:
    def to_df(self):
        raise ValueError("no frame")


@bk.blick(plot=LINE)
def broken(run):
    return Broken()


@bk.blick(plot=LINE)
def unbound(run):
    return pl.DataFrame({"year": YEARS, "value": run["values"], "extra": run["values"]})


@bk.blick(plot=LINE)
def skipping(run):
    raise bk.Skip("the run has no trade module")
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with the Blicks above and the run ``runs/a``, outside any git repository."""
    root = make_build_project(tmp_path, {"blicks/views.py": BLICKS})
    make_run(tmp_path / "runs" / "a")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return root


def build_id(project: Path, run: str = "runs/a") -> str:
    return bk.build(project, [run]).manifest.build.id


def test_statuses_and_files(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    # In the order of their definitions, a Blick that failed at definition among the others.
    statuses = [(entry.name, entry.status) for entry in built.manifest.blicks]
    assert statuses == [
        ("views/from_polars", "ok"),
        ("views/invalid", "error"),
        ("views/from_pandas", "ok"),
        ("views/raising", "error"),
        ("views/broken", "error"),
        ("views/unbound", "error"),
        ("views/skipping", "skipped"),
    ]
    ok = built.manifest.blicks[0]
    assert (ok.data, ok.rows) == ("blicks/views/from_polars.parquet", 3)
    assert ok.hash is not None
    assert ok.hash.startswith("parquet-sha256:")
    files = sorted(p.relative_to(built.path).as_posix() for p in built.path.rglob("*.*"))
    assert files == [
        "_nuxt/viewer.js",
        "blicks/views/from_pandas.parquet",
        "blicks/views/from_polars.parquet",
        "index.html",
        "manifest.json",
    ]
    written = json.loads((built.path / "manifest.json").read_text())
    assert written["config"] == {"tolerance": 1e-5}
    assert built.manifest.build.incomplete is False


@pytest.mark.parametrize(
    ("name", "message", "raised_in"),
    [
        ("raising", "transformation raised KeyError: 'missing'", 'run["missing"]'),
        ("broken", "converting the returned Broken raised ValueError: no frame", "no frame"),
    ],
)
def test_exceptions_are_located(project: Path, name: str, message: str, raised_in: str) -> None:
    (entry,) = [
        e for e in bk.build(project, ["runs/a"]).manifest.blicks if e.name == f"views/{name}"
    ]
    (problem,) = entry.problems
    where = f"blicks/views.py:{line_of(BLICKS, raised_in)}"
    assert (problem.kind, problem.location()) == ("transformation", where)
    assert problem.message == f"{message} (raised at {where})"
    assert problem.traceback is not None
    assert f'views.py", line {line_of(BLICKS, raised_in)}' in problem.traceback


def test_a_skipped_blick_has_its_reason_and_neither_a_table_nor_an_error(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    (skipping,) = [e for e in built.manifest.blicks if e.name == "views/skipping"]
    assert skipping.skipped == "the run has no trade module"
    assert (skipping.data, skipping.hash, skipping.rows, skipping.columns) == (None,) * 4
    assert (skipping.controls, skipping.problems) == ((), ())
    assert not (built.path / "blicks" / "views" / "skipping.parquet").exists()
    text = (built.path / "manifest.json").read_text()
    written = {entry["name"]: entry for entry in json.loads(text)["blicks"]}
    ok, skipped = written["views/from_polars"], written["views/skipping"]
    assert [(e["status"], e["skipped"]) for e in (ok, skipped)] == [
        ("ok", None),
        ("skipped", "the run has no trade module"),
    ]


def test_skipped_blicks_alone_are_no_error(tmp_path: Path) -> None:
    files = {"blicks/a.py": VALUES, "blicks/b.py": SKIPPING_VALUES}
    built = bk.build(make_build_project(tmp_path, files), [make_run(tmp_path / "run")]).manifest
    assert [entry.status for entry in built.blicks] == ["ok", "skipped"]
    assert not built.has_errors


def test_the_id_covers_the_reason_of_a_skip(project: Path) -> None:
    first = build_id(project)
    views = project / "blicks" / "views.py"
    views.write_text(views.read_text().replace("no trade module", "no trade data"))
    assert build_id(project) != first


def test_a_manifest_without_skipped_reads_as_before(project: Path) -> None:
    data = json.loads((bk.build(project, ["runs/a"]).path / "manifest.json").read_text())
    for entry in data["blicks"]:
        del entry["skipped"]
    assert all(entry.skipped is None for entry in Manifest.model_validate(data).blicks)


ERROR = bk.Problem(kind="transformation", message="transformation raised KeyError")


def scaled_values(scale: str | None) -> str:
    """The source of VALUES with the y scale ``scale`` on its plot, none for ``None``."""
    argument = "" if scale is None else f", y_scale={scale!r}"
    return (
        "import polars as pl\n\nimport blicket as bk\n\n\n"
        f'@bk.blick(plot=bk.plots.line(x="year", y="value"{argument}))\n'
        "def values(run):\n"
        '    return pl.DataFrame({"year": [2020, 2021, 2022], "value": run["values"]})\n'
    )


def test_the_manifest_records_the_scales_of_a_plot(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": scaled_values("log")})
    built = bk.build(root, [make_run(tmp_path / "run")])
    (entry,) = json.loads((built.path / "manifest.json").read_text())["blicks"]
    assert (entry["status"], entry["definition"]["plot"]) == (
        "ok",
        {"type": "line", "mapping": {"x": "year", "y": "value"}, "scales": {"y": "log"}},
    )


def test_the_id_covers_a_log_scale_but_not_a_linear_one(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": scaled_values(None)})
    run = make_run(tmp_path / "run")
    ids = []
    for scale in (None, "linear", "log"):
        (root / "blicks" / "a.py").write_text(scaled_values(scale))
        ids.append(bk.build(root, [run]).manifest.build.id)
    assert ids[0] == ids[1] != ids[2]


def test_the_status_is_skipped_with_a_reason_else_error_with_an_error_else_ok() -> None:
    def status(**fields: Any) -> str:
        return bk.BlickEntry(id="a/x", name="a/x", group="a", **fields).status

    assert status(skipped="no trade") == "skipped"
    assert status(problems=(ERROR,)) == "error"
    assert status() == "ok"


@pytest.mark.parametrize(
    "fields",
    [
        {"data": "blicks/a/x.parquet"},
        {"rows": 0},
        {"controls": (Control(dimension="year", kind="filter", default=None),)},
        {"problems": (ERROR,)},
        {"problems": (ERROR.model_copy(update={"severity": "warning"}),)},
    ],
    ids=["data", "rows", "controls", "error", "warning"],
)
def test_a_skipped_blick_has_no_table_controls_or_problems(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="a skipped Blick has no table, controls or problems"):
        bk.BlickEntry(id="a/x", name="a/x", group="a", skipped="no trade", **fields)


def test_failed_definitions_are_entries(project: Path) -> None:
    manifest = bk.build(project, ["runs/a"]).manifest
    (invalid,) = [entry for entry in manifest.blicks if entry.name == "views/invalid"]
    assert (invalid.id, invalid.definition) == ("views/invalid", None)
    assert invalid.problems[0].kind == "invalid_definition"


def test_a_module_that_fails_to_import_makes_the_build_incomplete(tmp_path: Path) -> None:
    files = {"blicks/a.py": one_blick("a/x"), "blicks/broken.py": "import nothere\n"}
    manifest = bk.build(make_build_project(tmp_path, files), [make_run(tmp_path / "run")]).manifest
    assert manifest.build.incomplete
    assert [p.kind for p in manifest.problems if p.severity == "error"] == ["import"]


def test_nothing_is_written_without_a_buildable_blick(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/broken.py": "import nothere\n"})
    with pytest.raises(NothingToBuild) as info:
        bk.build(root, [make_run(tmp_path / "run")])
    assert [p.kind for p in info.value.registry.errors] == ["import"]
    assert not (root / ".blicket").exists()


def test_nothing_is_written_without_a_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    monkeypatch.delenv(viewer.VIEWER_ENV)
    with pytest.raises(BlicketError, match="no viewer found: install blicket with its viewer"):
        bk.build(root, [make_run(tmp_path / "run")])
    assert not (root / ".blicket").exists()


def test_the_same_inputs_give_the_same_build(project: Path) -> None:
    first = bk.build(project, ["runs/a"])
    second = bk.build(project, ["runs/a"])
    assert (first.existed, second.existed, second.path) == (False, True, first.path)
    assert second.manifest.build.id == first.manifest.build.id
    assert manifest.read(first.path) == first.manifest  # the existing directory was left alone
    assert [p.name for p in first.path.parent.iterdir()] == [first.path.name]


def test_a_rebuild_reports_its_own_run_and_load_time(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = bk.build(project, ["runs/a"])
    shutil.copytree("runs/a", "runs/b")  # the same content, so the same build id
    load = loader.load
    monkeypatch.setattr(loader, "load", lambda *args: (*load(*args)[:2], 1234.5))
    second = bk.build(project, ["runs/b"])
    assert (second.existed, second.manifest.build.id) == (True, first.manifest.build.id)
    assert (second.manifest.run.id, second.manifest.build.loader_ms) == ("b", 1234.5)
    assert manifest.read(second.path) == first.manifest


def test_moving_a_blick_keeps_the_id(tmp_path: Path) -> None:
    source = VALUES.replace("import blicket as bk\n", 'import blicket as bk\n\nbk.group("views")\n')
    source = source.replace("@bk.blick(plot", '@bk.blick(id="views/values", plot')
    root = make_build_project(tmp_path, {"blicks/a.py": source})
    run = make_run(tmp_path / "run")
    first = bk.build(root, [run]).manifest.build.id
    (root / "blicks" / "a.py").unlink()
    (root / "blicks" / "b.py").write_text("# another file, another line\n" + source)
    assert bk.build(root, [run]).manifest.build.id == first


def test_a_check_that_raises_is_a_problem(tmp_path: Path) -> None:
    source = VALUES.replace(
        '"year": [2020, 2021, 2022]', '"year": pl.Series([2**63 + 1, 1, 2], dtype=pl.UInt64)'
    )
    root = make_build_project(tmp_path, {"blicks/a.py": source})
    (entry,) = bk.build(root, [make_run(tmp_path / "run")]).manifest.blicks
    (problem,) = entry.problems
    assert problem.message.startswith("checking the table raised InvalidOperationError")
    assert (problem.location(), problem.traceback is not None) == ("blicks/a.py:6", True)


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m["run"].update(id="other", paths=["elsewhere"]),
        lambda m: m["run"].update(commit="abc", branch="model", dirty=True),
        lambda m: m["repository"].update(branch="other", dirty=True),
        lambda m: m.update(blicket="9.9", created_at="2030-01-01T00:00:00Z"),
        lambda m: m["build"].update(loader_ms=99.0),
        lambda m: m["blicks"][3]["problems"][0].update(traceback="elsewhere"),
        lambda m: m["blicks"][0].update(module="moved", source={"file": "b.py", "line": 9}),
        lambda m: m["blicks"][0].update(timing_ms=1.0),
        lambda m: m["groups"][0].update(modules=["moved"]),
    ],
    ids=["run", "model", "repository", "blicket", "timing", "traceback", "place", "time", "group"],
)
def test_the_id_leaves_out(project: Path, edit: Any) -> None:
    commit_all(project)
    data = json.loads((bk.build(project, ["runs/a"]).path / "manifest.json").read_text())
    assert data["blicks"][3]["problems"][0]["traceback"] is not None
    before = Manifest.model_validate(data).content_id(project)
    edit(data)
    assert Manifest.model_validate(data).content_id(project) == before


def test_the_id_covers_problems_and_config(tmp_path: Path) -> None:
    raising = VALUES + '\n\n@bk.blick(plot=bk.plots.line(x="year", y="value"))\n'
    raising += 'def missing(run):\n    return run["missing"]\n'
    files = {"blicks/a.py": raising, "blicks/broken.py": "import nothere\n"}
    root = make_build_project(tmp_path, files)
    run = make_run(tmp_path / "run")
    ids = [bk.build(root, [run]).manifest.build.id]
    (root / "blicks" / "a.py").write_text(raising.replace('"missing"]', '"absent"]'))
    ids.append(bk.build(root, [run]).manifest.build.id)
    (root / "blicks" / "broken.py").unlink()
    ids.append(bk.build(root, [run]).manifest.build.id)
    with (root / "pyproject.toml").open("a") as file:
        file.write("tolerance = 1e-4\n")
    built = bk.build(root, [run]).manifest
    assert len({*ids, built.build.id}) == 4
    assert (built.config.tolerance, built.build.incomplete) == (1e-4, False)


def test_a_changed_table_or_profile_changes_the_id(project: Path, tmp_path: Path) -> None:
    make_run(tmp_path / "runs" / "other", profile="other")
    ids = {build_id(project), build_id(project, "runs/other")}
    views = project / "blicks" / "views.py"
    views.write_text(views.read_text().replace("FACTOR = 1", "FACTOR = 10"))
    ids.add(build_id(project))
    assert len(ids) == 3


def test_repository_state(project: Path) -> None:
    commit = commit_all(project)
    repository = bk.build(project, ["runs/a"]).manifest.repository
    assert repository is not None
    assert (repository.commit, repository.branch, repository.dirty) == (commit, "main", False)
    assert (project / ".blicket" / ".gitignore").read_text() == "*\n"
    git(project, "commit", "-q", "--allow-empty", "-m", "next")
    git(project, "checkout", "-q", "--detach")
    detached = bk.build(project, ["runs/a"]).manifest.repository
    assert detached is not None
    assert (detached.branch, detached.dirty) == (None, False)  # .blicket/ is ignored
    (project / "notes.txt").write_text("not committed")
    git(project, "commit", "-q", "--allow-empty", "-m", "third")
    dirty = bk.build(project, ["runs/a"]).manifest.repository
    assert dirty is not None
    assert dirty.dirty


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("outside", "the project is not in a git repository"),
        ("no commit", "the git repository has no commit yet"),
        ("no git", "git cannot run (No such file or directory)"),
    ],
)
def test_no_commit_is_a_warning(
    project: Path, monkeypatch: pytest.MonkeyPatch, case: str, reason: str
) -> None:
    if case == "no commit":
        git(project, "init", "-q")
    elif case == "no git":
        monkeypatch.setenv("PATH", "")
    manifest = bk.build(project, ["runs/a"]).manifest
    assert manifest.repository is None
    (warning,) = manifest.problems
    assert (warning.kind, warning.severity, warning.message) == (
        "repository",
        "warning",
        f"{reason}; the build records no commit",
    )


def test_run_paths_inside_the_project_are_relative(project: Path, tmp_path: Path) -> None:
    inside = make_run(project / "runs" / "b")
    outside = str((tmp_path / "runs" / "a").resolve())
    manifest = bk.build(project, [inside, outside, "runs/a"]).manifest
    assert manifest.run.paths == ["runs/b", outside, outside]


def test_out_puts_the_build_elsewhere(project: Path, tmp_path: Path) -> None:
    built = bk.build(project, ["runs/a"], out=tmp_path / "builds")
    assert built.path.parent == tmp_path / "builds"
    assert not (project / ".blicket").exists()


def test_unwritable_destination_and_unreadable_build(project: Path, tmp_path: Path) -> None:
    (tmp_path / "file").write_text("")
    with pytest.raises(BlicketError, match=r"^cannot write the build to .*: Not a directory$"):
        bk.build(project, ["runs/a"], out=tmp_path / "file" / "builds")
    built = bk.build(project, ["runs/a"])
    (built.path / "manifest.json").write_text("{")
    with pytest.raises(BlicketError, match=r"has no readable manifest\.json \(not valid JSON\)"):
        bk.build(project, ["runs/a"])
    (built.path / "manifest.json").write_text("{}")
    with pytest.raises(BlicketError, match=r"\(not a manifest of this blicket\)"):
        manifest.read(built.path)
    (built.path / "manifest.json").unlink()
    with pytest.raises(BlicketError, match=r"\(file missing\); delete it and rebuild$"):
        manifest.read(built.path)


def test_a_manifest_of_another_spec_says_so(project: Path) -> None:
    built = bk.build(project, ["runs/a"])
    data = json.loads((built.path / "manifest.json").read_text())
    (built.path / "manifest.json").write_text(json.dumps({**data, "spec": "0.1"}))
    with pytest.raises(
        BlicketError,
        match=r"manifest\.json is spec 0\.1; this blicket reads 0\.2: rebuild the run$",
    ):
        manifest.read(built.path)


@pytest.mark.parametrize("data", ["../x.parquet", "blicks/../../x.parquet", "/x.parquet", "x\0"])
def test_a_table_path_stays_in_the_build_directory(data: str) -> None:
    with pytest.raises(ValidationError, match="must be a path inside the build directory"):
        bk.BlickEntry(id="a/x", name="a/x", group="a", data=data)


def test_build_ids_have_the_shape_a_store_accepts(project: Path) -> None:
    assert manifest.BUILD_ID.fullmatch(build_id(project))


def test_manifest_holds_no_absolute_path(project: Path, tmp_path: Path) -> None:
    run = make_run(project / "runs" / "in")
    data = json.loads((bk.build(project, [run]).path / "manifest.json").read_text())
    for entry in data["blicks"]:
        for problem in entry["problems"]:
            problem["traceback"] = None  # tracebacks are text, which the rule does not cover
    assert str(tmp_path) not in json.dumps(data)


def test_manifest_validates_against_its_schema_and_round_trips(project: Path) -> None:
    text = (bk.build(project, ["runs/a"]).path / "manifest.json").read_text()
    jsonschema.validate(json.loads(text), Manifest.model_json_schema(mode="serialization"))
    assert json.loads(Manifest.model_validate_json(text).model_dump_json()) == json.loads(text)


CONTROLS = """\
import itertools

import polars as pl

import blicket as bk

KEYS = list(itertools.product(["low", "high"], ["USA", "EUR"], ["a", "b"], [2020, 2021]))


def table(run):
    columns = dict(zip(["scenario", "region", "kind", "year"], zip(*KEYS)))
    return pl.DataFrame({**columns, "value": [float(i) for i in range(len(KEYS))]})


@bk.blick(
    plot=bk.plots.line(x="year", y="value"),
    unit="t",
    independent_y=True,
    controls={"region": "split", "kind": "filter"},
    defaults={"scenario": "low", "kind": ["b", "a"], "region": "USA"},
)
def chosen(run):
    return table(run)


@bk.blick(plot=bk.plots.line(x="year", y="value", color="region"), defaults={"kind": "c"})
def derived(run):
    return table(run)
"""


SANKEY = """\
import polars as pl

import blicket as bk


@bk.blick(
    title="Flows",
    unit="t",
    plot=bk.plots.sankey(source="From", target="To", value="value", color="Stage"),
    defaults={"Time": 2100},
)
def flows(run):
    return pl.DataFrame({
        "Time": [2050, 2050, 2100, 2100],
        "From": ["Production", "Use", "Production", "Use"],
        "To": ["Use", "Production", "Use", "Production"],
        "Stage": ["Use", "Recycling", "Use", "Recycling"],
        "value": run["values"],
    })
"""


def test_a_sankey_blick_records_its_mapping_and_filters_the_other_dimensions(
    tmp_path: Path,
) -> None:
    root = make_build_project(tmp_path, {"blicks/flows.py": SANKEY})
    built = bk.build(root, [make_run(tmp_path / "run", "10 2 12 3")])
    (entry,) = built.manifest.blicks
    assert (entry.status, entry.rows) == ("ok", 4)
    assert entry.controls == (Control(dimension="Time", kind="filter", default=2100),)
    written = json.loads((built.path / "manifest.json").read_text())
    assert written["blicks"][0]["definition"]["plot"] == {
        "type": "sankey",
        "mapping": {"source": "From", "target": "To", "value": "value", "color": "Stage"},
    }


def test_panels_are_the_filters_and_with_independent_y_axes_the_splits() -> None:
    schema = TableSchema(
        dimensions=[
            Dimension(name=name, dtype="string", values=["a"])
            for name in ("scenario", "region", "kind")
        ],
        measures=[Measure(name="value", dtype="float")],
    )

    def entry(independent_y: bool) -> bk.BlickEntry:
        blick = bk.Blick(
            id="t/x",
            title="X",
            group="t",
            plot=bk.plots.line(x="kind", y="value"),
            independent_y=independent_y,
            controls={"region": "split"},
            transform=lambda run: run,
        )
        return blick.entry(columns=schema)

    assert entry(independent_y=False).panels == ("scenario",)
    assert entry(independent_y=True).panels == ("scenario", "region")


def test_controls_are_derived_from_the_table_and_the_requests(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/views.py": CONTROLS})
    built = bk.build(root, [make_run(tmp_path / "run")])
    chosen, derived = built.manifest.blicks
    # Values in display order, sorted here: high before low, EUR before USA.
    assert chosen.controls == (
        Control(dimension="scenario", kind="filter", default="low"),
        Control(dimension="region", kind="split", default="USA"),
        Control(dimension="kind", kind="filter", default="b"),
    )
    # Bound dimensions have no control; a default the table lacks falls back to the first value.
    assert derived.controls == (
        Control(dimension="scenario", kind="filter", default="high"),
        Control(dimension="kind", kind="filter", default="a"),
    )
    written = json.loads((built.path / "manifest.json").read_text())
    assert written["blicks"][1]["controls"][1] == {
        "dimension": "kind",
        "kind": "filter",
        "default": "a",
    }
    assert written["blicks"][1]["definition"]["controls"] == {}
    # The unit and the y axis default are part of the definition.
    definition = written["blicks"][0]["definition"]
    assert (definition["unit"], definition["independent_y"]) == ("t", True)
    # The controls follow from the definition and the columns; the id leaves them out.
    written["blicks"][0]["controls"] = []
    assert Manifest.model_validate(written).content_id(root) == built.manifest.build.id


SCATTERS = """\
import polars as pl

import blicket as bk

GDP = "GDP per capita"


def table(run):
    keys = [
        (time, region, period, scenario)
        for time in (2020, 2030)
        for region in ("EUR", "USA")
        for period in ("Historical", "Projected")
        for scenario in ("low", "high")
    ]
    columns = dict(zip(["Time", "Region", "Period", "Scenario"], zip(*keys)))
    # No GDP per capita for USA in 2030.
    gdp = [None if key[:2] == (2030, "USA") else 1e4 * (i + 1) for i, key in enumerate(keys)]
    value = [run["values"][0] * i for i in range(len(keys))]
    return pl.DataFrame({**columns, GDP: gdp, "value": value}, schema_overrides={GDP: pl.Float64})


@bk.blick(
    unit="t per person",
    plot=bk.plots.scatter(
        x=GDP, y="value", color="Region", linetype="Period", along="Time", x_scale="log"
    ),
)
def trajectories(run):
    return table(run)


@bk.blick(plot=bk.plots.scatter(x=GDP, y="value", color="Region"))
def points(run):
    return table(run)


@bk.blick(plot=bk.plots.scatter(x="Time", y="value", color="Region"))
def integer_x(run):
    return table(run).drop(GDP)
"""


@pytest.fixture
def scattered(tmp_path: Path) -> Build:
    """A build of the Blicks of SCATTERS."""
    root = make_build_project(tmp_path, {"blicks/stocks.py": SCATTERS})
    return bk.build(root, [make_run(tmp_path / "run")])


def test_a_scatter_builds_a_table_of_two_measures(scattered: Build) -> None:
    trajectories, points, _ = scattered.manifest.blicks
    assert [trajectories.status, points.status] == ["ok", "ok"]
    assert trajectories.columns is not None
    measures = [measure.name for measure in trajectories.columns.measures]
    assert (measures, trajectories.rows, trajectories.problems) == (
        ["GDP per capita", "value"],
        16,
        (),
    )


def test_rows_without_x_are_kept_with_a_null(scattered: Build) -> None:
    trajectories = scattered.manifest.blicks[0]
    assert trajectories.data is not None
    table = pl.read_parquet(scattered.path / trajectories.data)
    assert table["GDP per capita"].null_count() == 4


def test_the_dimension_the_points_connect_along_has_no_control(scattered: Build) -> None:
    trajectories, points, _ = scattered.manifest.blicks
    assert trajectories.controls == (Control(dimension="Scenario", kind="filter", default="high"),)
    assert [control.dimension for control in points.controls] == ["Time", "Period", "Scenario"]


def test_the_manifest_records_the_scales_only_where_there_are_some(scattered: Build) -> None:
    written = json.loads((scattered.path / "manifest.json").read_text())
    assert written["blicks"][0]["definition"]["plot"] == {
        "type": "scatter",
        "mapping": {
            "x": "GDP per capita",
            "y": "value",
            "color": "Region",
            "linetype": "Period",
            "along": "Time",
        },
        "scales": {"x": "log"},
    }
    assert "scales" not in written["blicks"][1]["definition"]["plot"]


def test_an_integer_column_on_x_counts_as_a_dimension(scattered: Build) -> None:
    integer_x = scattered.manifest.blicks[2]
    assert integer_x.status == "error"
    assert [problem.message for problem in integer_x.problems] == [
        "'Time' on x= is an integer column and so counts as a dimension; add measures=[\"Time\"]"
    ]


def test_a_manifest_with_scales_validates_against_its_schema(scattered: Build) -> None:
    text = (scattered.path / "manifest.json").read_text()
    jsonschema.validate(json.loads(text), Manifest.model_json_schema(mode="serialization"))
    assert json.loads(Manifest.model_validate_json(text).model_dump_json()) == json.loads(text)


def test_a_plot_without_scales_is_recorded_without_a_scales_key(project: Path) -> None:
    plot = PlotDefinition(type="line", mapping={"x": "year", "y": "value"})
    assert plot.model_dump(mode="json") == {"type": "line", "mapping": {"x": "year", "y": "value"}}
    assert PlotDefinition.model_validate(plot.model_dump()).scales == {}
    assert '"scales"' not in (bk.build(project, ["runs/a"]).path / "manifest.json").read_text()


def test_the_scales_are_part_of_the_build_id(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/stocks.py": SCATTERS})
    run = make_run(tmp_path / "run")
    first = bk.build(root, [run]).manifest.build.id
    stocks = root / "blicks" / "stocks.py"
    stocks.write_text(stocks.read_text().replace(', x_scale="log"', ""))
    assert bk.build(root, [run]).manifest.build.id != first
