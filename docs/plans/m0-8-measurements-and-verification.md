# M0.8 Measurements, defaults and M0 verification

Status: built 2026-10-26; plan written the same day and revised after its review. Result: the
`tolerance` default stays 1e-5; two reruns of remind-mfa give identical tables; every M0 item of
the verification list holds on one machine; the README's Installation section was checked by
installing the wheel; no change to `src/`. Facts and Approach are as planned except where
Deviations says otherwise (the fetch was not needed; the README names no git route);
Measurements, the Verification walk and Deviations are what happened. The task entry is in
`m0-tasks.md`; the verification list is the "Verification" section of `docs/architecture.md`.

## Goal

Close M0 with evidence: measure what the architecture asked to measure (loader time and the
noise between reruns, which sets the `tolerance` default), confirm or correct the default, walk
the M0 items of the verification list on this machine with the cross-machine item waived, and
give the README the installation section it lacks. Nothing new is built; what the walk finds
wrong is fixed. The measurements and the walk are recorded in this plan, as the M0.3 and M0.4
plans record theirs; the architecture points here.

## Facts the plan rests on (checked 2026-10-26, the review's checks included)

- The example runs in `data_out/` (28, 31, 34) were produced on 2026-10-24 from remind-mfa
  `a7c389a` with input data `rev2.8.0_h12`. The checkout at `~/code/remind-mfa` moved to
  `710302d` on 2026-10-26, eight commits on: the plastics model gained reuse flows and a
  `reuse_share` parameter, the stock saturation level changed (#244), and `config/default.toml`
  asks for input data `2.9.1`, which is not in `madrat_output/` (only `rev2.8.0`). So **a run at
  the current commit cannot start** without fetching the data from the cluster, and if it ran it
  would differ from the old runs by a model change and a data change at once. A rerun with the
  unchanged model needs the checkout at `a7c389a`, where the extracted `rev2.8.0` data and the
  command `uv run remind_mfa.py --config default --config blicket --model plastics` are right
  (at `710302d` the command is `uv run remind_mfa …`; there is also a `remind-mfa` script).
  The layer `config/blicket.toml` (pickle export only, no figures) is in the checkout, ignored by
  its `.gitignore`. (The 2.9.1 archive was fetched outside this walk, before it started; see
  Deviations.)
- The old runs build at `710302d`: the review built run 28 there into the scratchpad (10 built,
  loaded in 980 ms) and `diff` against run 28's stored build gives `10 unchanged`. That is the
  CI case, the same run under newer Blick code, and one verification item by itself.
- remind-mfa's `pyproject.toml` changed since `a7c389a` (PyYAML, `[project.scripts]`), so the
  first `uv run` in the example rewrites `examples/remind-mfa/uv.lock`; the walk restores it
  (Decided, 2).
- Reruns are byte-identical in their tables but **not in `model.pickle`**, so their builds have
  different ids (the id covers `run.fingerprint`, a sha256 over the pickle's name, size and
  content hash) and equal per-Blick `hash` values: builds `bfa7f61fc79b65c2` (run 28) and
  `9bb88a679a29a905` (run 31) in the example's store show it. The stored comparisons give
  magnitude 0 for all ten Blicks between them, and about 1.2e-16 in the two tables the
  deliberate change of run 34 touched only numerically; the deliberate change itself is 2.1% of
  scale.
- The `tolerance` default is 1e-5 (`config.py`), per Blick `tolerance=`; `value` needs a
  magnitude above it. The genuine changes seen are about 1e-2 and the largest noise a magnitude of
  1.2e-16, so any default from about 1e-13 to 1e-3 passes a "noise below, change above" test: the
  default has to be justified from both ends instead, and the risk left unmeasured lies in
  remind-mfa's fits (both argued once, under "The tolerance default" in Measurements). This laptop
  has AVX2 and no AVX-512.
- The 19 manifests under `examples/remind-mfa/.blicket/build/` record `loader_ms` from 627 to
  1014 ms; the pickle is 112 MB.
- The README had no installation section. blicket is not published and the repository had no
  git remote (it is public at https://github.com/tobiasdiez/blicket since 2026-10-27, see
  Deviations), and a `git+https://` source builds blicket without the viewer unless the installing
  project sets the meson option (off by default). `uv build --wheel
  -Csetup-args=-Dviewer=enabled` from a synced checkout gives a pure `py3-none-any` wheel with
  `blicket/_viewer` (checked on a scratch wheel: 23 viewer entries), needing Node, pnpm and
  network; `uv add path/to/wheel.whl` records a path source. `tests/projects/minimal` is a
  project with four Blicks in two groups and an `expected-list.txt`.
- The verification list's M0 items, with the evidence for each and its result: see the
  Verification walk. Hot reload is M2.

## Approach

### The fresh run and the noise

1. **Two fresh runs at the current commit** (decided at the sign-off): the input data 2.9.1 is
   fetched from the cluster as the old data was (`uv run scripts/fetch_from_hpc.py mfa-archive
   --config default hpc-jump` in `~/code/remind-mfa`; if the fetch needs an interactive login,
   the implementer stops and says so), then the plastics model runs twice through the `blicket`
   layer (`uv run remind_mfa --config default --config blicket --model plastics`), the runs
   moved into `data_out/` and recorded in `data_out/RUNS.md` with commit `710302d` and data
   revision 2.9.1. The first is built and pushed; the second is checked with no `--against`:
   baseline resolution on the real history takes the newest pushed build of the profile at an
   ancestor of the commit checked out here, the first fresh run's, and the expected result is
   `10 unchanged`, exit 0. The builds' `loader_ms` and the wall time of `check` end to end are
   recorded. Then the first fresh run checked `--against bfa7f61fc79b65c2` (run 28's build, the
   old model on the old data): counts and top movers recorded as what a model change plus a data
   change look like, a demonstration, not a verification item.
2. **The old run under the new Blick code**: `check` run 28 `--against bfa7f61fc79b65c2` (its
   stored build): `10 unchanged`, the CI case.
3. **A deliberate transformation change**: `flows/production_by_source` scaled by 1.01 in
   `examples/remind-mfa/blicks/flows.py`, `check` on run 28 `--against bfa7f61fc79b65c2`
   (naming the clean build, so the newest-pushed rule cannot pick another run's), expected `1
   value`, `Δ 1.0% of scale`, exit 1; the edit reverted, the output recorded here. The renamed
   dimension value is left to `test_diff.py`'s `schema` tests.
4. **Loader time**: the `loader_ms` of the existing manifests tabulated (range and median), plus
   the fresh builds; a pickle just written is warm, so no cold/warm split.
5. **The tolerance default** stays 1e-5 unless step 1 flags a Blick, justified from both
   ends: 1e-5 of a panel's scale is far below what a chart resolves (a 500 px plot resolves
   about 2e-3), so no visible change is hidden; the measured noise is 0 to 1e-16, nine orders
   below, which leaves room for other machines; and the unmeasured risk is named, the
   optimizers' stopping tests, with the remedy (`tolerance` in `[tool.blicket]`, `tolerance=` per
   Blick, and the magnitude in the report that shows which it was).

### The verification walk

Each M0 item gets a line in the "Verification walk" section of this plan: what shows it, the
command or the test, the result on 2026-10-26. Beyond the steps above: the no-op push by hand
(push the fresh build twice, the store says it was there already; the test covers the files),
the feature-branch and second-profile rules by their tests (the walk's own `check` at HEAD
resolves a build made at `604e20c`, which exercises the ancestry rule for real), the hashes
as the facts above state them, the magnitude properties by their tests, the viewer by one
`serve` of the fresh checked build.

### The README and the docs

- **Installation**, a new section before "Defining Blicks", one route that works today: clone,
  `uv sync`, `uv build --wheel -Csetup-args=-Dviewer=enabled` (Node 24, pnpm, network), then in a
  project with `requires-python = ">=3.14"`: `uv add path/to/blicket-….whl`. Verified by doing it:
  the wheel added to a scratch copy of `tests/projects/minimal` outside the repository, `blicket
  list`, `build` and `serve` working from the bundled viewer with `BLICKET_VIEWER` unset. The
  path dependency plus `BLICKET_VIEWER` stays in Development and the example's README; one
  sentence says that an install from git follows once the repository is public (a public remote
  is planned, decided at the sign-off; no URL yet). Overridden: the README names a wheel on a
  GitHub release instead, see Deviations.
- The example's README: the run command per commit (`uv run remind_mfa.py …` at `a7c389a`, `uv
  run remind_mfa …` now), the sentence on which commit a run loads with softened to "the commit
  that wrote it, or one whose classes still match: the runs of `a7c389a` load at `710302d`", and
  the fresh runs in the list. `examples/remind-mfa/uv.lock` is **not** committed refreshed
  (decided at the sign-off): `uv run` in the example rewrites it for remind-mfa at `710302d`,
  which the environment needs (PyYAML), and the walk restores it with git before the end; the
  README already says that `uv run` rewrites the lock after a checkout whose `pyproject.toml`
  differs, and that the rewrite is not to be committed.
- `docs/architecture.md`: an amendment line in "Verification" and one in the "Tolerance"
  paragraph (which says a rerun on another machine validates the default), both pointing here.
- `data_out/RUNS.md` gains the fresh run with its data revision.
- `m0-tasks.md`: the M0.8 entry rewritten as built; M0 closed; what M2 starts from.

## Affected areas

- `README.md` (Installation), `examples/remind-mfa/README.md`, `docs/architecture.md` (two
  amendment lines), `docs/plans/m0-tasks.md`, this plan.
- `data_out/` (gitignored): two run folders and `RUNS.md`; the example's `.blicket/store` gains
  the fresh builds (gitignored); `examples/remind-mfa/uv.lock` rewritten by `uv run` and
  restored, never committed.
- `~/code/remind-mfa`: the input data 2.9.1 fetched into `madrat_output/` and extracted into
  `data_in/` by remind-mfa itself (both ignored by its git), the runs written to its `data_out/`
  and moved away; nothing else touched, no commit switched.
- No change to `src/` unless the walk finds a defect; the tolerance default changes only if the
  measurement says so; no new tests expected.

## Testing

The measurements and the walk are the test; the record is this plan. `uv run pytest`, `ruff`
and `ty` stay green; the installation section is verified by the scratch install.

## Decided by Tobias on 2026-10-26

1. **Fetch input data 2.9.1 from the cluster and run at the current commit**, twice; the rerun
   noise is between the two fresh runs; a comparison with the old runs is a demonstration of a
   model change plus a data change. (The alternatives were a rerun at `a7c389a`, which needs his
   checkout switched, and no fresh run.)
2. **The refreshed `uv.lock` is not committed**; the walk restores it.
3. **A public remote is planned but not there yet**: the installation section names the wheel
   route and says the git route follows. (The remote came on 2026-10-27; see Deviations.)
4. **No AVX2-disabled rerun.**

## Measurements

Times are UTC, as the manifests and `check` print them, unless marked CET (UTC+1, the laptop's
clock).

| Item | Value |
|---|---|
| Date | 2026-10-26, 10:24 to 10:55 UTC |
| Machine | laptop, Intel Core Ultra 7 268V (8 cores, AVX2, no AVX-512), 32 GB, Linux 7.3 (CachyOS) |
| remind-mfa | `710302d` (upstream `main`, one commit past the fork's), input data `rev2.9.1_h12`, layers `default` + `blicket`; its environment: numpy 2.4.6, scipy 1.18.0, pandas 2.3.3, flodym 1.1.0 |
| blicket | `81d752e`, dirty (this plan untracked; `examples/remind-mfa/uv.lock` rewritten by `uv run`) |
| Example environment | CPython 3.14.8, polars 2.0.0, pandas 3.1.0, numpy 2.4.6, scipy 1.18.1, uv 0.13.5 |

The runs and builds, by label:

| Label | Run | Model, input data | Builds |
|---|---|---|---|
| A | `2026-10-26--11-25-00_plastics_SSP2_h12` | `710302d`, 2.9.1 | `976f428f3d33dbdf`, pushed |
| B | `2026-10-26--11-25-13_plastics_SSP2_h12` | `710302d`, 2.9.1; rerun of A | `2224d63eb5ef42e1` |
| 28 | `2026-10-24--01-25-28_plastics_SSP2_h12` | `a7c389a`, 2.8.0 | 28's build `bfa7f61fc79b65c2`, pushed, Blicks at `fe4d2dd`; `b0806cfd97b8b4be` at `81d752e`; `c89821f1595d8c1b` at `81d752e` with the deliberate edit |
| 31 | `2026-10-24--01-25-31_plastics_SSP2_h12` | `a7c389a`, 2.8.0; rerun of 28 | `9bb88a679a29a905`, pushed, at `fe4d2dd`; `094957f412733012`, built at `604e20c`, pushed; `67fcd2554cdc1d69` at `81d752e` |
| 34 | `2026-10-24--01-25-34_plastics_SSP2_h12` | `a7c389a`, 2.8.0; `collection_rate` × 0.9 | `34247dcb88fd54c3`, pushed, at `fe4d2dd`; `c6317235ed070309`, built at `604e20c`, pushed (the example README's `check` output); `ed7ecca33e644283` at `81d752e` |

### The fresh runs and the noise (step 1)

In the order taken:

1. The model ran twice in `~/code/remind-mfa` (11:24 and 11:25 CET), `uv run remind_mfa
   --config default --config blicket --model plastics`, about 2.6 s each; the first unpacked
   the 2.9.1 archive into `data_in/`. Runs A and B, moved into `data_out/` and added to
   `data_out/RUNS.md`. Their pickles are 119 MB, those of 2026-10-24 112 MB.
2. `build` A: 10 built, loaded in 833 ms, 1.54 s from `uv run` to exit.
3. `check` A with no `--against`: it resolved 31's build `094957f412733012`, built at `604e20c`
   and pushed (built 2026-10-24 20:02, pushed 20:07), the newest pushed build of the profile then,
   at an ancestor of `81d752e`. `3 unchanged · 7 value`, exit 1, 1.39 s: the ancestry rule on this
   repository's history.
4. `check` A `--against` 28's build: the demonstration below, 1.43 s, exit 1.
5. `push` A's build, twice (the walk's no-op push).
6. `check` B with no `--against`, 1.41 s from `uv run` to exit:

   ```
   run 2026-10-26--11-25-13_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 81d752e (dirty) · loaded in 639 ms
   10 Blicks: 10 built
   build 2224d63eb5ef42e1 → .blicket/build/2224d63eb5ef42e1

   baseline 976f428f3d33dbdf · run 2026-10-26--11-25-00_plastics_SSP2_h12 · blicks at 81d752e (dirty) · built 2026-10-26 10:25 UTC
   vs baseline: 10 unchanged
   nothing flagged
   comparison → .blicket/build/2224d63eb5ef42e1/compare/976f428f3d33dbdf
   ```

   Exit 0: resolution took A's build, the newest pushed build of the profile, at `81d752e`
   itself.

The noise between A and B is zero at every level measured:

- The model: a scratch script unpickled both runs in the example's environment and compared the
  bytes of every flow, stock, inflow, outflow and parameter array of `historical_mfa` and
  `future_mfa`: all 146 are identical, and so are all 143 of runs 28 and 31. The three more are
  the new reuse flows (`eol_management => reuse`, `reuse => use`) and the parameter
  `reuse_share`. The pickles differ elsewhere, so the fingerprints and the build ids differ.
- The tables: A's and B's builds have equal hashes for all ten Blicks, as 28's and 31's have.
- The comparison: magnitude 0.0 for all ten Blicks; `diff` of A's and B's builds and of 28's
  and 31's both print `10 Blicks: 10 unchanged`, exit 0.

**A model change plus a data change (a demonstration).** A against 28's build (remind-mfa
`a7c389a`, input data 2.8.0):

```
baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty) · built 2026-10-24 13:28 UTC
vs baseline: 3 unchanged · 7 value
top movers: flows/production_by_polymer 22% of scale (Time=2100, Region=SSA)
            flows/production_by_source 22% of scale (Time=2100, Region=SSA)
            flows/production_trade_consumption 22% of scale (Flow=Production, Time=2100, Region=SSA)
            … and 4 more
flagged: 7 of 10 Blicks
```

| Blick | flags | magnitude | where |
|---|---|---|---|
| `drivers/gdp_per_capita`, `drivers/scenario_rates`, `drivers/polymer_splits` | none | 0 | |
| `flows/consumption_by_end_use` | `value` | 0.215 (21%) | Time 2100, Region SSA |
| `flows/production_by_polymer` | `value` | 0.223 (22%) | Time 2100, Region SSA (the stack) |
| `flows/production_by_source` | `value` | 0.223 (22%) | Time 2100, Region SSA (the stack) |
| `flows/production_trade_consumption` | `value` | 0.216 (22%) | Flow Production, Time 2100, Region SSA |
| `flows/end_use_split` | `value` | 0.129 (13%) | Time 2069, Region SSA, End Use Buildings & Construction |
| `stocks/use_by_region` | `value` | 0.152 (15%) | Time 2100, Region OAS |
| `stocks/use_by_end_use` | `value` | 0.180 (18%) | Time 2100 (the stack) |

No `schema` flag and the same row counts: the reuse flows are in no Blick, and the dimensions
kept their values. The drivers did not move between input data 2.8.0 and 2.9.1. With seven Blicks
flagged, the comparison's copies of their baseline tables nearly double the build directory: 495
KB with `comparison.json`, next to the build's 543 KB of tables.

### The old runs under the new Blick code (step 2)

`check` run 28 `--against` 28's build, with remind-mfa at `710302d`: build `b0806cfd97b8b4be`,
`10 Blicks: 10 unchanged`, exit 0, 1.44 s. Runs 31 and 34 were rebuilt too, with the example's
`.venv/bin/blicket build` so that `uv.lock` stayed as committed, and `diff` against their builds
of 2026-10-24 gives `10 unchanged` for each. All ten table hashes equal the stored ones for all
three runs: the runs of `a7c389a` unpickle at `710302d` and give the same tables.

### A deliberate transformation change (step 3)

`flows/production_by_source` returned `_by_flow(_production_sources(run)) * 1.01` in
`examples/remind-mfa/blicks/flows.py`; `check` run 28 `--against` 28's build:

```
run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 81d752e (dirty) · loaded in 662 ms
10 Blicks: 10 built
build c89821f1595d8c1b → .blicket/build/c89821f1595d8c1b

baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty) · built 2026-10-24 13:28 UTC
vs baseline: 9 unchanged · 1 value
top movers: flows/production_by_source 0.99% of scale (Time=2100, Region=SSA)
flagged: 1 of 10 Blicks
comparison → .blicket/build/c89821f1595d8c1b/compare/bfa7f61fc79b65c2
```

Exit 1. The magnitude is 0.0099 = 0.01 / 1.01: the panel scale is the largest stack across both
tables, the scaled one, so a change by 1% of the baseline is 0.99% of the scale; `where` names
the stack of SSA in 2100, the largest. The comparison directory holds the baseline table and
`comparison.json`, 35 KB. The edit was reverted with `git checkout`.

### Loader time (step 4)

`loader_ms` from the 25 manifests under `examples/remind-mfa/.blicket/build/`, and the time the
ten Blicks take to build (`timing_ms` summed: transformation, checks, Parquet write and hash):

| Builds | n | loader min | median | max | ten Blicks |
|---|---|---|---|---|---|
| 2026-10-23/24, runs 28, 31 and 34 at older Blick commits | 19 | 627 ms | 676 ms | 1014 ms | 69 to 112 ms |
| 2026-10-26: A, B, 28 twice, 31, 34 | 6 | 636 ms | 668 ms | 833 ms | 79 to 103 ms |
| all | 25 | 627 ms | 674 ms | 1014 ms | 69 to 112 ms |

The two `check`s of A, which found the build made already, printed 628 and 643 ms. The cause of
the spread was not traced: the seven builds of 900 ms and more, and A's 833 ms, were each the
first after a pause, but other first builds after a pause took 661 to 676 ms (661, 676, 672 and
674, the last 31's rebuild, half an hour after the others). The conclusion does not depend on
it. `check`, from `uv run` to exit, build and comparison included, takes 1.39 to 1.44 s (four
checks). Far below the architecture's ten-second threshold: no loader cache.

### The tolerance default (step 5)

Nothing was flagged between the reruns, so the default stays **1e-5**. The argument, made once
here (the Facts and the Deviations point here):

- **No visible change is hidden.** 1e-5 of a panel's scale is far below what a chart resolves: a
  500 px plot shows about 2e-3 of its scale per pixel. The genuine changes seen are about 1e-2:
  9.9e-3 for the deliberate edit, 2.1e-2 for run 34.
- **The noise is far below it.** The reruns differ by nothing: 0 in every array and every Blick,
  on both days. The largest float-rounding difference in any comparison is a magnitude of 1.2e-16
  (run 34 against 28, in the two tables the change of `collection_rate` touched only through
  sums); the M0.4 plan measured the same pair per value against a column's scale and found at
  most 1.3e-15. 1e-5 is ten to eleven orders of magnitude above either.
- **What stays unmeasured is another machine**, where two kinds of difference can enter through
  remind-mfa's stock fits in `remind_mfa/common/fit_stocks.py`:
  - *Small noise.* `minimize(fun=…, jac=…, x0=…, tol=0.001)` names no method and has no bounds,
    so it is BFGS, where `tol` sets `gtol`, a stop on the gradient's norm. A last-bit difference
    (another BLAS, AVX-512) can move that stop by an iteration, and the fitted parameters by one
    BFGS step, of a size this plan cannot bound; `least_squares(…, gtol=1e-12)` in
    `remind_mfa/common/data_extrapolations.py` is the same kind. Should it show, the remedy is
    `tolerance=` on the stock and flow Blicks (or `tolerance` in `[tool.blicket]`); the drivers
    are inputs, never fitted, and stay at the default. Even a tolerance of 1e-3 stays below a
    pixel.
  - *A jump.* Before optimising, the fit picks its start by `np.argmin(penalties)` over 55
    offsets (`np.arange(-1.1, 0, 1 / 50)`); two near-equal penalties can swap on a last-bit
    difference, and the fit lands in another local minimum. That is a different result, not
    noise: no tolerance should absorb it, and it is a reproducibility report to remind-mfa.
- **Where the second machine is measured for free:** the first `check` on the cluster of an
  unchanged run against a build pushed from the laptop. Its result belongs in this section. What
  to look for: `value` flags on stock and flow Blicks only, with magnitudes well under 1e-3, are
  the small noise; larger ones, or flags on the drivers, are not.

## Verification walk

The M0 items of the architecture's "Verification" list, on 2026-10-26, on the machine above; the
items shown by runs first, those shown by tests after.

| Item | Evidence | Result |
|---|---|---|
| The `examples/` project builds | A, B and 28 (twice) built at `81d752e`, 31 and 34 rebuilt; the 19 builds of 2026-10-23/24 at older Blick commits | 10 of 10 Blicks built in all 25 builds |
| `check` on an unchanged run against its own previous build exits 0 | `check` run 28 `--against` 28's build; `check` B, which resolved A's build | `10 unchanged`, exit 0, both; on a second machine: waived (decision 3 of 2026-10-23) |
| A deliberate transformation change is detected with the expected flags and a sensible magnitude | `flows/production_by_source` × 1.01, `check` run 28 `--against` 28's build; `test_a_changed_transformation_is_flagged` | `9 unchanged · 1 value`, 0.99% of scale at SSA 2100, exit 1; the test passes |
| The viewer renders the example | `serve` of B's checked build, opened in headless Chrome | every file fetched answers 200; the overview names the baseline and `10 unchanged`; the page of `flows/production_by_source` draws its twelve panels and "unchanged against run …11-25-00" |
| Pushing the same build twice is a no-op | `push` A's build twice; `test_pushing_twice_is_a_no_op` | the second push says `(in the store already, left as it was; …)`, exit 0, every stored file's sha256 unchanged; the test passes |
| A rerun of remind-mfa produces zero `value` flags at the defaults | `check` B (against A, tolerance 1e-5); `diff` of 28's and 31's builds | no flags, magnitude 0 in every Blick; on a different machine: waived |
| A feature branch resolves main's latest build as baseline | `test_a_feature_branch_compares_with_mains_build`, `test_at_the_next_commit_the_branchs_build_is_the_baseline`, `test_after_the_merge_main_compares_with_the_branchs_build`, `test_against_a_ref_searches_its_history`, `test_older_builds_at_the_tip_lose_to_newer_ones_at_an_ancestor`; `check` A with no `--against` | the tests pass; the check at `81d752e` resolved 31's build, built at the ancestor `604e20c` |
| A second profile resolves its own | `test_each_profile_resolves_its_own` (the example has one profile) | passes |
| The same table written twice hashes identically | `test_output_is_deterministic`; A's and B's builds; 28, 31 and 34 built at `fe4d2dd` and at `81d752e` | passes; ten equal hashes in each pair |
| The same data from polars and pandas hashes identically | `test_pandas_and_polars_give_the_same_parquet` | passes |
| Magnitude: the property tests | the tests below | all pass |

The magnitude's tests, all in `tests/test_diff.py`: identical tables,
`test_identical_tables_are_unchanged`; scaling both tables,
`test_scaling_both_tables_keeps_the_magnitude` (factors −1, 1e-30, 3.7 and 1e12, with and
without panels and stacks); a sign flip,
`test_a_sign_flip_of_a_stack_is_total_and_names_the_stack` and the cap
`test_the_magnitude_is_at_most_1`; an added value,
`test_a_value_of_one_table_only_is_schema_and_its_rows_are_left_out`; near zero,
`test_the_scale_of_a_zero_panel_is_floored`, `test_the_scale_of_a_zero_stack_is_floored` and
`test_the_tiniest_value_against_null_is_total`; sign crossing,
`test_a_change_across_zero_counts_both_sides`. Hot reload is M2's.

**The installation check.** The wheel from `uv build --wheel -Csetup-args=-Dviewer=enabled` was
added with `uv add` to a copy of `tests/projects/minimal` in the scratchpad, made a uv project
with `requires-python = ">=3.14"` (its loader and run: see Deviations). With `BLICKET_VIEWER`
unset, `blicket list` printed `expected-list.txt`, `blicket build` built the Blicks and copied the
bundled viewer, and `blicket serve` served the manifest and the viewer's files, byte-identical to
the installed `blicket/_viewer`; headless Chrome drew the chart.

## Deviations

- **The fetch was not run.** The 2.9.1 archive was fetched outside this walk, before it started:
  it was in `madrat_output/`, written at 11:00 CET, before the walk began at 11:24 CET, and
  complete (89 entries, like the 2.8.0 archive, by `tar tzf`). The model run unpacked it. The fetch
  command in the example's README was checked against the script's signature (`mfa-archive
  REMOTE_HOST --config …`), not run.
- **The git route came with the public remote, on 2026-10-27**, a day after the wrap-up. Until
  then the README named no git route, against decision 3, since a git source is built in the
  installing project with the `viewer` option off (`meson.options`, and `meson.build`'s
  `find_program('pnpm', required: get_option('viewer'))`) and would have had no viewer; it said
  that a public release would put the wheel on a GitHub release and on PyPI. With the repository
  public, Installation leads with `uv add git+https://github.com/tobiasdiez/blicket` and
  `[tool.uv.config-settings-package] blicket = { setup-args = "-Dviewer=enabled" }`, which turns
  the option on in the installing project (uv 0.13.5). Verified in two scratch projects: with the
  setting, the install holds `blicket/_viewer` (20 files) and `viewer.find()` returns it, also
  with an empty uv cache; without it, `viewer.find()` raises. The cost is Node, pnpm and network
  on every machine that syncs the project, so the wheel route stays, for machines without Node.
  The viewer's "no viewer found" message now points at the README instead of at a release.
