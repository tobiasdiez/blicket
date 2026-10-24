import pytest
from pydantic import ValidationError

from blicket.schema import Change


def test_flags_are_written_in_a_fixed_order() -> None:
    change = Change(flags=frozenset({"value", "schema", "new"}))
    assert change.model_dump(mode="json")["flags"] == ["new", "schema", "value"]


def test_the_magnitude_lies_between_0_and_1() -> None:
    with pytest.raises(ValidationError):
        Change(magnitude=1.5)
