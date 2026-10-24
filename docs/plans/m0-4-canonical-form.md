# M0.4 Canonical form and content hashes

Status: **dropped on 2026-10-24** before implementation, after the plan review. Tobias decided
that neither a writer-independent content hash nor the canonical form is worth doing now: the
example reruns are byte-identical, the comparison's tolerance handles small differences, and the
Parquet hash is only a fast path. The plan is kept for the measured facts in "Facts the plan rests
on", which M0.5 uses. Nothing below was implemented. Companion to [architecture.md](../architecture.md) ("Data model at the Blick output",
"Change detection", the tolerance paragraph); where this plan fills in a detail, it says so.

## Goal

Every table a build writes is in canonical form, so that equal content gives equal bytes and an
equal hash whatever library produced it, however the Blick ordered its columns and rows, and
whatever rounding noise a rerun carries, as far as rounding can achieve that. The table hash in
the manifest stays the sha256 of the written Parquet bytes, now over the canonical table, so it is
independent of the input library and of how the Blick ordered its table; it still depends on the
polars version, which Tobias accepted (a polars upgrade renumbers builds once). Checked against
the example runs: the two unchanged reruns hash identically, the changed run differs in exactly
the Blick that carries the change.

An equal hash means unchanged. An unequal hash does not mean changed: a value sitting on a
rounding boundary flips between reruns under noise of 1e-16 (verified: 1.2345649999999998 and
1.2345650000000002 round to 1.23456 and 1.23457), so the hash is the fast path and the comparison
of M0.5 decides. Its rule `tolerance >= 10^(1 - digits)` absorbs a one-unit flip, because the panel
scale is at least the value itself.

## The flow this task enables

1. Nothing changes for a Blick author. A transformation returns a table; blicket checks it as
   before, then canonicalises it and writes it.
2. `blicket build` prints the same lines as before. In the manifest, each built Blick's `hash`
   is still `parquet-sha256:<hex>`, now of the canonical table, and the `config` block records
   `digits` and `zero_floor`.
3. Two builds of equal content produce equal hashes, also when one Blick returned a pandas frame
   and the other a polars frame, when a rewrite reordered the columns, or when a rerun differs by
   float rounding. The example's two unchanged reruns and the changed run give identical hashes
   for nine Blicks and a different one for `flows/production_by_source`.

## Facts the plan rests on

- `tables.check` already puts dimension columns first (in `dims=` order when given, else table
  order), sorts rows by the dimension columns, casts integers to `Int64`, datetimes to
  microseconds, categoricals to strings and measures to `Float64` with NaN as null, and records
  the schema (dimension values in display order). Nothing rounds, nothing floors.
- The architecture decides: canonical form rounds measures to N significant digits (`digits`,
  default 6; `tolerance` must be at least 10^(1−N)) and flushes values below a floor relative to
  the Blick-wide scale to zero, so solver noise around zero does not survive. Small changes are
  never hidden; they rank low.
- Measured on the example builds (M0.3 and the review of this plan): the two unchanged reruns
  are byte-identical; the changed run differs by at most 3.9e-16 relative in two tables and by 2
  to 10 % in `flows/production_by_source`. In `flows/production_by_polymer` the noise reaches at
  most 1.3e-15 of the column's scale (absolute 1.25e-7 against 9.6e7), and the smallest genuine
  value is 1.97e-8 of the scale (1.89 t, IND HDPE 1950). Every floor from 1e-12 to 1e-8 zeroes
  the same values (1454 there, 372 in `production_by_source`, 2 in `polymer_splits`); 1e-7 would
  zero 22 genuine values. Shares and rates lie in [0, 1]. A table has 1.2k to 24k rows.
- Rounding to 6 significant digits alone makes the two production tables of the changed run
  identical to the reruns while `production_by_source` still differs; the floor changes nothing in
  that outcome. The floor is the concept's guard against solver noise around zero, harmless on this
  data, and chosen by its margins, not by a hash outcome.
- Parquet bytes from polars are deterministic for equal frames within one polars version but
  embed the polars version, so they are not a content hash. `DataFrame.hash_rows` is documented
  as unstable across polars versions. `Expr.round_sig_figs` passes 0, −0.0, null, NaN and inf
  through unchanged, rounds halves away from zero, is idempotent and correctly rounded between
  1e-8 and 1e10 (200k values tested), not at extreme exponents (1e308), and is barely documented,
  so the golden test pins boundary cases. `x + 0.0` keeps −0.0 in polars; `when(x == 0)` does not.
- `check` accepts ±inf in a measure; with a floor relative to the column's maximum, an infinite
  value would turn every finite value of the column into zero.

## Approach

### `canonical(frame, digits)` in `tables.py`

Applied to a checked frame, after `check` and before writing. `check` keeps the roles and the
schema but no longer orders columns or rows; ordering lives in one place:

1. **Columns.** Dimension columns in alphabetical (code point) order, then measure columns in
   alphabetical order. The Blick's `dims=` order and the order a transformation happened to
   return are display matters the manifest's schema keeps; the stored table does not depend on
   them, so a rewrite that only reorders columns keeps its hash (`pd.concat` puts the naming
   dimension first, a flodym `to_df()` the array's order). The viewer and a table plot type take
   column order from the schema, not from the file; the `Checked` and `TableSchema` docstrings say so.
2. **Rows.** Sorted by the dimension columns in that order; typed sort, so years sort as numbers
   and strings by code point. Dimension values are unique and non-null (checked before).
3. **Measures.** Per measure column: round to `digits` significant digits; set every value whose
   magnitude is below `ZERO_FLOOR` times the column's scale to 0.0; turn −0.0 into 0.0 (with
   `when`, not by adding 0.0). Null stays null. The **scale** of a measure column is the largest
   absolute value in the canonical table, the Blick-wide scale the architecture names; M0.5 uses
   the same quantity. A column whose scale is 0 stays as it is.

