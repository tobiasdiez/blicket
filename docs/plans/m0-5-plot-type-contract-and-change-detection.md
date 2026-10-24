# M0.5 Plot type contract and change detection

Status: plan, 2026-10-24, **deferred the same day**: Tobias chose to build the viewer (M1) before
the comparison. The plan review's findings are appended below and are applied when the task
resumes; the body is otherwise the draft as reviewed. Fifth task of [m0-tasks.md](m0-tasks.md),
building on M0.3 (commit `fe60daf`; M0.4 was dropped). Companion to [architecture.md](../architecture.md), sections "Plot
type contract" and "Change detection, as implemented by the built-in diff routine"; where this
plan fills in or refines a detail, it says so.

## Goal

The build-time half of the plot type contract exists and the four built-ins implement it through
one shared routine: `controls` derives the controls of a Blick from its table, and the build
records them in the manifest; `diff` compares two tables of one Blick and returns the flags, the
bounded magnitude and the diagnostics the overview and the report need. Nothing is compared in a
build yet (that is M0.6 and M0.7); this task makes the comparison callable and tested, and
measures it on the example builds.

## The flow this task enables

1. A Blick author writes nothing new. In the manifest of a build, each built Blick now carries its
   controls, derived from the table and the plot mapping:

   ```json
   "controls": [{"dimension": "Region", "kind": "split", "default": null},
                {"dimension": "Driver Scenario", "kind": "filter", "default": "SSP2"}]
   ```

   Dimensions bound to a channel (`x`, `color`, ...) have no control; an unbound dimension is a
   filter unless the Blick asked for `split`; a dimension whose value is fixed by another
   dimension's value (a unit column that follows the variable) is hidden, since filtering the
   determining dimension filters it too.

2. From Python, two tables of one Blick are compared:

   ```python
   change = blick.plot.plot_type.diff(baseline, current, mapping, controls, tolerance=1e-5)
   change.flags        # {"value"}; {"schema", "value"}; or empty for unchanged
   change.magnitude    # 0.10 for the example's production_by_source between run 28 and run 34
   change.top_panels   # [{"values": {"Region": "CHA"}, "deviation": 0.10}, ...]
   ```

3. M0.6 writes `Change` into the comparison file and prints the counts and top movers; M0.7 ranks
   the overview by `magnitude`. Both read `tolerance` from the manifest's `config`.

## Facts the plan rests on

- The architecture decides the flag set (`new`, `removed`, `schema`, `value`, `error`), the
  tolerance rule (a row is *same* when |current − baseline| / s ≤ tolerance, with s the panel
  scale), the panel (one combination of filter-dimension values; split dimensions share a scale
  inside the panel), the panel scale (the maximum absolute value in the panel across both tables,
  per measure, floored at ε times the Blick-wide scale), the stacked rule (s = max over x of the
  larger of the positive and the negative stack), the bounded magnitude (min(1, max deviation)),
  and that the magnitude is always computed on the common keys. `new`, `removed` and `error` are
  set by the comparison driver, which has both manifests; `diff` sees two tables and sets `schema`
  and `value`.
- M0.4 was dropped, so stored tables are not rounded and carry no zero floor: the tolerance alone
  absorbs noise. Measured: rerun noise reaches 1.3e-15 of a column's scale in the example; the
  changed run moves `flows/production_by_source` by 10 % (recycled) and 2.1 % (primary) and the
  two production tables by at most 3.9e-16 relative. With no rounding, the `digits` config key
  and its rule `tolerance >= 10^(1 - digits)` have no job.
- `tables.check` leaves the frame with dimension columns first (in `dims=` order) and rows sorted
  by the dimension columns; the schema records each dimension's values in display order. The
  Blick's `controls=` keys are verified to be unbound dimensions, its `defaults=` keys to be
  dimensions, and a `defaults` value absent from this run's table is a warning.
- The `PlotType` base has abstract `controls(schema, mapping)` and `diff(baseline, current,
  mapping, controls)`; the built-ins raise `NotImplementedError` for both.
- `flows/production_trade_consumption` puts production (5e8) and sign-crossing net imports
  (−9e7) in one panel, so a panel-relative tolerance makes a 10 % change of net imports a 1.8 %
  deviation (m0-tasks.md asks for a decision).

## Approach

### Types, in `model.py` (they go into the manifest and the comparison file)

