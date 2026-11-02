# The overview as a sidebar and a preview pane

Status: built, 2026-10-29, on commit `57b9421`; the outcome is at the end. Revised 2026-10-28 after an
independent review that read the installed Nuxt UI 4.12.0 and Vega-Lite 6.5.0 sources and the
example build `c6317235ed070309`. Builds on
M2.1 (commit `57b9421`); the dev loop of [m2-2-dev-loop.md](m2-2-dev-loop.md) is not built yet
and nothing here depends on it. Takes the backlog item "The overview needs a revamp for REMIND's
scale" of [m0-tasks.md](m0-tasks.md) and, on the overview, "The plot type chips are not helpful".
Where this plan changes the architecture's "Viewer (Nuxt)" section, it says so; the architecture
gets the amendment when the task lands.

## Goal

The front page of a catalog stops being a list. The Blicks move into a sidebar that stays on
every page, grouped as the manifest groups them, searchable, with a badge on each Blick the
comparison flags, so that a catalog of ten or of three hundred Blicks reads the same way and a
Blick is one click away from any other. The space this frees on the overview shows a few Blicks as
small charts: the ones that changed since the baseline, biggest movers first, and the ones the
user pinned. A changed Blick's preview shows the panel where its largest change is, with the
baseline drawn behind it, so the overview answers "what did my change do" before a single click.
Nothing in a build directory changes: the manifest keeps spec 0.2, and the Python package is
untouched.

## The flows this plan enables

### 1. Open a build after a run

```
$ cd examples/remind-mfa
$ uv run blicket check ../../data_out/2026-10-24--01-25-34_plastics_SSP2_h12
…
vs baseline: 9 unchanged · 1 value
top movers: flows/production_by_source 2.1% of scale (Flow=Primary, Time=2100, Region=SSA)
$ uv run blicket serve
```

1. The page has two panes. On the left, the sidebar: the search box at the top; under it the
   three groups, "Drivers and scenario parameters", "Plastics flows", "In-use stocks", each
   open, each Blick a link by its title. "Production by source" carries the badge `Δ 2.1%`,
   whose title reads `largest change: 2.1% of the largest value in its panel`. At the bottom,
   `10 Blicks`. On the right, the main pane: the header as today, "blicket", the run, the
   profile and the Blick code commit, the colour mode button, and at its left a button that
   collapses the sidebar.
2. The main pane starts with the comparison, as today: the baseline selector, `9 unchanged · 1
   value`, the schema summary when there is one. Then the section **Changed since the baseline**:
   one card, "Production by source" with its badge, a small stacked area chart of the SSA panel
   with the baseline's stack faded behind the current one, and the caption `Region SSA · where
   the change is largest`. Then the section **Pinned**, which says `Nothing pinned yet. Pin
   Blicks on their pages to show them here.`
3. Clicking the title of the card opens `#/blick/flows/production_by_source?Region=SSA`: the
   Blick page as today, Region filtered to SSA, with the sidebar still on the left, "Production by
   source" marked as the current page and its group open, and the change strip's `largest change
   2.1% of the chart's scale at Region SSA, Flow Primary, Time 2100`. Clicking "Consumption by
   end use" in the sidebar switches to it without going back. The sidebar scrolls on its own
   when the list is long; the current Blick stays marked.
4. Typing `stock` in the search leaves two Blicks under "In-use stocks"; the other groups are
   gone until the search is cleared with its clear button. The toggle "Changed (1)" next to the
   search leaves the one flagged Blick.
5. The collapse button hides the sidebar, and the chart of a Blick page takes the width; the
   choice is kept in the browser, so a reload shows the same. On a page narrower than 1280 px
   the sidebar is a drawer that the button opens and that closes when a Blick is picked.

### 2. Pin what matters

1. On the Blick page of "GDP per capita" a button "Pin to overview" sits with the title. Clicking
   it pins the Blick: the button reads "Pinned" and the sidebar's item gets a pin icon.
2. Back on the overview, the **Pinned** section shows "GDP per capita" as a card with its pin icon
   and an unpin button, a small line chart of the twelve regions, and its first sentence as the
   caption. A pinned Blick that changed is a card in both sections. The hint is gone.
3. Pins live in the browser, per origin, as a list of Blick ids: a build of the same project
   served on the same port shows the same pins, a Blick that a build lacks is ignored and comes
   back when a later build has it, a renamed Blick keeps its pin through its aliases, and
   nothing is written into the project or the build. Two tabs of the viewer agree on them.

