"""Where the viewer comes from, and the copy of it that ``blicket build`` puts into a build."""

import importlib.resources
from pathlib import Path

import pytest

import blicket as bk
from blicket import viewer
from tests.support import VALUES, make_build_project, make_run, make_viewer


def test_build_copies_the_viewer_and_refreshes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    run = make_run(tmp_path / "run")
    monkeypatch.setenv(viewer.VIEWER_ENV, str(make_viewer(tmp_path / "one", "one")))
    built = bk.build(root, [run])
    assert built.viewer is True
    files = sorted(p.relative_to(built.path).as_posix() for p in built.path.rglob("*.*"))
    assert files == ["_nuxt/one.js", "blicks/a/values.parquet", "index.html", "manifest.json"]
    version, *copied = (built.path / viewer.MARKER).read_text().splitlines()
    assert copied == ["_nuxt/one.js", "index.html"]
    assert version == viewer.version(tmp_path / "one", copied)
    assert bk.build(root, [run]).viewer is False  # current already

    stored = (built.path / "manifest.json").read_bytes()
    (built.path / "report.md").write_text("added later")
    monkeypatch.setenv(viewer.VIEWER_ENV, str(make_viewer(tmp_path / "two", "two")))
    again = bk.build(root, [run])
    assert (again.existed, again.viewer, again.manifest.build.id) == (
        True,
        True,
        built.manifest.build.id,
    )
    files = sorted(p.relative_to(built.path).as_posix() for p in built.path.rglob("*.*"))
    # Exactly the old viewer's files are replaced; what else the directory holds stays.
    assert files == [
        "_nuxt/two.js",
        "blicks/a/values.parquet",
        "index.html",
        "manifest.json",
        "report.md",
    ]
    assert (built.path / "manifest.json").read_bytes() == stored


def test_the_bundled_viewer_is_found_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # bring back the real lookup, which the autouse fixture replaces
    monkeypatch.delenv(viewer.VIEWER_ENV, raising=False)
    package = tmp_path / "blicket"
    package.mkdir()
    monkeypatch.setattr(importlib.resources, "files", lambda name: package)
    with pytest.raises(bk.BlicketError, match="no viewer found: install a blicket release"):
        viewer.find()
    make_viewer(package / "_viewer")
    assert viewer.find() == package / "_viewer"


def test_the_environment_comes_before_the_bundled_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = make_viewer(tmp_path / "bundled")
    monkeypatch.setattr(viewer, "_bundled", lambda: bundled)
    monkeypatch.delenv(viewer.VIEWER_ENV)
    assert viewer.find() == bundled
    named = make_viewer(tmp_path / "named")
    monkeypatch.setenv(viewer.VIEWER_ENV, str(named))
    assert viewer.find() == named
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv(viewer.VIEWER_ENV, str(tmp_path / "empty"))
    with pytest.raises(bk.BlicketError, match=r"BLICKET_VIEWER names .*empty, which has no index"):
        viewer.find()
    monkeypatch.setenv(viewer.VIEWER_ENV, str(tmp_path / "nothere"))
    with pytest.raises(bk.BlicketError, match=r"BLICKET_VIEWER names .*nothere, which does not"):
        viewer.find()


def test_an_unreadable_viewer_is_an_error(tmp_path: Path) -> None:
    source = make_viewer(tmp_path / "source")
    (source / "index.html").chmod(0)
    target = tmp_path / "build"
    target.mkdir()
    with pytest.raises(bk.BlicketError, match="cannot copy the viewer into"):
        viewer.copy(source, target)
