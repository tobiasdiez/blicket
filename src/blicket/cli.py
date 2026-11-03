"""The ``blicket`` command line.

Exit codes: 0 success, 1 a Blick flagged by ``check``, 2 errors of any kind. typer alone exits 1
on an uncaught exception, so ``_App`` maps those to 2 for every command; click's usage errors exit
2 by themselves.

Streams: a command's result is the report on stdout, as text or, with ``--json``, as JSON; every
problem found in the project is part of it. ``check --json`` prints the comparison, or ``null``,
and its text report on stderr. What blicket cannot work around (a missing project,
an invalid ``[tool.blicket]``, a failing loader, a build that cannot be written) is one
``error: ...`` line on stderr instead, with the project's traceback under ``-v``; an unexpected
exception is an ``error:`` line, the traceback under ``-v``, and a line asking for a bug report.
What project code prints goes to stderr too, as does the line of ``serve`` and ``dev`` that
the default port is taken and which one they listen on instead.
"""

import importlib.metadata
import os
import sys
import traceback
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup, TyperOption

from blicket import check, comparison, dev, serve
from blicket.builder import Build, NothingToBuild, build
from blicket.config import ProjectNotFound, find_project_root
from blicket.discovery import discover
from blicket.errors import BlicketError, ConfigError, display_path
from blicket.model import Registry
from blicket.report import (
    render_build,
    render_check,
    render_diff,
    render_list,
    render_list_json,
    render_markdown,
    render_markdown_no_baseline,
    render_push,
)
from blicket.store import Store

FLAGGED_EXIT_CODE = 1
ERROR_EXIT_CODE = 2
STEP_SUMMARY_ENV = "GITHUB_STEP_SUMMARY"
_VERBOSE = "blicket.verbose"
_BARE = "blicket.bare"
_HELP_OPTIONS = ["--help", "-h"]
_OWN_OPTIONS = {*_HELP_OPTIONS, "--version"}


class _App(TyperGroup):
    """Runs a command; whatever fails exits with code 2, the traceback shown under ``-v``.

    Without a command, the command is ``dev``: with no arguments, before an argument that is no
    command but names an existing path or contains a ``/``, and before an option the group does not
    have, unless the first argument after the options and their values is a command, which the
    options belong after. Anything else stays an unknown command, so that a typo is not taken
    for a run.
    """

    # Any: the base class takes typer's vendored click Context, which typer does not export.
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        ctx.meta[_BARE] = not args
        first = args[0] if args else ""
        if first.startswith("-"):
            dev = first.partition("=")[0] not in _OWN_OPTIONS
            at = _first_positional(args, self.commands["dev"])
            command = args[at] if at < len(args) else ""
            if dev and command in self.commands and not Path(command).exists():
                after = " ".join([command, *args[:at]])
                ctx.fail(f"No such option: {first} (options go after the command: blicket {after})")
        else:
            named = first != "" and ("/" in first or Path(first).exists())
            dev = not args or (first not in self.commands and named)
        return super().parse_args(ctx, ["dev", *args] if dev else args)

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except typer.Exit, typer.TyperException:  # click's own errors; typer shows them
            raise
        except typer.Abort:
            typer.echo("error: aborted", err=True)
        except BlicketError as error:
            # Bare blicket outside a project may have been meant as the help.
            bare = ctx.meta.get(_BARE) and isinstance(error, ProjectNotFound)
            hint = "; blicket --help lists the commands" if bare else ""
            typer.echo(f"error: {error}{hint}", err=True)
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


def _first_positional(args: list[str], command: Any) -> int:
    """Where the first positional argument of ``command`` is in ``args``: past its options, and the
    values of those that take one (``--out DIR``; ``--out=DIR`` is one argument), up to ``--``."""
    valued = {
        name
        for param in command.params
        if isinstance(param, TyperOption) and not param.is_flag
        for name in param.opts
    }
    at = 0
    while at < len(args) and args[at].startswith("-") and args[at] != "--":
        at += 2 if args[at] in valued else 1
    return at


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

