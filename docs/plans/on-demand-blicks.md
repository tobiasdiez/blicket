# On-demand Blicks in `blicket dev`

Status: built 2026-11-16 on `dcfd796`, uncommitted, through the feature loop with three review
rounds. A first version, "Lazy runs", was built 2026-11-11 the same way: in it the loader called
a whole run lazy (`RunInfo.lazy`), `blicket dev` built such a run Blick by Blick as the viewer
opened them, and built every other run whole before serving it. Tobias then asked for two changes:
cost is said per Blick, and there is one kind of session. A Blick says that it is expensive, the
loader can make every Blick of its run expensive, and every session of `blicket dev` serves at
once and builds on demand. Later he added that the viewer's run picker offers the project itself,
computed from code, when `runs` lists `.`, and switches runs while one is served, so that one
session goes from a model checkout to a finished run and back; and he moved what a session does
when its run changes to m2-2. The sections below are the revised plan, built on top of the first
version's code. The deviations at the end are in two parts: those of the first version, which hold
for the revision, worded for it, and those of the revision. The first version's plan was revised
after an independent review that checked its claims against the code (the baseline resolution, the
split of `compare_builds`, serving a mutable directory, the viewer's reloads, pydantic's
`extra="forbid"` on `Run`) and against [m2-2-dev-loop.md](m2-2-dev-loop.md). What is left is in
[todo.md](todo.md).

Tobias asked for it from mrmfa, a madrat R package that gets Blicks for every file it exports: "one
of the ideal things would be to look at a Blick without needing to run the whole input data
generation".

## Goal

Some Blicks take long to build. mrmfa's run is "this checkout, computed with madrat": each Blick's
data is one or a few `calcOutput` calls that take seconds to minutes, and all of them together are
the whole input data generation, hours. `blicket dev` runs every transformation before it serves
(`dev._serve` → `builder.write`), so such a run shows its first chart after hours, and a run whose
Blicks are all quick still keeps the viewer waiting until the last one is built.

With this feature `blicket dev` serves at once on every run: it loads the run, lists every Blick
and builds the Blicks while the viewer is open. A Blick that is *expensive* is built when it is
opened in the viewer, and again on request, since the data behind such a run changes while the
session runs (the model code is being edited). Every other Blick, a *cheap* one, is built in the
background from the start, and again whenever its page is opened, so that it shows the run as it
is now without a button. A Blick opened in the viewer is built before the background. `blicket
build` and `blicket check` build every Blick, expensive or not, as they do today.

## The flows

### 1. Open an expensive Blick

mrmfa's project lists `.` in `runs`, beside the folders of its finished runs from the cluster
(`runs = [".", "/p/projects/mrmfa/output/*"]`), and its loader makes every Blick of a checkout
expensive. `blicket dev` serves the run picker; you pick "This project · computed from code".

```
$ blicket dev
runs: 4 in ., /p/projects/mrmfa/output/*
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
pick a run in the viewer, or pass one: blicket RUN_PATH
12:00:58 loading this project, picked in the viewer
run mrmfa 2.9.2 at d2f2b8b · profile h12 · blicks at 1c2d3e4 (dirty) · loaded in 1.1 s
62 Blicks, each built when it is opened in the viewer (expensive)

baseline 5d0c3f1e2a9b8c47 · run rev2.9.2_h12 · blicks at 0a6b858 · built 2026-11-10 09:14 UTC
builder: off, dataset(run) returned None
12:01:05 building cement/trade
12:01:47 cement/trade built in 42.1 s · value, 2.1% of scale (Region=CHA, Time=2019)
12:03:07 building steel/production
12:03:10 steel/production built in 3.2 s · unchanged
12:04:02 building steel/scrap
12:04:02 steel/scrap failed in 412 ms · transformation raised KeyError: 'st_scrap'   (-v for the traceback)
12:05:00 building plastics/validation
12:05:00 plastics/validation skipped in 104 ms · the run has no validation.mif
12:06:15 building cement/trade
12:06:57 cement/trade rebuilt in 41.8 s · unchanged
```

The lines `building <id>` go to stderr, where the transformation's own output follows them; the
lines of a build ended go to stdout.

1. The overview says what kind of session this is and how far it is:

   ```
   Compared with run rev2.9.2_h12 ▾          62 of 62 Blicks not built yet
   ─────────────────────────────────────────────────────────────────────────
   ⓘ An expensive Blick is built when you open it.

   A first look
   ┌──────────────────────────┐ ┌──────────────────────────┐
   │ Steel production       ☆ │ │ Steel trade            ☆ │
   │ Not built yet            │ │ Not built yet            │
   └──────────────────────────┘ └──────────────────────────┘
   ```

   A card of a Blick not built yet shows its title and `Not built yet` and links to its page,
   as every card does; cards never ask for a build. In a session with an expensive Blick, "A
   first look" shows the first six Blicks in sidebar order whatever their status, for as long as
   nothing is pinned, whether or not something changed, leaving out those already under "Changed
   since the baseline" (the rule of a build, the first six with a table and only while nothing
   changed, would show nothing). The sidebar lists every Blick, the ones not built yet marked
   with a dashed circle (not in italics, which says skipped), and counts them at its foot: `62
   Blicks · 62 not built yet`. The page's footer names the session, not a build.
2. You open `cement/trade`. Its page shows the title, description, plot type, unit and where it
   is defined, which the definition gives without a build. No Blick a page asked for builds, so
   the page asks the server for the Blick at once and shows `Building… 0:42 · what the
   transformation prints is in the terminal` with a spinner in place of the chart. A reload of
   the page, or the same page in a second tab, shows the same status: the state is the server's.
