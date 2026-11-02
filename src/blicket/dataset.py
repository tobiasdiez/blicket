"""The dataset protocol: what the Blick builder asks of a run, and how a project provides it.

A project provides it with ``dataset(run)`` in the module that holds its loader, ``blicketconf``
by default, next to ``load_run``. It returns an object with three methods: ``quantities()``, the
quantities of the run (flows, stocks, parameters, variables) as ``Quantity``; ``dimensions()``,
the dimensions they are defined over as ``Dimension``, each once, with its values in display
order; and ``select(quantity, keep, values)``, the table of one quantity. The function is
optional: a project without it has no builder. ``Frames`` is the stock dataset: tables, one per
quantity, which blicket filters and sums itself.
"""

import functools
import importlib
import inspect
import threading
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from blicket import tables
from blicket.errors import DatasetError, issue_field
from blicket.loader import DEFAULT_LOADER_MODULE, split_target
from blicket.schema import Dimension, DimensionType, dimension_type, polars_type
from blicket.tracebacks import project_traceback, raised_at

DATASET_FUNCTION = "dataset"
_METHODS = ("quantities", "dimensions", "select")


class Quantity(BaseModel):
    """A quantity of a run that the builder can chart, such as a flow, a stock or a parameter.

    ``name`` is unique in the dataset, such as ``flows/polymerization => primary_market``;
    ``title`` is what the builder shows, the name without its ``group`` prefix by default.
    ``unit`` is ``None`` when the model does not say. ``dimensions`` names dimensions of the
    dataset, in the model's order. ``additive`` says whether summing over a dimension makes sense:
    true for flows and stocks, false for rates, shares, prices and other intensive quantities,
    whose dimensions the builder never sums. ``group`` groups the quantities in the builder's
    list.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    title: str | None = None
    unit: str | None = None
    dimensions: tuple[str, ...]
    additive: bool = True
    group: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_title(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("title") is None:
            name, group = data.get("name"), data.get("group")
            if isinstance(name, str):
                prefix = f"{group}/" if isinstance(group, str) else ""
                data = {**data, "title": name.removeprefix(prefix) or name}
        return data

    @property
    def label(self) -> str:
        """The title, which a validated quantity always has."""
        return self.title or self.name


class Dataset(Protocol):
    """What the Blick builder asks of a run, as ``dataset(run)`` in the loader's module returns it.

    ``select`` returns a table that a transformation could return, a polars or pandas frame or an
    object with ``to_df()``: the ``keep`` dimensions as columns and one measure column, its rows
    restricted to ``values`` for the dimensions named there before aggregating, and aggregated
    (summed) over the quantity's other dimensions; with an empty ``keep``, one row, the total.
    blicket asks to aggregate only an ``additive`` quantity, and filters the kept dimensions once
    more. A value that a quantity lacks gives no rows.
    """

    def quantities(self) -> Sequence[Quantity]: ...

    def dimensions(self) -> Sequence[Dimension]: ...

    def select(
        self, quantity: str, keep: Sequence[str], values: Mapping[str, Sequence[Any]]
    ) -> Any: ...


_CONVERTED = 8  # how many tables a Frames keeps converted


def _a(dtype: DimensionType) -> str:
    return f"{'an' if dtype == 'integer' else 'a'} {dtype}"


def _normalized(column: pl.Series, target: pl.DataType) -> pl.Series:
    """``column`` as a checked table holds a dimension of ``target``: a time zone converted away,
    an integer widened, a categorical read as strings."""
    dtype = column.dtype
    if isinstance(dtype, pl.Datetime) and dtype.time_zone is not None:
        column = column.dt.convert_time_zone("UTC").dt.replace_time_zone(None)
    return column.cast(target)


class Frames:
    """A dataset over tables, one per quantity, which blicket filters and sums itself.

    ``add(name, table, ...)`` adds a quantity with its table, a long table as a transformation
    returns one: the quantity's dimensions as columns and one measure column. ``table`` may also
    be a function that returns it, called once the table is first needed. The quantity's
    dimensions are the table's columns but the last unless ``dimensions`` names them.
    ``dimensions()`` are the dimensions given to the constructor that a quantity names, in that
    order, then the others as the tables hold them: the dtype from the column, the values sorted,
    strings in order of appearance. ``select`` restricts the table to the values and sums over the
    dimensions not kept; a subclass that aggregates another way overrides it and reads the table
    with ``frame``. The last eight tables read stay converted.
    """

    def __init__(self, dimensions: Iterable[Dimension] = ()) -> None:
        self._known: dict[str, Dimension] = {}
        for dimension in dimensions:
            if dimension.name in self._known:
                raise ValueError(f"the dimension {dimension.name!r} is given twice")
            self._known[dimension.name] = dimension
        self._quantities: dict[str, Quantity] = {}
        self._given: dict[str, Any] = {}  # each quantity's table as given, or the function
        self._converted: OrderedDict[str, pl.DataFrame] = OrderedDict()
        self._lock = threading.Lock()

    def add(
        self,
        name: str,
        table: Any,
        *,
        title: str | None = None,
        unit: str | None = None,
        dimensions: Sequence[str] | None = None,
        additive: bool = True,
        group: str | None = None,
    ) -> Quantity:
        """Add the quantity ``name`` with its ``table`` and return it as a ``Quantity``.

        ``table`` is the quantity's table, or a function that returns it, called once the table
        is first needed; without ``dimensions``, now, since they are its columns but the last.
        The other arguments are the ``Quantity``'s fields.
        """
        if name in self._quantities:
            raise ValueError(f"{name!r} was added twice")
        converted = None
        if dimensions is None:
            converted = self._read(name, table)
            if not converted.columns:
                raise ValueError(f"the table of {name!r} has no columns")
            dimensions = converted.columns[:-1]
        quantity = Quantity(
            name=name,
            title=title,
            unit=unit,
            dimensions=tuple(dimensions),
            additive=additive,
            group=group,
        )
        self._quantities[name] = quantity
        self._given[name] = table
        if converted is not None:
            with self._lock:
                self._remember(name, converted)
        return quantity

    def quantities(self) -> list[Quantity]:
        return list(self._quantities.values())

    def dimensions(self) -> list[Dimension]:
        named = dict.fromkeys(d for q in self._quantities.values() for d in q.dimensions)
        known = [d for name, d in self._known.items() if name in named]
        return [*known, *(self._derive(name) for name in named if name not in self._known)]

    def frame(self, quantity: str) -> pl.DataFrame:
        """The table of ``quantity`` as a polars frame, converted once."""
        with self._lock:
            found = self._converted.get(quantity)
            if found is None:
                found = self._read(quantity, self._given[quantity])
                self._remember(quantity, found)
            else:
                self._converted.move_to_end(quantity)
            return found

    def select(
        self, quantity: str, keep: Sequence[str], values: Mapping[str, Sequence[Any]]
    ) -> pl.DataFrame:
        """The table of ``quantity`` restricted to ``values`` and summed to the ``keep`` columns;
        a sum of nulls only is null."""
        frame = self.frame(quantity)
        measure = self._measure(quantity, frame)
        for name, wanted in values.items():
            frame = frame.filter(pl.col(name).is_in(list(wanted)))
        if frame.is_empty():
            return frame.select([*keep, measure])
        total = pl.when(pl.col(measure).is_not_null().any()).then(pl.col(measure).sum())
        if not keep:
            return frame.select(total.alias(measure))
        return frame.group_by(keep, maintain_order=True).agg(total.alias(measure))

    def _read(self, quantity: str, given: Any) -> pl.DataFrame:
        """The table ``given`` for ``quantity``, or what the function given returns, as polars."""
        if inspect.isroutine(given) or isinstance(given, functools.partial):
            given = given()
        try:
            return tables.to_polars(given)[0]
        except tables.TableError as error:
            raise ValueError(f"the table of {quantity!r}: {error}") from None

    def _remember(self, quantity: str, frame: pl.DataFrame) -> None:
        """Keep ``frame`` converted, and forget the one read longest ago beyond the limit."""
        self._converted[quantity] = frame
        self._converted.move_to_end(quantity)
        while len(self._converted) > _CONVERTED:
            self._converted.popitem(last=False)

    def _measure(self, quantity: str, frame: pl.DataFrame) -> str:
        """The measure column of ``frame``, the table of ``quantity``: the one column that is no
        dimension of it."""
        dimensions = self._quantities[quantity].dimensions
        others = [column for column in frame.columns if column not in dimensions]
        if len(others) != 1 or any(d not in frame.columns for d in dimensions):
            raise ValueError(
                f"the table of {quantity!r} has the columns {', '.join(frame.columns) or 'none'}; "
                f"expected its dimensions ({', '.join(dimensions) or 'none'}) and one measure "
                "column"
            )
        return others[0]

    def _derive(self, name: str) -> Dimension:
        """The dimension ``name`` as the tables of the quantities that have it hold it."""
        columns: dict[str, pl.Series] = {}
        for quantity in self._quantities.values():
            if name in quantity.dimensions:
                frame = self.frame(quantity.name)
                self._measure(quantity.name, frame)
                columns[quantity.name] = frame.get_column(name)
        typed: dict[str, DimensionType] = {}
        for quantity, column in columns.items():
            kind = dimension_type(column.dtype)
            if kind is None:
                raise ValueError(
                    f"the column {name!r} of {quantity!r} is {column.dtype}; dimensions are "
                    "strings, integers, booleans, dates or datetimes"
                )
            typed[quantity] = kind
        first, dtype = next(iter(typed.items()))
        for quantity, kind in typed.items():
            if kind != dtype:
                raise ValueError(
                    f"the column {name!r} is {_a(dtype)} in {first!r} but {_a(kind)} in "
                    f"{quantity!r}"
                )
        target = polars_type(dtype)
        parts = [_normalized(c, target).unique(maintain_order=True) for c in columns.values()]
        values = pl.concat(parts).unique(maintain_order=True).drop_nulls()
        if dtype != "string":
            values = values.sort()
        return Dimension(name=name, dtype=dtype, values=values.to_list())


def coerce(value: Any, dtype: DimensionType) -> Any:
    """``value`` as a value of a dimension of ``dtype``, also when given as text, as a URL holds it.

    Datetimes become naive UTC, as tables hold them. Raises ``ValueError`` when ``value`` is no
    value of that type.
    """
    match dtype:
        case "string":
            if isinstance(value, str):
                return value
        case "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
                return int(value)
        case "boolean":
            if isinstance(value, bool):
                return value
            if value in ("true", "false"):
                return value == "true"
        case "date":
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return date.fromisoformat(value[:10])
        case "datetime":
            moment = datetime.fromisoformat(value) if isinstance(value, str) else value
            if isinstance(moment, datetime):
                if moment.tzinfo is not None:
                    moment = moment.astimezone(UTC).replace(tzinfo=None)
                return moment
    raise ValueError(f"{value!r} is not a{'n' if dtype == 'integer' else ''} {dtype}")


@dataclass(frozen=True)
class Contents:
    """A dataset checked against the protocol: its quantities and dimensions by name, read once,
    the dimensions' values typed by their dtype, and the dataset itself for ``select``."""

    dataset: Dataset
    quantities: Mapping[str, Quantity]
    dimensions: Mapping[str, Dimension]


