"""The ``blicket`` command line.

Exit codes: 0 success, 2 errors of any kind. typer alone exits 1 on an uncaught exception, so
``_App`` maps those to 2 for every command; click's usage errors exit 2 by themselves.

Streams: a command's result is the report on stdout, as text or, with ``--json``, as JSON; every
problem found in the project is part of it. What blicket cannot work around (a missing project,
an invalid ``[tool.blicket]``, a failing loader, a build that cannot be written) is one
``error: ...`` line on stderr instead, with the project's traceback under ``-v``; an unexpected
exception is an ``error:`` line, the traceback under ``-v``, and a line asking for a bug report.
What project code prints goes to stderr too.
"""

import importlib.metadata
import os
import sys
import traceback
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from blicket import serve
from blicket.builder import NothingToBuild, build
from blicket.comparison import compare_builds
from blicket.config import find_project_root, load_config
from blicket.discovery import discover
from blicket.errors import BlicketError, ConfigError, display_path
from blicket.model import Registry
from blicket.report import render_build, render_diff, render_list, render_list_json
from blicket.store import Store

ERROR_EXIT_CODE = 2
_VERBOSE = "blicket.verbose"


class _App(TyperGroup):
    """Runs a command; whatever fails exits with code 2, the traceback shown under ``-v``."""

    # Any: the base class takes typer's vendored click Context, which typer does not export.
    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except typer.Exit, typer.TyperException:  # click's own errors; typer shows them
            raise
        except typer.Abort:
            typer.echo("error: aborted", err=True)
        except BlicketError as error:
            typer.echo(f"error: {error}", err=True)
            if error.traceback and ctx.meta.get(_VERBOSE):
                typer.echo(error.traceback.rstrip(), err=True)
        except Exception as error:
            typer.echo(f"error: unexpected {type(error).__name__}: {error}", err=True)
            if ctx.meta.get(_VERBOSE):
                stack = "".join(traceback.format_tb(error.__traceback__)).rstrip()
                typer.echo(f"Traceback (most recent call last):\n{stack}", err=True)
                typer.echo("this is a bug in blicket; please report it", err=True)
            else:
                typer.echo("this is a bug in blicket; rerun with -v and report it", err=True)
        raise typer.Exit(ERROR_EXIT_CODE)


def _remember_verbose(ctx: typer.Context, verbose: bool) -> bool:
    """Keep ``-v`` where ``_App`` sees it: ``meta`` is shared by all contexts of one call."""
    ctx.meta[_VERBOSE] = verbose
    return verbose


ProjectOption = Annotated[
    Path | None,
    typer.Option(
        "--project",
        help="The project directory (default: the project containing the working directory).",
        show_default=False,
    ),
]
VerboseOption = Annotated[
    bool, typer.Option("-v", "--verbose", help="Show tracebacks.", callback=_remember_verbose)
]

app = typer.Typer(
    name="blicket",
    cls=_App,
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"blicket {importlib.metadata.version('blicket')}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", help="Print the version and exit.", callback=_print_version, is_eager=True
        ),
    ] = False,
) -> None:
    """A catalog of charts (Blicks) built from model runs."""


def _root(project: Path | None) -> Path:
    return project.resolve() if project else find_project_root()


@app.command("list")
def list_command(
    project: ProjectOption = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the Blicks and problems as JSON.")
    ] = False,
    verbose: VerboseOption = False,
) -> None:
    """Show the project's Blicks and any definition problems."""
    registry = discover(_root(project))
    finish(_list_report(registry, as_json, verbose), failed=registry.has_errors)


