# M0.6 Store, `push` and `blicket diff`

Status: plan, 2026-10-24, revised the same day after an independent review that prototyped the
matching and the copy on the example builds. Sixth task of [m0-tasks.md](m0-tasks.md), building on
M0.5 (commit `0b96d2a`). Companion to [architecture.md](../architecture.md), "Store and baseline
resolution", "Change detection" and "Build directory"; where this plan fills in a detail, it says
so.

## Goal

Two builds of a project can be compared from the command line: `blicket diff <baseline> <current>`
matches the Blicks of two builds, runs each plot type's `diff`, sets the flags the architecture
defines (`new`, `removed`, `schema`, `value`, `error`), and prints the terminal summary with counts
per flag and the top movers, or the comparison as JSON, which is the comparison file format that
`check` (M0.7) will write next to a build. Builds can be pushed into a store, an immutable,
content-addressed copy, and named by id from there.

## The flows this task enables

1. **Two runs, compared.** The example has builds of runs 28 and 31 (unchanged reruns) and 34
   (`collection_rate` scaled by 0.9):

   ```
   $ uv run blicket diff .blicket/build/bfa7f61fc79b65c2 .blicket/build/34247dcb88fd54c3
   baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty)
   current  34247dcb88fd54c3 · run 2026-10-24--01-25-34_plastics_SSP2_h12 · blicks at fe4d2dd (dirty)
   10 Blicks: 9 unchanged · 1 value · 0 schema · 0 new · 0 removed · 0 errors
   top movers: flows/production_by_source 0.021 (Flow Primary, Time 2100, Region SSA)
   ```

   Runs 28 against 31 print `10 Blicks: 10 unchanged` and no movers. `--json` prints the
   comparison instead of the text. The exit code is 0; changes are an answer, not a failure
   (`check`, M0.7, is the guard that exits 1); 2 when a build cannot be read or the current build
   has errors, as `build` exits 2 for them.

2. **A Blick author renames a Blick** and keeps the old id in `aliases=`: the comparison matches
   the new id to the old table and reports it unchanged. A Blick whose transformation changed is
   `value` with its magnitude and the row that moved most; one that gained a scenario is `schema`
   with the values named; a new Blick is `new`; a deleted one is `removed`, unless a module of the
   current build failed to import or another file-level error occurred, or a current Blick has
   no usable id, in which case nothing is `removed` and the summary says why; a Blick whose
   transformation raised is `error`, and its baseline is not `removed`.

3. **Builds go into the store.**

   ```
   $ uv run blicket push .blicket/build/34247dcb88fd54c3
   build 34247dcb88fd54c3 → .blicket/store/builds/34247dcb88fd54c3
   $ uv run blicket push .blicket/build/34247dcb88fd54c3
   build 34247dcb88fd54c3 is in .blicket/store already
   $ uv run blicket diff bfa7f61fc79b65c2 34247dcb88fd54c3     # ids, looked up in the store
   ```

   The store holds the manifest and the tables of each build, nothing else. A build in the store
   can be served (`serve` answers from the installed viewer first).

4. **Later tasks build on it.** M0.7 resolves a baseline from the store by profile and git
   ancestry, runs the same comparison inside `check`, writes it into the build directory's
   `compare/<baseline id>/` with the baseline tables of the changed Blicks and `compare/index.json`,
   decides with that whether `push` copies `compare/`, exits 1 on flags, and renders `report.md`
   from the same `Comparison`; the viewer's toggle reads those files.

## Facts the plan rests on (checked 2026-10-24)

- A build directory holds `manifest.json`, `blicks/<id>.parquet` (in group subdirectories) and
  the viewer files listed in `viewer-version`; `compare` is a reserved name there. Entries keep
  their `id` (`None` when none was usable) and `aliases`, the former ids, whether or not the
  Blick built: a raised transformation leaves an entry with its id and no table. The registry
  checks that an alias names no current Blick. `BlickEntry.panels` gives the panel dimensions;
  `definition.tolerance` is the Blick's own or `None`, `config.tolerance` the project's;
  `build.incomplete` says a module failed to import; `Manifest.has_errors` decides `build`'s exit
  code. Every alias list in the example is empty, so the alias case needs a scratch project.
- `PlotType.diff(baseline, current, mapping, panels)` returns a `Change` with `schema`; the core
  sets `value` when the magnitude exceeds the tolerance, and `new`, `removed`, `error` (M0.5).
  `Change` is frozen; `model_copy(update=...)` adds flags; its flags serialise in a fixed order
  and round-trip. `builtin(name)` raises `DefinitionError` for an unknown plot type name, which
  is every project plot type until M4.
