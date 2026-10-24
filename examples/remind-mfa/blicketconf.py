"""The blicket loader for remind-mfa runs."""

import pickle
from pathlib import Path
from typing import TYPE_CHECKING

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
