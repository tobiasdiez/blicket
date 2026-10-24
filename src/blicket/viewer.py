"""The generated viewer: where this installation has it, and its copy in a build directory.

The viewer is a static site (``index.html`` and its assets) that reads ``manifest.json`` and the
tables next to it. A release wheel bundles it under ``blicket/_viewer``; ``BLICKET_VIEWER`` names
another generated one, such as ``viewer/.output/public`` in a development installation.
"""

import hashlib
import importlib.resources
import os
import shutil
from pathlib import Path

from blicket.errors import BlicketError

VIEWER_ENV = "BLICKET_VIEWER"
MARKER = "viewer-version"


def _bundled() -> Path | None:
    """The viewer installed with blicket, if this installation has one on disk."""
    index = importlib.resources.files("blicket").joinpath("_viewer", "index.html")
    return index.parent if isinstance(index, Path) and index.is_file() else None


def find() -> Path:
    """The viewer to use: the one ``BLICKET_VIEWER`` names, else the bundled one.

    Raises ``BlicketError`` when ``BLICKET_VIEWER`` names a directory without ``index.html``, and
    when there is neither.
    """
    named = os.environ.get(VIEWER_ENV)
    if named:
        directory = Path(named).resolve()
        if not directory.exists():
            raise BlicketError(f"{VIEWER_ENV} names {directory}, which does not exist")
        if not (directory / "index.html").is_file():
            raise BlicketError(
                f"{VIEWER_ENV} names {directory}, which has no index.html; generate the viewer "
                "(pnpm generate in viewer/) or unset it"
            )
        return directory
    installed = _bundled()
    if installed is None:
        raise BlicketError(
            "no viewer found: install a blicket release (it bundles one), or from a checkout run "
            f"`pnpm generate` in viewer/ and set {VIEWER_ENV}=viewer/.output/public"
        )
    return installed


def files(source: Path) -> list[str]:
    """The viewer's files, as paths relative to ``source``, in sorted order."""
    return sorted(
        path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()
    )


def version(source: Path, names: list[str]) -> str:
    """16 hex digits of sha256 over the names and contents of the viewer's files ``names``."""
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode() + b"\0")
        digest.update((source / name).read_bytes())
    return digest.hexdigest()[:16]


def copy(source: Path, directory: Path) -> bool:
    """Put the viewer at ``source`` into the build directory ``directory``; return whether it
    wrote anything.

    The marker file ``viewer-version``, written by this function, holds the viewer's version on its
    first line and the copied files after it. Nothing is written when it names this version
    already; otherwise the files it lists are removed, the viewer's files copied, and the marker
    written last, so an interrupted copy is redone by the next build. No other file is touched;
    directories the old files leave empty stay.
    """
    marker = directory / MARKER
    try:
        names = files(source)
        current = version(source, names)
        previous = marker.read_text().splitlines() if marker.is_file() else []
        if previous[:1] == [current]:
            return False
        for name in previous[1:]:
            (directory / name).unlink(missing_ok=True)
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
        marker.write_text("\n".join([current, *names]) + "\n")
    except OSError as error:
        reason = error.strerror or str(error)
        raise BlicketError(f"cannot copy the viewer into {directory}: {reason}") from error
    return True
