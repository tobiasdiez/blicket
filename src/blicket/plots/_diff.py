"""The diff routine the built-in plot types share.

It imports polars, ``blicket.errors`` and ``blicket.schema`` only: ``blicket.model`` imports the
plot types, so a routine that reached ``model`` or ``manifest`` would import itself in a cycle.
"""

import math
from collections.abc import Iterable, Sequence
from typing import Any

import polars as pl

from blicket.errors import did_you_mean
from blicket.schema import Change, Flag, dimension_type

_EPSILON = 1e-6  # the least scale of a panel, relative to the largest absolute value compared
# A stack is named only when it moved more than the largest row by this fraction; sums carry
# rounding the rows do not.
_STACK_MARGIN = 1e-9
_CURRENT = "\0current"  # suffix of the current table's measure; no table column has a NUL


def compare(
    baseline: pl.DataFrame,
    current: pl.DataFrame,
    y: str,
    panels: Sequence[str],
    stacked_by: str | None = None,
) -> Change:
    """Compare two tables of a chart of the measure ``y`` over the other columns, the dimensions.

    The tables are as ``tables.check`` leaves them: ``y`` the one float column, no null dimension
    value, every combination of dimension values once. A column that appeared, vanished or
    changed its dtype sets ``schema``, and nothing is compared. Otherwise the rows are matched by
    their dimension values. A value of a dimension that only one table has sets ``schema``, and
    the rows that carry it are left out. A row of one table only is compared with null, and null,
    or NaN, counts as 0 against a value.

    A row's change is measured against the scale of its panel, the compared rows with the same
    values in the ``panels`` columns (all compared rows without them): the largest absolute value
    of ``y`` in the panel in either table, at least ``_EPSILON`` times the largest of all compared
    rows. ``stacked_by`` is the column on the ``color`` channel of a stacked chart: the scale is
    then the highest stack, positive and negative values stacked apart, and the stacks are
    compared as well. The magnitude is the largest change, at most 1. ``where`` holds the
    dimension values of the first row in sort order that reached it, or of the first stack when a
    stack changed more than every row by ``_STACK_MARGIN``, and is ``None`` when nothing changed.

    Raises ``TypeError`` for a table that is not a polars frame or ``panels`` given as a string,
    and ``ValueError`` when ``y``, ``panels`` or ``stacked_by`` do not fit the current table or a
    table repeats a combination of dimension values.
    """
    dims = _check_arguments(baseline, current, y, panels, stacked_by)
    after, before = dict(current.schema), dict(baseline.schema)
    if after != before:  # by name, in any order, since the tables are joined by name
        return Change(
            flags=frozenset({"schema"}),
            columns_added={c: _type(t) for c, t in after.items() if before.get(c) != t},
            columns_removed={c: _type(t) for c, t in before.items() if after.get(c) != t},
        )
    added, removed = _only_in(current, baseline, dims), _only_in(baseline, current, dims)
    flags: frozenset[Flag] = frozenset({"schema"}) if added or removed else frozenset()

    try:
        compared = baseline.join(
            current, on=dims, how="full", coalesce=True, validate="1:1", suffix=_CURRENT
        )
    except pl.exceptions.ComputeError:
        raise ValueError("dimension values must be unique in each table") from None
    for dim in added.keys() | removed.keys():
        compared = compared.filter(~pl.col(dim).is_in(added.get(dim, []) + removed.get(dim, [])))
    # Sorted before the sums, so that they add up in the same order every time.
    compared = compared.sort(dims).fill_nan(None)
    old, new = pl.col(y), pl.col(y + _CURRENT)
    peak = pl.max_horizontal(old.abs(), new.abs())
    # Multiplied by a power of two near the largest value, which is exact, the values lie within
    # (-1, 1), so no sum overflows; not divided by it, since polars divides through the
    # reciprocal, which overflows for a subnormal divisor. The power is applied in two halves,
    # each finite.
    largest, exponent = math.frexp(compared.select(peak.max()).item() or 1.0)
    half = exponent // 2
    compared = compared.with_columns(
        [column * 2.0**-half * 2.0 ** (half - exponent) for column in (old, new)]
    )

    groups = [d for d in dims if d != stacked_by]
    if stacked_by is None:
        height, stack = peak, pl.lit(0.0)
    else:
        (old_up, old_down), (new_up, new_down) = _stacks(old, groups), _stacks(new, groups)
        height = pl.max_horizontal(old_up, old_down, new_up, new_down)
        stack = pl.max_horizontal(_difference(old_up, new_up), _difference(old_down, new_down))
    scale = pl.max_horizontal(_over(height.max(), panels), _EPSILON * largest)
    deviations = compared.select(row=_difference(old, new) / scale, stack=stack / scale)

    magnitude = where = None
    if not compared.is_empty():
        row_max, stack_max = deviations.max().row(0)
        magnitude = min(1.0, max(row_max, stack_max))
        if magnitude:
            column, deviation, names = "row", row_max, dims
            if stack_max > row_max * (1 + _STACK_MARGIN):
                column, deviation, names = "stack", stack_max, groups
            first = compared.filter(deviations[column] == deviation).row(0, named=True)
            where = {name: first[name] for name in names}
    return Change(
        flags=flags,
        magnitude=magnitude,
        values_added=added,
        values_removed=removed,
        where=where,
    )


