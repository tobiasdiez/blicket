# M2.2 The dev loop: code reload and the viewer's refresh

Status: plan, 2026-10-27, revised the same day after an independent review that probed the module
purge, the bytecode cache, the timings on the example, server-sent events under uvicorn and the
stdlib server, Nuxt's dev proxy and the inotify watch count. Second task of milestone M2 of
[architecture.md](../architecture.md) ("Development loop" and walkthrough 1), after
[m2-1-blick-builder.md](m2-1-blick-builder.md), which brings `blicket dev` (a check without
`--push`, then the server with the run in memory and the dev endpoints) and the dev marker. Where
this plan changes the architecture, it says so; the architecture gets the amendments when the task
lands.

## Goal

The loop closes: with `blicket dev` running, saving a Blick module or a helper rebuilds every
Blick against the run held in memory, compares them with the baseline, and the browser refreshes
the chart within about half a second, with the controls where they were and without a flicker; a
rerun of the model landing in the run directory restarts the session on the new run; a broken edit
shows up as a problem in the viewer and in the terminal and the session goes on. Two backlog items
that need the dev server come along: a fixture project the viewer can be developed on without a
model, and "defined at `blicks/drivers.py:23`" opening the file in the editor.

## The flows this task enables

### 1. Edit a Blick and see it

```
$ cd examples/remind-mfa
$ uv run blicket dev ../../data_out/2026-10-26--11-25-13_plastics_SSP2_h12
run 2026-10-26--11-25-13_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at 444eb87 (dirty) · loaded in 672 ms
10 Blicks: 10 built
build 2224d63eb5ef42e1 → .blicket/build/2224d63eb5ef42e1

baseline 976f428f3d33dbdf · run 2026-10-26--11-25-00_plastics_SSP2_h12 · blicks at 81d752e (dirty) · built 2026-10-26 10:25 UTC
vs baseline: 10 unchanged
nothing flagged
comparison → .blicket/build/2224d63eb5ef42e1/compare/976f428f3d33dbdf
builder: 112 quantities, 6 dimensions
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
watching blicks/, blicketconf.py and pyproject.toml for code; the run directory every 2 s
```

1. The overview is M2.1's, with a dev indicator in the header: a green dot and `dev · built
   11:02:14`.
2. You open `flows/production_by_source`, set a filter, edit its transformation in
   `blicks/flows.py` (scale it by 1.01) and save. The terminal prints

   ```
   11:02:41 blicks/flows.py changed · rebuilt 10 Blicks in 310 ms · build c89821f1595d8c1b · vs baseline: 9 unchanged · 1 value
   ```

   and the chart redraws within the second, the filter still set, the URL unchanged, the old chart
   standing until the new rows arrive; the comparison strip now says `largest change 0.99% of the
   chart's scale at …`, the baseline ghost shows the gap. The overview in another tab shows the
   Blick as a card under "Changed since the baseline".
3. You break the edit with a `NameError` inside the transformation: the line says `rebuilt 10
   Blicks in 290 ms · 1 error`, the Blick's page shows the problem with its location in place of
   the chart, the dot stays green (the session is fine; one Blick is not). You break the module
   itself with a syntax error: the build is incomplete, the Blick is gone from the manifest, and
   its page says so with the import problem and keeps the last chart dimmed. You fix it; the
   chart is back.
4. You edit a helper or `pyproject.toml`: every Blick is rebuilt, no `loaded in`, since the run
   stays in memory and only the Blick code is re-imported.
5. You edit `blicketconf.py`, or any module the loader imported: the session restarts itself, as
   it does for a new run (flow 2), since the run object was built by that code.
6. Ctrl-C ends the session with exit 0, at once, tabs open or not, and prints the last build's
   path, which `blicket serve` shows and `blicket push` can push.

### 2. Rerun the model

With the session running, remind-mfa writes a new `model.pickle` into the run directory (the
example's README gets the `export.prefix` setting that makes remind-mfa rerun into the same folder
instead of a new timestamped one). The poller sees the directory change, waits until it has been
quiet for five seconds, and the session restarts itself: the same command, the same port; the
terminal prints the start report again, the viewer's indicator shows `disconnected` for the two
seconds the restart takes and then refreshes. `--no-watch-run` turns the poller off; the "Reload
run" button in the indicator restarts on demand either way.

