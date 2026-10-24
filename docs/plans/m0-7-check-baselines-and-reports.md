# M0.7 Baseline resolution, `blicket check` and reports

Status: plan, 2026-10-24, revised the same day after an independent review that prototyped the
resolution on this repository's history and the written layout on the example. Seventh task of
[m0-tasks.md](m0-tasks.md), building on M0.6 (commit `604e20c`). Companion to
[architecture.md](../architecture.md), "Store and baseline resolution", "Guard", "Build directory"
and walkthrough 2; where this plan fills in or changes a detail, it says so.

## Goal

One command does the guard's job: `blicket check <run dir>` builds the run, finds its baseline in
the store (by run profile and the git ancestry of the Blick repository, or as told by
`--against`), compares the two builds with M0.6's comparison, writes the comparison next to the
build so that a build directory carries its own verdict and the baseline tables of what changed,
prints the summary, writes `report.md` (and appends it to GitHub's step summary when that is
set), pushes its build when asked, and exits 0 when nothing is flagged, 1 when something is,
2 on errors. The viewer's half, reading the comparison from the build directory (the overview's
colouring and ranking, the comparison toggle with the ghost layer, the diagnostics strip), is the
task after this one, so that each has one implementer.

## The flows this task enables

1. **The guard on a run, as walkthrough 2 has it.** In the example the three builds are pushed;
   all three record the commit `fe4d2dd` (dirty), an ancestor of HEAD:

   ```
   $ uv run blicket check ../../data_out/2026-10-24--01-25-34_plastics_SSP2_h12
   run 2026-10-24--01-25-34_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 604e20c (dirty) · loaded in 0.9 s
   10 Blicks: 10 built
   build 7c1d… → .blicket/build/7c1d…
   baseline bfa7f61fc79b65c2 · run 2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty)
   10 Blicks: 9 unchanged · 1 value
   top movers: flows/production_by_source 0.021 (Flow=Primary, Time=2100, Region=SSA)
   comparison → .blicket/build/7c1d…/compare/bfa7f61fc79b65c2
   exit 1
   ```

   The baseline is the newest pushed build of the same profile whose commit is the current
   build's commit or one of its ancestors, the current build itself excluded; a build whose
   manifest says it is incomplete is never a baseline. On a pull request branch that means the
   branch's own previous pushed build, so a change shows once and then reads as unchanged;
   `--against main` keeps the branch compared with main until the merge, which is what CI wants.
   `--against` takes a build id in the store, a build directory, or a git ref (`main`,
   `origin/main`, a tag, a commit). `--push` pushes the build afterwards, comparison included.
   `--json` prints the comparison.

2. **No baseline.** The first `check` of a profile prints `baseline: none (no pushed build of
   profile X)`, writes no comparison, and exits 0: nothing to compare is not a change. When
   pushed builds of the profile exist but none of their commits is known to this clone, `check`
   says so and exits 2, since that is a shallow clone (`fetch-depth: 0` in GitHub Actions) or an
   unfetched history, and a guard that silently passes is worse than one that fails.

3. **A rerun.** `check` on an unchanged run whose previous build of another run id was pushed
   reports `10 unchanged` and exits 0; a retry of the same run after a failed `check --push`
   finds the same baseline as the first attempt, not itself.

4. **In CI.** `report.md` is appended to `$GITHUB_STEP_SUMMARY`; the exit code fails the job on
   flags; the pushed build is what the viewer shows on the laptop after an rsync of
   `builds/<id>/`, comparison included.

## Facts the plan rests on (checked 2026-10-24)

- `compare_builds(baseline, current) -> Comparison` (M0.6) compares two build directories; a
  `Comparison` is the file format, with `has_errors`, `counts` and `movers`. `render_diff`
  renders it; `Store.push` copies the manifest and the tables of a build, checking each is a
  regular file inside it; `Store.path(id)` finds a stored build; `BUILD_ID` names the id's shape.
  `build()` returns `Build(path, manifest, existed, root, viewer)`; the manifest records
  `run.profile`, `repository.commit` (or `None` outside git), `created_at` and
  `build.incomplete`. A rebuild of an existing id keeps the old `created_at`.
