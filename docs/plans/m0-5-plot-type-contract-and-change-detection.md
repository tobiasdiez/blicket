# M0.5 Change detection: the diff half of the plot type contract

Status: plan, 2026-10-24, revised the same day after M1 (commit `fe4d2dd`), which took the
`controls` half of the contract and the `digits` cleanup out of this task, and again after an
independent review that prototyped the routine on the example builds. The deferred draft's
review findings are applied here (list at the end). Fifth task of [m0-tasks.md](m0-tasks.md);
companion to [architecture.md](../architecture.md), "Plot type contract" and "Change detection, as
implemented by the built-in diff routine"; where this plan refines a detail, it says so.

## Goal

Two tables of one Blick can be compared from Python: the `schema` diagnostics the architecture
defines, a bounded magnitude that reads like the chart, and the row that moved most, which the
overview, the terminal summary and the report will need. The four built-ins implement `diff`
through one shared routine. Nothing is stored and no command changes: matching the Blicks of two
builds (`new`, `removed`, `error`, aliases) comes with the store and `blicket diff` in M0.6, the
baselines, `check`, the reports and the viewer's comparison toggle in M0.7. The task ends with the
routine measured on the three example runs.

## The flows this task enables

1. **Two tables of one Blick, compared from Python.** The example runs 28 and 31 are unchanged
   reruns, run 34 scaled `collection_rate` by 0.9; `production_by_source` is the one Blick that
   sees it.

   ```python
   import polars as pl
   from blicket.plots import builtin
   baseline = pl.read_parquet("<build of run 28>/blicks/flows/production_by_source.parquet")
   current = pl.read_parquet("<build of run 34>/blicks/flows/production_by_source.parquet")
   change = builtin("stacked_area").diff(baseline, current, mapping, panels=[])
   change.flags       # frozenset(): no column or value appeared or vanished
   change.magnitude   # 0.021: the recycled flow moved by a fiftieth of the largest stack
   change.where       # {"Flow": "Primary", "Time": 2100, "Region": "SSA"}: the row that moved most
   ```

   `panels=[]` because the Blick splits by Region with a shared y axis, so the whole table is
   one panel. The core (M0.6) sets `value` when the magnitude exceeds the Blick's tolerance.
   Between 28 and 31 every table gives magnitude 0; between 28 and 34, every table but this one
   gives 0 or about 1e-16 (`production_by_polymer` and `production_trade_consumption`), far
   below any tolerance.

2. **A Blick author changes a transformation, or adds a scenario**: `diff` gives the magnitude
   with the row that moved most, or `schema` with the dimension values that appeared, with the
   magnitude of the rows both tables have. A dropped row (a zero that a sparse output leaves out)
   is a value change, not a schema change.

3. **M0.6 and M0.7 build on it**: matching the Blicks of two builds, the terminal summary with
   counts per flag and the top movers by magnitude, the comparison file next to the manifest, the
   overview that colours the cards and opens a Blick at `where`.

## Facts the plan rests on (checked 2026-10-24)

- The manifest (spec 0.2) records per built Blick its `definition` (plot type, mapping,
  `independent_y`, `tolerance`; aliases live on the entry), `columns` (dimensions with dtype and
  values in display order; measures), the derived `controls` (`filter` or `split`, with a default)
  and `data`, the Parquet path. Stored tables come from `tables.check`: dimension columns first,
  rows sorted by them, dtypes normalised (`Int64`, `Datetime("us")`, strings for enums), float
  measures, every dimension combination unique, at least one dimension (`x` is required). NaN is
  null; ±inf passes `check` today.
- `BuiltinPlotType.controls` turns every unbound dimension into a filter; `Blick._controls_for`
  applies the author's `controls=` and `defaults=`. Every example Blick binds or splits all its
  dimensions except `scenario_rates`, which filters on `Parameter`. `independent_y` is a Blick
  option; the viewer draws split panels with a shared y axis unless it is set.
- `PlotType.diff(baseline, current, mapping, controls)` is abstract; the built-ins raise
  `NotImplementedError`. `plots/_base.py` reaches back into `model.py` under `TYPE_CHECKING` for
  `TableSchema`, because `model.py` imports `plots`.
