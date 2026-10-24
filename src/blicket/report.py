"""The reports of the commands: what ``list``, ``build``, ``push``, ``diff`` and ``check``
print, and the Markdown report of a comparison, as plain functions of what the commands
computed."""

import importlib.metadata
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

from blicket.baseline import Resolution
from blicket.builder import Build
from blicket.comparison import COMPARE, BlickComparison, BuildRef, Comparison
from blicket.errors import NOWHERE, Kind, Problem, Source, display_path
from blicket.manifest import Manifest, Repository
from blicket.model import Blick, BlickEntry, Registry
from blicket.schema import Flag
from blicket.store import Pushed


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
_EMPTY = "\N{EN DASH}"  # an empty cell of a Markdown table
_POINTER = " (all in --json)"  # after a shortened list in the text of diff


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


def render_push(pushed: Pushed) -> str:
    """The text of ``blicket push``: the build, where it went in the store, and the comparisons
    that went with it."""
    line = f"build {pushed.id} → {display_path(pushed.path, Path.cwd())}"
    if pushed.existed:
        return (
            f"{line} (in the store already, left as it was; comparisons are not added to a stored "
            "build)"
        )
    if pushed.comparisons:
        return f"{line} (with the comparisons against {', '.join(pushed.comparisons)})"
    return line


def render_diff(comparison: Comparison) -> str:
    """The text of ``blicket diff``: the two builds, the counts, why removed Blicks were not
    judged, the top movers, then the Blicks whose values appeared or vanished, the new and the
    removed Blicks, and the errors."""
    return "\n".join(
        [
            _build_line("baseline", comparison.baseline),
            _build_line("current", comparison.current),
            _counts_line(comparison, _count(len(comparison.blicks), "Blick")),
            *_incomplete_lines(comparison),
            *_mover_lines(comparison, _POINTER),
            *_detail_lines(comparison, pointer=_POINTER),
        ]
    )


def render_no_baseline(resolution: Resolution) -> str:
    """Why there is no baseline; an error when that is one, see ``Resolution.failed``."""
    if resolution.failed:
        return f"error: no baseline: {resolution.reason}"
    return f"baseline: none ({resolution.reason})"


def render_check(
    result: Build,
    resolution: Resolution,
    comparison: Comparison | None,
    pushed: Pushed | None,
    warnings: Sequence[str] = (),
    *,
    verbose: bool = False,
) -> str:
    """The text of ``blicket check``: the build's report, the warnings, the baseline or why there
    is none, the comparison's summary and verdict, where it was written, the push, and the
    comparison's details.

    What the build's report says is not repeated: the current build, and the errors of Blicks
    that did not build; errors only the comparison finds remain.
    """
    manifest = result.manifest
    lines = [f"warning: {warning}" for warning in warnings]
    if resolution.warning:
        lines.append(f"warning: {resolution.warning}")
    details: list[str] = []
    if comparison is None:
        lines.append(render_no_baseline(resolution))
    else:
        found = comparison.baseline
        created = found.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        parts = _build_parts(found, profile=found.profile != manifest.run.profile)
        verdict = (
            f"flagged: {comparison.flagged} of {_count(len(comparison.blicks), 'Blick')}"
            if comparison.flagged
            else "nothing flagged, but the build is incomplete"
            if comparison.has_errors
            else "nothing flagged"
        )
        lines += [
            " · ".join([f"baseline {found.id}", *parts, f"built {created}"]),
            _counts_line(comparison, "vs baseline"),
            *_incomplete_lines(comparison),
            *_mover_lines(comparison),
            verdict,
            f"comparison → {display_path(result.path / COMPARE / found.id, Path.cwd())}",
        ]
        details = _detail_lines(comparison, manifest)
    if pushed is not None:
        lines.append(render_push(pushed))
    return render_build(result, verbose=verbose) + "\n\n" + "\n".join([*lines, *details])


def _counts_line(comparison: Comparison, label: str) -> str:
    """``label``, then the Blicks per flag, the unchanged ones, and whether removed was judged."""
    blicks, counts = comparison.blicks, comparison.counts
    unchanged = len(blicks) - comparison.flagged
    numbers = [
        ("unchanged", unchanged),
        *((flag, counts[flag]) for flag in ("value", "schema", "new", "removed")),
    ]
    parts = [f"{number} {word}" for word, number in numbers if number]
    if comparison.incomplete:
        parts.append("removed not judged")
    if counts["error"]:
        parts.append(_count(counts["error"], "error"))
    return f"{label}: {' · '.join(parts)}" if parts else label


def _incomplete_lines(comparison: Comparison) -> list[str]:
    if not comparison.incomplete:
        return []
    return [f"removed not judged: {'; '.join(comparison.incomplete)}"]


def _mover_lines(comparison: Comparison, pointer: str = "") -> list[str]:
    """The top three movers, then how many more Blicks are flagged ``value``, and ``pointer``."""
    lead = "top movers: "
    movers = comparison.movers(3)
    lines: list[str] = []
    for index, mover in enumerate(movers):
        change = mover.change
        where = f" ({_where(change.where)})" if change.where else ""
        start = lead if index == 0 else " " * len(lead)
        lines.append(f"{start}{mover.name} {change.magnitude:.2g}{where}")
    if (more := comparison.counts["value"] - len(movers)) > 0:
        lines.append(f"{' ' * len(lead)}… and {more} more{pointer}")
    return lines


