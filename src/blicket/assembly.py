"""Assembly: from the records of executed Blick modules to a ``Registry``.

Finalises each module record (its group, default ids and titles), then checks across modules:
groups contributed by several modules, ids claimed twice and alias collisions. Works on records
alone, so it needs no files.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from blicket._validation import SEGMENT_RULE, default_title, validate_group
from blicket.config import PYPROJECT
from blicket.definitions import Definition, ModuleRecord
from blicket.errors import NOWHERE, SKIPPED, Kind, Problem, Source
from blicket.model import Blick, BlickEntry, Group, Registry


@dataclass
class _Entry:
    """One definition on its way to a Blick or a failed Blick; its problems collect here."""

    definition: Definition
    id: str | None
    group: str
    module: str
    problems: list[Problem] = field(default_factory=list)

    @property
    def source(self) -> Source:
        return self.definition.source

    def add(self, kind: str, message: str) -> None:
        ids = (self.id,) if self.id else ()
        self.problems.append(
            Problem(kind=kind, message=message, source=self.source, module=self.module, ids=ids)
        )

    def where(self, root: Path | None) -> str:
        return f"{self.id} ({self.source.display(root)})"


# A module's contribution: its group and the line of its bk.group() call, its definitions as
# entries, and its file-level problems.
type _Finalised = tuple[Group | None, int | None, list[_Entry], list[Problem]]


def _resolve_group(record: ModuleRecord) -> tuple[Group | None, list[str], int | None]:
    """The module's group from its first ``bk.group()`` call or its name, the problems, the line.

    The group is ``None`` when its name is unusable.
    """
    if not record.group_calls:
        name = record.name.rpartition(".")[2]
        if validate_group(name).name is None:
            problem = (
                f"the module name gives the group name {name!r}, which is not valid "
                f"({SEGMENT_RULE}); call bk.group('...') in the module or rename the file"
            )
            return None, [problem], None
        return Group(name=name, modules=(record.name,)), [], None

    first = record.group_calls[0]
    arguments = first.arguments
    problems = list(arguments.problems)
    if len(record.group_calls) > 1:
        lines = ", ".join(str(call.source.line) for call in record.group_calls)
        problems.append(
            f"bk.group() is called {len(record.group_calls)} times (lines {lines}); call it once "
            "per module and move Blicks of another group into their own module"
        )
    if arguments.name is None:
        return None, problems, first.source.line
    group = Group(
        name=arguments.name, title=arguments.title, tags=arguments.tags, modules=(record.name,)
    )
    return group, problems, first.source.line


def _group_problem(record: ModuleRecord, messages: list[str], line: int | None) -> Problem:
    return Problem(
        kind=Kind.GROUP,
        message="\n".join(messages),
        source=Source(record.file, line) if record.file else None,
        module=record.name,
        ids=tuple(d.options.id for d in record.definitions if d.options.id),
    )


def _finalise(record: ModuleRecord) -> _Finalised:
    """Resolve one module's group, default ids and titles, and check each definition."""
    if not record.group_calls and not record.definitions:
        return None, None, [], []
    group, group_messages, line = _resolve_group(record)
    if group is None:
        return None, line, [], [_group_problem(record, [*group_messages, SKIPPED], line)]
    problems = [_group_problem(record, group_messages, line)] if group_messages else []

    entries: list[_Entry] = []
    for definition in record.definitions:
        entry = _Entry(definition, definition.blick_id(group.name), group.name, record.name)
        if definition.id_problem:
            entry.add(Kind.INVALID_DEFINITION, definition.id_problem)
        for message in definition.problems:
            entry.add(Kind.INVALID_DEFINITION, message)
        entries.append(entry)
    return group, line, entries, problems


def _build(entry: _Entry) -> Blick:
    definition = entry.definition
    options = definition.options
    transform = definition.transform
    # Every definition without an id, a plot or a callable transform has an argument problem.
    assert entry.id is not None
    assert options.plot is not None
    assert callable(transform)
    return Blick(
        id=entry.id,
        title=options.title or default_title(definition.function_name or entry.id.split("/")[-1]),
        description=options.description,
        group=entry.group,
        tags=options.tags,
        plot=options.plot,
        controls=options.controls,
        defaults=options.defaults,
        tolerance=options.tolerance,
        aliases=options.aliases,
        dims=options.dims,
        measures=options.measures,
        order=options.order,
        transform=transform,
        module=entry.module,
        source=definition.source,
    )