- Measured by the plan reviews on the example (a prototype of the routine; builds of runs 28,
  31 and 34 at spec 0.2 exist under the example's `.blicket/build/` since the second review): a
  diff on the largest table (24k rows) takes 8 to 10 ms, the ten Blicks together 0.1 s including
  the Parquet reads; runs 28 and 31 deviate by 0 everywhere; between 28 and 34 only
  `production_by_source` moves, by 0.02096 under a shared scale over the Region split (0.041 with
  a scale per facet, 0.10 against the series' own scale), 2,622 of its 3,624 rows beyond 1e-5;
  the two other tables that depend on the collection rate differ by at most 1.1e-16 and the
  remaining seven are byte-identical. The Primary and Recycled changes at SSA 2100 are
  bit-identical in size, since production is conserved, so the row that moved most is a tie. ε is
  untested by the data: no example Blick filters into panels that are small against the whole;
  the smallest region panel is 2.7e-2 of the Blick-wide scale.
- `polars.DataFrame.join(how="full")` keeps no row order unless `maintain_order` says so and does
  not coalesce the key columns unless asked; `validate="1:1"` raises on duplicate keys; a key
  column of another dtype raises for string against integer but silently casts Int32 to Int64;
  `on=[]` raises. (`arg_max` on a filtered column returns the last maximum when polars flags the
  column as sorted, as the first review found; `where` filters for the maximum instead.)
- A module that imports `blicket.comparison` from a built-in plot type at import time cycles
  (`comparison` → `manifest` → `model` → `plots`), verified; a routine that imports only polars
  and the shared types does not.
- The trade sign convention asked for in M0.3 exists since then: net imports are imports minus
  exports, negative for net exporters (`flows/production_trade_consumption`).

## Approach

### A leaf module for the shared types

`schema.py` holds `Dimension`, `Measure`, `TableSchema`, `Control`, `ControlKind`, and the new
`Flag` and `Change`, with no blicket imports. `model.py` and `plots/_base.py` import it; the
`TYPE_CHECKING` reach-back goes; `blicket/__init__.py` re-exports `Change` next to `Control`. The
manifest shape does not change.

### `Change`, the result of one Blick's diff

```python
type Flag = Literal["new", "removed", "schema", "value", "error"]   # the architecture's set, typed once

class Change(BaseModel):
    flags: frozenset[Flag] = frozenset()       # serialised in the order above; empty means unchanged
    magnitude: float | None = None             # None when no row was compared
    columns_added: dict[str, str] = {}         # column → dtype, only in the current table
    columns_removed: dict[str, str] = {}
    values_added: dict[str, list[Any]] = {}    # dimension → values only the current table has
    values_removed: dict[str, list[Any]] = {}
    where: dict[str, Any] | None = None        # the dimension values that moved most; None at 0
```

`diff` sets `schema`; the core sets `value` when the magnitude exceeds the Blick's tolerance
(tolerance is below 1 and the magnitude is bounded by 1, so the two agree by construction, and a
project plot type cannot contradict its own magnitude), and `new`, `removed` and `error` for the
Blicks it cannot diff (M0.6). The defaults let the core build those three without diagnostics. No
formula version: the comparison file (M0.6) records the blicket version that wrote it, which
names the formula.

### `diff(baseline, current, mapping, panels) -> Change`

The architecture's signature with one refinement decided here: `panels` replaces `controls`, the
dimensions whose value combinations define a panel. The core derives them, since the panel layout
is the core's (splits are controls it derives for every plot type, `independent_y` is a Blick
option): the filter dimensions, plus the split dimensions when the Blick sets `independent_y`,
because then each facet has its own axis and its own scale. This matches how the viewer resolves
the y scales.

The built-ins share `plots/_diff.py`'s `compare(baseline, current, panels, stacked_by=None)`,
which imports only polars and `schema.py` (anything that reaches `manifest` or `model` would
cycle through `plots`); the two stacked types pass their colour column as `stacked_by`, the
others nothing. The routine:

1. **Columns.** Dimensions are the non-float columns, measures the float columns, compared by name
   and dtype. Any difference is `schema` with the columns in `columns_added`/`columns_removed`,
   magnitude `None`, no rows compared: a changed shape is for the author to look at, not a
   number. Dtypes are compared before the join, because polars casts some mismatches silently
   and raises on others.
2. **Keys.** Both tables get a marker column, then a full outer join on the dimension columns with
   coalesced keys, `maintain_order="left_right"` and `validate="1:1"` (the check made keys
   unique). Per dimension, the values present in only one table go into
   `values_added`/`values_removed`, the level the architecture's diagnostics name; either
   non-empty sets `schema`, and the rows carrying such a value are left out of the comparison,
   as the architecture asks (the magnitude is computed on the common keys). Every other row is
   compared, including a row present on one side only: its values exist on both sides, so it is
   a dropped or added zero of a sparse output, and the missing side counts as null (rule 4).
3. **Scale.** S per measure is the largest |value| over both whole tables. Per panel (every
   combination of the `panels` columns; the whole table when `panels` is empty) and measure, s is
   the largest |value| over both tables' rows in the panel, floored at ε·S with ε = 1e-6. For a
   stacked type the values are first summed per table, per group of all dimension columns except
   `stacked_by`, positives and negatives apart, and s is the largest of max(positive sum,
   |negative sum|) over the groups of both tables, so negative layers cannot cancel a stack to
   nothing. S = 0 means both tables are zero or null everywhere: every deviation is 0.
4. **Deviation.** Per compared row and measure, |current − baseline| / s; a null on one side and a
   value on the other counts |value| / s; null on both sides is 0. For a stacked type the
   positive and the negative stack sums of each group are compared the same way, so a change
   that moves every layer together is as large in the magnitude as the stack top's move on the
   chart (verified: +5 % on every layer of `production_by_polymer` gives 0.048 with the sums and
   0.009 without; a sign flip of four equal layers gives 1 instead of 0.5). The magnitude is
   min(1, the largest deviation over rows, groups and measures), computed also when `schema` is
   set; `where` is the dimension values of the first row (the joined rows are sorted by the
   dimensions) or group that reached it, so a viewer can set the filters and find the panel; it
   is set whenever the magnitude is above 0, and below the tolerance it names noise. No compared
   rows: magnitude `None`.
5. **Per panel, not per series.** Inside a panel every series shares one axis, so a 10 % change of
   a small series is as small in the magnitude as on the chart (the net-imports case of
   `production_trade_consumption`; a per-series scale would overrate what the eye cannot see).

`tables.check` gains one rule: a measure with an infinite value is a table error (inf − inf
would hide a change, and a chart cannot show it either).

### Not in this task, decided here

- Matching the Blicks of two builds (`new`, `removed`, `error`, aliases) stays in M0.6 with its
  first user, `blicket diff`: the review ran this task's measurement with a twenty-line loop, and
  M0.7's per-Blick fallback to older baselines means the shape of that result is M0.7's to
  decide. Cases for M0.6, recorded in the task list: a baseline entry in error with a fine current
  one (`new`), entries without an id, two error entries sharing a claimed id, and
  `manifest.build.incomplete` as the source of the `removed` rule.
- A colour dimension with many values offered as a split, and a plot type's veto of a split
  request: viewer features for the task that adds the comparison toggle (M0.7) or M4's first
  non-faceting plot type; noted in the task list.
- Dimensions functionally determined by others (`determined_by`): the detection misfires on 1:1
  pairs and single-valued dimensions and finds nothing in the example; it waits for a project that
  needs it.
- Deriving the plot factories from the channel declarations (`PlotType.__call__`): a refactor for
  M4's benefit, done when the first project plot type wants a factory.

## Affected areas

- New: `plots/_diff.py` (`compare`), `schema.py`.
- Changed: `model.py` and `plots/_base.py` (import the leaf; `diff` with `panels`),
  `plots/stacked_area.py` and `plots/bar.py` (`stacked_by`), `tables.py` (infinite measures),
  `__init__.py` (exports), README (a short paragraph on `diff` with the Python call),
  `docs/architecture.md` (dated sentences: `panels` instead of `controls` in `diff`, `value` set
  by the core from the magnitude, the stacked sums compared, `where`), `docs/plans/m0-tasks.md`
  (the M0.6 cases and the deferred items noted).
- `examples/remind-mfa/`: nothing; its builds are the measurement.

## Testing

- `compare`, on small generated tables: identical tables give no flags and magnitude 0; scaling both
  tables by any nonzero factor leaves the magnitude unchanged; a change crossing zero counts both
  sides (0.4 → −0.4 at scale 1 gives 0.8); a value added in one table gives `schema` with the value
  named and a magnitude from the rows both have; a row dropped without a new value counts as null
  against its value; nulls on one side count, on both sides do not; an all-zero baseline panel with
  a 1e-9 ripple at S = 1 gives a magnitude of 1e-3 (the ε floor); both tables all zero give 0; empty
  tables give no flags and magnitude `None`; a stacked panel with +5 and −5 layers has scale 5; a
  sign flip of equal layers of a stack gives 1; panels come from `panels`; `where` names the first
  row of a tie in the stored order; differing columns or a dtype change of a key column give
  `schema` and magnitude `None`; the magnitude is bounded by 1.
- `diff` on each built-in: the stacked types compare the stack sums as well, the others do not
  (one table where it matters).
- `check` rejects an infinite measure.
- The measurement below, by hand, recorded in the plan.

## Measurement, recorded 2026-10-24

`diff` of the built-ins on every Blick of the example, through a scratch loop over two manifests:
the current build's mapping and `BlickEntry.panels` (only `drivers/scenario_rates` has one, its
`Parameter` filter; no Blick sets `independent_y`), the Parquet tables read with polars. Run 28 is
build `bfa7f61fc79b65c2`, 31 `9bb88a679a29a905`, 34 `34247dcb88fd54c3`. No flags anywhere.

