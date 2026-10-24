"""The definition API, used directly from this module, outside discovery."""

import functools
from typing import TYPE_CHECKING, Any

import pytest

import blicket as bk
from blicket import definitions
from blicket._validation import _CHECKS, BlickOptions
from blicket.assembly import assemble
from blicket.model import BlickDefinition

if TYPE_CHECKING:
    # Bound for the type checker only, as such imports are in Blick modules.
    from collections.abc import Sized as RunType

LINE = bk.plots.line(x="year", y="value")
# For calls that are wrong on purpose, which the type checker would reject.
register: Any = bk.register


def assembled() -> bk.Registry:
    """The registry made of what this module defined."""
    record = definitions.module_record(__name__)
    assert record is not None, "nothing was recorded for this module"
    return assemble([record])


def identity(run: Any) -> Any:
    return run


def test_decorator_records_and_returns_the_function() -> None:
    bk.group("defs", title="Definitions", tags=["t"])

    @bk.blick(plot=LINE, controls={"region": "split"})
    def steel_by_process(run: Any) -> Any:
        """Steel flows.

        By process."""
        return run

    assert steel_by_process(1) == 1
    registry = assembled()
    assert registry.groups["defs"] == bk.Group(
        name="defs", title="Definitions", tags=("t",), modules=(__name__,)
    )
    blick = registry.blicks["defs/steel_by_process"]
    assert (blick.title, blick.description) == ("Steel by process", "Steel flows.\n\nBy process.")
    assert blick.transform is steel_by_process
    assert blick.source is not None
    assert blick.source.line == steel_by_process.__code__.co_firstlineno


def test_group_defaults_to_the_module_name() -> None:
    bk.blick(plot=LINE)(identity)
    group = __name__.rpartition(".")[2]
    assert list(assembled().blicks) == [f"{group}/identity"]


def test_every_option_is_checked_stored_and_named() -> None:
    assert _CHECKS.keys() == BlickOptions.__optional_keys__
    samples: dict[str, Any] = {
        "id": "defs/x",
        "title": "X",
        "description": "Text.",
        "plot": LINE,
        "controls": {"region": "filter"},
        "defaults": {"region": "EUR"},
        "tolerance": 1e-3,
        "aliases": ["defs/old_x"],
        "tags": ["t"],
        "dims": ["year"],
        "measures": ["value"],
        "order": {"region": ["EUR"]},
    }
    assert samples.keys() == BlickOptions.__optional_keys__
    bk.register(transform=identity, **samples)
    blick = assembled().blicks["defs/x"]
    stored = {key: getattr(blick, key) for key in samples}
    assert stored == {
        **samples,
        "aliases": ("defs/old_x",),
        "tags": ("t",),
        "dims": ("year",),
        "measures": ("value",),
        "order": {"region": ("EUR",)},
    }


def test_options_are_the_definition_fields_plus_the_identity() -> None:
    identity = {"id", "aliases"}  # recorded on the Blick's entry, beside its definition
    assert BlickOptions.__optional_keys__ == BlickDefinition.model_fields.keys() | identity


def test_register_defaults_the_title_to_the_last_segment() -> None:
    bk.register(id="defs/scrap-flows", plot=LINE, transform=lambda run, f="scrap": (run, f))
    blick = assembled().blicks["defs/scrap-flows"]
    assert (blick.title, blick.transform(1)) == ("Scrap flows", (1, "scrap"))


def test_invalid_definition_raises_with_location_name_and_problem() -> None:
    with pytest.raises(bk.DefinitionError) as info:

        @bk.blick(id="Flows/Steel", plot=LINE)
        def view(run: Any) -> Any:
            return run

    first, problem = str(info.value).splitlines()
    assert first.startswith(f"{__file__}:")
    assert first.endswith("  Blick view")
    assert problem == (
        "    id 'Flows/Steel' is not valid: lowercase letters, digits, '_' and '-' in two or more "
        "'/'-separated segments"
    )
    assert definitions.module_record(__name__) is None