```python
class Control(BaseModel):
    dimension: str
    kind: Literal["filter", "split"]
    default: Any | None = None            # a value of the dimension; None for split

class Change(BaseModel):
    flags: list[Literal["schema", "value"]]
    magnitude: float | None               # None when the tables share no dimension columns
    added: dict[str, list[Any]]           # dimension → values only the current table has
    removed: dict[str, list[Any]]         # dimension → values only the baseline has
    rows: Counts                          # common, changed, added, removed
    top_panels: list[Panel]               # up to three: {"values": {dim: value}, "deviation": f}
    version: int = 1                      # the magnitude formula
```

`Dimension` in the schema gains `determined_by: str | None`: the name of another dimension whose
value fixes this one, found at check time (for every pair of dimensions a, b: b is determined by a
when every value of a goes with exactly one value of b; the smallest-cardinality determiner wins).
It is computed from the table, so `controls(schema, mapping)` keeps the architecture's signature
and the viewer gets the information too.

### `controls(schema, mapping) -> list[Control]`

One implementation on the built-ins' base, usable by project plot types that want the default:
every dimension not bound to a channel and not determined by another unbound dimension becomes a
`filter` control whose default is the dimension's first value in display order. The core, not the
plot type, applies the Blick's wishes afterwards: `controls={dim: "split"}` turns a filter into a
split when the plot type's `splits: ClassVar[bool]` allows it (true for all four built-ins; a
plot type without facets makes the request a table error), `defaults={dim: value}` replaces the
default. A dimension with a single value still gets a filter control (the viewer may hide it).

The build calls this for every built Blick and records the list in `BlickEntry.controls`
(additive to the manifest). A `split` request on a determined dimension is a table error, since
the dimension cannot be split independently.

### `diff(baseline, current, mapping, controls, tolerance) -> Change`

