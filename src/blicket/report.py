"""The reports of the commands: what ``list``, ``build`` and ``diff`` print, as plain functions
of what the commands computed."""

import importlib.metadata
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from blicket.builder import Build
from blicket.comparison import BlickComparison, BuildRef, Comparison
from blicket.errors import NOWHERE, Kind, Problem, Source, display_path
from blicket.manifest import Manifest, Repository
from blicket.model import Blick, BlickEntry, Registry


def render_list_json(registry: Registry) -> str:
    """The JSON of ``blicket list``, with the absolute root, since it is local."""
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


def _headline(kind: str) -> str:
    """What a file-level problem is called in the report: the kind in words."""
    return {Kind.IMPORT: "import failed", Kind.GROUP: "bk.group()"}.get(
        kind, kind.replace("_", " ")
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


type _Block = tuple[Source | None, list[str]]

_INCOMPLETE = "incomplete (Blicks missing)"


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


def _head(repository: Repository | None) -> str:
    """The commit of the repository holding the Blicks, not of the model that produced the run."""
    if repository is None:
        return "no git commit"
    return f"blicks at {repository.commit[:7]}{' (dirty)' if repository.dirty else ''}"


def render_build(result: Build, *, verbose: bool = False) -> str:
    """The text of ``blicket build``: the run, the counts, the build directory, then problems."""
    manifest = result.manifest
    run, head = manifest.run, _head(manifest.repository)
    milliseconds = manifest.build.loader_ms
    loaded = f"{milliseconds:.0f} ms" if milliseconds < 1000 else f"{milliseconds / 1000:.1f} s"
    where = display_path(result.path, Path.cwd())
    existed = ""
    if result.existed:
        kept = "viewer refreshed" if result.viewer else "left as it was"
        existed = f" (built before, {kept})"
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
        parts.append(_INCOMPLETE)
    return " · ".join(parts)


def render_diff(comparison: Comparison) -> str:
    """The text of ``blicket diff``: the two builds, the counts, why removed Blicks were not
    judged, the top movers, then the Blicks whose values appeared or vanished, the new and the
    removed Blicks, and the errors."""
    blicks, counts = comparison.blicks, comparison.counts
    unchanged = sum(not blick.change.flags for blick in blicks)
    numbers = [
        ("unchanged", unchanged),
        *((flag, counts[flag]) for flag in ("value", "schema", "new", "removed")),
    ]
    parts = [f"{number} {word}" for word, number in numbers if number]
    if comparison.incomplete:
        parts.append("removed not judged")
    if counts["error"]:
        parts.append(_count(counts["error"], "error"))
    summary = _count(len(blicks), "Blick") + (f": {' · '.join(parts)}" if parts else "")
    lines = [
        _build_line("baseline", comparison.baseline),
        _build_line("current", comparison.current),
        summary,
    ]
    if comparison.incomplete:
        lines.append(f"removed not judged: {'; '.join(comparison.incomplete)}")
    lead = "top movers: "
    movers = comparison.movers(3)
    for index, mover in enumerate(movers):
        change = mover.change
        where = f" ({_where(change.where)})" if change.where else ""
        start = lead if index == 0 else " " * len(lead)
        lines.append(f"{start}{mover.name} {change.magnitude:.2g}{where}")
    if (more := counts["value"] - len(movers)) > 0:
        lines.append(f"{' ' * len(lead)}… and {more} more (all in --json)")

    sections = {
        "schema": [_schema_lines(b) for b in blicks if "schema" in b.change.flags],
        "new": [
            [f"  {b.name}  {b.message}" if b.message else f"  {b.name}"]
            for b in blicks
            if "new" in b.change.flags
        ],
        "removed": [[f"  {b.name}"] for b in blicks if "removed" in b.change.flags],
        "errors": [[f"  {b.name}  {b.message}"] for b in blicks if "error" in b.change.flags],
    }
    for title, blocks in sections.items():
        lines += _section(title, [(None, block) for block in blocks])
    return "\n".join(lines)


def _build_line(label: str, build: BuildRef) -> str:
    parts = [
        f"{label:<8} {build.id}",
        f"run {build.run}",
        f"profile {build.profile}",
        _head(build.repository),
    ]
    if build.incomplete:
        parts.append(_INCOMPLETE)
    return " · ".join(parts)


def _where(where: dict[str, Any]) -> str:
    return ", ".join(f"{dimension}={value}" for dimension, value in where.items())


def _listing(items: Sequence[object]) -> str:
    """The first five items, then how many more there are."""
    more = f" … and {len(items) - 5} more (all in --json)" if len(items) > 5 else ""
    return ", ".join(map(str, items[:5])) + more


def _schema_lines(blick: BlickComparison) -> list[str]:
    """The columns and dimension values that appeared or vanished in a Blick."""
    change = blick.change
    lines = [f"  {blick.name}"]
    for verb, columns in (("added", change.columns_added), ("removed", change.columns_removed)):
        if columns:
            named = [f"{column} ({dtype})" for column, dtype in columns.items()]
            lines.append(f"    columns {verb}: {_listing(named)}")
    for verb, values in (("added", change.values_added), ("removed", change.values_removed)):
        for dimension, found in values.items():
            lines.append(f"    {dimension} {verb}: {_listing(found)}")
    return lines