### 3. The run cannot be reloaded

The new pickle was written by another remind-mfa version and the loader raises on it. The restarted
session cannot start: it prints the loader error as `build` would and exits 2, as `dev` does for a
loader error at start; the viewer's indicator stays `disconnected` and says so. This is the one
flow that ends the session without Ctrl-C: the alternative, a session that serves a build of a run
that no longer exists, would show stale charts as current.

### 4. Developing the viewer without a model

```
$ cd viewer && pnpm fixture     # terminal 1: blicket dev on the fixture project
$ pnpm dev                      # terminal 2: the Nuxt dev server, proxying to it
```

`viewer/fixture/` is a tiny blicket project: a loader that reads a CSV, four Blicks covering the
four built-in plot types with a filter and a split, a dataset for the builder, and two runs, the
second with a changed value and a new dimension value. `pnpm fixture` checks and pushes the first
run, then starts `blicket dev` on the second, so the viewer shows a comparison with `value` and
`schema` flags, the builder has a dataset, and edits in the fixture's Blicks reload too. It needs
a generated viewer (`BLICKET_VIEWER`, as the root README says) and says so when there is none.

### 5. Open the definition in the editor

In dev mode, `defined at blicks/drivers.py:23` on a Blick page is a link that opens the file at the
line in the editor chosen once in the viewer (VS Code by default, Cursor, Zed; the choice is kept
in the browser), via the editor's URL scheme. In a served build directory it stays text: the
manifest holds no absolute path, the dev server knows the project root.

## Facts the plan rests on (checked 2026-10-27, the probes by the plan's review)

- On the example, rediscovery takes 31 to 58 ms, the ten transformations 130 to 150 ms and
  `compare_builds` about 100 ms, so a full rebuild with its comparison is about 300 ms. A loader
  that keeps the run's own module set small saves nothing worth a per-Blick reuse cache, which the
  review showed wrong as well (a Blick module that imports another Blick module would keep a stale
  table) and which leaves the comparison's half of the cost in place.
- `_purge_modules` drops every module under the project root; `build()` discovers before it loads,
  so nothing today rediscovers after a load. A run object whose classes are defined under the root
  (the architecture's `my-model/` layout with the model package next to `blicks/`, or a class in
  `blicketconf.py`) loses its identity after a rediscovery: `isinstance` and Enum comparisons turn
  False silently (probed). Model code outside the root, remind-mfa's editable checkout, is never
  re-imported in process, so a rerun after a model fix would unpickle with the old classes.
- Python's bytecode cache is keyed on the source's size and modification time in seconds: two saves
  of the same size within a second import stale bytecode (5 of 5 in the probe), none with
  `sys.dont_write_bytecode = True`.
- Comments, line shifts and timings are not in the build id. A rebuild that lands on an existing id
  reuses the directory, whose manifest keeps its old `source` lines and `created_at`.
- `fetchTable` caches rows by hash for the page's lifetime. The Blick page hands `useTable` a new
  `{path, hash}` object for every manifest, so a refetched manifest resets the rows to `null` and
  the page shows "Loading the table…" and remounts the chart; `BlickChart` also redraws on new
  `mapping` and `splits` objects. M2.1's builder page avoids this by swapping its entry and rows
  together in `useQuery`; the Blick page needs the fix in `useTable` itself, here.
- Over HTTP/1.1 a browser holds at most six connections per host, and an `EventSource` holds one
  for as long as the tab lives: with six tabs open, the seventh request to the dev server waits.
  Nitro's dev proxy forwards response headers and streams event responses (probed), so the proxy
  is no obstacle either way.
- The stdlib `ThreadingHTTPServer` exits on Ctrl-C with connections open, since its threads are
  daemons (probed); uvicorn waits for open streams unless told a timeout, and then logs an error.
  M2.1 keeps the stdlib server.
