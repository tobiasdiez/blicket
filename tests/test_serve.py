"""``blicket serve``: what it answers, from where, and how it starts and stops."""

import http.client
import json
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from blicket import cli, serve, viewer
from tests.support import make_build_project, make_viewer

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


def fetch(server: serve.Server, path: str) -> tuple[http.client.HTTPResponse, bytes]:
    """GET ``path`` as it is, without the normalisation a URL library would apply."""
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(str(host), port)
    try:
        connection.request("GET", path)
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


def test_nothing_outside_the_directories(tmp_path: Path) -> None:
    build = make_build(tmp_path / "build")
    (tmp_path / "secret.txt").write_text("secret")
    (build / "link.txt").symlink_to(tmp_path / "secret.txt")
    with serving(build) as server:
        assert fetch(server, "/../secret.txt")[0].status == 404
        assert fetch(server, "/link.txt")[0].status == 404
        assert fetch(server, "/missing.json")[0].status == 404
        assert fetch(server, "/blicks/")[0].status == 404  # no directory listing
        assert fetch(server, "/%00")[0].status == 400


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
    assert result.stderr.startswith("error: no viewer found: install a blicket release")


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
