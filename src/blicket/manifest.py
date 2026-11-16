"""``manifest.json``, the description of a build directory, as pydantic models.

The models are the specification of the file: ``Manifest.model_json_schema(mode="serialization")``
is its JSON Schema. The fields a reader resolves as paths are relative to the build directory
(``data``) or the project root (``source``, when dumped with ``context={"root": root}``); run
paths outside the project, messages and tracebacks may contain paths of the machine the build ran
on. The name ``compare`` inside a build directory is reserved. A unit's ``status`` is ``ok`` when
it built a table, ``error`` when it failed, and ``skipped`` when its transformation raised
``bk.Skip`` to say that it does not apply to the run, or a check's level is ``off``, which is no
failure; the entry then holds the reason and no table. The ``outcome`` of a unit's expectation
stands beside its status: a Blick whose expectation failed built its table and is ``ok``. Blicks
are in ``blicks``, their tables ``blicks/<id>.parquet``; checks in ``checks``, the offending rows
``checks/<id>.parquet``.

The build id is content-addressed over the whole manifest except what ``NOT_IN_ID`` leaves out:
timestamps and timings, the blicket version, tracebacks, the run's id, paths and model checkout,
the repository's branch and dirty flag, where the units are defined, and what blicket derives
from their definitions and tables: the controls, the level a unit has from its group or the
project, and its expectation in words. A rerun that differs only in those is the same build,
so its existing directory is reused. Equal content without problems gives the same id on any
machine and from any working directory. A build with problems embeds exception text, and the
reasons of skipped units are content too. Both may hold paths of the machine the build ran on,
so the id of such a build is reproducible on that machine only. Ids compare only within one
``spec``, and whether a Blick changed is judged by its table hash, never by the id.

This blicket writes ``spec`` 0.3 and reads 0.2 as well, whose builds have no checks, levels or
outcomes: every field 0.3 added has a default.
"""

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from blicket.errors import BlicketError, Problem
from blicket.expect._levels import DEFAULT_LEVEL, Level
from blicket.expect._outcome import Outcome
from blicket.model import BlickEntry, CheckEntry, Group, Status

SPEC = "0.3"
# The specs this blicket reads; their fields are a subset of this spec's, with defaults.
READS = ("0.2", SPEC)
MANIFEST = "manifest.json"
BUILD_ID = re.compile(r"[0-9a-f]{16}")  # what ``Manifest.content_id`` returns

# What is not in the id of an entry of either kind: where it is defined, how long it took,
# tracebacks, which hold machine paths, and what blicket derives from the definition and the
# table, which are in the id, by its code, which is not: the level from the group or the
# project, and the expectation in words.
_UNIT_NOT_IN_ID: dict[str, Any] = {
    "timing_ms": True,
    "module": True,
    "source": True,
    "problems": {"__all__": {"traceback"}},
    "level": True,
    "outcome": {"expectation"},
}

NOT_IN_ID: dict[str, Any] = {
    # when and by what the build was made
    "created_at": True,
    "blicket": True,
    "build": {"id", "loader_ms"},
    # names and places of the run and the checkouts, not their content
    "run": {"id", "paths", "commit", "branch", "dirty"},
    "repository": {"branch", "dirty"},
    # where the groups are defined
    "groups": {"__all__": {"modules"}},
    # derived from the columns as well: the controls
    "blicks": {"__all__": {**_UNIT_NOT_IN_ID, "controls": True}},
    "checks": {"__all__": _UNIT_NOT_IN_ID},
    "problems": {"__all__": {"traceback"}},
}