- `git merge-base --is-ancestor <commit> <tip>` exits 0 when `<commit>` is `<tip>` or an ancestor,
  1 when not, 128 when a commit is unknown to the clone; `git rev-parse --verify -q <ref>^{commit}`
  exits 1 for an unknown ref; `git rev-parse --is-shallow-repository` says whether the clone is
  shallow. In a depth-1 clone, GitHub Actions' default, every older commit is unknown and
  `main` does not resolve. One `is-ancestor` call takes about 2 ms; reading the three example
  manifests 1 ms.
- The example's three pushed builds all record `fe4d2dd` (dirty) and are all ancestors of HEAD
  `604e20c`; the newest by `created_at` is run 28's `bfa7f61fc79b65c2`; `main` is at `1072016`,
  so `--against main` finds nothing in the example and the by-hand check uses the branch name.
  `compare_builds` of a build with itself gives `10 unchanged`.
- `compare` is a reserved name in a build directory; `viewer.copy` touches only the files it
  listed, so `compare/` survives a viewer refresh; `serve.newest_build` goes by `created_at`.
  The viewer caches tables by path and hash; `serve`'s no-cache set holds `index.html` and
  `manifest.json` only.
- For 28 vs 34 the written comparison is 34 KB (the one changed table 29 KB, the JSON 5 KB)
  against a 594 KB build. `GITHUB_STEP_SUMMARY` names a file GitHub Actions renders as the job
  summary; appending Markdown to it is the documented use.
- A scratch git repository with a branch and a merge costs about 20 ms in a test; a two-Blick
  scratch build 20 to 30 ms.

## Approach

### Listing the store, resolving the baseline

`Store.list() -> list[Stored]`, `Stored(id, path, manifest)` for every
`builds/<id>/` whose name is a `BUILD_ID` and whose manifest reads with this spec; a manifest of
another spec is skipped and counted, a damaged one skipped with a warning line (one damaged
build must not block the guard; a spec bump must not warn for every old build).

`baseline.py`: `resolve(store, built: Manifest, root, against) -> Resolution`, a small module
of its own, so that git stays out of `Store`, the remote seam:

- `against` a build id in the store, or a build directory: that build, whatever its profile (the
  baseline line shows the profile when it differs).
- Else the tip: `built.repository.commit` by default (no second git call; `None` means outside
  git, where only an explicit build works, and `check` says so), or the commit `against`
  resolves to as a ref; an unresolvable ref is an error.
- Candidates: the stored builds of `built.run.profile` other than the current build's own id and
  not incomplete, newest `created_at` first; the baseline is the first whose commit is the tip
  or its ancestor (`is-ancestor`, run in `root`). A build without a commit is never one. The
  scan stops at the first hit. Dirty builds are candidates like any other.
- `Resolution` carries the baseline (`Stored | None`) and, when none, why: no build of the
  profile, or builds whose commits are unknown to this clone (the count, and whether the clone
  is shallow), which `check` reports with exit 2.

Per-Blick fallback to older candidates (the architecture's carry-over) is not built: on the
example every Blick's fallback came out empty, an incomplete newest baseline is excluded by the
rule above, and carry-over pays off over accepted baselines, which belong to the deferred accept
design (open question 4). `compare_builds(baseline, current)` stays as it is.

### `check`

`blicket check <run dir>... [--against <build id|dir|ref>] [--push] [--json] [--out] [--project]`:

1. `build()` as `build` does; print the build report.
2. Resolve; print `baseline <id> · run … · blicks at …` (plus `· profile …` when it differs), or
   `baseline: none (…)`, which also goes to the step summary.
3. With a baseline: compare, write the comparison into the build directory (below), print the
   comparison's summary lines after the build report without repeating what it printed (the
   current build's line, and the errors of Blicks that did not build, which the build report
   lists; errors the comparison alone finds, such as an unknown plot type, stay), then
   `comparison → <dir>`.
