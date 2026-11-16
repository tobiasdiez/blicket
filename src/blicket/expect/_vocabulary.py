"""The expectations of ``bk.expect``: their classes, the records a manifest holds of them, their
words, and the functions that make them."""

import decimal
import functools
import math
import numbers
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, SupportsFloat

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from blicket._callables import one_argument_problem
from blicket.errors import DefinitionError

type RowsFunction = Callable[[pl.DataFrame], Any]


# ---------------------------------------------------------------------------------------------
# The records of the expectations in a manifest: the expectation as declared


class NoRowsRecord(BaseModel):
    """``no_rows`` as declared; ``rows`` is the function's name."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["no_rows"] = "no_rows"
    rows: str | None = None
    by: str | None = None
    warn_within: float | None = None


class AtMostRecord(BaseModel):
    """``at_most`` as declared."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["at_most"] = "at_most"
    on: str | None = None
    bound: float
    warn_within: float | None = None


class AtLeastRecord(BaseModel):
    """``at_least`` as declared."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["at_least"] = "at_least"
    on: str | None = None
    bound: float
    warn_within: float | None = None


class BetweenRecord(BaseModel):
    """``between`` as declared."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["between"] = "between"
    on: str | None = None
    low: float
    high: float
    warn_within: float | None = None


type ExpectationRecord = Annotated[
    NoRowsRecord | AtMostRecord | AtLeastRecord | BetweenRecord, Field(discriminator="kind")
]


# ---------------------------------------------------------------------------------------------
# The expectations


class Unevaluable(Exception):
    """An expectation that cannot be evaluated on a table; the message says why and what to do."""


def number(value: float) -> str:
    """A bound or ``warn_within`` in words: ``0``, ``1e-09``, ``0.123456789``."""
    short = f"{value:g}"
    return short if float(short) == value else repr(value)


def function_name(function: object) -> str:
    """The name a ``rows`` function is recorded and named by, through ``functools.partial``."""
    while isinstance(function, functools.partial):
        function = function.func
    return getattr(function, "__name__", None) or type(function).__name__


# What a named column is when it is no measure: a dimension, as integer and string columns are.
_DIMENSION_HINT = (
    "integer and string columns are dimensions; cast it to float, or name it in measures="
)
# The same for a column of what a rows function returns, whose roles measures= does not set.
_ROWS_DIMENSION_HINT = (
    "integer and string columns are dimensions; cast it to float in the rows function"
)


@dataclass(frozen=True, kw_only=True, repr=False)
class Expectation:
    """A property of a unit's table, made by ``bk.expect.no_rows``, ``at_most``, ``at_least`` or
    ``between``; this base class is not one to use itself.

    ``warn_within`` makes the rows whose distance is at most that a warning rather than a failure.
    """

    # The function of bk.expect that makes the expectation, as its repr names it, and the option
    # that names its measure.
    call: ClassVar[str]
    option: ClassVar[str]

    warn_within: float | None = None

    @property
    def measure(self) -> str | None:
        """The measure named by ``on=`` or ``by=``, ``None`` when left to the default."""
        raise NotImplementedError

    def record(self) -> NoRowsRecord | AtMostRecord | AtLeastRecord | BetweenRecord:
        """The expectation as the manifest records it."""
        raise NotImplementedError

    def words(self, measure: str | None) -> str:
        """The expectation in words with ``measure`` as the measure: ``value between 0 and 1``,
        ``no rows, by relative, a warning within 1e-09``."""
        raise NotImplementedError

    def resolve(self, measures: Sequence[str], dims: Sequence[str] = ()) -> str | None:
        """The measure of a table with ``measures`` and ``dims`` this expectation applies to;
        raises ``Unevaluable`` when it names none of them, or when it needs one and there is none
        to default to."""
        raise NotImplementedError

    def distance(self, measure: str) -> pl.Expr:
        """How far a row offends, in the units of ``measure``."""
        raise NotImplementedError

    def _arguments(self) -> list[str]:
        """The arguments of the call that makes this expectation, as its ``repr`` gives them."""
        return []

    def __repr__(self) -> str:
        """The call that makes the expectation, ``bk.expect.no_rows(by='relative')``; for a class
        that ``bk.expect`` does not make, the class's name, ``Mine()``."""
        warn = [] if self.warn_within is None else [f"warn_within={number(self.warn_within)}"]
        arguments = ", ".join([*self._arguments(), *warn])
        if type(self) not in CONCRETE:
            return f"{type(self).__name__}({arguments})"
        return f"bk.expect.{self.call}({arguments})"

    def _dimension_hint(self) -> str:
        """What to do about a column named as the measure that is a dimension."""
        return _DIMENSION_HINT

    def _warning(self) -> list[str]:
        return [] if self.warn_within is None else [f"a warning within {number(self.warn_within)}"]

    def _named(self, measures: Sequence[str], dims: Sequence[str]) -> str | None:
        """The measure named by ``on=`` or ``by=``, which must be one of ``measures``."""
        named = self.measure
        if named is None or named in measures:
            return named
        if named in dims:
            raise Unevaluable(
                f"{self.option}= names {named!r}, a dimension of the table, not a measure; "
                f"{self._dimension_hint()}"
            )
        have = f"its measures are {', '.join(measures)}" if measures else "it has no measure"
        raise Unevaluable(
            f"{self.option}= names {named!r}, which is no column of the table; {have}"
        )


