"""The evaluation of an expectation on a table: its offending rows, worst first, and its outcome.

The rows are ranked by distance, the largest first, then in the order of the dimensions, nulls last
in both, so a rerun gives the same rows in the same order. A table without rows meets every
expectation; it is checked only for the column the expectation names, whatever that column's
role, since the roles of columns without values say little. An expectation that cannot be
evaluated raises ``Unevaluable``, which a build records as the outcome ``error``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from blicket.expect._levels import Level
from blicket.expect._outcome import Outcome, Result
from blicket.expect._vocabulary import Expectation, NoRows, Unevaluable

_DISTANCE = "__blicket_distance__"


@dataclass(frozen=True)
class Evaluation:
    """An outcome and the offending rows it counts, worst first, without the distance."""

    outcome: Outcome
    offending: pl.DataFrame


def ranked(frame: pl.DataFrame, dims: Sequence[str], distance: pl.Expr | None) -> pl.DataFrame:
    """``frame`` in a total order: by ``distance``, the largest first, then by the dimensions,
    nulls last in both, since no two rows share their dimension values."""
    if distance is None:
        return frame.sort(list(dims), nulls_last=True) if dims else frame
    keyed = frame.with_columns(distance.alias(_DISTANCE))
    order = [_DISTANCE, *dims]
    descending = [True, *(False for _ in dims)]
    return keyed.sort(order, descending=descending, nulls_last=True)


def _named_column(
    expectation: Expectation, columns: Sequence[str], measures: Sequence[str]
) -> str | None:
    """The measure of ``expectation`` on a table without rows, with ``columns`` and ``measures``:
    the one it names, which must be one of the columns when there are any, else the only measure,
    else none."""
    named = expectation.measure
    if named is None:
        return measures[0] if len(measures) == 1 else None
    if columns and named not in columns:
        raise Unevaluable(
            f"{expectation.option}= names {named!r}, which is no column of the table; its columns "
            f"are {', '.join(columns)}"
        )
    return named


def _place(row: dict[str, Any], dims: Sequence[str]) -> dict[str, Any]:
    """The dimension values of ``row`` among ``dims``, without the null ones."""
    return {dim: row[dim] for dim in dims if row.get(dim) is not None}


def evaluate(
    expectation: Expectation,
    frame: pl.DataFrame,
    dims: Sequence[str],
    measures: Sequence[str],
    level: Level,
    *,
    where: Sequence[str] | None = None,
) -> Evaluation:
    """Evaluate ``expectation`` on ``frame``, whose dimension and measure columns are ``dims`` and
    ``measures``, at ``level``, which is not ``off``.

    For ``no_rows`` with a function, ``frame`` is what the function returned. ``where`` limits the
    dimensions an outcome names, as the unit's own when that differs from ``dims``. Raises
    ``Unevaluable`` when ``on=`` or ``by=`` names no measure of the table, or a bound has no
    measure to default to; on a table without rows only when the column named is missing.
    """
    places = [dim for dim in dims if where is None or dim in where]
    if frame.height:
        measure = expectation.resolve(measures, dims)
    else:
        measure = _named_column(expectation, frame.columns, measures)
    words = expectation.words(measure)
    bound = not isinstance(expectation, NoRows)
    if not frame.height:
        outcome = Outcome(result="met", expectation=words, evaluated=0 if bound else None)
        return Evaluation(outcome, frame)
    distance = None if measure is None else expectation.distance(measure)
    evaluated = None
    if bound and measure is not None and distance is not None:  # a bound always has its measure
        evaluated = frame.height - frame[measure].null_count()
        frame = frame.filter(distance > 0)
    rows = ranked(frame, dims, distance)
    within = 0
    if expectation.warn_within is not None and distance is not None:
        within = int((rows[_DISTANCE] <= expectation.warn_within).sum())
    offending = rows.height
    worst = farthest = place = None
    if offending:
        first = rows.row(0, named=True)
        if measure is not None and (farthest := first.get(_DISTANCE)) is not None:
            worst = first[measure]
        place = _place(first, places)
    if not offending:
        result: Result = "met"
    elif level == "warn" or within == offending:
        result = "warning"
    else:
        result = "failed"
    outcome = Outcome(
        result=result,
        expectation=words,
        evaluated=evaluated,
        offending=offending,
        within=within,
        worst=worst,
        distance=farthest,
        where=place,
    )
    return Evaluation(outcome, rows.drop(_DISTANCE, strict=False))


def evaluation_error(expectation: Expectation, message: str) -> Outcome:
    """The outcome of an expectation that cannot be evaluated, and why."""
    return Outcome(
        result="error", expectation=expectation.words(expectation.measure), message=message
    )
