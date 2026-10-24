# M1 The viewer: catalog, Blick page, `blicket serve`

Status: plan, 2026-10-24, revised the same day after an independent review that scaffolded the
stack in a scratch directory and read a real Parquet file with it. Milestone M1 of [m0-tasks.md](m0-tasks.md)'s parent list in
[architecture.md](../architecture.md), pulled ahead of M0.5–M0.7 on Tobias's decision of
2026-10-24: the comparison comes after the UI. Builds on M0.3 (commit `fe60daf`). Companion to
the architecture's "Viewer (Nuxt)", "Build directory" and "Plot type contract" sections; where
this plan fills in or refines a detail, it says so.

## Goal

A build directory becomes something to look at. `blicket build` writes the viewer next to the
manifest, `blicket serve <build dir>` opens it, and the browser shows the catalog of a run: every
Blick as a card, grouped and searchable, and a page per Blick with the chart its plot type
renders, the controls derived from its table, and the control state in the URL. The four
built-in plot types get their browser halves. Node and Nuxt stay maintainer-only: the generated
viewer ships inside the wheel. Nothing about comparison yet; the overview's change colouring and
the comparison toggle arrive with M0.5–M0.7 as additive features.

## The flows this task enables

### 1. Build and look

```
$ cd examples/remind-mfa
$ uv run blicket build ../../data_out/2026-10-24--01-25-28_plastics_SSP2_h12
run 2026-10-24--01-25-28_plastics_SSP2_h12 · profile plastics_SSP2_h12 · blicks at fe60daf · loaded in 0.7 s
10 Blicks: 10 built
build 3abdf5dbc04efb97 → .blicket/build/3abdf5dbc04efb97
$ uv run blicket serve .blicket/build/3abdf5dbc04efb97
viewer: http://127.0.0.1:8765/#/   (Ctrl-C stops)
```

1. The overview opens: a header with the run id, profile and the Blick repository's commit; the
   groups as sections; a card per Blick with title, description, plot type and its dimensions;
   a search box and group and tag filters; failed Blicks as cards with their problems.
2. Clicking "Production by polymer" opens `#/blick/flows/production_by_polymer`: a stacked area
   chart, Time on x, Polymer as colour, one panel per Region because the Blick asked for
   `controls={"Region": "split"}`; above it the controls the manifest lists: nothing else here,
   since Time, Polymer and Region are all bound or split. "Scenario rates" is changed in this
   task to show the other kind: Region stays the colour, `Parameter` becomes a filter with
   `defaults={"Parameter": "collection_rate"}`, so a dropdown appears (today every example Blick
   splits or binds all its dimensions, and no filter would ever be seen).
3. Changing a control updates the chart and the URL
   (`#/blick/drivers/scenario_rates?Parameter=landfill_rate`), so the link reproduces the view.
   A toolbar toggle switches the panels between a shared y axis (default) and independent axes;
   a "data" tab shows the table's rows; the raw Parquet file is one link away.
4. The build directory is self-contained: copied to a laptop or pushed to GitHub Pages, it works
   from any sub-path (relative base URL, hash routing). Only `file://` does not work, because
   browsers block `fetch` there; `blicket serve` is the answer.

### 2. Developing the viewer

```
$ uv run blicket serve examples/remind-mfa/.blicket/build/3abdf5dbc04efb97      # terminal 1
$ cd viewer && pnpm install && pnpm dev                                            # terminal 2
```

Nuxt's dev server with hot reload proxies `/manifest.json` and `/blicks/` to `blicket serve`
(a `nitro.devProxy` rule, port from `BLICKET_SERVE`, default 8765), so the app always reads
`./manifest.json` and no CORS header is needed; a page of unpublished model data stays private to
the machine. `pnpm generate` produces `.output/public`. For a development installation,
`BLICKET_VIEWER=viewer/.output/public` tells `blicket serve` and `blicket build` where the generated
viewer is; the release wheel bundles it: `uv build --wheel -Csetup-args=-Dviewer=enabled`.

## Facts the plan rests on (checked 2026-10-24)

- Versions: Nuxt 4.6.2, Vue 3.5.44, vega-lite 6.5.0, vega 6.4.0, vega-embed 7.3.0, hyparquet
  1.31.5, hyparquet-compressors 1.1.2, vitest 5.0.5, vue-tsc 3.3.13, @nuxt/ui 4.12.0; Node
  26.11.1 and npm 12.2.1 on this machine, pnpm 12.15 too.