3. While `cement/trade` builds you open `steel/production`. Its page does not queue it by
   itself: it says `Cement trade is building (0:42).` with a `Build next` button, so clicking
   through the sidebar never lines up minutes of computation; pressed, the page shows `Queued
   behind Cement trade`, then `Building…`. The other Blick is named by its title, as a link to
   it. A Blick building in the background does not count here: an expensive Blick opened while
   only the background builds asks at once and is built next, once the build running ends.
4. The build ends. The page shows the chart with its controls, the comparison strip and the
   baseline behind it, as for any built Blick; the sidebar gives the Blick its badge (`Δ 2.1%`);
   the overview counts `61 of 62 Blicks not built yet` and shows it under "Changed since the
   baseline". Other pages and tabs learn of it within a second; a chart that did not change is
   not redrawn.
5. A Blick that fails shows its problems, one that skips the run its reason, as today. Both are
   built: opening them again builds nothing.

### 2. A session of cheap Blicks

A loader that says nothing makes every Blick cheap.

```
$ blicket dev examples/remind-summary
run remind 3.5.0 at 7e1f2a9 · profile default · blicks at 3c4d5e6 · loaded in 0.4 s
20 Blicks, built in the background

baseline 9a8b7c6d5e4f3a2b · run default · blicks at 2b3c4d5 · built 2026-11-10 09:14 UTC
builder: on, ...
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
<when the background is done: the counts, problems and comparison of check's report>
12:03:10 summary/gdp rebuilt in 180 ms · unchanged
```

1. The viewer answers at once. The overview counts `14 of 20 Blicks not built yet` while the
   background builds, without the note on expensive Blicks, and "Changed since the baseline"
   fills as the Blicks are built. The sidebar marks those not built yet and turns a spinner on
   the one building, as in flow 1.
2. You open a Blick not built yet: the page asks for it, and it is built next, once the build
   running ends, before the rest of the background (`Queued behind <title>`, then `Building…`).
3. You open a built Blick, or come back to one: the page shows what was built under `Updating…`
   and asks for the Blick again. The new table replaces the old one when it is there, compared
   with the baseline again, and the line says `Rebuilt in 180 ms`. There is no `Rebuild` button:
   opening the page, or reloading it, is the rebuild. Behind an expensive build, the page keeps
   what it shows under `Updating after Cement trade (0:42)`.
4. In the terminal a background build prints no line. When the background is done the session
   prints the rest of the report that `blicket dev` prints before serving today: the counts, the
   problems and the comparison with the baseline, of the Blicks built so far. A build a page
   asked for prints its lines, as in flow 1.

### 3. Rebuild after an edit

You edit the model code behind `cement/trade` and press `Rebuild` on its page (next to the pin).
The chart stays, dimmed, under `Rebuilding… 0:12`; the transformation runs again on the run the
session holds, and the page shows the new table, compared with the baseline again. `Rebuild` on a
failed or skipped Blick is the retry. Pressed while the Blick builds, it asks for one more build
after that one, once. A cheap Blick has no button: you open its page again. The run object decides
what is fresh: a run computed on demand answers a transformation from its source each time, or
knows when what it kept is stale; mrmfa's asks madrat, whose cache knows which code changed. Blick
code is not reloaded: an edit of a transformation takes a restart, as today.

### 4. Every Blick

`blicket build .` and `blicket check .` build every Blick, expensive or not, as today, so CI and
the cluster keep their whole builds and the store its baselines. `blicket dev` makes no build any
more; `blicket check --push` pushes one.

### 5. Switch between the checkout and a finished run

The header of a session whose project sets `runs` has `Pick another run`, which opens the picker
with the run served marked. You pick the folder of last night's run on the cluster and press
`Load`. The session has built 12 expensive Blicks, which another run drops, so the viewer asks
first: `Loading another run drops the 12 expensive Blicks built so far.` with `Load` and
`Cancel`; with none built, it does not ask. The run is loaded as one picked at the start
(`12:10:02 loading 2026-11-15_h12, picked in the viewer`, then the start report): its baseline is
resolved for it, the session gets a new id, and the viewer starts afresh on the overview. A load
waits for a cheap Blick that builds and is refused while an expensive one builds (`Cement trade is
building (12:03); load the run once it is built`), since a build cannot be interrupted. A load
that fails leaves the run served as it was and says why under the list, as today. Going back to
the checkout is the same, picking "This project".

### States of a Blick page

| State | What the page shows |
|---|---|
| expensive, not built, no Blick a page asked for builds or waits | asks for the build itself; then as "building" |
| expensive, not built, another Blick a page asked for builds or waits | `<title> is building (m:ss).` and `Build next` |
| cheap, not built | asks for the build itself; then as "queued" or "building" |
| queued | `Queued behind <title>` |
| building | `Building… m:ss · what the transformation prints is in the terminal` |
| built, ok | chart, controls, comparison as today; `Rebuild` on an expensive Blick |
| built, error | the problems as today; `Rebuild` on an expensive Blick |
| built, skipped | the reason as today; `Rebuild` on an expensive Blick |
| cheap, built, opened | what was built, under `Updating…`, asked for again at each visit |
| expensive, rebuilding | what was there, dimmed, under `Rebuilding… m:ss` |
| the definition is invalid (`registry.failed`) | the problems as today and `Cannot be built: its definition is invalid. Fix it at <source> and restart blicket dev.`; no `Rebuild` |
| the server does not answer | the dev alert as today ("Cannot reach blicket dev"); what was there stays |
| the Blick is not in the session | "No such Blick in this session" |

## Surfaces

### Library API

```python
@bk.blick(title="Scrap shares", plot=bk.plots.line(x="year", y="value"), expensive=False)
def scrap_shares(run):
    return pl.read_csv(run.path / "static" / "scrap_shares.csv")  # always there


def load_run(selection: bk.RunSelection) -> tuple[object, bk.RunInfo]:
    run = Checkout(selection.path)  # computes nothing yet
    return run, bk.RunInfo(id=..., profile="h12", fingerprint=..., expensive=True)
```

