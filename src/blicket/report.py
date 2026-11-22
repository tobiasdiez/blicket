"""The reports of the commands: what ``list``, ``build``, ``push``, ``diff`` and ``check``
print, what a session of ``dev`` prints, and the Markdown report of a comparison, as plain
functions of what the commands computed."""

import importlib.metadata
import json
import re
import textwrap
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

from blicket.baseline import Resolution
from blicket.builder import Build
from blicket.comparison import COMPARE, BlickComparison, BuildRef, Comparison
from blicket.errors import NOWHERE, Kind, Problem, Source, display_path, first_line
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
# The names of the Blicks skipped for one reason, under the reason.
_SKIPPED_NAMES = textwrap.TextWrapper(
    width=100,
    initial_indent="    ",
    subsequent_indent="    ",
    break_long_words=False,
    break_on_hyphens=False,
)


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

    The message comes last, so the note that a file's Blicks are missing ends the entry.
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


def duration(seconds: float) -> str:
    """How long a build took, as its line says it: ``412 ms`` under a second, ``42.1 s`` under a
    minute, then ``3 min 25 s`` or, from an hour, ``1 h 2 min 5 s``; each as it is rounded, so
    that 0.9996 s is ``1.0 s``, not ``1000 ms``."""
    if round(seconds * 1000) < 1000:
        return f"{seconds * 1000:.0f} ms"
    if round(seconds, 1) < 60:
        return f"{seconds:.1f} s"
    whole = round(seconds)
    hours, minutes, rest = whole // 3600, whole // 60 % 60, whole % 60
    return f"{hours} h {minutes} min {rest} s" if hours else f"{minutes} min {rest} s"


def _run_line(manifest: Manifest) -> str:
    """The run, its profile, the commit of the Blicks and the loader's wall time."""
    run, head = manifest.run, _head(manifest.repository)
    milliseconds = manifest.build.loader_ms
    loaded = f"{milliseconds:.0f} ms" if milliseconds < 1000 else f"{milliseconds / 1000:.1f} s"
    return f"run {run.id} · profile {run.profile} · {head} · loaded in {loaded}"


def render_build(result: Build, *, verbose: bool = False) -> str:
    """The text of ``blicket build``: the run, the counts, the build directory, the skipped
    Blicks with their reasons, then problems."""
    manifest = result.manifest
    where = display_path(result.path, Path.cwd())
    existed = ""
    if result.existed:
        kept = "viewer refreshed" if result.viewer else "left as it was"
        existed = f" (built before, {kept})"
    lines = [
        *_project_line(result.root),
        _run_line(manifest),
        _build_summary(manifest),
        f"build {manifest.build.id} → {where}{existed}",
    ]
    skipped = _section("skipped", _skipped_blocks(manifest))
    return "\n".join([*lines, *skipped, *_problem_sections(manifest, verbose)])


def _problem_sections(manifest: Manifest, verbose: bool, root: Path | None = None) -> list[str]:
    """The sections ``warnings`` and ``errors`` of a build's report: the problems of files and the
    project, and of the Blicks, located relative to ``root``, when the manifest's sources are not
    relative already."""
    warnings: list[_Block] = []
    errors: list[_Block] = []
    for problem in manifest.problems:
        blocks = errors if problem.severity == "error" else warnings
        blocks.append((problem.source, _problem_lines(problem, root, verbose)))
    for entry in manifest.blicks:
        for severity, blocks in (("error", errors), ("warning", warnings)):
            if problems := [p for p in entry.problems if p.severity == severity]:
                blocks.append((entry.source, _blick_lines(entry, problems, root, verbose)))
    return [*_section("warnings", warnings), *_section("errors", errors)]


def render_session_start(
    manifest: Manifest,
    root: Path,
    resolution: Resolution,
    baseline: BuildRef | None,
    removed: Sequence[str] = (),
    warnings: Sequence[str] = (),
    *,
    verbose: bool = False,
) -> str:
    """What a session of ``blicket dev`` prints when it starts, before it builds anything, in the
    order of ``check``'s report: the run, how many Blicks there are and how they are built, the
    problems of the definitions and files, then the warnings about the store, the baseline or why
    there is none, and the baseline's Blicks that no Blick claims, ``removed``, which the
    definitions alone tell."""
    lines = [*_project_line(root), _run_line(manifest), _session_summary(manifest)]
    lines += _problem_sections(manifest, verbose, root)
    lines += ["", *_baseline_lines(resolution, baseline, warnings, manifest.run.profile)]
    if removed:
        lines.append(f"vs baseline: {len(removed)} removed ({_listing(removed, '')})")
    return "\n".join(lines)


