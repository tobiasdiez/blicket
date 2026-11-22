"""A model checkout for the tests, whose tables are computed when a transformation asks for one,
from ``values.txt`` in the run folder, read afresh each time. A test can hold a table behind a
gate, so that the transformation asking for it waits until the test opens the gate.

The run's Blicks are expensive unless the environment sets ``BLICKET_TEST_CHEAP``; the Blicks
``steel/shares`` and ``plastics/validation`` say for themselves that they are cheap and
expensive. The project itself is a run too, ``checkout``, when ``runs`` picks it with ``.``. The
run has no dataset unless the environment sets ``BLICKET_TEST_DATASET``, which gives one whose
table is the run's trade, computed when the builder first asks for it.
"""

import os
import threading
from pathlib import Path

import polars as pl

import blicket as bk

CHEAP = "BLICKET_TEST_CHEAP"
WITH_DATASET = "BLICKET_TEST_DATASET"
YEARS = [2020, 2021, 2022]
WAIT = 10  # seconds a gate stays closed at most, so that a test that fails cannot hang


class Gate:
    """A table held back: ``reached`` once a transformation asks for it, which then waits until
    ``open``."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.opened = threading.Event()

    def open(self) -> None:
        self.opened.set()


class Checkout:
    """The run: the tables of the folder ``path``, computed when asked for; ``asked`` lists the
    tables asked for, in order."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.asked: list[str] = []
        self._gates: dict[str, Gate] = {}

    def hold(self, name: str) -> Gate:
        """Hold the table ``name`` back from now on, until the gate returned is opened."""
        gate = self._gates[name] = Gate()
        return gate

    def table(self, name: str) -> pl.DataFrame:
        self.asked.append(name)
        if (gate := self._gates.get(name)) is not None:
            gate.reached.set()
            if not gate.opened.wait(WAIT):
                raise TimeoutError(f"the table {name} was held for {WAIT} s")
        values = [float(v) for v in (self.path / "values.txt").read_text().split()]
        if name == "production":
            return pl.DataFrame(
                {
                    "region": ["CN"] * len(YEARS) + ["EU"] * len(YEARS),
                    "year": YEARS * 2,
                    "value": [2 * v for v in values] + values,
                }
            )
        if name == "trade":
            return pl.DataFrame({"year": YEARS, "value": values[::-1]})
        if name == "shares":
            return pl.DataFrame({"year": YEARS, "value": [v / sum(values) for v in values]})
        raise KeyError(name)


def load_run(selection: bk.RunSelection) -> tuple[Checkout, bk.RunInfo]:
    path = selection.path
    info = bk.RunInfo(
        id="checkout" if (path / "pyproject.toml").is_file() else path.name,
        profile="test",
        fingerprint=bk.fingerprint(path / "values.txt"),
        expensive=not os.environ.get(CHEAP),
    )
    return Checkout(path), info


def dataset(run: Checkout) -> bk.Frames | None:
    """No dataset, as a run of expensive Blicks usually has none: its dimensions are known once
    its tables are; or, with ``BLICKET_TEST_DATASET``, the trade, its dimension given."""
    if not os.environ.get(WITH_DATASET):
        return None
    frames = bk.Frames(dimensions=[bk.Dimension(name="year", dtype="integer", values=YEARS)])
    frames.add("trade", lambda: run.table("trade"), dimensions=["year"], unit="t per year")
    return frames
