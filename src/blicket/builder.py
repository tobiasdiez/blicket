"""The headless build: load a run, run every Blick's transformation, write a build directory.

A build directory holds ``manifest.json`` and ``blicks/<id>.parquet`` for every Blick that built.
It is assembled in a temporary directory next to its destination and renamed to its id at the
end, so it appears complete or not at all; an existing directory of the same id is left alone.
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

from blicket import manifest, tables
from blicket.config import PYPROJECT, load_config
from blicket.discovery import discover
from blicket.errors import NOWHERE, BlicketError, ConfigError, Kind, Problem
from blicket.loader import DEFAULT_LOADER_MODULE, RunSelection, load
from blicket.manifest import BuildConfig, BuildInfo, Manifest, Repository, Run
from blicket.model import Blick, BlickEntry, Registry
from blicket.tracebacks import locate, project_traceback, raised_at


class NothingToBuild(BlicketError):
    """No Blick of the project can be built, so no build is written; ``registry`` says why."""

    def __init__(self, registry: Registry) -> None:
        super().__init__("no Blick can be built, so no build was written")
        self.registry = registry


@dataclass(frozen=True)
class Build:
    """A build directory, the manifest this build computed, and the project root it was built from.

    ``existed`` when a build of the same id was there already. That directory is left as it was,
    so its manifest may hold another run id, paths, branch, dirty flag and timings than
    ``manifest``, which has this build's, with its sources relative to the root as written.
    """

    path: Path
    manifest: Manifest
    existed: bool
    root: Path


def build(
    project: str | os.PathLike[str],
    paths: Sequence[str | os.PathLike[str]],
    *,
    out: str | os.PathLike[str] | None = None,
) -> Build:
    """Build the run at ``paths`` with the Blicks of the project at ``project``.

    The build directory goes into ``out``, by default ``<project>/.blicket/build``. Problems with
    Blicks and files are recorded in the manifest. Raises ``NothingToBuild`` when no Blick can be
    built, and another ``BlicketError`` when the config, a run path or the loader fails or the
    build cannot be written, all before a build directory exists. What the loader and the
    transformations print goes to stderr.
    """
    root = Path(project).resolve()
    config = load_config(root)
    target = config.loader
    if target is None:
        if not (root / f"{DEFAULT_LOADER_MODULE}.py").is_file():
            raise ConfigError(
                f"{root}: no loader; add {DEFAULT_LOADER_MODULE}.py with a load_run(selection) "
                f'next to {PYPROJECT}, or set loader = "package.module:function" in '
                "[tool.blicket]"
            )
        target = f"{DEFAULT_LOADER_MODULE}:load_run"
    registry = discover(root, config)
    if not registry.blicks:
        raise NothingToBuild(registry)
    resolved: list[Path] = []
    shown: list[str] = []
    for given in paths:
        path = Path(given).resolve()
        if not path.exists():
            raise BlicketError(f"run path {os.fspath(given)} does not exist")
        resolved.append(path)
        shown.append(path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path))

    with contextlib.redirect_stdout(sys.stderr):
        run, info, loader_ms = load(target, RunSelection(paths=tuple(resolved)), root)
        repository, problems = _repository(root)
        destination = Path(out).resolve() if out is not None else root / ".blicket" / "build"
        temporary = destination / f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
        try:
            if out is None:  # .blicket/ ignores itself, so builds never make the tree dirty
                (root / ".blicket").mkdir(exist_ok=True)
                if not (ignore := root / ".blicket" / ".gitignore").exists():
                    ignore.write_text("*\n")
            temporary.mkdir(parents=True)  # with the permissions the umask gives
        except OSError as error:
            reason = error.strerror or str(error)
            raise BlicketError(f"cannot write the build to {destination}: {reason}") from error
        try:
            entries = [_run_blick(b, run, temporary, root) for b in registry.blicks.values()]
            # In the order of their definitions, as blicket list shows them.
            entries = sorted([*entries, *registry.failed], key=lambda e: e.source or NOWHERE)
            built = Manifest(
                blicket=importlib.metadata.version("blicket"),
                created_at=datetime.now(UTC),
                build=BuildInfo(
                    id="", incomplete=registry.incomplete, loader_ms=round(loader_ms, 1)
                ),
                config=BuildConfig(tolerance=config.tolerance),
                run=Run(**info.model_dump(), paths=shown),
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
            else:
                temporary.rename(final)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
    return Build(final, Manifest.model_validate_json(text), existed, root)


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


def _checked(blick: Blick, run: object, root: Path) -> tables.Checked:
    """Run the transformation, convert what it returned, and check the table.

    Nothing raised in these steps escapes; it becomes a problem located in the project's code.
    """
    action = "transformation"
    try:
        value = blick.transform(run)
        action = f"converting the returned {type(value).__name__}"
        frame, index_dropped = tables.to_polars(value)
        action = "checking the table"
        return tables.check(frame, blick, index_dropped)
    except tables.TableError as error:
        return tables.Checked.failed(blick.problem(Kind.TRANSFORMATION, str(error)))
    except (Exception, SystemExit) as error:
        prefer = blick.source.file if blick.source else None
        message = f"{action} raised {type(error).__name__}: {error}"
        problem = blick.problem(
            Kind.TRANSFORMATION,
            message + raised_at(error, root, blick.source),
            source=locate(error, root, prefer),
            traceback=project_traceback(error, root),
        )
        return tables.Checked.failed(problem)


def _run_blick(blick: Blick, run: object, directory: Path, root: Path) -> BlickEntry:
    """Build one Blick into ``directory``: its table as Parquet, and its manifest entry."""
    start = time.perf_counter()
    checked = _checked(blick, run, root)
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
    )