_RUN_PATH_HELP = (
    "A model run's output directory (several only if the project's loader combines them)."
)
RunsArgument = Annotated[
    list[Path],
    typer.Argument(help=_RUN_PATH_HELP, metavar="RUN_PATH...", show_default=False),
]
OptionalRunsArgument = Annotated[
    list[Path] | None,
    typer.Argument(help=_RUN_PATH_HELP, metavar="[RUN_PATH]...", show_default=False),
]
OutOption = Annotated[
    Path | None,
    typer.Option(
        "--out",
        help="Where build directories go (default: .blicket/build in the project).",
        show_default=False,
    ),
]
AgainstOption = Annotated[
    str | None,
    typer.Option(
        "--against",
        help=(
            "The baseline: a build id in the store or a build directory; or a git ref whose "
            "history is searched instead of the build's commit."
        ),
        metavar="BUILD|REF",
        show_default=False,
    ),
]
PortOption = Annotated[
    int | None,
    typer.Option(
        help=(
            f"The port to listen on (default: {serve.DEFAULT_PORT}, or the next free one; "
            "0: any free port)."
        ),
        min=0,
        max=65535,
        show_default=False,
    ),
]
HostOption = Annotated[str, typer.Option(help="The address to listen on.")]
OpenOption = Annotated[bool, typer.Option("--open", help="Open the viewer in your browser.")]