`ZERO_FLOOR = 1e-12` is a module constant, recorded in the manifest's `config` block as
`zero_floor`, not a `[tool.blicket]` key: the architecture lists `tolerance` and `digits` as the
keys, nobody needs to change the floor yet, and a key would be added when someone does. 1e-12
sits three orders of magnitude above the measured noise and four below the smallest genuine value;
it also protects IAMC-style tables that mix units in one measure column, where a relative floor of
1e-9 could bite. Canonicalising twice changes nothing (idempotence is tested).

`check` gains one rule: an infinite value in a measure is an error (`'value' has 3 infinite
values; replace them or drop the rows`), since no scale can be taken over it.

The manifest's `columns` schema is computed from the checked frame before canonicalisation, which
is right because canonicalisation touches neither rows nor dimension values, and `values` keep
the display order.

### Hash

Unchanged in kind: `parquet-sha256:<hex>` over the bytes `write_parquet` produced, now from the
canonical frame. Equal content from any input library and any column or row order gives equal
bytes within one polars version (verified by the review). A writer-independent content hash was
considered and dropped by Tobias on 2026-10-24: its only gain would be stable ids across polars
upgrades, and the diff of M0.5 does not depend on hashes.

### Config

No new key. `digits` stays 6 (the architecture's default; `tolerance = 1e-5` remains valid under
`tolerance >= 10 ** (1 - digits)`). The manifest's `config` block gains `zero_floor`, so a stored
build says what it was floored with.

### Where it runs

The builder's table-writing step applies `canonical` to `checked.frame` with the config's
`digits`, writes the result with `write_parquet` (zstd, as now) and hashes the written bytes as
before. Row counts and the schema are unchanged.

### Measurement, recorded in this plan when the task ends

Build the three example runs with the canonical form and compare manifests: the two unchanged
reruns must hash identically for all ten Blicks; the changed run must differ in
`flows/production_by_source` only, the float-rounding differences of the two production tables
gone. Record how many values the floor set to zero per Blick and the largest such value, next to
the smallest genuine value kept, so the margins of the default are on record. (The review already
did this once: 1454, 372 and 2 values at any floor between 1e-12 and 1e-8.)

## Affected areas

- `tables.py`: `canonical`, `ZERO_FLOOR`, the infinity check, ordering removed from `check`;
  `builder.py`: the call; `manifest.py`/`model.py`: `config.zero_floor`; `__init__.py` unchanged
  (no new public API; `blicket.tables.canonical` is reachable for the comparison tasks).
- `README.md`: the hash sentence and the canonical form in one paragraph.
- `docs/architecture.md`: one dated sentence that the floor is a constant 1e-12 of the column's
  scale recorded in the manifest, that the table hash is the Parquet hash of the canonical table,
  and that an equal hash means unchanged while an unequal hash hands over to the comparison.
- `docs/plans/m0-tasks.md`: the M0.4 done-when (the changed run differs in
  `production_by_source`, not in the two production tables) and a note for M0.5 that its ε must
  satisfy `ε >= zero_floor / tolerance` (1e-7 at the defaults) so a value flipping across the floor,
  or a new scenario raising the scale, cannot show as a change beyond tolerance; a column that is
  all noise keeps its noise under a relative floor, a known limit handed to M0.5.
- `examples/remind-mfa/`: nothing; its builds are the measurement.

## Testing

- Canonical form: a polars frame and the same data as a pandas frame give equal bytes and hash;
  a column permutation and a row permutation give the same hash; `dims=` order does not change
  the hash; values differing beyond `digits` hash differently and within `digits` identically
  (1.0000001 vs 1.0000002 at 6 digits equal, 1.00001 vs 1.00002 different); a value below
  `ZERO_FLOOR` × scale becomes 0.0 and one above stays; −0.0 becomes 0.0; null stays null and
  hashes differently from 0.0; a column of nulls and a column of zeros are left as they are;
  canonicalising twice changes nothing; an infinite measure value is a table error; the schema's
  `values` order is unaffected.
- Format: a golden canonical table for a small fixed input pins the form (the test the task's
  done-when asks for), with a rounding-boundary value, a value at an extreme exponent, a null, a
  date and a datetime among its rows, compared as rows, not as Parquet bytes, so a polars upgrade
  does not fail it.
- Manifest: `config.zero_floor` present; the JSON Schema still validates; the round trip.
- Build: the hash of a Blick is the same when its transformation returns the same data as a
  pandas frame with another column order; the id changes when a stored table changes.
- The example measurement above, by hand, recorded in the plan.

## Out of scope

Tolerance semantics and the magnitude (M0.5, which reads `digits`, `zero_floor` and `tolerance`
from the manifest's `config`); cross-machine noise (waived); a canonical form for the raw run
data (there is none: raw data stays opaque); a `digits` per Blick (the architecture has
`tolerance` per Blick only); a configurable floor.

## Decided by Tobias on 2026-10-24

1. **No content hash.** The table hash stays the sha256 of the canonical Parquet bytes; the churn
   of a polars upgrade is accepted.
2. **Alphabetical column order** in the stored table and **the zero floor as a constant 1e-12**
   recorded in the manifest were proposed twice without objection and are taken as agreed.

## Decisions taken here, not asked

- The scale for the floor is per measure column over the whole table (the Blick-wide scale of
  the architecture), computed after rounding; M0.5 uses the same definition.
- An infinite measure value is a table error.
- Ordering of columns and rows moves from `check` into `canonical`.