@dataclass(frozen=True, kw_only=True, repr=False)
class NoRows(Expectation):
    """No row offends: every row of the table, or every row ``rows`` returns, offends; ``by``
    names the measure whose absolute value is the distance."""

    call: ClassVar[str] = "no_rows"
    option: ClassVar[str] = "by"

    rows: RowsFunction | None = None
    by: str | None = None

    @property
    def measure(self) -> str | None:
        return self.by

    def record(self) -> NoRowsRecord:
        rows = None if self.rows is None else function_name(self.rows)
        return NoRowsRecord(rows=rows, by=self.by, warn_within=self.warn_within)

    def words(self, measure: str | None) -> str:
        head = "no rows" if self.rows is None else f"no rows of {function_name(self.rows)}"
        return ", ".join([head, *([f"by {measure}"] if measure else []), *self._warning()])

    def resolve(self, measures: Sequence[str], dims: Sequence[str] = ()) -> str | None:
        named = self._named(measures, dims)
        if named is not None:
            return named
        return measures[0] if len(measures) == 1 else None

    def distance(self, measure: str) -> pl.Expr:
        return pl.col(measure).abs()

    def _dimension_hint(self) -> str:
        # With a function, the measure is a column of what it returns.
        return _DIMENSION_HINT if self.rows is None else _ROWS_DIMENSION_HINT

    def _arguments(self) -> list[str]:
        rows = [] if self.rows is None else [function_name(self.rows)]
        return [*rows, *([] if self.by is None else [f"by={self.by!r}"])]


@dataclass(frozen=True, kw_only=True, repr=False)
class _Bound(Expectation):
    """A bound on a measure, ``on``; the distance is how far a value lies outside."""

    option: ClassVar[str] = "on"

    on: str | None = None

    @property
    def measure(self) -> str | None:
        return self.on

    def resolve(self, measures: Sequence[str], dims: Sequence[str] = ()) -> str:
        named = self._named(measures, dims)
        if named is not None:
            return named
        if len(measures) == 1:
            return measures[0]
        if not measures:
            raise Unevaluable(f"the table has no measure to bound; {_DIMENSION_HINT}")
        raise Unevaluable(
            f"the table has the measures {', '.join(measures)}; name the one to bound with on="
        )

    def words(self, measure: str | None) -> str:
        subject = f"{measure} {self._phrase()}" if measure else self._phrase()
        return ", ".join([subject, *self._warning()])

    def _phrase(self) -> str:
        raise NotImplementedError

    def _bounds(self) -> list[str]:
        raise NotImplementedError

    def _arguments(self) -> list[str]:
        return [*self._bounds(), *([] if self.on is None else [f"on={self.on!r}"])]


