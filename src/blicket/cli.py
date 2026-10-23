"""The ``blicket`` command line.

Exit codes: 0 success, 2 errors of any kind. typer alone exits 1 on an uncaught exception, so
``_Command`` maps those to 2; click's usage errors exit 2 by themselves.

Streams: once a project has been found, every problem is part of the report on stdout, as the
errors section or, with ``--json``, as JSON. A missing project or an invalid ``[tool.blicket]``
is one ``error: ...`` line on stderr instead; an unexpected exception is an ``error:`` line, the
traceback under ``-v``, and a line asking for a bug report.
"""

import importlib.metadata
import json
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperCommand

from blicket.config import PYPROJECT, find_project_root
from blicket.discovery import discover
from blicket.errors import NOWHERE, ConfigError, Kind, Problem
from blicket.model import Blick, FailedBlick, Registry

ERROR_EXIT_CODE = 2


class _Command(TyperCommand):
    """A command whose failures exit with code 2, the traceback shown under ``-v``."""

    # Any: the base class takes typer's vendored click Context, which typer does not export.
    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except typer.Exit, typer.TyperException:  # click's own errors; typer shows them
            raise
        except typer.Abort:
            typer.echo("error: aborted", err=True)
        except ConfigError as error:
            typer.echo(f"error: {error}", err=True)
        except Exception as error:
            typer.echo(f"error: unexpected {type(error).__name__}: {error}", err=True)
            if ctx.params.get("verbose"):
                stack = "".join(traceback.format_tb(error.__traceback__)).rstrip()
                typer.echo(f"Traceback (most recent call last):\n{stack}", err=True)
                typer.echo("this is a bug in blicket; please report it", err=True)
            else:
                typer.echo("this is a bug in blicket; rerun with -v and report it", err=True)
        raise typer.Exit(ERROR_EXIT_CODE)


# Every command must use cls=_Command, for the exit codes, and take -v/--verbose; a test checks
# the first.
app = typer.Typer(
    name="blicket",
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


@app.command("list", cls=_Command)
def list_command(
    project: Annotated[
        Path | None,
        typer.Option(
            "--project",
            help=(
                f"The project directory, which holds the {PYPROJECT} with \\[tool.blicket]. "
                "Default: found by walking up from the working directory."
            ),
            show_default=False,
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show tracebacks.")] = False,
) -> None:
    """List the project's groups and Blicks, then warnings and errors.

    Exit codes: 0 success, 2 errors.
    """
    registry = discover(project.resolve() if project else find_project_root())
    if as_json:
        version = importlib.metadata.version("blicket")
        typer.echo(json.dumps({"blicket": version, **registry.to_json()}, indent=2))
    else:
        typer.echo(render_list(registry, verbose=verbose))
    if registry.has_errors:
        raise typer.Exit(ERROR_EXIT_CODE)


# ---------------------------------------------------------------------------------------------
# Text output


def _headline(kind: str) -> str:
    """What a file-level problem is called in the report: the kind in words."""
    return {Kind.IMPORT: "import failed", Kind.GROUP: "bk.group()"}.get(
        kind, kind.replace("_", " ")
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def render_list(registry: Registry, *, verbose: bool = False) -> str:
    """The text of ``blicket list``: groups with their Blicks, a summary, warnings, errors."""
    root = registry.root
    lines = [*_project_line(root), *_group_lines(registry)]
    if lines:
        lines.append("")
    lines.append(_summary(registry))
    if registry.warnings:
        lines.extend(["", "warnings", *_problem_lines(registry.warnings, root)])
    if registry.has_errors:
        lines.extend(["", "errors"])
        blocks = [(blick.source, _failed_lines(blick, root)) for blick in registry.failed]
        blocks += [(e.source, _problem_lines([e], root, verbose)) for e in registry.errors]
        for _, block in sorted(blocks, key=lambda item: item[0] or NOWHERE):
            lines.extend(block)
    return "\n".join(lines)


def _project_line(root: Path | None) -> list[str]:
    """``project: <root>`` when the root is not the working directory, so paths can be found."""
    if root is None or root == Path.cwd().resolve():
        return []
    return [f"project: {root}"]


def _group_lines(registry: Registry) -> list[str]:
    entries: dict[str, list[Blick | FailedBlick]] = defaultdict(list)
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
            if isinstance(entry, FailedBlick):
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


def _problem_lines(
    problems: tuple[Problem, ...] | list[Problem], root: Path | None, verbose: bool = False
) -> list[str]:
    """Each problem: its location and kind, the traceback under ``-v``, then its message lines.

    The message comes last, so the note that a file's Blicks were skipped ends the entry.
    """
    lines: list[str] = []
    for problem in problems:
        hint = "   (-v for the traceback)" if problem.traceback and not verbose else ""
        location = problem.location(root)
        heading = f"{location}  {_headline(problem.kind)}" if location else _headline(problem.kind)
        lines.append(f"  {heading}{hint}")
        if verbose and problem.traceback:
            lines.extend(f"      {line}" for line in problem.traceback.rstrip().splitlines())
        lines.extend(f"    {line}" for line in problem.message.splitlines())
    return lines


def _failed_lines(blick: FailedBlick, root: Path | None) -> list[str]:
    where = blick.source.display(root) if blick.source else "-"
    return [f"  {where}  Blick {blick.name}", *(f"    {p.message}" for p in blick.problems)]
