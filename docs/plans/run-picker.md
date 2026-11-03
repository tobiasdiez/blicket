# The run picker, and `blicket` as `blicket dev`

Status: built 2026-11-03 on `e09ae62` through the feature loop with two review rounds and a
verification of the third, uncommitted; the outcome, the deviations and the follow-ups are at the
end. The plan was revised the same day after an independent review that prototyped the alias
rule on typer 0.27.3, a second `dev.start` in a worker thread and `builder.prepare` without paths. Tobias asked that a bare `blicket` start `blicket dev`, that
`blicket dev` without a run path offer a run picker, and that `blicket runs/x` mean `blicket dev
runs/x`. The architecture's run picker ("Run discovery and labels", "Blick builder (dev mode)",
walkthrough 3) is the starting point; where this plan departs from it, it says so.

## Goal

`blicket` in a project starts the dev server. Given no run, the viewer opens on a list of the
project's runs, newest first; you pick one (or several, for a loader that combines them), and the
run is loaded, built and checked as `blicket dev <run>` does today, then the catalog shows. From
then on the session is the one `blicket dev <run>` gives. `blicket <run>` is `blicket dev <run>`.

## The flows

### 1. Start without a run

```
$ cd examples/remind-mfa
$ uv run blicket
runs: 5 in ../../data_out/*_plastics_*
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
pick a run in the viewer, or pass one: blicket dev RUN_PATH
```

1. The browser shows the picker, `#/runs` (the shell sends every route there while no run is
   served), under the usual header without sidebar and run:

   ```
   blicket                                                          ◐
   ─────────────────────────────────────────────────────────────────────
   Pick a run
   Folders that runs = ["../../data_out/*_plastics_*"] matches, newest first.

   ☐ 2026-10-26--11-25-13_plastics_SSP2_h12                 8 days ago
   ☐ 2026-10-26--11-25-00_plastics_SSP2_h12                 8 days ago
   ☐ 2026-10-24--01-25-34_plastics_SSP2_h12                10 days ago
   ☐ 2026-10-24--01-25-31_plastics_SSP2_h12                10 days ago
   ☐ 2026-10-24--01-25-28_plastics_SSP2_h12                10 days ago

   [Load]                                                   [↻ Refresh]
   ```

   A row shows the folder's name and when it last changed; its path is the row's tooltip. `Load`
   is disabled until a row is ticked; it reads `Load 2 runs as one` when two are.
2. You tick the first and press `Load`. The button spins, the list is disabled, and a line says
   `Loading 2026-10-26--11-25-13_plastics_SSP2_h12; the loader's output goes to the terminal.`
   The terminal prints what `blicket dev <run>` prints today, under a time stamp:

   ```
   11:02:14 loading /home/…/data_out/2026-10-26--11-25-13_plastics_SSP2_h12, picked in the viewer
   run 2026-10-26--11-25-13_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at e09ae62 · loaded in 672 ms
   10 Blicks: 10 built
   build 2224d63eb5ef42e1 → .blicket/build/2224d63eb5ef42e1

   baseline 976f428f3d33dbdf · run 2026-10-26--11-25-00_plastics_SSP2_h12 · …
   vs baseline: 10 unchanged
   nothing flagged
   comparison → .blicket/build/2224d63eb5ef42e1/compare/976f428f3d33dbdf
   builder: 112 quantities, 6 dimensions
   ```

   The paths are shown as the build shows run paths (`Prepared.shown`): relative inside the
   project, absolute outside it.
3. The page reloads on `#/`: the overview of the build, as today. Another run: Ctrl-C and
   `blicket` again.

### 2. A run that cannot be loaded

You pick `2026-10-24--01-25-28_plastics_SSP2_h12`, pickled by an older remind-mfa. The picker
stays, the selection kept, with an alert under the list:

```
⚠ 2026-10-24--01-25-28_plastics_SSP2_h12 cannot be loaded
  loader blicketconf:load_run raised RuntimeError: …/model.pickle was written by another
  remind-mfa version than the checkout at … (blicketconf.py:31)
```

The terminal prints the same `error: …` line under the time stamp (the traceback with `-v`). You
pick another run.

### 3. A run given on the command line

`blicket runs/x` and `blicket dev runs/x` behave as `blicket dev runs/x` does today; `runs` is
not read.

