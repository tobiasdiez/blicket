"""The comparison of a build with its baseline, as ``check`` makes it: find the baseline in the
store, compare, and write the comparison into the build directory. A session of ``dev`` finds its
baseline the same way and compares its Blicks as they are built."""

from dataclasses import dataclass
from pathlib import Path

from blicket import comparison
from blicket.baseline import Resolution, resolve
from blicket.builder import Build
from blicket.comparison import Baseline, Comparison
from blicket.manifest import Manifest
from blicket.store import Store


@dataclass(frozen=True)
class Lookup:
    """What looking for the baseline of a build found: the baseline, ``None`` when there is
    none, why not, and warnings about the store."""

    resolution: Resolution
    baseline: Baseline | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Compared:
    """The baseline found or why there is none, the comparison written, ``None`` without a
    baseline, and warnings about the store."""

    resolution: Resolution
    comparison: Comparison | None
    warnings: tuple[str, ...] = ()


def find(built: Manifest, root: Path, against: str | None = None) -> Lookup:
    """The baseline of the build ``built`` of the project at ``root`` in the project's store, as
    ``blicket check`` finds it; ``against`` names it or a git ref, as ``--against`` does. A build
    in the store whose manifest cannot be read is a warning. Raises ``BlicketError`` when git
    cannot run."""
    listing = Store.of_project(root).list()
    resolution = resolve(listing, built, root, against)
    baseline = None
    if (stored := resolution.baseline) is not None:
        baseline = Baseline.of(stored.path, stored.manifest)
    warnings = tuple(f"skipped a build in the store: {damaged}" for damaged in listing.damaged)
    return Lookup(resolution, baseline, warnings)


def compare(build: Build, root: Path, against: str | None = None) -> Compared:
    """Compare ``build`` of the project at ``root`` with its baseline in the project's store.

    ``against`` names the baseline or a git ref, as ``blicket check --against`` does. The
    comparison goes into ``compare/<baseline id>/`` of the build directory. Raises
    ``BlicketError`` when git cannot run, and when the comparison cannot be written.
    """
    found = find(build.manifest, root, against)
    compared = None
    if (baseline := found.baseline) is not None:
        compared = comparison.write(comparison.compare(baseline, build.path), baseline, build.path)
    return Compared(found.resolution, compared, found.warnings)
