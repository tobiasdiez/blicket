"""The build: load a run, run every Blick's transformation, write a build directory.

``build`` composes the steps: ``prepare`` reads the config and checks everything that can fail
before the run is loaded, ``discover`` imports the Blicks, ``load`` loads the run, and ``write``
runs the transformations and writes the build directory. ``blicket dev`` takes the steps one by
one, since it keeps the run.

A build directory holds ``manifest.json``, ``blicks/<id>.parquet`` for every Blick that built,
and a copy of the viewer. It is assembled in a temporary directory next to its destination and
renamed to its id at the end, so it appears complete or not at all. An existing directory of the
same id keeps its manifest and tables; only its copy of the viewer is replaced when it is not the
installed one.
"""

import contextlib
import hashlib
import importlib.metadata
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from blicket import loader, manifest, tables, viewer
from blicket.config import PYPROJECT, Config, load_config
from blicket.discovery import discover
from blicket.errors import NOWHERE, BlicketError, ConfigError, Kind, Problem
from blicket.loader import DEFAULT_LOADER_MODULE, RunSelection
from blicket.manifest import BuildConfig, BuildInfo, Manifest, Repository, Run, RunInfo
from blicket.model import Blick, BlickEntry, Registry


class NothingToBuild(BlicketError):
    """No Blick of the project can be built, so no build is written; ``registry`` says why."""

    def __init__(self, registry: Registry) -> None:
        super().__init__("no Blick can be built, so no build was written")
        self.registry = registry


@dataclass(frozen=True)
class Build:
    """A build directory, the manifest this build computed, and the project root it was built from.

    ``existed`` when a build of the same id was there already. That directory keeps its manifest
    and tables, so its manifest may hold another run id, paths, branch, dirty flag and timings
    than ``manifest``, which has this build's, with its sources relative to the root as written.
    ``viewer`` is ``True`` when the installed viewer was copied into the directory, ``False``
    when its copy was current already.
    """

    path: Path
    manifest: Manifest
    existed: bool
    root: Path
    viewer: bool


@dataclass(frozen=True)
class Prepared:
    """What a build needs before it loads the run: the project root and config, the viewer, the
    loader target, the run paths and where the build goes.

    ``paths`` are the run paths resolved; ``shown`` are the same as the manifest records them,
    relative to the root inside it. ``default_out`` says that ``destination`` is
    ``.blicket/build`` in the project.
    """

    root: Path
    config: Config
    site: Path
    target: str
    paths: tuple[Path, ...]
    shown: tuple[str, ...]
    destination: Path
    default_out: bool


@dataclass(frozen=True)
class LoadedRun:
    """A run the loader returned: the run object, its ``RunInfo``, and the loader's wall time in
    milliseconds."""

    run: Any
    info: RunInfo
    loader_ms: float


def prepare(
    project: str | os.PathLike[str],
    paths: Sequence[str | os.PathLike[str]],
    out: str | os.PathLike[str] | None = None,
) -> Prepared:
    """Read what a build of the run at ``paths`` with the project at ``project`` needs.

    Raises ``ConfigError`` when the config is missing or invalid or there is no loader, and
    ``BlicketError`` when ``BLICKET_VIEWER`` names no viewer, there is none, or a run path does
    not exist.
    """
    root = Path(project).resolve()
    config = load_config(root)
    site = viewer.find()
    target = config.loader
    if target is None:
        if not (root / f"{DEFAULT_LOADER_MODULE}.py").is_file():
            raise ConfigError(
                f"{root}: no loader; add {DEFAULT_LOADER_MODULE}.py with a load_run(selection) "
                f'next to {PYPROJECT}, or set loader = "package.module:function" in '
                "[tool.blicket]"
            )
        target = f"{DEFAULT_LOADER_MODULE}:load_run"
    resolved: list[Path] = []
    shown: list[str] = []
    for given in paths:
        path = Path(given).resolve()
        if not path.exists():
            raise BlicketError(f"run path {os.fspath(given)} does not exist")
        resolved.append(path)
        shown.append(path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path))
    destination = Path(out).resolve() if out is not None else root / ".blicket" / "build"
    return Prepared(
        root=root,
        config=config,
        site=site,
        target=target,
        paths=tuple(resolved),
        shown=tuple(shown),
        destination=destination,
        default_out=out is None,
    )


def load(prepared: Prepared) -> LoadedRun:
    """Load the run with the project's loader; raises ``LoaderError`` when the loader fails."""
    selection = RunSelection(paths=prepared.paths)
    run, info, loader_ms = loader.load(prepared.target, selection, prepared.root)
    return LoadedRun(run, info, loader_ms)


