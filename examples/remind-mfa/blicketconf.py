"""The blicket loader for remind-mfa runs, and the dataset the Blick builder charts."""

import pickle
from pathlib import Path
from typing import TYPE_CHECKING

import flodym as fd
import remind_mfa

import blicket as bk

if TYPE_CHECKING:  # annotations only
    from remind_mfa.plastics.plastics_model import PlasticsModel


def load_run(selection: bk.RunSelection) -> tuple[PlasticsModel, bk.RunInfo]:
    """Unpickle the model of one plastics run folder, ``<prefix>_<model>_<scenario>_<regions>/``.

    The run id is the folder's name; the profile is model, scenario and region set from the
    run's config. The pickle carries no commit of the model checkout, so the run info has none.
    """
    folder = selection.path
    path = folder / "model.pickle"
    if not path.is_file():
        raise FileNotFoundError(f"{folder} holds no model.pickle; is it a remind-mfa run folder?")
    try:
        with path.open("rb") as file:
            run = pickle.load(file)
    except (AttributeError, ImportError) as error:
        checkout = Path(remind_mfa.__file__).parent.parent
        raise RuntimeError(
            f"{path} was written by another remind-mfa version than the checkout at {checkout} "
            f"({type(error).__name__}: {error}); check out the commit that produced the run. The "
            "pickle does not record its commit; for the example runs see data_out/RUNS.md. These "
            "Blicks read plastics runs only."
        ) from error
    cfg = run.cfg
    if cfg.model.value != "plastics":
        raise ValueError(f"{folder} is a {cfg.model.value} run; these Blicks read plastics runs")
    profile = f"{cfg.model.value}_{cfg.model_switches.scenario}_{cfg.input.region_mapping}"
    return run, bk.RunInfo(id=folder.name, profile=profile, fingerprint=bk.fingerprint(path))


def dataset(run: PlasticsModel) -> bk.Frames:
    """The flows, stocks and parameters of a plastics run for the Blick builder of ``blicket dev``.

    Quantities: ``flows/<flow>`` in t per year; ``stocks/<stock>/stock`` in t and
    ``stocks/<stock>/inflow`` and ``/outflow`` in t per year; ``parameters/<parameter>``, not
    additive, without the parameters that have no dimension; and the historical system's flows
    and stocks under ``historical/``, its parameters left out, since most of them are the future
    system's. ``Historical Time`` is called ``Time``. An array is read as a frame when first
    charted.
    """
    future, historical = run.future_mfa, run.historical_mfa
    frames = bk.Frames(dimensions=_dimensions(future.dims))
    for key, flow in future.flows.items():
        _add(frames, f"flows/{key}", flow, "flows", "t per year")
    for key, stock in future.stocks.items():
        _add_stock(frames, f"stocks/{key}", stock, "stocks")
    for key, parameter in future.parameters.items():
        if parameter.dims.ndim:
            unit = _parameter_unit(key)
            _add(frames, f"parameters/{key}", parameter, "parameters", unit, additive=False)
    for key, flow in historical.flows.items():
        title = f"{key} (historical)"
        _add(frames, f"historical/flows/{key}", flow, "historical", "t per year", title)
    for key, stock in historical.stocks.items():
        _add_stock(frames, f"historical/stocks/{key}", stock, "historical", " (historical)")
    return frames


# The historical system counts the same calendar years as the future one, on a dimension of its
# own; under one name, a historical flow and its future counterpart share a chart.
_NAMES = {"Historical Time": "Time"}
# Units of parameters by name. A rate or share is a fraction; the other parameters have none.
_UNITS = {
    "gdppc": "2005 USD PPP per person",
    "lifetime_mean": "years",
    "lifetime_std": "years",
}


def _parameter_unit(name: str) -> str | None:
    if name.endswith(("_rate", "_share", "_shares")):
        return "fraction"
    return _UNITS.get(name)


def _dimensions(dims: fd.DimensionSet) -> list[bk.Dimension]:
    """The model's dimensions as the dataset names them, typed by their items, in the model's
    order. Historical Time's years are a part of Time's, so the longer list of years wins."""
    named: dict[str, bk.Dimension] = {}
    for dimension in dims:
        name = _NAMES.get(dimension.name, dimension.name)
        known = named.get(name)
        if known is None or len(known.values) < dimension.len:
            integer = all(isinstance(item, int) for item in dimension.items)
            named[name] = bk.Dimension(
                name=name, dtype="integer" if integer else "string", values=list(dimension.items)
            )
    return list(named.values())


def _add(
    frames: bk.Frames,
    name: str,
    array: fd.FlodymArray,
    group: str,
    unit: str | None,
    title: str | None = None,
    *,
    additive: bool = True,
) -> None:
    """``array`` as the quantity ``name``, read as a frame when first charted; an array over both
    Time and Historical Time is left out."""
    names = [_NAMES.get(d, d) for d in array.dims.names]
    if len(set(names)) < len(names):
        return
    frames.add(
        name,
        lambda: array.to_df().rename_axis(index=names),
        title=title,
        unit=unit,
        dimensions=names,
        additive=additive,
        group=group,
    )


def _add_stock(frames: bk.Frames, name: str, stock: fd.Stock, group: str, suffix: str = "") -> None:
    key = name.rpartition("/")[2]
    for part, unit in (("stock", "t"), ("inflow", "t per year"), ("outflow", "t per year")):
        title = f"{key}/{part}{suffix}" if suffix else None
        _add(frames, f"{name}/{part}", getattr(stock, part), group, unit, title)
