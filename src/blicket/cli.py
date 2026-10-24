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
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from typer.core import TyperGroup

from blicket.builder import Build, NothingToBuild, build
from blicket.config import PYPROJECT, find_project_root
from blicket.discovery import discover
from blicket.errors import NOWHERE, BlicketError, Kind, Problem, Source, display_path
from blicket.manifest import Manifest
from blicket.model import Blick, BlickEntry, Registry

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
        help=(
            f"The project directory, which holds the {PYPROJECT} with \\[tool.blicket]. "
            "Default: found by walking up from the working directory."
        ),
        show_default=False,
    ),
]
VerboseOption = Annotated[
    bool, typer.Option("-v", "--verbose", help="Show tracebacks.", callback=_remember_verbose)
]

app = typer.Typer(
    name="blicket",
    cls=_App,
    help="Storybook for scientific model outputs.",
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
    """Storybook for scientific model outputs."""


def _root(project: Path | None) -> Path:
    return project.resolve() if project else find_project_root()


@app.command("list")
def list_command(
    project: ProjectOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """List the project's groups and Blicks, then warnings and errors.

    Exit codes: 0 success, 2 errors.
    """
    registry = discover(_root(project))
    finish(_list_report(registry, as_json, verbose), failed=registry.has_errors)


@app.command("build")
def build_command(
    runs: Annotated[
        list[Path],
        typer.Argument(
            help="The run directory, or several; the project's loader decides what they mean.",
            metavar="RUN_PATH...",
            show_default=False,
        ),
    ],
    project: ProjectOption = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help=(
                "The directory that receives the build directory <id>/. "
                "Default: .blicket/build in the project."
            ),
            show_default=False,
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the manifest.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Load a run, build every Blick's table and write a build directory with its manifest.

    Without a Blick that can be built, it prints what blicket list would and writes nothing.

    Exit codes: 0 every Blick built, 2 errors.
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
    """The report of ``blicket list``; as JSON with the absolute root, since it is local."""
    if not as_json:
        return render_list(registry, verbose=verbose)
    context = {"root": registry.root}
    # Built and failed Blicks alike, in the order of their definitions, as the manifest has them.
    entries = sorted(
        [*(blick.entry() for blick in registry.blicks.values()), *registry.failed],
        key=lambda entry: entry.source or NOWHERE,
    )

    def dump(model: BaseModel) -> Any:
        return model.model_dump(mode="json", context=context)

    report = {
        "blicket": importlib.metadata.version("blicket"),
        "root": str(registry.root),
        "groups": [dump(group) for group in registry.groups.values()],
        "blicks": [dump(entry) for entry in entries],
        "aliases": dict(registry.aliases),
        "errors": [dump(error) for error in registry.errors],
        "warnings": [dump(warning) for warning in registry.warnings],
    }
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------------------------
# Text output


def _headline(kind: str) -> str:
    """What a file-level problem is called in the report: the kind in words."""
    return {Kind.IMPORT: "import failed", Kind.GROUP: "bk.group()"}.get(
        kind, kind.replace("_", " ")
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


type _Block = tuple[Source | None, list[str]]


def _section(title: str, blocks: Sequence[_Block]) -> list[str]:
    """A titled section of blocks ordered by their location; nothing without blocks."""
    if not blocks:
        return []
    lines = ["", title]
    for _, block in sorted(blocks, key=lambda item: item[0] or NOWHERE):
        lines.extend(block)
    return lines


def render_list(registry: Registry, *, verbose: bool = False) -> str:
    """The text of ``blicket list``: groups with their Blicks, a summary, warnings, errors."""
    root = registry.root
    lines = [*_project_line(root), *_group_lines(registry)]
    if lines:
        lines.append("")
    lines.append(_summary(registry))
    warnings = [(w.source, _problem_lines(w, root)) for w in registry.warnings]
    errors = [(e.source, _problem_lines(e, root, verbose)) for e in registry.errors]
    errors += [
        (blick.source, _blick_lines(blick, blick.problems, root, verbose))
        for blick in registry.failed
    ]
    return "\n".join([*lines, *_section("warnings", warnings), *_section("errors", errors)])


def _project_line(root: Path | None) -> list[str]:
    """``project: <root>`` when the root is not the working directory, so paths can be found."""
    if root is None or root == Path.cwd().resolve():
        return []
    return [f"project: {root}"]


def _group_lines(registry: Registry) -> list[str]:
    entries: dict[str, list[Blick | BlickEntry]] = defaultdict(list)
    for entry in [*registry.blicks.values(), *registry.failed]:
        entries[entry.group].append(entry)
    blicks = list(registry.blicks.values())
    names = [b.id for b in blicks] + [f.name for f in registry.failed]
    titles = [b.title for b in blicks] + (["[error]"] if registry.failed else [])
    id_width = max(map(len, names), default=0)
    title_width = max(map(len, titles), default=0)
    plot_width = max((len(b.plot.plot_type.name) for b in blicks), default=0)

    lines: list[str] = []
    for name, group in registry.groups.items():
        heading = [name, *([group.title] if group.title else [])]
        if group.tags:
            heading.append(f"[{', '.join(group.tags)}]")
        lines.append("  ".join(heading))
        members = sorted(entries.get(name, []), key=lambda e: e.source or NOWHERE)
        if not members:
            lines.append("  (no Blicks)")
        for entry in members:
            if isinstance(entry, BlickEntry):
                where = entry.source.display(registry.root) if entry.source else ""
                cells = [entry.name.ljust(id_width), "[error]".ljust(title_width), where]
            else:
                cells = [
                    entry.id.ljust(id_width),
                    entry.title.ljust(title_width),
                    entry.plot.plot_type.name.ljust(plot_width),
                ]
                if entry.aliases:
                    cells.append(f"aliases: {', '.join(entry.aliases)}")
            lines.append(("  " + "   ".join(cells)).rstrip())
    return lines


def _summary(registry: Registry) -> str:
    total = len(registry.blicks) + len(registry.failed)
    blicks = _count(total, "Blick")
    if registry.failed:
        blicks += f" ({len(registry.failed)} with errors)"
    parts = [_count(len(registry.groups), "group"), blicks]
    if errors := len(registry.failed) + len(registry.errors):
        parts.append(_count(errors, "error"))
    if registry.warnings:
        parts.append(_count(len(registry.warnings), "warning"))
    return " · ".join(parts)


def _traceback_lines(problem: Problem, verbose: bool) -> list[str]:
    if not (verbose and problem.traceback):
        return []
    return [f"      {line}" for line in problem.traceback.rstrip().splitlines()]


def _hint(problem: Problem, verbose: bool) -> str:
    return "   (-v for the traceback)" if problem.traceback and not verbose else ""


def _problem_lines(problem: Problem, root: Path | None, verbose: bool = False) -> list[str]:
    """The problem's location and kind, the traceback under ``-v``, then its message lines.

    The message comes last, so the note that a file's Blicks were skipped ends the entry.
    """
    location = problem.location(root)
    heading = f"{location}  {_headline(problem.kind)}" if location else _headline(problem.kind)
    return [
        f"  {heading}{_hint(problem, verbose)}",
        *_traceback_lines(problem, verbose),
        *(f"    {line}" for line in problem.message.splitlines()),
    ]


def _blick_lines(
    entry: BlickEntry, problems: Sequence[Problem], root: Path | None, verbose: bool = False
) -> list[str]:
    """A Blick's location and name, then each problem's message, its traceback under ``-v``."""
    where = entry.source.display(root) if entry.source else "-"
    lines = [f"  {where}  Blick {entry.name}"]
    for problem in problems:
        first, *rest = problem.message.splitlines()
        lines.append(f"    {first}{_hint(problem, verbose)}")
        lines.extend(f"    {line}" for line in rest)
        lines.extend(_traceback_lines(problem, verbose))
    return lines


def render_build(result: Build, *, verbose: bool = False) -> str:
    """The text of ``blicket build``: the run, the counts, the build directory, then problems."""
    manifest = result.manifest
    run, repository = manifest.run, manifest.repository
    # The commit of the Blick repository, not of the model that produced the run.
    head = "no git commit"
    if repository is not None:
        head = f"blicks at {repository.commit[:7]}{' (dirty)' if repository.dirty else ''}"
    milliseconds = manifest.build.loader_ms
    loaded = f"{milliseconds:.0f} ms" if milliseconds < 1000 else f"{milliseconds / 1000:.1f} s"
    where = display_path(result.path, Path.cwd())
    existed = " (built before, left as it was)" if result.existed else ""
    lines = [
        *_project_line(result.root),
        f"run {run.id} · profile {run.profile} · {head} · loaded in {loaded}",
        _build_summary(manifest),
        f"build {manifest.build.id} → {where}{existed}",
    ]
    warnings: list[_Block] = []
    errors: list[_Block] = []
    for problem in manifest.problems:
        blocks = errors if problem.severity == "error" else warnings
        blocks.append((problem.source, _problem_lines(problem, None, verbose)))
    for entry in manifest.blicks:
        for severity, blocks in (("error", errors), ("warning", warnings)):
            if problems := [p for p in entry.problems if p.severity == severity]:
                blocks.append((entry.source, _blick_lines(entry, problems, None, verbose)))
    return "\n".join([*lines, *_section("warnings", warnings), *_section("errors", errors)])


def _build_summary(manifest: Manifest) -> str:
    """``N Blicks: n built · n errors``, file-level errors by kind, warnings, incompleteness."""
    built = sum(entry.data is not None for entry in manifest.blicks)
    parts = [f"{_count(len(manifest.blicks), 'Blick')}: {built} built"]
    if failed := len(manifest.blicks) - built:
        parts.append(_count(failed, "error"))
    file_errors = Counter(p.kind for p in manifest.problems if p.severity == "error")
    parts.extend(_count(n, f"{kind.replace('_', ' ')} error") for kind, n in file_errors.items())
    problems = [*manifest.problems, *(p for entry in manifest.blicks for p in entry.problems)]
    if warnings := sum(problem.severity == "warning" for problem in problems):
        parts.append(_count(warnings, "warning"))
    if manifest.build.incomplete:
        parts.append("incomplete (Blicks missing)")
    return " · ".join(parts)
