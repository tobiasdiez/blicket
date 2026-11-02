from typing import Any

import pytest
from pydantic import ValidationError

from blicket.schema import Change, dimension_type, polars_type


def test_flags_are_written_in_a_fixed_order() -> None:
    change = Change(flags=frozenset({"value", "schema", "new"}))
    assert change.model_dump(mode="json")["flags"] == ["new", "schema", "value"]


def test_the_magnitude_lies_between_0_and_1() -> None:
    with pytest.raises(ValidationError):
        Change(magnitude=1.5)


@pytest.mark.parametrize("dtype", ["string", "integer", "boolean", "date", "datetime"])
def test_polars_type_is_the_inverse_of_dimension_type(dtype: Any) -> None:
    assert dimension_type(polars_type(dtype)) == dtype
