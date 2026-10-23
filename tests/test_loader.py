"""The loader protocol: finding and calling the project's loader, and run fingerprints."""

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

import blicket as bk
from blicket.errors import BlicketError, LoaderError
from tests.support import LOADER, make_build_project, make_project, make_run, one_blick


def failing_build(tmp_path: Path, loader: str, runs: int = 1) -> LoaderError:
    """The ``LoaderError`` of a build whose loader module is ``loader``; nothing is written."""
    files = {"blicks/a.py": one_blick("a/x"), "model_loader.py": loader}
    root = make_build_project(tmp_path, files)
    paths = [make_run(tmp_path / f"run{i}") for i in range(runs)]
    with pytest.raises(LoaderError) as info:
        bk.build(root, paths)
    assert not (root / ".blicket").exists()
    return info.value


def test_missing_loader_key(tmp_path: Path) -> None:
    root = make_project(tmp_path, {"blicks/a.py": one_blick("a/x")})
    with pytest.raises(bk.ConfigError, match=r'no loader in \[tool.blicket\]; add loader = "'):
        bk.build(root, [make_run(tmp_path / "run")])


def test_missing_run_path(tmp_path: Path) -> None:
    root = make_build_project(tmp_path, {"blicks/a.py": one_blick("a/x")})
    with pytest.raises(BlicketError, match=r"^run path nope does not exist$"):
        bk.build(root, ["nope"])


def test_raising_loader_is_located(tmp_path: Path) -> None:
    error = failing_build(tmp_path, "def load_run(selection):\n    raise RuntimeError('no run')\n")
    assert str(error) == (
        "loader model_loader:load_run raised RuntimeError: no run (raised at model_loader.py:2)"
    )
    assert error.traceback is not None
    # Trimmed to the project's frames: the first frame is the loader's.
    assert 'model_loader.py", line 2, in load_run' in error.traceback.splitlines()[1]


@pytest.mark.parametrize(
    ("loader", "message"),
    [
        (
            "import nothere\n",
            "cannot be imported: ModuleNotFoundError: No module named 'nothere' "
            "(raised at model_loader.py:1)",
        ),
        ("def other(selection): ...\n", "load_run: model_loader has no load_run"),
        ("load_run = 3\n", "loader model_loader.load_run is not callable (it is an int)"),
        ("def load_run(selection):\n    return None\n", "returned None; return (run, bk.RunInfo"),
        ("def load_run(selection):\n    return (1,)\n", "returned tuple; return"),
        (
            "def load_run(selection):\n    return 1, {}\n",
            "returned a tuple whose second item is a dict, not a bk.RunInfo",
        ),
        (
            "import blicket as bk\ndef load_run(selection):\n    return 1, bk.RunInfo(id='')\n",
            "built an invalid RunInfo: id must not be empty; fingerprint is required; "
            "bk.fingerprint(path) computes one",
        ),
        (
            "import blicket as bk\n"
            "def load_run(selection):\n"
            "    return 1, bk.RunInfo(id='r', fingerprint='f', nope=1)\n",
            "built an invalid RunInfo: nope is not a RunInfo field",
        ),
        (
            "import sys\ndef load_run(selection):\n    sys.exit(3)\n",
            "raised SystemExit: 3",
        ),
    ],
)
def test_loader_failures(tmp_path: Path, loader: str, message: str) -> None:
    assert message in str(failing_build(tmp_path, loader))


def test_missing_loader_package_points_at_sys_path(tmp_path: Path) -> None:
    files = {"blicks/a.py": one_blick("a/x")}
    root = make_project(tmp_path, files, 'loader = "mymodel.blicket:load_run"\n')
    with pytest.raises(LoaderError) as info:
        bk.build(root, [make_run(tmp_path / "run")])
    assert f"; {root} is on sys.path, and a package under src/ must be installed" in str(info.value)


def test_loader_may_be_a_dotted_attribute(tmp_path: Path) -> None:
    loader = LOADER.replace(
        "def load_run(selection):", "class Loader:\n  @staticmethod\n  def load(selection):"
    )
    files = {"blicks/a.py": one_blick("a/x"), "model_loader.py": loader}
    root = make_project(tmp_path, files, 'loader = "model_loader:Loader.load"\n')
    run = make_run(tmp_path / "run")
    assert bk.build(root, [run]).manifest.run.id == "run"
    (root / "pyproject.toml").write_text('[tool.blicket]\nloader = "model_loader:Loader.nope"\n')
    with pytest.raises(LoaderError, match=r"model_loader\.Loader has no nope$"):
        bk.build(root, [run])


def test_selection_path_is_the_single_path(tmp_path: Path) -> None:
    assert bk.RunSelection(paths=(tmp_path,)).path == tmp_path
    loader = "def load_run(selection):\n    return selection.path\n"
    error = failing_build(tmp_path, loader, runs=2)
    assert "raised ValueError: this loader takes one run path, got 2" in str(error)


@pytest.mark.parametrize("empty", ["id", "profile", "fingerprint"])
def test_run_info_fields_are_not_empty(empty: str) -> None:
    with pytest.raises(ValidationError):
        bk.RunInfo(**{"id": "r", "profile": "p", "fingerprint": "f", empty: ""})


def test_fingerprint(tmp_path: Path) -> None:
    run = make_run(tmp_path / "cluster" / "run")
    (run / "sub").mkdir()
    (run / "sub" / "data.bin").write_bytes(b"\0\1")
    first = bk.fingerprint(run)
    assert first == bk.fingerprint(run)
    assert len(first) == 64
    copy = shutil.copytree(run, tmp_path / "laptop" / "run")
    assert bk.fingerprint(copy) == first
    (copy / "sub" / "data.bin").write_bytes(b"\0\2")
    assert bk.fingerprint(copy) != first
    (copy / "sub" / "data.bin").rename(copy / "sub" / "other.bin")
    assert bk.fingerprint(copy) not in {first, bk.fingerprint(run)}
    assert bk.fingerprint(run / "values.txt") != bk.fingerprint(copy / "values.txt", copy / "sub")


def test_fingerprint_of_nothing_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files to fingerprint"):
        bk.fingerprint(tmp_path)
    with pytest.raises(ValueError, match="no files to fingerprint"):
        bk.fingerprint()
