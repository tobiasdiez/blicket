# blicket viewer

The web viewer of a blicket build directory: a Nuxt 4 app in client-only mode with hash routing
and a relative base URL, generated to static files and shipped inside the blicket wheel. What it
shows and how a build directory is served is in the [root README](../README.md#looking-at-a-build);
the design is in [docs/plans/m1-viewer.md](../docs/plans/m1-viewer.md). Node and pnpm are needed
only to work on the viewer and to build the wheel that bundles it.

## Developing

With a build of the example (see [its README](../examples/remind-mfa/README.md)), and
`BLICKET_VIEWER` set for terminal 1 as the [root README](../README.md#development) shows (any
generated viewer will do: the dev server only takes the data from it):

```console
$ cd examples/remind-mfa && uv run blicket serve       # terminal 1, the data
$ cd viewer && pnpm install && pnpm dev                # terminal 2, the app
```

The dev server forwards `/manifest.json`, `/blicks/`, `/compare/` and `/dev/` to `blicket serve`
at `http://127.0.0.1:8765`, or the address in `BLICKET_SERVE`, so the app reads `./manifest.json`
as it does in a build directory, and nothing else on the machine can read the data. To work on
the comparison, serve a build directory that `blicket check` wrote comparisons into. To work on
the Blick builder, run `uv run blicket dev <run>` in terminal 1 instead of `serve`, and on the run
picker `uv run blicket dev` without a run: the paths under `/dev/` are its own, and the proxy
rewrites the `Host` header of a request to them, since `blicket dev` answers a query or a load
only when the header names it.

```console
$ pnpm test         # vitest on app/lib and app/plots, without Nuxt
$ pnpm typecheck    # nuxt typecheck, tests included
$ pnpm lint         # oxlint; unused variables in .vue files are pnpm typecheck's
$ pnpm generate     # the site, in .output/public
```

How blicket from a checkout uses a generated viewer (`BLICKET_VIEWER`), and how an installation
bundles it, is in the [root README](../README.md#development).

The Blick builder (`app/pages/builder.vue`, `#/builder`) is there in every generated site, but
works only under `blicket dev`; served from a build directory it says so. The viewer is in dev
mode when `manifest.json` comes with the header `Blicket-Dev: 1` (`useManifest`), and only then
shows "Build a Blick" under the sidebar's list, and on an overview without Blicks, and asks
`dev/info` (`useDev`). The page asks
`dev/dataset` for what the builder offers when `dev/info` says there is a dataset (`useDataset`),
posts the builder's state to `dev/query` and draws the entry it gets back with the Blick page's
components (`useQuery`). `app/lib/builder.ts` holds the state in the URL, the roles of the
dimensions, the request and the line that says what a chart was summed over, and describes the
shapes of `src/blicket/query.py` and `src/blicket/dataset.py` by hand; `app/lib/latest.ts` runs
only the latest of the queries, debounced, so a late answer never replaces a newer one, and
`app/lib/dev.ts` makes the requests to `blicket dev`, checks the shape of each answer and tells a
server that does not answer from one that refuses. The URL
keys of the builder start with an underscore (`_q`, `_plot`, `_c.<channel>`, `_keep`,
`_only.<dim>`, `_from.<dim>`, `_to.<dim>`); the controls keep the Blick page's (`<dim>=value`,
`_split`, `_y`), and a dimension on panels is in `_keep` and `_split`, so that the control bar's
split toggle turns it into a filter without a new query. A query's table is fetched as a Blick's
is, by its content hash; of the builder's tables, `dev/tables/<hex>.parquet`, the viewer keeps
the last 50 it used, and of a build's all.

The run picker (`app/pages/runs.vue`, `#/runs`) is the page while `blicket dev` serves no run yet.
`blicket dev` then answers `manifest.json` with a 404 that carries the header `Blicket-Dev: 1`
(`isNoRun` in `app/lib/dev.ts`), which `useManifest` records as `noRun`, and the shell
(`app/app.vue`) sends every route to `#/runs`, under the header without the sidebar and the run.
While a run is served, the header has `Pick another run` when `dev/runs` lists globs, which opens
the same page with the run served marked (`served` in `dev/runs`) and a link back to the overview.
The page lists the folders of `dev/runs` (`useRuns`), the project itself first when `runs` has `.`
(`project`, said to be computed from code, `whenText`), which loads alone (`ticked`), posts the
ones ticked to `dev/run` (`postRun`), which answers once the run is loaded and its baseline found,
and then reloads the viewer on the overview, since the session is another; a load that fails leaves
the ticks and the run served and shows why under the list, the keyboard staying on Load; while the
load waits for a cheap Blick that builds, the page says so and for how long (`loadingLine`). Before
a load that drops expensive Blicks built (`expensiveBuilt`), it asks in a dialog (`dropQuestion`),
without a transition, which stays until blicket dev answers; a load refused or failed closes it and
gives the keyboard to the alert under the list. `app/lib/runs.ts` holds the page's words and ticks:
how long ago a run changed, the load button's label, the `runs` setting, how a tick changes the
others, the ticks a new list keeps (`keepListed`) and the question; `app/lib/time.ts` writes a time
in UTC, for the picker and the comparison. Served by `blicket serve`, the page says that it needs
`blicket dev` and links the overview.

A session of `blicket dev` builds its Blicks while the viewer is open (see the
[root README](../README.md#developing-blicks)): a cheap Blick in the background and again at each
visit of its page, an [expensive one](../README.md#expensive-blicks) when its page asks for it.
`useRefresh`, which the shell starts in every session once it serves a run, asks `dev/info` once a
second while the tab is visible, and when its `session` or `revision` is not the one shown, reads
the manifest and the comparisons again without showing them (`fetch` of `useManifest` and
`useComparison`, through `reloadable` in `app/lib/resource.ts`), and once their header
`Blicket-Revision` names the revision of the answer, shows all three at one moment (`afterReading`
in `app/lib/reload.ts`), so that no page sees a Blick built and still building; when a Blick was
built meanwhile, it asks `dev/info` and reads them again at once, a few times at most before it
leaves them to the next tick. A restart of `blicket dev`, or the load of another run, is a new
`session`, read again whatever its revision. Asked while it reads, it reads once more after, and
`refresh` settles once a read asked for after the call has ended (`coalesced`), to whether its
answer was shown, so that a page that asked for a build knows whether it sees an answer that
knows of it. `useJobs` gives the pages what that answer
says, computed once for them all: the `jobs`, the Blick building and the Blicks a page asked for
that wait, each `asked` or of the background; where each Blick stands in them (`marks`, one map
that stays the same object while a build only goes on); the expensive Blicks, which the manifest
marks `expensive`; why the worker `stopped`; the seconds since the answer; whether `dev/info`
stopped answering (`lost`); and a Blick's title by its id (`title`).
Reading again disturbs nothing: `app/lib/reload.ts` keeps the entries and comparisons that did not
change as the objects they were (`share`), and the baseline chosen, "No baseline" too
(`keptChoice`); `useTable` fetches a table again only when its path or hash changed and keeps the
rows shown while their owner is the same (`rowsStay`, `rowOwners`): the Blick owns its own table's
rows, the baseline's table its own, so that another baseline never draws the old one's rows;
`useBlickChart` draws the entry before a rebuild until its new rows arrive (`settled`), so that new
controls never meet old rows; and `BlickChart` redraws only when its rows, or what it is drawn as,
change by value. A manifest that cannot be read again leaves the page as it is, and a Blick's page
warns that it may be older than the run. A poll that fails shows `Cannot reach blicket dev` with
Retry on a Blick's page, which then says that its Blick was building when contact was lost, and
counts no time; elsewhere the page stays as it is, its spinners stopped.

`useBlickBuild` is the build of the Blick on its page: `app/lib/jobs.ts` says what the page shows
(`pageState`) and what a visit asks (`visitRequest`), once per visit, and once more after a restart
of `blicket dev` (`visitOf`). A cheap Blick not built is asked for at once; built, it is asked for
again, and the page shows what was built under `Updating… 0:08`, or `Updating after <title> (0:42)`
behind an expensive build, not dimmed, without `Rebuild`. An expensive Blick not built is asked for
while no Blick a page asked for builds or waits, the background not counted; otherwise the page
offers `Build next`. The page says where the Blick waits or how long it builds (`statusLine`, which
names a Blick by its title, as a link, and leaves the time out of what a screen reader is told),
and offers `Rebuild` on an expensive Blick built (`rebuildable`), dimming it while it rebuilds; how
the last build ended (`outcomeLine`) takes the line's place when nothing builds, with the time when
the page asked for the build and saw it end: once blicket dev took the request on and an answer of
`dev/info` read after it was shown, the build ended when the Blick has left the jobs
(`askedEnded`), whether or not its entry changed, `Rebuilt` for a Blick built before; without such
an answer, the line says no time. `BuildStatus` draws the line, one `role="status"` that stays
while the page shows the Blick, and moves the keyboard to it after `Build next`, since the button
goes. An entry `pending` is a Blick not built yet: its card says so (`pendingText`: `Not built
yet`, `Queued`, `Building…`), the sidebar marks it with a dashed circle, a spinner while it builds
and a clock while a page asked for it and it waits, and counts them at its foot (`pendingCount`);
the overview says, in one notice (`overviewNotice`), that an expensive Blick is built when it is
opened, when the session has one, how many are left of all the Blicks (`notBuiltLine`) and which
Blick a page asked for builds (`buildingLine`), also to a screen reader, and in a session with an
expensive Blick fills "A first look" with the first six Blicks not already under "Changed since the
baseline" (`previewSections` with `expensive`); the footer names the session instead of a build
(`footerText`). An entry in error without a timing failed in its definition, which no build changes
(`isInvalid`): its page says where to fix it and has no `Rebuild`.

The shell (`app/app.vue`) is a row: the sidebar (`BlickSidebar`, on Nuxt UI's `USidebar`), and
a column of the header, the page and the footer. From 1280 px (Tailwind's `xl`) the sidebar stands
next to the page and the header's button collapses it; below, it is a drawer that the button opens
and a picked Blick closes. Whether it is open on a wide window is kept in the browser's
`localStorage` under `blicket:sidebar` (`useSidebar`), written only by the button, since the
sidebar closes itself on a narrow window. The search and the "Changed" filter are the sidebar's
own state, not in the URL, since the sidebar outlives the page; `app/lib/sidebar.ts` groups,
searches and filters the Blicks, and `app/lib/comparison.ts` gives each its badge
(`blickBadge`, drawn by `FlagBadge`). A Blick skipped for the run that no comparison flags has no
badge but its label in italics, its search text holds `skipped` and the reason, and the sidebar's
foot counts the skipped Blicks; a group of nothing but such Blicks starts closed
(`initiallyOpen`). The pins are a list of Blick ids under `blicket:pins`
(`usePins`, `app/lib/pins.ts`): per origin, read again on another tab's `storage` event, and
matched with the build's Blicks through their aliases too. `app/lib/storage.ts` reads and writes
both keys so that a browser that blocks storage only forgets them.

`app/lib/preview.ts` makes the overview's sections, the state a card draws, one panel, the one
where the change is largest when the comparison names it, and the card's caption and link. The
changed Blicks are six cards and, under a line "N more changed", a ranked list; the pinned ones
are cards with a button that unpins them, and while nothing is pinned or changed the section is "A
first look" at the first six Blicks, whose buttons pin them. After a click the overview puts the
keyboard on the button of the card in its place (`data-blick`, `data-pin`). A card
(`BlickPreview`) fetches its tables once it comes into view, through `useBlickChart`, which the
Blick page uses too, as the builder uses its `chartPropsOf`. Its chart is compact,
`PlotArgs.compact`: 160 px high (a Sankey diagram, which has no axes, 204 px), without legend and
export menu; the tooltips and highlights are kept, and the baseline too except on a Sankey.
`frame()` turns off the legend of each encoding, since an encoding's own `legend` wins over the
config's `legend.disable`. A card of a skipped Blick says so with the first
line of the reason, and its page with the whole reason; a line under the comparison says how many
Blicks the run skipped (`skippedLine`). Under the cards, whatever the comparison, the
overview lists the Blicks in error with their problems, the build's own problems from
`manifest.json`, and whether a Blick module failed to import: a Blick's problems are in its entry
only, and the sidebar, collapsed or a drawer, may not be in view. A line at the top (`troubles`)
says so with a button that brings the list into view.

`app/lib/manifest.ts` describes the manifest of the spec in its `SPEC` by hand; the Python models in
`src/blicket/manifest.py` and `model.py` are its source of truth, and the viewer refuses a build
of another spec. `app/lib/comparison.ts` describes `compare/<baseline id>/comparison.json` the
same way, after `src/blicket/comparison.py`. A build that was never checked has no
`compare/index.json`, and the browser's console logs the request's 404, as every static host
answers it.

A plot type's browser half (`app/plots/`) is a Vega-Lite specification built from the rows the
controls select, and from the baseline's rows after the same filters when the chart is compared
(`PlotArgs.baseline`): the built-ins draw them behind the current marks, faded and broader, in the
series' colours, and solid whatever the line style, as remind-mfa draws its reference run; the
legend click and the tooltip tell lines of a repeated hue apart. Their colours are the validated
palette in `app/plots/theme.ts`. The charts over a dimension on x (`line.ts`, `stacked_area.ts`,
`bar.ts`) share `channels()` and the encodings in `encodings.ts`; `scatter.ts` has a measure on
both axes. An axis is linear or logarithmic as the definition's `scales` choose
(`PlotArgs.scales`): `scaled` in `app/plots/scales.ts` gives a logarithmic axis its encoding,
"(log scale)" in its title, ends at the data, and grid lines at the labelled ticks only. `frame()`
in `layout.ts` lays out either kind of chart, and its data preparation makes a value at or below
zero on a logarithmic axis missing (`masked` in `scales.ts`), since Vega-Lite filters only null,
NaN and infinite values; the line breaks there and a tooltip shows the en dash of a missing value
(the data tab keeps the number). A chart leaves out such rows, and a scatter also those without an
x or a y; `leftOutNote` and `nothingToDraw` in `app/plots/index.ts`, which `useBlickChart` calls,
give the line under the chart that says how many and why, and tell the page and the cards when
none is left, which they say instead of a chart. A change chart gets the chart above as
`PlotArgs.above`, so a scatter's change charts share its x domain and name the baseline's x when x
moved between the runs.

The Sankey diagram is the exception. `app/plots/sankey.ts` holds what the plot types and the change
charts need: its channels, the panels' grid and the change bars, a bar per link that changed. Its
`render` holds about the chart's room and loads `app/plots/sankey_diagram.ts` by a dynamic import,
so only a page that draws a Sankey fetches that chunk, with `app/plots/sankey_graph.ts`, the rules
without the DOM, and `app/plots/svg_export.ts`, the export of SVG built by hand. Each panel's graph
is a node per value of the source and target columns and a link per row with a positive value
between two nodes; d3-sankey-diagram lays it out and draws the links and node bars, with
d3-selection 1, and the module draws the legend, whose click fades the other colour values, the unit
of the links' width, the panel and node labels, a caption that counts the rows not drawn, the
tooltips through vega-tooltip, in the other charts' look, on hover and on a tap, and an export menu
like vega-embed's. Given less than 61 px per layer of nodes, by more than 16 px in all, the diagram
scrolls sideways in a box of its own under the legend. `app/plots/d3.d.ts` declares what of the two
packages it uses, since they ship no types. The library breaks loops where a depth-first walk meets
a node again; the module gives it the nodes and flows in the order whose walk turns back the least
flow, so the main chain runs forward, drawn as ribbons rather than the library's arcs, and recycling
loops back, under the other links and fainter, and lays a panel out again in a narrower box where
such a loop would reach past its sides. A Sankey does not draw the baseline behind
(`drawsBaseline: false` in `app/plots/index.ts`): its tooltips give the baseline's value and the
change, and the overview's caption and the switch leave the faded baseline out.

While "Compare with baseline" is on, `app/plots/change.ts` draws two charts under a built-in
type's chart: the change of each row, absolute and relative, through the type's own specification
builder, which each built-in module exports next to its `definePlot` and `app/plots/index.ts`
collects, on the chart's x scale and a linear y, since a change crosses zero; the page says there
is nothing to compare when the Sankey's would draw no bar. Rows are compared as the Python diff
routine compares them: a row missing from one table counts as 0, and a row with a dimension value
only one table has gets no change drawn. A value counts as present when a row of the selection
carries it, while the routine looks at the whole tables, so a sparse table under a filter can
differ from the comparison's verdict.
`tests/table.parquet` is the one checked-in file: the Parquet reader must read a real zstd file,
and the test says how polars wrote it.