- Nuxt 4 documents the client-only static site: `ssr: false`, `router.options.hashMode: true`,
  `NUXT_APP_BASE_URL=./ npm run generate` for relative asset paths, output in `.output/public`
  with an `index.html` entry point. `runtimeConfig.public` values are overridden by `NUXT_PUBLIC_*`
  environment variables at build time, which gives the dev server its build URL.
- hyparquet reads a polars zstd Parquet file in the browser with the `compressors` object from
  hyparquet-compressors (verified on an example table: 23,556 rows; without the compressors zstd
  fails). INT64 columns come back as BigInt and need conversion to Number for Vega-Lite; dates come
  back as `Date` at UTC midnight. Python's `http.server` ignores Range requests, so hyparquet's
  `asyncBufferFromUrl` falls back to a HEAD plus a full GET; fetching the whole file with
  `fetch().arrayBuffer()` is one request on any host and the tables are small.
- Verified in a scratch app: Nuxt 4.6 with `ssr: false`, `hashMode` and `NUXT_APP_BASE_URL=./`
  gives `./_nuxt` paths and works from a sub-path in headless Chrome, deep links included;
  `NUXT_PUBLIC_*` values are baked in at generate time; Vega-Lite 6.5 compiles wrapped facets,
  `resolve`, `xOffset` and `strokeDash`; `typescript@7` breaks vue-tsc 3.3 (pin `^6`), and
  `vue-tsc --noEmit` on Nuxt's references-only tsconfig checks nothing (`nuxt typecheck` does);
  plain vitest 5 runs `lib/` tests without Nuxt test utilities when those files avoid auto-imports.
- Nuxt UI 4.12 builds with Nuxt 4.6 client-only, but adds 0.6 MB to the generated site (199 KB
  of CSS) and 120 MB to `node_modules`, and fetches icons at runtime from api.iconify.design unless
  an icon set is bundled; a paper supplement must work offline.
- meson rejects path segments in a `custom_target` output name, so the viewer script copies
  `.output/public` into `@OUTPUT@`; a directory output installs into the pure wheel;
  `build_always_stale` is needed or an edited viewer reports "no work to do". Nuxt's output is not
  reproducible unless `buildId` is fixed and the app manifest (`experimental.appManifest`) is off.
- The example's manifest shows that every Blick either splits or binds all its dimensions: no
  filter control, no `defaults`, exist in it today.
- The manifest holds almost everything the viewer needs: run, repository and config; groups with
  titles and tags; per Blick the definition (title, description, tags, plot type and mapping,
  `controls` requests, `defaults`, `order`), `data` (the Parquet path), `columns` (dimension names,
  dtypes and values in display order; measures) and problems. It lacks the derived controls
  (added in this task, see below), units and display names (every measure is `value`; units live
  in the description text; a `unit=` option is deferred).
- The polars `write_parquet` default is zstd with statistics; files are kilobytes to a few
  hundred kilobytes.
- meson's `custom_target` can run an arbitrary command producing an output directory and install
  it under `py.get_install_dir()`; a `feature` option gates it. meson-python's editable install
  reruns the build on import, so a viewer target must be off by default for development.
- The dataviz skill in this environment (palette, axis and tooltip rules, light and dark) is
  loaded by whoever writes chart code.

## Approach

### Layout

```
viewer/                       the Nuxt 4 app, pnpm, pnpm-lock.yaml committed
  package.json  nuxt.config.ts  tsconfig.json  vitest.config.ts  README.md
  app/
    app.vue                   shell: header (run, profile, commit), theme, router view
    pages/index.vue           the overview
    pages/blick/[...id].vue   the Blick page (ids contain slashes)
    components/               BlickCard, ControlBar, Chart, DataTable, ProblemList
    composables/useManifest.ts   fetches <buildUrl>/manifest.json once, typed
    composables/useTable.ts      fetches and decodes one Parquet file (hyparquet + compressors,
                                 BigInt → number, Date passthrough), cached per path
    lib/manifest.ts           hand-written TypeScript types for the manifest (spec 0.1)
    lib/controls.ts           controls from an entry: unbound dimensions → filter, requested
                              splits, defaults; state ↔ URL query
    lib/select.ts             apply control state to rows: filter, pass-through for split
    plots/index.ts            the plot type registry by name
    plots/{line,stacked_area,bar,stacked_bar}.ts   browser halves: render({ el, table, mapping, state })
    plots/vega.ts             shared spec pieces: facet by split, axes, palette, tooltip, theme
  tests/                      vitest: controls, select, spec builders, BigInt conversion
src/blicket/serve.py          the static server (stdlib http.server) with the viewer overlay
src/blicket/viewer.py         locate the bundled viewer, copy it into a build directory
meson.build                   option('viewer', type: 'feature', value: 'disabled') and the target
```

