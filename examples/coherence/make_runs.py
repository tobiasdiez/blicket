"""Write the example's two runs, runs/baseline and runs/changed: python make_runs.py

A run is the output of a made-up model of a steel cycle in three regions over the years 2020 to
2030, in Mt per year: steel is made from ore and from collected scrap, goes into use, leaves use
as scrap, and the scrap that is not recycled goes to landfill. The run folder holds four tables:

- flows.csv: the flows between the processes, a row per region, year and flow.
- stock.csv: the steel in use at the end of each year.
- end_use.csv: the share of each end use in the steel that goes into use.
- recycling.csv: the share of the collected scrap that is recycled, and the most it may be.

The baseline is coherent. The changed run is what a careless change to the model gives: its
recycling rate in East rises above the maximum, its end-use split in North has a negative share
in 2030, and its stock in South gains steel that no flow brings from 2026 on. Both carry what a
solver leaves: South makes steel from scrap alone, and its flow of ore is zero up to round-off.
"""

import csv
from pathlib import Path
from typing import NamedTuple

YEARS = range(2020, 2031)
MAXIMUM = 0.9  # of the recycling rate
END_USES = ["Construction", "Machinery", "Packaging"]


class Region(NamedTuple):
    """A region's model: each pair is the value in 2020 and its change per year."""

    out: tuple[float, float]  # the scrap leaving use
    into: tuple[float, float] | None  # the steel going into use; None: what the scrap yields
    rate: tuple[float, float]  # the recycling rate
    stock: float  # the steel in use in 2020
    split: tuple[float, float]  # the shares of construction and machinery in 2020


REGIONS = {
    "North": Region(out=(100, 2), into=(140, 1), rate=(0.70, 0.01), stock=3000, split=(0.52, 0.33)),
    "South": Region(out=(40, 1), into=None, rate=(0.85, 0), stock=1200, split=(0.45, 0.35)),
    "East": Region(out=(300, 10), into=(600, -5), rate=(0.60, 0.02), stock=8000, split=(0.6, 0.3)),
}

type Table = list[dict[str, str | int | float]]


def run(changed: bool) -> dict[str, Table]:
    flows: Table = []
    stock: Table = []
    end_use: Table = []
    recycling: Table = []
    for region, model in REGIONS.items():
        in_use = model.stock
        for step, year in enumerate(YEARS):
            cell: dict[str, str | int | float] = {"Region": region, "Year": year}

            rate = model.rate[0] + model.rate[1] * step
            if changed and region == "East":
                rate = model.rate[0] + 0.035 * step  # above the maximum from 2029 on
            rate = round(rate, 3)
            recycling += [
                cell | {"Series": "Recycling rate", "value": rate},
                cell | {"Series": "Maximum", "value": MAXIMUM},
            ]

            out = float(model.out[0] + model.out[1] * step)
            recycled = round(rate * out, 3)
            into = recycled if model.into is None else float(model.into[0] + model.into[1] * step)
            ore = round(into - recycled, 3)
            if model.into is None and step % 3 == 1:
                ore = -1e-14 * step  # zero, as a solver leaves it
            flows += [
                cell | {"From": "ore", "To": "steelmaking", "value": ore},
                cell | {"From": "collection", "To": "steelmaking", "value": recycled},
                cell | {"From": "steelmaking", "To": "use", "value": into},
                cell | {"From": "use", "To": "collection", "value": out},
                cell | {"From": "collection", "To": "landfill", "value": round(out - recycled, 3)},
            ]

            if step:  # the stock of 2020 is given
                in_use = round(in_use + into - out, 3)
                if changed and region == "South" and year >= 2026:
                    in_use = round(in_use + 0.3 * (year - 2025), 3)  # steel from nowhere
            stock.append(cell | {"value": float(in_use)})

            construction = round(model.split[0] - 0.005 * step, 3)
            machinery = round(model.split[1] + 0.005 * step, 3)
            shares = [construction, machinery, round(1 - construction - machinery, 3)]
            if changed and region == "North" and year == 2030:
                shares = [0.58, 0.45, -0.03]
            end_use += [
                cell | {"End use": use, "value": share}
                for use, share in zip(END_USES, shares, strict=True)
            ]
    return {"flows": flows, "stock": stock, "end_use": end_use, "recycling": recycling}


def write(directory: Path, tables: dict[str, Table]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (directory / f"{name}.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    runs = Path(__file__).parent / "runs"
    write(runs / "baseline", run(changed=False))
    write(runs / "changed", run(changed=True))
