"""Where project code raised an exception, and its traceback without blicket's own frames.

Discovery, the loader and the build use these, so an exception raised by a Blick module, by the
loader and by a transformation is located and trimmed alike.
"""

import traceback
from pathlib import Path

from blicket.errors import Source


def in_project(location: str, root: Path) -> bool:
    """Whether ``location`` is a real file under ``root``, outside its hidden directories."""
    path = Path(location)
    if not path.is_absolute():  # pseudo-filenames such as <frozen importlib._bootstrap>
        return False
    path = path.resolve()
    if not path.is_relative_to(root):
        return False
    return not any(part.startswith(".") for part in path.relative_to(root).parts)


def locate(error: BaseException, root: Path, prefer: Path | None = None) -> Source | None:
    """Where the project's code raised ``error``.

    The innermost frame in the file ``prefer``, else the innermost frame in the project; for a
    syntax error without such a frame, the line it points at. ``None`` when no project file is
    involved.
    """
    stack = traceback.extract_tb(error.__traceback__)
    frames = [frame for frame in stack if in_project(frame.filename, root)]
    if prefer is not None:
        preferred = prefer.resolve()
        frames = [f for f in frames if Path(f.filename).resolve() == preferred] or frames
    if frames:
        return Source(Path(frames[-1].filename), frames[-1].lineno)
    if isinstance(error, SyntaxError) and error.filename:
        return Source(Path(error.filename), error.lineno)
    return None


def raised_at(error: BaseException, root: Path, shown: Source | None) -> str:
    """`` (raised at file:line)`` when ``error`` was raised elsewhere in the project than at
    ``shown``, the location a report already names; else nothing."""
    raised = locate(error, root)
    if raised is None or raised == shown:
        return ""
    return f" (raised at {raised.display(root)})"


def project_traceback(error: BaseException, root: Path) -> str:
    """The traceback from the first frame in the project's files, without blicket's own.

    When no frame lies in the project, as for a loader installed elsewhere, the whole traceback.
    """
    exception = traceback.TracebackException.from_exception(error)
    frames = list(exception.stack)
    first = next((i for i, frame in enumerate(frames) if in_project(frame.filename, root)), 0)
    exception.stack = traceback.StackSummary.from_list(frames[first:])
    return "".join(exception.format())
