"""Blick output tables: what a transformation returns, as a polars frame checked against the Blick.

blicket depends on polars only. A pandas frame is recognised by its type's module and converted
column by column through numpy, so neither pandas nor pyarrow is needed here. Dimension columns
are normalised (strings for categoricals, ``Int64``, naive UTC ``Datetime("us")``), so that equal
tables from different libraries are equal.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from blicket.errors import Kind, Problem
from blicket.model import Blick
from blicket.schema import Dimension, Measure, TableSchema, dimension_type

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


@dataclass(frozen=True)
class Checked:
    """A table checked against its Blick.

    ``frame`` and ``schema`` are set exactly when no problem is an error; ``frame`` then holds the
    dimensions first, then the measures, its rows sorted by the dimensions.
    """

    frame: pl.DataFrame | None
    schema: TableSchema | None
    problems: tuple[Problem, ...]

    @classmethod
    def failed(cls, *problems: Problem) -> Checked:
        return cls(None, None, problems)


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


def to_polars(value: Any) -> tuple[pl.DataFrame, bool]:
    """Convert what a transformation returned to a polars frame.

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
        raise TableError(
            f'the transformation returned a {library} Series; return series.to_frame("value")'
        )
    if hasattr(value, "__arrow_c_stream__"):
        return pl.DataFrame(value), False
    for method in ("to_df", "to_dataframe"):
        convert = getattr(value, method, None)
        if callable(convert):
            frame = convert()
            if not _is_pandas(frame, "DataFrame"):
                raise TableError(
                    f"the transformation returned {_type_name(value)}, whose {method}() gives "
                    f"{_type_name(frame)}, not a pandas frame"
                )
            return _from_pandas(frame)
    if value is None:
        raise TableError("the transformation returned None; did it forget return?")
    if isinstance(value, dict | list):
        raise TableError(
            f"the transformation returned a {type(value).__name__}; wrap it in pl.DataFrame(...)"
        )
    raise TableError(
        f"the transformation returned {_type_name(value)}; return a polars or pandas frame, an "
        "Arrow table, or an object with to_df() or to_dataframe()"
    )


