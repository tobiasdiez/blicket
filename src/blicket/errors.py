"""Problems and errors, shared by every part of blicket. Depends on nothing else in blicket."""

import difflib
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, SerializationInfo, field_serializer


class Kind:
    """The known problem kinds. ``Problem.kind`` is an open string, so other kinds may occur."""

    IMPORT = "import"
    NAME_CLASH = "name_clash"
    BAD_FILENAME = "bad_filename"
    NO_MATCH = "no_match"
    NO_BLICKS = "no_blicks"
    INVALID_DEFINITION = "invalid_definition"
    DUPLICATE_ID = "duplicate_id"
    ALIAS_COLLISION = "alias_collision"
    GROUP = "group"
    TRANSFORMATION = "transformation"
    TABLE = "table"
    REPOSITORY = "repository"


class DefinitionError(ValueError):
    """A Blick, group or plot definition is invalid.

    The plot spec checks, ``bk.slug``, a bare ``@bk.blick`` and a ``bk.group()`` without a name
    raise it while a Blick module executes. Outside discovery, an invalid ``@bk.blick``,
    ``bk.register`` or ``bk.group`` raises it too; during discovery those are recorded instead,
    so that one bad Blick does not hide the others. ``kind`` is the kind discovery reports.
    """

    def __init__(self, message: str, *, kind: str = Kind.INVALID_DEFINITION) -> None:
        super().__init__(message)
        self.kind = kind


class BlicketError(Exception):
    """Something blicket cannot work around, said in one line; ``traceback`` is the traceback of
    project code that raised it, if any."""

    def __init__(self, message: str, traceback: str | None = None) -> None:
        super().__init__(message)
        self.traceback = traceback


class ConfigError(BlicketError):
    """The project or its ``[tool.blicket]`` section cannot be found or is invalid."""


class LoaderError(BlicketError):
    """The project's loader cannot be imported, raised, or returned no ``(run, RunInfo)``."""


SKIPPED = "the Blicks in this file were skipped"


def did_you_mean(word: str, options: Iterable[str]) -> str | None:
    """The option closest to a misspelled ``word``, if any is close."""
    close = difflib.get_close_matches(word, list(options), n=1)
    return close[0] if close else None


def os_reason(error: OSError) -> str:
    """What an ``OSError`` says, with the file it concerns when it names one."""
    return f"{error.strerror}: {error.filename}" if error.filename else str(error)


def display_path(path: str | Path, root: Path | None) -> str:
    """``path`` relative to ``root`` in POSIX form when it lies inside, else as it is."""
    path = Path(path)
    if root is not None and path.is_relative_to(root):
        return path.relative_to(root).as_posix()
    return path.as_posix()


class Source(BaseModel):
    """A place in a file; ``line`` is ``None`` for the file as a whole. Sorts by file, then line.

    Dumped with ``context={"root": root}``, the file is written relative to ``root`` when it lies
    inside, so that a build directory holds no path of the machine it was built on.
    """

    model_config = ConfigDict(frozen=True)

    file: Path
    line: int | None = None

    def __init__(self, file: Path, line: int | None = None) -> None:
        super().__init__(file=file, line=line)

    def __lt__(self, other: Source) -> bool:
        return (self.file, self.line or 0) < (other.file, other.line or 0)

    @field_serializer("file")
    def _relative(self, file: Path, info: SerializationInfo) -> str:
        return display_path(file, (info.context or {}).get("root"))

    def display(self, root: Path | None = None) -> str:
        path = display_path(self.file, root)
        return f"{path}:{self.line}" if self.line is not None else path


NOWHERE = Source(Path())


class Problem(BaseModel):
    """Something wrong with a project: an error, or a warning that blicket reports and goes on.

    ``message`` may hold several lines: what is wrong, then what follows from it. ``ids`` names
    the Blicks concerned; ``traceback`` is set for exceptions raised by project code.
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    severity: Literal["error", "warning"] = "error"
    source: Source | None = None
    module: str | None = None
    ids: tuple[str, ...] = ()
    message: str
    traceback: str | None = None

    @property
    def sort_key(self) -> Source:
        return self.source or NOWHERE

    def location(self, root: Path | None = None) -> str | None:
        """``file:line`` or the file alone, relative to ``root`` when inside it."""
        return self.source.display(root) if self.source else None
