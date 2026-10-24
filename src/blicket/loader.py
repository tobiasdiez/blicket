"""The loader protocol: the run selection a loader receives, and the call of the project's loader.

The loader is ``load_run`` in ``blicketconf.py`` next to the project's ``pyproject.toml``, like
pytest's ``conftest.py``, unless ``[tool.blicket] loader`` names another function. The ``RunInfo``
it returns is part of the manifest."""

import hashlib
import importlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from blicket.errors import LoaderError
from blicket.manifest import RunInfo
from blicket.tracebacks import project_traceback, raised_at

DEFAULT_LOADER_MODULE = "blicketconf"


@dataclass(frozen=True)
class RunSelection:
    """What a loader is asked to load: the run paths from the command line, resolved.

    The loader decides what several paths mean, for example several model runs collected into
    one run.
    """

    paths: tuple[Path, ...]

    @property
    def path(self) -> Path:
        """The one run path, for a loader that loads a single run."""
        if len(self.paths) != 1:
            raise ValueError(f"this loader takes one run path, got {len(self.paths)}")
        return self.paths[0]


def fingerprint(*paths: str | os.PathLike[str]) -> str:
    """A sha256 hex digest over the files at ``paths``, for ``RunInfo.fingerprint``.

    Covers each file's path relative to the path given, its size and its content; directories
    are walked in sorted order. A run copied to another place keeps its fingerprint. Raises
    ``ValueError`` when there are no files.
    """
    files: list[tuple[Path, Path]] = []
    for base in map(Path, paths):
        found = sorted(p for p in base.rglob("*") if p.is_file()) if base.is_dir() else [base]
        files += [(base, file) for file in found]
    if not files:
        shown = ", ".join(str(path) for path in paths) or "no paths"
        raise ValueError(f"no files to fingerprint in {shown}")
    digest = hashlib.sha256()
    for base, file in files:
        with file.open("rb") as stream:
            content = hashlib.file_digest(stream, "sha256").hexdigest()
        name = file.relative_to(base).as_posix()
        digest.update(f"{name}\0{file.stat().st_size}\0{content}\0".encode())
    return digest.hexdigest()


def _resolve(target: str, root: Path) -> Callable[[RunSelection], Any]:
    """The function ``target`` names: a module path, a colon, attribute names joined by dots."""
    module_name, _, attribute = target.partition(":")
    try:
        found: Any = importlib.import_module(module_name)
    except (Exception, SystemExit) as error:
        message = f"loader {target} cannot be imported: {type(error).__name__}: {error}"
        if isinstance(error, ModuleNotFoundError) and f"{module_name}.".startswith(
            f"{error.name}."
        ):
            message += (
                f"; {root} is on sys.path, and a package under src/ must be installed in "
                "blicket's environment"
            )
        message += raised_at(error, root, None)
        raise LoaderError(message, project_traceback(error, root)) from error
    where = module_name
    for name in attribute.split("."):
        if not hasattr(found, name):
            raise LoaderError(f"loader {target}: {where} has no {name}")
        found, where = getattr(found, name), f"{where}.{name}"
    if not callable(found):
        kind = type(found).__name__
        article = "an" if kind[0] in "aeiou" else "a"
        raise LoaderError(f"loader {where} is not callable (it is {article} {kind})")
    return found


def _invalid_run_info(error: ValidationError) -> str:
    """One sentence per field of an invalid ``RunInfo``."""
    sentences = []
    for issue in error.errors():
        field = ".".join(map(str, issue["loc"]))
        sentence = {
            "missing": f"{field} is required"
            + ("; bk.fingerprint(path) computes one" if field == "fingerprint" else ""),
            "extra_forbidden": f"{field} is not a RunInfo field",
            "string_too_short": f"{field} must not be empty",
        }.get(issue["type"], f"{field}: {issue['msg']}")
        sentences.append(sentence)
    return "; ".join(sentences)


def load(target: str, selection: RunSelection, root: Path) -> tuple[Any, RunInfo, float]:
    """Import the loader ``target`` (``package.module:function``) and load ``selection``.

    Returns the run, its ``RunInfo`` and the wall time of importing and calling the loader in
    milliseconds. Raises ``LoaderError`` when the loader cannot be imported, raises, or returns
    something else than ``(run, RunInfo)``.
    """
    start = time.perf_counter()
    loader = _resolve(target, root)
    try:
        result = loader(selection)
    except (Exception, SystemExit) as error:
        if isinstance(error, ValidationError) and error.title == RunInfo.__name__:
            message = f"loader {target} built an invalid RunInfo: {_invalid_run_info(error)}"
        else:
            message = f"loader {target} raised {type(error).__name__}: {error}"
        message += raised_at(error, root, None)
        raise LoaderError(message, project_traceback(error, root)) from error
    elapsed = (time.perf_counter() - start) * 1000
    if not (isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], RunInfo)):
        shown = "None" if result is None else type(result).__name__
        if isinstance(result, tuple) and len(result) == 2:
            shown = f"a tuple whose second item is a {type(result[1]).__name__}, not a bk.RunInfo"
        raise LoaderError(f"loader {target} returned {shown}; return (run, bk.RunInfo(...))")
    return result[0], result[1], elapsed
