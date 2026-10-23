"""Helpers shared by the tests."""

import subprocess
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


# A loader for generated projects: the run is a directory with values.txt and, optionally,
# profile.txt; its fingerprint covers values.txt only.
LOADER = """
import blicket as bk

def load_run(selection):
    path = selection.paths[0]
    values = [float(v) for v in (path / "values.txt").read_text().split()]
    profile = path / "profile.txt"
    info = bk.RunInfo(
        id=path.name,
        profile=profile.read_text() if profile.exists() else "test",
        fingerprint=bk.fingerprint(path / "values.txt"),
    )
    return {"values": values}, info
"""


def make_build_project(tmp_path: Path, files: dict[str, str], config: str = "") -> Path:
    """A project whose loader is ``LOADER``, with ``files`` and ``config`` lines."""
    files = {"model_loader.py": LOADER, **files}
    return make_project(tmp_path, files, f'loader = "model_loader:load_run"\n{config}')


def make_run(directory: Path, values: str = "1 2 3", profile: str | None = None) -> Path:
    """A run directory for ``LOADER``."""
    directory.mkdir(parents=True)
    (directory / "values.txt").write_text(values)
    if profile is not None:
        (directory / "profile.txt").write_text(profile)
    return directory


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` with a fixed identity and return its output."""
    identity = ["-c", "user.name=blicket", "-c", "user.email=blicket@example.org"]
    command = ["git", *identity, *args]
    return subprocess.run(command, cwd=root, check=True, capture_output=True, text=True).stdout


def commit_all(root: Path) -> str:
    """Make ``root`` a git repository with everything committed; return the commit."""
    (root / ".gitignore").write_text("__pycache__/\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "all")
    return git(root, "rev-parse", "HEAD").strip()


def line_of(source: str, text: str) -> int:
    """The number of the first line of ``source`` that contains ``text``."""
    return next(i for i, line in enumerate(source.splitlines(), 1) if text in line)


# A Blick module with one Blick that builds from a run of LOADER.
VALUES = """\
import polars as pl

import blicket as bk


@bk.blick(plot=bk.plots.line(x="year", y="value"))
def values(run):
    return pl.DataFrame({"year": [2020, 2021, 2022], "value": run["values"]})
"""