class RunInfo(BaseModel):
    """What the loader says about the run it loaded.

    ``id`` names the run. ``profile`` names the run configuration, such as "baseline" or
    "policy", so that each has its own baseline. ``fingerprint`` identifies the input files, see
    ``bk.fingerprint``. ``commit``, ``branch`` and ``dirty`` describe the model's checkout when
    the loader knows it; blicket records the Blick repository itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    fingerprint: str = Field(min_length=1)
    commit: str | None = None
    branch: str | None = None
    dirty: bool | None = None


class BuildInfo(BaseModel):
    """The build's id, whether a Blick module failed to import, and the loader's wall time."""

    model_config = ConfigDict(frozen=True)

    id: str
    incomplete: bool
    loader_ms: float


class BuildConfig(BaseModel):
    """The project's comparison settings and its level from ``[tool.blicket]`` when the build
    ran."""

    model_config = ConfigDict(frozen=True)

    tolerance: float
    level: Level = DEFAULT_LEVEL


class Run(RunInfo):
    """The ``RunInfo`` from the loader and the run paths: relative to the project inside it,
    absolute outside it."""

    paths: list[str]


class Repository(BaseModel):
    """The state of the git repository holding the Blick code, read when the build ran."""

    model_config = ConfigDict(frozen=True)

    commit: str
    branch: str | None
    dirty: bool


class Manifest(BaseModel):
    """What a build holds: its definitions, run, settings, repository state, tables, outcomes,
    problems.

    ``problems`` concern a file or the project; a unit's own are in its entry, as are the reason
    when it was skipped and the outcome of its expectation. ``checks`` are the project's checks,
    beside its Blicks.
    """

    model_config = ConfigDict(frozen=True)

    spec: str = SPEC
    blicket: str
    created_at: datetime
    build: BuildInfo
    config: BuildConfig
    run: Run
    repository: Repository | None
    groups: tuple[Group, ...]
    blicks: tuple[BlickEntry, ...]
    checks: tuple[CheckEntry, ...] = ()
    problems: tuple[Problem, ...]

    @property
    def entries(self) -> tuple[BlickEntry | CheckEntry, ...]:
        """The entries of both kinds, the Blicks first, each kind in the manifest's order."""
        return (*self.blicks, *self.checks)

    @property
    def has_errors(self) -> bool:
        """Whether a unit or a file failed, or an expectation could not be evaluated; a skipped
        unit did not fail, nor did one whose expectation failed."""
        unevaluable = self.results["error"] > 0
        return self.build.incomplete or self.statuses["error"] > 0 or unevaluable

    @property
    def statuses(self) -> Counter[Status]:
        """How many units of both kinds have each status."""
        return Counter(entry.status for entry in self.entries)

    @property
    def outcomes(self) -> list[tuple[BlickEntry | CheckEntry, Outcome]]:
        """The entries with an outcome and their outcomes, in the order of ``entries``."""
        return [(entry, entry.outcome) for entry in self.entries if entry.outcome is not None]

    @property
    def results(self) -> Counter[str]:
        """How many outcomes have each result."""
        return Counter(outcome.result for _, outcome in self.outcomes)

    @property
    def failed_expectations(self) -> int:
        """How many expectations failed, which makes ``build`` and ``check`` exit 1."""
        return self.results["failed"]

    def content_id(self, root: Path) -> str:
        """16 hex digits of sha256 over the manifest without ``NOT_IN_ID``."""
        content = self.model_dump(mode="json", context={"root": root}, exclude=NOT_IN_ID)
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class OtherSpec(BlicketError):
    """A manifest of another ``spec`` than this blicket reads."""


def read(directory: Path) -> Manifest:
    """The manifest of the build directory ``directory``.

    Raises ``OtherSpec`` when it is of a ``spec`` this blicket does not read, and
    ``BlicketError`` when it cannot be read or is invalid.
    """
    try:
        data = json.loads((directory / MANIFEST).read_bytes())
        spec = data.get("spec") if isinstance(data, dict) else None
        if isinstance(spec, str) and spec not in READS:
            raise OtherSpec(
                f"{directory / MANIFEST} is spec {spec}; this blicket reads {' and '.join(READS)}: "
                "rebuild the run"
            )
        return Manifest.model_validate(data)
    except OSError as error:
        reason = "file missing" if isinstance(error, FileNotFoundError) else error.strerror
        cause: Exception = error
    except ValidationError as error:
        reason, cause = "not a manifest of this blicket", error
    except ValueError as error:
        reason, cause = "not valid JSON", error
    raise BlicketError(
        f"build directory {directory} has no readable {MANIFEST} ({reason}); delete it and rebuild"
    ) from cause
