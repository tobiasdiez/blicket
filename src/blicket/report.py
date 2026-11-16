"""The reports of the commands: what ``list``, ``build``, ``push``, ``diff`` and ``check``
print, and the Markdown report of a comparison, as plain functions of what the commands
computed.

An outcome of an expectation is said one way in every report: ``outcome_sentence`` and
``outcome_worst`` in the text, the same parts in the cells of the Markdown.
"""

import importlib.metadata
import json
import textwrap
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

from blicket.baseline import Resolution
from blicket.builder import Build
from blicket.comparison import (
    COMPARE,
    TRANSITIONS,
    BlickComparison,
    BuildRef,
    Comparison,
    ExpectationComparison,
    Transition,
)
from blicket.errors import NOWHERE, Kind, Problem, Source, display_path
from blicket.expect._levels import DEFAULT_LEVEL
from blicket.expect._outcome import Outcome
from blicket.manifest import Manifest, Repository
from blicket.model import Blick, BlickEntry, CheckEntry, Entry, Registry, Unit
from blicket.schema import Flag
from blicket.store import Pushed


def _listed(registry: Registry) -> list[Entry]:
    """Built and failed units alike, each with its level, in the order of their definitions, as
    the manifest has them."""
    units = [unit.entry(level=registry.level_of(unit)) for unit in registry.units]
    return sorted([*units, *registry.failed], key=lambda entry: entry.source or NOWHERE)