4. `--push`: `Store.push`, comparison included, and its line; pushed whatever the exit code, so
   that CI keeps what it checked.
5. Exit 2 when the build `has_errors`, the comparison `has_errors`, or the baseline could not be
   resolved for a reason (unknown commits, an unresolvable ref, outside git without an explicit
   build); else 1 when any Blick carries a flag; else 0. `--json` prints the comparison, or
   `null` without a baseline.

### The comparison in the build directory

`comparison.write(comparison, baseline_dir, current_dir)` puts `comparison.json` into
`<current>/compare/<baseline id>/`, copies the baseline tables of the Blicks flagged `value` or
`schema` to `compare/<baseline id>/blicks/<current id>.parquet` (named by the current id, also
for an alias match; the site stays self-contained but small), writes `report.md` beside the
JSON, and regenerates `compare/index.json` from the directory: the baseline ids ordered by their
comparison's `created_at`, newest last (the viewer cannot list a directory over HTTP; the
filesystem can, so no merge logic). Each `BlickComparison` gains `baseline_data: str | None`,
the copied table's path relative to the build directory, and `baseline_hash: str | None`, the
baseline entry's table hash, which the viewer's table cache keys on. A second `check` against the
same baseline replaces that one directory. `comparison.json` is the comparison file (the
architecture's `report.json`); nothing else is written. `serve` sends `compare/index.json` and the comparison files with `no-cache`, since
`check` rewrites them.

`Store.push` copies `compare/` along with the manifest and the tables: `index.json`, and per
baseline `comparison.json`, `report.md` and the `baseline_data` files the comparison names, each
checked as the tables are. A build the store holds already is left as it is, comparisons
included (adding comparisons to a stored build is a second write path with a race of its own;
deferred until a build is checked against a second baseline in practice).

### `report.md`

`render_markdown(comparison) -> str` in `report.py`: a heading with the two builds, the counts
line, a table of the flagged Blicks (name, flags, magnitude, where), the schema details and the
errors, in the text's order. Appended to the file `GITHUB_STEP_SUMMARY` names when set; the
`baseline: none` line likewise.

### Not in this task, decided here

- The viewer's half (overview ranking and colouring by flag, the comparison toggle and the ghost
  layer from `compare/<id>/blicks/`, the diagnostics strip at `where`, reading `compare/index.json`
  and `baseline_hash`): the next task.
- Per-Blick fallback to older baselines: deferred to the accept design (open question 4).
- Adding comparisons to a build already in the store: deferred (above).
- A Blick that does not apply to a run (a plastics Blick on a steel run): waits for the
  multi-model example. The constraint it leaves: such a Blick stays in the manifest with a status
  of its own, so it is neither `error` nor `removed`; and a Blick that built in the baseline but
  is skipped now, in the same profile, must be reported, not ignored.
- Acceptance (which builds are candidates once reviews exist), the PR comment, a remote store.

## Affected areas

- New: `baseline.py`, `tests/test_baseline.py`, `tests/test_check.py`.
- Changed: `store.py` (`list`, `push` with `compare/`), `comparison.py` (`baseline_data`,
  `baseline_hash`, `write`), `report.py` (`render_markdown`; the summary lines reusable without
  the build lines), `cli.py` (`check`), `serve.py` (no-cache set), README (check, the comparison
  directory, `report.md`, exit codes, shallow clones), `docs/architecture.md` (dated sentences:
  `report.json` is the comparison file; `push` copies `compare/`; fallback deferred; the current
  build excluded), `docs/plans/m0-tasks.md` (M0.7 built; the viewer half as the next task; M0.8),
  the example README (the check walkthrough), `tests/test_store.py`, `tests/test_comparison.py`,
  `tests/test_cli.py`.

## Testing