_IN_THE_BACKGROUND = "built in the background"
_WHEN_OPENED = "when opened in the viewer (expensive)"


def _session_summary(manifest: Manifest) -> str:
    """How many Blicks a session has and how it builds them: the cheap ones in the background,
    the expensive ones when they are opened, as ``62 Blicks: 2 built in the background, 60 when
    opened in the viewer (expensive)``; those whose definition is invalid, the only errors before
    anything is built, are left out of both."""
    total, invalid = len(manifest.blicks), manifest.statuses["error"]
    expensive = sum(entry.expensive for entry in manifest.blicks)
    cheap = total - invalid - expensive
    head = _count(total, "Blick")
    if total and (invalid or (cheap and expensive)):
        parts = [f"{cheap} {_IN_THE_BACKGROUND}"] if cheap or not expensive else []
        if expensive:
            parts.append(
                f"{expensive} {_WHEN_OPENED}" if parts else f"{expensive} built {_WHEN_OPENED}"
            )
        head += ": " + ", ".join(parts)
    elif expensive:
        each = "each built when it is" if expensive > 1 else "built when it is"
        head += f", {each} opened in the viewer (expensive)"
    elif cheap:
        head += f", {_IN_THE_BACKGROUND}"
    return " · ".join([head, *_troubles(manifest)])


def render_session_report(
    manifest: Manifest,
    comparison: Comparison | None,
    root: Path,
    at: datetime,
    buildable: Collection[str],
    *,
    verbose: bool = False,
) -> str:
    """What a session of ``blicket dev`` prints once the background has built every cheap Blick,
    at the time ``at``: the rest of ``check``'s report, of the Blicks built so far, which the
    start report did not say: the counts, the skipped Blicks with their reasons, the problems of
    the Blicks built, those of ``buildable``, sources relative to ``root``, then the comparison's
    counts, top movers, verdict and details; neither the problems of the files and of the
    definitions, which the start report said, nor where a comparison went, since nothing is
    written."""
    lines = [f"{at:%H:%M:%S} {_build_summary(manifest)}"]
    lines += _section("skipped", _skipped_blocks(manifest))
    built = tuple(entry for entry in manifest.blicks if entry.id in buildable)
    lines += _problem_sections(
        manifest.model_copy(update={"blicks": built, "problems": ()}), verbose, root
    )
    if comparison is not None:
        lines += ["", *_verdict_lines(comparison), *_detail_lines(comparison, manifest)]
    return "\n".join(lines)


_RAISED_AT = re.compile(r" \(raised at [^()]*\)$")


def _message_head(message: str) -> str:
    """The first line of a problem's message, with the place it was raised at, which ends the
    message, also when that is on a later line."""
    first, *rest = message.splitlines() or [""]
    if rest and (raised := _RAISED_AT.search(rest[-1])) and not _RAISED_AT.search(first):
        first += raised.group(0)
    return first


def render_session_build(
    entry: BlickEntry,
    compared: BlickComparison | None,
    seconds: float,
    at: datetime,
    *,
    rebuilt: bool = False,
    verbose: bool = False,
) -> str:
    """The line a session of ``blicket dev`` prints when it has built a Blick, at the time
    ``at``: the Blick, whether it built (``rebuilt`` when it was built before), failed or skipped
    the run, in how long, why it failed or skipped, what the comparison with the baseline found,
    and its warnings, as ``12:01:47 cement/trade built in 42.1 s · value, 2.1% of scale
    (Region=CHA, Time=2019)``. A failure says where it was raised, and that ``-v`` shows the
    traceback; further errors follow on lines of their own, and under ``verbose`` the
    tracebacks."""
    verb = {"error": "failed", "skipped": "skipped"}.get(
        entry.status, "rebuilt" if rebuilt else "built"
    )
    parts = [f"{at:%H:%M:%S} {entry.name} {verb} in {duration(seconds)}"]
    errors = [p for p in entry.problems if p.severity == "error"]
    warnings = [p for p in entry.problems if p.severity == "warning"]
    if errors:
        parts.append(_message_head(errors[0].message))
    elif entry.status == "skipped":
        parts.append(first_line(entry.skipped or ""))
    if compared is not None:
        parts += _change_parts(compared, entry, failed=bool(errors))
    if warnings:
        first = _message_head(warnings[0].message) + (" …" if len(warnings) > 1 else "")
        parts.append(f"{_count(len(warnings), 'warning')}: {first}")
    hint = next((_hint(p, verbose) for p in entry.problems if _hint(p, verbose)), "")
    lines = [" · ".join(parts) + hint]
    lines += [f"    {_message_head(problem.message)}" for problem in errors[1:]]
    for problem in entry.problems:
        lines += _traceback_lines(problem, verbose)
    return "\n".join(lines)