The architecture's signature plus `tolerance`, which the plot type needs and the caller has (per
Blick, else the project's). One shared routine in `blicket/comparison.py`, `compare(baseline,
current, dims, measures, panels, tolerance, stacked_by=None)`, which the built-ins call with the
roles taken from the two frames and the panel dimensions taken from the filter controls; the
stacked types pass their colour dimension as `stacked_by`.

1. **Columns.** The dimension columns are the non-float columns, the measures the float columns
   of each table (the stored tables come from `check`, so the roles are reliable). If the two
   tables disagree on either set, the result is `schema` with the differing column names in
   `added`/`removed` under the key `"columns"`, `magnitude` None, no rows compared: a changed
   shape is a change the author has to look at, not a magnitude.
2. **Keys.** A full outer join on the dimension columns. Rows only in the current table are
   added, only in the baseline removed; `added`/`removed` list, per dimension, the values that
   occur in only one table (the value level the architecture's diagnostics name). Either set
   non-empty sets `schema`.
3. **Panels.** The filter-control dimensions define panels; every other dimension (bound, split,
   determined) lies inside a panel. With no filter control the whole table is one panel.
4. **Scale.** Per measure and panel, s = max |v| over the panel's common rows in both tables,
   floored at ε × S with S the measure's maximum |v| over both whole tables and ε = 1e-6. For a
   stacked plot type, the values inside a panel are first summed per x and sign over the
   `stacked_by` dimension, and s is the maximum over x and both tables of max(sum of positives,
   |sum of negatives|), so negative flows cannot cancel a stack to zero. ε keeps an all-zero
   panel from ranking a 1e-16 ripple as a total change while still judging a small panel on its
   own scale (a region a thousandth of the world is measured against itself, not against the
   world, until it falls below a millionth).
5. **Deviation.** Per common row and measure, |current − baseline| / s; a null on one side and a
   value on the other counts as |value| / s; null on both sides is same. A row is changed when any
   measure's deviation exceeds `tolerance`; `value` is set when any row is changed. The magnitude
   is min(1, the largest deviation over rows and measures), computed on the common rows also when
   `schema` is set. `top_panels` are the three panels with the largest deviation, with their
   filter values, for the overview to open a changed Blick where it changed most.
6. **Per panel, not per series.** Within a panel all series share one axis, so a 10 % change of
   a small series is as small on the chart as in the magnitude. Decided here with the
   `production_trade_consumption` case in view; a per-series scale would overrate changes the eye
   cannot see.

`version = 1` names this formula; M0.6 writes it into the comparison file, so a later formula
change is visible in old comparisons.

### Cleanup: `digits` goes

The config loses `digits` and the `tolerance >= 10^(1 - digits)` rule (a project that still sets
`digits` gets the unknown-key error with the usual hint); the manifest's `config` block holds
`tolerance` only; a per-Blick `tolerance` must be positive and below 1. The README's config table
and the architecture's tolerance paragraph are amended with a dated sentence: no rounding, no
zero floor, the tolerance alone absorbs noise.

### Measurement, recorded here when the task ends

With the Python API, on the example builds: `diff` of every Blick between the two unchanged
reruns (expect no flags, magnitude 0 for all ten), and between run 28 and the changed run 34
(expect `value` on `flows/production_by_source` with magnitude about 0.10 and the top panels by
region, no flags on the two production tables whose differences are 1e-16 ≪ tolerance, no flags
elsewhere). Record the magnitudes and the wall time of a diff on the largest table (24k rows).

## Affected areas

- New: `comparison.py`.
- Changed: `plots/_base.py` (`splits`, the shared `controls` and `diff`, the stacked types'
  `stacked_by`), `plots/stacked_area.py` and `bar.py` (declare stacking), `model.py` (`Control`,
  `Change`, `Dimension.determined_by`, `BlickEntry.controls`), `tables.py` (determined-by
  detection; the split-on-determined check), `builder.py` (controls recorded per Blick),
  `config.py` and `manifest.py` (`digits` removed), `_validation.py` (per-Blick tolerance bounds),
  `__init__.py` (exports `Control`, `Change`), README, `docs/architecture.md` (two dated
  sentences: `digits` gone; `diff` takes `tolerance`).
- `examples/remind-mfa/`: nothing; its builds are the measurement.

## Testing

- Properties of `compare`, each on small generated tables: identical tables give no flags and
  magnitude 0; scaling both tables by any factor leaves the magnitude unchanged; a sign flip at
  the panel's scale gives 1; a value added in one table gives `schema` with the value named and a
  magnitude from the common rows; an all-zero baseline panel with a 1e-9 ripple in the current
  table gives a magnitude below 1e-3; a change crossing zero (1 → −1 at scale 1) gives 1; a
  deviation exactly at the tolerance is same, just above is changed; nulls on one side count,
  nulls on both sides do not; a stacked panel with +5 and −5 series has scale 5, not 0; the
  magnitude is bounded by 1; panels come from the filter dimensions and `top_panels` are ordered
  and at most three; differing dimension or measure columns give `schema` and magnitude None.
- Controls: unbound dimensions become filters with the first value as default; a bound dimension
  gets none; `defaults=` sets the default; `controls={...: "split"}` gives a split; a
  determined dimension is hidden and `determined_by` names its determiner (a unit column following
  a variable column); a split request on a determined dimension or on a plot type without
  `splits` is a table error.
- Build: the manifest entry carries `controls`; the JSON Schema and the round trip still pass;
  `digits` in a pyproject is an unknown key with a hint; `config` has `tolerance` only.
- The measurement above, by hand, recorded in the plan.

## Out of scope

The comparison file, `blicket diff`, the terminal summary (M0.6); baseline resolution, `new`,
`removed` and `error` as flags of a build comparison, reports (M0.7); the browser halves of the
plot types (M1); public helpers for project plot types (later, once two project plot types want
the same thing).

## Open questions for Tobias

1. **ε = 1e-6** as the floor of the panel scale relative to the Blick-wide scale: small panels
   are judged on their own scale down to a millionth of the largest value. Alternative: 1e-3,
   which measures small regions against the world. Proposal: 1e-6.
2. **Per-panel scale**, not per-series (the `production_trade_consumption` case: a 10 % change
   of net imports next to production five times larger shows as 1.8 %). Proposal: per panel, as
   the architecture's facet reasoning says.
3. **Removing `digits`** from the config now that nothing rounds. Proposal: remove.

## Decisions taken here, not asked

- `diff` gains a `tolerance` parameter; `controls` keeps the architecture's signature because the
  functional dependence is computed at check time into the schema (`determined_by`).
- Differing column sets are `schema` without a magnitude.
- The core applies `controls=` and `defaults=` after the plot type's default controls; plot types
  declare `splits`.
- The formula version is a field of `Change`.

## Review findings, to apply when the task resumes (2026-10-24)

Verified on the example builds and with polars 2.0 unless marked as opinion.

1. **The expected magnitude is wrong under the plan's own rule.** Every example Blick splits by
   Region, so `production_by_source` is one panel and its 28-vs-34 magnitude is 0.021 (stacks per
   Time × Region), not 0.10, which is the per-series scale the plan rejects; a 10 % change in
   Japan reads 0.36 % against the shared scale. Decide the panel definition together with whether
   facets share a y axis in M1: if each facet has its own axis, the panel should be filter *and*
   split values (one scale per facet).
2. **`top_panels` carries nothing on the example** (no filter controls anywhere). Replace it with
   one `where`: the dimension values of the row with the largest deviation, filter and split
   values alike, which is what the viewer needs to open a Blick where it changed most.
3. **The coalesced full join loses the side a row came from**: a baseline-only row and a common
   row with a null current value look alike. Add an `_in_current` marker before the join (or use
   semi/anti joins), pass `validate="1:1"`, and sort before ranking; `how="full"` does not
   coalesce by default and keeps no order.
4. **Degenerate scales**: an all-zero measure gives S = 0 and `min(1, nan)` returns 1 (a total
   change reported for equal tables); an empty table makes `ε * None` raise; `check` accepts
   ±inf and inf − inf hides changes. Deviation is 0 when s = 0 and the values are equal; an empty
   table has magnitude 0; `check` rejects infinite measures.
5. **`determined_by` as specified misfires**: in a 1:1 pair both dimensions determine each other
   and both vanish; a single-valued dimension is determined by everything; the result depends on
   the run's data, so a `split` request would be an error on one run and fine on another. It finds
   nothing in the example. Defer it to the viewer's needs, or require more than one value and keep
   the first dimension of a mutual pair.
6. **The stacked rule must group by every dimension except `stacked_by`** (x, split, hidden);
   grouping by x alone sums across facets (0.005 instead of 0.021). S for the ε floor is max |v|,
   s is a stack sum.
7. **A key column whose dtype differs between the tables crashes the join**; the column
   comparison includes dtypes and sets `schema`. The float-columns-are-measures claim holds.
8. **Removing `digits` touches more than listed**: `assembly._finalise` (`check_tolerance`) and
   `assemble`'s then-unused `config` parameter, the `Registry` docstring, `test_config.py`,
   `test_assembly.py`, `test_build.py`, architecture.md lines on digits (52, 206, 228, 371), the
   M0.8 text in m0-tasks.md; the project tolerance gets the same "below 1" bound as the per-Blick
   one.
9. **`Change` lacks what M0.6 needs**: type the full flag set once (`new`, `removed`, `error`
   included) rather than wrapping; separate fields for differing columns instead of a `"columns"`
   key that collides with a dimension of that name; define `Counts` and `Panel`. (Opinion.)
10. **Missing M0.5 items from m0-tasks.md**: deriving the plot factories from the channel
    declarations (`PlotType.__call__`), and the trade sign convention, are neither in scope nor
    deferred.
11. **Manifest changes**: `BlickEntry.controls` needs a default so older builds stay readable; it
    sits next to `definition.controls`, which means the requested kinds, so rename one; every id
    changes and `BuildConfig` loses a field, so bump `spec` or say why not.
12. **Import cycle**: `model.py` imports `blicket.plots`; `Control` and `Change` defined in
    `model.py` and imported by `plots/_base.py` would cycle. Define them in `comparison.py` or
    `plots/_base.py` and re-export.
13. **`tolerance` as a `diff` parameter is derivable** (opinion): with tolerance below 1, `value`
    is set exactly when magnitude > tolerance, so the driver can set the flag and `diff` keeps the
    architecture's signature; only the changed-row count needs tolerance.
14. **ε is untested by the data** (no filter panels; the smallest region panel is 3.4e-2 of S).
    Keep 1e-6 but say it is chosen without data; with 1e-6 changes below 1e-11·S are hidden, four
    orders above the measured noise. The planned test "1e-9 ripple gives below 1e-3" gives exactly
    1e-3 at S = 1.
15. **Lean cuts** (opinion): drop `splits` (true for all built-ins); move `version` to the
    comparison file; one `where` instead of `top_panels`.
16. **Details**: `diff` uses the current build's controls after `controls=`/`defaults=`; a
    `defaults=` value missing from the table falls back to the first value; an unbound Time
    defaulting to 1950 is a poor default.
17. Measured: a diff on 24k rows takes 4 to 8 ms; 28 vs 31 deviates by 0; the two production
    tables differ by at most 1.1e-16 relative between 28 and 34.
