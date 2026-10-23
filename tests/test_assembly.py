"""The rules that turn module records into a registry, on records built in memory."""

from pathlib import Path
from typing import Any, NamedTuple

import blicket as bk
from blicket._validation import validate_definition, validate_group
from blicket.assembly import assemble
from blicket.definitions import Definition, GroupCall, ModuleRecord
from blicket.errors import Kind, Problem, Source

LINE = bk.plots.line(x="year", y="value")
ROOT = Path("/project")


def identity(run: Any) -> Any:
    return run


class Spec(NamedTuple):
    options: dict[str, Any]
    name: str | None
    line: int


def definition(
    blick_id: str | None = None, *, name: str | None = None, line: int = 1, **options: Any
) -> Spec:
    """A ``@bk.blick`` (with ``name``) or ``bk.register`` (without), as options."""
    return Spec({"plot": LINE, "id": blick_id, **options}, name, line)


def record(
    file: str,
    *specs: Spec,
    group: str | None = None,
    title: str | None = None,
    tags: tuple[str, ...] = (),
) -> ModuleRecord:
    path = ROOT / file
    definitions = []
    for spec in specs:
        checked, problems = validate_definition(spec.options, identity, "transform")
        given = spec.options["id"]
        source = Source(path, spec.line)
        definitions.append(Definition(given, spec.name, checked, identity, problems, source))
    calls = [GroupCall(validate_group(group, title, tags), Source(path, 1))] if group else []
    name = file.removesuffix(".py").replace("/", ".")
    return ModuleRecord(name=name, file=path, group_calls=calls, definitions=definitions)


def messages(registry: bk.Registry, name: str) -> list[str]:
    (failed,) = [f for f in registry.failed if f.name == name]
    return [problem.message for problem in failed.problems]


def test_default_id_and_title_come_from_the_group_and_function() -> None:
    registry = assemble([record("blicks/flows.py", definition(name="steel_by_process"))], root=ROOT)
    blick = registry.blicks["flows/steel_by_process"]
    assert (blick.title, blick.group, blick.module) == ("Steel by process", "flows", "blicks.flows")


def test_invalid_module_name_as_group() -> None:
    registry = assemble([record("blicks/Flows.py", definition(name="steel"))], root=ROOT)
    (error,) = registry.errors
    assert (error.kind, error.location(ROOT)) == (Kind.GROUP, "blicks/Flows.py")
    assert "the module name gives the group name 'Flows'" in error.message
    assert registry.blicks == {}


def test_duplicate_id_fails_every_claimant() -> None:
    registry = assemble(
        [
            record("blicks/a.py", definition("shared/view", line=4)),
            record(
                "blicks/b.py", definition("shared/view", controls={"r": "x"}), definition(name="ok")
            ),
        ],
        root=ROOT,
    )
    assert list(registry.blicks) == ["b/ok"]
    first, second = registry.failed
    assert (first.group, second.group) == ("a", "b")
    assert first.problems[0].kind == Kind.DUPLICATE_ID
    assert "also defined at blicks/b.py:1" in first.problems[0].message


def test_alias_collisions_fail_all_involved() -> None:
    registry = assemble(
        [
            record("blicks/a.py", definition("a/one", aliases=["old/view"])),
            record("blicks/b.py", definition("b/two", aliases=["old/view"])),
            record(
                "blicks/c.py",
                definition("c/three", aliases=["a/one"]),
                definition("c/x", aliases=["c/x"]),
            ),
            record("blicks/d.py", definition("d/four", aliases=["old/fine"])),
        ],
        root=ROOT,
    )
    assert list(registry.blicks) == ["d/four"]
    assert registry.aliases == {"old/fine": "d/four"}
    assert "is also claimed by b/two (blicks/b.py:1)" in messages(registry, "a/one")[0]
    assert "listed as an alias by c/three" in messages(registry, "a/one")[1]
    assert "is the current id of a/one" in messages(registry, "c/three")[0]
    assert "is its own id" in messages(registry, "c/x")[0]


def test_groups_merge_across_modules_in_file_order() -> None:
    records = [
        record("blicks/a.py", definition(name="x"), group="shared", tags=("a",)),
        record("blicks/b.py", definition(name="y"), group="shared", title="B", tags=("b", "a")),
        record("blicks/c.py", definition(name="z"), group="shared", title="C"),
    ]
    for order in (records, records[::-1]):
        registry = assemble(order, root=ROOT)
        group = registry.groups["shared"]
        # The second module supplies the title; the third one's title is a warning.
        assert (group.title, group.modules) == ("B", ("blicks.a", "blicks.b", "blicks.c"))
        assert group.tags == ("a", "b")
        assert registry.tags_of("shared/y") == ("a", "b")
        (warning,) = registry.warnings
        assert (warning.kind, warning.location(ROOT)) == (Kind.GROUP, "blicks/c.py:1")
        assert "gets a title in blicks/b.py:1" in warning.message


def test_blick_tolerance_must_fit_digits() -> None:
    records = [record("blicks/tol.py", definition(name="precise", tolerance=1e-7))]
    assert "finer than 6 significant digits" in messages(assemble(records), "tol/precise")[0]
    assert list(assemble(records, config=bk.Config(digits=8)).blicks) == ["tol/precise"]


def test_invalid_ids_do_not_take_the_derived_id() -> None:
    registry = assemble(
        [
            record("blicks/a.py", definition("Bad/Id", name="steel"), definition("Nope")),
            record("blicks/b.py", definition(name="steel"), group="a"),
        ],
        root=ROOT,
    )
    assert list(registry.blicks) == ["a/steel"]
    assert [(f.id, f.name) for f in registry.failed] == [(None, "steel"), (None, "'Nope'")]
    assert registry.to_json()["failed"][1]["name"] == "'Nope'"


def test_function_name_that_is_no_segment_needs_an_id() -> None:
    registry = assemble([record("blicks/a.py", definition(name="SteelFlows"))])
    (failed,) = registry.failed
    assert (failed.id, failed.name) == (None, "SteelFlows")
    assert "cannot be an id segment; pass id=" in failed.problems[0].message


def test_modules_without_blicks() -> None:
    nothing = assemble([record("blicks/a.py"), record("blicks/b.py", group="b")], root=ROOT)
    (error,) = nothing.errors
    assert error.kind == Kind.NO_BLICKS
    assert "none of the 2 matched modules defines a Blick" in error.message
    assert nothing.warnings == ()
    some = assemble([record("blicks/a.py", definition(name="x")), record("blicks/notes.py")])
    (warning,) = some.warnings
    assert (warning.kind, warning.location(ROOT)) == (Kind.NO_BLICKS, "blicks/notes.py")


def test_incomplete_only_with_file_or_project_errors() -> None:
    failing = assemble([record("blicks/a.py", definition("a/x", controls={"r": 1}))])
    assert failing.has_errors
    assert not failing.incomplete
    broken = Problem(kind=Kind.IMPORT, message="boom", source=Source(ROOT / "blicks/b.py"))
    assert assemble([record("blicks/a.py", definition("a/x"))], [broken]).incomplete