| Blick | rows | 28 vs 31 | 28 vs 34 | `where`, 28 vs 34 |
|---|---:|---:|---:|---|
| `drivers/gdp_per_capita` | 1,812 | 0 | 0 | |
| `drivers/scenario_rates` | 10,872 | 0 | 0 | |
| `drivers/polymer_splits` | 1,248 | 0 | 0 | |
| `flows/consumption_by_end_use` | 14,496 | 0 | 0 | |
| `flows/production_by_polymer` | 23,556 | 0 | 1.18e-16 | `{"Time": 2051, "Region": "CHA"}`, a stack |
| `flows/production_by_source` | 3,624 | 0 | 0.020961 | `{"Flow": "Primary", "Time": 2100, "Region": "SSA"}` |
| `flows/production_trade_consumption` | 7,248 | 0 | 1.14e-16 | `{"Flow": "Production", "Time": 2034, "Region": "CHA"}` |
| `flows/end_use_split` | 14,496 | 0 | 0 | |
| `stocks/use_by_region` | 1,812 | 0 | 0 | |
| `stocks/use_by_end_use` | 1,208 | 0 | 0 | |

As expected: `production_by_polymer` reaches 1.18e-16 and `production_trade_consumption` 1.14e-16,
about 1e-16 and eleven orders of magnitude below the default tolerance. The rows of
`production_by_polymer` differ by at most 2.9e-17 of the highest stack, its stack sums, which the
prototype did not compare, by 1.18e-16, so its `where` names a stack. `where` is `None` wherever the
magnitude is 0. The Primary/Recycled tie in `production_by_source` resolves to Primary, the first in
the stored order. Wall time of the ten diffs, over eight runs after the second review: 54 to 62 ms
(the largest table, 23,556 rows, 10 to 12 ms; the prototype took 8 to 10 ms without the stack
comparison and the checks of the arguments), plus 21 to 25 ms for the twenty Parquet reads. The
magnitudes and `where` are the same after both reviews' changes (scale over the compared rows, one
measure, values scaled by a power of two).