### 3. A build with many changes, or none

- Thirty Blicks changed: the Changed section shows the six biggest movers as cards and, under
  them, the other twenty-four as a ranked list, title, badge and link each, the way the overview
  lists its movers today; removed Blicks and Blicks in error are in that list, by name, without a
  chart.
- Nothing changed and nothing pinned, or a build never checked: there is no Changed section, and
  the Pinned section shows the first six Blicks as cards under the line `Nothing pinned yet; these
  are the first six Blicks. Pin Blicks on their pages to choose what shows here.` A build without
  Blicks shows the sentence it shows today (`No Blicks yet. Build one from the run, or write it as
  code.` in dev, `This build has no Blicks.` under `serve`).

## Facts the plan rests on (checked 2026-10-28)

- The overview (`viewer/app/pages/index.vue`) is one page: `ComparisonBar`, a search box whose
  text is the route query `q`, group and tag chips, a "Changed since the baseline" section of
  `ranked()` movers, the groups as sections of `BlickCard`s (title, id, first sentence of the
  description, flag badges, plot type and role chips, an inline `ProblemList` for an error
  entry), the empty states and the file-level problems. `BlickCard` and `roles()` in
  `lib/roles.ts` are used nowhere else; `searchText()` is the search's text, and
  `CHANNEL_LABELS` of the same module is used by `lib/builder.ts`.
- `app.vue` is the shell: a header (brand, run, profile, Blick code, colour mode), `main` with
  `max-w-7xl`, a footer with version, build id and time. Pages are the overview, `blick/[...id]`
  and `builder` (dev only, a form of 22 rem next to the chart at `lg`).
- `useComparison()` is module state: `chosen` baseline, `comparison`, `blicks` by name, and
  `loading`, which is `true` until the comparisons are fetched; `useManifest()` likewise.
  `ChangeStrip` computes the "Show where" state with `whereState(state, change.where, schema)`
  from `lib/comparison.ts`, which changes filters only and leaves splits alone, so for a Blick
  whose `where` names a split dimension it returns `null`. `stateFromQuery(controls, schema,
  query, defaultY)` gives a Blick's control state (a split control is a split when the query
  does not filter it; `dim=value` in the query turns it into a filter), `queryFromState(schema,
  state, defaultY)` the URL for a state, `select()` the rows of a state's filters. The Blick page
  passes `defaultY` from `definition.independent_y`. A comparison's `flags` come in the order of
  `Flag` (`new`, `removed`, `schema`, `value`, `error`); `ranked()` orders by `value`, `schema`,
  `new`, `removed`, `error`. `baselineTable(blick)` names the baseline's copied table when the
  columns did not change, and `useTable()` fetches a table by `{path, hash}`, cached by hash
  across pages (`fetchTable`; a build's tables are never evicted, only the builder's).
- `BlickChart.vue` renders through `PLOT_TYPES[type].plot.render(args)` with `PlotArgs` (`table`,
  `schema`, `mapping`, `unit`, `state: {splits, y}`, `baseline`, `theme`, `name`), redraws on a
  width change past 16 px and on its props, and queues renders. `plots/types.ts` says that a
  chart of the measure that differs in presentation only (legend, tooltips, size) gets an
  argument of its own, never a new `Quantity`. `frame()` in `plots/layout.ts` sets the heights
  (320 px single, 180 px per panel; 200 and 140 for a change chart) and the Vega-Lite `config`;
  `definePlot()` in `plots/embed.ts` fixes `actions` (the export menu) and tooltips. The hover
  rule and the legend-highlight params are referred to by name elsewhere in each spec (the hover
  dots of a line chart, `highlighted()` and `ghost()`, a bar's stroke), so a spec without them
  fails to compile; a legend-bound param is inert when the legend is disabled.
- Nuxt UI 4.12.0, installed, ships `USidebar`: an `aside` with `collapsible` (`offcanvas`,
  `icon`, `none`), `v-model:open`, a `breakpoint` (default `lg`) below which it renders as a
  slideover and sets its own model to `false` while the window is narrow, copying the drawer's
  opening and closing into it too; slots `header` (whose default content holds the close
  button), `title`, `actions`, default, `footer`; the width from `--sidebar-width`, which its
  root class declares at 16 rem, so an override goes on the root (`:ui="{ root: … }"`); a
  collapsed off-canvas sidebar is moved out of view but neither hidden nor `inert`; its
  container is fixed and full height with a spacer that reserves the width, so a flex row of
  sidebar and content is the right parent. `UNavigationMenu` in `orientation="vertical"`
  renders groups with `children` as an accordion, several open at once by default, with
  `v-model` over the open items' `value`s (the default values are indices, which shift when
  groups are filtered out; `defaultOpen` is read once at mount), items with `to`, `badge`
  (`string | number | BadgeProps`, spread over neutral defaults, `title` included),
  `trailingIcon` (not read by screen readers), `disabled` (rendered as no link), and the item of
  the current route marked active through `ULink`, which under the hash router compares the
  catch-all params and ignores the query.
