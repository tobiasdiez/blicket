"""``blicket serve`` and ``blicket dev``: a build directory over HTTP, with the viewer of this
installation in front.

A request is answered from the installed viewer when it has the path, else from the build
directory, so a directory that carries an older copy of the viewer shows the current one. Nothing
outside the two directories is served, not through a symbolic link either, and directories are
not listed. ``index.html``, ``manifest.json`` and the JSON files under ``compare/``, which
``check`` rewrites, are sent with ``Cache-Control: no-cache``; the viewer fetches tables by their
content hash and its assets are named by their content.

With a ``DevSession``, as ``blicket dev`` attaches one, nothing of a build directory is served: the
viewer's files are served alone, and each request is answered from the state the session is in when
the request comes. ``manifest.json`` comes from the session, with the header ``Blicket-Dev: 1``
that tells the viewer it is in dev mode, and so do ``compare/index.json``, empty without a
baseline, and the comparison with the baseline; each carries the header ``Blicket-Revision`` naming
the revision it is of, so that a client tells whether what it read is of the revision that
``dev/info`` says. The routes under ``dev/``: ``info`` (the project root, whether there is a
dataset, the session's id, which a restart and the load of another run change, the revision, the
Blick building and the Blicks a page asked for that wait, and why the worker that builds them
stopped, if it did), ``dataset`` (what the Blick builder offers), ``query`` (``POST``, a builder
query, answered with its entry, after the cheap build that holds the session's lock, if one does;
409 while an expensive one builds or a run loads, to be asked again then), ``tables/<hex>.parquet``
(the tables of the last queries, and of the session its Blicks' and their baseline's; one that a
rebuild replaced stays for ``jobs.KEPT`` revisions more; 404 for a table not kept, or never built),
``runs`` (the run folders the project offers to pick, the project itself first when ``runs`` has
``.``), ``run`` (``POST``, load one of them in place of the run served, after the cheap build that
holds the lock, if one does; 409 while an expensive one builds or another run loads, and once the
worker stopped) and ``build`` (``POST``, ``{"id": ..., "rebuild": false}``, build a Blick, answered
at once with its state, ``queued``, ``building`` or ``done``; a client that waits for the build
waits until the Blick has left the jobs of ``info``; 404 for a Blick the session cannot build, 409
while a run loads and once the worker stopped). While the session serves no run yet,
``manifest.json``, ``compare/index.json``, ``dataset``, ``query``, ``build`` and the tables answer
404, ``manifest.json`` and ``compare/index.json`` with the header all the same. Another method on
the path of a route answers 405 with the methods it has. A route that changes anything, or runs the
project's code, answers only the viewer's own page. A route that fails answers 500 and the
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
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from blicket import viewer
from blicket.comparison import COMPARE, COMPARISON, INDEX, Comparison
from blicket.errors import BlicketError, DatasetError, NoSuchBlick, Refused, issue_field
from blicket.manifest import MANIFEST, Manifest
from blicket.query import TABLES, Options, Query

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_DEFAULT_PORTS = 10  # how many ports from DEFAULT_PORT on a server tries when given none
DEV_HEADER = "Blicket-Dev"
NO_RUN = "no run served yet"
_NO_CACHE = frozenset({"/", "/index.html", f"/{MANIFEST}"})
_TABLE = re.compile(rf"/{TABLES}/([0-9a-f]{{64}})\.parquet")
_COMPARISON = re.compile(rf"/{COMPARE}/([^/]+)/{COMPARISON}")
_MAX_BODY = 1 << 20  # bytes of a request's body
_BODY_TIMEOUT = 30  # seconds a client may stay silent while it sends a body it announced
# Whence a request that changes something may come: the viewer's own page, or the address bar.
_SITES = frozenset({"same-origin", "none"})
REVISION_HEADER = "Blicket-Revision"
# The failures of a dev session that the access log leaves out, by path and status: those the
# viewer meets in its course, or the session reports itself.
_SAID = frozenset(
    {
        (f"/{MANIFEST}", HTTPStatus.NOT_FOUND),
        (f"/{COMPARE}/{INDEX}", HTTPStatus.NOT_FOUND),
        ("/dev/run", HTTPStatus.UNPROCESSABLE_ENTITY),
        ("/dev/run", HTTPStatus.CONFLICT),
        ("/dev/query", HTTPStatus.CONFLICT),
    }
)
_GONE = (
    "no table of this hash: it was never built, or is no longer kept; read manifest.json again, "
    "or run the builder's query again"
)
_BUILD_SHAPE = 'send {"id": "<blick id>", "rebuild": false}'

# What ``dev/build`` says of the Blick asked for: it waits, it builds, or it is done, built,
# failed or skipped, and nothing was asked of it.
type BuildState = Literal["queued", "building", "done"]


class Job(BaseModel):
    """A Blick that builds, or that a page asked for and waits to, as ``dev/info`` lists it.

    ``asked`` says that a page asked for it; a Blick that the background builds is not, and the
    Blicks that wait in the background are not listed. A Blick queued or building is still
    ``pending`` in the manifest until it is built, and is listed twice while it builds and a
    rebuild of it waits. ``since`` is when a running job started, and when a queued one was asked
    for; ``seconds`` is how long it has run or waited when ``dev/info`` answered, which a client
    counts on from, whatever its clock says.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    state: Literal["building", "queued"]
    asked: bool
    since: datetime
    seconds: float


