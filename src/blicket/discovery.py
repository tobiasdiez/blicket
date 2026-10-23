"""Discovery: glob a project's Blick modules, import them, and hand the records to assembly.

Problems in project files never raise; they become problems in the registry. Only a missing or
invalid ``[tool.blicket]`` raises, as ``ConfigError``.
"""

import contextlib
import glob
import importlib
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from blicket import definitions
from blicket.assembly import assemble
from blicket.config import PYPROJECT, Config, load_config
from blicket.errors import SKIPPED, DefinitionError, Kind, Problem, Source, display_path
from blicket.model import Registry
from blicket.tracebacks import in_project, locate, project_traceback, raised_at


@dataclass(frozen=True)
class _Target:
    """A Blick file and the module name it is imported under."""

    path: Path
    relative: str
    name: str


def discover(project: str | os.PathLike[str], config: Config | None = None) -> Registry:
    """Import the Blick modules of the project at ``project`` and assemble its registry.

    ``config`` defaults to the project's ``[tool.blicket]``; loading it raises
    ``blicket.ConfigError`` if it is missing or invalid. Everything else that can go wrong in
    project files is recorded in the registry.

    The project root is put first on ``sys.path`` and left there, since transformations may import
    project modules after discovery has returned. Modules under the root, and modules sharing a
    top-level package with a Blick module, are dropped from ``sys.modules`` first, so every Blick
    module executes and records its definitions afresh. One project per process is the supported
    case: a second project re-imports only those modules, so a helper package of the same name
    in both projects is the first project's. What Blick modules print goes to stderr, so stdout
    stays free for blicket's own output.
    """
    root = Path(project).resolve()
    if config is None:
        config = load_config(root)

    targets, problems = _targets(root, config.blicks)
    if not targets and not problems:
        problems.append(_no_match(root, config.blicks))

    _put_first_on_path(root)
    _purge_modules(root, targets)
    for target in targets:
        definitions.reset_module(target.name)

    records: list[definitions.ModuleRecord] = []
    with (
        definitions.importing(target.name for target in targets),
        contextlib.redirect_stdout(sys.stderr),
    ):
        for target in targets:
            problem = _import(target, root)
            if problem is not None:
                problems.append(problem)
            else:
                record = definitions.module_record(target.name)
                records.append(record or definitions.ModuleRecord(target.name, target.path))
    # A package __init__.py that raises fails every Blick module under it alike.
    unique = list({(p.kind, p.source, p.message): p for p in problems}.values())
    return assemble(records, unique, config=config, root=root)


# ---------------------------------------------------------------------------------------------
# Files and module names


def _bad_filename(path: Path, message: str) -> Problem:
    return Problem(kind=Kind.BAD_FILENAME, message=f"{message}\n{SKIPPED}", source=Source(path))


def _targets(root: Path, patterns: Sequence[str]) -> tuple[list[_Target], list[Problem]]:
    """The Blick files matched by ``patterns``, sorted by POSIX path, with their module names.

    Hidden directories and files (``.venv`` among them) never match a wildcard, and files whose
    stem starts with ``_`` are helpers, except ``__init__.py``.
    """
    found: set[Path] = set()
    for pattern in patterns:
        for match in glob.glob(pattern, root_dir=root, recursive=True):
            path = Path(os.path.normpath(root / match))
            if path.suffix == ".py" and path.is_file():
                found.add(path)

    targets: list[_Target] = []
    problems: list[Problem] = []
    for path in sorted(found, key=lambda p: p.as_posix()):
        if not path.is_relative_to(root):
            message = (
                f"lies outside the project root {root}; Blick modules must be inside it, fix "
                "the globs in [tool.blicket] blicks"
            )
            problems.append(_bad_filename(path, message))
            continue
        if path.stem.startswith("_") and path.stem != "__init__":
            continue
        relative = path.relative_to(root)
        parts = [*relative.parent.parts, path.stem]
        if parts[-1] == "__init__":
            parts.pop()
        problem = _module_name_problem(parts)
        if problem is not None:
            problems.append(_bad_filename(path, problem))
            continue
        targets.append(_Target(path, relative.as_posix(), ".".join(parts)))
    return targets, problems


def _module_name_problem(parts: Sequence[str]) -> str | None:
    if not parts:
        return (
            "the project root's __init__.py cannot be a Blick module; move the Blicks into a module"
        )
    for part in parts:
        if not part.isidentifier():
            suggestion = part.replace("-", "_").replace(" ", "_").replace(".", "_")
            hint = (
                f"rename it to {suggestion!r}"
                if suggestion.isidentifier()
                else "use letters, digits and underscores, not starting with a digit"
            )
            return (
                f"{part!r} is not a valid Python module name, so the file cannot be imported; "
                f"{hint}"
            )
    return None


