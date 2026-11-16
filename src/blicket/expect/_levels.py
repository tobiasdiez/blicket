"""Levels: what a failed expectation is, and which one a unit has."""

from typing import Literal

type Level = Literal["off", "warn", "error"]
LEVELS: tuple[str, ...] = ("off", "warn", "error")
DEFAULT_LEVEL: Level = "error"


def level_problem(value: object) -> str | None:
    """Why ``value`` is no level, or ``None`` when it is one."""
    if isinstance(value, str) and value in LEVELS:
        return None
    return f'level must be "off", "warn" or "error", got {value!r}'


def resolve_level(own: Level | None, group: Level | None, project: Level) -> Level:
    """The level of a unit: its own, else its group's, else the project's."""
    if own is not None:
        return own
    return group if group is not None else project
