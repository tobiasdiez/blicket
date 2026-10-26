"""The shapes the data model and the plot types share: a table's schema, the controls the viewer
offers for it, and the change between two tables of a Blick.

This module imports nothing from blicket, so that ``blicket.model`` and ``blicket.plots`` both
can import it.
"""

from decimal import Decimal
from typing import Any, Literal, get_args

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_serializer

type DimensionType = Literal["string", "integer", "boolean", "date", "datetime"]
ControlKind = Literal["filter", "split"]
Flag = Literal["new", "removed", "schema", "value", "error"]

_DIMENSION_TYPES: dict[Any, DimensionType] = {
    pl.String: "string",
    pl.Boolean: "boolean",
    pl.Date: "date",
    pl.Datetime: "datetime",
}


def dimension_type(dtype: pl.DataType) -> DimensionType | None:
    """The type of a dimension column of ``dtype``, ``None`` for a dtype no dimension can have."""
    return "integer" if dtype.is_integer() else _DIMENSION_TYPES.get(dtype.base_type())


class Dimension(BaseModel):
    """A dimension column of a Blick's table: its name, type and values in display order."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: DimensionType
    values: list[Any]


class Measure(BaseModel):
    """A measure column of a Blick's table: its name and type."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: Literal["float"]


class TableSchema(BaseModel):
    """The columns of a Blick's table, dimensions first."""

    model_config = ConfigDict(frozen=True)

    dimensions: list[Dimension]
    measures: list[Measure]


class Control(BaseModel):
    """What the viewer offers for a dimension that the plot leaves unbound.

    A ``filter`` shows the rows of one value at a time, ``default`` first. A ``split`` draws a
    panel per value; its ``default`` is the value it filters on when the viewer turns it into a
    filter. ``default`` is ``None`` only for a dimension without values.
    """

    model_config = ConfigDict(frozen=True)

    dimension: str
    kind: ControlKind
    default: Any = None


class Change(BaseModel):
    """How the current table of a Blick differs from its baseline.

    No flags and magnitude 0 means unchanged. A plot type's ``diff`` sets ``schema`` when columns,
    or values of a dimension, appeared or vanished, and names them: ``columns_added`` and
    ``columns_removed`` map a column to its type in the words of ``TableSchema`` (a column whose
    type changed appears in both), ``values_added`` and ``values_removed`` map a dimension to its
    values that only one table has. ``magnitude`` is the change of the rows both tables have,
    between 0 and 1, and ``None`` when no row was compared. ``where`` holds the dimension values
    of the row that changed most, without the stacked column when a whole stack changed more, and
    is ``None`` when nothing changed. ``value`` is set by the caller from the magnitude and the
    Blick's tolerance, as are ``new``, ``removed`` and ``error``, which need both builds. The flags
    are written to JSON in the order of ``Flag``.
    """

    model_config = ConfigDict(frozen=True)

    flags: frozenset[Flag] = frozenset()
    magnitude: float | None = Field(None, ge=0, le=1)
    columns_added: dict[str, str] = {}
    columns_removed: dict[str, str] = {}
    values_added: dict[str, list[Any]] = {}
    values_removed: dict[str, list[Any]] = {}
    where: dict[str, Any] | None = None

    @property
    def percent(self) -> str | None:
        """The magnitude as the percent of the chart's scale it is, to two significant digits
        and without an exponent: ``2.1%``, ``100%``, ``0.012%``; ``None`` when no row was
        compared. The viewer's ``percent`` in viewer/app/lib/comparison.ts writes the same, but
        the two differ on exact ties, which Python rounds half to even."""
        if self.magnitude is None:
            return None
        return f"{Decimal(f'{self.magnitude * 100:.2g}'):f}%"

    @field_serializer("flags", when_used="json")
    def _flags_in_order(self, flags: frozenset[Flag]) -> list[Flag]:
        return [flag for flag in get_args(Flag) if flag in flags]
