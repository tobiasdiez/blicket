"""The store: what a push copies, with which permissions, and looking builds up by id."""

import errno
import json
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

import blicket as bk
from blicket import store
from blicket.comparison import compare_builds, write
from blicket.errors import BlicketError
from blicket.store import Store
from tests.support import VALUES, commit_all, git, make_build_project, make_run

RAISING = (
    VALUES + '\n\n@bk.blick(plot=bk.plots.line(x="year", y="value"))\n'
    'def missing(run):\n    return run["missing"]\n'
)


@pytest.fixture
def built(tmp_path: Path) -> bk.Build:
    """A build of a project with one Blick, in ``.blicket/build``."""
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    return bk.build(root, [make_run(tmp_path / "run")])


@pytest.fixture
def umask_022() -> Iterator[None]:
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def files(directory: Path) -> dict[str, str]:
    """The files and directories under ``directory`` with their permission bits."""
    return {
        path.relative_to(directory).as_posix(): oct(stat.S_IMODE(path.stat().st_mode))
        for path in sorted(directory.rglob("*"))
    }


def test_push_copies_the_manifest_tables_and_comparisons_with_the_umask_modes(
    built: bk.Build, tmp_path: Path, umask_022: None
) -> None:
    write(compare_builds(built.path, built.path), built.path, built.path)
    (built.path / "compare" / ".tmp-1-abc").mkdir()  # a write in progress
    (built.path / "compare" / ".tmp-1-abc" / "comparison.json").write_text("{}")
    for path in built.path.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    pushed = Store(tmp_path / "store").push(built.path)
    build_id = built.manifest.build.id
    final = tmp_path / "store" / "builds" / build_id
    assert pushed == store.Pushed(build_id, final, False, (build_id,))
    # Not the viewer.
    assert files(pushed.path) == {
        "blicks": "0o755",
        "blicks/a": "0o755",
        "blicks/a/values.parquet": "0o644",
        "compare": "0o755",
        f"compare/{build_id}": "0o755",
        f"compare/{build_id}/comparison.json": "0o644",
        "compare/index.json": "0o644",
        "manifest.json": "0o644",
    }
    assert (pushed.path / "manifest.json").read_bytes() == (
        built.path / "manifest.json"
    ).read_bytes()
    assert sorted(os.listdir(tmp_path / "store" / "builds")) == [".gitignore", build_id]


@pytest.fixture
def compared(tmp_path: Path) -> tuple[Path, Path]:
    """Two builds of a project with one Blick, the second with a changed value, and the
    comparison of the second with the first written into it."""
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    before = bk.build(root, [make_run(tmp_path / "a")]).path
    after = bk.build(root, [make_run(tmp_path / "b", "1 2 3.3")]).path
    write(compare_builds(before, after), before, after)
    return before, after


def test_push_copies_the_baseline_tables_of_a_comparison(
    compared: tuple[Path, Path], tmp_path: Path
) -> None:
    before, after = compared
    pushed = Store(tmp_path / "store").push(after)
    assert pushed.comparisons == (before.name,)
    copy = pushed.path / "compare" / before.name / "blicks" / "a" / "values.parquet"
    assert copy.read_bytes() == (before / "blicks" / "a" / "values.parquet").read_bytes()


def test_a_file_linked_from_outside_the_comparisons_is_refused(
    compared: tuple[Path, Path], tmp_path: Path
) -> None:
    before, after = compared
    table = after / "compare" / before.name / "blicks" / "a" / "values.parquet"
    table.unlink()
    (tmp_path / "secret.parquet").write_text("secret")
    table.symlink_to(tmp_path / "secret.parquet")
    with pytest.raises(BlicketError, match=r"values\.parquet is not a regular file inside "):
        Store(tmp_path / "store").push(after)
    assert not (tmp_path / "store").exists()


def test_comparisons_written_after_the_first_push_stay_out(
    compared: tuple[Path, Path], tmp_path: Path
) -> None:
    _, after = compared
    shutil.rmtree(after / "compare")
    the_store = Store(tmp_path / "store")
    first = the_store.push(after)
    write(compare_builds(after, after), after, after)
    assert the_store.push(after).existed
    assert not (first.path / "compare").exists()


def test_list_of_a_store_not_created_yet_is_empty(tmp_path: Path) -> None:
    assert Store(tmp_path / "store").list() == store.Listing((), 0, ())


def test_list_reads_the_builds_in_the_order_of_their_ids(
    compared: tuple[Path, Path], tmp_path: Path
) -> None:
    the_store = Store(tmp_path / "store")
    pushed = [the_store.push(build) for build in compared]
    listing = the_store.list()
    assert [(s.id, s.path) for s in listing.builds] == sorted((p.id, p.path) for p in pushed)
    assert [s.manifest.build.id for s in listing.builds] == [s.id for s in listing.builds]


def unreadable(the_store: Store, name: str, text: str) -> None:
    (the_store.builds / name).mkdir(parents=True)
    (the_store.builds / name / "manifest.json").write_text(text)


def test_list_counts_and_skips_builds_of_another_spec(tmp_path: Path) -> None:
    the_store = Store(tmp_path / "store")
    unreadable(the_store, "0" * 16, '{"spec": "0.1"}')
    assert the_store.list() == store.Listing((), 1, ())


def test_list_describes_and_skips_damaged_builds(tmp_path: Path) -> None:
    the_store = Store(tmp_path / "store")
    unreadable(the_store, "1" * 16, "not json")
    assert the_store.list().damaged == (
        f"build directory {the_store.builds / ('1' * 16)} has no readable manifest.json (not "
        "valid JSON); delete it and rebuild",
    )