- **One more `check`, for the ancestry rule**: A with no `--against`, before A was pushed (step 1,
  item 3); its comparison went into the store with A's build.
- **0.99% of scale, not 1.0%**: the formula as documented (step 3).
- **Runs 31 and 34 rebuilt**, beyond the plan, to show that all three runs of `a7c389a` load at
  `710302d` (step 2).
- **More evidence than planned** for the noise (the pickles' arrays compared, step 1) and the
  viewer (headless Chrome, the walk).
- **The loader times spread** from 627 to 1014 ms with no traced cause (step 4).
- **The tolerance margin is ten to eleven orders of magnitude**, not nine (step 5).
- **The minimal fixture needed a loader and a run for `build`.** `tests/projects/minimal` has
  neither, and its `flows/scrap` and `flows/slag` return a tuple, as the registration tests want.
  The scratch copy got a `blicketconf.py` that reads `flows.csv` into a polars frame and a run
  `runs/2026-10-22/flows.csv` (year, process, region, value). Its first build exited 2 with those
  two as errors (`the transformation returned tuple; …`) while the other two built and the viewer
  was copied; the copy's two lambdas then returned the run, and the build gave four built, exit 0.
  `blicket list` matched `expected-list.txt` before and after.
- **The wheel had 20 viewer entries**, not the 23 of the scratch wheel in the Facts: the viewer's
  chunks changed since.
- **The READMEs got more than listed.** The root README's Installation section has the installer's
  step first and "Building the wheel" after, and Development now says that a build with the
  `viewer` option fails without pnpm; `viewer/README.md` says Node and pnpm also build the wheel.
  The example's README clones upstream `pik-piam/remind-mfa`, which holds both commits (the
  fork's default branch holds neither), has Node and pnpm under Prerequisites, "Producing a run"
  as numbered steps after "Environment", starting with the checkout, and the two generations of
  runs, with what a newer generation's pushed build means for `check`.
