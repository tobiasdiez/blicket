"""The Blick builder's query: an ad hoc Blick over a project's dataset, built as a code Blick is.

A query names one or more quantities of the dataset, a plot type, the dimensions bound to the
plot's dimension channels, the other dimensions kept, and the values kept per dimension. Every
other dimension of a quantity is summed by the dataset. Several quantities are told apart by a
dimension ``Quantity`` holding their titles; when it is not kept, blicket sums over it. What the
viewer shows of the result (the split into panels, the y axes, the filter values) is not part of
the query: every kept dimension the plot leaves unbound is a filter control of the result.
"""

import functools
import hashlib
import io
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from blicket import plots, tables
from blicket.dataset import Contents, Dataset, Quantity, coerce
from blicket.errors import DefinitionError, Kind, Problem, did_you_mean
from blicket.model import Blick, BlickEntry
from blicket.plots import Channel, PlotSpec, PlotType
from blicket.schema import Dimension, DimensionType, polars_type

BLICK_ID = "builder/query"
GROUP = "builder"
QUANTITY = "Quantity"
MEASURE = "value"
MAX_ROWS = 100_000
TABLES = "dev/tables"
# The words for the built-in channels in messages, as the viewer names them.
_CHANNEL_WORDS = {"color": "colour", "linetype": "line type"}


def plot_types() -> list[PlotType]:
    """The plot types the builder offers: the built-ins that chart one measure, since a query
    makes one."""
    return [
        plot_type
        for plot_type in plots.builtins()
        if sum(channel.kind == "measure" for channel in plot_type.channels) == 1
    ]


class Query(BaseModel):
    """What the builder asks for: the quantities, in the order picked, the plot type, the plot's
    dimension channels bound to dimensions, the unbound dimensions kept, and per dimension the
    values kept, all of them when absent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quantities: tuple[str, ...] = Field(min_length=1)
    plot: str
    mapping: dict[str, str] = {}
    keep: tuple[str, ...] = ()
    values: dict[str, tuple[Any, ...]] = {}


class PlotOption(BaseModel):
    """A plot type the builder offers, with its channels."""

    model_config = ConfigDict(frozen=True)

    name: str
    channels: tuple[Channel, ...]


class Options(BaseModel):
    """What the builder offers: the dataset's quantities and dimensions, and the plot types."""

    model_config = ConfigDict(frozen=True)

    quantities: tuple[Quantity, ...]
    dimensions: tuple[Dimension, ...]
    plots: tuple[PlotOption, ...]

    @classmethod
    def of(cls, contents: Contents) -> Options:
        """What the builder offers for the dataset ``contents``."""
        return cls(
            quantities=tuple(contents.quantities.values()),
            dimensions=tuple(contents.dimensions.values()),
            plots=tuple(PlotOption(name=t.name, channels=t.channels) for t in plot_types()),
        )


@dataclass(frozen=True)
class Result:
    """The entry of a query's Blick, as a build's manifest would hold it, and its table as
    Parquet, ``None`` when the entry has an error. The entry's ``hash`` names the bytes."""

    entry: BlickEntry
    table: bytes | None = None


class _Refused(Exception):
    """A query that cannot be made into a Blick, with why."""


@dataclass(frozen=True)
class _Plan:
    """A query checked against the dataset: the quantities, the kept dimensions in the order of
    the table's columns, the values coerced to their dimension's type, each kept dimension's
    values in display order, and the type of every dimension."""

    quantities: tuple[Quantity, ...]
    dims: tuple[str, ...]
    values: Mapping[str, tuple[Any, ...]]
    order: Mapping[str, tuple[Any, ...]]
    dtypes: Mapping[str, DimensionType]

    @property
    def several(self) -> bool:
        return len(self.quantities) > 1

    @property
    def keep(self) -> list[str]:
        """The dimensions kept that the dataset knows: all but ``Quantity`` of several."""
        return [d for d in self.dims if not (self.several and d == QUANTITY)]


def _channel(name: str) -> str:
    return f"the {_CHANNEL_WORDS.get(name, name)} channel"


def _plot_type(name: str) -> PlotType:
    offered = {plot_type.name: plot_type for plot_type in plot_types()}
    if name not in offered:
        raise _Refused(f"no plot type {name!r} in the builder; it offers {', '.join(offered)}")
    return offered[name]