- `[tool.blicket] store` exists in the config with the default `.blicket/store`, relative to the
  project. `build()` writes `.blicket/.gitignore` only when it writes under `.blicket/build`; a
  project built with `--out` only has no ignore file, and git then lists an untracked
  `.blicket/store`, which makes every later build `dirty`.
- Copy modes, measured on 3.14: `shutil.copy` copies the source's mode, so a build written under
  umask 077 stays 0600 in a store meant to be shared; `shutil.copyfile` writes with the umask;
  `copytree` copies the directory stat whatever its `copy_function`. `mkdir` plus `copyfile`
  gives the store the modes the umask says. `builder.build` cleans its temporary directory in a
  `finally`.
- The comparison of the three example builds takes about 80 ms; its JSON is 4.4 KB for ten
  Blicks; 28 vs 34 gives one `value` on `flows/production_by_source` (0.021, Flow Primary,
  Time 2100, Region SSA), two magnitudes of 1e-16 with `where` set and no flag, and 0 elsewhere;
  28 vs 31 gives 0 everywhere. The newest example build by `created_at` is run 28's.
- `cli.py` holds the renderers of `list` and `build` (211 lines); the 29 CLI tests go through
  `CliRunner`, none calls a renderer directly.

## Approach

### `store.py`: `Store`

```python
class Store:
    def __init__(self, directory: Path): ...
    def push(self, build: Path) -> Pushed:      # Pushed(id, path, existed)
    def path(self, build_id: str) -> Path:      # raises BlicketError when the id is not in the store
```

`push` reads the manifest of `build` (a damaged directory is refused before anything is
written), makes a temporary directory under `<store>/builds/` with `mkdir`, copies
`manifest.json` and the files the entries' `data` name with `shutil.copyfile` (so the modes
follow the umask, and only the tables the manifest knows), and renames it to the build id; an
existing id is a no-op (`existed`), and so is a rename that finds the id there (a push race).
The temporary directory goes in a `finally`. Nothing else is copied: not the viewer files, not a
`compare/` directory. The store directory is created on first use, and the `.blicket/.gitignore`
that `build` writes is written by `push` too, through one shared helper, so a store under
`.blicket/` never makes the tree dirty. `store` from `[tool.blicket]` resolves against the
project root. Whatever walks `builds/` skips `.tmp-*`, as `serve` does. No listing yet: M0.7's
resolution needs profile, commit and `created_at`, so it will read manifests, not a list of ids.

### `comparison.py`: matching two builds

```python
def compare_builds(baseline: Path, current: Path) -> Comparison
```

Both manifests are read through `manifest.read`. Every current entry claims the baseline entries
named by its id and its aliases, whether or not it has a table, so a failed Blick is never also
`removed`; then, in the current manifest's order:

- An entry without a table (`status == "error"`, or no usable id) is `error`, nothing else.
- Its baseline entry is the one with the same id, else the first baseline entry whose id is
  among the entry's `aliases`. No match, or a match without a table, is `new`.
