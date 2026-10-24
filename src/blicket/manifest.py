"""``manifest.json``, the description of a build directory, as pydantic models.

The models are the specification of the file: ``Manifest.model_json_schema(mode="serialization")``
is its JSON Schema. The fields a reader resolves as paths are relative to the build directory
(``data``) or the project root (``source``, when dumped with ``context={"root": root}``); run
paths outside the project, messages and tracebacks may contain paths of the machine the build ran
on. The name ``compare`` inside a build directory is reserved.

The build id is content-addressed over the whole manifest except what ``NOT_IN_ID`` leaves out:
timestamps and timings, the blicket version, tracebacks, the run's id, paths and model checkout,
the repository's branch and dirty flag, where the Blicks are defined, and the controls blicket
derives from their definitions and columns. A rerun that differs
only in those is the same build, so its existing directory is reused. Equal content without
problems gives the same id on any machine and from any working directory; a build with problems
embeds exception text, so its id is reproducible on one machine only. Ids compare only within
one ``spec``, and whether a Blick changed is judged by its table hash, never by the id.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from blicket.errors import BlicketError, Problem
from blicket.model import BlickEntry, Group

SPEC = "0.2"
MANIFEST = "manifest.json"
BUILD_ID = re.compile(r"[0-9a-f]{16}")  # what ``Manifest.content_id`` returns

NOT_IN_ID: dict[str, Any] = {
    # when and by what the build was made
    "created_at": True,
    "blicket": True,
    "build": {"id", "loader_ms"},
    # names and places of the run and the checkouts, not their content
    "run": {"id", "paths", "commit", "branch", "dirty"},
    "repository": {"branch", "dirty"},
    # where the Blicks are defined, how long they took, and tracebacks, which hold machine paths
    "groups": {"__all__": {"modules"}},
    "blicks": {
        "__all__": {
            "timing_ms": True,
            "module": True,
            "source": True,
            "problems": {"__all__": {"traceback"}},
            # derived from the definition and the columns, which are in the id, by blicket's
            # code, which is not
            "controls": True,
        }
    },
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
    """The project's comparison settings from ``[tool.blicket]`` when the build ran."""

    model_config = ConfigDict(frozen=True)

    tolerance: float


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
    """What a build holds: its definitions, run, settings, repository state, tables, problems.

    ``problems`` concern a file or the project; a Blick's own are in its entry.
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
    problems: tuple[Problem, ...]

    @property
    def has_errors(self) -> bool:
        """Whether a Blick or a file failed."""
        return self.build.incomplete or any(entry.status == "error" for entry in self.blicks)

    def content_id(self, root: Path) -> str:
        """16 hex digits of sha256 over the manifest without ``NOT_IN_ID``."""
        content = self.model_dump(mode="json", context={"root": root}, exclude=NOT_IN_ID)
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def read(directory: Path) -> Manifest:
    """The manifest of the build directory ``directory``.

    Raises ``BlicketError`` when it cannot be read, is of another ``spec``, or is invalid.
    """
    try:
        data = json.loads((directory / MANIFEST).read_bytes())
        spec = data.get("spec") if isinstance(data, dict) else None
        if isinstance(spec, str) and spec != SPEC:
            raise BlicketError(
                f"{directory / MANIFEST} is spec {spec}; this blicket reads {SPEC}: rebuild the run"
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
