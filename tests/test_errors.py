import typing
from pathlib import Path

import blicket as bk
from blicket.errors import Problem, Source, did_you_mean


def test_sources_display_and_json(tmp_path: Path) -> None:
    inside = Source(tmp_path / "blicks" / "a.py", 4)
    assert inside.display(tmp_path) == "blicks/a.py:4"
    assert inside.display() == f"{inside.file.as_posix()}:4"
    assert Source(tmp_path / "a.py").to_json(tmp_path) == {"file": "a.py", "line": None}
    problem = Problem(kind="import", message="boom", source=Source(Path("/elsewhere/x.py"), 3))
    assert problem.to_json(tmp_path)["source"] == {"file": "/elsewhere/x.py", "line": 3}
    assert Problem(kind="x", message="m").to_json()["source"] is None


def test_sources_sort_by_file_then_line() -> None:
    sources = [Source(Path("b.py"), 1), Source(Path("a.py"), 9), Source(Path("a.py"), 2)]
    assert sorted(sources) == [sources[2], sources[1], sources[0]]


def test_did_you_mean() -> None:
    assert did_you_mean("blick", ["blicks", "loader"]) == "blicks"
    assert did_you_mean("zzz", ["blicks", "loader"]) is None


def test_blick_type_hints_resolve() -> None:
    assert typing.get_type_hints(bk.Blick)["plot"] is bk.PlotSpec
