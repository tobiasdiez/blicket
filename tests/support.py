"""Helpers shared by the tests."""

import textwrap
from pathlib import Path

import blicket as bk

PROJECTS = Path(__file__).parent / "projects"


def make_project(
    tmp_path: Path, files: dict[str, str], config: str = "", name: str = "project"
) -> Path:
    """Write a project under ``tmp_path``: ``[tool.blicket]`` plus ``config`` lines, and files."""
    root = tmp_path / name
    root.mkdir()
    (root / "pyproject.toml").write_text(f"[tool.blicket]\n{config}")
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
    return root


def discover_clean(root: Path) -> bk.Registry:
    """Discover a project and assert that it has no problems at all."""
    found = bk.discover(root)
    assert found.problems == ()
    assert found.failed == ()
    return found


def one_blick(blick_id: str) -> str:
    """The source of a Blick module that registers one Blick with the given id."""
    return (
        "import blicket as bk\n"
        f"bk.register(id={blick_id!r}, plot=bk.plots.line(x='a', y='b'), transform=lambda r: r)\n"
    )