- A matched pair is diffed by the plot type the current definition names, with the current
  mapping and `entry.panels`; `value` is added when the magnitude exceeds the entry's tolerance
  (the current manifest's project tolerance when the Blick sets none). A plot type name this
  blicket does not know (every project plot type until M4) makes the entry `error` with a
  message; an unreadable table is a `BlicketError`.
- Baseline entries with a table that no current entry claimed are `removed`, listed after the
  current ones, unless the current build is `incomplete` or a current entry has no id: then none
  is, and `Comparison.incomplete` says so.

```python
class BuildRef(BaseModel):        # what the summary and the viewer show about a build
    id: str; run: str; profile: str; created_at: datetime
    commit: str | None; branch: str | None; dirty: bool | None

class BlickComparison(BaseModel):
    id: str | None                # the current id; the baseline id for a removed Blick
    name: str                     # as the entry has it, for entries without an id
    baseline_id: str | None       # when matched through an alias
    change: Change
    message: str | None = None    # for error: what went wrong in the comparison itself

class Comparison(BaseModel):
    spec: str; blicket: str; created_at: datetime
    baseline: BuildRef; current: BuildRef
    incomplete: bool              # removed not judged
    blicks: tuple[BlickComparison, ...]
    @property counts -> Counter[Flag]; movers(n) -> the n largest magnitudes among value
```

This is the comparison file format: `--json` prints it, `check` (M0.7) writes it. The blicket
version in it names the formula; the spec is the manifest's.

### `report.py`: the text renderers

The renderers of `list` and `build` move from `cli.py` into `report.py` as the plain functions
they are, with their helpers, and `render_diff(comparison) -> str` joins them: the two build
lines (id, run, profile, `blicks at <commit> (dirty)`), the counts line, the top three movers with
their `where`, a `schema` section naming the values that appeared or vanished per Blick, an
`errors` section with the messages, and the line "removed not judged: …" when `incomplete`.
`cli.finish(text, failed)` stays as it is; the `Report` protocol the M0.2 review suggested is
declined: no test calls a renderer directly, and `report.md` (M0.7) is one more function over
`Comparison`, not a protocol.

### Commands

- `blicket push BUILD_DIR [--project]`: the argument is required, since pushing is deliberate and
  "the newest" surprised on the example; prints the store path, or that the build is there already.
- `blicket diff BASELINE CURRENT [--json] [--project]`: each argument is an existing build
  directory, else a build id in the project's store (two directories need no project). Exit code
  0, or 2 when a build cannot be read or the current manifest `has_errors`.

### Not in this task, decided here

Writing the comparison next to the build (`compare/<baseline id>/`, the copied baseline tables,
`compare/index.json`), together with whether `push` copies `compare/` and what the user of
walkthrough 2 rsyncs: M0.7, with `check`, which is where the architecture puts it. Baseline
resolution by profile and ancestry, `check`, `report.md` and the exit code 1 (M0.7); the viewer's
comparison toggle and ghost layer (M0.7); a Blick that does not apply to a run as a status of its
own (M0.7, with `removed`); a remote store (the `Store` class is the seam); store `gc` (M4).

## Affected areas

- New: `store.py`, `comparison.py`, `report.py`, `tests/test_store.py`,
  `tests/test_comparison.py`.
- Changed: `cli.py` (two commands; the renderers moved out), `builder.py` (the ignore-file
  helper shared with the store), `tests/test_cli.py` (push and diff, the command set),
  `__init__.py` (exports `Comparison`), `meson.build`, README (push, diff, the store, the
  comparison format), `docs/architecture.md` (dated sentences: `diff` prints and exits 0 on
  changes; `check` writes the comparison), `docs/plans/m0-tasks.md` (M0.7 inherits the writing).
- `examples/remind-mfa/README.md`: the diff of two runs as the example's second command.

## Testing

- `Store`: push copies the manifest and the entries' tables only, with the umask's modes (a
  source file at 0600 under umask 022 arrives at 0644); pushing twice is a no-op reporting
  `existed`; a damaged build directory is refused before writing; `path` of an unknown id
  raises; the ignore file is written; `.tmp-*` is skipped.
- `compare_builds`, on build directories made by `build()` on scratch projects as the build tests
  do (two builds cost about 0.1 s): unchanged, a changed transformation (`value`, the magnitude,
  `where`), a new dimension value (`schema`), a per-Blick tolerance that turns a small change into
  `value`; and, by editing a copied manifest (about fifteen lines, since the comparison checks
  neither hashes nor the id): a Blick renamed with an alias (matched, unchanged), a new Blick, a
  removed Blick, a removed Blick when a module failed to import (`incomplete`, nothing removed), a
  failing transformation whose baseline exists (`error`, not `removed`), two error entries
  sharing a claimed id, an entry without an id (nothing removed), an unknown plot type name
  (`error` with a message).
- CLI: `push` and its no-op text, `diff` with directories and with ids, a directory beside an id,
  `--json` round-trips to `Comparison`, the exit codes, the summary text of the example-like
  cases, the command set.
- By hand, recorded here: `push` of the three example builds, `diff` 28 vs 31 and 28 vs 34, the
  summary and the JSON.

  Checked by hand on 2026-10-24, after review round 1, from `examples/remind-mfa` after
  `uv sync --frozen --reinstall-package blicket` and with a fresh store: `uv run blicket push
  .blicket/build/<id>` for the builds of runs 28, 31 and 34 printed `build <id> →
  .blicket/store/builds/<id>` each, a second push of 34 `build 34247dcb88fd54c3 →
  .blicket/store/builds/34247dcb88fd54c3 (in the store already)`; each stored build holds
  `manifest.json` and its ten tables, 604 KB against 2.5 MB for the build directory with the
  viewer, with modes 0755 and 0644, and `builds/` holds the `.gitignore`; `blicket serve
  .blicket/store/builds/<id>` serves a stored build. `diff bfa7f61fc79b65c2 9bb88a679a29a905`, by
  id from the store, printed the two build lines and `10 Blicks: 10 unchanged`, exit 0;
  `diff bfa7f61fc79b65c2 34247dcb88fd54c3` printed `10 Blicks: 9 unchanged · 1 value` and
  `top movers: flows/production_by_source 0.021 (Flow=Primary, Time=2100, Region=SSA)`, exit 0,
  the same with the baseline given as its build directory; `diff deadbeef …` said `deadbeef is
  neither a build directory nor the id of a build in .blicket/store (blicket push adds one)`. The
  JSON is 4.7 KB (4.4 KB for 28 vs 31): `spec`, `blicket`, `created_at`, `baseline` and `current`
  (`id`, `run`, `profile`, `created_at`, `repository` with `commit`, `branch` and `dirty`,
  `incomplete`), `incomplete` empty, and ten `blicks` with `id`, `name`, `matched`, `change` (the
  `Change` fields) and `message`; the mover has magnitude 0.020961, two flows 1.1e-16 and 1.2e-16
  with `where` set and no flag, the others 0.0 with `where` null. A diff takes about 0.3 s,
  Python's start included.

## Decided by Tobias on 2026-10-24

1. **`blicket push` is a command now**, not only `check --push` in M0.7.
2. **`diff` exits 0 when it finds changes**, 2 only when a build cannot be read or the current
   build has errors; `check` (M0.7) is the guard that exits 1.

## Decisions taken here, not asked

- `diff` prints and writes nothing: the comparison next to a build, the copied baseline tables
  and `index.json` belong to `check` (M0.7), which also decides what `push` copies; writing from
  `diff` would mutate store builds and make the local build and its store copy drift.
- The `Report` protocol is declined; the renderers are plain functions in `report.py`.
- Matching by id, then by the current entry's aliases, claimed by every current entry; `removed`
  only for baseline Blicks that had a table; `incomplete` or an entry without an id disables
  `removed`. Three top movers, among the Blicks flagged `value`.
- `push` takes its argument; `Store` has `push` and `path` only.

## Deviations

- `push` writes the `.gitignore` (`*`) into `builds/` when it creates it, not into `.blicket/`:
  `Store` knows only its directory, and a store directory that exists, maybe tracked, keeps its
  other files in git; `build` writes `.blicket/.gitignore` itself, so there is no shared helper.
- `push` refuses a build id that does not match `manifest.BUILD_ID` (what `content_id` returns), a
  table that is not a regular file inside the build directory, and a `builds/<id>` without a
  manifest; `BlickEntry.data` must be a relative path without `..` or NUL for every reader of a
  manifest; `Store.path` and `diff` take `BUILD_ID` ids only, which skips `.tmp-*`.
- `diff` exits 2 on `Comparison.has_errors`: removed not judged, or a Blick flagged `error`, so
  also for an unknown plot type or tables its `diff` rejects (`ValueError`, `TypeError`), which
  the current manifest's `has_errors` does not cover.
- A current entry has no table when its `data`, `id` or `definition` is `None`, not by
  `status == "error"`; the two agree for every manifest blicket writes.
- The comparison's shape, from the review: `BlickComparison.matched` instead of `baseline_id`
  (M0.7 may need a baseline build per Blick); `BuildRef.repository` instead of commit, branch and
  dirty flag, and `BuildRef.incomplete`; `Comparison.incomplete` holds the reasons, empty when
  removed was judged; `Comparison.has_errors`; `message` also carries the first line of the error
  of a Blick that did not build.
- The summary: the build lines carry the profile, as "Approach" says (the sample under flow 1
  lacks it), and `incomplete (Blicks missing)`; zero counts are left out; `removed not judged`
  takes the place of the removed count, its reasons on the next line; `where` reads
  `name=value`; `new` and `removed` sections name the Blicks; value lists stop after five and more
  than three movers after the third, each with "… and N more".
- `push` of a build already in the store prints its path with `(in the store already)`.
- `manifest.read` checks the spec before validating, so a build of another spec says "is spec X;
  this blicket reads Y: rebuild the run".
- A `diff` argument that is neither a build directory nor the id of a build in the store says so,
  with the store relative to the working directory, or that without a project there is no store.
- The match is made among the baseline entries that have a table, by id, then by the aliases in
  order, so an alias with a table wins over the id without one ("Approach" matches first and calls
  a table-less match `new`); a `new` Blick whose baseline entry had no table carries the message
  "did not build in the baseline".
- The README's Python snippet that compared two builds' tables (M0.5) gave way to `blicket diff`;
  the plot type's `diff` stays documented in the docstrings and `bk.Change`.
