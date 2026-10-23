"""Problems and errors, shared by every part of blicket. Depends on nothing else in blicket."""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple


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


class ConfigError(Exception):
    """The project or its ``[tool.blicket]`` section cannot be found or is invalid."""


SKIPPED = "the Blicks in this file were skipped"


def did_you_mean(word: str, options: Iterable[str]) -> str | None:
    """The option closest to a misspelled ``word``, if any is close."""
    close = difflib.get_close_matches(word, list(options), n=1)
    return close[0] if close else None


def display_path(path: str | Path, root: Path | None) -> str:
    """``path`` relative to ``root`` in POSIX form when it lies inside, else as it is."""
    path = Path(path)
    if root is not None and path.is_relative_to(root):
        return path.relative_to(root).as_posix()
    return path.as_posix()


class Source(NamedTuple):
    """A place in a file; ``line`` 0 stands for the file as a whole. Sorts by file, then line."""

    file: Path
    line: int = 0

    def display(self, root: Path | None = None) -> str:
        path = display_path(self.file, root)
        return f"{path}:{self.line}" if self.line else path

    def to_json(self, root: Path | None = None) -> dict[str, Any]:
        """``{"file": ..., "line": ...}``, the line ``null`` for the file as a whole."""
        return {"file": display_path(self.file, root), "line": self.line or None}


NOWHERE = Source(Path(), 0)


@dataclass(frozen=True, kw_only=True)
class Problem:
    """Something wrong with a project: an error, or a warning that blicket reports and goes on.

    ``message`` may hold several lines: what is wrong, then what follows from it. ``ids`` names
    the Blicks concerned; ``traceback`` is set for exceptions raised by project code.
    """

    kind: str
    message: str
    severity: Literal["error", "warning"] = "error"
    source: Source | None = None
    module: str | None = None
    ids: tuple[str, ...] = ()
    traceback: str | None = None

    @property
    def sort_key(self) -> Source:
        return self.source or NOWHERE

    def location(self, root: Path | None = None) -> str | None:
        """``file:line`` or the file alone, relative to ``root`` when inside it."""
        return self.source.display(root) if self.source else None

    def to_json(self, root: Path | None = None) -> dict[str, Any]:
        """The JSON form, as ``blicket list --json`` prints it."""
        return {
            "kind": self.kind,
            "severity": self.severity,
            "source": self.source.to_json(root) if self.source else None,
            "module": self.module,
            "ids": list(self.ids),
            "message": self.message,
            "traceback": self.traceback,
        }
