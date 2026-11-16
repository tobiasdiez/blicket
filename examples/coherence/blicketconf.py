"""The loader of the example: a run is a folder of CSV files, each a table of the run."""

import polars as pl

import blicket as bk


def load_run(selection: bk.RunSelection) -> tuple[dict[str, pl.DataFrame], bk.RunInfo]:
    """The tables of the run folder by the names of their files, ``flows`` for ``flows.csv``.

    ``value`` is read as a float whatever the file holds, so that it is a measure of every table:
    a column of whole numbers would be read as integers, which blicket takes for a dimension.
    """
    path = selection.path
    run = {
        file.stem: pl.read_csv(file, schema_overrides={"value": pl.Float64})
        for file in sorted(path.glob("*.csv"))
    }
    info = bk.RunInfo(id=path.name, profile="steel", fingerprint=bk.fingerprint(path))
    return run, info