### 4. A project without `runs`, or without matching folders

```
$ uv run blicket
error: no run to serve; pass one (blicket dev RUN_PATH), or set runs = ["output/*"] in
[tool.blicket] to pick one in the viewer
$ echo $status
2
```

A `runs` that matches no folder serves the picker anyway, empty: `No folder matches runs = [...]
yet.` with `Refresh`, since a model run may land there while the server waits.

## Key decisions

1. **Where the runs come from: globs in `[tool.blicket]`, not an adapter function.** The
   architecture has the adapter implement `discover(root) -> list[RunInfo]` with labels. A
   `RunInfo` needs a fingerprint, which hashes the run's files (a remind-mfa pickle is about 100
   MB), so a picker that lists ten runs would read a gigabyte before it shows anything. Both
   example projects find their runs with one glob each, and `blicks` is already a list of globs.
   So: `runs = ["output/*"]`, globs relative to the project root (`..` allowed), matching
   directories only, hidden ones skipped; the label is the folder's name, the order newest change
   first. Run locations can depend on the machine while the config is committed; that suits
   projects whose runs land inside the checkout (`output/`), and the examples, whose `data_out`
   the READMEs place. A `runs(root)` function in the loader's module, for filtering and labels,
   can come when a project needs it. The architecture is amended.
2. **The picker is a page of the viewer**, as the architecture has it, not a prompt in the
   terminal: the browser is where the result shows.