- watchfiles' `watch()` and `awatch()` yield about 50 ms after a save (`step`), group bursts up to
  `debounce`, take a filter callable, and watch recursively by default: on the example's root that
  registers 5,139 inotify watches, `.venv` included (`DefaultFilter` filters events, not watches),
  against two for `blicks/`.
- remind-mfa names a run folder by a timestamp unless `export.prefix` is set, so a rerun lands in a
  sibling folder; `builder.build` resolves the run paths, which would pin a `latest` symbolic link.
- The viewer's query keys with an underscore are the page's; `useComparison.chosen` is `null` for
  "No baseline", and `offered` hides a baseline of the same run that the terminal still reports.

## Approach

### The command

`blicket dev` from M2.1 gains the watch, on by default, and `--no-watch-run`. It prints one line
per rebuild with the time, what changed, how many Blicks were rebuilt, how long it took, the build
id and the comparison's counts, followed by the problems of the Blicks as `build` prints them,
and a `warning:` line for the mutation signal below. Exit codes as in M2.1: 0 on Ctrl-C, 2 when
the session cannot start.

### The build pipeline in steps (`builder.py`)

M2.1 splits `build()` into `prepare`, `load` and `write`; the session composes them itself,
rediscovering and writing per change. `LoadedRun` gains the run paths as given, unresolved, for
the poller (M2.1's holds none).

### The session (`dev.py`)

One object holds the `Prepared` project, the registry, the loaded run with the set of project
modules the load imported (the modules under the root in `sys.modules` after the load that were not
there before: the loader module and what it pulled in), the current build and its comparison, and
the baseline resolution. Its work runs in one daemon thread off a job queue, one job at a time, so
the discovery globals have one writer and Ctrl-C never waits for a job. `sys.dont_write_bytecode`
is set for the process.

- **Start** is M2.1's `dev`: discover, load, build, compare, serve. The run's module set is
  recorded right after the load.
- **A code change** is a set of paths from the watcher under the root, kept when they end in `.py`
  or are `pyproject.toml`, lie outside hidden directories and `__pycache__`, and are not under a
  run path. The broadest of these applies:
  - a file of the run's module set (the loader module, or a module it imported): **restart** (see
    the run change), since the run object was made by that code and cannot be reloaded in place;
  - `pyproject.toml`: the config is re-read (an invalid one is a failure: reported, the build
    stays); a changed loader target restarts; otherwise rediscover and rebuild;
  - anything else: **rediscover and rebuild every Blick**. The rediscovery keeps the run's module
    set out of the purge, so `discover` gains a `keep` argument, the one primitive the loop needs.
    Changes queued during a build are coalesced into the next job.
- **The mutation signal, for free.** When the change touched Blick modules only, a Blick of an
  unchanged module whose table hash moved is reported: `warning: stocks/use_by_region changed
  though its code did not: a transformation mutates the run, or is not deterministic`. This
  replaces the architecture's fingerprinting of the loader output, which has no cheap form for an
  arbitrary object, and the second full pass an earlier draft of this plan had.
- **A run change**: the poller walks the run paths as given (unresolved, re-resolved on each walk,
  so a `latest` link follows its target) every two seconds, names, sizes and modification times,
  off the server's threads, tolerant of files vanishing mid-walk; a change starts a quiet period,
  and when the snapshot has not changed for five seconds the session **restarts**: `os.execv` of
  the same command with the bound port made explicit, so a `--port 0` session keeps its port. The
  restarted process loads the run afresh with fresh model code, builds (an unchanged run lands on
  the existing build), compares and serves; the viewer's polling bridges the gap. This amends the
  architecture's "reload code, not data" for the run: data and the code that made it are reloaded
  together, because model code outside the project is otherwise never re-imported, and the restart
  costs about two seconds against runs that take minutes. `--no-watch-run` skips the poller;
  `POST /dev/restart`, the viewer's button, restarts on demand either way, when the request's
  `Sec-Fetch-Site` is `same-origin` or `none`, so another site's page cannot trigger it.
- **Failures** of the config re-read or a `NothingToBuild` from a rediscovery (every Blick module
  broken) keep the current build and comparison, reported in the terminal and in `dev/info`; a
  restart that cannot start exits 2 as flow 3 says.
