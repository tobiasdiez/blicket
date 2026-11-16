"""The tables of Blicks and checks: what a transformation returns, as a polars frame checked
against its unit, and the outcome of the unit's expectation on it.

blicket depends on polars only. A pandas frame is recognised by its type's module and converted
column by column through numpy, so neither pandas nor pyarrow is needed here. Dimension columns
are normalised (strings for categoricals, ``Int64``, naive UTC ``Datetime("us")``), so that equal
tables from different libraries are equal.

A Blick's table fits its plot: every measure on a channel, no null in a dimension. A check's table
is the rows that offend, so it has no plot: any number of measures, nulls in its dimensions (the
union of several arrays' dimensions, say, with no two rows alike, nulls counting as equal), and
no rows, with or without columns, which is the normal case. A check stores its offending rows
worst first, at most ``MAX_STORED`` of them.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from blicket.errors import Kind, Problem, Skip
from blicket.expect._evaluation import evaluate, evaluation_error
from blicket.expect._levels import DEFAULT_LEVEL, Level
from blicket.expect._outcome import Outcome
from blicket.expect._vocabulary import NoRows, Unevaluable, function_name
from blicket.model import LEVEL_OFF, Blick, Check, Unit
from blicket.schema import Dimension, Measure, TableSchema, dimension_type
from blicket.tracebacks import locate, project_traceback, raised_at

# The most offending rows a check stores, as many as the Blick builder draws.
MAX_STORED = 100_000
# What a check's transformation returns, added to what is wrong with what it returned.
_CHECK_HINT = (
    "a check returns the rows that offend as a table, an empty one when the property holds"
)


def _with_check_hint(message: str) -> str:
    """``message`` and what a check returns, as a sentence of its own after a question."""
    if message.endswith("?"):
        return f"{message} {_CHECK_HINT[0].upper()}{_CHECK_HINT[1:]}"
    return f"{message}; {_CHECK_HINT}"


_INDEX_HINT = (
    "an unnamed pandas index level was dropped; if it holds data, name it, "
    'df.index.name = "year" or df.index.names = [...]; if it is only row numbers, call '
    "reset_index(drop=True)"
)
_UNPIVOT_HINT = (
    "bind each measure to a channel, drop it in the transformation, or unpivot a wide table into a "
    "long one with a column that names the measure"
)


class TableError(Exception):
    """A transformation returned something that is not a table."""


class Raised(Exception):
    """An exception ``error`` that project code raised while a transformation called it.

    ``action`` names the call, such as ``select('flows/steel') of the dataset``; the problem
    ``compute`` makes of it names that call instead of the transformation.
    """

    def __init__(self, action: str, error: BaseException) -> None:
        super().__init__(f"{action} raised {type(error).__name__}: {error}")
        self.action = action
        self.error = error


@dataclass(frozen=True)
class Checked:
    """A table checked against its unit, or why there is none, and the outcome of the unit's
    expectation on it.

    ``frame`` and ``schema`` are set exactly when no problem is an error and the transformation
    did not skip the run; ``frame`` then holds the dimensions first, then the measures. A Blick's
    rows are sorted by the dimensions; once its expectation is evaluated, a check's are the
    offending rows, worst first, at most ``MAX_STORED`` of them. ``skipped`` is the reason of the
    ``Skip`` the transformation raised, or that a check's level is off, which leaves no table and
    no problem. ``outcome`` is ``None`` before the evaluation, without an expectation, and at
    level ``off``.
    """

    frame: pl.DataFrame | None
    schema: TableSchema | None
    problems: tuple[Problem, ...]
    skipped: str | None = None
    outcome: Outcome | None = None

    @classmethod
    def failed(cls, *problems: Problem) -> Checked:
        return cls(None, None, problems)

    @classmethod
    def skip(cls, reason: str) -> Checked:
        return cls(None, None, (), reason)


def _type_name(value: object) -> str:
    module, name = type(value).__module__, type(value).__name__
    return name if module == "builtins" else f"{module}.{name}"


def _is_pandas(value: object, kind: str) -> bool:
    """Whether ``value`` is a pandas ``DataFrame`` or ``Series``, as ``kind`` says."""
    return any(
        cls.__name__ == kind and cls.__module__.partition(".")[0] == "pandas"
        for cls in type(value).__mro__
    )


def _from_pandas_column(name: str, series: Any) -> pl.Series:
    dtype = series.dtype
    if type(dtype).__module__.startswith("numpy") and dtype.kind in "biufmM":
        return pl.Series(name, series.to_numpy())
    # Strings, nullable and categorical columns; a list, since polars keeps an object array as
    # Object.
    values = series.to_numpy(dtype=object, na_value=None).tolist()
    if getattr(dtype, "ordered", False):
        values = [None if value is None else str(value) for value in values]
        return pl.Series(name, values, dtype=pl.Enum([str(c) for c in dtype.categories]))
    return pl.Series(name, values)


def _from_pandas(frame: Any) -> tuple[pl.DataFrame, bool]:
    """The frame with its named index levels as columns; unnamed levels are dropped.

    Also returns whether a dropped level was something else than a ``RangeIndex``.
    """
    index = frame.index
    names = [name for name in index.names if name is not None]
    if clash := [n for n in names if names.count(n) > 1 or n in frame.columns]:
        raise TableError(
            f"the pandas index level {clash[0]!r} is also a column (or appears twice); "
            "rename it before returning"
        )
    dropped = len(names) < index.nlevels and type(index).__name__ != "RangeIndex"
    if names:
        frame = frame.reset_index(level=names)
    columns = [
        _from_pandas_column(str(name), frame.iloc[:, i]) for i, name in enumerate(frame.columns)
    ]
    return pl.DataFrame(columns), dropped


def to_polars(value: Any, what: str = "the transformation") -> tuple[pl.DataFrame, bool]:
    """Convert what a transformation, or the function ``what`` names, returned to a polars frame.

    Also returns whether an unnamed pandas index was dropped, which a later check may mention.

    Accepted are polars frames, lazy frames, pandas frames, objects with an Arrow stream (pyarrow
    tables, duckdb relations), and objects whose ``to_df()`` or ``to_dataframe()`` returns a
    pandas frame (flodym arrays, xarray). Raises ``TableError`` for anything else.
    """
    if isinstance(value, pl.DataFrame):
        return value, False
    if isinstance(value, pl.LazyFrame):
        return value.collect(), False
    if _is_pandas(value, "DataFrame"):
        return _from_pandas(value)
    if isinstance(value, pl.Series) or _is_pandas(value, "Series"):
        library = type(value).__module__.partition(".")[0]
        raise TableError(f'{what} returned a {library} Series; return series.to_frame("value")')
    if hasattr(value, "__arrow_c_stream__"):
        return pl.DataFrame(value), False
    for method in ("to_df", "to_dataframe"):
        convert = getattr(value, method, None)
        if callable(convert):
            frame = convert()
            if not _is_pandas(frame, "DataFrame"):
                raise TableError(
                    f"{what} returned {_type_name(value)}, whose {method}() gives "
                    f"{_type_name(frame)}, not a pandas frame"
                )
            return _from_pandas(frame)
    if value is None:
        raise TableError(f"{what} returned None; did it forget return?")
    if isinstance(value, dict | list):
        raise TableError(f"{what} returned a {type(value).__name__}; wrap it in pl.DataFrame(...)")
    raise TableError(
        f"{what} returned {_type_name(value)}; return a polars or pandas frame, an "
        "Arrow table, or an object with to_df() or to_dataframe()"
    )


@dataclass(frozen=True)
class _Rules:
    """What a table is checked against: the roles that ``dims=`` and ``measures=`` give its
    columns, and for a Blick its plot, controls, order and defaults; ``blick`` is ``None`` for the
    rules of a check's table."""

    dims: tuple[str, ...] | None
    measures: tuple[str, ...] | None
    blick: Blick | None = None

    @classmethod
    def of(cls, unit: Unit) -> _Rules:
        return cls(unit.dims, unit.measures, unit if isinstance(unit, Blick) else None)

    @property
    def bound(self) -> dict[str, str]:
        """The channel each column of the plot is bound to; none for a check."""
        if self.blick is None:
            return {}
        return {column: channel for channel, column in self.blick.plot.mapping.items()}