def render_list_json(registry: Registry) -> str:
    """The JSON of ``blicket list``, with the absolute root, since it is local."""
    context = {"root": registry.root}
    entries = _listed(registry)

    def dump(model: BaseModel) -> Any:
        return model.model_dump(mode="json", context=context)

    report = {
        "blicket": importlib.metadata.version("blicket"),
        "root": str(registry.root),
        "groups": [dump(group) for group in registry.groups.values()],
        "blicks": [dump(entry) for entry in entries if isinstance(entry, BlickEntry)],
        "checks": [dump(entry) for entry in entries if isinstance(entry, CheckEntry)],
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


def _incomplete(checks: bool) -> str:
    """What a build line says of a build whose module failed to import; ``checks`` says that the
    project defines checks, which may be missing too."""
    return "incomplete (Blicks and checks missing)" if checks else "incomplete (Blicks missing)"


def render_list(registry: Registry, *, verbose: bool = False) -> str:
    """The text of ``blicket list``: groups with their Blicks and checks, a summary, warnings,
    errors."""
    root = registry.root
    lines = [*_project_line(root), *_group_lines(registry)]
    if lines:
        lines.append("")
    lines.append(_summary(registry))
    warnings = [(w.source, _problem_lines(w, root)) for w in registry.warnings]
    errors = [(e.source, _problem_lines(e, root, verbose)) for e in registry.errors]
    errors += [
        (unit.source, _unit_lines(unit, unit.problems, root, verbose)) for unit in registry.failed
    ]
    return "\n".join([*lines, *_section("warnings", warnings), *_section("errors", errors)])


def _project_line(root: Path | None) -> list[str]:
    """``project: <root>`` when the root is not the working directory, so paths can be found."""
    if root is None or root == Path.cwd().resolve():
        return []
    return [f"project: {root}"]


def _shape(unit: Unit) -> str:
    """What ``list`` shows of a unit in place of a Blick's plot type: ``check`` for a check."""
    return unit.plot.plot_type.name if isinstance(unit, Blick) else "check"


def _group_lines(registry: Registry) -> list[str]:
    """The groups with their units, each Blick with its plot type and each check with ``check``,
    then the expectation as declared and, with one, the level when it is not ``error``, then the
    aliases."""
    entries: dict[str, list[Unit | Entry]] = defaultdict(list)
    for entry in [*registry.units, *registry.failed]:
        entries[entry.group].append(entry)
    units = registry.units
    names = [u.id for u in units] + [f.name for f in registry.failed]
    titles = [u.title for u in units] + (["[error]"] if registry.failed else [])
    id_width = max(map(len, names), default=0)
    title_width = max(map(len, titles), default=0)
    shape_width = max((len(_shape(u)) for u in units), default=0)

    lines: list[str] = []
    for name, group in registry.groups.items():
        heading = [name, *([group.title] if group.title else [])]
        if group.tags:
            heading.append(f"[{', '.join(group.tags)}]")
        if group.level is not None:
            heading.append(f"level: {group.level}")
        lines.append("  ".join(heading))
        members = sorted(entries.get(name, []), key=lambda e: e.source or NOWHERE)
        if not members:
            lines.append("  (no Blicks)")
        for entry in members:
            if isinstance(entry, Entry):
                where = entry.source.display(registry.root) if entry.source else ""
                cells = [entry.name.ljust(id_width), "[error]".ljust(title_width), where]
            else:
                cells = [
                    entry.id.ljust(id_width),
                    entry.title.ljust(title_width),
                    _shape(entry).ljust(shape_width),
                ]
                if (expectation := entry.expect) is not None:
                    cells.append(f"expect: {expectation.words(expectation.measure)}")
                    if (level := registry.level_of(entry)) != DEFAULT_LEVEL:
                        cells.append(f"level: {level}")
                if entry.aliases:
                    cells.append(f"aliases: {', '.join(entry.aliases)}")
            lines.append(("  " + "   ".join(cells)).rstrip())
    return lines


def _summary(registry: Registry) -> str:
    """``N groups · N Blicks · N checks``, how many of them have errors, the errors, warnings."""
    parts = [_count(len(registry.groups), "group")]
    for noun, built, kind in (
        ("Blick", registry.blicks, BlickEntry),
        ("check", registry.checks, CheckEntry),
    ):
        failed = sum(isinstance(entry, kind) for entry in registry.failed)
        if noun == "check" and not built and not failed:
            continue
        counted = _count(len(built) + failed, noun)
        parts.append(f"{counted} ({failed} with errors)" if failed else counted)
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


def _unit_heading(entry: Entry, root: Path | None = None) -> str:
    """A unit's location, its kind and its name: ``  blicks/flows.py:41  Blick flows/x``."""
    where = entry.source.display(root) if entry.source else "-"
    return f"  {where}  {entry.kind} {entry.name}"


def _unit_lines(
    entry: Entry, problems: Sequence[Problem], root: Path | None, verbose: bool = False
) -> list[str]:
    """A unit's location, kind and name, then each problem's message, its traceback under
    ``-v``."""
    lines = [_unit_heading(entry, root)]
    for problem in problems:
        first, *rest = problem.message.splitlines()
        lines.append(f"    {first}{_hint(problem, verbose)}")
        lines.extend(f"    {line}" for line in rest)
        lines.extend(_traceback_lines(problem, verbose))
    return lines


def _value(value: float, distance: float | None) -> str:
    """A measure's value as the reports show it, to three significant digits, ``-3.2e-12``, and
    to more while rounding would move it as far as its ``distance`` from the bound it violates,
    so that it never reads as the bound: ``1.0004`` for a value at most 1."""
    for digits in range(3, 18):
        text = f"{value:.{digits}g}"
        if not distance or abs(float(text) - value) < distance:
            return text
    return repr(value)


def _rows(number: int) -> str:
    return f"{number:,} row{'' if number == 1 else 's'}"


def outcome_rows(outcome: Outcome) -> str:
    """How many rows offend, of how many a bound was applied to, how many of them lie within
    ``warn_within``, and that the level made them a warning when it did: ``3 of 2,412 rows
    offend``, ``200,131 rows offend, all within warn_within``, ``1 row offends, a warning at level
    warn``."""
    offending = outcome.offending
    verb = "offends" if offending == 1 else "offend"
    if outcome.evaluated is not None:
        parts = [f"{offending:,} of {_rows(outcome.evaluated)} {verb}"]
    else:
        parts = [f"{_rows(offending)} {verb}"]
    if outcome.within and outcome.within == offending:
        parts.append("all within warn_within")
    elif outcome.within:
        parts.append(f"{outcome.within:,} within warn_within")
    if outcome.result == "warning" and outcome.within < offending:
        parts.append("a warning at level warn")
    return ", ".join(parts)


def outcome_sentence(outcome: Outcome) -> str:
    """An outcome in a sentence, as every report says it: ``3 of 2,412 rows offend: expected
    value between 0 and 1``, ``no row offends: expected no rows, by value``, ``no row offends, as
    no row has a value: expected value at least 0``, or why it cannot be evaluated."""
    if outcome.result == "error":
        return f"cannot evaluate {outcome.expectation}: {outcome.message}"
    if outcome.met:
        empty = ", as no row has a value" if outcome.evaluated == 0 else ""
        return f"no row offends{empty}: expected {outcome.expectation}"
    return f"{outcome_rows(outcome)}: expected {outcome.expectation}"


def outcome_worst(outcome: Outcome) -> str | None:
    """Where an outcome's offending rows are worst: ``worst 1.07 at Region=SSA, Time=2050``, or
    ``first at ...`` when nothing ranks the rows; ``None`` when there is nothing to say. A line
    break in a dimension value is a space, so that the line stays one."""
    if not outcome.offends:
        return None
    at = f" at {' '.join(_where(outcome.where).splitlines())}" if outcome.where else ""
    if outcome.worst is not None:
        return f"worst {_value(outcome.worst, outcome.distance)}{at}"
    return f"first{at}" if at else None


def _outcome_lines(entry: Entry, outcome: Outcome) -> list[str]:
    """A unit with its outcome: its heading, the sentence and where it is worst."""
    worst = outcome_worst(outcome)
    return [
        _unit_heading(entry),
        f"    {outcome_sentence(outcome)}",
        *([f"    {worst}"] if worst else []),
    ]


def _head(repository: Repository | None) -> str:
    """The commit of the repository holding the Blicks, not of the model that produced the run."""
    if repository is None:
        return "no git commit"
    return f"blicks at {repository.commit[:7]}{' (dirty)' if repository.dirty else ''}"


def render_build(result: Build, *, verbose: bool = False) -> str:
    """The text of ``blicket build``: the run, the counts, the build directory, the skipped
    Blicks and checks with their reasons, then problems and the expectations not met, the most
    severe last: the warnings, the expectations warned, those failed, the errors, among which the
    expectations that cannot be evaluated."""
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
        *_build_summary(manifest),
        f"build {manifest.build.id} → {where}{existed}",
    ]
    warnings: list[_Block] = []
    errors: list[_Block] = []
    for problem in manifest.problems:
        blocks = errors if problem.severity == "error" else warnings
        blocks.append((problem.source, _problem_lines(problem, None, verbose)))
    for entry in manifest.entries:
        for severity, blocks in (("error", errors), ("warning", warnings)):
            if problems := [p for p in entry.problems if p.severity == severity]:
                blocks.append((entry.source, _unit_lines(entry, problems, None, verbose)))
    outcomes: dict[str, list[_Block]] = {"warning": [], "failed": [], "error": errors}
    for entry, outcome in manifest.outcomes:
        if outcome.result in outcomes:
            outcomes[outcome.result].append((entry.source, _outcome_lines(entry, outcome)))
    sections = [
        *_section("skipped", _skipped_blocks(manifest)),
        *_section("warnings", warnings),
        *_section("expectations warned", outcomes["warning"]),
        *_section("expectations failed", outcomes["failed"]),
        *_section("errors", errors),
    ]
    return "\n".join([*lines, *sections])


