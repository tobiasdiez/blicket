"""The blicket loader for REMIND runs, and the dataset the Blick builder charts."""

import functools
import itertools
import sys

import polars as pl
from remind import DIMENSIONS, Folder, Run, read_run

import blicket as bk


def load_run(selection: bk.RunSelection) -> tuple[Run, bk.RunInfo]:
    """Read one REMIND output folder per scenario into one run, the scenario as a column.

    The folders are taken in the order of their scenario titles, whatever the order given. The
    run id is the folder's name for one folder and ``<n> scenarios of REMIND <version>, latest
    <timestamp>`` for several, the timestamp of the newest folder's name; folders of different
    versions or commits name every version, with a warning. The profile is the region mapping,
    such as ``H12``, which all folders must share. The commit and branch are REMIND's when every
    folder's log names the same commit.
    """
    folders = sorted((Folder.read(path) for path in selection.paths), key=lambda f: f.title)
    for first, second in itertools.pairwise(folders):
        if first.title == second.title:
            raise ValueError(
                f"{first.path} and {second.path} are both of {first.title}; pass one folder per "
                "scenario"
            )
    if len({folder.mapping for folder in folders}) > 1:
        shown = ", ".join(f"{folder.path.name} {folder.mapping}" for folder in folders)
        raise ValueError(f"pass runs of one region mapping; these are of several: {shown}")
    run = read_run(folders)
    commits = {folder.commit for folder in folders}
    versions = sorted({folder.version for folder in folders})
    if len(folders) == 1:
        run_id = folders[0].path.name
    else:
        latest = max(folder.started for folder in folders)
        run_id = f"{len(folders)} scenarios of REMIND {', '.join(versions)}, latest {latest}"
        if len(versions) > 1 or len(commits) > 1:
            shown = ", ".join(f"{f.path.name} {f.version} at {f.commit}" for f in folders)
            print(f"warning: the folders are of different REMIND commits: {shown}", file=sys.stderr)
    same = len(commits) == 1
    files = [
        *(folder.mif for folder in folders),
        folders[0].historical,
        *(folder.config for folder in folders),
    ]
    info = bk.RunInfo(
        id=run_id,
        profile=folders[0].mapping,
        fingerprint=bk.fingerprint(*files),
        commit=folders[0].commit if same else None,
        branch=folders[0].branch if same else None,
    )
    return run, info


def dataset(run: Run) -> bk.Frames:
    """Every variable of the scenarios for the Blick builder of ``blicket dev``.

    One quantity per variable and unit, named by the variable, with the unit in brackets for a
    variable reported in two units; the name carries the unit only while the variable has two,
    so a builder URL that names such a quantity is tied to runs that report both. The quantities
    are grouped by the first segment of the name, such as ``Emi`` or ``FE``. None is additive:
    summing over regions would count World twice, and summing over scenarios means nothing.
    """
    frames = bk.Frames(
        dimensions=[
            bk.Dimension(name="Scenario", dtype="string", values=list(run.titles)),
            bk.Dimension(name="Region", dtype="string", values=list(run.regions)),
            bk.Dimension(name="Year", dtype="integer", values=run.years),
        ]
    )
    pairs = run.scenarios.select(pl.col("Variable", "Unit").cast(pl.String)).unique(
        maintain_order=True
    )
    twice = set(pairs.filter(pl.col("Variable").is_duplicated())["Variable"].to_list())
    for variable, unit in pairs.iter_rows():
        frames.add(
            f"{variable} [{unit}]" if variable in twice else variable,
            functools.partial(_table, run, variable, unit),
            unit=unit,
            dimensions=DIMENSIONS,
            additive=False,
            group=variable.partition("|")[0],
        )
    return frames


def _table(run: Run, variable: str, unit: str | None) -> pl.DataFrame:
    """The rows of ``variable`` in ``unit``, or without a unit when ``unit`` is ``None``."""
    rows = run.rows([variable]).filter(pl.col("Unit").eq_missing(unit))
    return rows.select(*DIMENSIONS, "value")