def _absent(target: str) -> str:
    """Why a project whose loader is ``target`` has no builder: its module has no ``dataset``."""
    module, attribute = split_target(target)
    where = f"{module}.py" if module == DEFAULT_LOADER_MODULE else module
    return (
        f"no {DATASET_FUNCTION}(run) next to {attribute.rpartition('.')[2]} in {where}; add one "
        'that returns the quantities and dimensions of a run (see "The Blick builder" in the '
        "README)"
    )


def _raised(what: str, error: BaseException, root: Path) -> DatasetError:
    """A ``DatasetError`` for an exception raised by project code, with its traceback."""
    message = f"{what} raised {type(error).__name__}: {error}" + raised_at(error, root, None)
    return DatasetError(message, project_traceback(error, root))


def check(found: Any, root: Path, call: str = "the dataset") -> Contents:
    """The dataset ``found`` of the project at ``root``, read and checked against the protocol.

    ``call`` says where it came from, for the messages. Raises ``DatasetError`` when it lacks a
    method, its ``quantities()`` or ``dimensions()`` raise, or what they return is invalid: a
    name given twice, a dimension unknown, a value of another type than its dimension's.
    """
    kind = type(found).__name__
    for method in _METHODS:
        if not callable(getattr(found, method, None)):
            raise DatasetError(
                f"{call} returned a {kind}, which has no {method}(); a dataset has quantities(), "
                "dimensions() and select(quantity, keep, values)"
            )
    listed: dict[str, list[Any]] = {}
    for method in ("dimensions", "quantities"):
        try:
            listed[method] = list(getattr(found, method)())
        except (Exception, SystemExit) as error:
            raise _raised(f"{method}() of the dataset of {call}", error, root) from error
    try:
        dimensions = [Dimension.model_validate(d) for d in listed["dimensions"]]
        quantities = [Quantity.model_validate(q) for q in listed["quantities"]]
    except ValidationError as error:
        issue = error.errors()[0]
        field = issue_field(issue) or "it"
        raise DatasetError(
            f"{call}: a {error.title} is invalid: {field}: {issue['msg']}"
        ) from error
    known: dict[str, Dimension] = {}
    for dimension in dimensions:
        if dimension.name in known:
            raise DatasetError(f"{call}: dimensions() names {dimension.name!r} twice")
        try:
            values = [coerce(value, dimension.dtype) for value in dimension.values]
        except ValueError as error:
            raise DatasetError(f"{call}: dimension {dimension.name!r}: {error}") from error
        known[dimension.name] = dimension.model_copy(update={"values": values})
    by_name: dict[str, Quantity] = {}
    for quantity in quantities:
        if quantity.name in by_name:
            raise DatasetError(f"{call}: quantities() names {quantity.name!r} twice")
        if unknown := [d for d in quantity.dimensions if d not in known]:
            raise DatasetError(
                f"{call}: quantity {quantity.name!r} has the dimension(s) {', '.join(unknown)}, "
                "which dimensions() lacks"
            )
        if len(set(quantity.dimensions)) < len(quantity.dimensions):
            raise DatasetError(f"{call}: quantity {quantity.name!r} names a dimension twice")
        by_name[quantity.name] = quantity
    return Contents(found, by_name, known)