def _skipped_blocks(manifest: Manifest) -> list[_Block]:
    """The skipped Blicks and checks grouped by their reason, a block per reason, ordered by
    location like the other sections: the reason, its further lines indented as the names of its
    units under it, which are wrapped to 100 columns."""
    by_reason: dict[str, list[Entry]] = defaultdict(list)
    for entry in manifest.entries:
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


def _units_line(entries: Sequence[Entry], noun: str, done: str) -> str:
    """``N Blicks: n built · n skipped · n errors``, with ``done`` for the units that did."""
    statuses = Counter(entry.status for entry in entries)
    parts = [f"{statuses['ok']} {done}"]
    if statuses["skipped"]:
        parts.append(f"{statuses['skipped']} skipped")
    if statuses["error"]:
        parts.append(_count(statuses["error"], "error"))
    return f"{_count(len(entries), noun)}: {' · '.join(parts)}"


def _build_summary(manifest: Manifest) -> list[str]:
    """``N Blicks: n built · n skipped · n errors`` unless the project defines checks and no
    Blick, ``N checks: n ran · ...`` when it defines checks, the first of them with the file-level
    errors by kind, the warnings of units and files, and the incompleteness; then
    ``expectations: n met · n warnings · n failed · n cannot be evaluated`` when a unit has an
    expectation."""
    lines: list[str] = []
    if manifest.blicks or not manifest.checks:
        lines.append(_units_line(manifest.blicks, "Blick", "built"))
    if manifest.checks:
        lines.append(_units_line(manifest.checks, "check", "ran"))
    file_errors = Counter(p.kind for p in manifest.problems if p.severity == "error")
    parts = [_count(n, f"{kind.replace('_', ' ')} error") for kind, n in file_errors.items()]
    problems = [*manifest.problems, *(p for entry in manifest.entries for p in entry.problems)]
    if warnings := sum(problem.severity == "warning" for problem in problems):
        parts.append(_count(warnings, "warning"))
    if manifest.build.incomplete:
        parts.append(_incomplete(bool(manifest.checks)))
    lines[0] = " · ".join([lines[0], *parts])
    if any(entry.expectation is not None for entry in manifest.entries):
        results = manifest.results
        counted = [
            f"{results['met']} met" if results["met"] else "",
            _count(results["warning"], "warning") if results["warning"] else "",
            f"{results['failed']} failed" if results["failed"] else "",
            f"{results['error']} cannot be evaluated" if results["error"] else "",
        ]
        lines.append(f"expectations: {' · '.join(filter(None, counted)) or 'none evaluated'}")
    return lines


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
    """The text of ``blicket diff``: the two builds, the counts, the transitions of the
    expectations, why removed Blicks were not judged, the top movers, then the Blicks whose values
    appeared or vanished, the new and the removed Blicks, the units of each transition but still
    failing, and the errors."""
    checks = bool(comparison.checks)
    return "\n".join(
        [
            _build_line("baseline", comparison.baseline, checks),
            _build_line("current", comparison.current, checks),
            _counts_line(comparison, _blicks_label(comparison)),
            *_transitions_line(comparison),
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
    is none, the comparison's summary, the transitions of the expectations and the verdict, where
    it was written, the push, and the comparison's details.

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
        parts = _build_parts(
            found, profile=found.profile != manifest.run.profile, checks=bool(manifest.checks)
        )
        verdict = (
            f"flagged: {comparison.flagged} of {_count(len(comparison.blicks), 'Blick')}"
            if comparison.flagged
            else "nothing flagged, but the build is incomplete"
            if comparison.incomplete
            else "nothing flagged"
        )
        if failed := manifest.failed_expectations:
            verdict += f" · failed: {_count(failed, 'expectation')}"
        lines += [
            " · ".join([f"baseline {found.id}", *parts, f"built {created}"]),
            _counts_line(comparison, "vs baseline")
            if comparison.blicks
            else "vs baseline: no Blicks",
            *_transitions_line(comparison),
            *_incomplete_lines(comparison),
            *_mover_lines(comparison),
            verdict,
            f"comparison → {display_path(result.path / COMPARE / found.id, Path.cwd())}",
        ]
        details = _detail_lines(comparison, manifest)
    if pushed is not None:
        lines.append(render_push(pushed))
    return render_build(result, verbose=verbose) + "\n\n" + "\n".join([*lines, *details])


def _blicks_label(comparison: Comparison) -> str:
    """``N Blicks``, the label of the counts of ``diff`` and the Markdown, ``no Blicks`` for a
    project of checks only, as ``check`` says it."""
    return _count(len(comparison.blicks), "Blick") if comparison.blicks else "no Blicks"


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
        parts.append(_not_judged(comparison))
    if counts["error"]:
        parts.append(_count(counts["error"], "error"))
    return f"{label}: {' · '.join(parts)}" if parts else label


# The transitions as the reports name them.
_TRANSITION_WORDS: dict[Transition, str] = {
    "broken": "broken",
    "new": "new",
    "fixed": "fixed",
    "still_failing": "still failing",
    "dropped": "dropped",
}


def _transitions_line(comparison: Comparison) -> list[str]:
    """``expectations vs baseline: 1 broken · 1 new · ...`` when an expectation has a
    transition."""
    counts = comparison.transitions
    parts = [f"{counts[t]} {_TRANSITION_WORDS[t]}" for t in TRANSITIONS if counts[t]]
    return [f"expectations vs baseline: {' · '.join(parts)}"] if parts else []


def _against(related: ExpectationComparison) -> str:
    """What a unit's expectation is now against the baseline: ``failed, was met``, with why a
    side has no outcome: ``was failed; skipped now: the run has no stocks``."""
    parts = []
    if related.current is not None:
        parts.append(related.current.result)
    if related.baseline is not None:
        parts.append(f"was {related.baseline.result}")
    said = ", ".join(parts)
    return f"{said}; {related.message}" if related.message else said


def _transition_blocks(comparison: Comparison) -> dict[str, list[list[str]]]:
    """The units of each transition but still failing, a line each, by section title, the most
    severe last: fixed, dropped, new, broken."""
    sections: dict[str, list[list[str]]] = {
        f"expectations {_TRANSITION_WORDS[t]}": [] for t in ("fixed", "dropped", "new", "broken")
    }
    for unit, related in comparison.expectations():
        if related.transition is None or related.transition == "still_failing":
            continue
        title = f"expectations {_TRANSITION_WORDS[related.transition]}"
        sections[title].append([f"  {unit.kind} {unit.name}  {_against(related)}"])
    return sections


def _not_judged(comparison: Comparison) -> str:
    """What was not judged in an incomplete build: the removed Blicks, and the dropped checks in a
    comparison with checks."""
    return "removed and dropped not judged" if comparison.checks else "removed not judged"


def _incomplete_lines(comparison: Comparison) -> list[str]:
    if not comparison.incomplete:
        return []
    return [f"{_not_judged(comparison)}: {'; '.join(comparison.incomplete)}"]


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
    the units of each transition of their expectations but still failing, and the errors of both
    kinds of units; without those the build's report gives when ``built`` is given: of the Blicks
    without a table, the checks in error and the expectations that cannot be evaluated.
    ``pointer`` follows a shortened list of values."""
    blicks = comparison.blicks
    errors = _errors(comparison, built)
    sections = {
        "schema": [_schema_lines(b, pointer) for b in blicks if "schema" in b.change.flags],
        "new": [_named(b) for b in blicks if "new" in b.change.flags],
        "removed": [_named(b) for b in blicks if "removed" in b.change.flags],
        **_transition_blocks(comparison),
        "errors": [[f"  {name}  {message}"] for name, message in errors],
    }
    lines: list[str] = []
    for title, blocks in sections.items():
        lines += _section(title, [(None, block) for block in blocks])
    return lines


def _errors(comparison: Comparison, built: Manifest | None = None) -> list[tuple[str, str | None]]:
    """The errors of a comparison by unit name, with their cause: the units in error, then the
    expectations that cannot be evaluated now. With ``built``, whose report gives the errors of
    its units, only those the comparison alone finds: of Blicks that built a table."""
    if built is not None:
        tables = {entry.id for entry in built.blicks if entry.data is not None}
        return [(unit.name, unit.message) for unit in comparison.errors() if unit.id in tables]
    return [
        *((unit.name, unit.message) for unit in comparison.errors()),
        *((unit.name, outcome_sentence(outcome)) for unit, outcome in comparison.unevaluable()),
    ]


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
    checks = bool(comparison.checks)
    lines = [
        f"### blicket: run {current.run} (`{current.id[:8]}`) against run {baseline.run} "
        f"(`{baseline.id[:8]}`)",
        "",
        " · ".join([f"- baseline `{baseline.id}`", *_build_parts(baseline, checks=checks)]),
        " · ".join([f"- current `{current.id}`", *_build_parts(current, checks=checks)]),
        "",
        _counts_line(comparison, _blicks_label(comparison)),
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
        lines.append(_markdown_row(cells))
    schema = [b for b in comparison.blicks if "schema" in b.change.flags]
    new = [b for b in comparison.blicks if "new" in b.change.flags and b.message]
    removed = [b for b in comparison.blicks if "removed" in b.change.flags and b.message]
    errors = _errors(comparison)
    if schema:
        lines += ["", "#### schema", ""]
    for blick in schema:
        lines += [f"- `{blick.name}`", *(f"  - {line}" for line in _schema_details(blick))]
    for title, blicks in (("new", new), ("removed", removed)):
        if blicks:
            lines += ["", f"#### {title}", ""]
            lines += [f"- `{blick.name}`: {blick.message}" for blick in blicks]
    shown = [
        (unit.kind, unit.name, related.current, related)
        for unit, related in comparison.expectations()
        if (related.current is not None and related.current.offends)
        or related.transition in ("fixed", "dropped")
    ]
    lines += _expectation_table(shown)
    if errors or comparison.incomplete:
        lines += ["", "#### errors", ""]
        lines += [f"- {reason}" for reason in comparison.incomplete]
        lines += [f"- `{name}`: {_cell(message or '')}" for name, message in errors]
    return "\n".join(lines) + "\n"


def render_markdown_no_baseline(built: Manifest, resolution: Resolution) -> str:
    """The Markdown summary of a check without a baseline: the heading with the build, why there
    is none, the expectations whose rows offend, and the errors: of the files, of the units that
    failed, and of the expectations that cannot be evaluated."""
    lines = [
        f"### blicket: run {built.run.id} (`{built.build.id[:8]}`)",
        "",
        render_no_baseline(resolution),
    ]
    shown = [
        (entry.kind, entry.name, outcome, None)
        for entry, outcome in built.outcomes
        if outcome.offends
    ]
    lines += _expectation_table(shown)
    errors = [
        f"- {problem.location() or 'the project'}: {_first_line(problem.message)}"
        for problem in built.problems
        if problem.severity == "error"
    ]
    for entry in built.entries:
        if failed := [p for p in entry.problems if p.severity == "error"]:
            errors.append(f"- `{entry.name}`: {_first_line(failed[0].message)}")
        if entry.outcome is not None and entry.outcome.result == "error":
            errors.append(f"- `{entry.name}`: {_cell(outcome_sentence(entry.outcome))}")
    if errors:
        lines += ["", "#### errors", "", *errors]
    return "\n".join(lines) + "\n"


def _first_line(text: str) -> str:
    """The first line of ``text``, as a Markdown list item holds it."""
    return _cell(next(iter(text.splitlines()), ""))


def _cell(text: str) -> str:
    """``text`` in a cell of a Markdown table or a list item: a ``|`` escaped, a line break a
    space."""
    return " ".join(text.replace("|", "\\|").splitlines())


def _markdown_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |"


type _Shown = tuple[str, str, Outcome | None, ExpectationComparison | None]


def _expectation_table(shown: Iterable[_Shown]) -> list[str]:
    """The table "expectations" of the Markdown: per unit its kind and name, the result, the
    rows, the worst value and where it is, and, with a comparison, the transition against the
    baseline; the failed first, then the warned, the dropped and the fixed."""
    rows = list(shown)
    if not rows:
        return []
    compared = any(related is not None for *_, related in rows)

    def severity(row: _Shown) -> int:
        _, _, outcome, related = row
        if outcome is not None and outcome.offends:
            return 0 if outcome.result == "failed" else 1
        return 2 if related is not None and related.transition == "dropped" else 3

    header = [
        "Blick or check",
        "result",
        "rows",
        "worst",
        "where",
        *(["against the baseline"] if compared else []),
    ]
    lines = [
        "",
        "#### expectations",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for kind, name, outcome, related in sorted(rows, key=severity):
        offends = outcome is not None and outcome.offends
        cells = [
            f"{kind} `{name}`",
            outcome.result if outcome else _EMPTY,
            outcome_rows(outcome) if outcome and offends else _EMPTY,
            _value(outcome.worst, outcome.distance)
            if outcome and outcome.worst is not None
            else _EMPTY,
            _where(outcome.where) if outcome and outcome.where else _EMPTY,
        ]
        if compared:
            cells.append(_markdown_against(related))
        lines.append(_markdown_row(cells))
    return lines


def _markdown_against(related: ExpectationComparison | None) -> str:
    """A unit's transition as the Markdown table says it: ``broken (was met)``, ``still
    failing``, ``dropped (was failed; skipped now: ...)``."""
    if related is None or related.transition is None:
        return _EMPTY
    words = _TRANSITION_WORDS[related.transition]
    said = [f"was {related.baseline.result}"] if related.baseline is not None else []
    if related.transition in ("new", "dropped") and related.message:
        said.append(related.message)
    return f"{words} ({'; '.join(said)})" if said else words


def _build_line(label: str, build: BuildRef, checks: bool) -> str:
    return " · ".join([f"{label:<8} {build.id}", *_build_parts(build, checks=checks)])


def _build_parts(build: BuildRef, *, profile: bool = True, checks: bool = False) -> list[str]:
    """The run, the profile unless left out, the commit, and whether the build is incomplete;
    ``checks`` says that the project defines checks."""
    parts = [f"run {build.run}", *([f"profile {build.profile}"] if profile else [])]
    parts.append(_head(build.repository))
    if build.incomplete:
        parts.append(_incomplete(checks))
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