app = typer.Typer(
    name="blicket",
    cls=_App,
    context_settings={"help_option_names": _HELP_OPTIONS},
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
    """A catalog of charts (Blicks) built from model runs.

    Without a command, blicket is blicket dev: blicket runs/x is blicket dev runs/x.
    """


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
    runs: RunsArgument,
    project: ProjectOption = None,
    out: OutOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the manifest as JSON.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Build every Blick of a run into a browsable build directory.

    Writes to .blicket/build/<id>/ (under --out if given) and prints the id; show it with
    blicket serve.
    """
    built = _build_or_exit(_root(project), runs, out, as_json, verbose)
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
    port: PortOption = None,
    host: HostOption = serve.DEFAULT_HOST,
    open_browser: OpenOption = False,
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Serve a build directory on localhost; Ctrl-C stops."""
    path = (
        serve.newest_build(_root(project))
        if directory is None
        else serve.build_directory(directory)
    )
    server = _make_server(path, host, port)
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
    """Copy a build's manifest, tables and comparisons into the project's store.

    The store is .blicket/store unless the store setting of the project names another directory.
    A build already in the store is left as it is.
    """
    pushed = Store.of_project(_root(project)).push(serve.build_directory(directory))
    finish(render_push(pushed), failed=False)


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
    Each top mover shows its largest change as a percent of the chart's
    scale, and the row where it occurs (--json: the magnitude, 0 to 1).
    """
    compared = comparison.compare_builds(
        _build_path(baseline, project), _build_path(current, project)
    )
    text = compared.model_dump_json(indent=2) if as_json else render_diff(compared)
    finish(text, failed=compared.has_errors)


@app.command("check")
def check_command(
    runs: RunsArgument,
    against: AgainstOption = None,
    push: Annotated[
        bool, typer.Option("--push", help="Push the build into the store, comparison included.")
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help=(
                "Print the comparison as JSON on stdout (null without baseline); the report goes "
                "to stderr."
            ),
        ),
    ] = False,
    project: ProjectOption = None,
    out: OutOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Build a run, compare it with its baseline, write the comparison.

    The baseline is the newest pushed build of the run's profile at the
    build's commit or an ancestor. --against names another baseline, or a
    git ref whose history is searched instead (in CI: --against origin/main).

    The comparison goes to compare/<baseline id>/ in the build directory, a
    Markdown summary to the file GITHUB_STEP_SUMMARY names. A Blick is
    flagged value, schema, new, removed or error; each top mover shows its
    largest change as a percent of the chart's scale (--json: the
    magnitude, 0 to 1).

    Exit codes: 0 nothing flagged or no baseline yet; 1 value, schema, new
    or removed; 2 errors or a baseline that cannot be resolved.
    """
    root = _root(project)
    built = _build_or_exit(root, runs, out, as_json, verbose, null=True)
    result = check.compare(built, root, against)
    resolution, compared = result.resolution, result.comparison
    pushed = Store.of_project(root).push(built.path) if push else None
    text = render_check(built, resolution, compared, pushed, result.warnings, verbose=verbose)
    markdown = (
        render_markdown(compared)
        if compared is not None
        else render_markdown_no_baseline(built.manifest, resolution)
    )
    if (problem := _append_step_summary(markdown)) is not None:
        text += f"\nwarning: {problem}"
    if as_json:
        _echo(text, err=True)
        text = compared.model_dump_json(indent=2) if compared is not None else "null"
    failed = (
        built.manifest.has_errors
        or resolution.failed
        or (compared is not None and compared.has_errors)
    )
    finish(text, failed=failed, flagged=compared is not None and compared.flagged > 0)


@app.command("dev")
def dev_command(
    runs: OptionalRunsArgument = None,
    against: AgainstOption = None,
    port: PortOption = None,
    host: HostOption = serve.DEFAULT_HOST,
    open_browser: OpenOption = False,
    project: ProjectOption = None,
    out: OutOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Check a run given or picked in the viewer and serve it with the Blick builder; Ctrl-C stops.

    Builds the run and compares it with its baseline as blicket check
    does, without pushing, then keeps the run in memory: "Build a Blick"
    in the viewer charts any quantity of the dataset that dataset(run) in
    the loader's module returns.

    Without RUN_PATH, serve a run picker: the viewer lists the folders the
    globs in runs in \\[tool.blicket] match, newest first; without runs,
    exit 2.

    Exit codes: 0 when stopped with Ctrl-C, whatever the build holds or a
    run picked in the viewer did; 2 when the session cannot start, without
    RUN_PATH also when runs is not set.
    """
    root = _root(project)
    # Bound first, so that a port in use fails before the run is loaded.
    server = _make_server(None, host, port)
    try:
        session, report = dev.start(root, runs or [], out=out, against=against, verbose=verbose)
    except BaseException:
        server.server_close()
        raise
    server.session = session
    _echo(report)
    typer.echo(f"viewer: {server.url}#/   (Ctrl-C stops)")
    if session.current() is None:
        typer.echo("pick a run in the viewer, or pass one: blicket RUN_PATH")
    if open_browser:
        webbrowser.open(server.url)
    serve.run(server)


def _make_server(directory: Path | None, host: str, port: int | None) -> serve.Server:
    """The server of ``serve`` or ``dev``; without ``port``, a line on stderr says when the
    default port is taken and which one the server listens on instead."""
    server = serve.make_server(directory, host, port)
    bound = server.server_address[1]
    if port is None and bound != serve.DEFAULT_PORT:
        typer.echo(f"port {serve.DEFAULT_PORT} is in use; listening on {bound} instead", err=True)
    return server


def _build_or_exit(
    root: Path,
    runs: list[Path],
    out: Path | None,
    as_json: bool,
    verbose: bool,
    *,
    null: bool = False,
) -> Build:
    """The build of ``runs``; when no Blick can be built, the report of why, and exit 2. With
    ``null``, ``--json`` prints ``null`` and the report goes to stderr, as ``check`` does."""
    try:
        return build(root, runs, out=out)
    except NothingToBuild as error:
        typer.echo(f"error: {error}", err=True)
        if as_json and null:
            _echo(render_list(error.registry, verbose=verbose), err=True)
            _echo("null")
        else:
            _echo(_list_report(error.registry, as_json, verbose))
        raise typer.Exit(ERROR_EXIT_CODE) from None


def _append_step_summary(markdown: str) -> str | None:
    """Append ``markdown`` to the file ``GITHUB_STEP_SUMMARY`` names, if set; why not, if not."""
    if not (summary := os.environ.get(STEP_SUMMARY_ENV)):
        return None
    try:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(markdown)
    except OSError as error:
        return f"cannot append to {STEP_SUMMARY_ENV} {summary}: {error.strerror or error}"
    return None


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
    store = Store.of_project(root)
    if (found := store.path(given)) is not None:
        return found
    where = display_path(store.directory, Path.cwd())
    raise BlicketError(f"{neither} the id of a build in {where} (blicket push adds one)")


def finish(text: str, *, failed: bool, flagged: bool = False) -> None:
    """Print a command's report on stdout; exit 2 if it holds an error, else 1 if it flags a
    Blick."""
    _echo(text)
    if failed:
        raise typer.Exit(ERROR_EXIT_CODE)
    if flagged:
        raise typer.Exit(FLAGGED_EXIT_CODE)


def _echo(text: str, *, err: bool = False) -> None:
    """Print ``text``; a reader that stops reading early, such as ``head``, ends the output
    without an error."""
    try:
        typer.echo(text, err=err)
    except BrokenPipeError:
        # Python flushes the stream again on exit; devnull keeps that quiet.
        stream = sys.stderr if err else sys.stdout
        os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())


def _list_report(registry: Registry, as_json: bool, verbose: bool) -> str:
    return render_list_json(registry) if as_json else render_list(registry, verbose=verbose)
