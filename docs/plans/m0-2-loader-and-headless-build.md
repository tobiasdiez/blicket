# M0.2 Loader, RunInfo and the headless build

Status: plan, 2026-10-23, revised the same day after an independent review that tested the
polars, pandas and pydantic claims, and signed off by Tobias the same day. Second task of [m0-tasks.md](m0-tasks.md), building on the
M0.1 code (commit `0a6b858`). Companion to [architecture.md](../architecture.md); where this plan
fills in a detail the architecture leaves open, it says so. Two phases: first the restructuring
the M0.1 reviews deferred to the start of this task, then the build.

## Goal

`blicket build <run dir>` loads a run through the project's loader, runs every Blick's
transformation, writes each table as Parquet into an immutable build directory, and writes a
`manifest.json` that describes the build: the definitions, the run, the repository state, the
per-Blick table schemas and hashes, and every problem. No comparison, no canonical form, no
viewer. The manifest is the first versioned file of the on-disk protocol, so its shape is
designed with the later tasks in mind; the Parquet content is provisional until M0.4
canonicalises it.

## The flow this task enables

1. The project names its loader and writes it:

   ```toml
   [tool.blicket]
   loader = "mymodel.blicket:load_run"
   ```

   ```python
   # mymodel/blicket.py
   import blicket as bk

   def load_run(selection: bk.RunSelection) -> tuple[object, bk.RunInfo]:
       path = selection.paths[0]
       run = pickle.load(open(path / "model.pickle", "rb"))
       return run, bk.RunInfo(
           id=path.name,
           profile="plastics_SSP2_h12",
           fingerprint=bk.fingerprint(path / "model.pickle"),
       )
   ```

2. Blick transformations return tables in whatever library the project uses:

   ```python
   @bk.blick(title="Use stock", plot=bk.plots.stacked_area(x="Time", y="value", color="End Use"))
   def use_stock(run):
       return run.future_mfa.stocks["use"].stock.to_df()     # a pandas frame with a MultiIndex
   ```

3. `blicket build data_out/2026-10-22--10-18-17_plastics_SSP2_h12` prints

   ```
   run 2026-10-22--10-18-17_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 0a6b858 (dirty) · loaded in 1.5 s
   7 Blicks: 6 built · 1 error
   build 3f9a1c2b7d4e6f80 → .blicket/build/3f9a1c2b7d4e6f80

   errors
     blicks/stocks.py:12  Blick stocks/in_use
       transformation raised KeyError: 'use' (raised at blicks/stocks.py:14)   (-v for the traceback)
   ```

   and exits 2 because of the error, 0 otherwise. The build directory holds `manifest.json`
   and `blicks/stocks/use_stock.parquet` and so on, one file per built Blick. Running the same
   build again yields the same id and leaves the existing directory alone.

4. `blicket build --json ...` prints the manifest itself, so tooling reads the same file the
   directory holds.

## Phase 1: restructuring carried over from M0.1

The M0.1 architecture reviews deferred these to the start of this task (see m0-tasks.md). The
review of this plan trimmed them: input validation stays where it is, and the pydantic models
are the *output* shapes the manifest needs, built at assembly time when id and group are known.

