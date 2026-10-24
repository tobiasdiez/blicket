"""The headless build: entries and files, build ids, repository state, the manifest's schema."""

import json
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import pytest

import blicket as bk
from blicket import builder, manifest
from blicket.builder import NothingToBuild
from blicket.errors import BlicketError
from blicket.manifest import BuildConfig, Manifest
from tests.support import VALUES, commit_all, git, line_of, make_build_project, make_run, one_blick

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
    ]
    ok = built.manifest.blicks[0]
    assert (ok.data, ok.rows) == ("blicks/views/from_polars.parquet", 3)
    assert ok.hash is not None
    assert ok.hash.startswith("parquet-sha256:")
    files = sorted(p.relative_to(built.path).as_posix() for p in built.path.rglob("*.*"))
    assert files == [
        "blicks/views/from_pandas.parquet",
        "blicks/views/from_polars.parquet",
        "manifest.json",
    ]
    assert built.manifest.config == BuildConfig(tolerance=1e-5, digits=6)
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
    load = builder.load
    monkeypatch.setattr(builder, "load", lambda *args: (*load(*args)[:2], 1234.5))
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
        file.write("digits = 8\n")
    built = bk.build(root, [run]).manifest
    assert len({*ids, built.build.id}) == 4
    assert (built.config.digits, built.build.incomplete) == (8, False)


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