class Info(BaseModel):
    """What ``dev/info`` says: the project root, whether the project has a dataset, why not, and
    whether because ``dataset(run)`` failed; ``session`` names the session, so that a client
    learns of a restart.

    ``revision`` rises whenever the manifest or the comparison changed, and ``jobs`` are the
    Blick building and the Blicks a page asked for that wait, in the order they are built.
    ``stopped`` says why the worker that builds them stopped, if it did, which only a bug makes it
    do; ``dev/build`` then answers 409.
    """

    model_config = ConfigDict(frozen=True)

    root: str
    dataset: bool
    message: str | None = None
    failed: bool = False
    session: str = ""
    revision: int = 0
    jobs: tuple[Job, ...] = ()
    stopped: str | None = None


class RunFolder(BaseModel):
    """A run folder to pick: its path, resolved, its name, and when it last changed; or, with
    ``project``, the project itself, named ``This project``, whose run is computed from its code,
    which a folder's time does not tell, so ``modified`` is ``None``. ``served`` says that the run
    served now was loaded from it."""

    model_config = ConfigDict(frozen=True)

    path: Path
    name: str
    modified: datetime | None
    project: bool = False
    served: bool = False


class RunList(BaseModel):
    """What ``dev/runs`` says: the globs of ``runs`` in ``[tool.blicket]`` and the folders they
    match, the project itself first, then newest first."""

    model_config = ConfigDict(frozen=True)

    patterns: list[str]
    runs: list[RunFolder]


class RunRequest(BaseModel):
    """What ``dev/run`` is asked: the paths of the folders to load as one run, as ``dev/runs``
    lists them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paths: list[str]


class BuildRequest(BaseModel):
    """What ``dev/build`` is asked: the id of a Blick to build, and whether to build it once more
    when it is built or building, ``true`` or ``false``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    rebuild: StrictBool = False


@dataclass(frozen=True)
class Served:
    """What a dev session serves, as it was when a request came: one request reads one state,
    whatever the session does meanwhile.

    ``manifest`` and ``comparison``, the comparison with the baseline, ``None`` without one, are
    answered from memory, the manifest's sources relative to the project ``root``. ``tables``
    are Parquet bytes by their sha256 in hex, as ``dev/tables/<hex>.parquet`` serves them: those
    of the session's Blicks and of the baseline it draws them against, and those of the last
    snapshots before. ``revision`` counts the snapshots of the session.
    """

    manifest: Manifest
    root: Path
    comparison: Comparison | None = None
    tables: Mapping[str, bytes] = field(default_factory=dict)
    revision: int = 0

    def manifest_json(self) -> bytes:
        """The manifest as JSON, its sources relative to the project root."""
        text = self.manifest.model_dump_json(indent=2, context={"root": self.root})
        return text.encode() + b"\n"

    def index_json(self) -> bytes:
        """``compare/index.json``: the baseline's id, if there is one."""
        found = [self.comparison.baseline.id] if self.comparison is not None else []
        return (json.dumps(found) + "\n").encode()

    def comparison_json(self, baseline: str) -> bytes | None:
        """The comparison with the baseline ``baseline`` as JSON; ``None`` for another."""
        if self.comparison is None or self.comparison.baseline.id != baseline:
            return None
        return self.comparison.model_dump_json(indent=2).encode() + b"\n"