@dataclass(frozen=True, kw_only=True, repr=False)
class AtMost(_Bound):
    call: ClassVar[str] = "at_most"

    bound: float

    def record(self) -> AtMostRecord:
        return AtMostRecord(on=self.on, bound=self.bound, warn_within=self.warn_within)

    def _phrase(self) -> str:
        return f"at most {number(self.bound)}"

    def _bounds(self) -> list[str]:
        return [number(self.bound)]

    def distance(self, measure: str) -> pl.Expr:
        return pl.col(measure) - self.bound


@dataclass(frozen=True, kw_only=True, repr=False)
class AtLeast(_Bound):
    call: ClassVar[str] = "at_least"

    bound: float

    def record(self) -> AtLeastRecord:
        return AtLeastRecord(on=self.on, bound=self.bound, warn_within=self.warn_within)

    def _phrase(self) -> str:
        return f"at least {number(self.bound)}"

    def _bounds(self) -> list[str]:
        return [number(self.bound)]

    def distance(self, measure: str) -> pl.Expr:
        return self.bound - pl.col(measure)


@dataclass(frozen=True, kw_only=True, repr=False)
class Between(_Bound):
    call: ClassVar[str] = "between"

    low: float
    high: float

    def record(self) -> BetweenRecord:
        return BetweenRecord(on=self.on, low=self.low, high=self.high, warn_within=self.warn_within)

    def _phrase(self) -> str:
        return f"between {number(self.low)} and {number(self.high)}"

    def _bounds(self) -> list[str]:
        return [number(self.low), number(self.high)]

    def distance(self, measure: str) -> pl.Expr:
        return pl.max_horizontal(self.low - pl.col(measure), pl.col(measure) - self.high)


# The expectations a unit takes: what the functions below make.
CONCRETE: tuple[type[Expectation], ...] = (NoRows, AtMost, AtLeast, Between)


# ---------------------------------------------------------------------------------------------
# The vocabulary, bk.expect.*; each checks its arguments as the plot factories do


def _finite(value: object, call: str, what: str) -> float:
    """``value`` as a float: a real number, numpy's and ``Decimal`` included, but not a bool, that
    is finite as a float; a signaling NaN, which no float holds, is none."""
    if isinstance(value, numbers.Real | decimal.Decimal) and not isinstance(value, bool):
        try:
            number = float(value)
        except OverflowError:
            raise DefinitionError(
                f"{call}: {what} must be a finite number, got one beyond the range of a float",
                checks=True,
            ) from None
        except ValueError:
            number = math.nan
        if math.isfinite(number):
            return number
    raise DefinitionError(f"{call}: {what} must be a finite number, got {value!r}", checks=True)


def _warn_within(value: object, call: str) -> float | None:
    if value is None:
        return None
    within = _finite(value, call, "warn_within")
    if within < 0:
        raise DefinitionError(
            f"{call}: warn_within must be 0 or more, an absolute distance in the units of the "
            f"measure, got {value!r}",
            checks=True,
        )
    return within


def _measure_name(value: object, call: str, option: str) -> str | None:
    if value is None or (isinstance(value, str) and value):
        return value
    raise DefinitionError(
        f"{call}: {option}= must name a measure column, got {value!r}", checks=True
    )


def _rows_function(value: object, call: str) -> RowsFunction | None:
    if value is None:
        return None
    hint = "a function of the table that returns its offending rows"
    if not callable(value):
        raise DefinitionError(f"{call}: rows must be {hint}, got {value!r}", checks=True)
    if (signature := one_argument_problem(value)) is not None:
        raise DefinitionError(
            f"{call}: rows must be {hint}, taking exactly one positional parameter, the table; "
            f"its signature is {signature}",
            checks=True,
        )
    return value