def _quantities(contents: Contents, names: tuple[str, ...]) -> tuple[Quantity, ...]:
    found: list[Quantity] = []
    for name in names:
        if (quantity := contents.quantities.get(name)) is None:
            close = did_you_mean(name, contents.quantities)
            hint = f"; did you mean {close!r}?" if close else ""
            raise _Refused(f"the dataset has no quantity {name!r}{hint}")
        if quantity.name in (q.name for q in found):
            raise _Refused(f"the quantity {name!r} is picked twice")
        found.append(quantity)
    if len(found) > 1:
        if QUANTITY in contents.dimensions:
            raise _Refused(
                f"the dataset has a dimension called {QUANTITY}, so several quantities cannot be "
                "told apart in one chart; pick one"
            )
        titles = [quantity.label for quantity in found]
        if repeated := sorted({title for title in titles if titles.count(title) > 1}):
            raise _Refused(
                f"several quantities have the title {repeated[0]!r}, so the chart cannot tell "
                "them apart; pick one of them"
            )
    return tuple(found)


def _check_mapping(plot_type: PlotType, mapping: Mapping[str, str]) -> None:
    """Refuse a mapping that names a channel the plot type has not, or leaves required ones
    empty, all of them in one message, in the builder's words."""
    dimension_channels = [c.name for c in plot_type.channels if c.kind == "dimension"]
    for channel in mapping:
        if channel not in dimension_channels:
            raise _Refused(
                f"plot type {plot_type.name} has no dimension channel {channel!r}; its dimension "
                f"channels are {', '.join(dimension_channels)}"
            )
    empty = [
        channel.name
        for channel in plot_type.channels
        if channel.kind == "dimension" and channel.required and channel.name not in mapping
    ]
    if not empty:
        return
    words = [_CHANNEL_WORDS.get(name, name) for name in empty]
    roles = " and one the ".join(f"role {word}" for word in words)
    if len(empty) == 1:
        raise _Refused(f"{_channel(empty[0])} needs a dimension; give one the {roles}")
    listed = f"{', '.join(words[:-1])} and {words[-1]}"
    raise _Refused(f"the {listed} channels need a dimension; give one the {roles}")


def _kept(contents: Contents, query: Query, picked: tuple[Quantity, ...]) -> list[str]:
    """The dimensions kept, mapped ones first; refused when a quantity lacks one or would be
    summed though it is not additive."""
    bound = {dimension: channel for channel, dimension in query.mapping.items()}
    kept = list(dict.fromkeys([*query.mapping.values(), *query.keep]))
    several = len(picked) > 1
    for dimension in kept:
        if dimension == MEASURE:
            raise _Refused(f"a dimension called {MEASURE!r} cannot be kept: it is the measure")
        if dimension == QUANTITY and several:
            continue
        if dimension not in contents.dimensions:
            raise _Refused(f"the dataset has no dimension {dimension!r}")
        for quantity in picked:
            if dimension not in quantity.dimensions:
                role = (
                    f"{dimension} is on {_channel(bound[dimension])}"
                    if dimension in bound
                    else f"{dimension} is a filter or on panels"
                )
                raise _Refused(f"{role}, but {quantity.label} has no dimension {dimension}")
    for quantity in picked:
        summed = [d for d in quantity.dimensions if d not in kept]
        if summed and not quantity.additive:
            raise _Refused(
                f"{quantity.label} is not additive, so it cannot be summed over "
                f"{', '.join(summed)}; keep {'it' if len(summed) == 1 else 'them'} as a filter or "
                "on a channel"
            )
    intensive = [quantity.label for quantity in picked if not quantity.additive]
    if several and QUANTITY not in kept and intensive:
        raise _Refused(
            f"{QUANTITY} is summed, but {intensive[0]} is not additive; keep {QUANTITY} as a "
            "filter, on panels or on a channel"
        )
    return kept


def _unit(picked: tuple[Quantity, ...]) -> str | None:
    """The one unit the quantities know; refused when they know several."""
    units = list(dict.fromkeys(q.unit for q in picked if q.unit is not None))
    if len(units) > 1:
        raise _Refused(
            f"the quantities have different units ({', '.join(units)}); pick quantities of one unit"
        )
    return units[0] if units else None