def _detail_lines(
    comparison: Comparison, built: Manifest | None = None, *, pointer: str = ""
) -> list[str]:
    """The Blicks whose values appeared or vanished, the new, the removed, and the errors;
    without the errors of Blicks that have no table in ``built``, when given. ``pointer`` follows
    a shortened list of values."""
    blicks = comparison.blicks
    tables = None if built is None else {e.id for e in built.blicks if e.data is not None}
    sections = {
        "schema": [_schema_lines(b, pointer) for b in blicks if "schema" in b.change.flags],
        "new": [
            [f"  {b.name}  {b.message}" if b.message else f"  {b.name}"]
            for b in blicks
            if "new" in b.change.flags
        ],
        "removed": [[f"  {b.name}"] for b in blicks if "removed" in b.change.flags],
        "errors": [
            [f"  {b.name}  {b.message}"]
            for b in blicks
            if "error" in b.change.flags and (tables is None or b.id in tables)
        ],
    }
    lines: list[str] = []
    for title, blocks in sections.items():
        lines += _section(title, [(None, block) for block in blocks])
    return lines


def render_markdown(comparison: Comparison) -> str:
    """The Markdown summary of a comparison: a heading with the two builds, the counts, a table
    of the flagged Blicks, the largest magnitude first, then the columns and values that
    appeared or vanished, the new Blicks that did not build in the baseline, and the errors,
    those of the files of an incomplete build first."""
    current, baseline = comparison.current, comparison.baseline
    lines = [
        f"### blicket: run {current.run} (`{current.id[:8]}`) against run {baseline.run} "
        f"(`{baseline.id[:8]}`)",
        "",
        " · ".join([f"- baseline `{baseline.id}`", *_build_parts(baseline)]),
        " · ".join([f"- current `{current.id}`", *_build_parts(current)]),
        "",
        _counts_line(comparison, _count(len(comparison.blicks), "Blick")),
    ]
    flagged = sorted(
        (blick for blick in comparison.blicks if blick.change.flags),
        key=lambda blick: blick.change.magnitude or 0.0,
        reverse=True,
    )
    if flagged:
        lines += ["", "| Blick | flags | magnitude | where |", "|---|---|---|---|"]
    for blick in flagged:
        change = blick.change
        cells = [
            f"`{blick.name}`",
            ", ".join(flag for flag in get_args(Flag) if flag in change.flags),
            _EMPTY if change.magnitude is None else f"{change.magnitude:.2g}",
            _where(change.where) if change.where else _EMPTY,
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    schema = [b for b in comparison.blicks if "schema" in b.change.flags]
    new = [b for b in comparison.blicks if "new" in b.change.flags and b.message]
    errors = [b for b in comparison.blicks if "error" in b.change.flags]
    if schema:
        lines += ["", "#### schema", ""]
    for blick in schema:
        lines += [f"- `{blick.name}`", *(f"  - {line}" for line in _schema_details(blick))]
    if new:
        lines += ["", "#### new", ""]
        lines += [f"- `{blick.name}`: {blick.message}" for blick in new]
    if errors or comparison.incomplete:
        lines += ["", "#### errors", ""]
        lines += [f"- {reason}" for reason in comparison.incomplete]
        lines += [f"- `{blick.name}`: {blick.message}" for blick in errors]
    return "\n".join(lines) + "\n"


def render_markdown_no_baseline(built: Manifest, resolution: Resolution) -> str:
    """The Markdown summary of a check without a baseline: the heading with the build, and why."""
    heading = f"### blicket: run {built.run.id} (`{built.build.id[:8]}`)"
    return f"{heading}\n\n{render_no_baseline(resolution)}\n"


def _build_line(label: str, build: BuildRef) -> str:
    return " · ".join([f"{label:<8} {build.id}", *_build_parts(build)])


def _build_parts(build: BuildRef, *, profile: bool = True) -> list[str]:
    """The run, the profile unless left out, the commit, and whether the build is incomplete."""
    parts = [f"run {build.run}", *([f"profile {build.profile}"] if profile else [])]
    parts.append(_head(build.repository))
    if build.incomplete:
        parts.append(_INCOMPLETE)
    return parts


def _where(where: dict[str, Any]) -> str:
    return ", ".join(f"{dimension}={value}" for dimension, value in where.items())


def _listing(items: Sequence[object], pointer: str) -> str:
    """The first five items, then how many more there are, and ``pointer``."""
    more = f" … and {len(items) - 5} more{pointer}" if len(items) > 5 else ""
    return ", ".join(map(str, items[:5])) + more


def _schema_lines(blick: BlickComparison, pointer: str) -> list[str]:
    return [f"  {blick.name}", *(f"    {line}" for line in _schema_details(blick, pointer))]


def _schema_details(blick: BlickComparison, pointer: str = "") -> list[str]:
    """The columns and dimension values that appeared or vanished in a Blick, ``pointer`` after
    a shortened list."""
    change = blick.change
    lines: list[str] = []
    for verb, columns in (("added", change.columns_added), ("removed", change.columns_removed)):
        if columns:
            named = [f"{column} ({dtype})" for column, dtype in columns.items()]
            lines.append(f"columns {verb}: {_listing(named, pointer)}")
    for verb, values in (("added", change.values_added), ("removed", change.values_removed)):
        for dimension, found in values.items():
            lines.append(f"{dimension} {verb}: {_listing(found, pointer)}")
    return lines
