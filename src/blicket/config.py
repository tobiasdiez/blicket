"""The ``[tool.blicket]`` section of a project's ``pyproject.toml`` and the project root lookup."""

import math
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from blicket.errors import ConfigError, did_you_mean

PYPROJECT = "pyproject.toml"
MAX_DIGITS = 17  # a double has at most 17 significant decimal digits

# Messages for values of the wrong type, in place of pydantic's.
_WRONG_TYPE = {
    "blicks": "blicks must be a list of glob strings, got {value!r}",
    "loader": 'loader must be a string "package.module:function", got {value!r}',
    "store": "store must be a directory path, got {value!r}",
    "tolerance": "tolerance must be a number, got {value!r}",
    "digits": "digits must be a whole number, got {value!r}",
}


def check_tolerance(tolerance: float, digits: int) -> str | None:
    """Return why the positive ``tolerance`` is unusable with ``digits`` digits, or ``None``.

    A tolerance below ``10 ** (1 - digits)`` is finer than ``digits`` significant digits can
    express.
    """
    floor = 10.0 ** (1 - digits)
    # The relative slack keeps 1e-5 with digits = 6 valid despite floating-point rounding.
    if tolerance >= floor * (1 - 1e-9):
        return None
    needed = math.ceil(1 - math.log10(tolerance) - 1e-9)
    fix = f"use tolerance >= {floor:g}"
    if needed <= MAX_DIGITS:
        fix += f" or raise digits (now {digits}) to {needed} in [tool.blicket]"
    return f"tolerance {tolerance:g} is finer than {digits} significant digits can express; {fix}"


class Config(BaseModel):
    """The ``[tool.blicket]`` section. Unknown keys are rejected so that typos fail loudly."""

    # strict: no "6" for a number, no 6.0 for a whole number
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    blicks: list[str] = Field(
        default_factory=lambda: ["blicks/**/*.py"],
        description="Globs relative to the project root that select the Blick modules.",
    )
    loader: str | None = Field(
        default=None,
        pattern=r"^\w+(\.\w+)*:\w+(\.\w+)*$",
        description='Import path of the function that loads a run, as "package.module:function".',
    )
    store: str = Field(
        default=".blicket/store", description="Directory of the store, relative to the project."
    )
    tolerance: float = Field(
        default=1e-5,
        gt=0,
        allow_inf_nan=False,
        description="Relative tolerance below which a value counts as unchanged.",
    )
    digits: int = Field(default=6, description="Significant digits kept when values are rounded.")

    @field_validator("digits")
    @classmethod
    def _digits_in_range(cls, digits: int) -> int:
        if not 1 <= digits <= MAX_DIGITS:
            raise ValueError(f"digits must be between 1 and {MAX_DIGITS}, got {digits}")
        return digits

    @model_validator(mode="after")
    def _tolerance_fits_digits(self) -> Config:
        problem = check_tolerance(self.tolerance, self.digits)
        if problem is not None:
            raise ValueError(problem)
        return self


def _read_pyproject(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: invalid TOML: {error}") from error


def _blicket_section(data: dict[str, Any]) -> dict[str, Any] | None:
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    section = tool.get("blicket")
    return section if isinstance(section, dict) else None


def _describe(error: ValidationError, section: dict[str, Any]) -> list[str]:
    """The validation problems in the words of ``[tool.blicket]``, without pydantic's prefixes."""
    keys = list(Config.model_fields)
    problems: list[str] = []
    for issue in error.errors():
        key = str(issue["loc"][0]) if issue["loc"] else ""
        if issue["type"] == "extra_forbidden":
            close = did_you_mean(key, keys)
            hint = f"; did you mean {close!r}? Valid" if close else "; valid"
            problem = f"unknown key {key!r} in [tool.blicket]{hint} keys: {', '.join(keys)}"
        elif issue["type"] in {"greater_than", "finite_number"}:
            problem = f"{key} must be a positive number, got {section.get(key)!r}"
        elif issue["type"] == "value_error":
            problem = str(issue.get("ctx", {}).get("error", issue["msg"]))
        elif issue["type"] == "string_pattern_mismatch":
            problem = f'loader must be "package.module:function", got {section.get(key)!r}'
        else:
            problem = _WRONG_TYPE[key].format(value=section.get(key))
        if problem not in problems:
            problems.append(problem)
    return problems


def find_project_root(start: str | Path | None = None) -> Path:
    """Return the directory of the nearest ``pyproject.toml`` with a ``[tool.blicket]`` section.

    The search starts at ``start`` (default: the working directory) and walks up; a
    ``pyproject.toml`` without the section is skipped, so a project nested in another repository
    is found.
    """
    origin = Path.cwd() if start is None else Path(start)
    origin = origin.resolve()
    for directory in (origin, *origin.parents):
        candidate = directory / PYPROJECT
        if candidate.is_file() and _blicket_section(_read_pyproject(candidate)) is not None:
            return directory
    raise ConfigError(
        f"no {PYPROJECT} with a [tool.blicket] section in {origin} or any parent directory; "
        "run blicket inside a project or pass --project"
    )


def load_config(root: str | Path) -> Config:
    """Read and validate ``[tool.blicket]`` from ``<root>/pyproject.toml``."""
    path = Path(root) / PYPROJECT
    if not path.is_file():
        raise ConfigError(
            f"{root} has no {PYPROJECT}; pass the directory that holds the project's {PYPROJECT}"
        )
    section = _blicket_section(_read_pyproject(path))
    if section is None:
        raise ConfigError(f"{path}: no [tool.blicket] section; add one, it may be empty")
    try:
        return Config.model_validate(section)
    except ValidationError as error:
        raise ConfigError(f"{path}: {'; '.join(_describe(error, section))}") from error