class DevSession(Protocol):
    """What ``blicket dev`` serves besides the viewer's files."""

    def current(self) -> Served | None:
        """What the session serves now; ``None`` while no run is served yet."""
        ...

    def info(self) -> Info:
        """What ``dev/info`` says."""
        ...

    def options(self) -> Options:
        """What the Blick builder offers; raises ``DatasetError`` without a dataset."""
        ...

    def query(self, query: Query) -> bytes:
        """The entry of a builder query as JSON, after the cheap build that holds the session's
        lock, if one does; raises ``DatasetError`` without a dataset, and ``Refused`` while an
        expensive Blick builds or a run loads, which the query would wait for."""
        ...

    def table(self, digest: str) -> bytes | None:
        """The Parquet bytes of a query's table, or of a Blick of the session or of its baseline,
        by their sha256, if still kept."""
        ...

    def build(self, blick: str, rebuild: bool) -> BuildState:
        """Ask for the Blick ``blick`` to be built, once more with ``rebuild``; its state,
        ``queued``, ``building``, or ``done`` when there is nothing to do. Raises ``NoSuchBlick``
        for an id the session cannot build and while no run is served, and ``Refused`` while a
        run loads and once the worker that builds stopped."""
        ...

    def runs(self) -> RunList:
        """The run folders to pick, as ``dev/runs`` lists them."""
        ...

    def load(self, paths: list[str]) -> str:
        """Load the run at ``paths`` and serve it in place of the run served, if any, after the
        cheap build that holds the session's lock, if one does; the run's id. The caller checks
        that ``runs`` lists the paths. Raises ``LoadRefused`` while another load runs or an
        expensive Blick builds, and once the worker stopped; and another ``BlicketError`` when the
        loader or the baseline fails, which the session reports in the terminal itself, and
        which leaves the run served as it was."""
        ...


class Server(ThreadingHTTPServer):
    """The HTTP server of a build directory, ``directory``, for ``blicket serve``, or of the
    ``session`` of ``blicket dev``, which is attached once the server is bound. ``site`` is the
    installed viewer."""

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
        """The build directory served; the viewer's for a session, which has none."""
        if self.session is not None:
            return self.site
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


def _json(
    status: HTTPStatus,
    data: Any,
    cache: str = "no-store",
    headers: Mapping[str, str] | None = None,
) -> _Response:
    """A JSON response of ``data``: JSON bytes, a pydantic model, or JSON data, with ``headers``
    besides ``Cache-Control``."""
    if isinstance(data, bytes):
        body = data
    else:
        text = data.model_dump_json() if isinstance(data, BaseModel) else json.dumps(data)
        body = text.encode()
    return _Response(status, body, headers={"Cache-Control": cache, **(headers or {})})


