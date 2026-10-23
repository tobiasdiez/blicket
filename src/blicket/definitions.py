"""The definition API (``bk.group``, ``@bk.blick``, ``bk.register``, ``bk.slug``) and its records.

The API does not build Blicks directly. It appends to the record of the Blick module a call is
attributed to; ``assembly`` turns the records into a registry once all modules have been
imported, because only then are the group, the default ids and the default titles known. So
``bk.group()`` may stand anywhere in a module, and a module that runs again, in a second discovery
for instance, simply gets a fresh record.

During discovery, invalid definitions are recorded, so that one bad Blick does not hide the
others. Outside discovery, in a notebook or a test, they raise ``DefinitionError`` at once.
"""

import dataclasses
import inspect
import re
import unicodedata
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, Unpack, overload

from blicket._validation import (
    BlickOptions,
    CheckedOptions,
    GroupArguments,
    reserved_name,
    reserved_segment,
    valid_segment,
    validate_definition,
    validate_group,
)
from blicket.errors import DefinitionError, Kind, Source
from blicket.model import Transform

__all__ = ["blick", "group", "register", "slug"]


@dataclass
class GroupCall:
    """One ``bk.group()`` call with its checked arguments."""

    arguments: GroupArguments
    source: Source


@dataclass
class Definition:
    """One ``@bk.blick`` or ``bk.register`` call, checked, before its group is known.

    ``given_id`` is the id as passed, valid or not. ``problems`` leave out whether an id can be
    derived from the function name; ``id_problem`` says that.
    """

    given_id: object
    function_name: str | None
    options: CheckedOptions
    transform: object
    problems: list[str]
    source: Source

    @property
    def name(self) -> str:
        """The id if there is one, else the function's name, else the id as given."""
        given = "(no id)" if self.given_id is None else repr(self.given_id)
        return self.options.id or self.function_name or given

    @property
    def id_problem(self) -> str | None:
        """Why no id can be derived when none was given, or ``None``."""
        if self.given_id is not None:
            return None
        if self.function_name is None:
            return "pass id=; there is no function name to derive one from"
        if (reserved := reserved_segment(self.function_name)) is not None:
            return reserved_name("the function name", self.function_name, reserved) + "; pass id="
        if not valid_segment(self.function_name):
            return f"the function name {self.function_name!r} cannot be an id segment; pass id="
        return None

    def blick_id(self, group: str) -> str | None:
        """The given id if valid, else the id derived from the group and the function name."""
        if self.given_id is not None or self.id_problem is not None:
            return self.options.id
        return f"{group}/{self.function_name}"


@dataclass
class ModuleRecord:
    """What one execution of a Blick module defined."""

    name: str
    file: Path | None = None
    group_calls: list[GroupCall] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)


# Process-wide, keyed by module name, so a module imported before discovery is not lost and a
# second project in the same process starts from fresh records.
_records: dict[str, ModuleRecord] = {}
# The Blick modules discovery is importing; empty outside discovery.
_importing: frozenset[str] = frozenset()


def module_record(name: str) -> ModuleRecord | None:
    """The record of the module called ``name``, if it defined anything."""
    return _records.get(name)


def reset_module(name: str) -> None:
    """Forget what the module called ``name`` defined, before it executes again."""
    _records.pop(name, None)


@contextmanager
def importing(names: Iterable[str]) -> Generator[None]:
    """Record definitions for the nearest of these modules on the stack while active."""
    global _importing
    previous = _importing
    _importing = frozenset(names)
    try:
        yield
    finally:
        _importing = previous


def _attributed_frame() -> FrameType:
    """The frame of the Blick module a definition belongs to.

    During discovery that is the innermost frame on the stack whose module is being discovered,
    so helpers in ``blicks/_helpers.py`` or in the project's package are transparent, and a
    Blick module importing another one keeps its own definitions. Otherwise, and as a fallback,
    it is the immediate caller of the blicket API.
    """
    caller: FrameType | None = None
    frame = inspect.currentframe()
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if caller is None and name != "blicket" and not name.startswith("blicket."):
            caller = frame
            if not _importing:
                break
        if caller is not None and name in _importing:
            return frame
        frame = frame.f_back
    assert caller is not None, "the API is always called from some frame outside blicket"
    return caller