def _roles(
    frame: pl.DataFrame, rules: _Rules, kinds: Mapping[str, str], errors: list[str]
) -> tuple[list[str], list[str]]:
    """The dimension and measure columns, from ``dims=``, ``measures=`` and the plot."""
    columns = frame.columns
    for option, named in (("dims", rules.dims), ("measures", rules.measures)):
        for column in named or ():
            if column not in columns:
                errors.append(
                    f"{option}= names the column {column!r}, which the table lacks; its columns "
                    f"are {', '.join(columns)}"
                )
    if errors:
        return [], []
    for column in sorted(set(rules.dims or ()) & set(rules.measures or ())):
        errors.append(f"{column!r} is named in both dims= and measures=")

    if rules.dims is not None:
        dims = [c for c in rules.dims if c in columns]
    elif rules.measures is not None:
        dims = [c for c in columns if c not in rules.measures]
    else:
        dims = [c for c in columns if kinds.get(c) == "dimension" or not frame.schema[c].is_float()]
    if rules.measures is not None:
        measures = [c for c in rules.measures if c in columns and c not in dims]
    else:
        measures = [c for c in columns if c not in dims]
    if neither := [c for c in columns if c not in dims and c not in measures]:
        errors.append(
            f"the column(s) {', '.join(map(repr, neither))} are in neither dims= nor measures=; "
            "name them or drop them in the transformation"
        )
    return dims, measures


