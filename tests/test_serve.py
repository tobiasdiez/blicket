"""``blicket serve`` and ``blicket dev``'s server: what it answers, from where, and how it starts
and stops."""

import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner, Result

from blicket import builder, cli, dev, serve, viewer
from blicket.errors import BlicketError
from blicket.query import Query
from tests.support import DATASET, LOADER, VALUES, make_build_project, make_run, make_viewer

YEARS = [2020, 2021, 2022]  # of VALUES

runner = CliRunner()


def invoke(*args: str | Path) -> Result:
    return runner.invoke(cli.app, ["serve", *map(str, args)])


def make_build(directory: Path, created_at: str = "2026-10-24T12:00:00Z") -> Path:
    """A build directory with a manifest and the table of a Blick ``flows/steel``."""
    (directory / "blicks" / "flows").mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"created_at": created_at}))
    (directory / "blicks" / "flows" / "steel.parquet").write_bytes(b"PAR1")
    return directory


@contextmanager
def serving(directory: Path) -> Generator[serve.Server]:
    """Serve ``directory`` on a free port in a thread."""
    server = serve.make_server(directory, port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def address(server: serve.Server) -> tuple[str, int]:
    """The host and port the server listens on."""
    host, port = server.server_address[:2]
    return str(host), port


def raw(server: serve.Server, data: bytes) -> bytes:
    """Send ``data`` on one connection and read until the server closes it."""
    with socket.create_connection(address(server), timeout=5) as connection:
        connection.sendall(data)
        received = b""
        while chunk := connection.recv(65536):
            received += chunk
    return received


def fetch(
    server: serve.Server, path: str, method: str = "GET"
) -> tuple[http.client.HTTPResponse, bytes]:
    """``method`` ``path`` as it is, without the normalisation a URL library would apply."""
    connection = http.client.HTTPConnection(*address(server))
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response, response.read()
    finally:
        connection.close()


def test_the_installed_viewer_comes_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build = make_viewer(make_build(tmp_path / "build"), "old")
    monkeypatch.setenv(viewer.VIEWER_ENV, str(make_viewer(tmp_path / "installed", "new")))
    with serving(build) as server:
        assert fetch(server, "/")[1] == b"<html>new</html>"
        assert fetch(server, "/_nuxt/new.js")[1] == b"// new"
        assert fetch(server, "/_nuxt/old.js")[1] == b"// old"  # the directory's own files remain
        assert fetch(server, "/blicks/flows/steel.parquet")[1] == b"PAR1"


def test_headers(tmp_path: Path) -> None:
    build = make_build(tmp_path / "build")
    compared = build / "compare" / "0123456789abcdef"
    (compared / "blicks" / "flows").mkdir(parents=True)
    for name in ("index.json", "0123456789abcdef/comparison.json"):
        (build / "compare" / name).write_text("{}")
    (compared / "blicks" / "flows" / "steel.parquet").write_bytes(b"PAR1")
    with serving(build) as server:
        rewritten = ["/compare/index.json", "/compare/0123456789abcdef/comparison.json"]
        for path in ("/", "/index.html", "/manifest.json", *rewritten):
            response, _ = fetch(server, path)
            assert (response.status, response.headers["Cache-Control"]) == (200, "no-cache")
        for path in (
            "/blicks/flows/steel.parquet",
            "/compare/0123456789abcdef/blicks/flows/steel.parquet",
        ):
            response, _ = fetch(server, path)
            assert (response.status, response.headers["Cache-Control"]) == (200, None)
        assert (response.version, response.headers["Content-Length"]) == (11, "4")  # HTTP/1.1


def test_nothing_outside_the_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build = make_build(tmp_path / "build")
    (tmp_path / "secret.txt").write_text("secret")
    (build / "link.txt").symlink_to(tmp_path / "secret.txt")
    with serving(build) as server:
        assert fetch(server, "/../secret.txt")[0].status == 404
        assert fetch(server, "/link.txt")[0].status == 404
        assert fetch(server, "/missing.json")[0].status == 404
        assert fetch(server, "/blicks/")[0].status == 404  # no directory listing
        assert fetch(server, "/%00")[0].status == 400
        assert fetch(server, "/%ED%A0%80")[0].status == 404  # a lone surrogate, no file name
        for line, status in (
            (b"\x01\x02 garbage here", b"400"),
            (b"GET", b"400"),
            (b"GET / HTTP/9.9", b"505"),
            (b"GET /" + b"a" * 70_000 + b" HTTP/1.1", b"414"),
        ):
            assert raw(server, line + b"\r\n\r\n").split(b" ", 2)[1] == status
        # A request line that cannot be parsed takes nothing from the request before it.
        too_long = b"GET /" + b"a" * 70_000 + b" HTTP/1.1\r\n\r\n"
        received = raw(server, b"GET /manifest.json HTTP/1.1\r\nHost: x\r\n\r\n" + too_long)
        first, second = received.split(b"HTTP/1.1 414", 1)
        assert b"Cache-Control: no-cache" in first
        assert b"Cache-Control" not in second
    assert "Traceback" not in capsys.readouterr().err


def test_a_closed_connection_is_no_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = serve.make_server(make_build(tmp_path / "build"), port=0)
    try:
        for error, reported in ((ConnectionResetError(), False), (ValueError("bug"), True)):
            try:
                raise error
            except Exception:
                server.handle_error(None, ("127.0.0.1", 1))
            assert ("Traceback" in capsys.readouterr().err) is reported
    finally:
        server.server_close()


def test_serve_prints_the_url_and_stops_on_ctrl_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = make_build(tmp_path / "build")

    def interrupt(self: serve.Server) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(serve.Server, "serve_forever", interrupt)
    result = invoke(build, "--port", "0")
    assert result.exit_code == 0
    (url,) = result.stdout.splitlines()
    assert url.startswith("viewer: http://127.0.0.1:")
    assert url.endswith("/#/   (Ctrl-C stops)")
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    result = invoke(build, "--port", "0", "--open")
    assert result.stdout.startswith("viewer: http://127.0.0.1:")
    assert opened == [result.stdout.split()[1].removesuffix("#/")]


def test_no_argument_serves_the_build_made_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_build_project(tmp_path, {})
    builds = root / ".blicket" / "build"
    # The manifest's time decides, not the order of writing.
    make_build(builds / "newest", "2026-10-24T12:00:00Z")
    make_build(builds / "older", "2026-10-23T12:00:00Z")
    (builds / "damaged").mkdir()
    (builds / "damaged" / "manifest.json").write_text("{")
    (builds / ".tmp-1-abc").mkdir()
    served: list[serve.Server] = []
    monkeypatch.setattr(serve, "run", served.append)
    monkeypatch.chdir(root)
    result = invoke("--port", "0")
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("build newest → .blicket/build/newest\nviewer: http://")
    assert served[0].directory == (builds / "newest").resolve()
    served[0].server_close()


def test_serve_needs_a_viewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(viewer.VIEWER_ENV)
    root = make_build_project(tmp_path, {})
    make_build(root / ".blicket" / "build" / "only")
    monkeypatch.chdir(root)
    result = invoke()  # the build line comes only once the server is up
    assert (result.exit_code, result.stdout) == (2, "")
    assert result.stderr.startswith("error: no viewer found: install blicket from PyPI")


def test_serve_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = invoke(tmp_path / "nothere")
    assert (missing.exit_code, missing.stderr) == (
        2,
        f"error: build directory {tmp_path / 'nothere'} does not exist\n",
    )
    no_manifest = invoke(tmp_path)
    assert no_manifest.exit_code == 2
    assert "has no manifest.json; pass a build directory" in no_manifest.stderr
    monkeypatch.chdir(make_build_project(tmp_path, {}))
    assert "error: no build in" in invoke().stderr
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        result = invoke(make_build(tmp_path / "build"), "--port", port)
    assert result.exit_code == 2
    out_of_range = invoke(tmp_path / "build", "--port", "99999")
    assert out_of_range.exit_code == 2
    assert "not in the range 0<=x<=65535" in out_of_range.output
    assert result.stderr == (
        f"error: cannot serve on 127.0.0.1:{port}: the port is in use; pass another with --port\n"
    )


def test_a_taken_default_port_moves_the_server_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[serve.Server] = []
    monkeypatch.setattr(serve, "run", served.append)
    build = make_build(tmp_path / "build")
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        monkeypatch.setattr(serve, "DEFAULT_PORT", port)
        result = invoke(build)
        bound = address(served[0])[1]
        served[0].server_close()
        assert port < bound < port + serve._DEFAULT_PORTS  # the next free one
        assert result.stdout == f"viewer: http://127.0.0.1:{bound}/#/   (Ctrl-C stops)\n"
        assert result.stderr == f"port {port} is in use; listening on {bound} instead\n"
        monkeypatch.setattr(serve, "_DEFAULT_PORTS", 1)
        with serve.make_server(build) as anywhere:
            assert address(anywhere)[1] != port


# ---------------------------------------------------------------------------------------------
# blicket dev's routes

FAILING = LOADER + DATASET.replace("return Values(run)", "raise KeyError('flows')")


def session(tmp_path: Path, loader: str = LOADER + DATASET) -> dev.Session:
    """The session of a project with one Blick and the loader module ``loader``."""
    root = make_build_project(tmp_path, {"blicks/a.py": VALUES, "model_loader.py": loader})
    return dev.start(root, [make_run(root / "runs" / "a")])[0]


@contextmanager
def dev_serving(tmp_path: Path, loader: str = LOADER + DATASET) -> Generator[serve.Server]:
    """Serve a session on a free port in a thread."""
    with serving_session(session(tmp_path, loader)) as server:
        yield server


@contextmanager
def serving_session(started: dev.Session) -> Generator[serve.Server]:
    """Serve the session ``started`` on a free port in a thread."""
    server = serve.make_server(port=0)
    server.session = started
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def the_session(server: serve.Server) -> dev.Session:
    assert isinstance(server.session, dev.Session)
    return server.session


def request(
    server: serve.Server,
    path: str = "/dev/query",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """POST ``body`` to ``path`` with exactly ``headers``; return the status and the JSON, if
    the answer is JSON."""
    connection = http.client.HTTPConnection(*address(server))
    try:
        connection.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        connection.endheaders(body)
        response = connection.getresponse()
        text = response.read()
        is_json = response.headers.get_content_type() == "application/json"
        return response.status, json.loads(text) if is_json else text
    finally:
        connection.close()


def viewer_headers(server: serve.Server, body: bytes) -> dict[str, str]:
    """The headers the viewer's page sends with ``body``."""
    host, port = address(server)
    return {
        "Host": f"{host}:{port}",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "Sec-Fetch-Site": "same-origin",
    }


def post(server: serve.Server, query: object, changed: dict[str, str] | None = None) -> Any:
    """POST ``query`` as the viewer's page does, with the headers ``changed`` (``""`` drops one);
    return the status and the JSON."""
    body = json.dumps(query).encode()
    sent = {**viewer_headers(server, body), **(changed or {})}
    return request(server, body=body, headers={k: v for k, v in sent.items() if v})


QUERY = {"quantities": ["values"], "plot": "line", "mapping": {"x": "year"}}


def test_dev_serves_the_manifest_from_memory_with_the_dev_header(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        (server.directory / "manifest.json").write_text("{}")  # what is on disk is not served
        response, body = fetch(server, "/manifest.json")
        assert (response.status, response.headers["Blicket-Dev"]) == (200, "1")
        assert response.headers["Cache-Control"] == "no-cache"
        manifest = json.loads(body)
        assert manifest["build"]["id"] == server.directory.name
        assert manifest["blicks"][0]["source"]["file"] == "blicks/a.py"  # relative to the root
    with serving(server.directory) as plain:
        response, body = fetch(plain, "/manifest.json")
        assert (body, response.headers["Blicket-Dev"]) == (b"{}", None)
        assert fetch(plain, "/dev/info")[0].status == 404


def test_each_request_reads_the_build_served_when_it_comes(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        other = make_build(tmp_path / "other")
        (other / "only-here.txt").write_text("here")
        current = the_session(server)
        connection = http.client.HTTPConnection(*address(server))
        try:
            connection.request("GET", "/only-here.txt")
            first = connection.getresponse()
            first.read()
            was = current.serving
            assert was is not None
            moved = dev.Current(replace(was.served.build, path=other), was.served.compared)
            current.serving = replace(was, served=moved)
            connection.request("GET", "/only-here.txt")  # the same connection, kept alive
            second = connection.getresponse()
            assert (first.status, second.status, second.read()) == (404, 200, b"here")
        finally:
            connection.close()


def test_dev_info_and_dataset(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        response, body = fetch(server, "/dev/info")
        assert response.headers["Cache-Control"] == "no-store"
        assert json.loads(body) == {
            "root": str(tmp_path / "project"),
            "dataset": True,
            "message": None,
            "failed": False,
        }
        response, body = fetch(server, "/dev/dataset")
        assert response.headers["Cache-Control"] == "no-cache"
        options = json.loads(body)
        assert options["quantities"] == [
            {
                "name": "values",
                "title": "values",
                "unit": "t",
                "dimensions": ["year"],
                "additive": True,
                "group": None,
            }
        ]
        assert options["dimensions"] == [
            {"name": "year", "dtype": "integer", "values": [2020, 2021, 2022]}
        ]
        assert [p["name"] for p in options["plots"]] == [
            "line",
            "stacked_area",
            "bar",
            "stacked_bar",
            "sankey",
        ]
        assert fetch(server, "/dev/nothing")[0].status == 404
        response, body = fetch(server, "/dev/query")  # a GET
        assert (response.status, response.headers["Allow"]) == (405, "POST")


@pytest.mark.parametrize(
    ("loader", "failed", "message"),
    [
        (LOADER, False, "no dataset(run) next to load_run in model_loader;"),
        (FAILING, True, "dataset(run) in model_loader raised KeyError: 'flows'"),
    ],
)
def test_dev_without_a_dataset(tmp_path: Path, loader: str, failed: bool, message: str) -> None:
    with dev_serving(tmp_path, loader) as server:
        info = json.loads(fetch(server, "/dev/info")[1])
        assert (info["dataset"], info["failed"]) == (False, failed)
        assert info["message"].startswith(message)
        response, body = fetch(server, "/dev/dataset")
        assert (response.status, response.headers["Cache-Control"]) == (404, "no-cache")
        assert json.loads(body) == {"message": info["message"]}
        assert post(server, QUERY) == (404, {"message": info["message"]})


def test_dev_query_and_its_table(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        status, entry = post(server, {**QUERY, "values": {"year": ["2021", "2022"]}})
        assert (status, entry["status"], entry["rows"]) == (200, "ok", 2)
        assert entry["definition"]["plot"] == {
            "type": "line",
            "mapping": {"x": "year", "y": "value"},
        }
        digest = entry["hash"].removeprefix("parquet-sha256:")
        assert entry["data"] == f"dev/tables/{digest}.parquet"
        response, table = fetch(server, f"/{entry['data']}?{entry['hash']}")
        assert response.status == 200
        assert response.headers["Cache-Control"] == "max-age=31536000, immutable"
        assert hashlib.sha256(table).hexdigest() == digest
        assert pl.read_parquet(table)["value"].to_list() == [2.0, 3.0]
        assert fetch(server, f"/dev/tables/{'0' * 64}.parquet")[0].status == 404
        status, entry = post(server, {**QUERY, "plot": "pie"})
        assert (status, entry["status"], entry["definition"]) == (200, "error", None)


def test_a_query_problem_names_project_files_relative_to_the_root(tmp_path: Path) -> None:
    raising = LOADER + DATASET.replace("values):\n", "values):\n        1 / 0\n")
    with dev_serving(tmp_path, raising) as server:
        status, entry = post(server, QUERY)
        (problem,) = entry["problems"]
        assert (status, problem["source"]["file"]) == (200, "model_loader.py")


def test_dev_keeps_the_tables_used_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "KEPT_TABLES", 2)
    with dev_serving(tmp_path) as server:
        a, b, c = ({**QUERY, "values": {"year": [year]}} for year in YEARS)
        paths = {name: post(server, q)[1]["data"] for name, q in (("a", a), ("b", b))}
        post(server, a)  # used again, so b is the one used longest ago
        paths["c"] = post(server, c)[1]["data"]
        status = {name: fetch(server, f"/{path}")[0].status for name, path in paths.items()}
        assert status == {"a": 200, "b": 404, "c": 200}


@pytest.mark.parametrize(
    ("headers", "status", "message"),
    [
        ({"Sec-Fetch-Site": "cross-site"}, 403, "a request comes from the viewer's own page"),
        ({"Sec-Fetch-Site": ""}, 403, "a request comes from the viewer's own page"),
        ({"Host": "attacker.example:80"}, 403, "the Host header names another server"),
        ({"Host": ""}, 403, "the Host header names another server"),
        ({"Content-Type": "text/plain"}, 415, "the body is sent as Content-Type: application/json"),
        ({"Content-Length": ""}, 411, "the request has no Content-Length"),
        ({"Content-Length": "-1"}, 400, "Content-Length '-1' is no length"),
        ({"Content-Length": "1_0"}, 400, "Content-Length '1_0' is no length"),
        (
            {"Content-Length": "\N{SUPERSCRIPT TWO}"},
            400,
            "Content-Length '\N{SUPERSCRIPT TWO}' is no",
        ),
        ({"Content-Length": str(2 << 20)}, 413, "the body exceeds 1048576 bytes"),
        ({"Content-Length": "9" * 5000}, 413, "the body exceeds 1048576 bytes"),
    ],
)
def test_dev_refuses_queries(
    tmp_path: Path, headers: dict[str, str], status: int, message: str
) -> None:
    with dev_serving(tmp_path) as server:
        answered, body = post(server, QUERY, headers)
        assert answered == status
        assert body["message"].startswith(message)


def test_dev_answers_the_viewer_and_its_address_bar(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        _, port = address(server)
        assert post(server, QUERY, {"Host": f"localhost:{port}"})[0] == 200
        assert post(server, QUERY, {"Sec-Fetch-Site": "none"})[0] == 200
        status, body = post(server, {"quantities": []})
        assert status == 400
        assert body["message"].startswith("not a builder query: quantities:")


def test_a_failing_route_answers_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(self: dev.Session, query: object) -> bytes:
        raise RuntimeError("a bug")

    monkeypatch.setattr(dev.Session, "query", broken)
    with dev_serving(tmp_path) as server:
        assert post(server, QUERY) == (500, {"message": "internal error; see the terminal"})
    assert "RuntimeError: a bug" in capsys.readouterr().err


def test_a_post_elsewhere_is_not_found(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        body = b"{}"
        assert request(server, "/dev/info", body, viewer_headers(server, body))[0] == 405
        assert request(server, "/elsewhere", body, viewer_headers(server, body))[0] == 404
    with serving(make_build(tmp_path / "build")) as plain:
        assert request(plain, "/dev/query", body, viewer_headers(plain, body))[0] == 404


def test_an_unread_body_is_never_read_as_a_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[object] = []
    query = dev.Session.query

    def recording(self: dev.Session, question: Query) -> bytes:
        asked.append(question)
        return query(self, question)

    monkeypatch.setattr(dev.Session, "query", recording)
    with dev_serving(tmp_path) as server:
        host, port = address(server)
        body = json.dumps(QUERY)
        inner = (  # a query the server would run, would it read it as a request
            f"POST /dev/query HTTP/1.1\r\nHost: {host}:{port}\r\nSec-Fetch-Site: same-origin\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}"
        ).encode()
        follow = f"GET /dev/info HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode()
        for path in ("/dev/info", "/elsewhere"):
            outer = (
                f"POST {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                f"Content-Type: text/plain\r\nContent-Length: {len(inner)}\r\n\r\n"
            ).encode()
            received = raw(server, outer + inner + follow)
            assert received.count(b"HTTP/1.1 ") == 1, received
            assert received.count(b"\r\nConnection: close\r\n") == 1
        chunked = (
            f"GET /dev/info HTTP/1.1\r\nHost: {host}:{port}\r\nTransfer-Encoding: chunked\r\n\r\n"
        )
        chunk = f"{len(inner):x}\r\n".encode() + inner + b"\r\n0\r\n\r\n"
        received = raw(server, chunked.encode() + chunk + follow)
        assert received.count(b"HTTP/1.1 ") == 1, received
        assert received.count(b"\r\nConnection: close\r\n") == 1
        # A query whose body is framed twice: refused, and the rest never read as a request.
        framed = (
            f"POST /dev/query HTTP/1.1\r\nHost: {host}:{port}\r\nSec-Fetch-Site: same-origin\r\n"
        )
        framed += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        for second in ("Transfer-Encoding: chunked", f"Content-Length: {len(body) + len(inner)}"):
            received = raw(server, f"{framed}{second}\r\n\r\n{body}".encode() + inner + follow)
            assert received.startswith(b"HTTP/1.1 400"), received
            assert received.count(b"HTTP/1.1 ") == 1, received
            assert received.count(b"\r\nConnection: close\r\n") == 1
        assert asked == []  # the queries inside were never run
        assert post(server, QUERY)[0] == 200
        assert len(asked) == 1
    with serving(make_build(tmp_path / "build")) as plain:
        follow = b"GET /manifest.json HTTP/1.1\r\nHost: x\r\n\r\n"
        received = raw(plain, b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}" + follow)
        assert received.count(b"HTTP/1.1 ") == 1
        received = raw(
            plain, b"GET /manifest.json HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}"
        )
        assert received.startswith(b"HTTP/1.1 200")
        assert received.count(b"\r\nConnection: close\r\n") == 1  # a static answer says so too


def test_head_of_the_dev_routes(tmp_path: Path) -> None:
    with dev_serving(tmp_path) as server:
        response, body = fetch(server, "/dev/query", "HEAD")
        assert (response.status, response.headers["Allow"], body) == (405, "POST", b"")
        response, body = fetch(server, "/dev/info", "HEAD")
        assert (response.status, body) == (200, b"")
        assert int(response.headers["Content-Length"]) > 0


def test_a_body_shorter_than_announced_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve, "_BODY_TIMEOUT", 0.2)
    with dev_serving(tmp_path) as server:
        headers = viewer_headers(server, b"{}" * 10)
        start = (
            b"POST /dev/query HTTP/1.1\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers.items()).encode()
        )
        assert raw(server, start + b"\r\n{}") == b""  # closed without an answer
        assert post(server, QUERY)[0] == 200  # and the server goes on


# ---------------------------------------------------------------------------------------------
# blicket dev started without a run: the run picker's routes

NOW = 1_700_000_000
NO_RUN = {"message": "no run served yet"}


@contextmanager
def picking(tmp_path: Path, loader: str = LOADER + DATASET) -> Generator[serve.Server]:
    """Serve a session started without a run, of a project with one Blick whose runs = ["runs/*"]
    matches the runs a, b and bad (values that do not parse), changed last in this order."""
    files = {"blicks/a.py": VALUES, "model_loader.py": loader}
    root = make_build_project(tmp_path, files, 'runs = ["runs/*"]\n')
    for age, name, values in ((300, "a", "1 2 3"), (200, "b", "1 2 3.3"), (100, "bad", "one")):
        os.utime(make_run(root / "runs" / name, values), (NOW - age, NOW - age))
    with serving_session(dev.start(root, [])[0]) as server:
        yield server


def run_path(server: serve.Server, name: str) -> str:
    """The path of the run ``name`` as ``dev/runs`` lists it."""
    return str(the_session(server).root / "runs" / name)


def post_run(server: serve.Server, body: object, changed: dict[str, str] | None = None) -> Any:
    """POST ``body`` to ``dev/run`` as the viewer's page does, with the headers ``changed``
    (``""`` drops one); return the status and the JSON."""
    data = json.dumps(body).encode()
    sent = {**viewer_headers(server, data), **(changed or {})}
    return request(server, "/dev/run", data, {k: v for k, v in sent.items() if v})


def pick(server: serve.Server, *names: str) -> Any:
    """Load the runs ``names`` as the picker does; the status and the JSON."""
    return post_run(server, {"paths": [run_path(server, name) for name in names]})


def test_without_a_run_dev_serves_the_viewer_alone(tmp_path: Path) -> None:
    with picking(tmp_path) as server:
        assert fetch(server, "/")[1] == b"<html>viewer</html>"
        assert fetch(server, "/runs/a/values.txt")[0].status == 404  # nothing of the project
        response, body = fetch(server, "/manifest.json")
        assert (response.status, response.headers["Blicket-Dev"]) == (404, "1")
        assert response.headers["Cache-Control"] == "no-cache"
        assert json.loads(body) == NO_RUN
        assert json.loads(fetch(server, "/dev/info")[1]) == {
            "root": str(tmp_path / "project"),
            "dataset": False,
            "message": "no run served yet",
            "failed": False,
        }
        response, body = fetch(server, "/dev/dataset")
        assert (response.status, json.loads(body)) == (404, NO_RUN)
        assert post(server, QUERY) == (404, NO_RUN)
        assert fetch(server, f"/dev/tables/{'0' * 64}.parquet")[0].status == 404
        response, _ = fetch(server, "/dev/run")
        assert (response.status, response.headers["Allow"]) == (405, "POST")


def test_dev_runs_lists_the_folders_runs_matches_newest_first(tmp_path: Path) -> None:
    with picking(tmp_path) as server:
        response, body = fetch(server, "/dev/runs")
        assert (response.status, response.headers["Cache-Control"]) == (200, "no-store")
        when = {
            name: datetime.fromtimestamp(NOW - age, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for name, age in (("a", 300), ("b", 200), ("bad", 100))
        }
        assert json.loads(body) == {
            "patterns": ["runs/*"],
            "runs": [
                {"path": run_path(server, name), "name": name, "modified": when[name]}
                for name in ("bad", "b", "a")
            ],
        }
        make_run(the_session(server).root / "runs" / "c")  # a run that lands while dev waits
        names = [run["name"] for run in json.loads(fetch(server, "/dev/runs")[1])["runs"]]
        assert names == ["c", "bad", "b", "a"]


def test_dev_run_loads_the_run_picked_and_serves_its_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with picking(tmp_path) as server:
        assert fetch(server, "/manifest.json")[0].status == 404
        assert pick(server, "b") == (200, {"id": "b"})
        lines = capsys.readouterr().out.splitlines()
        assert re.fullmatch(r"\d\d:\d\d:\d\d loading runs/b, picked in the viewer", lines[0])
        assert any(line.startswith("run b · profile test · ") for line in lines)
        assert lines[-1] == "builder: 1 quantity, 1 dimension"
        response, body = fetch(server, "/manifest.json")
        assert (response.status, response.headers["Blicket-Dev"]) == (200, "1")
        run = json.loads(body)["run"]
        assert (run["id"], run["paths"]) == ("b", ["runs/b"])
        loaded = the_session(server).serving
        assert loaded is not None
        assert loaded.prepared.shown == ("runs/b",)  # the session keeps what the run needed
        assert fetch(server, "/dev/dataset")[0].status == 200
        assert post(server, QUERY)[0] == 200
        assert pick(server, "a") == (
            409,
            {
                "message": "a run is served already; reload the viewer, or restart blicket dev to "
                "pick another"
            },
        )


def test_a_run_that_cannot_be_loaded_leaves_the_picker_open(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with picking(tmp_path) as server:
        capsys.readouterr()
        status, body = pick(server, "bad")
        assert status == 422
        assert body["message"].startswith(
            "loader model_loader:load_run raised ValueError: could not convert string to float: "
            "'one' (raised at model_loader.py:"
        )
        printed = capsys.readouterr()
        assert re.fullmatch(r"\d\d:\d\d:\d\d loading runs/bad, picked in the viewer\n", printed.out)
        assert printed.err == f"error: cannot load runs/bad: {body['message']}\n"  # no log line
        assert fetch(server, "/manifest.json")[0].status == 404
        the_session(server).verbose = True
        assert pick(server, "bad")[0] == 422
        assert 'model_loader.py", line' in capsys.readouterr().err
        assert pick(server, "a") == (200, {"id": "a"})


def test_several_runs_picked_are_one_run_for_the_loader(tmp_path: Path) -> None:
    with picking(tmp_path, LOADER.replace("selection.paths[0]", "selection.path")) as server:
        status, body = pick(server, "a", "b")
        assert status == 422
        assert body["message"].startswith(
            "loader model_loader:load_run raised ValueError: this loader takes one run path, got 2"
        )
        assert pick(server, "a") == (200, {"id": "a"})


@pytest.mark.parametrize(
    ("body", "headers", "status", "message"),
    [
        ({"paths": []}, {}, 400, "no run path given; pick a run"),
        ({"paths": ["/"]}, {}, 400, "/ is not a folder that runs in [tool.blicket] matches"),
        ({"paths": "runs/a"}, {}, 400, "not a run to load: paths: Input should be a valid array"),
        ({"paths": [1]}, {}, 400, "not a run to load: paths.0: Input should be a valid string"),
        ({}, {}, 400, "not a run to load: paths: Field required"),
        ([], {}, 400, "not a run to load: Input should be"),
        ({"paths": []}, {"Sec-Fetch-Site": "cross-site"}, 403, "a request comes from the viewer"),
    ],
)
def test_dev_run_refuses(
    tmp_path: Path, body: object, headers: dict[str, str], status: int, message: str
) -> None:
    with picking(tmp_path) as server:
        answered, said = post_run(server, body, headers)
        assert (answered, said["message"][: len(message)]) == (status, message)
        assert fetch(server, "/manifest.json")[0].status == 404


def test_a_folder_gone_since_the_list_is_named(tmp_path: Path) -> None:
    with picking(tmp_path) as server:
        shutil.rmtree(the_session(server).root / "runs" / "a")
        assert pick(server, "a") == (400, {"message": "a no longer exists; refresh the list"})
        assert pick(server, "b") == (200, {"id": "b"})


def test_dev_run_loads_one_run_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entered, release = threading.Event(), threading.Event()
    load = builder.load

    def slow(prepared: builder.Prepared) -> builder.LoadedRun:
        entered.set()
        release.wait(5)
        return load(prepared)

    monkeypatch.setattr(builder, "load", slow)
    with picking(tmp_path) as server:
        answers: list[Any] = []
        first = threading.Thread(target=lambda: answers.append(pick(server, "a")))
        first.start()
        try:
            assert entered.wait(5)
            assert pick(server, "b") == (409, {"message": "another run is loading; wait for it"})
        finally:
            release.set()
            first.join()
        assert answers == [(200, {"id": "a"})]


def test_run_needs_a_directory_or_a_session() -> None:
    with pytest.raises(BlicketError, match="no build directory and no session"):
        serve.run(serve.make_server(port=0))


@pytest.mark.parametrize(
    ("bound", "host", "own"),
    [
        ("127.0.0.1", "127.0.0.1:8765", True),
        ("127.0.0.1", "localhost:8765", True),
        ("127.0.0.1", "[::1]:8765", True),
        ("127.0.0.1", "10.0.0.5:8765", True),  # an address names the machine, as a name cannot
        ("127.0.0.1", "127.0.0.1:9999", False),
        ("127.0.0.1", "127.0.0.1", False),  # no port: 80
        ("127.0.0.1", "", False),
        ("127.0.0.1", "attacker.example:8765", False),
        ("127.0.0.1", "[::1", False),
        ("0.0.0.0", "mybox:8765", True),
        ("127.0.0.1", "mybox:8765", False),
    ],
)
def test_own_host(monkeypatch: pytest.MonkeyPatch, bound: str, host: str, own: bool) -> None:
    monkeypatch.setattr(socket, "gethostname", lambda: "mybox")
    assert serve._own_host(host, (bound, 8765)) is own