def _record_for(frame: FrameType) -> ModuleRecord:
    name = frame.f_globals.get("__name__") or "__main__"
    record = _records.get(name)
    if record is None:
        file = frame.f_globals.get("__file__")
        record = ModuleRecord(name=name, file=Path(file).resolve() if file else None)
        _records[name] = record
    return record


def _source(frame: FrameType, function: object = None) -> Source:
    """The definition's location in the attributed module.

    A decorated function defined in that module points at its own definition; anything else,
    such as a ``bk.register`` call or a helper's function, points at the line of the module that
    led to the definition.
    """
    file = Path(frame.f_code.co_filename)
    code = getattr(function, "__code__", None)
    if code is not None and Path(code.co_filename) == file:
        return Source(file, code.co_firstlineno)
    return Source(file, frame.f_lineno or 0)


def _definition_failure(label: str, source: Source, problems: list[str]) -> DefinitionError:
    """The error raised outside discovery, worded as ``blicket list`` prints it."""
    lines = "".join(f"\n    {problem}" for problem in problems)
    return DefinitionError(f"{source.display()}  {label}{lines}")


def slug(text: str) -> str:
    """Turn arbitrary text into a valid id segment, for ids of generated Blick families.

    Lowercase, accents dropped, every run of other characters replaced by one ``-``.
    """
    ascii_text = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not result:
        raise DefinitionError(
            f"bk.slug({text!r}): cannot make an id segment of text without letters or digits"
        )
    if not valid_segment(result):
        raise DefinitionError(reserved_name(f"bk.slug({text!r}) gives", result, result))
    return result


def group(name: str = "", title: str | None = None, tags: Iterable[str] = ()) -> None:
    """Name the group of the calling Blick module and give it a title and tags.

    May stand anywhere in the module, once. Without it the group is named after the module file,
    or after the package for an ``__init__.py``. Several modules may contribute to one group.
    """
    if not name:
        raise DefinitionError(
            'bk.group() needs the group name first: bk.group("steel", title="...")',
            kind=Kind.GROUP,
        )
    frame = _attributed_frame()
    source = _source(frame)
    arguments = validate_group(name, title, tags)
    if arguments.problems and not _importing:
        raise _definition_failure("bk.group()", source, arguments.problems)
    _record_for(frame).group_calls.append(GroupCall(arguments, source))


def _define(
    frame: FrameType,
    source: Source,
    options: Mapping[str, object],
    transform: object,
    transform_label: str,
    function_name: str | None = None,
) -> None:
    """Check a definition; record it during discovery, else raise if it is invalid."""
    checked, problems = validate_definition(options, transform, transform_label)
    if (
        checked.description is None
        and inspect.isfunction(transform)
        and (doc := inspect.getdoc(transform))
    ):
        checked = dataclasses.replace(checked, description=doc)
    definition = Definition(options.get("id"), function_name, checked, transform, problems, source)
    if not _importing:
        all_problems = [*filter(None, [definition.id_problem]), *problems]
        if all_problems:
            raise _definition_failure(f"Blick {definition.name}", source, all_problems)
    _record_for(frame).definitions.append(definition)


@overload
def blick[F: Callable[..., Any]](**options: Unpack[BlickOptions]) -> Callable[[F], F]: ...
@overload
def blick(function: Callable[..., Any], /) -> NoReturn: ...
def blick(function: object = None, /, **options: Any) -> Any:
    """Declare the decorated function, which takes the run, as a Blick.

    The id defaults to ``<group>/<function name>`` and the title to the function name with
    spaces; the docstring becomes the description. The function is returned unchanged.
    """
    if function is not None:
        raise DefinitionError("use @bk.blick(plot=...), with parentheses")

    def decorate[F: Callable[..., Any]](function: F) -> F:
        frame = _attributed_frame()
        name = getattr(function, "__name__", None)
        label = f"the function {name}" if name else "the decorated callable"
        _define(frame, _source(frame, function), options, function, label, function_name=name)
        return function

    return decorate


def register(*, transform: Transform | None = None, **options: Unpack[BlickOptions]) -> None:
    """Declare a Blick from a transformation, for families generated in a loop.

    ``id`` is required, because a lambda or a ``functools.partial`` has no usable name. The
    title defaults to the last id segment with spaces.
    """
    frame = _attributed_frame()
    _define(frame, _source(frame), options, transform, "transform")