def write(prepared: Prepared, registry: Registry, loaded: LoadedRun) -> Build:
    """Run every Blick of ``registry`` on the loaded run and write the build directory.

    A registry without a buildable Blick gives a build of its failed Blicks and problems. Raises
    ``BlicketError`` when the build cannot be written, before a build directory exists, or when
    the viewer of an existing build cannot be replaced.
    """
    root, destination = prepared.root, prepared.destination
    repository, problems = _repository(root)
    temporary = destination / f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        if prepared.default_out:  # .blicket/ ignores itself, so builds never make the tree dirty
            (root / ".blicket").mkdir(exist_ok=True)
            if not (ignore := root / ".blicket" / ".gitignore").exists():
                ignore.write_text("*\n")
        temporary.mkdir(parents=True)  # with the permissions the umask gives
    except OSError as error:
        reason = error.strerror or str(error)
        raise BlicketError(f"cannot write the build to {destination}: {reason}") from error
    try:
        entries = [_run_blick(b, loaded.run, temporary, root) for b in registry.blicks.values()]
        # In the order of their definitions, as blicket list shows them.
        entries = sorted([*entries, *registry.failed], key=lambda e: e.source or NOWHERE)
        built = Manifest(
            blicket=importlib.metadata.version("blicket"),
            created_at=datetime.now(UTC),
            build=BuildInfo(
                id="", incomplete=registry.incomplete, loader_ms=round(loaded.loader_ms, 1)
            ),
            config=BuildConfig(tolerance=prepared.config.tolerance),
            run=Run(**loaded.info.model_dump(), paths=list(prepared.shown)),
            repository=repository,
            groups=tuple(registry.groups.values()),
            blicks=tuple(entries),
            problems=(*registry.problems, *problems),
        )
        build_info = built.build.model_copy(update={"id": built.content_id(root)})
        built = built.model_copy(update={"build": build_info})
        text = built.model_dump_json(indent=2, context={"root": root})
        (temporary / manifest.MANIFEST).write_text(text + "\n")
        final = destination / built.build.id
        existed = final.exists()
        if existed:
            manifest.read(final)  # raises when the existing build is damaged
        copied = viewer.copy(prepared.site, final if existed else temporary)
        if not existed:
            temporary.rename(final)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return Build(final, Manifest.model_validate_json(text), existed, root, copied)


def build(
    project: str | os.PathLike[str],
    paths: Sequence[str | os.PathLike[str]],
    *,
    out: str | os.PathLike[str] | None = None,
) -> Build:
    """Build the run at ``paths`` with the Blicks of the project at ``project``.

    The build directory goes into ``out``, by default ``<project>/.blicket/build``, with the
    viewer ``viewer.find`` returns. Problems with Blicks and files are recorded in the manifest.
    Raises ``NothingToBuild`` when no Blick can be built, and another ``BlicketError`` when the
    config, ``BLICKET_VIEWER``, a run path or the loader fails or the build cannot be written,
    all before a build directory exists, or when the viewer of an existing build cannot be
    replaced. What the loader and the transformations print goes to stderr.
    """
    prepared = prepare(project, paths, out)
    registry = discover(prepared.root, prepared.config)
    if not registry.blicks:
        raise NothingToBuild(registry)
    with contextlib.redirect_stdout(sys.stderr):
        return write(prepared, registry, load(prepared))


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _repository(root: Path) -> tuple[Repository | None, list[Problem]]:
    """The commit, branch and dirty flag of the repository holding ``root``, or a warning."""
    try:
        commit = _git(root, "rev-parse", "--verify", "-q", "HEAD")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        dirty = bool(_git(root, "status", "--porcelain"))
    except OSError as error:
        reason = f"git cannot run ({error.strerror})"
    except subprocess.CalledProcessError as error:
        # --verify -q exits 1 in a repository without commits, 128 outside a repository.
        if error.returncode == 1:
            reason = "the git repository has no commit yet"
        else:
            reason = "the project is not in a git repository"
    else:
        # A detached HEAD has no branch; git prints "HEAD" for it.
        branch_name = None if branch == "HEAD" else branch
        return Repository(commit=commit, branch=branch_name, dirty=dirty), []
    message = f"{reason}; the build records no commit"
    return None, [Problem(kind=Kind.REPOSITORY, severity="warning", message=message)]


def _run_blick(blick: Blick, run: object, directory: Path, root: Path) -> BlickEntry:
    """Build one Blick into ``directory``: its table as Parquet, and its manifest entry."""
    start = time.perf_counter()
    checked = tables.compute(blick, run, root)
    data: str | None = None
    digest: str | None = None
    rows: int | None = None
    if checked.frame is not None:
        data = f"blicks/{blick.id}.parquet"
        path = directory / data
        path.parent.mkdir(parents=True, exist_ok=True)
        checked.frame.write_parquet(path)
        digest = f"parquet-sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        rows = checked.frame.height
    return blick.entry(
        problems=checked.problems,
        data=data,
        hash=digest,
        rows=rows,
        columns=checked.schema,
        timing_ms=round((time.perf_counter() - start) * 1000, 1),
        skipped=checked.skipped,
    )