class _Refusal(Exception):
    """A request a route refuses, with the status and why."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _parsed[M: BaseModel](model: type[M], body: bytes, what: str, shape: str = "") -> M:
    """``body`` as ``model``; refused with 400 and the first problem, by its field, otherwise,
    followed by ``shape``, which says what to send."""
    try:
        return model.model_validate_json(body)
    except ValidationError as error:
        issue = error.errors()[0]
        where = issue_field(issue)
        message = f"not {what}: {where + ': ' if where else ''}{issue['msg']}"
        raise _Refusal(
            HTTPStatus.BAD_REQUEST, f"{message}; {shape}" if shape else message
        ) from error


def _from_memory(handler: _Handler, body: Callable[[Served], bytes]) -> _Response:
    """What the session serves now, as ``body`` makes it of it, with the revision it is of; while
    it serves no run yet, a 404 that says so, still in dev mode, which the viewer reads from the
    header. No-cache, as ``end_headers`` says."""
    if (served := handler.served) is None:
        message = json.dumps({"message": NO_RUN}).encode()
        return _Response(HTTPStatus.NOT_FOUND, message, headers={DEV_HEADER: "1"})
    headers = {DEV_HEADER: "1", REVISION_HEADER: str(served.revision)}
    return _Response(HTTPStatus.OK, body(served), headers=headers)


def _manifest(handler: _Handler, session: DevSession) -> _Response:
    return _from_memory(handler, Served.manifest_json)


def _index(handler: _Handler, session: DevSession) -> _Response:
    return _from_memory(handler, Served.index_json)


def _info(handler: _Handler, session: DevSession) -> _Response:
    return _json(HTTPStatus.OK, session.info())


def _dataset(handler: _Handler, session: DevSession) -> _Response:
    return _json(HTTPStatus.OK, session.options(), cache="no-cache")


def _query(handler: _Handler, session: DevSession) -> _Response:
    handler.same_origin()
    query = _parsed(Query, handler.json_body(), "a builder query")
    return _json(HTTPStatus.OK, session.query(query))


def _build(handler: _Handler, session: DevSession) -> _Response:
    handler.same_origin()
    asked = _parsed(BuildRequest, handler.json_body(), "a Blick to build", _BUILD_SHAPE)
    return _json(HTTPStatus.OK, {"state": session.build(asked.id, asked.rebuild)})


def _runs(handler: _Handler, session: DevSession) -> _Response:
    return _json(HTTPStatus.OK, session.runs())


def _run(handler: _Handler, session: DevSession) -> _Response:
    handler.same_origin()
    paths = _parsed(RunRequest, handler.json_body(), "a run to load").paths
    if not paths:
        raise _Refusal(HTTPStatus.BAD_REQUEST, "no run path given; pick a run")
    listed = {str(folder.path) for folder in session.runs().runs}
    for path in paths:
        if path not in listed:
            if not Path(path).is_absolute():
                message = f"{path} is relative; send the absolute paths that dev/runs lists"
            elif Path(path).exists():
                message = f"{path} is not a folder that runs in [tool.blicket] matches"
            else:
                message = f"{Path(path).name} no longer exists; refresh the list"
            raise _Refusal(HTTPStatus.BAD_REQUEST, message)
    try:
        run = session.load(paths)
    except Refused:
        raise
    except BlicketError as error:
        raise _Refusal(HTTPStatus.UNPROCESSABLE_ENTITY, str(error)) from error
    return _json(HTTPStatus.OK, {"id": run})


type _Route = Callable[[_Handler, DevSession], _Response]

_ROUTES: dict[tuple[str, str], _Route] = {
    ("GET", f"/{MANIFEST}"): _manifest,
    ("GET", f"/{COMPARE}/{INDEX}"): _index,
    ("GET", "/dev/info"): _info,
    ("GET", "/dev/dataset"): _dataset,
    ("POST", "/dev/query"): _query,
    ("GET", "/dev/runs"): _runs,
    ("POST", "/dev/run"): _run,
    ("POST", "/dev/build"): _build,
}
# The methods of each path with a route, for the Allow header of a 405.
_METHODS: dict[str, list[str]] = {
    path: [method for method, route_path in _ROUTES if route_path == path] for _, path in _ROUTES
}


class _Handler(SimpleHTTPRequestHandler):
    """Serves the server's build directory, looking each path up in its viewer first, or the
    viewer and the routes of a dev session.

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
        """Read the request's headers, then take what it is answered from: the session, and what
        it serves at this moment, or the build directory."""
        if not super().parse_request():
            return False
        self.keep_alive = not self.close_connection
        length = self.headers.get("Content-Length", "")
        body = length not in ("", "0") or "Transfer-Encoding" in self.headers
        if self.command not in ("GET", "HEAD") or body:
            self.close_connection = True
        self.session = self.owner.session
        self.served = self.session.current() if self.session is not None else None
        self.root = self.owner.directory
        self.directory = str(self.root)
        return True

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
            if method == "GET" and (matched := _COMPARISON.fullmatch(path)):
                served, baseline = self.served, matched[1]
                if served is None or (body := served.comparison_json(baseline)) is None:
                    return _json(
                        HTTPStatus.NOT_FOUND, {"message": f"no comparison with {baseline}"}
                    )
                revision = {REVISION_HEADER: str(served.revision)}  # no-cache, as end_headers says
                return _Response(HTTPStatus.OK, body, headers=revision)
            if (allowed := _METHODS.get(path)) is not None:
                message, methods = {"message": f"{method} {path}"}, {"Allow": ", ".join(allowed)}
                return _json(HTTPStatus.METHOD_NOT_ALLOWED, message, headers=methods)
            if method == "GET" and (matched := _TABLE.fullmatch(path)):
                if (table := session.table(matched[1])) is None:
                    return _json(HTTPStatus.NOT_FOUND, {"message": _GONE})
                immutable = {"Cache-Control": "max-age=31536000, immutable"}
                return _Response(HTTPStatus.OK, table, "application/vnd.apache.parquet", immutable)
            if path == "/dev" or path.startswith("/dev/"):
                return _json(HTTPStatus.NOT_FOUND, {"message": f"no route {method} {path}"})
        except _Refusal as refusal:
            return _json(refusal.status, {"message": str(refusal)})
        except Refused as error:  # what the session cannot do in the state it is in
            return _json(HTTPStatus.CONFLICT, {"message": str(error)})
        except NoSuchBlick as error:
            return _json(HTTPStatus.NOT_FOUND, {"message": str(error)})
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

    def _other(self, method: str) -> None:
        """A method no route has: a path of a dev session's routes answers 405 with the methods
        it has, any other path under ``dev/`` 404, as JSON; elsewhere the method is not
        implemented."""
        if (response := self._route(method)) is None:
            self.send_error(HTTPStatus.NOT_IMPLEMENTED, f"Unsupported method ({method!r})")
            return
        self.wfile.write(self._respond(response).getvalue())

    def do_PUT(self) -> None:
        self._other("PUT")

    def do_DELETE(self) -> None:
        self._other("DELETE")

    def do_PATCH(self) -> None:
        self._other("PATCH")

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
        """Log failed requests only, but those of a dev session that say nothing new: the 404 of
        ``manifest.json`` and ``compare/index.json`` while no run is served, which the viewer asks
        for on every page load then, the 422 of a run that cannot be loaded, which the session
        reports itself, and the 409 of a query or a load refused while an expensive Blick builds
        or a run loads."""
        expected = self.session is not None and (self.path, code) in _SAID
        if isinstance(code, int) and code >= HTTPStatus.BAD_REQUEST and not expected:
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