def assemble(
    records: Sequence[ModuleRecord],
    problems: Sequence[Problem] = (),
    *,
    root: Path | None = None,
) -> Registry:
    """Build a registry from module records.

    The records are taken in the order of their files, so that "first wins" rules do not depend
    on the order in which modules ran. ``problems`` are those found before assembly, such as
    import errors. Every Blick with a problem goes to ``Registry.failed``.
    """
    found = list(problems)
    ordered = sorted(
        records, key=lambda r: (r.file is None, r.file.as_posix() if r.file else r.name)
    )
    modules = [(record, _finalise(record)) for record in ordered]
    groups = _merge_groups(modules, found, root)
    entries = [entry for _, (_, _, module_entries, _) in modules for entry in module_entries]
    for _, (_, _, _, module_problems) in modules:
        found.extend(module_problems)

    if not entries and not any(problem.severity == "error" for problem in found):
        found.append(
            Problem(
                kind=Kind.NO_BLICKS,
                message=(
                    f"none of the {len(records)} matched modules defines a Blick; add @bk.blick"
                ),
                source=Source(root / PYPROJECT) if root else None,
            )
        )
    else:
        found.extend(_empty_module_warning(r) for r, _ in modules if _defines_nothing(r))

    _check_duplicates(entries, root)
    aliases = _check_aliases(entries, root)
    blicks: dict[str, Blick] = {}
    failed: list[BlickEntry] = []
    for entry in entries:
        # A Blick with valid arguments has a definition even when another check failed.
        valid = not entry.definition.problems and entry.definition.id_problem is None
        blick = _build(entry) if valid else None
        if blick is not None and not entry.problems:
            blicks[blick.id] = blick
            continue
        failed.append(
            BlickEntry(
                id=entry.id,
                name=entry.id or entry.definition.name,
                aliases=entry.definition.options.aliases,
                group=entry.group,
                module=entry.module,
                source=entry.source,
                definition=blick.definition() if blick else None,
                problems=tuple(entry.problems),
            )
        )
    aliases = {alias: blick_id for alias, blick_id in aliases.items() if blick_id in blicks}

    return Registry(
        root=root,
        blicks=blicks,
        failed=tuple(sorted(failed, key=lambda blick: blick.source or NOWHERE)),
        groups=dict(sorted(groups.items())),
        aliases=aliases,
        problems=tuple(sorted(found, key=lambda problem: problem.sort_key)),
    )


def _defines_nothing(record: ModuleRecord) -> bool:
    """A Blick module without definitions; an empty ``__init__.py`` is a mere package marker."""
    is_package = record.file is not None and record.file.name == "__init__.py"
    return not record.definitions and (bool(record.group_calls) or not is_package)


def _empty_module_warning(record: ModuleRecord) -> Problem:
    return Problem(
        kind=Kind.NO_BLICKS,
        severity="warning",
        message="defines no Blicks; add @bk.blick, or rename it to _<name>.py if it is a helper",
        source=Source(record.file) if record.file else None,
        module=record.name,
    )


def _check_duplicates(entries: Sequence[_Entry], root: Path | None) -> None:
    """An id claimed twice fails every claimant: no first-come rule a file rename could flip."""
    claimants: dict[str, list[_Entry]] = {}
    for entry in entries:
        if entry.id is not None:
            claimants.setdefault(entry.id, []).append(entry)
    for blick_id, claiming in claimants.items():
        if len(claiming) < 2:
            continue
        for entry in claiming:
            others = ", ".join(o.source.display(root) for o in claiming if o is not entry)
            entry.add(
                Kind.DUPLICATE_ID,
                f"id {blick_id} is also defined at {others}; give one of them a different id",
            )


def _check_aliases(entries: Sequence[_Entry], root: Path | None) -> dict[str, str]:
    """Map each alias to its Blick; an alias claimed twice or equal to an id fails all involved."""
    holders: dict[str, list[_Entry]] = {}
    owners: dict[str, list[_Entry]] = {}
    for entry in entries:
        if entry.id is None:
            continue
        holders.setdefault(entry.id, []).append(entry)
        for alias in entry.definition.options.aliases:
            owners.setdefault(alias, []).append(entry)

    aliases: dict[str, str] = {}
    for alias, owning in owners.items():
        holding = holders.get(alias, [])
        if len(owning) == 1 and not holding:
            aliases[alias] = str(owning[0].id)
            continue
        for entry in owning:
            if any(entry is holder for holder in holding):
                message = f"alias {alias!r} is its own id; remove it"
            elif holding:
                message = (
                    f"alias {alias!r} is the current id of {holding[0].where(root)}; remove it"
                )
            else:
                others = ", ".join(other.where(root) for other in owning if other is not entry)
                message = f"alias {alias!r} is also claimed by {others}; keep it on one Blick only"
            entry.add(Kind.ALIAS_COLLISION, message)
        for holder in holding:
            if not any(holder is owner for owner in owning):
                listed_by = ", ".join(owner.where(root) for owner in owning)
                holder.add(
                    Kind.ALIAS_COLLISION,
                    f"its id is listed as an alias by {listed_by}; remove that alias",
                )
    return aliases


def _merge_groups(
    modules: Sequence[tuple[ModuleRecord, _Finalised]], found: list[Problem], root: Path | None
) -> dict[str, Group]:
    """One group per name: the first title in file order, the union of the tags."""
    groups: dict[str, Group] = {}
    title_from: dict[str, Source] = {}
    for record, (group, line, _, _) in modules:
        if group is None:
            continue
        here = Source(record.file, line) if record.file else NOWHERE
        existing = groups.get(group.name)
        if existing is None:
            groups[group.name] = group
            if group.title is not None:
                title_from[group.name] = here
            continue
        title = existing.title
        if group.title is not None and title is None:
            title = group.title
            title_from[group.name] = here
        elif group.title is not None:
            found.append(
                Problem(
                    kind=Kind.GROUP,
                    severity="warning",
                    message=(
                        f"group {group.name!r} gets a title in "
                        f"{title_from[group.name].display(root)} ({title!r}) and here "
                        f"({group.title!r}); the first is used, give the title in one module only"
                    ),
                    source=here,
                    module=record.name,
                )
            )
        groups[group.name] = Group(
            name=group.name,
            title=title,
            tags=tuple(dict.fromkeys((*existing.tags, *group.tags))),
            modules=(*existing.modules, *group.modules),
        )
    return groups
