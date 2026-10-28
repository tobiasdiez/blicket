"""The comparison of a build with its baseline, as ``check`` and ``dev`` make it: find the
baseline in the store, compare, and write the comparison into the build directory."""

from dataclasses import dataclass
from pathlib import Path

from blicket import comparison
from blicket.baseline import Resolution, resolve
from blicket.builder import Build
from blicket.comparison import Comparison
from blicket.store import Store


@dataclass(frozen=True)
class Compared:
    """The baseline found or why there is none, the comparison written, ``None`` without a
    baseline, and warnings about the store."""

    resolution: Resolution
    comparison: Comparison | None
    warnings: tuple[str, ...] = ()


def compare(build: Build, root: Path, against: str | None = None) -> Compared:
    """Compare ``build`` of the project at ``root`` with its baseline in the project's store.

    ``against`` names the baseline or a git ref, as ``blicket check --against`` does. The
    comparison goes into ``compare/<baseline id>/`` of the build directory. Raises
    ``BlicketError`` when git cannot run, and when the comparison cannot be written.
    """
    listing = Store.of_project(root).list()
    resolution = resolve(listing, build.manifest, root, against)
    compared = None
    if (found := resolution.baseline) is not None:
        compared = comparison.write(
            comparison.compare_builds(found.path, build.path), found.path, build.path
        )
    warnings = tuple(f"skipped a build in the store: {damaged}" for damaged in listing.damaged)
    return Compared(resolution, compared, warnings)