def _casts(
    frame: pl.DataFrame,
    rules: _Rules,
    dims: Sequence[str],
    measures: Sequence[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[list[pl.Expr], set[str]]:
    """The casts to the normalised type of every column's role, and the columns whose type
    their role does not allow, with a problem for each. In a check's table, a dimension of nulls
    only, which an empty table's columns may be, is a string column."""
    bound = rules.bound
    casts: list[pl.Expr] = []
    rejected: set[str] = set()
    for column in dims:
        dtype = frame.schema[column]
        if dtype.base_type() in (pl.Categorical, pl.Enum):
            casts.append(pl.col(column).cast(pl.String))
        elif dtype.is_integer():
            casts.append(pl.col(column).cast(pl.Int64))
        elif isinstance(dtype, pl.Datetime):
            expression = pl.col(column)
            if dtype.time_zone is not None:
                warnings.append(f"{column!r} in time zone {dtype.time_zone} was converted to UTC")
                expression = expression.dt.convert_time_zone("UTC").dt.replace_time_zone(None)
            casts.append(expression.cast(pl.Datetime("us")))
        elif dtype == pl.Null and rules.blick is None:
            casts.append(pl.col(column).cast(pl.String))
        elif dtype.is_float() and rules.dims is None and rules.measures is not None:
            rejected.add(column)
            on = f" on {bound[column]}=" if column in bound else ""
            errors.append(
                f"{column!r}{on} is a float column that measures= leaves out, so it counts as a "
                f"dimension; add {column!r} to measures="
            )
        elif dimension_type(dtype) is None:
            rejected.add(column)
            where = f" (bound to {bound[column]}=)" if column in bound else ""
            if column in (rules.dims or ()):
                where = " (in dims=)"
            fix = ""
            if dtype.is_float():
                fix = "; round and cast it, e.g. .astype(int) in pandas, .cast(pl.Int64) in polars"
            errors.append(
                f"column {column!r}{where} is {dtype}; dimensions are strings, integers, "
                f"booleans, dates or datetimes, because their values are keys{fix}"
            )
    for column in measures:
        dtype = frame.schema[column]
        if dtype.is_integer() or dtype == pl.Boolean:
            casts.append(pl.col(column).cast(pl.Float64))
        elif dtype.is_float():
            casts.append(pl.col(column).cast(pl.Float64).fill_nan(None))
        else:
            rejected.add(column)
            implied = rules.dims is not None and column not in (rules.measures or ())
            fix = "; with dims= given, every other column is a measure, so add it to dims="
            reason = fix if implied else " and cannot be a measure"
            errors.append(f"{column!r} is a {dimension_type(dtype) or dtype} column{reason}")
    return casts, rejected


def _check_plot(
    frame: pl.DataFrame,
    blick: Blick,
    roles: tuple[Sequence[str], set[str]],
    kinds: Mapping[str, str],
    index_dropped: bool,
    errors: list[str],
) -> None:
    """The plot's columns against the table; ``roles`` holds the dimensions and the columns
    whose type was rejected already. A channel with a scale needs numbers: a measure, or an
    integer dimension."""
    dims, rejected = roles
    for channel, column in blick.plot.mapping.items():
        dtype = frame.schema.get(column)
        scale = blick.plot.scales.get(channel)
        if dtype is None:
            hint = f" ({_INDEX_HINT})" if index_dropped else ""
            errors.append(
                f"the plot maps {channel}= to the column {column!r}, which the table lacks; "
                f"its columns are {', '.join(frame.columns)}{hint}"
            )
        elif column in rejected:
            continue
        elif kinds[column] == "dimension" and column not in dims:
            option = "dims= leaves out" if blick.dims is not None else "measures= names"
            errors.append(f"{channel}= needs a dimension, but {option} {column!r}")
        elif kinds[column] == "measure" and column in dims:
            if column in (blick.dims or ()):
                errors.append(f"{channel}= needs a measure, but dims= names {column!r}")
            elif dtype.is_integer() or dtype == pl.Boolean:
                fix = f'add measures=["{column}"]'
                if blick.measures is not None:
                    fix = f"add {column!r} to measures="
                errors.append(
                    f"{column!r} on {channel}= is an integer column and so counts as a "
                    f"dimension; {fix}"
                )
            else:
                errors.append(
                    f"{column!r} on {channel}= is a {dimension_type(dtype) or dtype} column and "
                    "cannot be a measure"
                )
        elif scale is not None and column in dims and dimension_type(dtype) != "integer":
            errors.append(
                f"{channel}_scale={scale!r} needs numbers on {channel}, but {column!r} is a "
                f"{dimension_type(dtype)} column; bind an integer dimension to {channel} or drop "
                f"{channel}_scale"
            )


def _check_rows(
    frame: pl.DataFrame, dims: Sequence[str], errors: list[str], *, nulls: bool = False
) -> None:
    """Dimension values are keys: no two rows alike and, unless ``nulls`` allows them, as in a
    check's table, no nulls; two nulls count as equal."""
    if not dims:
        if frame.height > 1:
            errors.append(
                f"the table has {frame.height} rows but no dimension column to tell them apart"
            )
        return
    checked = [] if nulls else dims
    for column in checked:
        if count := frame[column].null_count():
            errors.append(
                f"dimension column {column!r} has {count} null value(s); dimension values are "
                "keys, so fill or drop them"
            )
    duplicated = frame.select(dims).is_duplicated()
    if count := duplicated.sum():
        example = frame.filter(duplicated).select(dims).row(0, named=True)
        errors.append(
            f"{count} rows repeat the dimension values of another row, such as {example}; "
            "aggregate them or add the column that tells them apart"
        )


def _check_measures(
    frame: pl.DataFrame, measures: Sequence[str], errors: list[str], *, charted: bool = True
) -> None:
    """Measures are finite: a chart cannot show an infinite value, nor a comparison measure it,
    nor can it rank a check's rows, as ``charted`` says which."""
    why = (
        "which no chart can show and no comparison can measure" if charted else "which ranks no row"
    )
    for column in measures:
        if infinite := frame[column].is_infinite().sum():
            errors.append(
                f"measure column {column!r} has {infinite} infinite value(s), {why}; replace them "
                "with null or a number"
            )


def _check_options(
    frame: pl.DataFrame,
    blick: Blick,
    dims: Sequence[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """``controls``, ``order`` and ``defaults`` against the table's dimensions and values."""
    bound = {column: channel for channel, column in blick.plot.mapping.items()}
    for column in blick.controls:
        if column not in dims:
            errors.append(f"controls[{column!r}]: the table has no dimension {column!r}")
        elif column in bound:
            errors.append(
                f"controls[{column!r}]: the plot binds {column!r} to {bound[column]}=; controls "
                "are for the dimensions the plot leaves unbound"
            )
    for option, given in (("order", blick.order), ("defaults", blick.defaults)):
        for column, value in given.items():
            if column not in dims:
                errors.append(f"{option}[{column!r}]: the table has no dimension {column!r}")
                continue
            present = frame[column].unique().to_list()
            values = value if isinstance(value, list | tuple) else [value]
            if missing := [v for v in values if v not in present]:
                warnings.append(
                    f"{option}[{column!r}] names {', '.join(map(repr, missing))}, which this "
                    "run's table does not contain"
                )


def _values(column: pl.Series, order: Sequence[Any]) -> list[Any]:
    """The column's values but null: those in ``order`` first, the rest sorted."""
    values = column.drop_nulls().unique().sort().to_list()
    return [v for v in order if v in values] + [v for v in values if v not in order]


def _schema(
    frame: pl.DataFrame,
    dims: Sequence[str],
    measures: Sequence[str],
    order: Mapping[str, Sequence[Any]],
) -> TableSchema:
    """The schema of a checked table, each dimension's values in ``order`` first."""
    dimensions = []
    for column in dims:
        dtype = dimension_type(frame.schema[column])
        assert dtype is not None, "every dimension type was checked"
        values = _values(frame[column], order.get(column, ()))
        dimensions.append(Dimension(name=column, dtype=dtype, values=values))
    measured = [Measure(name=column, dtype="float") for column in measures]
    return TableSchema(dimensions=dimensions, measures=measured)


@dataclass(frozen=True)
class _Table:
    """A table checked against rules: the frame in output order and its roles, if no error."""

    frame: pl.DataFrame | None
    dims: list[str]
    measures: list[str]
    enum_order: dict[str, list[Any]]
    errors: list[str]
    notes: list[str]


def _checked_table(frame: pl.DataFrame, rules: _Rules, index_dropped: bool) -> _Table:
    """Find each column's role, check ``frame`` against ``rules``, and put it in output order:
    the dimensions first, the rows sorted by them, nulls last.

    Every problem is collected before giving up, except that ``dims=`` and ``measures=`` must fit
    the table before anything else is checked.
    """
    blick = rules.blick
    kinds: dict[str, str] = {}
    if blick is not None:
        channels = {channel.name: channel.kind for channel in blick.plot.plot_type.channels}
        kinds = {column: channels[channel] for channel, column in blick.plot.mapping.items()}
    errors: list[str] = []
    notes: list[str] = []
    dims, measures = _roles(frame, rules, kinds, errors)
    if errors:
        return _Table(None, [], [], {}, errors, notes)
    # An Enum's categories give the display order of its values, which become strings.
    enum_order = {
        column: dtype.categories.to_list()
        for column in dims
        if isinstance(dtype := frame.schema[column], pl.Enum)
    }
    casts, rejected = _casts(frame, rules, dims, measures, errors, notes)
    frame = frame.with_columns(casts)
    # Keys and values are only checked once every column has a usable type.
    sound = not errors
    if blick is not None:
        _check_plot(frame, blick, (dims, rejected), kinds, index_dropped, errors)
        if unbound := [m for m in measures if m not in kinds]:
            errors.append(
                f"the measure(s) {', '.join(map(repr, unbound))} are bound to no plot channel, so "
                f"no chart shows them; {_UNPIVOT_HINT}"
            )
        if frame.height == 0:
            notes.append("the table has no rows")
    if sound:
        _check_rows(frame, dims, errors, nulls=blick is None)
        _check_measures(frame, measures, errors, charted=blick is not None)
        if blick is not None:
            _check_options(frame, blick, dims, errors, notes)
    if errors:
        return _Table(None, dims, measures, enum_order, errors, notes)
    frame = frame.select([*dims, *measures])
    if dims:
        frame = frame.sort(dims, nulls_last=True)
    return _Table(frame, dims, measures, enum_order, errors, notes)


def check(frame: pl.DataFrame, unit: Unit, index_dropped: bool = False) -> Checked:
    """Find each column's role, check the table against the unit, a Blick or a check, and put it
    in output order.

    ``index_dropped`` says that the conversion dropped an unnamed pandas index, which a missing
    plot column may be. Every problem is collected before giving up, except that ``dims=`` and
    ``measures=`` must fit the table before anything else is checked.
    """
    if not frame.columns:
        if isinstance(unit, Check):
            return Checked(frame, TableSchema(dimensions=[], measures=[]), ())
        return Checked.failed(unit.problem(Kind.TABLE, "the table has no columns"))
    table = _checked_table(frame, _Rules.of(unit), index_dropped)
    problems = (
        *(unit.problem(Kind.TABLE, message) for message in table.errors),
        *(unit.problem(Kind.TABLE, message, severity="warning") for message in table.notes),
    )
    if table.frame is None:
        return Checked.failed(*problems)
    order: Mapping[str, Sequence[Any]] = table.enum_order
    if isinstance(unit, Blick):
        enums = table.enum_order
        order = {column: unit.order.get(column) or enums.get(column, ()) for column in table.dims}
    schema = _schema(table.frame, table.dims, table.measures, order)
    return Checked(table.frame, schema, problems)


def ordered(schema: TableSchema, order: Mapping[str, Sequence[Any]]) -> TableSchema:
    """``schema`` with the values of each dimension named in ``order`` in that order, and the
    values ``order`` lacks after them; values ``order`` names that the table lacks play no part."""
    dimensions = []
    for dimension in schema.dimensions:
        if (wanted := order.get(dimension.name)) is not None:
            present = set(dimension.values)
            first = [value for value in wanted if value in present]
            chosen = set(first)
            values = first + [value for value in dimension.values if value not in chosen]
            dimension = dimension.model_copy(update={"values": values})
        dimensions.append(dimension)
    return schema.model_copy(update={"dimensions": dimensions})


def compute(unit: Unit, run: object, root: Path, level: Level = DEFAULT_LEVEL) -> Checked:
    """Run the transformation of a Blick or check on ``run``, convert what it returned, check
    the table, and evaluate the unit's expectation at ``level``.

    A ``Skip`` that the transformation itself raises gives its reason, and neither a table nor a
    problem; so does a check at level ``off``, which does not run. Nothing else escapes,
    including a ``Skip`` raised while converting or checking what the transformation returned; it
    becomes a problem located in the code of the project at ``root``. An exception the
    transformation wraps in ``Raised`` is reported as raised by the action it names; a check's
    messages call its transformation the check. An expectation that cannot be evaluated keeps the
    table and gives the outcome ``error``.
    """
    is_check = isinstance(unit, Check)
    if is_check and level == "off":
        return Checked.skip(LEVEL_OFF)
    transformation = "check" if is_check else "transformation"
    action = transformation
    try:
        value = unit.transform(run)
        action = f"converting the returned {type(value).__name__}"
        frame, index_dropped = to_polars(value, f"the {transformation}")
        action = "checking the table"
        checked = check(frame, unit, index_dropped)
    except TableError as error:
        message = _with_check_hint(str(error)) if is_check else str(error)
        return Checked.failed(unit.problem(Kind.TRANSFORMATION, message))
    except (Exception, SystemExit) as error:
        if isinstance(error, Skip) and action == transformation:
            return Checked.skip(str(error))
        cause: BaseException = error
        if isinstance(error, Raised):
            action, cause = error.action, error.error
        prefer = unit.source.file if unit.source else None
        message = f"{action} raised {type(cause).__name__}: {cause}"
        problem = unit.problem(
            Kind.TRANSFORMATION,
            message + raised_at(cause, root, unit.source),
            source=locate(cause, root, prefer),
            traceback=project_traceback(cause, root),
        )
        return Checked.failed(problem)
    return _evaluated(checked, unit, level, root)


def _first_line(error: BaseException) -> str:
    """The first line of an error's message, which an outcome's message holds on one line."""
    return next(iter(str(error).splitlines()), "")


@dataclass(frozen=True)
class _Rows:
    """Rows and the roles of their columns."""

    frame: pl.DataFrame
    dims: Sequence[str]
    measures: Sequence[str]


def _picked(expectation: NoRows, table: _Rows, unit: Unit, root: Path) -> _Rows:
    """The rows that the function of ``no_rows`` returns for ``table``, checked under a check's
    table rules; raises ``Unevaluable`` when it raises, ``bk.Skip`` included, or returns what a
    check could not hold or what cannot be read at all."""
    assert expectation.rows is not None
    name = f"the rows function {function_name(expectation.rows)}"
    try:
        value = expectation.rows(table.frame)
    except (Exception, SystemExit) as error:
        located = raised_at(error, root, unit.source)
        raise Unevaluable(
            f"{name} raised {type(error).__name__}: {_first_line(error)}{located}"
        ) from error
    try:
        frame, _ = to_polars(value, name)
        if not frame.columns:
            return _Rows(frame, [], [])
        picked = _checked_table(frame, _Rules(None, None), False)
    except TableError as error:
        raise Unevaluable(str(error)) from error
    except Exception as error:
        raise Unevaluable(
            f"{name} returned rows that cannot be read: {type(error).__name__}: "
            f"{_first_line(error)}"
        ) from error
    if picked.frame is None:
        raise Unevaluable(
            f"{name} returned rows a check could not hold: {'; '.join(picked.errors)}"
        )
    return _Rows(picked.frame, picked.dims, picked.measures)


def _evaluated(checked: Checked, unit: Unit, level: Level, root: Path) -> Checked:
    """``checked`` with the outcome of the unit's expectation at ``level``; for a check, its table
    is then the offending rows, worst first, at most ``MAX_STORED`` of them, or, when the
    expectation cannot be evaluated, its rows as they are."""
    expectation = unit.expect
    if checked.frame is None or checked.schema is None or expectation is None or level == "off":
        return checked
    table = _Rows(
        checked.frame,
        [d.name for d in checked.schema.dimensions],
        [m.name for m in checked.schema.measures],
    )
    rows = table
    try:
        subject = table
        if isinstance(expectation, NoRows) and expectation.rows is not None:
            # Without rows there is nothing to pick, and the columns of what the function would
            # return are unknown, so nothing is checked against them.
            subject = (
                _picked(expectation, table, unit, root)
                if table.frame.height
                else _Rows(pl.DataFrame(), [], [])
            )
        evaluation = evaluate(
            expectation, subject.frame, subject.dims, subject.measures, level, where=table.dims
        )
    except Unevaluable as error:
        outcome = evaluation_error(expectation, str(error))
    else:
        outcome = evaluation.outcome
        rows = _Rows(evaluation.offending, subject.dims, subject.measures)
    if not isinstance(unit, Check):
        return dataclasses.replace(checked, outcome=outcome)
    stored = rows.frame.head(MAX_STORED)
    schema = _schema(stored, rows.dims, rows.measures, {})
    return dataclasses.replace(checked, frame=stored, schema=schema, outcome=outcome)
