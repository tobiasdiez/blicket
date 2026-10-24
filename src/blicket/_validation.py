"""Checks of the arguments of ``bk.blick``, ``bk.register`` and ``bk.group``.

Every check normalises one value or raises ``_Invalid`` with all that is wrong with it; the
collectors at the end turn those into lists of problems, each saying what to do.
"""

import annotationlib
import inspect
import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, TypedDict, get_args

from blicket.errors import did_you_mean
from blicket.plots import PlotSpec
from blicket.schema import ControlKind

SEGMENT_RULE = "lowercase letters, digits, '_' and '-', starting with a letter or digit"
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]*")
# Ids become file and directory names; these names are reserved on Windows.
_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_JSON_HINT = "use strings, numbers, booleans, lists and dicts"


class _Invalid(ValueError):
    """A value that cannot be used; ``problems`` say why and what to do."""

    def __init__(self, *problems: str) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class BlickOptions(TypedDict, total=False):
    """The options of ``@bk.blick`` and ``bk.register``."""

    id: str
    title: str
    description: str
    unit: str
    plot: PlotSpec
    independent_y: bool
    controls: Mapping[str, ControlKind]
    defaults: Mapping[str, Any]
    tolerance: float
    aliases: Iterable[str]
    tags: Iterable[str]
    dims: Iterable[str]
    measures: Iterable[str]
    order: Mapping[str, Iterable[Any]]


@dataclass(frozen=True)
class CheckedOptions:
    """The valid options of a definition as ``Blick`` fields, empty where not given or invalid."""

    id: str | None = None
    title: str | None = None
    description: str | None = None
    unit: str | None = None
    plot: PlotSpec | None = None
    independent_y: bool = False
    controls: Mapping[str, ControlKind] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)
    tolerance: float | None = None
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    dims: tuple[str, ...] | None = None
    measures: tuple[str, ...] | None = None
    order: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)


def valid_segment(text: str) -> bool:
    """Whether ``text`` can be one segment of an id or group name."""
    return bool(_SEGMENT.fullmatch(text)) and text not in _RESERVED


def reserved_name(what: str, value: str, segment: str) -> str:
    """The message for a name with a segment that is a reserved file name on Windows."""
    return f"{what} {value!r} has the segment {segment!r}, a reserved name on Windows"


def default_title(name: str) -> str:
    """``steel_by_process`` → ``Steel by process``."""
    words = " ".join(part for part in re.split(r"[_-]+", name) if part)
    return words[:1].upper() + words[1:]


def _shown(value: object) -> str:
    """A value for a message; callables by name, since their repr holds a memory address."""
    if callable(value):
        return f"the callable {getattr(value, '__qualname__', type(value).__name__)}"
    return repr(value)


# ---------------------------------------------------------------------------------------------
# Checks of single values; each raises _Invalid


def reserved_segment(value: str) -> str | None:
    """The first segment of ``value`` that is a reserved file name on Windows, if any."""
    return next((s for s in value.split("/") if s in _RESERVED), None)


def _id(value: object, what: str = "id") -> str:
    if isinstance(value, str):
        segments = value.split("/")
        if len(segments) >= 2 and all(valid_segment(s) for s in segments):
            return value
        if (reserved := reserved_segment(value)) is not None:
            raise _Invalid(reserved_name(what, value, reserved))
    raise _Invalid(
        f"{what} {_shown(value)} is not valid: lowercase letters, digits, '_' and '-' in two or "
        "more '/'-separated segments"
    )


def _group_name(value: object) -> str:
    if isinstance(value, str):
        if all(valid_segment(s) for s in value.split("/")):
            return value
        if (reserved := reserved_segment(value)) is not None:
            raise _Invalid(reserved_name("group name", value, reserved))
    raise _Invalid(
        f"group name {_shown(value)} is not valid: one or more segments separated by '/', each "
        f"made of {SEGMENT_RULE}"
    )


