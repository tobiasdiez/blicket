"""REMIND output folders: what a folder says about its scenario, and the reporting of several
folders read into one run, the scenario as a column.

The mif reader, with its summation markers and its missing cells, and ``Run.rows``, on which the
dataset in ``blicketconf.py`` builds one quantity per variable and unit, hold for any IAMC-style
mif; ``Folder``, with ``cfg.txt`` and ``log.txt``, and the reading of R vector cells, ``c(a, b)``,
are REMIND's.
"""

import filecmp
import math
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml

KEYS = ["Scenario", "Region", "Variable", "Unit"]
DIMENSIONS = ["Scenario", "Region", "Year"]
WORLD = "World"
LAST_YEAR = 2100  # the report shows no later year
FIRST_HISTORICAL_YEAR = 1990  # the first year of history the report shows for H12 runs

# REMIND names an output folder by the scenario title and the time the run started.
_FOLDER_NAME = re.compile(r".+_(?P<started>\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2})")
# The git info at the top of log.txt, up to the next heading.
_GIT_INFO = re.compile(r"^===== git info =====$(?P<block>.*?)^====", re.MULTILINE | re.DOTALL)
_COMMIT = re.compile(r"^Latest commit: (\S+)", re.MULTILINE)
_BRANCH = re.compile(r"On branch (\S+)")
# A summation marker between two segments of a variable name: |+|, |++|, ...
_MARKER = r"\|\++\|"
_MISSING = ["NA", "N/A"]
# How close the numbers of an R vector cell, c(a, b, ...), must be, relative to the largest.
_AGREE = 1e-6
_FETCHED = "did the run finish, and was the file fetched (see the README)?"


@dataclass(frozen=True)
class Folder:
    """A REMIND output folder, ``<title>_<YYYY-MM-DD>_<HH.MM.SS>/``, as its ``cfg.txt`` and
    ``log.txt`` describe it.

    ``mapping`` is the name of the region mapping, ``H12`` for ``regionmappingH12.csv``;
    ``version`` is REMIND's ``model_version``; ``commit`` and ``branch`` are REMIND's, from the git
    info of ``log.txt``, ``None`` without one.
    """

    path: Path
    title: str
    mapping: str
    version: str
    commit: str | None
    branch: str | None

    @classmethod
    def read(cls, path: Path) -> Folder:
        """The folder at ``path``; raises ``ValueError`` when it is no directory or its
        ``cfg.txt`` lacks a setting, ``FileNotFoundError`` without a ``cfg.txt``."""
        if not path.is_dir():
            raise ValueError(
                f"{path} is not a directory; pass one REMIND output folder per scenario"
            )
        config_path = path / "cfg.txt"
        if not config_path.is_file():
            raise FileNotFoundError(
                f"{path} holds no cfg.txt; pass one REMIND output folder per scenario"
            )
        config = yaml.safe_load(config_path.read_text())
        missing = [k for k in ("title", "regionmapping", "model_version") if k not in config]
        if missing:
            raise ValueError(f"{config_path} sets no {', '.join(missing)}")
        commit = branch = None
        log = path / "log.txt"
        if log.is_file() and (info := _GIT_INFO.search(log.read_text(errors="replace"))):
            block = info["block"]
            commit = found[1] if (found := _COMMIT.search(block)) else None
            branch = found[1] if (found := _BRANCH.search(block)) else None
        stem = Path(config["regionmapping"]).stem
        return cls(
            path=path,
            title=str(config["title"]),
            mapping=re.sub(r"^regionmapping_?", "", stem) or stem,
            version=str(config["model_version"]),
            commit=commit,
            branch=branch,
        )

    @property
    def started(self) -> str:
        """The timestamp of the folder's name; raises ``ValueError`` when the name has none."""
        if named := _FOLDER_NAME.fullmatch(self.path.name):
            return named["started"]
        raise ValueError(
            f"{self.path} is not named <title>_<YYYY-MM-DD>_<HH.MM.SS>, which the run id of "
            "several folders needs; keep the names REMIND gives its output folders"
        )

    @property
    def mif(self) -> Path:
        """The reporting of the scenario, with the summation markers in the variable names."""
        return self.path / f"REMIND_generic_{self.title}.mif"

    @property
    def config(self) -> Path:
        return self.path / "cfg.txt"

    @property
    def historical(self) -> Path:
        """The historical data REMIND copied into the folder, the same for every scenario."""
        return self.path / "historical.mif"


@dataclass(frozen=True)
class Run:
    """The reporting of several REMIND scenarios and the historical data, as one run.

    ``scenarios`` holds the scenarios' mifs in their wide shape: ``Scenario``, ``Region``,
    ``Variable`` without the summation markers and ``Unit``, categorical, then one Float64
    column per year up to 2100, named by the year. ``historical`` holds ``historical.mif`` in
    the long shape: the data source in ``Model``, ``Region``, ``Variable``, ``Unit``, ``Year``
    from 1990 and ``value``, the missing values left out. ``titles`` are the scenario titles in
    the order of the folders; ``regions`` are ``World`` first, then the other regions sorted;
    ``sources`` are the data sources of the historical data, sorted.
    """

    scenarios: pl.DataFrame
    historical: pl.DataFrame
    titles: tuple[str, ...]
    regions: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def years(self) -> list[int]:
        return [int(column) for column in self.scenarios.columns if column.isdigit()]

    def rows(self, variables: Iterable[str]) -> pl.DataFrame:
        """The rows of ``variables`` in the long shape: ``Scenario``, ``Region``, ``Variable``,
        ``Unit``, ``Year`` and ``value``."""
        wide = self.scenarios.filter(pl.col("Variable").is_in(list(variables)))
        long = wide.unpivot(index=KEYS, variable_name="Year", value_name="value")
        return long.with_columns(pl.col("Year").cast(pl.Int64))