### The viewer reads a build directory

- `buildUrl` is a public runtime config value, `./` by default (the generated site sits next to
  `manifest.json` inside the build directory), `http://127.0.0.1:8765` during viewer development.
- `useManifest` fetches `manifest.json` once; `useTable(path)` fetches `blicks/<id>.parquet`
  through hyparquet with the zstd decompressor, converts BigInt to Number (values are years and
  counts, far below 2^53) and keeps Dates; rows are plain objects keyed by column name.
- Types are hand-written for spec 0.1, as the architecture decided; a comment points at
  `manifest.py` as the source of truth.

### Controls, derived at build time

The controls are the Python half of the plot type contract, so they are derived in the build,
not in the browser (a project plot type of M4 would otherwise be ignored). The rule, shared by the
built-ins through their base class: dimensions bound to a channel in the plot mapping have no
control; every other dimension is a `filter` whose default is the Blick's `defaults[dim]` when the
table has that value (a list means its first element), else the first value in display order;
`controls={dim: "split"}` makes it a `split`. The build records the result as
`BlickEntry.controls: list[Control]`, additive to the manifest; `Control(dimension, kind, default)`
is defined in `plots/_base.py` (model.py imports plots, so the other way round would cycle) and
re-exported. The entry's `controls` are the derived list; `definition.controls` stays the author's
requests, and the field docstrings say which is which. The `PlotType.controls(schema, mapping)`
method keeps the architecture's signature; `diff` stays unimplemented until M0.5.