@pytest.mark.parametrize("bad_id", ["Flows/Steel", "steel", "flows/", "flows/a.b", "flows/_x", 5])
def test_invalid_ids(bad_id: object) -> None:
    with pytest.raises(bk.DefinitionError, match="is not valid"):
        register(id=bad_id, plot=LINE, transform=identity)


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda: bk.register(id="flows/con", plot=LINE, transform=identity), "reserved name"),
        (lambda: bk.register(plot=LINE, transform=identity), "pass id="),
        (lambda: bk.register(id="defs/x", plot=LINE), "transform= is missing"),
        (lambda: bk.blick(plot=LINE)(functools.partial(identity)), "pass id="),
        (lambda: bk.blick()(identity), "plot= is missing"),
        (lambda: bk.blick(plot=LINE)(lambda run, extra: run), "must take exactly one"),
        (lambda: register(id="defs/x", plot=LINE, transform="no"), "must be a function"),
        (lambda: register(id="defs/x", plot=LINE, transform=identity, plto=LINE), "plot=?"),
        (lambda: bk.blick(plot=LINE, transform=identity)(identity), "belongs to bk.register()"),
        (lambda: bk.blick(identity), "with parentheses"),
        (lambda: bk.group(title="Steel"), "needs the group name first"),
        (lambda: bk.group("Bad Group"), "group name 'Bad Group' is not valid"),
        (lambda: bk.group("defs", title=""), "the group title must be a non-empty string"),
        (lambda: bk.group("defs", tags="x"), "tags must be a list of strings"),
        (lambda: bk.group("con"), "reserved name"),
        (lambda: bk.slug("!!!"), "without letters or digits"),
        (lambda: bk.slug("CON"), "reserved name"),
    ],
)
def test_definition_errors(make: Any, expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        make()
    assert expected in str(info.value)
    assert "0x" not in str(info.value)  # no repr of a callable


def test_reserved_function_name_asks_for_an_id() -> None:
    def view(run: Any) -> Any:
        return run

    view.__name__ = "con"
    with pytest.raises(bk.DefinitionError, match="'con', a reserved name on Windows; pass id="):
        bk.blick(plot=LINE)(view)


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"controls": {"r": "facet"}}, "controls['r'] is 'facet'"),
        ({"controls": {1: "split"}}, "use a column name"),
        ({"controls": ["r"]}, "controls must be a dict"),
        ({"defaults": {"year": object()}}, "defaults['year'] is of type object"),
        ({"defaults": {"nested": {1: "a"}}}, "has the key 1; keys must be strings"),
        ({"defaults": {"x": float("nan")}}, "a number that JSON cannot hold"),
        ({"defaults": ["year"]}, "defaults must be a dict"),
        ({"order": {"scenario": "low"}}, "order['scenario'] must be a list"),
        ({"tags": "mfa"}, "tags must be a list of strings"),
        ({"tags": ["", 1]}, "list of non-empty strings, got '', 1"),
        ({"aliases": ["Old/x"]}, "alias 'Old/x' is not valid"),
        ({"aliases": ["a/b", "a/b"]}, "aliases lists an id twice"),
        ({"dims": "year"}, "dims must be a list of strings"),
        ({"tolerance": -1.0}, "tolerance must be a positive number below 1"),
        ({"tolerance": 1}, "tolerance must be a positive number below 1, got 1"),
        ({"title": ""}, "title must be a non-empty string"),
        ({"description": 3}, "description must be a string"),
        ({"plot": bk.plots.line}, "plot must be a plot spec"),
    ],
)
def test_invalid_fields(options: dict[str, Any], expected: str) -> None:
    with pytest.raises(bk.DefinitionError) as info:
        register(**{"id": "defs/x", "plot": LINE, "transform": identity, **options})
    assert expected in str(info.value)


def test_every_problem_of_a_blick_is_reported() -> None:
    controls: Any = {"a": "bogus", "b": "also"}
    with pytest.raises(bk.DefinitionError) as info:
        bk.register(id="defs/x", plot=LINE, transform=identity, controls=controls, tags="t")
    assert len(str(info.value).splitlines()) == 4


def test_transform_without_a_signature_is_accepted() -> None:
    bk.register(id="defs/x", plot=LINE, transform=str)
    assert list(assembled().blicks) == ["defs/x"]


def test_transform_annotated_with_a_type_checking_import_is_accepted() -> None:
    def total(run: RunType) -> RunType:
        return run

    bk.register(id="defs/x", plot=LINE, transform=total)
    assert list(assembled().blicks) == ["defs/x"]


def test_group_called_twice() -> None:
    bk.group("defs")
    bk.register(id="defs/x", plot=LINE, transform=identity)
    bk.group("other")
    registry = assembled()
    (problem,) = registry.errors
    assert (problem.kind, list(registry.blicks)) == ("group", ["defs/x"])
    assert "bk.group() is called 2 times" in problem.message


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Rest of World", "rest-of-world"), ("  --A__b--  ", "a-b"), ("Übermaß", "ubermass")],
)
def test_slug(text: str, expected: str) -> None:
    assert bk.slug(text) == expected