- `localStorage` is per origin; `blicket serve` and `blicket dev` serve every build of a machine
  on `127.0.0.1:8765` unless told otherwise. It can throw in a private window or when storage is
  blocked. Tabs of one origin see each other's writes through the `storage` event.
- Example builds for the check by hand: `c6317235ed070309` (run 34) was checked against five
  baselines and flags `flows/production_by_source` (`value`, 2.1 %) against four of them;
  `2224d63eb5ef42e1` (run 13) is unchanged against `976f428f3d33dbdf`; builds under
  `.blicket/build/` without `compare/` show no comparison. Chrome is at
  `/usr/bin/google-chrome-stable`; the viewer was last generated on 2026-10-27 into
  `viewer/.output/public`, which `BLICKET_VIEWER` points `serve` at.

## Approach

### The shell: a sidebar on every page

`app.vue` becomes a row: `USidebar` on the left, and on the right a column of the header, `main`
and the footer as today. The sidebar is `collapsible="offcanvas"`, 18 rem wide, with `breakpoint`
`xl`: from 1280 px it stands next to the content, below it is a drawer (`menu` titled "Blicks")
that the header's toggle opens and that closes when the route changes. The header gains the
toggle at its left (`i-lucide-panel-left`, with `aria-label`, `aria-expanded` and
`aria-controls`) and takes the sidebar's header height, so the two borders line up; it keeps
"blicket", the run, the profile, the Blick code and the colour mode button, since a collapsed
sidebar must leave the brand and the build visible. A skip link to `main` comes first in the DOM,
and the sidebar is `inert` while collapsed, so its links leave the tab order. `main` keeps
`max-w-7xl`, so charts do not stretch across a wide screen once the sidebar is collapsed. The
footer stays.

The user's preference, open or collapsed, is kept in `localStorage` (`blicket:sidebar`) apart from
the ref bound to the component: the toggle writes it while the window is wide, and the narrow
drawer's opening and closing, which the component copies into its model, never does.

This amends the architecture's overview bullet: the groups, the badges, the search and the flag
filter live in the sidebar on every page, not on the overview alone. The Blick page's breadcrumb
reads "Overview" instead of "All Blicks", and the page gains the pin button below; the builder
page is untouched, and below 1280 px its form and chart have the width they have today, since the
sidebar is a drawer there.

### The sidebar (`components/BlickSidebar.vue`, `lib/sidebar.ts`, `composables/useSidebar.ts`)

- **Header:** the search box (`UInput`, `i-lucide-search`, a clear button) and a "Changed" toggle
  button (`UButton` with `aria-pressed`, shown when the comparison flags a Blick of the build,
  labelled with their count: `Changed (1)`; removed Blicks are not in the sidebar and not
  counted), in the `title` and `actions` slots, so the component's close button stays. The
  overview's tag and group chips go: the groups are sections, and `searchText` matches the tags.