def test_list_skips_names_that_are_no_build_ids(tmp_path: Path) -> None:
    the_store = Store(tmp_path / "store")
    unreadable(the_store, ".tmp-1-abc", "not json")  # a push in progress
    assert the_store.list() == store.Listing((), 0, ())


def test_pushing_twice_is_a_no_op(built: bk.Build, tmp_path: Path) -> None:
    first = Store(tmp_path / "store").push(built.path)
    (first.path / "blicks" / "a" / "values.parquet").unlink()
    second = Store(tmp_path / "store").push(built.path)
    assert (second.path, second.existed) == (first.path, True)
    assert not (first.path / "blicks" / "a" / "values.parquet").exists()


def test_a_build_with_a_failed_blick_is_pushed_without_its_table(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": RAISING})
    built = bk.build(root, [make_run(tmp_path / "run")])
    pushed = Store(tmp_path / "store").push(built.path)
    assert sorted(files(pushed.path)) == [
        "blicks",
        "blicks/a",
        "blicks/a/values.parquet",
        "manifest.json",
    ]


def test_a_directory_of_the_id_without_a_manifest_is_an_error(
    built: bk.Build, tmp_path: Path
) -> None:
    partial = tmp_path / "store" / "builds" / built.manifest.build.id
    (partial / "blicks").mkdir(parents=True)
    with pytest.raises(BlicketError, match=r"holds no manifest\.json; delete it and push again$"):
        Store(tmp_path / "store").push(built.path)


def test_a_table_linked_from_outside_the_build_is_refused(built: bk.Build, tmp_path: Path) -> None:
    table = built.path / "blicks" / "a" / "values.parquet"
    table.unlink()
    (tmp_path / "secret.parquet").write_text("secret")
    table.symlink_to(tmp_path / "secret.parquet")
    with pytest.raises(BlicketError, match=r"values\.parquet is not a regular file inside "):
        Store(tmp_path / "store").push(built.path)
    assert not (tmp_path / "store").exists()


def test_a_missing_table_is_refused(built: bk.Build, tmp_path: Path) -> None:
    (built.path / "blicks" / "a" / "values.parquet").unlink()
    with pytest.raises(BlicketError, match=r"values\.parquet is missing; rebuild the run$"):
        Store(tmp_path / "store").push(built.path)
    assert not (tmp_path / "store").exists()


def test_a_build_id_of_another_shape_is_refused(built: bk.Build, tmp_path: Path) -> None:
    data = json.loads((built.path / "manifest.json").read_text())
    data["build"]["id"] = "٣" * 16  # digits, but not the hex digits of a build id
    (built.path / "manifest.json").write_text(json.dumps(data))
    with pytest.raises(BlicketError, match="has an invalid build id"):
        Store(tmp_path / "store").push(built.path)
    assert not (tmp_path / "store").exists()


def test_a_failed_copy_leaves_nothing_behind(
    built: bk.Build, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(source: Path, target: Path) -> None:
        raise OSError(errno.ENOSPC, "No space left on device", str(target))

    monkeypatch.setattr(store.shutil, "copyfile", full)
    with pytest.raises(BlicketError, match=r"cannot push build \w+ to .*: No space left on device"):
        Store(tmp_path / "store").push(built.path)
    assert os.listdir(tmp_path / "store" / "builds") == [".gitignore"]


def test_a_build_pushed_meanwhile_is_there_already(
    built: bk.Build, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "store" / "builds" / built.manifest.build.id
    copyfile = shutil.copyfile

    def copy_while_another_finishes(source: Path, target: Path) -> None:
        final.mkdir(parents=True, exist_ok=True)
        (final / "manifest.json").write_bytes((built.path / "manifest.json").read_bytes())
        copyfile(source, target)

    monkeypatch.setattr(store.shutil, "copyfile", copy_while_another_finishes)
    pushed = Store(tmp_path / "store").push(built.path)
    assert (pushed.path, pushed.existed) == (final, True)
    assert sorted(os.listdir(final.parent)) == [".gitignore", final.name]


def test_path_finds_a_pushed_build(built: bk.Build, tmp_path: Path) -> None:
    the_store = Store(tmp_path / "store")
    pushed = the_store.push(built.path)
    assert the_store.path(pushed.id) == pushed.path


@pytest.mark.parametrize("name", ["0123456789abcdef", ".tmp-1-abc", "../builds/x", "٣" * 16])
def test_path_finds_nothing_but_builds(tmp_path: Path, name: str) -> None:
    for directory in (".tmp-1-abc", "x", "٣" * 16):
        (tmp_path / "store" / "builds" / directory).mkdir(parents=True)
        (tmp_path / "store" / "builds" / directory / "manifest.json").write_text("{}")
    assert Store(tmp_path / "store").path(name) is None


def test_the_store_stays_out_of_git(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES})
    built = bk.build(root, [make_run(tmp_path / "run")], out=tmp_path / "builds")
    commit_all(root)
    Store(root / ".blicket" / "store").push(built.path)
    assert git(root, "status", "--porcelain") == ""


def test_a_store_in_a_tracked_directory_hides_only_its_builds(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES, "data/notes.txt": "notes"})
    built = bk.build(root, [make_run(tmp_path / "run")], out=tmp_path / "builds")
    commit_all(root)
    Store(root / "data").push(built.path)
    (root / "data" / "more.txt").write_text("more")
    assert git(root, "status", "--porcelain") == "?? data/more.txt\n"