- **Every rebuild is a build** under `.blicket/build/` (or `--out`), the dirty flag recorded. The
  session deletes the directories it created one switch late (the current and the previous stay),
  never one that existed before it, never the current one when a rebuild lands on the same id. In
  dev, `manifest.json` is served from the current `Build.manifest` in memory (M2.1), so a rebuild
  that lands on an existing directory still shows this build's `source` lines and time; a table
  request whose `?hash` is not the current entry's hash is answered 404 with `no-store`, so a
  request from before a switch cannot put stale rows into the viewer's cache under a new hash.
- **The baseline** is resolved at start and again when the repository's HEAD differs from the
  resolution's tip, not on every rebuild: the store grows with every CI push and the listing reads
  every manifest.

### The viewer learns of rebuilds by polling

`GET /dev/info` (M2.1's, `no-store`, the model `serve.Info`) gains `build` (the current id),
`status` (`watching`, `building`, `broken`), `detail` (what the status is about) and `at`; M2.1's
`message` and `failed` keep saying why there is no dataset. The viewer polls it every 500 ms in
dev mode; a changed
`build` calls `useManifest().reload()` and `useComparison().reload()`, the status drives the
indicator, a failed fetch shows `disconnected` (a restart in progress) and the polling goes on.
This amends the architecture's server-sent events: polling costs a request per half second on
localhost and needs no streaming server, no connection per tab against the browser's six, and no
shutdown dance.

### The viewer's refresh

- `useManifest.reload()` refetches; on failure the manifest shown stays and the error goes to the
  indicator. `useComparison.reload()` refetches the index and the comparisons without flipping
  `loading`, and keeps `chosen` as it is, `null` included, unless the chosen id is gone.
- No flicker: `useTable` watches the string `path?hash` instead of a fresh object, keeps the rows
  shown until the new ones arrive and resets only when the Blick changes; `BlickChart`'s watch
  compares `mapping` and `splits` by value, so a refetched manifest with the same definition does
  not redraw a chart whose rows did not change.
- The import-failure page: when the id is not in the manifest and the build is incomplete, the
  Blick page shows the file-level problems of the build instead of "No such Blick", and keeps the
  last chart it drew, dimmed, until the Blick is back.
- The dev indicator in the header (dev mode only): the dot, `dev · built 11:02:14`, a "Restart"
  icon button; an alert under the header while the status is broken or disconnected, with the
  detail.
- The editor link: `dev/info` carries the project root; the viewer renders `defined at` as a link
  from a template chosen once in a small menu next to it (VS Code `vscode://file/{path}:{line}`,
  Cursor `cursor://file/{path}:{line}`, Zed `zed://file/{path}:{line}`; PyCharm's scheme is not
  registered on Linux by default and is left out), kept in `localStorage`, VS Code until chosen.
- The fixture project as flow 4 describes it, with `pnpm fixture` in `package.json`; its `.blicket/`
  is ignored by the `.gitignore` blicket writes there.

### Dependencies, packaging, docs

`watchfiles>=1.3` joins `dependencies` (`dev.py` is in `meson.build` since M2.1). README:
"Developing Blicks" gains the loop (what rebuilds, what restarts, the run poller, the editor
link); the example's README: `export.prefix` for reruns into one folder, `dev` in "Looking at a
build"; `viewer/README.md`: the fixture flow; `docs/architecture.md`: the dev loop section
amended (restart on a run change and on loader code, in-place reload for Blick code, no reuse,
polling instead of events, the mutation signal, dev builds and their removal); `m0-tasks.md`:
this task's entry.

## Affected areas

- New: `viewer/fixture/**`, the indicator component.
- Changed: `src/blicket/dev.py` and `tests/test_dev.py` (both from M2.1, which put the session
  in `dev.py`): the rebuild pipeline split out of `start()` and the atomic swap of the build
  behind `Session.current()`; `viewer/app/lib/dev.ts` and `viewer/tests/dev.test.ts` (from M2.1,
  the requests to `blicket dev`), which gain the editor templates and the status model; `builder.py` (`LoadedRun` gains the unresolved run paths),
  `discovery.py` (`keep`), `serve.py` (the `dev/info` fields, on its model `Info`,
  `dev/restart`, the hash check), `cli.py` (`--no-watch-run`),
  `report.py` (the rebuild line), `pyproject.toml`, `meson.build`,
  `viewer/app/composables/{useDev,useManifest,useComparison,useTable}.ts`, `viewer/app/app.vue`,
  `viewer/app/pages/blick/[...id].vue`, `viewer/app/components/BlickChart.vue`,
  `viewer/package.json`, the READMEs, `docs/architecture.md`, `docs/plans/m0-tasks.md`.
- Untouched: the plot types, the comparison, the store, the baseline resolution's rules, the
  manifest (spec stays 0.2).

## Testing

- **The session** (`tests/test_dev.py`, on generated projects with `support.LOADER`, whose loader
  also appends to a counter file so the tests see how often the run was loaded, with the restart
  replaced by a recorded call): a change to a Blick module or a helper rebuilds every Blick and
  does not load the run; a Blick module that imports another one gets the other's change; a
  change to the loader's file, to a module it imported, or to the loader target in
  `pyproject.toml` asks for a restart; an invalid `pyproject.toml` and a broken `blicks/__init__.py`
  keep the current build and report; a syntax error in a Blick module gives an incomplete build and
  the session goes on; the mutation signal names a Blick of an unchanged module whose table moved
  and stays quiet when a helper changed; a run whose classes live under the root keeps its class
  identity through a rediscovery (the probe as a test); the previous dev build is removed one
  switch late and a pre-existing directory kept, a same-id rebuild never deletes the current one;
  the baseline is resolved again only when HEAD moved; the poller's snapshot and quiet period as a
  pure function of two snapshots and a clock; the change classification as a pure function.
- **The server**: `dev/info` with its fields in dev; the hash check (an old hash is 404
  `no-store`); `dev/restart` refused without `Sec-Fetch-Site`; the CLI's `dev` with
  `--no-watch-run`; Ctrl-C exits at once with a connection open (a thread test with a real
  socket).
- **The viewer**: vitest on `lib/dev.ts` (the editor templates, the status model, which baseline
  stays chosen); the composables are not unit-tested, as before.
- **By hand, recorded in this plan**: the example under `blicket dev` in headless Chrome: a
  transformation edit redraws the chart with the URL and controls unchanged, no page load and no
  "Loading" flash; a helper edit prints no `loaded in`; a syntax error shows the import problem on
  the Blick's page and the fix brings the chart back; a rerun into the same folder restarts the
  session and the overview refreshes; seven tabs open and everything still answers; Ctrl-C with
  tabs open exits at once; `serve` on what stays; the fixture flow; the editor link opens VS
  Code. This is the architecture's hot-reload verification item, both halves.

## Out of scope

Per-Blick reuse across rebuilds and import-edge tracking (the whole rebuild is 300 ms on the
example; a project with hundreds of slow Blicks revisits this, together with an incremental
comparison); reloading model code in place; reloading when a non-Python file a transformation reads
changes; server-sent events; pushing dev builds; the overview's revamp, the plot type chips, the
header's "Blick code" label and the "World" panel from the backlog; colours per dimension value;
end-to-end browser tests; scatter and table (M2.3).

## Open questions and decisions for Tobias

1. **Restart on a run change and on loader code**, in-place reload for Blick code (an architecture
   amendment). The alternative, reloading the run in process, keeps stale model code for any
   model installed outside the project, remind-mfa included.
2. **Polling `dev/info` instead of server-sent events** (an amendment): a request per half second
   per tab against a held connection per tab and the browser's six.
3. **Whole rebuilds, no reuse cache and no second pass**; the mutation signal from Blicks of
   unchanged modules.
4. **The editor link** as a choice kept in the browser, VS Code by default; or deferred.
5. **One loop or two**: the review suggests the session and server first, tested headless, and the
   viewer's refresh, indicator, import-failure page and fixture second. With the cuts above the
   whole fits one implementer; two loops give two reviews.