- **Body:** a `UNavigationMenu` in vertical orientation, one top-level item per group (`value`
  the group's name, `label` its title or name), its `children` the Blicks of the group in
  manifest order, each with `label` the title (the name when there is none), `to` `/blick/<id>`,
  a short `badge` for the Blick's first flag in `ranked()`'s order (`Δ 2.1%` with the full
  sentence as its `title`; `schema`, `new`, `error`) in `FlagBadges`'s colours, an `error` badge
  for an entry in error without a comparison, and, when pinned, a pin icon with text for screen
  readers in the item's trailing slot. An error entry without an id is `disabled`; its problems
  are in the overview's problem section. A group whose Blicks are all filtered out is not shown.
- **Open groups:** `v-model` over the group names from `useSidebar`, all open at first. While a
  search or the filter is active, every group with a match is open; afterwards the user's set is
  restored. Navigating to a Blick opens its group and scrolls its item into view.
- **Search and filter:** module state in `useSidebar`, not the URL, since the sidebar outlives the
  page; the search matches as today (`searchText`, every word). The "Changed" toggle keeps the
  flagged Blicks. `No Blick matches` when nothing is left.
- **Footer:** `10 Blicks · 1 with errors · incomplete, a module failed to import` as the overview
  says it today, and in dev mode the "Build a Blick" button.
- `lib/sidebar.ts` holds the pure part in a model of its own, not Nuxt UI's: `sidebarGroups(
  manifest, changes, pinned, search, changedOnly)` returns the groups with their entries, each
  entry's badge (flag, label, title) and whether it is pinned or disabled; the component maps that
  onto navigation items. The badge colours move from `FlagBadges.vue` into `lib/comparison.ts`,
  next to `badges()`, so the sidebar and the badges share them.

### Pins (`lib/pins.ts`, `composables/usePins.ts`, `components/PinButton.vue`)

- `lib/pins.ts`: `readPins(storage)` and `writePins(storage, ids)` over a `Storage`-like argument,
  every access in a `try`, so a blocked storage reads as no pins and a write that throws is
  ignored; a stored value that is not a list of strings reads as no pins. `resolvePins(ids,
  entries)` maps each pinned id to the entry whose id or `aliases` hold it, so a renamed Blick
  keeps its pin. The key is `blicket:pins`.
- `usePins()` is module state: the ordered list of pinned ids, read from `localStorage` at first
  use and again before every write, so a second tab's pins are not overwritten, and refreshed on
  the `storage` event. `isPinned(id)` and `toggle(id)`.
- `PinButton` is one toggle button in two places: on the Blick page next to the title, `Pin to
  overview` / `Pinned` (`i-lucide-pin`, `aria-pressed`), and on a preview card as an icon button,
  `Unpin`.

### The previews (`lib/preview.ts`, `components/BlickPreview.vue`, the overview)

- **The sections.** `previewSections(entries, comparison, pins, limit)` in `lib/preview.ts`
  returns the two sections. *Changed since the baseline*, when the comparison flags anything: the
  flagged Blicks in `ranked()` order, the first `limit` (six) of those with a table as cards, the
  rest as a list (title, badge, link; removed and error Blicks by name). *Pinned*: the pinned
  entries in sidebar order as cards, a pinned Blick in error as a card with its badge and first
  problem and no chart; or, when nothing is pinned, the hint alone when the Changed section has
  cards, and the first `limit` Blicks with a table as cards under the hint otherwise. A Blick
  that is both changed and pinned is a card in both sections. Nothing is drawn while
  `useComparison().loading` is true, so the fill never shows and then jumps to the changed set.
- **A card:** the title as the link, the badge of its first flag and the pin icon or the unpin
  button on the title row; a compact chart of the Blick at its **preview state**; a caption.
  `previewState(entry, change, defaultY)` is `stateFromQuery(controls, schema, {}, defaultY)` with
  every split turned into a filter at its control's default, so the preview is one panel, and
  then `whereState` applied when the comparison names `where`, so it shows the panel where the
  change is largest. The caption names the filter values shown (`Region SSA`), with `· where the
  change is largest` when `where` set them, and the first sentence of the description when there
  are no filters. The card's link is the preview state as a query (`queryFromState(schema,
  state, defaultY)`) when `where` set it, so what the card shows is what opens; otherwise
  `/blick/<id>` alone, the Blick as its author laid it out. The card fetches its rows and the
  baseline's (`baselineTable()`) with `useTable` when it first scrolls into view
  (`IntersectionObserver`), so a long pinned list costs what is seen, waits for both as the Blick
  page does, and draws the baseline behind the chart when there is one. While the rows load the
  card shows its title and a placeholder of the chart's height; a table that cannot be read shows
  the error in the card; a selection without rows says so; a plot type without a browser half
  says `no chart for the plot type <type>`.
- **Compact charts:** `PlotArgs` gains `compact?: boolean`, the presentation argument that
  `plots/types.ts` reserves for this, read in two places only: `frame()` draws 160 px high with
  the legend off (`config.legend.disable`), and `definePlot()` embeds with `actions: false`. The
  hover rule, the tooltips and the legend-highlight params stay, since other layers refer to them
  and the tooltip is what tells thirteen polymers apart without a legend; the axes keep their
  titles and the unit; the baseline's ghost is drawn as on the Blick page. `BlickChart` passes the
  prop through. `compact` and `kind` are never set together.
- **The overview page** (`pages/index.vue`) becomes: `ComparisonBar`; the two sections, their cards
  in a grid of two columns when the pane is wide enough, by a container query on the pane, not
  on the viewport, since the sidebar changes the pane's width; the empty states; the problems
  section as today. Search and filter have left the page, and so has the `q` route query, which
  nothing else wrote.
- **Order of work:** the shell and the sidebar first, then the pins and the previews; one
  implementer, one loop.

### What goes

`BlickCard.vue`, `roles()` and its test (the plot type and role chips of the overview, the
backlog item; the Blick page keeps its text line with the plot type and the unit; `roles.ts` keeps
`searchText` and `CHANNEL_LABELS`), the overview's chips and its `q` query.

### Docs

`README.md` "Looking at a build": the overview as sidebar and previews, pins in the browser and
shared by every catalog served from one origin, a static host included; `viewer/README.md`: the
shell, the sidebar's and the pins' storage keys, the compact argument; `docs/architecture.md`
"Viewer (Nuxt)": a dated amendment of the overview bullet; `docs/plans/m0-tasks.md`: the two
backlog items marked done here, with the pin decision; `docs/plans/m2-2-dev-loop.md` flow 1 step
2, which has the overview list a changed Blick under "Changed since the baseline": as a card now.

## Affected areas

- New: `viewer/app/components/{BlickSidebar,BlickPreview,PinButton}.vue`,
  `viewer/app/composables/{useSidebar,usePins}.ts`, `viewer/app/lib/{sidebar,pins,preview}.ts`,
  `viewer/tests/{sidebar,pins,preview}.test.ts`.
- Changed: `viewer/app/app.vue`, `pages/index.vue`, `pages/blick/[...id].vue` (the pin button, the
  breadcrumb), `components/{BlickChart,FlagBadges}.vue`, `plots/{types,layout,embed}.ts`
  (`compact`), `lib/comparison.ts` (the badge colours), `lib/roles.ts`, `tests/plots.test.ts`,
  `tests/roles.test.ts`, the READMEs, `docs/architecture.md`, `docs/plans/m0-tasks.md`,
  `docs/plans/m2-2-dev-loop.md`.
- Removed: `components/BlickCard.vue`.
- Untouched: the Python package, the manifest and comparison formats, the controls, the Blick
  page's behaviour, the builder.

## Testing

- **vitest** (`app/lib`, `app/plots`, no Nuxt): `sidebarGroups` keeps the groups in manifest
  order with stable values when some are filtered out, labels by title with the name as fallback,
  the badge from the flags in ranked order (`[schema, value]` gives the Δ badge), an `error` badge
  for an entry in error without a comparison, the pinned mark, a disabled entry without id, the
  search over `searchText` by every word, the changed filter, groups without a match left out and
  the open set while a search is active; `readPins`/`writePins` over a fake storage: the round
  trip, a value that is not a list of strings, a storage that throws on read and on write;
  `resolvePins` through an alias; `previewSections`: the changed cards in ranked order capped at
  the limit with the rest listed, removed and error Blicks in the list and never a chart, a
  pinned Blick in both sections, the hint without fill when something changed, the fill when
  nothing changed and nothing is pinned, nothing while loading; `previewState` for a split
  dimension named by `where`, a bound dimension in `where`, a `where` value the build lacks, a
  Blick without controls, `independent_y`; the caption and the link with and without `where`;
  the compact spec of each built-in, compiled and run through the `run()` helper of
  `tests/plots.test.ts` without warnings: 160 px high, `config.legend.disable`, the baseline's
  layers and the hover rule still there; `nuxt typecheck` and `pnpm lint` pass.
- **By hand**, headless Chrome on the example builds, recorded in this plan: build
  `c6317235ed070309` (one flagged Blick) and `2224d63eb5ef42e1` (unchanged) under `blicket
  serve`, a build without `compare/`; at 1440, 1280, 1024 and 390 px, light and dark: the
  sidebar's groups, badges and current item, its group opened and the item scrolled into view
  on navigation; search and the changed filter; collapse and its persistence over a reload, and
  a narrow window that does not overwrite it; the drawer below 1280 px closing on a pick; Tab
  skipping a collapsed sidebar; the preview grid's charts with the baseline ghost on the flagged
  Blick and the SSA caption; the card's link opening the page at `Region=SSA`; pin on a Blick
  page, the icon in the sidebar, the card on the overview, unpin from the card, pins surviving a
  reload and a pin made in a second tab; the fill and its hint; no horizontal scroll at 390 px;
  the console without errors; `pnpm generate` and the generated site under `BLICKET_VIEWER`.

## Out of scope

A project-side `featured=` option for Blicks (pins are the user's; a project default waits for a
project that needs it, and would change the manifest spec); reordering pins; thumbnails rendered
at build time; the dev loop (M2.2), whose indicator joins the header then; the header's "Blick
code" label and the "World" panel from the backlog; a command palette over the Blicks; keyboard
shortcuts for the sidebar; virtualising the list for thousands of Blicks (a `UNavigationMenu` of a
few hundred items is fine); end-to-end browser tests.

## Decisions

Tobias accepted all seven as proposed on 2026-10-28.

1. **The sidebar on every page**, Storybook-like, collapsible, a drawer below 1280 px, rather than
   on the overview alone. A Blick page's chart loses 18 rem of width while the sidebar is open;
   the toggle gives it back.
2. **Pins live in the browser**, as the backlog item says, shared by every catalog served from
   one origin; no project-side option now.
3. **Two sections on the overview**: the changed Blicks, six as cards and the rest as a ranked
   list; the pinned ones as cards, or the first six Blicks with a hint when nothing is pinned and
   nothing changed. A Blick that is both is a card twice.
4. **A changed Blick's preview shows the panel of its largest change**, with the baseline faded
   behind, and its link opens the page at that panel; an unchanged or pinned Blick's preview
   shows its first panel and links to the page as its author laid it out.
5. **Compact charts keep their tooltips and axes and lose the legend and the export menu.**
6. **The overview drops the plot type and role chips** (the backlog item); the Blick page keeps its
   text line.
7. **The search leaves the URL**: it is sidebar state that outlives the page.

## Outcome (2026-10-29)

Built in one implementation pass and three review rounds (architecture, plan fidelity, UX with the
app running, code quality; the general reviewer was unavailable). Where the code departs from the
plan above, the plan was wrong or the review found something better; the list is complete.

### Deviations

- **Compact legends.** `config.legend.disable` alone leaves the legends in place: an encoding's own
  `legend` object overrides the config (Vega-Lite `compile/legend/parse.ts`), and the colour and
  line type encodings always carry one. `frame()` therefore also sets `legend.disable` on every
  encoding, in layers too, through `withoutLegends()` in `plots/layout.ts`. `compact` is still read
  only in `frame()` and `definePlot()`; the heights sit in a `HEIGHTS` table.
- **Pins do not re-read storage before a write.** The re-read made unpinning impossible when
  storage is blocked (`readPins` returns `[]`, so the toggle re-added the pin). `togglePin(ids,
  id, entries)` is a pure function in `lib/pins.ts` that removes every id the Blick holds,
  aliases included; `usePins().toggle` works from its own ids and writes. Two tabs agree through
  the `storage` event alone. Storage access goes through `lib/storage.ts` (`read`, `write` over a
  `KeyValueStorage`), shared with the sidebar preference.
- **The preview model.** `previewSections(entries, compared, changes, pinned, limit)` takes the
  comparison's Blicks map and the resolved pins, as `sidebarGroups` does, and has no `loading`
  parameter: the page draws nothing while `useComparison().loading`, and the "nothing while
  loading" test went with it. `Preview` is `{ state, largest }`; `largest` is true whenever the
  state agrees with the change's `where`, so a change in the panel shown first also links with
  the explicit query.
- **Sidebar state lives in `BlickSidebar`.** The component wraps the `USidebar` and is mounted
  once under `v-if="manifest"`, so search, the changed filter and the open groups are local refs
  that outlive the pages all the same; `useSidebar` keeps `open`, `toggle` and `closeDrawer`. The
  open set has no vitest case (component logic).
- **Problems on the overview.** A Blick's problems are in its manifest entry, not in
  `manifest.problems`, so the removed list card was the only place that showed them. The overview
  has a Problems section (incomplete-build note, every error Blick by name with its `ProblemList`,
  linked when it has an id, then the file and project problems), independent of the comparison,
  and a one-line alert under the comparison bar when a Blick failed, the build is incomplete or a
  manifest problem is an error; "See problems" scrolls to the section. Warnings alone raise no
  alert.
- **"A first look".** When nothing is pinned and nothing changed, the fill section carries that
  title instead of "Pinned", and its cards have a pin button; pinning from one turns the section
  into "Pinned".
- **Captions.** `whereText` and the card captions write `name: value` (the change strip changed
  with them). A card that shows a panel the comparison did not choose says "first of N panels"
  (or "one of N panels" when the control's default is not the first value). A changed card reads
  like "Region: SSA · largest change at Flow: Primary, Time: 2100 · baseline faded"; the
  percentage stays in the badge on the title row, since the caption wrapped with it.
- **Ranked list.** Under the cards a line says "N more changed"; each row has its badge beside the
  title and, for an error Blick, its first problem.
- **Sidebar details.** The empty state says which filter excludes everything ("No changed Blick
  matches 'stock'.") with a "Show all" button; the footer reads "2 of 10 Blicks" while filtering;
  the changed filter switches itself off when the count drops to 0; the drawer focuses the current
  item or its close button on opening, not the search box; the badge and pin mark have spoken
  text (", changed by 2.1% of scale", ", pinned"); the "Changed (n)" button's room is reserved
  while the comparisons load. The drawer is the slideover's 28 rem, not 18 rem. The loading
  placeholders are hidden from assistive technology and each section has one `role="status"`
  line reading "Loading charts" while a card waits, since `USkeleton` announces itself as an
  alert.
- **Shell details.** The toggle's accessible name is the constant "Blick list" with the state in
  `aria-expanded` and a varying tooltip; the skip link focuses `main` from a click handler,
  because `#main` is a route under the hash router; the builder's breadcrumb and the "No such
  Blick" button read "Overview" too (the plan left the builder untouched); the empty dev
  overview offers "Build a Blick" as well as the sidebar footer.