3. **The picker serves the start only.** It is there while no run is served; once a run is
   loaded, the session is that of `blicket dev <run>`, and another run takes a restart. Changing
   the run within a session (the architecture's "add, remove ... model runs within the session")
   would need the run swapped under requests that are running, a check that tables of other tabs
   still belong to the build they show (M2.2 plans one), two runs in memory during the swap, and
   the discovery's module purge running beside builder queries; M2.2's restart on a run change is
   the place for it.
4. **Several runs make one run** when ticked together: the loader receives them as one
   `RunSelection`, as from `blicket dev a b`. A loader that takes one path says so in its error
   (`this loader takes one run path, got 2`), shown in the picker. The picker does not know which
   loaders combine runs.
5. **One load at a time, of a listed folder.** A load runs in the request's thread while the
   picker waits on the answer; a second `POST` while a load runs, or once a run is served, is
   refused. The picker offers only the folders `runs` matches, so the page cannot make the server
   load an arbitrary path. The report is printed after stdout is no longer redirected to stderr.
6. **After a load, the page reloads** (`location.replace('./#/')`, then `reload()`): the viewer's
   composables fetch the manifest once, and the session has had no build until then.
7. **`blicket` without a command is `blicket dev`.** The rule: `dev` is put first when there are
   no arguments, when the first argument is an option the group does not have (`blicket --open`,
   `blicket -v`), or when it is not a command but names an existing path or contains a `/`
   (`blicket runs/x`, `blicket ../../data_out/run`). Anything else stays click's `No such command
   'lst'. Did you mean 'list'?`, so a typo of a command is not taken for a run. A run folder named
   like a command needs `blicket dev list` or `blicket ./list`. `blicket --help` and `blicket
   --version` are the group's as today. `blicket -v list` becomes `blicket dev -v list` (`run path
   list does not exist`) instead of `No such option`.

## Surfaces

### CLI

```
blicket [OPTIONS] COMMAND [ARGS]...
blicket [RUN_PATH]... [dev options]          same as blicket dev [RUN_PATH]...
blicket dev [RUN_PATH]... [--against BUILD|REF] [--port N] [--host H] [--open]
            [--project DIR] [--out DIR] [-v]
```

- `blicket --help`: today's help; the description gains `Without a command, blicket is blicket
  dev.` Bare `blicket` no longer prints the help.
- `blicket dev --help`: `RUN_PATH` is optional (`[RUN_PATH]...`); the description gains `Without
  RUN_PATH, pick the run in the viewer, from the folders runs in [tool.blicket] matches.`
- Without a run, `dev` prints `runs: N in <patterns>` (`runs: none yet in <patterns>`), the
  viewer's URL, and `pick a run in the viewer, or pass one: blicket dev RUN_PATH`. `--open`
  opens the URL.
- A load picked in the viewer prints `HH:MM:SS loading <paths shown>, picked in the viewer`, then
  the report `dev` prints at start, or the `error: …` line (traceback under `-v`).
- Exit codes: 0 when stopped with Ctrl-C, whatever the loads in the viewer did; 2 when the session
  cannot start: as today, plus no run given and no `runs` in `[tool.blicket]`.
- `build`, `check`, `serve`, `push`, `diff`, `list` are unchanged; `build` and `check` still
  require a run.

### Config

```toml
[tool.blicket]
runs = ["../../data_out/*_plastics_*"]  # folders the run picker offers; default: none
```

`runs` must be a list of glob strings (the wrong-type message as for `blicks`, in
`_WRONG_TYPE`). The config is read once when `dev` starts, as today; `dev/runs` globs its
patterns afresh on each request. The two examples set it: `examples/remind-mfa` as above,
`examples/remind` to `["../../data_out/remind/*"]`, next to the existing `data_out`
instructions in their READMEs.

### HTTP (between the viewer and `blicket dev`)

- While no run is served, the viewer's files are served from the installed viewer alone;
  `manifest.json` answers 404 with `Blicket-Dev: 1` and `{"message": "no run served yet"}`, so the
  viewer knows it is in dev mode; `dev/dataset`, `dev/query` and `dev/tables/…` answer 404 `no run
  served yet`.
- `GET dev/info` gains `run`: whether a run is served (`dataset` and `message` say what they say
  today once it is).
- `GET dev/runs`:

  ```json
  {"patterns": ["../../data_out/*_plastics_*"],
   "runs": [{"path": "/home/…/data_out/2026-10-26--11-25-13_plastics_SSP2_h12",
             "name": "2026-10-26--11-25-13_plastics_SSP2_h12",
             "modified": "2026-10-26T10:25:13Z"}]}
  ```
- `POST dev/run`, `{"paths": [...]}`, from the viewer's own page only (as `dev/query`): 200 with
  `{"id": "<run id>"}` once the run is served; 400 for no path or a path `dev/runs` does not list;
  409 while another load runs or once a run is served; 422 with `{"message": "<the error line>"}`
  when the loader, the build or the baseline fails.

### UI

- `#/runs`, the picker: flows 1, 2 and 4. States: loading the list (`Looking for runs…`), the
  list, empty, a load running, a load failed, `blicket dev` unreachable (the builder's existing
  `Cannot reach blicket dev` alert), and, in a static build or with a run served, the
  builder's "needs blicket dev" kind of notice with a link to the overview. Keyboard: the rows are
  checkboxes in a list, `Load` is a button. Narrow screens: the time goes under the name.
- The app shell: in dev mode with no run served, every route goes to `#/runs` instead of
  `Loading the build…` / `The build cannot be shown`.

## Approach

**Config** (`config.py`): `runs: list[str] = []` with its description and wrong-type message.

**Finding runs** (`dev.py`): `find_runs(root, patterns)` globs each pattern with
`glob.glob(pattern, root_dir=root, recursive=True)` (which takes `..`), keeps directories, drops
hidden ones, dedups by resolved path, and sorts by modification time, newest first, then name.

**The session** (`dev.py`): `start(root, runs, …)` with runs is today's. Without runs, it
prepares the project (`builder.prepare(root, [], out)` works) and returns a session that serves
no run yet, or raises the `BlicketError` of flow 4 when `runs` is unset. The session's run state
(`loaded`, `dataset`, `served`) is optional, set once; `load(paths)` takes a lock (refusing while
held or once a run is served), checks the paths against `find_runs`, resolves them with
`prepare`, runs the steps `start` runs now, and sets the run state in one assignment after the
build and the check; the report is printed after the `redirect_stdout` block. `start` with runs
and `load` share one function for those steps. `current()` returns `None` without a run.

**The server** (`serve.py`): with a session and no run, `parse_request` takes the installed
viewer's directory as the root; `served_manifest` and the dataset routes answer the 404s above;
`dev/runs` and `dev/run` join `_ROUTES`; `dev/run` calls `same_origin` and `json_body` and maps
`BlicketError` to 422. `DevSession.current()` returns `Served | None`.

**The CLI** (`cli.py`): `_App.parse_args` puts `dev` first by the rule in decision 7 (about six
lines; `no_args_is_help` goes); `dev_command` takes `RUN_PATH` as optional (its own annotated
argument, since `build` and `check` keep the required one) and prints the lines without a run.

**The viewer**: `useManifest` records dev mode and "no run served" from a 404 that carries the
header; `lib/dev.ts` gains the shape of `dev/runs` and `postRun`; `pages/runs.vue` is the picker;
`app.vue` routes to `#/runs` without a run; `DevInfo` gains `run`.

**Docs**: README "Developing Blicks" gains the bare `blicket`, `blicket <run>`, the picker and
`runs`, and the config section lists `runs`; the architecture's "Run discovery and labels" and
walkthrough 3 get an amendment (globs, no labels, a picker at the start only).

## Affected areas

`src/blicket/cli.py`, `config.py`, `dev.py`, `serve.py`; `viewer/app/app.vue`,
`composables/useManifest.ts`, `composables/useDev.ts`, `lib/dev.ts`, a new `pages/runs.vue`;
`tests/test_cli.py`, `test_dev.py`, `test_serve.py`, `test_config.py`, viewer unit tests for the
new `lib` functions; `README.md`, `docs/architecture.md`, both examples' `pyproject.toml` and
READMEs.

## Testing

- CLI, through `CliRunner` and the fixture helpers: bare `blicket` and `blicket <existing dir>`,
  `blicket runs/x` (missing), `blicket --open`, `blicket lst` (no such command), `blicket --help`,
  `blicket --version`, `blicket dev` without `runs` (exit 2 and the message). The server is not
  started in these: `dev` is tested up to the point it would serve, as the existing dev tests do.
- `find_runs`: globs with `..`, files and hidden folders dropped, duplicates across patterns, the
  order.
- The routes, on a real server as `test_serve.py` does: the viewer's page and the 404s with no run,
  `dev/runs`, `dev/run` success (then `manifest.json` is the build), a loader failure (422, the
  picker can load another), a path not listed (400), a cross-site request (403), a load while one
  runs and once a run is served (409).
- The viewer: unit tests for the new `lib` functions; by hand (and by the UI reviewer) on the
  remind-mfa example with `data_out` symlinked: flows 1, 2 and 4, light and dark, 390 px.

## Known limits

- The loader runs in a server thread, not the main thread; a loader that installs signal handlers
  would fail there. Ctrl-C during a load leaves a `.tmp-*` build directory, which `newest_build`
  skips.
- A run is picked once per session.

## Out of scope

Changing the run within a session (decision 3); a path field in the picker for a folder outside
`runs`; runs of earlier builds offered without configuration; labels and filtering by project
code (`runs(root)` in the loader's module); runs as a dimension of the builder; M2.2's code reload
and polling; opening the browser by default.

## Decisions

Put to Tobias on 2026-11-03 and accepted as proposed:

1. **Globs in `[tool.blicket]`** (decision 1), the `runs` key, not a function in `blicketconf.py`.
2. **The picker at the start only** (decision 3); changing the run within a session waits.

## Outcome

Built as planned, with these deviations, most of them from the review rounds (architecture, plan
fidelity, CLI, UI in a browser, code quality):

- **The alias rule** (decision 7) is sharper. An option before a command is not routed to `dev`:
  the first positional argument, past dev's options and the values of those that take one
  (`--out build runs/x` routes to `dev`), is looked at, and when it is a command and no existing
  path, `blicket -v list` fails with `No such option: -v (options go after the command: blicket
  list -v)` instead of becoming `blicket dev -v list`. `blicket ""` is `No such command ''.`.
  `-h` is a help option of the group and every command. A bare `blicket` outside a project adds
  `; blicket --help lists the commands` to the error (`ProjectNotFound`, a `ConfigError` raised by
  `find_project_root`); other config errors get no hint.
- **The hints name the short form**: `pick a run in the viewer, or pass one: blicket RUN_PATH`, and
  the no-runs error `no run to serve; pass one (blicket RUN_PATH), or set runs = ["output/*"] in
  [tool.blicket] to pick one in the viewer`. The help texts were reworded to say the alias and the
  picker; `dev`'s summary is `Check a run given or picked in the viewer and serve it with the Blick
  builder; Ctrl-C stops.`
- **`dev/info` has no `run`**: the viewer learns that no run is served from the 404 of
  `manifest.json` with `Blicket-Dev: 1` (`isNoRun`), and nothing read the field.
- **Where the checks live.** `serve._run` validates the body (`RunRequest`, sharing `_parsed` with
  `_query`) and makes the 400 checks: no path, a path `dev/runs` does not list, and `<name> no
  longer exists; refresh the list` for a listed folder that is gone. `Session.load` raises
  `LoadRefused` (`errors.py`, a `BlicketError`) for a load running or a run served, which the
  route maps to 409; any other `BlicketError` is 422. A load takes the session's `lock` without
  waiting; there is no second lock.
- **No second `prepare`.** A load swaps the resolved run paths (`builder.run_paths`, which uses
  `display_path`) into the `Prepared` read at start, so the config is read once. The run state is
  one frozen `Serving(prepared, loaded, dataset, served)` set in one assignment, so the picked
  run's paths are kept for a restart.
- **The terminal.** A failed load prints `error: cannot load <paths shown>: <error>`; the 422 body
  stays the bare error. The access log leaves out the expected 404 of `manifest.json` while no run
  is served and the 422 of `POST dev/run`, which the session reports itself.
- **`find_runs`** names a folder as it was matched, so `output/latest -> …/2026-run-a` is listed
  as `latest`; folders are deduplicated by their resolved path; one `stat()` per match.
- **The picker.** A hint under the list, `Tick a folder to load it, or several to load them as one
  run.`, tied to `Load` with `aria-describedby`; `Load` neutral and disabled with nothing ticked,
  its icon spinning with `aria-busy` during a load so that focus stays on it. One alert for a failed
  load, titled `Cannot reach blicket dev` when the server did not answer, cleared by Refresh, a
  change of the ticks or another Load, scrolled into view, and not shown when the list already says
  the server is unreachable. The rows are `UCheckbox` elements in a `fieldset`, one Tab stop each,
  since a `UCheckboxGroup` cannot carry the path as the whole row's title; the time is a `<time>`
  with the exact UTC time as its title. The empty state names the project root the globs are
  relative to. Times read "N days ago" up to a year, then the date.
- **Files beyond the plan's list**: `lib/runs.ts`, `lib/time.ts` (`utcTime`, shared with
  `comparison.ts`), `composables/useRuns.ts`, `errors.py`, `viewer/README.md`; the `runs`
  example in the README is in the new subsection "Picking the run in the viewer", since the README
  has no list of config keys.

Checked: `uv run --frozen pytest` 748 passed (708 before), ruff and ty clean; viewer `pnpm test`
290 passed, lint, typecheck and generate clean. By hand on `examples/remind` with `data_out`
linked: bare `blicket` lists the eight REMIND folders; one folder loads in about 0.3 s and the page
lands on the overview; four scenarios load as one run; two folders of one scenario fail with the
loader's message; the empty state with Refresh; the server stopped under Refresh and Load; the
static-build and run-served notices; a second tab's 409; light, dark and 390 px in headless Chrome;
the CLI cases above with `CliRunner` and by hand. `examples/remind-mfa` was not run: its path
dependency on the remind-mfa checkout does not resolve from a worktree.

## Follow-ups

- Changing the run within a session (decision 3), with M2.2: a restart on a run picked in the
  viewer must be built from `Serving.prepared`'s paths, not `sys.argv`, which has none; the
  `location.reload()` after a load gives way to `useManifest` reloading (which must also reset
  `noRun`).
- A long list of runs: each row is a Tab stop and `Load` sits below the list; repeat or pin the
  buttons above it, or use arrow keys between rows, if projects with dozens of runs appear.
- `runs(root)` in the loader's module, for filtering and labels, when a glob does not do.
- Problems that `blicket dev <run>` reports at start, such as an `--out` that cannot be written,
  surface only at the first pick.
- `blicket <command> --help | head` ends with `unexpected BrokenPipeError … this is a bug`; it did
  before this change.
- An option before a word that is both a command and an existing folder (`blicket -v list` with a
  `list/` folder) loads the folder as a run, as the rule says; `blicket --versio` gets `dev`'s
  usage; `runs = [""]` prints `runs: none yet in ` with a trailing space.