def _coerced_values(
    values: Mapping[str, tuple[Any, ...]], dtypes: Mapping[str, DimensionType]
) -> dict[str, tuple[Any, ...]]:
    """The values kept, each coerced to its dimension's type; refused when one is not one."""
    coerced: dict[str, tuple[Any, ...]] = {}
    for dimension, given in values.items():
        if dimension not in dtypes:
            raise _Refused(f"values are given for {dimension!r}, which is no dimension here")
        try:
            coerced[dimension] = tuple(coerce(value, dtypes[dimension]) for value in given)
        except ValueError as error:
            raise _Refused(f"a value of {dimension}: {error}") from None
    return coerced


def _plan(contents: Contents, query: Query) -> tuple[_Plan, Blick]:
    """The query checked against the dataset, and the Blick that runs it."""
    picked = _quantities(contents, query.quantities)
    plot_type = _plot_type(query.plot)
    _check_mapping(plot_type, query.mapping)
    kept = _kept(contents, query, picked)
    unit = _unit(picked)
    several = len(picked) > 1
    titles = tuple(quantity.label for quantity in picked)
    dtypes: dict[str, DimensionType] = {n: d.dtype for n, d in contents.dimensions.items()}
    if several:
        dtypes[QUANTITY] = "string"
    values = _coerced_values(query.values, dtypes)
    # The table's columns: Quantity first, then the dataset's dimensions in its order.
    named = [d for d in contents.dimensions if d in kept]
    order = {d: tuple(contents.dimensions[d].values) for d in named}
    if several and QUANTITY in kept:
        named.insert(0, QUANTITY)
        order[QUANTITY] = titles
    measure = next(c.name for c in plot_type.channels if c.kind == "measure")
    try:
        spec = PlotSpec(plot_type, {**query.mapping, measure: MEASURE})
    except DefinitionError as error:
        raise _Refused(str(error)) from None
    plan = _Plan(picked, tuple(named), values, order, dtypes)
    blick = Blick(
        id=BLICK_ID,
        title=", ".join(titles),
        unit=unit,
        group=GROUP,
        plot=spec,
        dims=plan.dims,
        measures=(MEASURE,),
        transform=functools.partial(_table, plan),
    )
    return plan, blick


def _cast(
    frame: pl.DataFrame, column: str, dtype: pl.DataType, quantity: Quantity, kind: str
) -> pl.DataFrame:
    """``frame`` with ``column`` cast to ``dtype``; a ``TableError`` that names the quantity when
    its values are not of that type."""
    try:
        return frame.with_columns(pl.col(column).cast(dtype))
    except pl.exceptions.PolarsError as error:
        reason = str(error).splitlines()[0]
        raise tables.TableError(
            f"select({quantity.name!r}) returned a {column!r} column that cannot be read as "
            f"{kind}: {reason}"
        ) from None


def _conform(frame: pl.DataFrame, quantity: Quantity, plan: _Plan) -> pl.DataFrame:
    """The frame ``select`` returned for ``quantity``: its measure as ``value``, the kept
    dimensions cast to their type and filtered by the values kept, in a fixed order."""
    keep = plan.keep
    others = [column for column in frame.columns if column not in keep]
    if [d for d in keep if d not in frame.columns] or len(others) != 1:
        expected = ", ".join(keep) if keep else "no dimension"
        raise tables.TableError(
            f"select({quantity.name!r}, ...) returned the columns {', '.join(frame.columns)}; "
            f"a dataset returns the dimensions kept ({expected}) and one measure column"
        )
    frame = frame.rename({others[0]: MEASURE})
    for dimension in keep:
        dtype = plan.dtypes[dimension]
        frame = _cast(frame, dimension, polars_type(dtype), quantity, f"{dtype}s")
    frame = _cast(frame, MEASURE, pl.Float64(), quantity, "numbers")
    for dimension in keep:
        if (wanted := plan.values.get(dimension)) is not None:
            kept = pl.Series(list(wanted), dtype=polars_type(plan.dtypes[dimension]))
            frame = frame.filter(pl.col(dimension).is_in(kept.implode()))
    return frame.select([*keep, MEASURE])