def _strings(value: object, what: str) -> tuple[str, ...]:
    """A collection of non-empty strings. A bare string is rejected: ``tags="mfa"`` is a typo."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise _Invalid(f"{what} must be a list of strings, got {_shown(value)}")
    items = tuple(value)
    bad = [_shown(item) for item in items if not isinstance(item, str) or not item]
    if bad:
        raise _Invalid(f"{what} must be a list of non-empty strings, got {', '.join(bad)} in it")
    return items


def _title(value: object, what: str = "title") -> str:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid(f"{what} must be a non-empty string, got {_shown(value)}")
    return value


def _transform(value: object, what: str) -> None:
    if not callable(value):
        raise _Invalid(f"{what} must be a function of the run, got {_shown(value)}")
    try:
        # A name bound only under TYPE_CHECKING stays a ForwardRef instead of raising.
        signature = inspect.signature(value, annotation_format=annotationlib.Format.FORWARDREF)
    except ValueError:  # some builtins, such as str, have no signature; nothing to check
        return
    try:
        signature.bind(None)
    except TypeError:
        raise _Invalid(
            f"{what} must take exactly one positional parameter, the run; "
            f"its signature is {signature}"
        ) from None


def _json_issues(value: object, where: str) -> Iterator[str]:
    """Every part of ``value`` that cannot be written as JSON."""
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            yield f"{where} is {value!r}, a number that JSON cannot hold; {_JSON_HINT}"
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield from _json_issues(item, f"{where}[{index}]")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield from _json_issues(item, f"{where}[{key!r}]")
            else:
                yield f"{where} has the key {key!r}; keys must be strings"
    else:
        yield f"{where} is of type {type(value).__name__}, which JSON cannot hold; {_JSON_HINT}"


def _json_mapping(value: object, what: str, shape: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        raise _Invalid(f"{what} must be a dict of {shape}, got {_shown(value)}")
    if issues := list(_json_issues(value, what)):
        raise _Invalid(*issues)
    return value


def _description(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"description must be a string, got {_shown(value)}")
    return value


def _plot(value: object) -> PlotSpec:
    if not isinstance(value, PlotSpec):
        raise _Invalid(
            f"plot must be a plot spec such as bk.plots.line(x=..., y=...), got {_shown(value)}"
        )
    return value


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise _Invalid(f"independent_y must be True or False, got {_shown(value)}")
    return value


def _controls(value: object) -> dict[str, ControlKind]:
    if not isinstance(value, Mapping):
        raise _Invalid(
            f"controls must be a dict of column to 'filter' or 'split', got {_shown(value)}"
        )
    kinds = get_args(ControlKind)
    issues = [
        f"controls[{column!r}] is {_shown(kind)}; use a column name and 'filter' or 'split'"
        for column, kind in value.items()
        if not isinstance(column, str) or kind not in kinds
    ]
    if issues:
        raise _Invalid(*issues)
    return dict(value)


def _tolerance(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool) and 0 < value < 1:
        return float(value)
    raise _Invalid(f"tolerance must be a positive number below 1, got {_shown(value)}")


def _aliases(value: object) -> tuple[str, ...]:
    aliases = _strings(value, "aliases")
    issues: list[str] = []
    for alias in aliases:
        _collect(issues, _id, alias, "alias")
    if len(set(aliases)) != len(aliases):
        issues.append(f"aliases lists an id twice: {list(aliases)}")
    if issues:
        raise _Invalid(*issues)
    return aliases


def _order(value: object) -> dict[str, tuple[Any, ...]]:
    order = _json_mapping(value, "order", "column to a list of values")
    issues = [
        f"order[{key!r}] must be a list of values in display order"
        for key, values in order.items()
        if not isinstance(values, list | tuple)
    ]
    if issues:
        raise _Invalid(*issues)
    return {key: tuple(values) for key, values in order.items()}


# One check per option of BlickOptions; test_definitions holds them to the same keys.
_CHECKS: dict[str, Callable[[object], Any]] = {
    "id": _id,
    "title": _title,
    "description": _description,
    "unit": lambda value: _title(value, "unit"),
    "plot": _plot,
    "independent_y": _flag,
    "controls": _controls,
    "defaults": lambda value: dict(_json_mapping(value, "defaults", "column to value")),
    "tolerance": _tolerance,
    "aliases": _aliases,
    "tags": lambda value: tuple(dict.fromkeys(_strings(value, "tags"))),
    "dims": lambda value: _strings(value, "dims"),
    "measures": lambda value: _strings(value, "measures"),
    "order": _order,
}


# ---------------------------------------------------------------------------------------------
# Collectors


def _collect[T](problems: list[str], check: Callable[..., T], *args: object) -> T | None:
    """Run ``check``; on ``_Invalid`` add its problems and return ``None``."""
    try:
        return check(*args)
    except _Invalid as error:
        problems.extend(error.problems)
        return None


def validate_definition(
    options: Mapping[str, object], transform: object, transform_label: str
) -> tuple[CheckedOptions, list[str]]:
    """Check the options of a definition and its transform, and collect every problem.

    An option passed as ``None`` counts as not given. ``transform`` is ``None`` when missing.
    """
    values: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in options.items():
        if key not in _CHECKS:
            problems.append(_unknown_option(key))
        elif value is not None:
            values[key] = _collect(problems, _CHECKS[key], value)
    if options.get("plot") is None:
        problems.append("plot= is missing; pass a plot spec such as bk.plots.line(x=..., y=...)")
    if transform is None:
        problems.append("transform= is missing; pass a function that takes the run")
    else:
        _collect(problems, _transform, transform, transform_label)
    checked = {key: value for key, value in values.items() if value is not None}
    return CheckedOptions(**checked), problems


def _unknown_option(key: str) -> str:
    if key == "transform":
        return (
            "transform= belongs to bk.register(); with @bk.blick the decorated function is the "
            "transform"
        )
    close = did_you_mean(key, _CHECKS)
    hint = f"did you mean {close}=?" if close else f"valid: {', '.join(_CHECKS)}"
    return f"unknown option {key}=; {hint}"


@dataclass
class GroupArguments:
    """The checked arguments of ``bk.group()``; ``name`` is ``None`` when it is unusable."""

    name: str | None
    title: str | None = None
    tags: tuple[str, ...] = ()
    problems: list[str] = field(default_factory=list)


def validate_group(name: object, title: object = None, tags: object = ()) -> GroupArguments:
    """Check the arguments of ``bk.group()``, or a group name derived from a module name."""
    problems: list[str] = []
    checked_name = _collect(problems, _group_name, name)
    checked_title = None if title is None else _collect(problems, _title, title, "the group title")
    checked_tags = _collect(problems, _strings, tags, "tags") or ()
    return GroupArguments(checked_name, checked_title, tuple(dict.fromkeys(checked_tags)), problems)
