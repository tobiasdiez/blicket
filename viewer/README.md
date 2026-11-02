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
the Blick builder, run `uv run blicket dev <run>` in terminal 1 instead of `serve`: the paths
under `/dev/` are its own, and the proxy rewrites the `Host` header of a request to them, since
`blicket dev` answers a query only when the header names it.

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
`PlotArgs.compact`: 160 px high, without legend and export menu, the tooltips, the highlights and
the baseline kept. `frame()` turns off the legend of each encoding, since an encoding's own
`legend` wins over the config's `legend.disable`. A card of a skipped Blick says so with the first
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
palette in `app/plots/theme.ts`. A channel the plot puts on a logarithmic axis (`PlotArgs.scales`)
gets its encoding from `scaled` in `app/plots/scales.ts`: "(log scale)" in its title, ends at the
data, and grid lines at the labelled ticks only. `frame` hands Vega the values at or below zero
on such an axis as null, since Vega-Lite filters only null, NaN and infinite values; the line
breaks there, a tooltip shows the en dash of a missing value (the data tab keeps the number), and
`BlickChart` says below the chart how many current values it left out.

While "Compare with baseline" is on, `app/plots/change.ts` draws two charts under a built-in
type's chart: the change of each row, absolute and relative, through the type's own specification
builder, which each built-in module exports next to its `definePlot` and `app/plots/index.ts`
collects, on the chart's x scale and a linear y, since a change crosses zero. Rows are compared as
the Python diff routine compares them: a row missing from one table counts as 0, and a row with a
dimension value only one table has gets no change drawn. A value counts as present when a row of
the selection carries it, while the routine looks at the whole tables, so a sparse table under a
filter can differ from the comparison's verdict.
`tests/table.parquet` is the one checked-in file: the Parquet reader must read a real zstd file,
and the test says how polars wrote it.
