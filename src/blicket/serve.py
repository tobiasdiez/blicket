"""``blicket serve`` and ``blicket dev``: a build directory over HTTP, with the viewer of this
installation in front.

A request is answered from the installed viewer when it has the path, else from the build
directory, so a directory that carries an older copy of the viewer shows the current one. Nothing
outside the two directories is served, not through a symbolic link either, and directories are
not listed. ``index.html``, ``manifest.json`` and the JSON files under ``compare/``, which
``check`` rewrites, are sent with ``Cache-Control: no-cache``; the viewer fetches tables by their
content hash and its assets are named by their content.

With a ``DevSession``, as ``blicket dev`` attaches one, each request is answered from the build
the session serves when the request comes: ``manifest.json`` from the session, with the header
``Blicket-Dev: 1`` that tells the viewer it is in dev mode, and the routes under ``dev/``:
``info`` (the project root, and whether there is a dataset), ``dataset`` (what the Blick builder
offers), ``query`` (``POST``, a builder query, answered with its entry) and
``tables/<hex>.parquet`` (the tables of the last queries). A route that changes anything, or runs
the project's code, answers only the viewer's own page. A route that fails answers 500 and the
traceback goes to stderr.
"""

import errno
import ipaddress
import json
import os
import re
import socket
import sys
import traceback
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from blicket import viewer
from blicket.comparison import COMPARE
from blicket.errors import BlicketError, DatasetError, issue_field
from blicket.manifest import MANIFEST
from blicket.query import TABLES, Options, Query

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_DEFAULT_PORTS = 10  # how many ports from DEFAULT_PORT on a server tries when given none
DEV_HEADER = "Blicket-Dev"
_NO_CACHE = frozenset({"/", "/index.html", f"/{MANIFEST}"})
_TABLE = re.compile(rf"/{TABLES}/([0-9a-f]{{64}})\.parquet")
_MAX_BODY = 1 << 20  # bytes of a request's body
_BODY_TIMEOUT = 30  # seconds a client may stay silent while it sends a body it announced
# Whence a request that changes something may come: the viewer's own page, or the address bar.
_SITES = frozenset({"same-origin", "none"})


class Info(BaseModel):
    """What ``dev/info`` says: the project root, whether the project has a dataset, why not, and
    whether because ``dataset(run)`` failed."""

    model_config = ConfigDict(frozen=True)

    root: str
    dataset: bool
    message: str | None = None
    failed: bool = False


class Served(Protocol):
    """The build a dev session serves, as it was when a request came: one request reads one
    build, whatever the session does meanwhile."""

    @property
    def directory(self) -> Path:
        """The build directory."""
        ...

    def manifest(self) -> bytes:
        """The manifest of the build, as JSON."""
        ...


class DevSession(Protocol):
    """What ``blicket dev`` serves besides the files of a build directory."""

    def current(self) -> Served:
        """The build served now."""
        ...

    def info(self) -> Info:
        """What ``dev/info`` says."""
        ...

    def options(self) -> Options:
        """What the Blick builder offers; raises ``DatasetError`` without a dataset."""
        ...

    def query(self, query: Query) -> bytes:
        """The entry of a builder query as JSON; raises ``DatasetError`` without a dataset."""
        ...

    def table(self, digest: str) -> bytes | None:
        """The Parquet bytes of a query's table by their sha256, if still kept."""
        ...