## Decided by Tobias on 2026-10-24

1. **Panels follow `independent_y`**: with it set, each split facet is its own panel for the
   magnitude; without it, split facets share the scale, as they share the axis.
2. **ε = 1e-6** as the floor of a panel's scale relative to the Blick-wide scale, chosen without
   data; revisit when a Blick with very unequal filter panels exists.
3. **Per-panel scale**, not per series, as the architecture reasons.

## Decisions taken here, not asked

- `diff` takes `panels` instead of `controls`: the core defines panels; the plot type scales and
  compares inside them. It takes no tolerance: the core sets `value` from the magnitude.
- Differing columns are `schema` without a magnitude; `columns_added`/`columns_removed` and
  `values_added`/`values_removed` are separate fields (no `"columns"` key that a dimension could
  be called). A row missing on one side without a new dimension value is a value change.
- One `where` instead of top panels; no formula version (the comparison file records the blicket
  version).
- `schema.py` is the leaf module for the shared types; the routine lives in `plots/_diff.py`.

## How the deferred draft's review findings were applied

1 panel definition decided with `independent_y` (open question 1); 2 `where` replaces `top_panels`;
3 marker columns, coalesced keys, `validate="1:1"`; 4 degenerate scales and infinite measures
handled; 5 `determined_by` deferred; 6 the stacked rule groups by every dimension but `stacked_by`;
7 dtypes compared, no join on mismatched keys; 8 done in the digits commit; 9 flags typed once,
separate fields, `RowCounts` defined; 10 the factory refactor deferred, the sign convention exists;
11 done in M1 (spec 0.2, `controls` on the entry); 12 `schema.py`; 13 `tolerance` left out of `diff`
after the second review (the core sets `value`, no row count); 14 ε kept at 1e-6 and said to be
untested; 15 `splits` not added, no formula version, one `where`; 16 the current build's controls
and tolerance are used; 17 the measurements are in the facts.