def no_rows(
    rows: RowsFunction | None = None,
    *,
    by: str | None = None,
    warn_within: SupportsFloat | None = None,
) -> NoRows:
    """No row offends. Without ``rows``, every row of the table offends, which suits a check,
    whose table is what offends, and is a check's expectation unless it names another.

    ``rows`` is a function of the table that returns the offending rows, as a transformation
    returns a table, for a property that relates rows to each other:
    ``bk.expect.no_rows(above_maximum, by="excess")``. It receives the table with the dimensions
    first, sorted; it is recorded by its name. When it raises, ``bk.Skip`` included, or returns
    what a check could not return, the expectation cannot be evaluated: the outcome is ``error``,
    an error of the build. On a table without rows it is not called, and ``by`` is not looked
    up; without a function, a table without rows meets the expectation as long as ``by`` names
    one of its columns, if it has any.

    ``by`` names the measure whose absolute value is a row's distance, by default the table's only
    measure; with several and no ``by``, nothing ranks the rows. ``warn_within`` makes the rows
    whose distance is at most that a warning rather than a failure; it is absolute, in the units of
    the measure, and needs ``by``.
    """
    call = "bk.expect.no_rows()"
    function = _rows_function(rows, call)
    measure = _measure_name(by, call, "by")
    within = _warn_within(warn_within, call)
    if within is not None and measure is None:
        raise DefinitionError(
            f"{call}: warn_within= needs by=, the measure whose distance it bounds: "
            f'bk.expect.no_rows(by="relative", warn_within={number(within)})',
            checks=True,
        )
    return NoRows(rows=function, by=measure, warn_within=within)


def at_most(
    bound: SupportsFloat, *, on: str | None = None, warn_within: SupportsFloat | None = None
) -> AtMost:
    """The measure ``on``, by default the table's only one, is at most ``bound``, which is
    included: ``bk.expect.at_most(1)`` for a share. A null value never offends, and a table
    without rows meets it as long as ``on`` names one of its columns, if it has any.

    A row above the bound offends by as much as it lies above. ``warn_within`` makes the rows at
    most that far above a warning rather than a failure; it is absolute, in the units of the
    measure.
    """
    call = f"bk.expect.at_most({bound!r})"
    return AtMost(
        bound=_finite(bound, call, "the bound"),
        on=_measure_name(on, call, "on"),
        warn_within=_warn_within(warn_within, call),
    )


def at_least(
    bound: SupportsFloat, *, on: str | None = None, warn_within: SupportsFloat | None = None
) -> AtLeast:
    """The measure ``on``, by default the table's only one, is at least ``bound``, which is
    included: ``bk.expect.at_least(0, warn_within=1e-9)`` for a quantity that is never negative
    but for round-off. A null value never offends, and a table without rows meets it as long as
    ``on`` names one of its columns, if it has any.

    A row below the bound offends by as much as it lies below. ``warn_within`` makes the rows at
    most that far below a warning rather than a failure; it is absolute, in the units of the
    measure.
    """
    call = f"bk.expect.at_least({bound!r})"
    return AtLeast(
        bound=_finite(bound, call, "the bound"),
        on=_measure_name(on, call, "on"),
        warn_within=_warn_within(warn_within, call),
    )


def between(
    low: SupportsFloat,
    high: SupportsFloat,
    *,
    on: str | None = None,
    warn_within: SupportsFloat | None = None,
) -> Between:
    """The measure ``on``, by default the table's only one, lies between ``low`` and ``high``, both
    included: ``bk.expect.between(0, 1)`` for a share. A null value never offends, and a table
    without rows meets it as long as ``on`` names one of its columns, if it has any.

    A row outside offends by as much as it lies outside. ``warn_within`` makes the rows at most
    that far outside a warning rather than a failure; it is absolute, in the units of the measure.
    """
    call = f"bk.expect.between({low!r}, {high!r})"
    lower = _finite(low, call, "low")
    upper = _finite(high, call, "high")
    if lower > upper:
        raise DefinitionError(
            f"{call}: low is above high; pass bk.expect.between({high!r}, {low!r})", checks=True
        )
    return Between(
        low=lower,
        high=upper,
        on=_measure_name(on, call, "on"),
        warn_within=_warn_within(warn_within, call),
    )


# The functions above, which a definition may pass uncalled.
FACTORIES: tuple[Callable[..., Expectation], ...] = (no_rows, at_most, at_least, between)
