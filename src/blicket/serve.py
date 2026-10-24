"""``blicket serve``: a build directory over HTTP, with the viewer of this installation in front.

A request is answered from the installed viewer when it has the path, else from the build
directory, so a directory that carries an older copy of the viewer shows the current one. Nothing
outside the two directories is served, not through a symbolic link either, and directories are
not listed. ``index.html`` and ``manifest.json`` are sent with ``Cache-Control: no-cache``; the
viewer fetches tables by their content hash and its assets are named by their content.
"""

import errno
import json
import os
import sys
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from blicket import viewer
from blicket.errors import BlicketError
from blicket.manifest import MANIFEST

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_NO_CACHE = frozenset({"/", "/index.html", f"/{MANIFEST}"})


class Server(ThreadingHTTPServer):
    """The HTTP server of the build directory ``directory``; ``site`` is the installed viewer."""

    def __init__(self, address: tuple[str, int], directory: Path, site: Path) -> None:
        self.directory = directory.resolve()
        self.site = site.resolve()
        super().__init__(address, _Handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Report errors of a request, except a browser closing its connection."""
        if not isinstance(sys.exception(), ConnectionError):
            super().handle_error(request, client_address)

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host!s}:{port}/"


class _Handler(SimpleHTTPRequestHandler):
    """Serves the server's build directory, looking each path up in its viewer first."""

    protocol_version = "HTTP/1.1"

    def __init__(self, request: Any, client_address: Any, server: Server) -> None:
        # Set before the base class handles the request, which it does on construction.
        self.site = server.site
        self.root = server.directory
        super().__init__(request, client_address, server, directory=str(server.directory))

    def _locate(self, path: str) -> tuple[str, Path]:
        """The file for the URL path ``path`` and the directory it was found in."""
        local = super().translate_path(path)  # within the build directory, '..' dropped
        candidate = self.site / Path(local).relative_to(self.root)
        if candidate.exists():
            return str(candidate) + ("/" if local.endswith("/") else ""), self.site
        return local, self.root

    def translate_path(self, path: str) -> str:
        return self._locate(path)[0]

    def send_head(self) -> Any:
        if "\0" in urllib.parse.unquote(self.path):
            self.send_error(HTTPStatus.BAD_REQUEST, "Path with a NUL character")
            return None
        local, root = self._locate(self.path)
        if Path(local).exists() and not Path(local).resolve().is_relative_to(root):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")  # a link out of the root
            return None
        return super().send_head()

    def list_directory(self, path: str | os.PathLike[str]) -> None:
        self.send_error(HTTPStatus.NOT_FOUND, "File not found")

    def end_headers(self) -> None:
        if urllib.parse.urlsplit(self.path).path in _NO_CACHE:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Log failed requests only."""
        if isinstance(code, int) and code >= HTTPStatus.BAD_REQUEST:
            super().log_request(code, size)


def build_directory(given: Path) -> Path:
    """``given`` resolved, after checking that it is a build directory."""
    directory = given.resolve()
    if not directory.is_dir():
        raise BlicketError(f"build directory {given} does not exist")
    if not (directory / MANIFEST).is_file():
        raise BlicketError(
            f"{given} has no {MANIFEST}; pass a build directory, such as .blicket/build/<id>"
        )
    return directory


def _created_at(directory: Path) -> datetime | None:
    """When the build in ``directory`` was made, from its manifest; ``None`` if unreadable."""
    try:
        return datetime.fromisoformat(json.loads((directory / MANIFEST).read_bytes())["created_at"])
    except OSError, ValueError, KeyError, TypeError:
        return None


def newest_build(root: Path) -> Path:
    """The build directory under ``<root>/.blicket/build`` that was made last.

    Its manifest's ``created_at`` decides, not file times, which a copy or a rebuild changes.
    """
    builds = root / ".blicket" / "build"
    made = {
        path: created
        for path in (builds.iterdir() if builds.is_dir() else ())
        if not path.name.startswith(".") and (created := _created_at(path)) is not None
    }
    if not made:
        raise BlicketError(f"no build in {builds}; run blicket build first, or pass a directory")
    return max(made, key=made.__getitem__)


def make_server(directory: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Server:
    """A server for the build directory ``directory`` and the viewer, bound but not serving yet.

    Raises ``BlicketError`` when there is no viewer or the port is taken.
    """
    site = viewer.find()
    try:
        return Server((host, port), directory, site)
    except OSError as error:
        reason = error.strerror or str(error)
        if error.errno == errno.EADDRINUSE:
            reason = "the port is in use; pass another with --port"
        raise BlicketError(f"cannot serve on {host}:{port}: {reason}") from error


def run(server: Server) -> None:
    """Serve until Ctrl-C, then close the server."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