@app.command("build")
def build_command(
    runs: Annotated[
        list[Path],
        typer.Argument(
            help=(
                "A model run's output directory (several only if the project's loader combines "
                "them)."
            ),
            metavar="RUN_PATH...",
            show_default=False,
        ),
    ],
    project: ProjectOption = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Where build directories go (default: .blicket/build in the project).",
            show_default=False,
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the manifest as JSON.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Build every Blick of a run into a browsable build directory.

    Writes to .blicket/build/<id>/ (under --out if given) and prints the id; show it with
    blicket serve.
    """
    try:
        built = build(_root(project), runs, out=out)
    except NothingToBuild as error:
        typer.echo(f"error: {error}", err=True)
        finish(_list_report(error.registry, as_json, verbose), failed=True)
        return
    if as_json:
        text = built.manifest.model_dump_json(indent=2)
    else:
        text = render_build(built, verbose=verbose)
    finish(text, failed=built.manifest.has_errors)


@app.command("serve")
def serve_command(
    directory: Annotated[
        Path | None,
        typer.Argument(
            help="A build directory (default: the newest in the project).",
            metavar="[BUILD_DIR]",
            show_default=False,
        ),
    ] = None,
    port: Annotated[
        int, typer.Option(help="The port to listen on (0: any free port).", min=0, max=65535)
    ] = serve.DEFAULT_PORT,
    host: Annotated[str, typer.Option(help="The address to listen on.")] = serve.DEFAULT_HOST,
    open_browser: Annotated[
        bool, typer.Option("--open", help="Open the viewer in your browser.")
    ] = False,
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Serve a build directory on localhost; Ctrl-C stops."""
    path = (
        serve.newest_build(_root(project))
        if directory is None
        else serve.build_directory(directory)
    )
    server = serve.make_server(path, host, port)
    if directory is None:
        typer.echo(f"build {path.name} → {display_path(path, Path.cwd())}")
    typer.echo(f"viewer: {server.url}#/   (Ctrl-C stops)")
    if open_browser:
        webbrowser.open(server.url)
    serve.run(server)


@app.command("push")
def push_command(
    directory: Annotated[
        Path, typer.Argument(help="A build directory.", metavar="BUILD_DIR", show_default=False)
    ],
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Copy a build's manifest and tables into the project's store.

    The store is .blicket/store unless the store setting of the project names another directory.
    A build already in the store is left as it is.
    """
    pushed = _store(_root(project)).push(serve.build_directory(directory))
    already = " (in the store already)" if pushed.existed else ""
    finish(f"build {pushed.id} → {display_path(pushed.path, Path.cwd())}{already}", failed=False)


@app.command("diff")
def diff_command(
    baseline: Annotated[
        str,
        typer.Argument(
            help="The build to compare against.", metavar="BASELINE", show_default=False
        ),
    ],
    current: Annotated[
        str,
        typer.Argument(
            help="The build whose changes are reported.", metavar="CURRENT", show_default=False
        ),
    ],
    as_json: Annotated[bool, typer.Option("--json", help="Print the comparison as JSON.")] = False,
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Compare two builds Blick by Blick: the counts per flag and the Blicks that changed most.

    A build is a build directory or the id of a build in the project's store.
    A Blick is flagged value, schema, new, removed or error.
    Each top mover shows its magnitude and the row where it occurs.
    The magnitude is its largest change relative to the chart's scale, 0 to 1.
    """
    comparison = compare_builds(_build_path(baseline, project), _build_path(current, project))
    text = comparison.model_dump_json(indent=2) if as_json else render_diff(comparison)
    finish(text, failed=comparison.has_errors)


def _store(root: Path) -> Store:
    return Store(root / load_config(root).store)


def _build_path(given: str, project: Path | None) -> Path:
    """A build directory, given as its path or as the id of a build in the project's store."""
    if Path(given).is_dir():
        return serve.build_directory(Path(given))
    neither = f"{given} is neither a build directory nor"
    try:
        root = _root(project)
    except ConfigError:
        raise BlicketError(
            f"{neither} a build id (no project here, so no store; run inside the project or pass "
            "--project)"
        ) from None
    store = _store(root)
    if (found := store.path(given)) is not None:
        return found
    where = display_path(store.directory, Path.cwd())
    raise BlicketError(f"{neither} the id of a build in {where} (blicket push adds one)")


def finish(text: str, *, failed: bool) -> None:
    """Print a command's report on stdout and exit 2 if it holds an error.

    A reader that stops reading early, such as ``head``, ends the output without an error.
    """
    try:
        typer.echo(text)
    except BrokenPipeError:
        # Python flushes stdout again on exit; devnull keeps that quiet.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    if failed:
        raise typer.Exit(ERROR_EXIT_CODE)


def _list_report(registry: Registry, as_json: bool, verbose: bool) -> str:
    return render_list_json(registry) if as_json else render_list(registry, verbose=verbose)