- **`BlickDefinition`**, a frozen pydantic model of the decorator options: `title`,
  `description`, `tags` (the Blick's own), `plot` (`type` and `mapping`), `controls`, `defaults`,
  `tolerance`, `dims`, `measures`, `order`. Identity and location (`id`, `group`, `aliases`,
  `module`, `source`) live on `BlickEntry`, the one shape for a Blick in the registry and in the
  manifest (see the manifest section), so nothing is written twice. `Blick` stays a dataclass
  holding the fields plus `transform` and the `PlotSpec`, and gains `entry()` returning the
  `BlickEntry`; the hand-written `to_json` methods go. Checking the decorator arguments stays in
  `_validation.py`, because it happens at decoration time, before id and group exist, and because
  the tolerance check needs the config. The `BlickOptions` TypedDict stays for the decorators'
  keyword typing; a test asserts its keys equal the definition's fields plus `id` and `aliases`.
  (This departs from the m0-tasks.md note, which expected validators on the model and the
  TypedDict to go; the review showed that does not fit decoration-time checks. m0-tasks.md is
  updated.)
- **`Problem` and `Source` become pydantic models**, so the manifest embeds them as they are.
  `Source.line` is `int | None` (today `0` stands for the whole file); `Source.file` is
  serialised relative to the project root through a dump context
  (`model_dump(context={"root": root})`), so a build directory never contains a path a reader
  would resolve against the machine it was built on. Text that happens to contain an absolute
  path (a traceback, the "installed in <prefix>" hint) is not covered by that rule.
- **Failed Blicks** are `BlickEntry`s too (`Registry.failed`), with `id: str | None` and
  `aliases` at the top level and `definition: BlickDefinition | None`: a Blick that failed after
  its definition could be built (an id claimed twice, a tolerance too fine) keeps the definition;
  one whose arguments were invalid has `None` but still its id when one was given, so M0.7 can
  tell "failed" from "removed". (The plan first had a separate `FailedBlick` type; review round 2
  merged it.)
- **Tracebacks and locations** move from `discovery.py` into `blicket/tracebacks.py`:
  `project_traceback(error, root)` (frames under the root only, pseudo-filenames excluded) and
  `locate(error, root, prefer=file) -> Source | None`. Discovery and the build use the same two
  functions, so a raised transformation is located and trimmed like a raised import.
- **CLI scaffolding.** The exit-code policy sits on the app's group class, so no command can
  miss it; `--project` and `-v` are shared `Annotated` option aliases (not a callback-resolved
  root, which m0-tasks.md suggested; the alias is enough for two commands), `-v` carried in
  click's `ctx.meta` for the group to read. Each command renders its own text or JSON and hands
  it to one `finish(text, failed)`, which also exits quietly on a closed pipe. A test injects a
  failure into every registered command. Errors raised by blicket's own checks derive from one
  `BlicketError` base. What project code prints goes to
  stderr during the loader and the transformations too, as it does during discovery.

## Phase 2: the build

### Loader protocol

- `[tool.blicket] loader = "package.module:function"`, imported with the project root on
  `sys.path` (discovery already puts it there). Missing key → `ConfigError` naming the key; a
  loader that cannot be imported, raises, or returns the wrong shape → one `error:` line on
  stderr with the trimmed traceback under `-v`, exit 2, no directory and no JSON. Without a run
  nothing can be built.
- `RunSelection` (frozen dataclass): `paths: tuple[Path, ...]` as resolved from the command line,
  and `path`, a property that returns the single path and raises with a clear message when there
  are several. `blicket build` accepts one or more paths; the loader decides what several paths
  mean (several model runs collected into one blicket run, as the architecture allows). Labels
  for the dev-mode run picker are added when that picker exists. A run path that does not exist
  is reported before the loader runs.
- `RunInfo` (pydantic, part of the manifest): `id: str` (non-empty), `profile: str = "default"`
  (non-empty), `fingerprint: str`, `commit: str | None = None`, `branch: str | None = None`,
  `dirty: bool | None = None`. `commit`, `branch` and `dirty` describe the *model* checkout, if
  the loader knows it; the Blick repository's state is recorded separately by blicket.
- `bk.fingerprint(*paths)` helps loaders: sha256 over each file's path relative to the given
  path, its size and its content, directories walked in sorted order, as a hex string. Relative
  names, so a run copied from the cluster to the laptop keeps its fingerprint; no files at all is
  an error rather than the hash of nothing. A loader may compute its own instead.
- The loader is called once per build and its wall time is recorded in the manifest.

### Tables

`blicket/tables.py` turns whatever a transformation returns into a polars frame and checks it
against the Blick's definition. blicket depends on polars only; pandas, pyarrow and xarray stay
the project's business and are never imported by blicket (the review found that pandas does not
require pyarrow and that remind-mfa's environment has none, so `pl.from_pandas` is out).

- **Conversion**, in this order: a polars `DataFrame` as is, a `LazyFrame` collected; a pandas
  frame (recognised by its type's module) is reset so that its index becomes columns when every
  index level is named, then built column by column from numpy arrays, with an ordered pandas
  Categorical becoming a polars `Enum` in its category order; an object with
  `__arrow_c_stream__` (pyarrow tables, duckdb relations) through `pl.DataFrame(obj)`; an object
  with `to_df()` (flodym arrays) or `to_dataframe()` (xarray) is converted and then handled as a
  pandas frame. Anything else is a transformation `error` naming the type. NaN in measure
  columns becomes null for every input, so the same data from pandas and polars hashes alike.
- **Roles.** A column bound to a dimension channel is a dimension; among the rest, float columns
  are measures and everything else a dimension; `dims=` and `measures=` on the Blick override
  either side (the other side is the remaining columns). A column named by both, or named but
  absent, is an error. Integer or boolean columns declared as measures are cast to float.
  Dimension columns may be string, Enum, int, bool, date or datetime; a polars Categorical is
  cast to string; every other type, float included, is an error that names the cast to apply.
  Dimension values are keys (the outer join of the comparison, the control values of the viewer),
  and float keys break equality after rounding and across libraries, so a float year is cast by
  the Blick, not accepted by blicket (decided in review round 1). A table may have no dimension
  (then at most one row).
- **Checks**, each a problem on the Blick, all collected before giving up, except that a
  `dims=` or `measures=` entry naming an absent column is reported alone, since every other check
  would only echo the typo: a plot channel maps a column that does not exist; a measure channel maps a dimension; a measure bound to no channel
  (decided in M0.1: nothing invisible is diffed; the message suggests unpivoting a wide table);
  the dimension values of a row are not unique; a `controls` key that is not an unbound
  dimension; an `order` or `defaults` key that is not a dimension. An `order` or `defaults`
  value that this run's table does not contain is a warning, since that is data, not definition.
- **Schema** recorded per Blick (`columns`): `dimensions: [{name, dtype, values}]` with the
  values in the Blick's `order` where given, else in the categories' order for an Enum or ordered
  Categorical input, else sorted; and `measures: [{name, dtype}]`. `dtype` uses blicket's own
  vocabulary (`string`, `integer`, `boolean`, `date`, `datetime`; measures `float`), not polars
  type names, so the manifest does not depend on the input library or the polars version
  (decided in review round 1). There is no `enum` dtype: Enum keys break joins when the categories
  differ and sort by category rather than value, so Enum and Categorical columns become strings
  and their order lives in `values` (review round 2). Datetimes are normalised to microseconds (a
  timezone-aware column is converted to UTC with a warning) and integers to 64 bits, so the same
  data from pandas and polars produces the same bytes.
- **Output**: dimension columns first (in `dims` order when given), then measures; rows sorted
  by the dimension columns, so a Parquet file is deterministic for equal content. Rounding, the
  zero floor and the treatment of `-0.0` are M0.4.

### Running the Blicks

For each buildable Blick, in registry order: call `transform(run)`, convert, check, write
`blicks/<id>.parquet` (zstd, the default) into the temporary build directory, record rows, the
table hash and the wall time. A raised transformation becomes a `Problem` of kind
`transformation` located by `tracebacks.locate` with the trimmed traceback; the Blick's entry
gets status `error` and no data. A transformation that mutates the run object is not detected
here (the fingerprint check is M2). Nothing a Blick does aborts the build.

The table hash in this task is `parquet-sha256:<hex>` over the written bytes: stable for equal
content within one polars version (verified), and the scheme prefix tells it apart from the
writer-independent content hash M0.4 introduces. Until then a polars upgrade changes every id,
which is acceptable because nothing is stored yet.

### Build id and directory

The id is the first 16 hex characters of a sha256 over the manifest itself, minus an explicit
exclusion list (`NOT_IN_ID` in `manifest.py`): timestamps and timings, the blicket version,
tracebacks, the run's id, paths and model checkout, the repository's branch and dirty flag, and
where Blicks are defined (`source`, `module`). Everything else, including `spec`, `config`,
`profile`, the fingerprint, the commit, the definitions, the table hashes and every problem's kind,
source and message, is in it (decided in review round 2, after an existing id was shown to serve a
stale report when only an error or the config had changed). A rerun that differs only in the
excluded fields is the same build; a dirty tree with equal content *is* the clean build.

The build is assembled in a `.tmp-<pid>-<token>` directory created with `mkdir` inside the
destination directory (same filesystem, so the final rename is atomic; `mkdtemp` would make it
0700, which a copy to a shared store would carry along), renamed to `<id>` at the end, and removed
if anything fails before the final directory exists. If `<id>` exists already the new directory
is removed and the command reports the existing build. The destination is
`<project root>/.blicket/build/`, or `--out DIR`. blicket writes `.blicket/.gitignore` containing
`*` whenever it is missing from the default destination (not under `--out`), so builds never
make the project's working tree dirty.

Repository state: `git rev-parse HEAD`, `git rev-parse --abbrev-ref HEAD` (a detached HEAD
records `null`) and `git status --porcelain` run in the project root; a project outside a git
repository, or in one without commits, records `null`s and a warning that says which.

### Manifest

`blicket/manifest.py`, pydantic, `spec = "0.1"`:

```
Manifest
  spec, blicket (version), created_at
  build: {id, incomplete, loader_ms}
  config: {tolerance, digits}     what the build was made with, so a stored build is self-describing
  run: RunInfo + {paths}          paths relative to the project when inside it, resolved otherwise
  repository: {commit, branch, dirty} | null
  groups: [Group]
  blicks: [BlickEntry]            one per defined Blick, built or not
  problems: [Problem]             file- and project-level, errors and warnings
```

`BlickEntry` is the one shape for a Blick in a build, in `model.py`, and also what the registry
holds for Blicks that failed at definition (there is no separate failed-Blick type): `id: str |
null`, `name`, `group`, `module`, `source`, `aliases`, `definition: BlickDefinition | null`,
`status` (computed: `"error"` when there are problems), `data: "blicks/<id>.parquet" | null`,
`hash`, `rows`, `columns: TableSchema | null`, `timing_ms`, `problems: [Problem]`. `RunInfo`
and the schema types live in `manifest.py` and `model.py`, so the module graph that reads a
manifest needs neither polars nor the loader machinery (the package `__init__` still imports
both for `bk.build`). Two containers, as decided: file-level problems make the build
`incomplete`; per-Blick problems set the entry's status.

The build directory reserves `compare/<baseline-id>/` for M0.6 and M0.7 (the comparison result
and the baseline tables of changed Blicks). Comparison output is additive: it never changes the
manifest or the id, and a build may hold comparisons against several baselines. What `push`
copies is M0.6's decision.

A test validates the written file with `jsonschema` against
`Manifest.model_json_schema(mode="serialization")` and compares a round trip through
`Manifest.model_validate_json` as JSON. No schema file is checked in and there is no `schema`
command; the model is the spec until the first release extracts one.

### CLI

`blicket build <run path>... [--project] [--out DIR] [--json] [-v]`. Text output as in the flow:
the `project:` line when the root is not the working directory, the run line (load time in
milliseconds below a second, import of the loader module included), the counts line (`N Blicks:
n built · n errors · n warnings`, plus `· n import errors · incomplete (Blicks missing)` when a
module failed to import), the build line, then the warnings and errors sections in the `list`
layout; the counts line lists errors, import errors, warnings, then `incomplete`. A project with
no buildable Blick writes no build and prints the `list` report instead, also under `--json`. `--json` prints
the manifest. Exit 0 when every Blick built and no file-level error exists, else 2. `list` keeps
its behaviour; its `--json` now prints `definition()` per Blick (own tags; the group's tags are in
`groups`) and keeps the absolute `root`, since it is a local report, not a build artefact.

## Affected areas

- New: `tables.py`, `builder.py` (named so because the exported function `bk.build` would
  shadow a module `build`), `manifest.py` (`Manifest`, `RunInfo`, `read`), `loader.py`
  (protocol, resolution, `RunSelection`, `fingerprint`), `tracebacks.py`.
- Changed: `model.py` (`BlickDefinition`, `BlickEntry`, the schema types, `Blick.entry()`),
  `errors.py` (pydantic `Problem`, `Source`, the `BlicketError` base), `assembly.py` and
  `definitions.py` (construct the new shapes), `discovery.py` (uses `tracebacks`), `config.py`
  (loader key format), `plots/_base.py` (`PlotDefinition`), `cli.py` (scaffolding, `build`),
  `__init__.py` (exports `RunInfo`, `RunSelection`, `fingerprint`, `build`, `BlickEntry`,
  `Build`, `Manifest`, the error types), `meson.build`, `pyproject.toml`
  (`polars>=2.0` runtime; `pandas`, `pyarrow`, `xarray`, `jsonschema` in the dev group for the
  conversion and schema tests), README (the build walkthrough).
- `docs/architecture.md`: one amendment, recorded when this lands: comparison results live
  outside the manifest, keyed by the baseline build id (decided 2026-10-23).
- `docs/plans/m0-tasks.md`: the Phase 1 departures noted above.

## Testing

Projects are generated in the tests, as in M0.1; a loader module written into the project root
returns a small dict-like run and a `RunInfo`.

- Loader: missing key, unimportable, raising, wrong return shape; `fingerprint` is stable,
  changes with content, and is unchanged when the run directory is copied elsewhere.
- Tables: each conversion path (polars, LazyFrame, pandas with a named MultiIndex, pandas with
  an unnamed filtered index, an ordered Categorical, a duck-typed `to_df` object, a duck-typed
  `to_dataframe` object, a pyarrow table through the Arrow stream, an unsupported type); role
  inference, both overrides and the dimension-channel rule; integer measure cast; NaN to null;
  each check as a problem and several at once; schema values ordered by `order=` and by Enum;
  deterministic output order.
- Build: a project with Blicks returning polars and pandas, one raising, one with an unbound
  measure, one with duplicate keys: manifest entries and statuses, Parquet files present for ok
  entries only, `incomplete` set when a module failed to import, the same inputs give the same id
  and an existing directory is left alone, a changed table and a changed profile change the id,
  git info inside a repository with a commit, in a detached HEAD, and outside a repository,
  `.blicket/.gitignore` written, no absolute path in the manifest, the manifest validates against
  its JSON Schema and round-trips.
- CLI: text output and exit codes for a clean and a failing build, loader failure on stderr,
  `--json` prints the manifest, `--out`, both commands go through the exit-code policy.
- Phase 1: `BlickOptions` keys equal the definition fields plus `id` and `aliases`;
  `typing.get_type_hints(Blick)` resolves; `list --json` golden updated once for the new
  `Problem`/`Source` shape and own tags.

## Out of scope

Canonical form and content hashes (M0.4); `controls` and `diff` (M0.5); the store and `diff`
(M0.6); baseline resolution and `check` (M0.7); the remind-mfa adapter (M0.3, for which this
task's loader protocol and pandas conversion are designed).

## Decided by Tobias on 2026-10-23

1. **`build` exits 2 when a transformation failed**, like every other error; the build directory
   is still written, so the good Blicks can be looked at.
2. **A measure column bound to no channel is an error**, confirmed.
3. **`--json` prints the manifest**, since it is the report.

## Decisions taken here, not asked

- `BlickDefinition`, `Problem` and `Source` are pydantic output shapes; input validation stays
  in `_validation.py`; `Blick` stays a dataclass with `definition()`.
- No pyarrow dependency: pandas frames are converted through numpy; Arrow objects through the
  PyCapsule interface.
- The loader returns a tuple `(run, RunInfo)`, as the architecture sketches; several run paths
  are passed as one selection; a loader failure stops the build before any directory exists.
- Table hash `parquet-sha256:` until M0.4; build id = 16 hex characters of sha256 over the
  manifest minus its exclusion list (see "Build id and directory").
- Builds are assembled in a temporary directory inside the destination and renamed; an existing
  id wins; `compare/<baseline-id>/` is reserved for later tasks.
- `.blicket/.gitignore` is written by blicket.

## Deviations

Recorded on 2026-10-23 by the implementer.

- **Exit-code policy** sits on the app's group class (`typer.Typer(cls=_App)`), so no command
  can miss it; the shared `-v` alias stores its value in click's shared `ctx.meta` for it. The
  test injects a failure into every registered command instead of checking a class.
- **`BlickOptions`** keys equal the model fields minus `group`, `module` and `source`: `id` is an
  option of the decorators, so it stays.
- **Shapes.** `Group` is a pydantic model too (the manifest and `list --json` embed it);
  `PlotSpec.to_json` went with the other `to_json` methods, replaced by a
  `PlotDefinition` model. `Source` keeps positional construction and sorting.
- **`tracebacks.py`** also holds `in_project` (used by discovery's purge) and `raised_at`, the
  "(raised at file:line)" suffix discovery and the build share. `project_traceback` keeps the
  whole traceback when no frame lies in the project, as for a loader installed elsewhere.
- **Checks added.** A dimension channel bound to a measure; with both `dims=` and `measures=`, a
  column in neither; any dimension type outside string, categorical, integer, bool, date, datetime
  (so float dimensions too, not only List, Struct, Object, Null); a non-numeric measure; a null in a
  dimension column; an empty table (a warning). An exception raised while converting a returned
  value (a failing `to_df()`) is located and traced like a raising transformation. The `loader` key
  is checked against `package.module:attribute`, dotted attributes allowed, in the config.
- **Build result.** `build(project, paths, *, out=None) -> Build(path, manifest, existed, root)`
  in `blicket/builder.py`; the manifest returned is always the one read back from the directory,
  so text and `--json` show the file, and for an existing id that build's. The text output adds
  the `project:` line, a warnings count and section, and file-level errors counted by kind;
  without git the run line says `no git commit` and a `repository` warning follows.

Added after review round 1:

- **Module `builder.py`**, not `build.py`: the exported function `bk.build` shadowed the module.
- **Manifest.** A `config` block records `tolerance` and `digits`. Schema dtypes use blicket's own
  vocabulary (dimensions `string`, `integer`, `boolean`, `date`, `datetime`; measures `float`),
  not polars' names. `manifest.py` does not import polars.
- **No buildable Blick:** `build` stops after discovery, prints the `list` report and writes
  nothing (exit 2).
- **Float dimensions stay rejected**, because dimension values are join keys and control values,
  and float keys break equality after rounding and across libraries; the message says so and
  names the cast.

Added after review round 2:

- **No `enum` dtype:** Enum and Categorical dimensions become strings, because Enum keys break joins
  between differing categories and sort by category; an Enum's categories become the implicit
  `order=` of its values.
- **Dimension types normalised:** integers to `Int64`, datetimes to naive `Datetime("us")`, a time
  zone converted to UTC with a warning.
- **One shape for a Blick in a report:** `BlickEntry` (in `model.py`, with `id`, `aliases`,
  `group`, `module`, `source` and a computed `status`) replaces `FailedBlick`; `Registry.failed`
  holds `BlickEntry`s and `bk.BlickEntry` is exported. `BlickDefinition` keeps only the other
  decorator options, and `list --json` prints a `BlickEntry` for built and failed Blicks alike,
  in definition order, as the manifest does.
- **`columns`** is the entry's table schema field, in the model and in JSON.
- **`RunInfo`** lives in `manifest.py`, so the spec module does not import the loader.
- **Run paths** are root-relative inside the project and resolved absolute outside it.
- **Build id** is a hash of the manifest without timestamps, timings, the blicket version,
  tracebacks, the run's id, paths and model checkout, the branch and dirty flag, and the Blicks'
  locations; so it covers `config`, `incomplete` and every problem's kind, source and message.
- **pandas index:** named levels become columns and unnamed levels are dropped silently; when a
  plot column is then missing, the error adds a hint about the dropped level.
- **`RunSelection`:** `labels` removed (nothing set or read it); `path` added for single-run
  loaders.
- **CLI:** `finish(text, failed)` replaces `emit`; a closed stdout pipe ends quietly with the
  command's exit code.
- **Build directory** is assembled in `.tmp-<pid>-<token>`, created with the umask's permissions;
  `.blicket/.gitignore` is written whenever missing, for the default destination only, not for
  `--out`.
- **Counts line:** `N Blicks: n built · n errors · n <kind> errors · n warnings · incomplete (Blicks
  missing)`.
- **Run checks:** `RunInfo` ids, profiles and fingerprints must be non-empty, `fingerprint` raises
  without files, and every run path is checked before the loader runs.
- **`Registry.tags_of`** removed; nothing outside the tests used it.
- **`BlicketError`** is the base of `ConfigError`, `LoaderError` and the build's own errors, with an
  optional traceback; the CLI has one clause for it.
- **`dims=` and `measures=` first:** a name of an absent column is the only error reported, since
  every role and check after it would be wrong.
- **Return values:** an empty frame is `the table has no columns`; a pandas or polars Series is told
  to `series.to_frame("value")`.
- **No git:** when git cannot run, the warning says so (`git cannot run (...)`), beside the ones for
  no repository and no commit.
- **Nothing a Blick does aborts the build:** the transformation, the conversion and the checks run
  in one guarded step.
- **Exports:** `Build`, `Manifest`, `NothingToBuild`, `LoaderError` and `BlicketError` join `bk`,
  since `bk.build` returns or raises them; `Manifest.has_errors` names what `failed` did.