- Resolution, on store manifests written with explicit `created_at`, commit and profile (as
  `test_comparison` edits copied manifests) over a scratch git repository made in the test: the
  newest build of the profile on the tip's history wins; another profile resolves its own; the
  current id is excluded; an incomplete build is skipped; an unrelated commit is not a candidate;
  a build without a commit is not; `--against <id>`, a directory, and a ref; an unresolvable ref
  is an error; unknown commits give the reason and count; a shallow clone is named; another-spec
  and damaged manifests are skipped as planned; no build of the profile gives none.
- One CLI test with a real branch and merge: the feature branch resolves main's build, and after
  the merge main sees the branch's build.
- `write`: the JSON, the copied tables of changed Blicks only (named by the current id),
  `baseline_data` and `baseline_hash` set for them, `index.json` regenerated and ordered,
  `report.md` present, a second write replaces the directory.
- `push` with `compare/`: copied for a new build with its files checked; a stored build is left
  as it is.
- `check` through the CLI on scratch projects: unchanged run exits 0; a changed transformation
  exits 1 with the flags and magnitude; a failing Blick exits 2 and its error appears once; no
  baseline exits 0 and writes no comparison, `--json` prints `null`; unknown commits exit 2;
  `--push` pushes on exit 1; `GITHUB_STEP_SUMMARY` set to a temporary file receives the Markdown;
  outside git without `--against` exits 2 with the message.
- `render_markdown`: one rendered example, checked for the table and the sections.
- By hand, recorded here: `check` of run 34 against the example's pushed builds, with the
  branch name for `--against`, the written directory's contents and sizes, `report.md`, a
  `--push`.

  Superseded by the next paragraph; kept for the resolution and the sizes, which stand. Checked by
  hand on 2026-10-24, before the reviews, from `examples/remind-mfa` after `uv sync --frozen
  --reinstall-package blicket` (the text of `check`, `report.md` in the build directory and the
  push line described here are no longer what blicket does), with `BLICKET_VIEWER` set and the store holding the builds of runs
  28, 31 and 34 (all at `fe4d2dd`, dirty): `uv run blicket check
  ../../data_out/2026-10-24--01-25-34_plastics_SSP2_h12` built `c6317235ed070309` (at `604e20c`,
  dirty) in 2.0 s wall time and printed `baseline bfa7f61fc79b65c2 · run
  2026-10-24--01-25-28_plastics_SSP2_h12 · blicks at fe4d2dd (dirty)`, `10 Blicks: 9 unchanged · 1
  value`, `top movers: flows/production_by_source 0.021 (Flow=Primary, Time=2100, Region=SSA)` and
  `comparison → .blicket/build/c6317235ed070309/compare/bfa7f61fc79b65c2`, exit 1. That directory
  holds `comparison.json` (5,437 B), `report.md` (548 B) and
  `blicks/flows/production_by_source.parquet` (29,435 B, byte-identical to run 28's stored table,
  named in `baseline_data` with its `baseline_hash`); with `index.json` (21 B), `compare/` is
  35 KB against 594 KB of manifest and tables (2.5 MB with the viewer). `report.md` has the
  heading, the two build lines, `10 Blicks: 9 unchanged · 1 value` and the one-row table
  `| flows/production_by_source | value | 0.021 | Flow=Primary, Time=2100, Region=SSA |`.
  `--against m0-1-skeleton-and-registry` found the same baseline, exit 1; `--against main` printed
  `baseline: none (no pushed build of profile plastics_SSP2_h12 at main or an ancestor of it)`,
  exit 0, since `fe4d2dd` is not on main; `--against 9bb88a679a29a905` compared with run 31, with
  the same summary, and `index.json` then listed both baselines. `--push` printed `build
  c6317235ed070309 → .blicket/store/builds/c6317235ed070309`, exit 1; the stored build holds the
  manifest, the ten tables and `compare/` with both comparisons, 665 KB. A retry without `--push`
  found `bfa7f61fc79b65c2` again, not the build it had pushed. Nothing in the store was deleted.

  Checked again on 2026-10-24 after review round 2, same setup; the store had meanwhile gained
  run 34's build `c6317235ed070309` (the push above) and run 31's build `094957f412733012`, both at
  `604e20c`, pushed during the reviews. `check` of run 34 printed:

  ```
  run 2026-10-24--01-25-34_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 604e20c (dirty) · loaded in 643 ms
  10 Blicks: 10 built
  build c6317235ed070309 → .blicket/build/c6317235ed070309 (built before, left as it was)

  baseline 094957f412733012 · run 2026-10-24--01-25-31_plastics_SSP2_h12 · blicks at 604e20c (dirty) · built 2026-10-24 20:02 UTC
  vs baseline: 9 unchanged · 1 value
  top movers: flows/production_by_source 0.021 (Flow=Primary, Time=2100, Region=SSA)
  flagged: 1 of 10 Blicks
  comparison → .blicket/build/c6317235ed070309/compare/094957f412733012
  ```

  exit 1: its own stored build excluded, run 31's newer build wins. That directory holds
  `comparison.json` (5,437 B) and the copied table (29,435 B). `--against main` printed `baseline:
  none (4 pushed builds of profile plastics_SSP2_h12, none at main (1072016) or its ancestors)`,
  exit 0; `--against nonsense --json` printed `null` on stdout and the report ending in `error: no
  baseline: nonsense is neither a build directory, a build in the store, nor a git ref` on
  stderr, exit 2. `--push` printed `build c6317235ed070309 →
  .blicket/store/builds/c6317235ed070309 (in the store already, left as it was; comparisons are
  not added to a stored build)`, exit 1. Under `LC_ALL=C` with `GITHUB_STEP_SUMMARY` set, the
  summary was appended in UTF-8, exit 1. Nothing in the store was deleted.