class Server(ThreadingHTTPServer):
    """The HTTP server of a build directory: ``directory`` for ``blicket serve``, or the one the
    ``session`` of ``blicket dev`` serves, which is attached once the server is bound. ``site``
    is the installed viewer."""

    def __init__(self, address: tuple[str, int], site: Path, directory: Path | None = None) -> None:
        self.site = site.resolve()
        self.session: DevSession | None = None
        self._directory = directory.resolve() if directory is not None else None
        super().__init__(address, _Handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Report errors of a request, except a browser closing its connection."""
        if not isinstance(sys.exception(), ConnectionError):
            super().handle_error(request, client_address)

    @property
    def ready(self) -> bool:
        """Whether there is a build to serve: a directory, or a session."""
        return self.session is not None or self._directory is not None

    @property
    def directory(self) -> Path:
        """The build directory served now."""
        if self.session is not None:
            return self.session.current().directory
        if self._directory is None:
            raise BlicketError("the server has no build directory and no session")
        return self._directory

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host!s}:{port}/"


@dataclass(frozen=True)
class _Response:
    status: HTTPStatus
    body: bytes
    content_type: str = "application/json"
    headers: Mapping[str, str] = field(default_factory=dict)


def _json(status: HTTPStatus, data: Any, cache: str = "no-store") -> _Response:
    """A JSON response of ``data``: JSON bytes, a pydantic model, or JSON data."""
    if isinstance(data, bytes):
        body = data
    else:
        text = data.model_dump_json() if isinstance(data, BaseModel) else json.dumps(data)
        body = text.encode()
    return _Response(status, body, headers={"Cache-Control": cache})


class _Refusal(Exception):
    """A request a route refuses, with the status and why."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _manifest(handler: _Handler, session: DevSession) -> _Response:
    return _Response(HTTPStatus.OK, handler.served_manifest(), headers={DEV_HEADER: "1"})


def _info(handler: _Handler, session: DevSession) -> _Response:
    return _json(HTTPStatus.OK, session.info())


def _dataset(handler: _Handler, session: DevSession) -> _Response:
    return _json(HTTPStatus.OK, session.options(), cache="no-cache")


def _query(handler: _Handler, session: DevSession) -> _Response:
    handler.same_origin()
    body = handler.json_body()
    try:
        query = Query.model_validate_json(body)
    except ValidationError as error:
        issue = error.errors()[0]
        where = issue_field(issue)
        message = f"not a builder query: {where + ': ' if where else ''}{issue['msg']}"
        raise _Refusal(HTTPStatus.BAD_REQUEST, message) from error
    return _json(HTTPStatus.OK, session.query(query))


type _Route = Callable[[_Handler, DevSession], _Response]

_ROUTES: dict[tuple[str, str], _Route] = {
    ("GET", f"/{MANIFEST}"): _manifest,
    ("GET", "/dev/info"): _info,
    ("GET", "/dev/dataset"): _dataset,
    ("POST", "/dev/query"): _query,
}
# The methods of each path with a route, for the Allow header of a 405.
_METHODS: dict[str, list[str]] = {
    path: [method for method, route_path in _ROUTES if route_path == path] for _, path in _ROUTES
}


class _Handler(SimpleHTTPRequestHandler):
    """Serves the server's build directory, looking each path up in its viewer first, and the
    routes of a dev session.

    A request that is not a ``GET`` or ``HEAD``, or that carries a body, closes the connection
    unless a route reads its body in full: an unread body would be read as the next request. An
    answer on a connection that closes says ``Connection: close``.
    """

    protocol_version = "HTTP/1.1"

    def __init__(self, request: Any, client_address: Any, server: Server) -> None:
        self.owner = server  # ``server`` as the base class types it is any socketserver
        self.site = server.site
        self.session: DevSession | None = None
        self.served: Served | None = None
        self.root = Path()
        self.keep_alive = False
        self.connection_said = False
        self.path = ""  # read by end_headers, also for a request line that cannot be parsed
        super().__init__(request, client_address, server, directory=os.devnull)

    def handle_one_request(self) -> None:
        # Nothing of the request before on the connection, also when this one cannot be parsed.
        self.connection_said = False
        self.path = ""
        super().handle_one_request()

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "connection":
            self.connection_said = True
        super().send_header(keyword, value)

    def parse_request(self) -> bool:
        """Read the request's headers, then take what it is answered from: the session, and the
        build it serves at this moment."""
        if not super().parse_request():
            return False
        self.keep_alive = not self.close_connection
        length = self.headers.get("Content-Length", "")
        body = length not in ("", "0") or "Transfer-Encoding" in self.headers
        if self.command not in ("GET", "HEAD") or body:
            self.close_connection = True
        self.session = self.owner.session
        self.served = self.session.current() if self.session is not None else None
        self.root = self.served.directory if self.served is not None else self.owner.directory
        self.directory = str(self.root)
        return True

    def served_manifest(self) -> bytes:
        assert self.served is not None, "a dev session serves the manifest"
        return self.served.manifest()

    def _locate(self, path: str) -> tuple[str, Path]:
        """The file for the URL path ``path`` and the directory it was found in."""
        local = super().translate_path(path)  # within the build directory, '..' dropped
        candidate = self.site / Path(local).relative_to(self.root)
        if candidate.exists():
            return str(candidate) + ("/" if local.endswith("/") else ""), self.site
        return local, self.root

    def translate_path(self, path: str) -> str:
        return self._locate(path)[0]

    def _route(self, method: str) -> _Response | None:
        """The response of the dev session's route for this request, ``None`` without a
        session or for a path that is not its. A refusal, a missing dataset and an unexpected
        exception are answered too."""
        if (session := self.session) is None:
            return None
        path = urllib.parse.urlsplit(self.path).path
        try:
            if (route := _ROUTES.get((method, path))) is not None:
                return route(self, session)
            if (allowed := _METHODS.get(path)) is not None:
                response = _json(HTTPStatus.METHOD_NOT_ALLOWED, {"message": f"{method} {path}"})
                return _Response(
                    response.status, response.body, headers={"Allow": ", ".join(allowed)}
                )
            if method == "GET" and (matched := _TABLE.fullmatch(path)):
                if (table := session.table(matched[1])) is None:
                    return _json(HTTPStatus.NOT_FOUND, {"message": "no such table in this session"})
                immutable = {"Cache-Control": "max-age=31536000, immutable"}
                return _Response(HTTPStatus.OK, table, "application/vnd.apache.parquet", immutable)
            if path == "/dev" or path.startswith("/dev/"):
                return _json(HTTPStatus.NOT_FOUND, {"message": f"no route {method} {path}"})
        except _Refusal as refusal:
            return _json(refusal.status, {"message": str(refusal)})
        except DatasetError as error:
            return _json(HTTPStatus.NOT_FOUND, {"message": str(error)}, cache="no-cache")
        except TimeoutError, ConnectionError:
            raise  # the connection timed out or broke: the base class closes it
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return _json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"message": "internal error; see the terminal"}
            )
        return None

    def _respond(self, response: _Response) -> BytesIO:
        """Send the status and headers of ``response``; return its body to send."""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.end_headers()
        return BytesIO(response.body)

    def same_origin(self) -> None:
        """Refuse a request that does not come from the viewer's own page to this server: its
        ``Sec-Fetch-Site`` must be ``same-origin`` or ``none`` and its ``Host`` this server."""
        if self.headers.get("Sec-Fetch-Site") not in _SITES:
            raise _Refusal(
                HTTPStatus.FORBIDDEN,
                "a request comes from the viewer's own page (Sec-Fetch-Site: same-origin)",
            )
        if not _own_host(self.headers.get("Host"), self.server.server_address):
            raise _Refusal(HTTPStatus.FORBIDDEN, "the Host header names another server")

    def json_body(self) -> bytes:
        """The request's JSON body, read in full, which keeps the connection open; refused when
        its framing is ambiguous (a ``Transfer-Encoding``, or ``Content-Length`` twice), it is not
        JSON, or its length is missing, malformed or too large. A client that stays silent for
        ``_BODY_TIMEOUT`` seconds while it sends the body loses the connection."""
        lengths = self.headers.get_all("Content-Length", [])
        if "Transfer-Encoding" in self.headers or len(lengths) > 1:
            raise _Refusal(
                HTTPStatus.BAD_REQUEST,
                "the body is framed by one Content-Length, without Transfer-Encoding",
            )
        if self.headers.get_content_type() != "application/json":
            raise _Refusal(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "the body is sent as Content-Type: application/json",
            )
        length = self.headers.get("Content-Length")
        if length is None:
            raise _Refusal(HTTPStatus.LENGTH_REQUIRED, "the request has no Content-Length")
        if not (length.isascii() and length.isdigit()):
            raise _Refusal(HTTPStatus.BAD_REQUEST, f"Content-Length {length!r} is no length")
        # Measured by its digits first: int() refuses a string of thousands of them.
        if len(length.lstrip("0")) > len(str(_MAX_BODY)) or (size := int(length)) > _MAX_BODY:
            raise _Refusal(HTTPStatus.CONTENT_TOO_LARGE, f"the body exceeds {_MAX_BODY} bytes")
        self.connection.settimeout(_BODY_TIMEOUT)
        try:
            body = self.rfile.read(size)
        finally:
            self.connection.settimeout(None)
        if len(body) == size:
            self.close_connection = not self.keep_alive
        return body

    def send_head(self) -> Any:
        if "\0" in urllib.parse.unquote(self.path):
            self.send_error(HTTPStatus.BAD_REQUEST, "Path with a NUL character")
            return None
        if (response := self._route("GET")) is not None:
            return self._respond(response)
        try:
            local, root = self._locate(self.path)
            if Path(local).exists() and not Path(local).resolve().is_relative_to(root):
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")  # a link out of the root
                return None
            return super().send_head()
        except ValueError:  # a path no file can have, such as an escaped lone surrogate
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

    def do_POST(self) -> None:
        """A dev session's route; any other ``POST`` is not found."""
        if (response := self._route("POST")) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        self.wfile.write(self._respond(response).getvalue())

    def list_directory(self, path: str | os.PathLike[str]) -> None:
        self.send_error(HTTPStatus.NOT_FOUND, "File not found")

    def end_headers(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path in _NO_CACHE or (path.startswith(f"/{COMPARE}/") and path.endswith(".json")):
            self.send_header("Cache-Control", "no-cache")
        if self.close_connection and not self.connection_said:
            self.send_header("Connection", "close")
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


def _own_host(given: str | None, address: Any) -> bool:
    """Whether the ``Host`` header ``given`` names the server listening on ``address``: its port,
    and an IP address, ``localhost``, the address it listens on, or, listening on every address,
    this machine's name. A name that only resolves to the server, as a page of another site can
    make one, is not."""
    if not given:
        return False
    bound, port = address[:2]
    try:
        parsed = urllib.parse.urlsplit(f"//{given}")
        name, given_port = parsed.hostname, parsed.port
    except ValueError:
        return False
    if name is None or (given_port or 80) != port:
        return False
    names = {"localhost", str(bound).lower()}
    if str(bound) in ("0.0.0.0", "::", ""):
        names.add(socket.gethostname().lower())
    if name in names:
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def make_server(
    directory: Path | None = None, host: str = DEFAULT_HOST, port: int | None = None
) -> Server:
    """A server for the build directory ``directory`` and the viewer, bound but not serving yet.

    Without ``port``, it listens on ``DEFAULT_PORT``, or on the first free port of the ones after
    it, or, when those are taken too, on any free port. Without ``directory``, a dev session is
    attached to the server before it serves. Raises ``BlicketError`` when there is no viewer or
    the port ``port`` is taken.
    """
    site = viewer.find()
    if port is None:
        for candidate in range(DEFAULT_PORT, DEFAULT_PORT + _DEFAULT_PORTS):
            try:
                return Server((host, candidate), site, directory)
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    raise _cannot_serve(host, candidate, error) from error
        port = 0
    try:
        return Server((host, port), site, directory)
    except OSError as error:
        raise _cannot_serve(host, port, error) from error


def _cannot_serve(host: str, port: int, error: OSError) -> BlicketError:
    reason = error.strerror or str(error)
    if error.errno == errno.EADDRINUSE:
        reason = "the port is in use; pass another with --port"
    return BlicketError(f"cannot serve on {host}:{port}: {reason}")


def run(server: Server) -> None:
    """Serve until Ctrl-C, then close the server; raises ``BlicketError`` when the server has
    neither a build directory nor a session."""
    if not server.ready:
        server.server_close()
        raise BlicketError("the server has no build directory and no session to serve")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
