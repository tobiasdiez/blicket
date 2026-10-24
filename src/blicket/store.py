"""The store: a directory of builds, each the manifest, tables and comparisons of a build
directory, kept under ``builds/<build id>/`` and never changed once there.

A build is copied into a temporary directory next to its destination and renamed to its id at the
end, so it appears complete or not at all; ``Store.path`` accepts only names shaped like a build
id, so it never finds the temporary directories. Directories and files are created with the
permissions the umask gives, not copied from the build directory, so a build written by a
private umask can go into a shared store. ``builds/`` gets a ``.gitignore`` when a push creates
it, so a store inside a repository never makes the tree dirty.
"""

import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from blicket import manifest
from blicket.comparison import COMPARE, COMPARISON
from blicket.errors import BlicketError, os_reason
from blicket.manifest import Manifest


@dataclass(frozen=True)
class Pushed:
    """A build in the store: its id, its directory there, whether it was there already, and the
    baseline ids of the comparisons copied with it."""

    id: str
    path: Path
    existed: bool
    comparisons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stored:
    """A build with its id, its directory and its manifest."""

    id: str
    path: Path
    manifest: Manifest


@dataclass(frozen=True)
class Listing:
    """The builds in the store whose manifests this blicket reads; ``other_spec`` counts those
    of another ``spec``, and ``damaged`` says why the unreadable ones were skipped."""

    builds: tuple[Stored, ...]
    other_spec: int
    damaged: tuple[str, ...]


class Store:
    """The store in ``directory``, created on the first push."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.builds = directory / "builds"

    def push(self, build: Path) -> Pushed:
        """Copy the manifest of the build directory ``build``, the tables its entries name, and
        the files in its ``compare`` directory, but those under names starting with a dot, into
        the store; nothing else, so not the viewer.

        Nothing is written when the store holds the build already, so comparisons written after
        the first push stay out. Raises ``BlicketError`` when the manifest cannot be read, the
        build id is not one ``Manifest.content_id`` gives, a file is missing or not a regular file
        inside ``build``, or the store holds a directory of the id without a manifest, all before
        anything is written, and when the copy fails.
        """
        built = manifest.read(build)
        build_id = built.build.id
        if not manifest.BUILD_ID.fullmatch(build_id):
            raise BlicketError(f"{build} has an invalid build id {build_id!r}")
        compared = [
            path.relative_to(build).as_posix()
            for path in sorted((build / COMPARE).rglob("*"))
            if path.is_file() and not any(p.startswith(".") for p in path.relative_to(build).parts)
        ]
        names = [
            manifest.MANIFEST,
            *(e.data for e in built.blicks if e.data is not None),
            *compared,
        ]
        inside = build.resolve()
        for name in names:
            source = build / name
            if not source.exists():
                raise BlicketError(f"{source} is missing; rebuild the run")
            if not (source.is_file() and source.resolve().is_relative_to(inside)):
                raise BlicketError(f"{source} is not a regular file inside {build}")
        final = self.builds / build_id
        if (final / manifest.MANIFEST).is_file():
            return Pushed(build_id, final, existed=True)
        if final.exists():
            raise BlicketError(f"{final} holds no {manifest.MANIFEST}; delete it and push again")
        created = not self.builds.exists()
        temporary = self.builds / f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
        try:
            temporary.mkdir(parents=True)
            if created:
                (self.builds / ".gitignore").write_text("*\n")
            for name in names:
                target = temporary / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(build / name, target)
            temporary.rename(final)
        except OSError as error:
            if (final / manifest.MANIFEST).is_file():  # pushed by another process meanwhile
                return Pushed(build_id, final, existed=True)
            raise BlicketError(
                f"cannot push build {build_id} to {self.directory}: {os_reason(error)}"
            ) from error
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
        baselines = [name.split("/")[1] for name in compared if name.endswith(f"/{COMPARISON}")]
        return Pushed(build_id, final, existed=False, comparisons=tuple(baselines))

    def list(self) -> Listing:
        """The builds in the store, in the order of their ids.

        A build of another ``spec`` is counted, a build whose manifest cannot be read described,
        and both skipped, so that neither keeps the others from being found.
        """
        builds: list[Stored] = []
        damaged: list[str] = []
        other_spec = 0
        for directory in sorted(self.builds.iterdir()) if self.builds.is_dir() else ():
            if not manifest.BUILD_ID.fullmatch(directory.name):
                continue
            try:
                builds.append(Stored(directory.name, directory, manifest.read(directory)))
            except manifest.OtherSpec:
                other_spec += 1
            except BlicketError as error:
                damaged.append(str(error))
        return Listing(tuple(builds), other_spec, tuple(damaged))

    def path(self, build_id: str) -> Path | None:
        """The directory of the build ``build_id`` in the store, ``None`` when the store holds no
        build of that id or ``build_id`` is not shaped like one."""
        directory = self.builds / build_id
        if manifest.BUILD_ID.fullmatch(build_id) and (directory / manifest.MANIFEST).is_file():
            return directory
        return None