def _check_arguments(
    baseline: pl.DataFrame,
    current: pl.DataFrame,
    y: str,
    panels: Sequence[str],
    stacked_by: str | None,
) -> list[str]:
    """The dimensions of the current table, after checking that both tables are polars frames,
    ``y`` is a float column of the current table beside at least one dimension, and ``panels``
    and ``stacked_by`` are dimensions, and different ones."""
    for name, table in (("baseline", baseline), ("current", current)):
        if not isinstance(table, pl.DataFrame):
            raise TypeError(
                f"the {name} table must be a polars DataFrame, got {type(table).__name__}"
            )
    if isinstance(panels, str):
        raise TypeError(f"panels is a list of column names, got the string {panels!r}")
    columns = current.schema
    if y not in columns:
        raise ValueError(f"y={y!r} is not a column of the current table{_hint(y, columns)}")
    if not (dtype := columns[y]).is_float():
        raise ValueError(f"y={y!r} holds {dtype} values, not floats")
    dims = [column for column in columns if column != y]
    if not dims:
        raise ValueError(f"the current table has no dimension column beside y={y!r}")
    if missing := [column for column in panels if column not in dims]:
        names = ", ".join(map(repr, missing))
        what = "is not a dimension" if len(missing) == 1 else "are not dimensions"
        raise ValueError(
            f"panels name {names}, which {what} of the current table (dimensions: "
            f"{', '.join(dims)})"
        )
    if stacked_by is not None and stacked_by not in dims:
        raise ValueError(
            f"color={stacked_by!r} is not a dimension of the current table{_hint(stacked_by, dims)}"
        )
    if stacked_by in panels:
        raise ValueError(
            f"color={stacked_by!r} is also in panels; the layers of a stack share its panel"
        )
    return dims


def _hint(word: str, options: Iterable[str]) -> str:
    close = did_you_mean(word, options)
    return f"; did you mean {close!r}?" if close else ""


def _type(dtype: pl.DataType) -> str:
    """A dtype in the words of ``TableSchema``."""
    return "float" if dtype.is_float() else dimension_type(dtype) or str(dtype)


def _only_in(frame: pl.DataFrame, other: pl.DataFrame, dims: Sequence[str]) -> dict[str, list[Any]]:
    """Per dimension, the values of ``frame`` that ``other`` lacks, sorted; dimensions without
    such values are left out."""
    found: dict[str, list[Any]] = {}
    for dim in dims:
        values = frame[dim].unique().sort()
        if missing := values.filter(~values.is_in(other[dim].unique().implode())).to_list():
            found[dim] = missing
    return found


def _over(expression: pl.Expr, columns: Sequence[str]) -> pl.Expr:
    """``expression`` per group of ``columns``, or over all rows without them."""
    return expression.over(columns) if columns else expression


def _stacks(column: pl.Expr, groups: Sequence[str]) -> tuple[pl.Expr, pl.Expr]:
    """The heights of the positive and of the negative stack of each group of ``groups``."""
    positive = column.clip(lower_bound=0).sum()
    negative = -column.clip(upper_bound=0).sum()
    return _over(positive, groups), _over(negative, groups)


def _difference(old: pl.Expr, new: pl.Expr) -> pl.Expr:
    return (new.fill_null(0.0) - old.fill_null(0.0)).abs()