def _open(target: str, run: object, root: Path) -> Contents | None:
    """The dataset of ``run``, from ``dataset(run)`` in the module of the loader ``target``.

    ``None`` when the module has no ``dataset``. Raises ``DatasetError`` when it raises, or when
    what it returns lacks a method of the protocol, its ``quantities()`` or ``dimensions()``
    raise, or what they return is invalid: a name given twice, a dimension unknown.
    """
    module_name, _ = split_target(target)
    module = importlib.import_module(module_name)  # imported by the loader already
    function = getattr(module, DATASET_FUNCTION, None)
    if function is None:
        return None
    call = f"{DATASET_FUNCTION}(run) in {module_name}"
    if not callable(function):
        raise DatasetError(f"{DATASET_FUNCTION} in {module_name} is not a function")
    try:
        found = function(run)
    except (Exception, SystemExit) as error:
        raise _raised(call, error, root) from error
    return check(found, root, call)


@dataclass(frozen=True)
class Found:
    """The dataset of a run, or why there is none.

    ``contents`` is ``None`` when the project has no dataset or ``dataset(run)`` failed; then
    ``reason`` says why, and ``error`` is the failure, if that is what it was.
    """

    contents: Contents | None
    reason: str | None = None
    error: DatasetError | None = None


def find(target: str, run: object, root: Path) -> Found:
    """The dataset of ``run``, from ``dataset(run)`` in the module of the loader ``target``, or why
    there is none: the module has no ``dataset``, or it raised, or what it returned does not
    follow the protocol (a method missing or raising, a name given twice, a dimension unknown,
    a value of another type than its dimension's)."""
    try:
        contents = _open(target, run, root)
    except DatasetError as error:
        return Found(None, str(error), error)
    return Found(contents) if contents is not None else Found(None, _absent(target))