def _table(plan: _Plan, dataset: Dataset) -> pl.DataFrame:
    """The table of the query: each quantity selected from ``dataset``, several told apart by
    ``Quantity`` and summed over it when it is not kept."""
    keep = plan.keep
    frames: list[pl.DataFrame] = []
    for quantity in plan.quantities:
        values = {d: list(v) for d, v in plan.values.items() if d in quantity.dimensions}
        try:
            returned = dataset.select(quantity.name, list(keep), values)
        except (Exception, SystemExit) as error:
            raise tables.Raised(f"select({quantity.name!r}) of the dataset", error) from error
        frame = _conform(tables.to_polars(returned)[0], quantity, plan)
        if plan.several:
            frame = frame.with_columns(pl.lit(quantity.label).alias(QUANTITY))
        frames.append(frame)
    if not plan.several:
        return frames[0]
    table = pl.concat(frames, how="vertical_relaxed")
    if (wanted := plan.values.get(QUANTITY)) is not None:
        table = table.filter(
            pl.col(QUANTITY).is_in(pl.Series(list(wanted), dtype=pl.String).implode())
        )
    if QUANTITY not in plan.dims:
        # A row that one quantity lacks counts as 0; a sum of nothing but nulls stays null.
        total = pl.when(pl.col(MEASURE).is_not_null().any()).then(pl.col(MEASURE).sum())
        if keep:
            table = table.group_by(keep, maintain_order=True).agg(total)
        else:
            table = table.select(total)
    return table.select([*plan.dims, MEASURE])


def _refusal_entry(message: str, start: float) -> BlickEntry:
    """The entry of a query that cannot be made into a Blick: no definition, one problem."""
    problem = Problem(kind=Kind.QUERY, message=message, ids=(BLICK_ID,))
    return BlickEntry(
        id=BLICK_ID, name=BLICK_ID, group=GROUP, problems=(problem,), timing_ms=_since(start)
    )


def _since(start: float) -> float:
    """The milliseconds since ``start``, a ``perf_counter`` reading, to a tenth."""
    return round((time.perf_counter() - start) * 1000, 1)


def _parquet(frame: pl.DataFrame) -> tuple[bytes, str]:
    """The frame as Parquet, and the sha256 of the bytes in hex."""
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    table = buffer.getvalue()
    return table, hashlib.sha256(table).hexdigest()


def _too_many_rows(frame: pl.DataFrame, plan: _Plan) -> str:
    """Why a table is too large: its size per dimension, and what helps, which for a quantity
    that is not additive is no sum."""
    sizes = " \N{MULTIPLICATION SIGN} ".join(f"{d} {frame[d].n_unique()}" for d in plan.dims)
    helps = (
        "sum a dimension or keep fewer of its values"
        if all(quantity.additive for quantity in plan.quantities)
        else "keep fewer values of a dimension with its Values list"
    )
    return (
        f"the table has {frame.height:,} rows, more than the {MAX_ROWS:,} the builder draws "
        f"({sizes}); {helps}"
    )


def run_query(contents: Contents, query: Query, root: Path) -> Result:
    """Run ``query`` over the dataset ``contents`` of the project at ``root``.

    The table is checked as a code Blick's is, and an exception raised by the dataset becomes a
    problem with the project's traceback. The entry's ``data`` is ``dev/tables/<hex>.parquet``,
    where ``<hex>`` is the sha256 of the Parquet bytes, its ``hash`` ``parquet-sha256:<hex>``, and
    the values of its dimensions are in the dataset's display order. A query that cannot be made
    into a Blick (an unknown quantity or plot type, a dimension a quantity lacks, a sum over an
    intensive quantity, different units) gives an entry without a definition and with the
    problem; a table of more than ``MAX_ROWS`` rows gives an entry with a problem and no table.
    """
    start = time.perf_counter()
    try:
        plan, blick = _plan(contents, query)
    except _Refused as refused:
        return Result(_refusal_entry(str(refused), start))
    checked = tables.compute(blick, contents.dataset, root)
    if checked.frame is None or checked.schema is None:
        return Result(blick.entry(problems=checked.problems, timing_ms=_since(start)))
    frame = checked.frame
    if frame.height > MAX_ROWS:
        problem = blick.problem(Kind.QUERY, _too_many_rows(frame, plan))
        problems = (*checked.problems, problem)
        return Result(blick.entry(problems=problems, timing_ms=_since(start)))
    table, digest = _parquet(frame)
    entry = blick.entry(
        problems=checked.problems,
        data=f"{TABLES}/{digest}.parquet",
        hash=f"parquet-sha256:{digest}",
        rows=frame.height,
        columns=tables.ordered(checked.schema, plan.order),
        timing_ms=_since(start),
    )
    return Result(entry, table)
