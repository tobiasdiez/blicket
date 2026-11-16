"""Checks of plastics runs: properties every run must have, whether or not a Blick charts them.

Each check returns the cells of the run that offend as a long table, none when the property holds.
The values are measured against the largest flow or stock of their MFA system, the scale of
flodym's own checks (``MFASystem._absolute_float_precision``), so that the round-off a solver
leaves, up to ``ROUND_OFF`` of that scale, is a warning, and anything beyond it fails. The project
is at level ``warn`` (``pyproject.toml``); the check of the flows is raised to ``error``.
"""

from typing import TYPE_CHECKING

import numpy as np
import polars as pl

import blicket as bk

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd
    from remind_mfa.plastics.plastics_model import PlasticsModel

bk.group("checks", title="Coherence checks")

# Within this, relative to the scale of its system, a value is round-off: a little more than
# flodym's tolerance of 100 float epsilons, 2.2e-14.
ROUND_OFF = 1e-13

# The historical system counts the same calendar years as the future one, on a dimension of its
# own; under one name, its cells and the future system's share a column.
_NAMES = {"Historical Time": "Time"}
# The order of the dimension columns, the union of the arrays' dimensions.
_ORDER = ["Time", "Element", "Region", "Polymer Type", "Polymer", "End Use"]


def _systems(run: PlasticsModel) -> dict[str, fd.MFASystem]:
    return {"future": run.future_mfa, "historical": run.historical_mfa}


def _scale(mfa: fd.MFASystem) -> float:
    """The largest absolute value of a flow or a stock of ``mfa``, as flodym scales its checks."""
    flows = [np.max(np.abs(flow.values)) for flow in mfa.flows.values()]
    stocks = [np.max(np.abs(stock.stock.values)) for stock in mfa.stocks.values()]
    return float(max(flows + stocks))


def _cells(array: fd.FlodymArray, values: np.ndarray, mask: np.ndarray) -> pl.DataFrame:
    """The cells of ``array`` where ``mask`` holds, as dimension columns and ``values`` there."""
    where = np.nonzero(mask)
    columns = {
        _NAMES.get(dimension.name, dimension.name): np.asarray(dimension.items)[index]
        for dimension, index in zip(array.dims, where, strict=True)
    }
    return pl.DataFrame({**columns, "value": values[where]})


def _table(frames: list[pl.DataFrame], first: list[str], measures: list[str]) -> pl.DataFrame:
    """The frames in one table: ``first``, the dimensions in a fixed order, null where an array
    lacks one, then ``measures``; empty when there are none."""
    if not frames:
        return pl.DataFrame()
    table = pl.concat(frames, how="diagonal_relaxed")
    dims = [name for name in _ORDER if name in table.columns]
    return table.select(*first, *dims, *measures)


@bk.check(
    title="Flows are not negative",
    expect=bk.expect.no_rows(by="relative", warn_within=ROUND_OFF),
    level="error",
)
def non_negative_flows(run: PlasticsModel) -> pl.DataFrame:
    """Every flow of the future and the historical system, relative to the largest flow or stock of
    its system; round-off below zero is a warning, a flow below that fails."""
    frames = []
    for system, mfa in _systems(run).items():
        scale = _scale(mfa)
        for name, flow in mfa.flows.items():
            values = flow.values
            if (negative := values < 0).any():
                cells = _cells(flow, values, negative)
                frames.append(
                    cells.with_columns(
                        System=pl.lit(system), Flow=pl.lit(name), relative=pl.col("value") / scale
                    )
                )
    return _table(frames, ["System", "Flow"], ["value", "relative"])


@bk.check(
    title="Stocks balance their flows",
    expect=bk.expect.no_rows(by="relative", warn_within=ROUND_OFF),
)
def stock_balance(run: PlasticsModel) -> pl.DataFrame:
    """Each stock's change from the year before equals its inflow minus its outflow, as flodym's
    get_stock_balance computes it; the gap, inflow minus outflow minus the change, relative to the
    largest flow or stock of its system."""
    frames = []
    for system, mfa in _systems(run).items():
        scale = _scale(mfa)
        for name, stock in mfa.stocks.items():
            change = np.diff(stock.stock.values, axis=0, prepend=0)
            gap = stock.inflow.values - stock.outflow.values - change
            if (unbalanced := gap != 0).any():
                cells = _cells(stock.stock, gap, unbalanced).rename({"value": "gap"})
                frames.append(
                    cells.with_columns(
                        System=pl.lit(system), Stock=pl.lit(name), relative=pl.col("gap") / scale
                    )
                )
    return _table(frames, ["System", "Stock"], ["gap", "relative"])