## Decided by Tobias on 2026-10-24

1. **No baseline exits 0** and writes no comparison; builds of the profile whose commits this
   clone does not know exit 2.
2. **Split**: the viewer's comparison half is the task after this one.
3. **`push` copies `compare/`** on the first push of a build; a build already in the store is
   left as it is, comparisons included.
4. **Per-Blick fallback to older baselines is deferred** to the accept design; the architecture's
   sentence is amended. A Blick the baseline lacks is `new`.

## Decisions taken here, not asked

- Candidates are the stored builds of the same profile, not the current build, not incomplete,
  newest first; the first on the tip's history wins; dirty builds count; a build without a
  commit never does.
- The tip is the current manifest's commit; `--against` takes an id, a directory or a ref.
- `comparison.json` is the comparison file (the architecture's `report.json`); the Markdown
  summary goes to the step summary only (see Deviations); `index.json` is regenerated from the directory; copied tables are named by the
  current id and carry the baseline hash.
- Resolution lives in `baseline.py`; `Store` lists, git stays out of it.
- The skip status is deferred with its constraint stated.

## Deviations

The body above predates these deviations: where it has `report.md` written into the build
directory, pushed and tested (the Goal, flow 4, "The comparison in the build directory", `push`,
"Testing" and the by-hand item), the deviation on `report.md` below applies.

- `Store.list` returns a `Listing` (the builds, the count of another spec, the messages of the
  damaged ones) instead of `list[Stored]`, since the count and the warnings must reach `check`;
  `manifest.read` raises the subclass `OtherSpec` for another spec to tell the two apart.
  `resolve` takes that listing, not the store, and `check` prints the warnings.
- `report.md` is not written into the build directory: the comparison file is the record, and
  the Markdown summary, derived from it, goes to `$GITHUB_STEP_SUMMARY` only, appended after the
  push; a summary that cannot be appended is a warning line.
- Unknown commits: newest first, each candidate's commit is classified with `git cat-file -e
  <commit>` (exit 1: the clone lacks it; the `^{commit}` form exits 128 on git 2.56) before
  `is-ancestor`. Resolution fails only when no candidate is on the tip's history and the clone
  lacks the commits of some (the shallow clone); when a baseline is found, newer candidates at
  commits the clone lacks are skipped with a warning line, so that a build pushed from a laptop
  at an unpushed commit does not fail every other clone. Both texts name the builds, five at
  most, by their full id (so that it can be passed to `--against` as is) and short commit, and end
  with "fetch the full history: git fetch --unshallow, or fetch-depth: 0 in GitHub Actions, or
  name the baseline: --against <id>". An `--against` ref that does not resolve in a shallow clone
  gets the same hint. Every git call treats an exit code other than 0 and 1 as an error quoting
  git's first line, so outside a repository `--against <ref>` is an `error:` line.
- Outside git: with no other pushed build of the profile, `baseline: none (no other pushed build
  of profile X)`, exit 0; with pushed builds, they are named (five at most) with "pass it" or
  "pass one as --against", exit 2.
- Pushed builds of the profile none of which is on the tip's history give `baseline: none (N
  pushed builds of profile X, none at <ref> (<commit>) or its ancestors)` and exit 0; exit 2
  needs a commit the clone lacks. Without any candidate, the reason reads "no other pushed build"
  and adds the incomplete builds and the builds of another spec skipped.
- `--against` is tried as a build directory (one holding `manifest.json`), then as an id in the
  listing, then as a git ref.
- `compare/index.json` is regenerated from the `compare/<build id>/` directories holding a
  `comparison.json`, ordered by that file's modification time, and nothing reads it in blicket;
  `push` copies `compare/` as a walk of its regular files, names starting with a dot skipped, each
  checked as the tables are. `baseline_data` has the inside-the-build check of `BlickEntry.data`
  (the `BuildPath` type in `model.py`).
- `serve` sends every `.json` under `compare/` with `no-cache`.
- The text of `check`: a blank line after the build report; the baseline line ends with `built
  <time> UTC` and shows the profile only when it differs; the counts read `vs baseline: …`;
  `flagged: N of M Blicks`, `nothing flagged`, or `nothing flagged, but the build is incomplete`
  comes before `comparison →`; the push line names the comparisons pushed; the comparison's
  sections come last; a summary that cannot be appended is a warning at the end. Shortened lists
  carry the pointer "(all in --json)" in `diff`'s text only (its movers and its lists of values),
  never in `check`'s or the Markdown; movers equal to two significant digits go by name.
  `--json` puts the report on stderr and prints `null` for every failure, a build with no
  buildable Blick included.
- `push`'s own output: the comparisons pushed, or, for a build the store holds, "(in the store
  already, left as it was; comparisons are not added to a stored build)".
- `write` refuses a comparison whose baseline or current id is not shaped like a build id, since
  the baseline id names a directory it replaces.
- The reasons why removed Blicks were not judged carry the first line of the import error
  (`blicks/d.py failed to import: ModuleNotFoundError: …`), in `diff`, `check` and the Markdown.
- The Markdown summary: a level-3 heading naming run and short build id on each side, the build
  lines as a list, the counts, a table of every flagged Blick, largest magnitude first (ids in
  backticks, `–` for an empty cell, `|` escaped), then `schema`, `new` (those that did not build
  in the baseline) and `errors` sections. The reasons why removed Blicks were not judged, such as
  a module that failed to import, lead the `errors` section, in place of the text's `removed not
  judged:` line. Without a baseline, the summary is the heading with the current build and the
  line saying why.
- `errors.os_reason` is the one helper that words an `OSError` with its file, used by `Store.push`
  and `comparison.write`.
- `build`'s run argument and `--out` became the aliases `RunsArgument` and `OutOption`, shared
  with `check`, as is the handling of a build with no buildable Blick; `finish` gained `flagged`
  for exit 1.
- The next task is named M0.7b in `m0-tasks.md`; `architecture.md` also says, under M1, that the
  comparison toggle comes with it.