def _roles(
    frame: pl.DataFrame, blick: Blick, kinds: Mapping[str, str], errors: list[str]
) -> tuple[list[str], list[str]]:
    """The dimension and measure columns, from ``dims=``, ``measures=`` and the plot."""
    columns = frame.columns
    for option, named in (("dims", blick.dims), ("measures", blick.measures)):
        for column in named or ():
            if column not in columns:
                errors.append(
                    f"{option}= names the column {column!r}, which the table lacks; its columns "
                    f"are {', '.join(columns)}"
                )
    if errors:
        return [], []
    for column in sorted(set(blick.dims or ()) & set(blick.measures or ())):
        errors.append(f"{column!r} is named in both dims= and measures=")

    if blick.dims is not None:
        dims = [c for c in blick.dims if c in columns]
    elif blick.measures is not None:
        dims = [c for c in columns if c not in blick.measures]
    else:
        dims = [c for c in columns if kinds.get(c) == "dimension" or not frame.schema[c].is_float()]
    if blick.measures is not None:
        measures = [c for c in blick.measures if c in columns and c not in dims]
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
    blick: Blick,
    dims: Sequence[str],
    measures: Sequence[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[list[pl.Expr], set[str]]:
    """The casts to the normalised type of every column's role, and the columns whose type
    their role does not allow, with a problem for each."""
    bound = {column: channel for channel, column in blick.plot.mapping.items()}
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
        elif dtype.is_float() and blick.dims is None and blick.measures is not None:
            rejected.add(column)
            on = f" on {bound[column]}=" if column in bound else ""
            errors.append(
                f"{column!r}{on} is a float column that measures= leaves out, so it counts as a "
                f"dimension; add {column!r} to measures="
            )
        elif dimension_type(dtype) is None:
            rejected.add(column)
            where = f" (bound to {bound[column]}=)" if column in bound else ""
            if column in (blick.dims or ()):
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
            implied = blick.dims is not None and column not in (blick.measures or ())
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
    whose type was rejected already."""
    dims, rejected = roles
    for channel, column in blick.plot.mapping.items():
        dtype = frame.schema.get(column)
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


def _check_rows(frame: pl.DataFrame, dims: Sequence[str], errors: list[str]) -> None:
    """Dimension values are keys: no nulls, and no two rows alike."""
    if not dims:
        if frame.height > 1:
            errors.append(
                f"the table has {frame.height} rows but no dimension column to tell them apart"
            )
        return
    for column in dims:
        if nulls := frame[column].null_count():
            errors.append(
                f"dimension column {column!r} has {nulls} null value(s); dimension values are "
                "keys, so fill or drop them"
            )
    duplicated = frame.select(dims).is_duplicated()
    if count := duplicated.sum():
        example = frame.filter(duplicated).select(dims).row(0, named=True)
        errors.append(
            f"{count} rows repeat the dimension values of another row, such as {example}; "
            "aggregate them or add the column that tells them apart"
        )


def _check_measures(frame: pl.DataFrame, measures: Sequence[str], errors: list[str]) -> None:
    """Measures are finite."""
    for column in measures:
        if infinite := frame[column].is_infinite().sum():
            errors.append(
                f"measure column {column!r} has {infinite} infinite value(s), which no chart can "
                "show and no comparison can measure; replace them with null or a number"
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
    """The column's values: those in ``order`` first, the rest sorted."""
    values = column.unique().sort().to_list()
    return [v for v in order if v in values] + [v for v in values if v not in order]


def check(frame: pl.DataFrame, blick: Blick, index_dropped: bool = False) -> Checked:
    """Find each column's role, check the table against the Blick, and put it in output order.

    ``index_dropped`` says that the conversion dropped an unnamed pandas index, which a missing
    plot column may be. Every problem is collected before giving up, except that ``dims=`` and
    ``measures=`` must fit the table before anything else is checked.
    """
    if not frame.columns:
        return Checked.failed(blick.problem(Kind.TABLE, "the table has no columns"))
    channels = {channel.name: channel.kind for channel in blick.plot.plot_type.channels}
    kinds = {column: channels[channel] for channel, column in blick.plot.mapping.items()}
    errors: list[str] = []
    notes: list[str] = []
    dims, measures = _roles(frame, blick, kinds, errors)
    if errors:
        return Checked.failed(*(blick.problem(Kind.TABLE, message) for message in errors))
    # An Enum's categories give the display order of its values, which become strings.
    enum_order = {
        column: dtype.categories.to_list()
        for column in dims
        if isinstance(dtype := frame.schema[column], pl.Enum)
    }
    casts, rejected = _casts(frame, blick, dims, measures, errors, notes)
    frame = frame.with_columns(casts)
    # Keys and values are only checked once every column has a usable type.
    sound = not errors
    _check_plot(frame, blick, (dims, rejected), kinds, index_dropped, errors)
    if unbound := [m for m in measures if m not in kinds]:
        errors.append(
            f"the measure(s) {', '.join(map(repr, unbound))} are bound to no plot channel, so "
            f"no chart shows them; {_UNPIVOT_HINT}"
        )
    if frame.height == 0:
        notes.append("the table has no rows")
    if sound:
        _check_rows(frame, dims, errors)
        _check_measures(frame, measures, errors)
        _check_options(frame, blick, dims, errors, notes)
    problems = (
        *(blick.problem(Kind.TABLE, message) for message in errors),
        *(blick.problem(Kind.TABLE, message, severity="warning") for message in notes),
    )
    if errors:
        return Checked.failed(*problems)

    frame = frame.select([*dims, *measures])
    if dims:
        frame = frame.sort(dims)
    dimensions = []
    for column in dims:
        dtype = dimension_type(frame.schema[column])
        assert dtype is not None, "every dimension type was checked"
        order = blick.order.get(column) or enum_order.get(column, ())
        dimensions.append(Dimension(name=column, dtype=dtype, values=_values(frame[column], order)))
    measured = [Measure(name=column, dtype="float") for column in measures]
    return Checked(frame, TableSchema(dimensions=dimensions, measures=measured), problems)