def read_run(folders: Sequence[Folder]) -> Run:
    """The mifs of ``folders`` and the historical data of the first.

    Raises ``FileNotFoundError`` when a folder lacks its mif or the first lacks
    ``historical.mif``, and ``ValueError`` when a mif holds another scenario than its folder's
    title or a variable twice. Warns on stderr when another folder lacks ``historical.mif`` or
    holds a different one.
    """
    frames = []
    for folder in folders:
        if not folder.mif.is_file():
            raise FileNotFoundError(f"{folder.path} holds no {folder.mif.name}; {_FETCHED}")
        frame = _read_mif(folder.mif, lambda year: year <= LAST_YEAR).drop("Model")
        found = frame["Scenario"].unique().sort().to_list()
        if found != [folder.title]:
            raise ValueError(
                f"{folder.mif} holds the scenario {', '.join(map(str, found))}, not "
                f"{folder.title} as {folder.config} names it"
            )
        if (twice := frame.select(KEYS).is_duplicated()).any():
            variable, unit = frame.filter(twice).select("Variable", "Unit").row(0)
            raise ValueError(
                f"{folder.mif} reports {variable} ({unit}) twice in a region, with the summation "
                "markers stripped"
            )
        frames.append(frame)
    scenarios = pl.concat(frames, how="diagonal")
    years = sorted((column for column in scenarios.columns if column.isdigit()), key=int)
    scenarios = scenarios.select(pl.col(KEYS).cast(pl.Categorical), *years)
    regions = scenarios["Region"].unique().to_list()
    historical = _read_historical(folders)
    return Run(
        scenarios=scenarios,
        historical=historical,
        titles=tuple(folder.title for folder in folders),
        regions=tuple(sorted(regions, key=lambda region: (region != WORLD, region))),
        sources=tuple(sorted(historical["Model"].unique().to_list())),
    )


def _read_historical(folders: Sequence[Folder]) -> pl.DataFrame:
    """``historical.mif`` of the first folder in the long shape, from 1990, without missing
    values; a warning for each other folder that lacks one or holds a different one."""
    path = folders[0].historical
    if not path.is_file():
        raise FileNotFoundError(f"{folders[0].path} holds no {path.name}; {_FETCHED}")
    for folder in folders[1:]:
        other = folder.historical
        if not (other.is_file() and filecmp.cmp(path, other, shallow=False)):
            print(f"warning: {other} is missing or differs; the run uses {path}", file=sys.stderr)
    frame = _read_mif(path, lambda year: year >= FIRST_HISTORICAL_YEAR).drop("Scenario")
    index = ["Model", "Region", "Variable", "Unit"]
    long = frame.unpivot(index=index, variable_name="Year", value_name="value")
    return long.drop_nulls("value").with_columns(
        pl.col(index).cast(pl.Categorical), pl.col("Year").cast(pl.Int64)
    )


def _read_mif(path: Path, keep: Callable[[int], bool]) -> pl.DataFrame:
    """The mif at ``path`` in its wide shape: ``Model``, ``Scenario``, ``Region``, ``Variable``
    with the summation markers stripped, ``Unit``, then the year columns that ``keep`` accepts as
    Float64.

    ``NA`` and ``N/A`` are missing. An R vector cell, ``c(a, b, ...)``, is its last number when
    the numbers agree; any other text is missing, and stderr says how many cells of which
    variables could not be read.
    """
    raw = pl.read_csv(path, separator=";", infer_schema_length=0, null_values=_MISSING)
    years = [column for column in raw.columns if column.isdigit() and keep(int(column))]
    frame = raw.select(
        "Model",
        "Scenario",
        "Region",
        pl.col("Variable").str.replace_all(_MARKER, "|"),
        "Unit",
        *(_number(pl.col(year)).alias(year) for year in years),
    )
    unread: Counter[str] = Counter()
    for year in years:
        cells = raw[year]
        odd = (cells.is_not_null() & frame[year].is_null()).arg_true()
        if odd.is_empty():
            continue
        values = [_vector(cell) for cell in cells.gather(odd).to_list()]
        frame = frame.with_columns(frame[year].scatter(odd, values))
        variables = frame["Variable"].gather(odd).to_list()
        unread.update(v for v, value in zip(variables, values, strict=True) if value is None)
    if unread:
        shown = ", ".join(f"{variable} ({count})" for variable, count in unread.most_common())
        print(
            f"warning: {path}: {unread.total()} cells could not be read and are missing: {shown}",
            file=sys.stderr,
        )
    return frame


def _number(cell: pl.Expr) -> pl.Expr:
    """The cell as a finite number, else null."""
    number = cell.cast(pl.Float64, strict=False)
    return pl.when(number.is_finite()).then(number)


def _vector(cell: str) -> float | None:
    """The last number of an R vector cell, ``c(a, b, ...)``, the one with the most digits in
    REMIND's mifs, when all its numbers are finite and agree within 1e-6 of the largest; ``None``
    for any other text."""
    if not (cell.startswith("c(") and cell.endswith(")")):
        return None
    try:
        numbers = [float(part) for part in cell[2:-1].split(",")]
    except ValueError:
        return None
    if not all(map(math.isfinite, numbers)):
        return None
    if max(numbers) - min(numbers) > _AGREE * max(map(abs, numbers)):
        return None
    return numbers[-1]