def _no_match(root: Path, patterns: Sequence[str]) -> Problem:
    default = " (the default)" if list(patterns) == Config().blicks else ""
    return Problem(
        kind=Kind.NO_MATCH,
        message=(
            f"blicks = {json.dumps(list(patterns))}{default} matches no files in this project "
            "(files starting with '_' are helpers); add a Blick module or fix blicks in "
            "[tool.blicket]"
        ),
        source=Source(root / PYPROJECT),
    )


# ---------------------------------------------------------------------------------------------
# Importing


def _put_first_on_path(root: Path) -> None:
    entry = str(root)
    sys.path[:] = [item for item in sys.path if item != entry]
    sys.path.insert(0, entry)
    importlib.invalidate_caches()


def _locations(module: ModuleType) -> list[str]:
    """The file of a module, or the directories of a namespace package."""
    file = getattr(module, "__file__", None)
    return [file] if isinstance(file, str) else [str(p) for p in getattr(module, "__path__", [])]


def _purge_modules(root: Path, targets: Sequence[_Target]) -> None:
    """Drop modules so that the Blick modules and the project's own code execute afresh.

    Dropped are modules whose file lies under the project root outside its hidden directories,
    and modules sharing a top-level package with a Blick module, so that the ``blicks`` package
    of another project discovered earlier does not stand in for this one's. The standard library
    and blicket itself are never dropped.
    """
    top_levels = {target.name.partition(".")[0] for target in targets}
    top_levels -= {*sys.stdlib_module_names, "blicket"}

    def stale(name: str, module: ModuleType) -> bool:
        if name == "blicket" or name.startswith("blicket."):
            return False
        file = getattr(module, "__file__", None)
        inside = isinstance(file, str) and in_project(file, root)
        return inside or name.partition(".")[0] in top_levels

    # Decide first, delete afterwards: a namespace package's path needs its parent in place.
    for name in [name for name, module in list(sys.modules.items()) if stale(name, module)]:
        del sys.modules[name]


def _import(target: _Target, root: Path) -> Problem | None:
    try:
        module = importlib.import_module(target.name)
    except (Exception, SystemExit) as error:
        return _clash(target, root) or _execution_error(target, root, error)
    file = getattr(module, "__file__", None)
    if file is None or Path(file).resolve() != target.path.resolve():
        return _clash(target, root) or _clash_error(target, root, module, Source(target.path))
    return None


def _execution_error(target: _Target, root: Path, error: BaseException) -> Problem:
    """An exception raised while a Blick module executed, located in the project's files.

    The location is the line of the Blick module that led to the error, with the place it was
    raised added when that is another project file. When no frame lies in the Blick module (its
    package's ``__init__.py`` raised, say), it is the last frame in the project.
    """
    source = locate(error, root, prefer=target.path) or Source(target.path)
    first = str(error) if isinstance(error, DefinitionError) else f"{type(error).__name__}: {error}"
    lines = [first + raised_at(error, root, source)]
    if isinstance(error, ModuleNotFoundError) and error.name:
        lines.append(f"is {error.name!r} installed in {sys.prefix}?")
    # The location already says all a traceback of these two would: it is blicket's own frames.
    plain = isinstance(error, DefinitionError | SyntaxError)
    return Problem(
        kind=error.kind if isinstance(error, DefinitionError) else Kind.IMPORT,
        message="\n".join([*lines, SKIPPED]),
        source=source,
        module=target.name,
        traceback=None if plain else project_traceback(error, root),
    )


def _clash(target: _Target, root: Path) -> Problem | None:
    """A name clash on a parent package of ``target``, resolved outside the project.

    It is located at the project's shadowed directory, so it is reported once for all modules.
    """
    parts = target.name.split(".")
    for depth in range(1, len(parts)):
        parent = sys.modules.get(".".join(parts[:depth]))
        if parent is None:
            continue
        locations = _locations(parent)
        if locations and not any(Path(item).resolve().is_relative_to(root) for item in locations):
            return _clash_error(target, root, parent, Source(root.joinpath(*parts[:depth])))
    return None


def _clash_error(target: _Target, root: Path, other: ModuleType, source: Source) -> Problem:
    locations = [Path(location).resolve() for location in _locations(other)]
    shown = ", ".join(display_path(location, root) for location in locations) or "no file"
    top = target.name.partition(".")[0]
    if locations and all(location.is_relative_to(root) for location in locations):
        advice = (
            "a package and a module of the same name cannot both be imported; rename one of them"
        )
    else:
        advice = (
            f"something of that name elsewhere on sys.path shadows the project's, and a directory "
            f"without __init__.py loses against a regular package; add {top}/__init__.py or "
            f"rename the {top} directory"
        )
    return Problem(
        kind=Kind.NAME_CLASH,
        message=f"{other.__name__} resolves to {shown}, not to this project; {advice}\n{SKIPPED}",
        source=source,
        module=target.name,
    )