The viewer only reads the list. The state lives in the route query: a filter is `dim=value`
(values parsed by the dimension's dtype), splits under `_split`, the axis toggle under `_y`
(underscore-prefixed, so a dimension named `split` or `y` cannot collide). Missing query entries
fall back to the defaults, so `#/blick/<id>` alone is valid; changing a control replaces the query
without a history entry. Un-splitting a dimension turns it into a filter at its default.

The M0.5 review's open point, which panel shares a scale, is decided here for the rendering:
panels share a y axis by default, independent axes are a toggle; a per-Blick default is deferred.

### Charts: the browser half of the built-ins

A plot type module exports `render({ el, table, schema, mapping, state, theme })` returning a
cleanup function (vega-embed's `finalize`, so a control change does not leak a view), and nothing
Vue-specific, as the architecture's contract sketches (`renderComparison` comes with the
comparison). `schema` carries the dimension dtypes and display order the spec needs, `theme` is
`light` or `dark` and a theme switch re-renders. The four built-ins build a Vega-Lite spec and hand
it to vega-embed (`actions: false`, tooltips on):

| plot type | encoding |
|---|---|
| line | x, y, color, strokeDash for `linetype` |
| stacked_area | x, y stacked, color |
| bar | x, y, color, `xOffset` by color for grouped bars |
| stacked_bar | x, y stacked, color |

Encoding types follow the dimension's dtype: an `integer` x on line and area charts is
quantitative with `format: "d"`, `nice` and `zero` off (so years read 1950, not 1,950, and the
axis starts at the data); on bar charts x is ordinal; `date` and `datetime` are temporal on a UTC
scale (hyparquet yields UTC midnight); strings are nominal with the display order from `columns`
as the domain. Measures are quantitative with an SI number format and the measure's name as axis
title (units are not in the manifest yet; the description shows them). Split dimensions become a
top-level `facet` around the `spec` (not an `encoding.facet`, so the comparison's ghost layer of
M0.7 can be added as a layer) with wrapped columns and a header per panel; `state.y` chooses
`resolve.scale.y` shared or independent. Colours, axis formatting, the theme for light and dark
mode and the tooltip follow the dataviz skill; colours consistent per dimension value across
Blicks are deferred. A plot type without a module (a project plot type, M4) shows a placeholder
naming it; dynamic import of `plot_types/<name>.js` from the build directory is M4, and bundling
the built-ins skips that plugin path for now, deliberately.

### The pages

- **Overview** (`#/`): header; a search box matching id, title, description and tags; groups as
  sections with their title; a row per Blick with title, first sentence of the description, plot
  type and dimensions; failed entries with their problems; the manifest's file-level problems and
  warnings at the end; a footer with the blicket version and the build id. Tag and group chips
  appear only when the build has tags; the example has none. No charts on the overview
  (thumbnails are a later nicety; the comparison ranking of M0.7 is what will order it).
- **Blick page** (`#/blick/<id>`): breadcrumb (group › title), description, the control bar
  (filters as selects, splits as chips, the axis toggle), the chart, a "data" tab with the rows
  currently shown (sortable, capped with a note beyond a few thousand rows), links to the raw
  Parquet file and to the definition's source (`file:line`). Error entries show their problems in
  place of the chart. Unknown ids get a "no such Blick in this build" page with a link back.
- Styling: Nuxt UI 4 (Tobias's choice) for layout, selects, badges, tabs and dark mode, with the
  icon set bundled (`@iconify-json/lucide`, the icon client bundle scanning the app, no fallback to
  the iconify API), so the site works offline, as a paper supplement must. Chart colours and the
  theme tokens follow the dataviz skill.

### `blicket serve` and the assets

- `blicket serve [<build dir>] [--port 8765] [--host 127.0.0.1] [--open]`: a stdlib
  `ThreadingHTTPServer` serving the directory; without an argument, the newest directory under
  the project's `.blicket/build/`. The installed viewer is looked up first and the directory's own
  files second, so an upgraded blicket shows its current viewer even for a directory that carries
  an older copy; `index.html` and `manifest.json` are sent with `Cache-Control: no-cache`. A port
  in use, a missing directory or a missing manifest is an `error:` line and exit 2; Ctrl-C exits 0.
- `blicket build` copies the viewer (`index.html`, `_nuxt/`, favicon, plus a `viewer-version`
  marker) into the build directory, so the directory is self-contained for copying or hosting, as
  Storybook's static build is. The files are not in the manifest and do not affect the id; when a
  build with the same id exists, the viewer copy is refreshed if its marker differs from the
  installed version (the manifest and the tables stay untouched). The store (M0.6) will copy
  manifest and tables only. Without a viewer in the installation, `build` says so once in the
  summary and `serve` serves the data with a hint.
- `src/blicket/viewer.py` finds the viewer in this order: the bundled files under
  `blicket/_viewer/` (via `importlib.resources`), then the directory named by `BLICKET_VIEWER`
  (a development installation points it at `viewer/.output/public`), else none. The viewer checks
  the manifest's `spec` and says when it cannot read a build.

### Packaging

- `meson_options.txt`: `option('viewer', type: 'feature', value: 'disabled')`;
  `find_program('pnpm', required: get_option('viewer'))`. When enabled, a `custom_target` with
  `build_always_stale: true` runs a small script that does `pnpm install --frozen-lockfile`,
  `NUXT_APP_BASE_URL=./ pnpm generate` and copies `.output/public` into `@OUTPUT@` (meson rejects path segments in an output
  name), installed to `py.get_install_dir() / 'blicket' / '_viewer'`. Disabled by default, so `uv
  sync` and the editable install need no Node; the release wheel is built with `uv build --wheel
  -Csetup-args=-Dviewer=enabled`, and the CI job does the same with `setup-node` and
  `pnpm/action-setup` (pnpm cache) and
  checks the wheel holds `blicket/_viewer/index.html`. A wheel built from the sdist without network
  has no viewer; the README says so.
- Reproducible output: a fixed `buildId` and `experimental.appManifest: false`, so two generates
  of the same source give the same files.
- The `.gitignore` gains `viewer/node_modules/`, `viewer/.nuxt/`, `viewer/.output/`; `viewer/` is
  source and stays in the sdist.
- Node 24 LTS or newer; pnpm (Tobias's choice) with a committed `pnpm-lock.yaml`; `typescript`
  pinned to `^6`;
  `nuxt typecheck` as the type check.

### Cleanup carried along, as its own commit

`digits` leaves the config, the manifest's `config` block, `check_tolerance`, the assembly's use
of it, the tests and the docs (the list from the M0.5 review); `tolerance` must be positive and
below 1 for the project and per Blick. Nothing rounds (M0.4 was dropped), so the key had no job.
It changes every build id and the manifest shape; `spec` stays `0.1`, since no build has been
stored anywhere yet, and the commit says so.

## Affected areas

- New: `viewer/**`, `src/blicket/serve.py`, `src/blicket/viewer.py`, `meson_options.txt`, the
  CI job for the viewer and the viewer-enabled wheel.
- Changed: `plots/_base.py` (`Control`, the shared `controls`), `model.py`
  (`BlickEntry.controls`), `builder.py` (controls recorded; the viewer copied), `cli.py` (`serve`,
  the `build` summary line about the viewer), `config.py`, `manifest.py`, `_validation.py`,
  `assembly.py` (digits), `meson.build`, `.gitignore`, README (serve, the viewer, developing it),
  `docs/architecture.md` (dated sentences: `digits` gone; `serve`; the M1 milestone line),
  `examples/remind-mfa/README.md` (serve; `BLICKET_VIEWER`) and `blicks/drivers.py` (the
  `Parameter` filter with a default).

## Testing

- Python: controls derived per entry (bound dimensions excluded, defaults applied including a
  list, a missing default falls back to the first value, splits requested) and present in the
  manifest; `serve` on a temporary build directory (a thread, a free port): `manifest.json` and a
  Parquet file with a slash in the Blick id come back, `index.html` from the installed viewer
  first and from the directory when there is no installed one, `no-cache` on the two files, a
  missing path is 404, a missing directory and a port in use are `error:` lines with exit 2, no
  argument picks the newest build; `build` copies the viewer when one is found (a monkeypatched
  directory, `BLICKET_VIEWER`), refreshes it on an existing id when the marker differs, and prints
  the hint when there is none. `digits` removal: the config rejects the key with the usual hint;
  the manifest has `tolerance` only.
- Viewer (vitest on `lib/` and `plots/`, no Nuxt test utilities): URL state round trip with the
  prefixed keys and dtype parsing; `select` filters rows and leaves split dimensions in; each plot
  type's spec has the planned encodings and encoding types per dtype, a top-level facet when a
  split is set, `resolve.scale.y` from the toggle, the display order as the domain; BigInt rows
  become numbers; `nuxt typecheck` passes.
- By hand, recorded in the plan: build the example run with the viewer, `serve`, open every
  Blick, check the controls, the URL state, the data tab and dark mode; load the generated site
  from a sub-path on a plain static server to confirm the relative base URL and hash routing.

## Out of scope

Change colouring, the comparison toggle and the diagnostics strip (M0.5–M0.7); the dev server
with reload and the Blick builder (M2); project plot types loaded from the build directory and the
Sankey (M4); thumbnails on the overview; a `file://` folder picker; end-to-end browser tests
(Playwright) until the UI settles; a switch to turn the viewer copy off (feature suggestion of
2026-10-24); a `unit=` option and consistent colours per dimension value across Blicks.

## Decided by Tobias on 2026-10-24

1. **Nuxt UI**, with the icon set bundled so the site works offline.
2. **The viewer copied into every build directory**, refreshed when the installed version differs,
   `serve` preferring the installed viewer. A way to turn the copying off (a config key or a
   `build` flag) is recorded as a possible later feature, not built now.
3. **Shared y axis across panels by default**, with a toggle for independent axes.
4. **pnpm** as the viewer's package manager.

## Decisions taken here, not asked

- Controls are derived at build time, as the Python half of the plot type contract, and recorded
  in the manifest; the viewer only reads them. This pulls the `controls` half of M0.5 forward;
  `diff` stays with M0.5.
- The viewer is an opt-in meson feature, off for development, on for the release wheel;
  `BLICKET_VIEWER` points a development installation at a generated viewer.
- `serve` is a stdlib static server; the dev server proxies to it; no CORS. Starlette and uvicorn
  wait for M2's SSE.
- Plot type modules are framework-agnostic `render({ el, table, schema, mapping, state, theme })`
  returning a cleanup; the built-ins are bundled with the viewer, the plugin path is M4.
- Tables are fetched whole; the overview is a grouped list with search.
- `digits` is removed in passing, as its own commit.