## Deviations

- `compare(baseline, current, y, panels, stacked_by=None)` takes the measure column: every
  built-in has one measure channel, so the other columns are the dimensions, and the measure loop
  and the branch for a table without dimensions have no caller.
- The scales (per panel, per stack and Blick-wide) use the compared rows only, as the
  architecture's "common keys" asks: a row that carries a value only one table has neither counts
  nor sets a scale (decided in the first review; the plan had the whole tables).
- No marker columns: a row that one table lacks and a null measure count alike, so the join's
  nulls suffice, and the values only one table has come from the dimension columns. The joined
  rows are sorted by the dimensions, the stored order, rather than kept in the join's order.
- `where` is `None` when the magnitude is 0 and set whenever it is above 0. It names the first
  row whose deviation is the largest of the rows, unless the largest stack deviation exceeds that
  by more than 1e-9 relative, the rounding of a sum; then the named row can sit up to 1e-9
  relative below the magnitude. A stack's `where` leaves out the stacked column.
- A column whose dtype changed is in both `columns_added` and `columns_removed`; the types are
  the manifest's words (`integer`, `float`, ...) through `dimension_type`, which moved from
  `tables.py` to `schema.py` and is public there, so Int32 against Int64 reads `integer` twice.
- `compare` checks its arguments: polars frames, `panels` a list, `y` a float column beside at
  least one dimension, `panels` and `stacked_by` dimension columns of the current table and not
  the same (a baseline that lacks them is `schema`), unique dimension values in each table (the
  join's 1:1 validation); NaN counts as null.
- The values are scaled by a power of two near the largest compared value before any sum, so
  that stacks of values near 1e308 do not overflow and subnormal values keep their ratios
  (polars divides through the reciprocal, which overflows for a subnormal divisor).
- The panel rule lives on the entry, `BlickEntry.panels`, rather than in the core's comparison.
- `Flag` is a plain `Literal` alias like `ControlKind`, not a `type` statement as sketched above.
- `Change` is frozen and its magnitude validated to [0, 1]; the core sets `value` with
  `model_copy`.
- The stacked types say so with a class attribute, `BuiltinPlotType.stacked`, and the shared
  `diff` passes their `color` column as `stacked_by`, instead of overriding `diff` twice.