- `bk.blick(..., expensive: bool | None = None)`: `True`, the Blick takes long to build, so
  `blicket dev` builds it when it is opened and on `Rebuild`; `False`, it is cheap whatever the
  run says; `None`, the run decides. It is not part of the Blick's definition
  (`Blick.definition()`), so it changes no build, no manifest id and no comparison.
- `RunInfo.expensive: bool = False`: every Blick of the run whose definition says nothing is
  expensive. mrmfa's loader sets it for a checkout and not for a finished archive, which it loads
  too. It tells `dev` how to serve the run and is never written: `Run` forbids unknown fields, so
  a manifest with `expensive` would be damaged for an older blicket reading a shared store.
  Manifests, ids and `--json` output stay as they are.
- `dataset(run)` may return `None`: this run has no dataset, the builder is off, and that is no
  warning; the report says the fact, `builder: off, dataset(run) returned None`, so that a
  `dataset` that forgot its `return` is told apart. A run of expensive Blicks usually has none,
  since a dataset lists the values of its dimensions, which come from the tables.

### CLI

No new option. `blicket dev [RUN_PATH...]`, also on a run picked in the viewer, prints the run
line; how its Blicks are built (`20 Blicks, built in the background`, `62 Blicks, each built when
it is opened in the viewer (expensive)`, or `62 Blicks: 2 built in the background, 60 when opened
in the viewer (expensive)`); the baseline line (or why there is none); the builder line; and the
viewer's URL. Then, for each build a page asked for, a line on stderr when it starts, `HH:MM:SS
building <id>`, and one on stdout when it ends, as above, `built`, `rebuilt` (built before in the
session), `failed` or `skipped`, with the traceback of a failure under `-v`. A build in the
background prints no line of its own; when the background is done, the session prints the counts,
problems and comparison of `check`'s report for the Blicks built so far, without `comparison →`,
since nothing is written. Exit codes as today: 0 on Ctrl-C whatever was built, 2 when the session
cannot start. A project without a Blick is served as an empty session.

Without a path, `blicket dev` serves the run picker, as today; without `runs` it exits 2, as
today, and the message names `.` too (`set runs = ["output/*"] in [tool.blicket] to pick one in
the viewer, or "." for the project itself`). A `.` among the globs of `runs` lists the project
itself, first, as "This project · computed from code". Picked, the loader gets the project root
as its one path, `RunSelection` as it is, which a model checkout such as mrmfa's recognises, and
the terminal names it `this project`. `blicket dev .` loads it without the picker. `build` and
`check` still take a path (`blicket check .`).

`--out` is accepted and not used, since `blicket dev` writes no build directory any more; its help
says so, and so does a line on stderr when it is given. `blicket serve` without a path serves the
build made last, which is now one of `build` or `check`.

### HTTP API of `blicket dev`

- `GET dev/info` has `session`, `revision` (a counter that rises whenever the manifest or the
  comparison changed), `jobs` and `stopped` in every session; the first version's `lazy` goes,
  since every session builds on demand. `jobs` lists the Blick building and the Blicks a page
  asked for, in the order they are built: `[{"id": "cement/trade", "state": "building",
  "asked": true, "since": "2026-11-11T12:01:05Z", "seconds": 42.0}, {"id": "steel/scrap",
  "state": "queued", "asked": true, …}]`; `asked` is false for a build of the background. The
  Blicks waiting in the background are not listed: they are the cheap ones still `pending`.
- `POST dev/build` with `{"id": "cement/trade", "rebuild": false}` → `{"state": "queued" |
  "building" | "done"}`: asks for the Blick; `done` when there is nothing to do, the Blick built,
  failed or skipped; with `rebuild` (a boolean, nothing else), one more build, at most one waiting
  per Blick. A request for a Blick waiting in the background moves it before the background. The
  page of a cheap Blick sends `rebuild: true` once the Blick is built. 404 for an id the session
  has no buildable Blick for, 409 once the worker stopped, 400 for another body. Same-origin
  only, as `dev/query`. It returns at once: a request held open for the minutes of a build would
  meet the browsers' timeouts and take one of the six connections a page has. A client that waits
  for the build waits until the Blick has left `dev/info`'s `jobs`.
- `GET dev/runs` lists the project itself first when `runs` has `.`: its entry has `project:
  true`, the name `This project` and no time (`modified` is `null`), which a folder's time would
  not tell for a checkout. The globs and the other folders are as today.
- `POST dev/run` loads also while a run is served, in its place: it waits for a cheap Blick that
  builds, and answers 409 while an expensive one builds or another load runs. The run served
  stays until the new one is loaded, and a load that fails leaves it served; a load that succeeds
  gives the session a new id.
- `POST dev/query` waits while a cheap Blick builds and answers 409 `an expensive Blick is
  building; run the query again when it is built` while an expensive one builds, instead of
  waiting on the lock for minutes.
- `manifest.json`, `compare/index.json` and `compare/<baseline>/comparison.json` keep their shapes
  and are answered from the session's state at the moment of the request, with the header
  `Blicket-Revision` naming the revision they are of; the tables are served by content,
  `dev/tables/<sha256>.parquet`, the route of the builder's tables, which a manifest entry's
  `data` and a comparison's `baseline_data` name. `blicket dev` serves no build directory.

### Manifest and comparison

- A Blick's `status` gains `pending`: the Blick is defined and not built. Only the manifest that
  a session of `blicket dev` answers has such entries; a build directory never does, so the spec
  stays 0.2. `BlickEntry.pending: bool`, left out of the dump when false, so today's manifests and
  ids are unchanged (the JSON Schema's status enum gains the value).
- `BlickEntry.expensive: bool`, left out of the dump when false, which only the manifest of a
  session sets, so that the viewer knows which Blicks wait to be opened; a build's manifest never
  has it, whatever the definitions say (the JSON Schema gains the field).
- The manifest of a session carries an id that names the session, not a build; nothing writes or
  pushes it.
- The comparison of a session lists the Blicks built so far and the removed ones that no current
  Blick claims, which the definitions alone say (pending and failed Blicks claim their ids and
  aliases). A pending Blick is not in it: it is neither `new`, `removed` nor unchanged.

### Viewer

As the flows say. Every session of `blicket dev` follows its state, as only a lazy one did in the
first version: on an expensive Blick's page, the status with `Build next` and `Rebuild`; on a
cheap one's, the request at each visit and `Updating…`; sidebar entries marked as not built yet,
with a spinner on the one that builds and a clock on those a page asked for that wait; `N not
built yet` at the sidebar's foot; `N of M Blicks not built yet` on the overview while a Blick is
pending, with the note on expensive Blicks when the session has one; cards that say `Not built
yet`; the footer. In a session whose project sets `runs`, `Pick another run` in the header; on the
picker, the project's own entry first, and the question before a load drops expensive Blicks
built. The counts of the comparison bar count built Blicks. Status changes are
announced (`role="status"`), the buttons reachable by keyboard. A served build directory looks
and behaves as today.

## Approach

**One kind of session.** `dev._serve` loads the run, discovers the Blicks, resolves the baseline
and starts the session's builds (the first version's `LazyRun`), which queue the cheap Blicks at
once; `builder.write` is left to `build` and `check`. What `dev` has for a build made at the
start goes: the branch on `RunInfo.lazy`, `Current`, serving a build directory, the check's report
before the URL, and the viewer's paths for a session that does not build on demand.

**A load replaces the session's run.** A run picked while another is served is loaded with the
session's lock held, so that no build runs meanwhile; once its loader has returned, the session
drops the old run's queues, tables and comparison, resolves the baseline for the new run, takes a
new id and starts the background, and the viewer starts afresh as it does after a restart. When
the loader raises, the old run stays served and its worker goes on.

**The session, not a build, holds the tables, in memory.** A build is immutable and has a content
id; a session grows. So a session writes nothing to disk: it keeps each built Blick's table as
Parquet bytes by their sha256, as the session keeps the builder's tables, and serves them through
the same route. A rebuild replaces a Blick's table; the bytes it replaces are kept for the next
eight revisions (`KEPT`), so that a fetch made from an earlier manifest still finds them. The
baseline's tables of flagged Blicks are kept the same way, as the comparison read them from the
store, checked against the hash in the baseline's manifest. A session of cheap Blicks now holds
every table of its run, which the soft limit on a table's size bounds. The manifest and the
comparison are objects in memory, replaced as a whole when a build ends, so a request reads one
state; `compare/index.json` and `comparison.json` are answered from them as `manifest.json` is.
There is no directory to clean up and nothing `--out` would change.

**One worker, three queues.** A daemon thread builds one Blick at a time: first the cheap Blicks a
page asked for, in the order asked; then the expensive ones a page asked for, in the order asked;
then the background, in the order `blicket list` shows the Blicks. A build running is never
interrupted. A cheap Blick goes before expensive ones asked, since it costs seconds where they
cost minutes, so a page opened on a cheap Blick waits at most for the build running. A request for
a Blick waiting in the background moves it to its queue. The worker holds the session's lock while
a transformation runs, compares the table and publishes the new state. Whatever a job raises, in
the transformation, the conversion, the comparison or the store, becomes that Blick's error, and
the worker goes on; `dev/info` says so if the worker itself has died. The transformations run on
that thread, which suits a run that computes in a subprocess, as mrmfa's does with `Rscript`; a
run that computes in the process holds the interpreter while it does, and the server answers when
it lets go. Only the worker redirects what project code prints to stderr, and the session writes
its own lines to the stdout it kept, since `redirect_stdout` is the process's.

**Queries and builds share the lock.** The builder's queries take the lock too, since blicket does
not ask a run object to be thread-safe. A query waits while a cheap Blick builds and is refused
while an expensive one builds. The worker lets go of the lock between two builds and lets a query
that waits take it first, so that the builder answers while the background runs.

**The terminal counts the background.** A build of the background prints no line; when the last
one ends, the session renders the counts, problems and comparison of `check`'s report from its
manifest and comparison. A build a page asked for prints its lines, and so does a cheap Blick
built again at a visit.

**The baseline is resolved once, at the start**, from the run's profile and the repository's
commit, which need no table (`baseline.resolve` reads the manifest's run, repository and id). A
Blick is compared when it is built, by the code that compares builds (`comparison.compare_blick`,
which `compare_builds` uses as well).

**The viewer polls `dev/info`** once a second in every session of `blicket dev` while the tab is
visible; when `revision` rises, or the session is another, it reads the manifest and the
comparison again, and shows the three together once the header `Blicket-Revision` of both says the
revision of the answer, reading again at once when a Blick was built meanwhile. Reading them again
does not disturb what is on the page: a table is fetched again only when its hash changed, a chart
is redrawn only when its rows or definition changed, the baseline chosen stays chosen, the
overview does not blank while the comparison is read again, and a failed poll leaves the page as
it is and is retried. While a Blick is rebuilt, its old entry and rows stay together until the new
ones are there, so new controls never meet old rows. A cheap Blick's page asks for its Blick at
each visit, each time the route enters the page and not when a tab is focused again, and keeps
what it shows, not dimmed, until the new table is there.

## Relation to the dev loop (m2-2)

[m2-2-dev-loop.md](m2-2-dev-loop.md) is planned, not built. What a session does when its code or
its run changes is m2-2's, not this feature's: this feature watches nothing. It changes m2-2 in
the places that m2-2's "Changed by on-demand Blicks" lists: a change keeps what the session built,
says so, and marks the expensive Blicks built before it, which `Rebuild` builds again; the
session's worker is where m2-2's job queue starts; and `blicket dev` makes no builds.

## Key design decisions

1. **A Blick says whether it is expensive, and the loader gives the default for its run**
   (`bk.blick(expensive=…)`, `RunInfo.expensive`). The cost belongs to a Blick on a run: the same
   Blick takes minutes on mrmfa's checkout and milliseconds on a finished archive, both loaded by
   one loader. So the loader sets the default for the run it loads, and a definition overrides it
   where its author knows better, as for a Blick that reads a file that is always there. A config
   key would make archives expensive too. There is no `--expensive` or `--cheap`: nothing asks for
   them yet, and a loader can read an environment variable. This replaces `RunInfo.lazy`, which
   made a whole run build on demand and built every other run at the start.
2. **Every session of `blicket dev` builds on demand.** The server answers at once on every run,
   and `dev` has one kind of session, not one for a build directory and one for a session in
   memory. The start loses the check's report before the URL, which comes when the background is
   done, and the build directory, which `build` and `check` make.
3. **A cheap Blick is built in the background and again at each visit; an expensive one when it is
   opened and on `Rebuild`.** Building a cheap Blick again costs less than knowing whether the run
   changed, so its page shows the run as it is now, without a button. An expensive build cannot be
   interrupted, so none starts without a visit or a click.
4. **Opening an expensive Blick builds it when no Blick a page asked for builds or waits;
   otherwise the user asks** (`Build next`). The click on a Blick is the request to see it, so the
   common case, one Blick after the other, takes no second click; and since a build cannot be
   interrupted and may take minutes, nothing queues behind a running build without `Build next`.
   The background does not count, since it is cheap. No build is ever cancelled, so there is no
   cancel route and no question of what a second tab does when the first leaves.
5. **Cheap Blicks asked for, then expensive ones asked for, then the background**, each in its
   order; a build running is never interrupted.
6. **No partial builds.** Nothing a session makes is a build: no id, no directory, nothing to
   push. The whole build of a run is `blicket build`.
7. **`pending` is a status of the session's manifest only**, beside `ok`, `error` and `skipped`;
   comparisons leave pending Blicks out instead of flagging them.
8. **A rebuild runs the transformation again on the same run object.** The loader is not called
   again and no hook is added.
9. **Sequential.** One build at a time.
10. **The viewer picks between the checkout and a finished run.** A `.` in `runs` lists the
    project itself in the run picker, beside the run folders, and the picker switches runs while
    one is served, so that one session goes from the model's code to a run from the cluster and
    back. No new config key and no CLI option: `runs` already lists what can be picked, and asking
    the loader instead would load the project at every start to learn whether it is a run, and
    could not tell a broken checkout from a project that is none. `blicket dev <path>` stays for
    a run named on the command line.

## Affected areas

The first version's code is where the revision starts; it changes:

- `model.py` and `bk.blick` in `definitions.py`: `Blick.expensive`, which `definition()` leaves
  out.
- `manifest.py`: `RunInfo.expensive` in place of `lazy`, never dumped; `BlickEntry.expensive`,
  left out when false.
- `lazy.py`: the builds of every session, renamed `jobs.py`; the three queues, the background,
  its report, a query waiting for a cheap build.
- `dev.py`: one kind of session; the branch on `lazy` and what served a build made at the start
  go; `find_runs` keeps a `.` match as the project itself; `Session.load` replaces a served run,
  waiting for a cheap build, refused during an expensive one, keeping the served run when the load
  fails; the message without `runs` names `.`.
- `serve.py`: `RunFolder.project` and a `modified` that may be `null`, `dev/run` while a run is
  served, `dev/info` without `lazy`, `asked` in a job, the 409 of `POST dev/build` for a
  session that does not build on demand gone, `dev/query` waiting for a cheap build, no build
  directory served by `dev`.
- `report.py`, `cli.py`: the line of how the Blicks are built, the report when the background is
  done, `--out` of `dev`.
- viewer: `lib/dev.ts` (`Info` without `lazy`, `Job.asked`), `useLazy` and `lib/lazy.ts` (per
  Blick, renamed after jobs), `useBlickBuild` (a cheap Blick's visit), `BuildStatus.vue`
  (`Updating…`), the Blick page (`Rebuild` on an expensive Blick only), `app.vue` (`useRefresh`
  for every dev session, the footer, `Pick another run`), the overview's note, `lib/preview.ts`
  (the first look), `pages/runs.vue` and `lib/runs.ts` (the project's entry, the question before
  a load drops expensive Blicks, the run served marked).
- `README.md` ("Lazy runs" becomes "Expensive Blicks" under "Developing Blicks", with `.` in
  `runs` for a model checkout and switching runs in the viewer; the routes in
  `serve.py`'s docstring), `viewer/README.md`, `docs/architecture.md` (the amendment under
  "Development loop" rewritten), `docs/plans/m2-2-dev-loop.md` (the three changes above).
- tests: `tests/projects/lazy` becomes `tests/projects/on-demand`, whose loader makes its Blicks
  expensive unless `BLICKET_TEST_CHEAP` is set, with one Blick that says `expensive=False` and
  one that says `expensive=True`; tests of the queues' order, the background's report, a cheap
  Blick built again at a visit, a query that waits for a cheap build and is refused during an
  expensive one; `.` in `runs` (the project listed first, loaded as the project root); a switch of
  runs (in place, waiting for a cheap build, refused during an expensive one, the served run kept
  when the load fails); the tests of a session built at the start (its build id, `push` of the
  build `dev` made) rewritten for a session; `test_build.py` (an expensive run builds whole, with
  the manifest and id of the same run with cheap Blicks); vitest for the viewer's new pure functions;
  the viewer walked through in a browser on that project, cheap and expensive, in both themes and
  narrow.

## Out of scope

- Selecting Blicks in `build` and `check` (`--only`); pushing what a session built, or writing it
  as a build directory, from a button in the viewer
  ([#30](https://github.com/tobiasdiez/blicket/issues/30)).
- Keeping the tables of a session for the next one
  ([#31](https://github.com/tobiasdiez/blicket/issues/31)).
- Watching the code and the run, and what a change does (m2-2).
- Interrupting or cancelling a build; parallel builds; a "Build all" button for expensive Blicks.
- `--expensive` and `--cheap`.
- Telling a Blick's cost from how long it took to build.
- Reloading Blick code (m2-2).

## Open questions

1. The names: `expensive` on the Blick and on `RunInfo` (or `RunInfo.expensive_blicks`, since the
   run itself is not what is expensive), `pending` for the status, "not built yet" in the viewer,
   `jobs.py`.
2. Decision 4, when an expensive Blick's page builds, carried over from the first version: at
   once when no Blick a page asked for builds or waits, and by `Build next` otherwise (planned);
   always at once, queueing behind a running build; or always by a `Build` button.
3. `--out` of `dev`: accepted and not used (planned), or removed.

## Deviations

### Of the first version

Recorded while the first version was built, where it departs from its plan or settles what that
plan left open. They hold for the revision, worded for it: where the first version said a lazy run
or a lazy session, the revision has a session of `blicket dev`, and an expensive Blick where it
builds only when opened.

- **`compare_blick` takes what reads the current table**, a function without arguments, or
  `None` for an entry without one, not a frame, so that `compare_builds` still reads a current
  table only when the baseline has one, and after the baseline's: the comparison of two builds is
  the same to the byte, the error of two unreadable tables included. A session passes a function
  that reads its Parquet bytes, so its comparison is the one `check` makes of the same tables.
  `Baseline` (the baseline's directory, manifest and Blicks by id; `Baseline.keeping()`, as a
  session uses it, reads each table once and keeps its bytes, checked against the manifest's hash)
  and `assemble` (the comparisons of the Blicks, then the removed ones) are the other two parts;
  `reference` and `flagged` are public. The API around them changed with it:
  `comparison.compare(baseline, current)` beside `compare_builds`, `place_baseline` (the baseline
  table a flagged Blick is drawn against, which `write` and a session share), `write(comparison,
  baseline, current)` taking a `Baseline`, `check.find` returning a `check.Lookup` (the
  resolution, the baseline, the store's warnings) that `check.compare` and a session share; and
  `manifest.Run` and `RunInfo` share a base instead of `Run` being a `RunInfo`, so that no
  manifest accepts `expensive`. `tests/projects/comparison` holds a scenario of the common
  branches (unchanged, a value change, one within tolerance, a schema change, a Blick renamed by
  alias, skipped now and on both sides, failed in the baseline and now, new, removed) and the JSON
  the code before the split gave for it; a plot type's diff that raises and an incomplete build
  are not in it. Every comparison the test suite makes was also checked to be the same to the byte
  before and after the split, once, outside the suite.
- **`jobs`, not `builds`** (decided in review): "build" names the immutable directory with an
  id, so the Blicks queued and building are jobs: `serve.Job`, `Info.jobs` on the wire, `Job` in
  the viewer. `POST dev/build` keeps its name, since it asks to build a Blick. A job also has
  `seconds`, how long it has run or waited when `dev/info` answered, which the viewer counts on
  from, so that a browser whose clock is apart from the server's (a cluster behind an SSH tunnel)
  counts right.
- **`POST dev/build` answers `done`, not `built`** (decided in review), for a Blick with nothing
  to do whatever its status, so that "built" keeps meaning ok, as in `check`. Its answer has no
  revision (decided in review): a client waits until the Blick has left `dev/info`'s `jobs`.
  `rebuild` is a strict boolean, so `"yes"` or `1` is a 400. A Blick queued or building is still
  `pending` in the manifest.
- **`dev/info` has `stopped`** besides `revision` and `jobs`: why the worker stopped, which
  "dev/info says so if the worker itself has died" asks for. The viewer shows it on a Blick's page
  in place of the build line. `POST dev/build` then answers 409. It keeps its name beside m2-2's
  planned `status` and `detail`, which are about the session, as m2-2's "Changed by on-demand
  Blicks" says. `dev/info` also has `session`, the session's id, so that the viewer reads the
  manifest again after a restart of `blicket dev` even when the revision is the same; and a page
  left open on an expensive Blick asks for it again after a restart, which built nothing yet.
- **The session's id** is 16 random hex digits, the shape of a build id, so that a comparison's
  `current.id` stays one; the manifest's `created_at` is when the session started. The footer says
  `session started <time> UTC`. The manifest and the comparisons of a session carry the header
  `Blicket-Revision`, which the viewer compares with the revision of `dev/info` (decided in
  review), so that the manifest, the comparison and the jobs it shows are of one revision, and a
  Blick built for the first time never reads "Rebuilt".
- **The overview counts what is left, of all the Blicks** (decided in review): `53 of 56 Blicks
  not built yet`, the words of the cards and the sidebar's foot, with one denominator everywhere.
  A Blick whose definition is invalid is neither built nor left to build and is named so, `1 Blick
  has an invalid definition`, not "failed to build"; the terminal says `16 Blicks: 15 built when
  opened in the viewer (expensive) · 1 error`. The note and the count are one notice under the
  comparison bar (`An expensive Blick is built when you open it.` / `53 of 56 Blicks not built yet
  · Cement trade is building (0:42).`), with a visually hidden status that tells a screen reader
  the same without the time; `ComparisonBar.vue` is unchanged, since a comparison holds the built
  Blicks only and its counts are of them. "A first look" leaves out the Blicks already under
  "Changed since the baseline".
- **The sidebar marks a Blick not built yet** with a dashed circle and in the muted grey of the
  other entries, not dimmed, which failed contrast; the entry of the page shown keeps the active
  colour while it builds. Its screen-reader suffixes say `(building)`, `(queued)` and `(not built
  yet)`.
- **A page that offers `Build next` asks for its Blick itself once no Blick a page asked for builds
  or waits**, which is the table's first row; a hint under the button says so. A page asks at
  most once per visit to the Blick: a request that fails is repeated by Retry, not by the page.
  While its request runs the page says `Asking blicket dev to build it…`, and when the job ahead is
  queued, not building, `<title> is about to build.`
- **A rebuild that waits** has a state the table lacks: a built Blick whose rebuild is queued
  behind another shows `Rebuild queued behind <title>`; `Queued behind <title> and N more` counts
  the Blicks waiting ahead. Cards say `Building…` and `Queued` besides `Not built yet`, and a
  queued Blick has a clock where a building one has a spinner, both in one map for the sidebar
  and the cards that stays the same object while a build only goes on. When nothing builds, the
  page's line says how the last build ended and in how long (`Built in 3.2 s`, `Failed in 412
  ms`, `Skipped in 104 ms`), and when, if the page saw it end (`Rebuilt in 3.0 s at 12:04:10`), so
  that a screen reader is told and the page does not jump; the browser tab's title says
  `Building…` while the page's Blick builds; `Rebuild` has the tooltip `Run the transformation
  again`.
- **Other words of the viewer in a session**: a value that the URL names and the table lacks is
  "not in this run" instead of "not in this build"; "No such Blick in this session"; the overview
  with nothing left to build says `None of the 56 Blicks is left to build`; a manifest that cannot
  be read again leaves the page as it is, and a Blick's page warns `What the page shows may be
  older than the run`. The builder's page, for a run without a dataset, says `The builder is off`
  and the reason `blicket dev` gives (`dataset(run) returned None`), and that a run of expensive
  Blicks usually has none.
- **When `dev/info` stops answering**, a page whose Blick builds says `It was building when
  blicket dev stopped answering.` and counts no time; spinners stop. A restart of `blicket dev`
  is a new `session`: an open tab reads the manifest again.
- **A build that raises outside the transformation** (a bug in blicket, or a `BaseException` such
  as `KeyboardInterrupt` that the transformation lets through) gives the Blick an error of the
  problem kind `build`, `building the Blick raised …`, and its comparison the flag `error`.
  Comparing that raises (decided in review), a bug in a plot type's `diff` or in polars, flags
  the comparison `error` with `comparing raised …` and leaves the Blick built and its table; so
  does a table of the baseline that cannot be read or does not match its hash, whose message
  says that the baseline is damaged and what to do.
- **The build lines** (`rebuilt` and the start line decided in review) say `built`, `rebuilt`
  (built before in the session), `failed` or `skipped` and the time (milliseconds under a second,
  `x.y s` under a minute, then `2 min 5 s` and `1 h 2 min 5 s`, each as it is rounded, as the
  viewer says it; the run line of `build` and `check` is as it was), the first line of the error
  or reason with where it was raised and `(-v for the traceback)`, further errors on lines below,
  then what the comparison found (`value, 2.1% of scale (…)`, `schema`, `new`, `removed`, or
  `unchanged`), and `N warnings: <the first>` when the table has some; without a baseline they say
  nothing of a comparison. A line on stderr, `HH:MM:SS building <id>`, marks where a build starts.
  The start report has `check`'s order, and the removed Blicks, which the definitions alone tell,
  in a line `vs baseline: 1 removed (extra/slow)`. Nothing about these lines costs a build
  (decided in review): every line goes through one guarded writer, so a reader of stdout or stderr
  that goes away (`| head`), a full disk (`2>/dev/full`), a stream closed or a line that cannot be
  rendered leaves the line out, the stream silenced, and the worker builds on; the worker records
  why it stopped before it tries to say so. An exception without a message is named alone (`raised
  KeyboardInterrupt`). `dev --help` names the stderr line too, and `--out` says in its help, and
  on stderr when given, that `dev` does not use it.
- **The builder line for a `dataset(run)` that returned `None`** (decided in review) says the
  fact, `builder: off, dataset(run) returned None`, so that a `dataset` that forgot its `return`
  is told apart from a run that has none; it stays no warning.
- **Errors**: `errors.Refused` (409: an expensive Blick builds while a query asks, the worker
  stopped; `LoadRefused` for `dev/run`) and `errors.NoSuchBlick` (404: no Blick of that id to
  build, or no run served yet); for a Blick whose definition is invalid the message says so. The
  409 of `dev/query` says what to do, `an expensive Blick is building; run the query again when it
  is built`, and stays out of the access log. One object, `RunLock`, holds the lock and what
  builds, so that a query waits or is refused without polling.
- **Tables kept**: the tables a rebuild replaced are kept for `KEPT` (eight) revisions, not one,
  since a tab that polls once a second can lag more than one revision behind a run of quick
  builds; then the route answers 404 with what to do, worded also for a hash never built. A table
  built again unchanged is kept once, the bytes already kept reused; the baseline's tables are
  served from the bytes the comparison read, once per file, not from the store at each request,
  so a store cleaned meanwhile changes nothing.
- **The viewer's poll lives in `useRefresh`**, which the shell starts for every session of
  `blicket dev`, not in `useDev`; `isInfo` requires the fields of `dev/info`, which a viewer and a
  server of the same installation always agree on. The session's progress is `Progress`, apart
  from a Blick's `Status`.
- **The test project** holds gates (`threading.Event`s) in its run that a test closes to hold a
  table, and the session's `wait_idle` waits until the worker has nothing left and has printed its
  last line; it has a dataset only with `BLICKET_TEST_DATASET`.
- **`pnpm generate`** writes an `index.html` of `"Redirecting..."` on the machine this was built
  on, which has Node 26 only, at the base commit as well, so the relative base URL `./` meets a
  redirect when Nitro prerenders the page; generated with `NUXT_APP_BASE_URL=/`, the viewer is
  right when served at the root, as `blicket serve` and `dev` do, which is how it was walked
  through. Nothing in this feature touches it.

### Of the revision

Recorded while the revision was built on the first version's code, 2026-11-16, and in its three
review rounds.

- **One worker per session** (decided in review): `jobs.Worker` belongs to the session for its
  whole life and holds one ranked list of jobs (cheap asked, expensive asked, background), which
  one choice serves for the worker and for the fast path of `POST dev/build`. Its jobs are
  `Task`s, `Build` so far, each queued with the run it is for; `OnDemandRun` is the state a job
  acts on. A job holds the session's lock from before its first line to after its last line, its
  publish and the background report included, so a load comes between two jobs, and nothing of
  the run before is built, printed or published after `loading`. A load swaps the run and drops
  the jobs of the run before. m2-2's code reload is a second kind of `Task`; the split of what
  the definitions give (the registry, the expensive Blicks, the background's order, the baseline)
  from what was built (tables, snapshots), so that a reload keeps the tables, is left to it.
- **A load holds the session still** (decided in review): while a load holds or waits for the
  lock, the worker takes no job, and `dev/query` and `POST dev/build` answer 409 `a run is
  loading; …`, since a loader may take minutes and replaces the run and its dataset. The plan
  named only the refusal during an expensive build. `dev/run` answers 409 once the worker
  stopped.
- **The revision rises across loads** (decided in review) and is owned by the run's snapshot: a
  load's first revision is the one served + 1, so that `Blicket-Revision` alone never confuses two
  runs of one session.
- **`Session.begin()` starts the worker** after the start report and the viewer line are
  printed, so that no build line comes before them.
- **The background report** has the time in its first line (`12:00:03 6 Blicks: 3 built · 1 not
  built yet · 2 errors`) and is printed once, when every cheap Blick is built, one a page moved
  out of the background included; a session without a cheap Blick prints none. It leaves out the
  file-level and invalid-definition problems that the start report listed (decided in review), and
  its verdict counts the Blicks built, as the comparison bar does.
- **HTTP**:
  - `compare/index.json` answers `[]` in a session without a baseline instead of a 404, which
    each revision would print twice in the terminal now that every session polls, and a JSON 404
    with `Blicket-Dev` before a run is served, as `manifest.json` does;
    `compare/<id>/comparison.json` for an unknown id is a JSON 404. The snapshot keeps the
    comparison as a model, as it does the manifest. The viewer polls once a run is served, not on
    the empty picker.
  - `dev/runs` gives every entry `project` (false for a folder) and `served`, computed by the
    server from resolved paths, so that a run reached through a link is marked too.
  - `dev/run` answers 422 with the loader's error when the load fails, and 400 for a path that
    `dev/runs` does not list, a relative one (`… is relative; send the absolute paths that dev/runs
    lists`) or another body. The 409 of a refused load names the Blick and its time (`Steel
    production is building (1:10); load the run once it is built`), which the viewer does not count
    on, and stays out of the access log.
  - `PUT`, `DELETE` and `PATCH` on a route of `dev` answer a JSON 405 with `Allow`, and on another
    path under `dev/` a JSON 404; `Refused` and `NoSuchBlick` become 409 and 404 in one place.
  - `dev/info` keeps `root`, `dataset`, `message` and `failed` beside the fields the plan names.
  - A builder query waits for the cheap build that holds the lock, not for the background.
- **A cheap Blick's page** asks once per visit: a build when the Blick is not built, a rebuild
  when it is built and nothing of it waits, nothing while it builds or waits. `Updating… 0:08`
  counts its job's time; `Updating after <title> (m:ss)` shows only when the build ahead is
  expensive; a lost connection says `It was updating when blicket dev stopped answering.`
- **The outcome line has a time only after a fresh answer** (decided in review): `refresh()`
  resolves to whether an answer asked for after the call was shown, and a page knows that its
  build ended when, after it asked, the Blick has left `jobs`, not by comparing entries. A rebuild
  whose entry is the same says `Rebuilt … at 12:04:10` too, and one whose end the page did not see
  says no time.
- **The overview's building line** names only the Blicks a page asked for, never the background.
  Without an expensive Blick the count is the notice's title, and the notice goes once nothing is
  pending.
- **The picker**:
  - The served run has a `served` badge and the line `The run served, b, is marked; loading
    another replaces it.`
  - The question is a dialog, `Load another run?`, without an animation. It stays, with a spinner
    on its `Load` and `Cancel` disabled, until `dev/run` answers, and on a refusal closes with the
    focus on the message.
  - `This project` loads alone: ticking it unticks the folders, and the hint says so.
  - `Back to the overview` stands beside `Refresh` while a run is served, and `Pick another run`
    is hidden on the picker itself.
  - While a load waits for a cheap build, the picker says `Waiting for <title> to build… m:ss`,
    then `Loading …`.
- **The session's fields of an entry** (`expensive`, `pending`) are set by one function,
  `jobs.stamped`; `Blick.entry` takes neither. `RunInfo.expensive` is a strict boolean, as the
  Blick's option is. One `Terminal`, owned by the session, writes every line of the session, so
  a stderr that fails leaves a failing load its 422.
- **A load clears the builder's kept query tables**, which belong to the run before.
- **`--out`**: its line on stderr is printed once at the start, also when no run is given.
- **The test project** has `steel/shares` with `expensive=False` and `plastics/validation` with
  `expensive=True`, so that neither of its modes is purely cheap or purely expensive; the report
  lines of those are tested in a temporary copy without some modules. `values.txt` at its root
  makes `.` a run, with the id `checkout`.
- **The examples' READMEs** (`remind`, `remind-mfa`) no longer say that `dev` checks a run as
  `check` does.