def _change_parts(compared: BlickComparison, entry: BlickEntry, *, failed: bool) -> list[str]:
    """What the comparison found of a Blick built, as parts of its line: its flags, ``value``
    with the largest change and where, and ``error`` with why, but not for a Blick that failed,
    whose line says why already; ``unchanged`` for a Blick that built and has no flag."""
    change, parts = compared.change, []
    for flag in ("value", "schema", "new", "removed", "error"):
        if flag not in change.flags or (flag == "error" and failed):
            continue
        if flag == "value":
            where = f" ({_where(change.where)})" if change.where else ""
            parts.append(f"value, {change.percent} of scale{where}")
        else:
            parts.append(f"error: {compared.message}" if flag == "error" else flag)
    if not change.flags and entry.status == "ok":
        parts.append("unchanged")
    return parts


def _skipped_blocks(manifest: Manifest) -> list[_Block]:
    """The skipped Blicks grouped by their reason, a block per reason, ordered by location like
    the other sections: the reason, its further lines indented as the names of its Blicks under
    it, which are wrapped to 100 columns."""
    by_reason: dict[str, list[BlickEntry]] = defaultdict(list)
    for entry in manifest.blicks:
        if entry.status == "skipped":
            by_reason[entry.skipped or ""].append(entry)
    blocks: list[_Block] = []
    for reason, entries in by_reason.items():
        first, *rest = reason.splitlines() or [""]
        names = _SKIPPED_NAMES.wrap(", ".join(entry.name for entry in entries))
        blocks.append(
            (entries[0].source, [f"  {first}", *(f"    {line}" for line in rest), *names])
        )
    return blocks


def _build_summary(manifest: Manifest) -> str:
    """``N Blicks: n built · n skipped · n not built yet · n errors``, file-level errors by kind,
    warnings, incompleteness; only the manifest of a session has Blicks not built yet."""
    statuses = manifest.statuses
    parts = [f"{_count(len(manifest.blicks), 'Blick')}: {statuses['ok']} built"]
    if statuses["skipped"]:
        parts.append(f"{statuses['skipped']} skipped")
    if statuses["pending"]:
        parts.append(f"{statuses['pending']} not built yet")
    return " · ".join([*parts, *_troubles(manifest)])


def _troubles(manifest: Manifest) -> list[str]:
    """The Blicks in error, the file-level errors by kind, the warnings and whether the build is
    incomplete, as parts of a summary line."""
    parts: list[str] = []
    if errors := manifest.statuses["error"]:
        parts.append(_count(errors, "error"))
    file_errors = Counter(p.kind for p in manifest.problems if p.severity == "error")
    parts.extend(_count(n, f"{kind.replace('_', ' ')} error") for kind, n in file_errors.items())
    problems = [*manifest.problems, *(p for entry in manifest.blicks for p in entry.problems)]
    if warnings := sum(problem.severity == "warning" for problem in problems):
        parts.append(_count(warnings, "warning"))
    if manifest.build.incomplete:
        parts.append(_INCOMPLETE)
    return parts


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
    found = comparison.baseline if comparison is not None else None
    lines = _baseline_lines(resolution, found, warnings, manifest.run.profile)
    details: list[str] = []
    if comparison is not None:
        written = result.path / COMPARE / comparison.baseline.id
        lines += [
            *_verdict_lines(comparison),
            f"comparison → {display_path(written, Path.cwd())}",
        ]
        details = _detail_lines(comparison, manifest)
    if pushed is not None:
        lines.append(render_push(pushed))
    return render_build(result, verbose=verbose) + "\n\n" + "\n".join([*lines, *details])