- **Shared code the plan did not name.** `useBlickChart(entry, state, change, { load, compare })`
  holds the table pipeline of the Blick page and the card, with `chartPropsOf()` shared by the
  builder too; `useBlickId()`; `yAxisOf(definition)` in `lib/controls.ts`; `FlagBadge.vue` and
  `PinMark.vue`; `blickBadge(entry, compared)` in `lib/comparison.ts` next to `badges()`, sharing
  a private `badge()`; `firstProblem`, `pinnedHint`, `troubles` in `lib/preview.ts`, `noMatch`
  in `lib/sidebar.ts`; the storage stand-ins in `tests/fake-storage.ts`.
- **Docs.** The docstring of `blicket dev` in `src/blicket/cli.py` says "in the viewer" instead of
  "on the overview"; nothing else in the Python package changed.

### Verification

- `pnpm vitest run`: 14 files, 184 tests. `pnpm nuxt typecheck` and `pnpm lint` clean.
  `pnpm generate` builds the site.
- By hand in headless Chrome, by the implementer and the UX reviewer with their own scripts over
  the DevTools protocol, at 1440, 1280, 1024 and 390 px in light and dark: the example builds
  `c6317235ed070309` (one flagged Blick), `2224d63eb5ef42e1` (unchanged), `10f18017e822473b`
  (never checked, no `compare/`) under `blicket serve`, two synthetic copies with error Blicks
  with and without an id, an incomplete build and a file problem, with and without `compare/`,
  and the builder under `blicket dev`. Checked: no horizontal scroll, every visible chart drawn,
  the console clean apart from the known `compare/index.json` 404 on a never-checked build; the
  header and sidebar header borders meeting at 64 px; the SSA card with its faded baseline, its
  caption and its link opening the page at `Region=SSA` with the sidebar item marked and its
  group open; search, the changed filter, the empty-search message and "Show all"; collapse
  stored as `blicket:sidebar=closed` and surviving a reload and a narrow window; the sidebar
  `inert` when collapsed and Tab skipping it; the drawer at 1024 and 390 px opening on the
  current item, closing on a pick, on Esc and on its button, returning focus to the toggle;
  pins from the Blick page, from "A first look" and their removal from a card, with focus kept
  on the card that took the place or on the heading, surviving a reload and arriving from a
  second tab; a Blick both changed and pinned as a card in both sections; the Problems section
  and the alert on the error builds, "See problems" landing on the heading; the builder with the
  sidebar open, collapsed and at 1024 px. Measured contrast: sidebar focus rings 6.6:1, badges
  5.7:1 light and 9.0:1 dark, captions 4.7:1 and 6.7:1.