def _verdict_lines(comparison: Comparison) -> list[str]:
    """What a comparison found, in short: the counts, why removed Blicks were not judged, the top
    movers, and the verdict."""
    verdict = (
        f"flagged: {comparison.flagged} of {_count(len(comparison.blicks), 'Blick')}"
        if comparison.flagged
        else "nothing flagged, but the build is incomplete"
        if comparison.has_errors
        else "nothing flagged"
    )
    return [
        _counts_line(comparison, "vs baseline"),
        *_incomplete_lines(comparison),
        *_mover_lines(comparison),
        verdict,
    ]


def _baseline_lines(
    resolution: Resolution, found: BuildRef | None, warnings: Sequence[str], profile: str
) -> list[str]:
    """The warnings about the store and the baseline's resolution, then the baseline found, or
    why there is none."""
    lines = [f"warning: {warning}" for warning in warnings]
    if resolution.warning:
        lines.append(f"warning: {resolution.warning}")
    lines.append(_baseline_line(found, profile) if found else render_no_baseline(resolution))
    return lines


def _baseline_line(found: BuildRef, profile: str) -> str:
    """The baseline: its id, run, its profile when it is not ``profile``, the commit, and when it
    was built."""
    created = found.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts = _build_parts(found, profile=found.profile != profile)
    return " · ".join([f"baseline {found.id}", *parts, f"built {created}"])


def _counts_line(comparison: Comparison, label: str) -> str:
    """``label``, then the unchanged Blicks, the skipped ones, which were not compared, whether
    flagged ``removed`` or not, the Blicks per flag, and whether removed was judged."""
    blicks, counts = comparison.blicks, comparison.counts
    unchanged = sum(not blick.change.flags and not blick.skipped for blick in blicks)
    numbers = [
        ("unchanged", unchanged),
        ("skipped", comparison.skipped),
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
        lines.append(f"{start}{mover.name} {change.percent} of scale{where}")
    if (more := comparison.counts["value"] - len(movers)) > 0:
        lines.append(f"{' ' * len(lead)}… and {more} more{pointer}")
    return lines


def _detail_lines(
    comparison: Comparison, built: Manifest | None = None, *, pointer: str = ""
) -> list[str]:
    """The Blicks whose values appeared or vanished, the new and the removed, with their messages,
    and the errors; without the errors of Blicks that have no table in ``built``, when given.
    ``pointer`` follows a shortened list of values."""
    blicks = comparison.blicks
    tables = None if built is None else {e.id for e in built.blicks if e.data is not None}
    sections = {
        "schema": [_schema_lines(b, pointer) for b in blicks if "schema" in b.change.flags],
        "new": [_named(b) for b in blicks if "new" in b.change.flags],
        "removed": [_named(b) for b in blicks if "removed" in b.change.flags],
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


def _named(blick: BlickComparison) -> list[str]:
    """A Blick's line in a section of the details: its name, and its message if any."""
    return [f"  {blick.name}  {blick.message}" if blick.message else f"  {blick.name}"]


def render_markdown(comparison: Comparison) -> str:
    """The Markdown summary of a comparison: a heading with the two builds, the counts, a table
    of the flagged Blicks, the largest change first, then the columns and values that
    appeared or vanished, the new Blicks that did not build in the baseline or were skipped there,
    the removed Blicks that were skipped, and the errors, those of the files of an incomplete
    build first. A skipped Blick that is removed has the flags ``removed (skipped)``, so that it
    does not read as a Blick that was deleted."""
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
        lines += [
            "",
            "| Blick | flags | largest change (of the chart's scale) | where |",
            "|---|---|---|---|",
        ]
    for blick in flagged:
        change = blick.change
        flags = ", ".join(flag for flag in get_args(Flag) if flag in change.flags)
        cells = [
            f"`{blick.name}`",
            f"{flags} (skipped)" if blick.skipped else flags,
            change.percent or _EMPTY,
            _where(change.where) if change.where else _EMPTY,
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    schema = [b for b in comparison.blicks if "schema" in b.change.flags]
    new = [b for b in comparison.blicks if "new" in b.change.flags and b.message]
    removed = [b for b in comparison.blicks if "removed" in b.change.flags and b.message]
    errors = [b for b in comparison.blicks if "error" in b.change.flags]
    if schema:
        lines += ["", "#### schema", ""]
    for blick in schema:
        lines += [f"- `{blick.name}`", *(f"  - {line}" for line in _schema_details(blick))]
    for title, blicks in (("new", new), ("removed", removed)):
        if blicks:
            lines += ["", f"#### {title}", ""]
            lines += [f"- `{blick.name}`: {blick.message}" for blick in blicks]
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
