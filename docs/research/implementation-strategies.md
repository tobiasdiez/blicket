# Implementation strategies for `blicket`

Status: research note, written 2026-10-22. Input: [`docs/concept.md`](../concept.md), the only spec.
Library versions were checked against the npm, PyPI and CRAN registries on the same day;
APIs were checked with Context7 and the projects' docs. Two small experiments (snapshot
file formats, generic change magnitude) were run with polars 2.0.0; results are below.

## Summary

- **Recommendation: a Python core built protocol-first ("A+C").** A Python package provides
  the CLI, the build pipeline, diffing, the snapshot store and the dev server. The viewer is a
  prebuilt TypeScript web app that ships inside the wheel. Everything between the two goes
  through a small, versioned on-disk protocol: an immutable build made of a JSON manifest and
  one Parquet table per Blick, pushed to a store. An R SDK can later write the same files and
  reuse the core, and the viewer can be used on its own.
- **The plot type contract runs on two sides.** `controls` and the change magnitude part of
  `diff` belong at build time, because CI and the terminal summary need them without a browser.
  `render` and the comparison rendering belong in the browser. The design should say so
  openly instead of hiding it. Every plot type, built in or project defined, implements the
  full contract and declares its channels; the built-ins render through Vega-Lite templates,
  and a declarative template tier could become a helper layer later.
- **The generic change magnitude is computed per panel.** The largest absolute deviation is
  divided by the largest absolute value in the same view (one combination of control values),
  then combined with the share of rows that were added or removed. The result is bounded to
  [0, 1], works across units and stays stable when values cross zero (for example net-negative
  CO2).
- **Snapshots do not belong in git.** The storage experiment shows why: any compressed
  columnar file defeats git's delta compression, and even uncompressed, rounded Parquet adds
  tens of kilobytes per Blick and accept to the history. Builds therefore go to a store as
  immutable units, Parquet with zstd, and storage is treated as no constraint.
- **CI has two modes.** In guard mode, run data is available: the build is compared with its
  resolved baseline from the store and pushed. In review mode, no run is needed: the build
  already pushed for the PR's head commit, for example by a cluster post-run hook, is compared
  and reported. The second mode matters because IAM runs take hours and often need solver
  licences, so they cannot run in PR CI.

## 1. What the concept forces

These constraints in `concept.md` shape any implementation:

1. **Transformations run at build time in the host language.** In practice that means a
   Python process, later also R, must be part of the build and of the dev loop.
2. **The output is a static site, with a dev server on top.** So the viewer must work with
   no server, and only the dev server may write anything.
3. **Snapshots live in a store, not in git.** Builds are immutable and identified by content
   hashes, so determinism of the table serialisation matters from day one; repository growth
   does not.
4. **The plot type contract includes `diff`, and change magnitude is used for ranking.**
   The magnitude must be computable without a browser, for the terminal summary and for CI.
   The comparison rendering, however, is a browser concern.
5. **Controls need named dimensions on the Blick output.** This settles the deferred data
   model at the Blick-output level: every Blick output is a labelled long table with
   dimension columns and one or more measure columns. Raw run data can stay opaque behind a
   project-defined loader.
6. **Python first, R desirable.** Whatever language the core uses, the boundary to the host
   language must be narrow and file-based.

The key observation is that the contract splits cleanly into two halves:

| Operation | Needs | Runs best |
|---|---|---|
| `controls(schema, mapping)` | schema and mapping only | build time; result goes into the manifest |
| `diff` → magnitude | both tables, numerics | build time, headless (CI, terminal) |
| `render(table, state)` | DOM, interactivity | browser |
| `diff` → comparison rendering | DOM, both tables | browser |

Every strategy below is mostly a different answer to the question of which language
implements which half.

## 2. Storybook's architecture mapped onto `blicket`

Storybook 10 (current 10.6.3) is ESM-only. Its main concepts and their counterparts:

| Storybook | What it is | `blicket` counterpart | Borrow? |
|---|---|---|---|
| Story, CSF file | ES module: a default export (meta) plus named exports (stories). Statically analysable, so it can be indexed without rendering. CSF Factories are in preview in SB 10. | Blick module: a Python module with decorated transformation functions, plus module-level defaults (group, tags). | **Yes.** One file holds many Blicks, meta sits at module level, and the id comes from a title plus the export name, with an explicit override. |
| Indexer → `index.json` | Builds the list of stories and their metadata (`title`, `name`, `tags`, `importPath`, optional `__id` override). Custom indexers allow non-CSF inputs. | `manifest.json`: the Blick index plus build results. | **Yes.** It is the core of the protocol. |
| args, argTypes, Controls addon | Controls inferred from component props; state is kept in the URL. | Controls inferred from unbound dimensions; state is kept in the URL. | **Yes**, including URL state so that a link opens a Blick at a specific control state. |
| Manager / preview split | The manager (sidebar, toolbar, addon panels) is prebundled. Stories render in an `iframe.html` preview built with the project's builder. The two talk over a postMessage channel. | Viewer shell (prebuilt) and plot type renderers. | **Partly.** Ship the shell prebuilt, as Storybook does with its manager. Skip the two-iframe split and its channel at first: plugins render into a DOM node with an error boundary. Keep an embed route (`embed.html#/blick/<id>`), the equivalent of `iframe.html`, for papers and docs. |
| Addons (panels, toolbars, decorators) | A general extension API for the UI. | Plot types are the only extension point. | **Not in v0.** A general addon API brings a large support burden. Panels such as a data table or source view can be built-in. |
| Loaders | Async data that a story needs before rendering. | Run loader and shared, memoised inputs. | **Yes**, as the answer to "how transformations access raw run data". |
| Tags | Filter stories in the sidebar and in test runs. | Group Blicks, and later set the CI policy per tag (for example `headline` fails, others warn). | **Yes.** |
| Composition (refs) | Embed other Storybooks in one UI. | Several models or runs in one repository. | **Later.** It answers the open question about several models per repository. |
| `storybook dev` / `storybook build` | Dev server with HMR; static build. | `blicket dev` / `blicket build`. | **Yes.** |
| Chromatic baselines | Baselines are kept per branch, follow git history and are updated only on accept. Accepts made in the Visual Tests addon carry over to CI. *UI Tests* compares with the ancestor build; *UI Review* compares with the merge base. TurboSnap skips stories whose dependencies did not change. | Builds in a store; baselines resolved along git ancestry and by run profile. Guard mode corresponds to UI Tests, review mode to UI Review. Input fingerprints play the role of TurboSnap. | **Borrow the flow and the baseline model, not the hosting.** A directory store replaces the SaaS baseline store. How accepting works is still open; Chromatic's UI-and-PR-first flow is the stated direction. |
| Pixel diffs | Screenshot comparison with a threshold. | Data diff with a magnitude. | **No.** Data diffs are deterministic and rankable. Rendering changes such as a library upgrade are deliberately invisible to the guard. |

Two more precedents from snapshot testing are worth copying:

- **Insta (Rust) keeps pending candidates apart from accepted baselines.** Failing tests
  write `.snap.new` files, and `cargo insta review` accepts or rejects each one. The
  counterpart in blicket: a build is a candidate until something marks it accepted, and the
  build itself never changes. Insta's separation of pending and accepted is input for the
  open accept design.
- **pytest-regressions has `dataframe_regression` with tolerances.** It is a reference for
  how per-column tolerances can be expressed.

## 3. Strategies

### A. Python-centric

**Architecture.** The Python package `blicket` contains:

- a CLI (typer),
- a registry and discovery of Blick modules,
- a build pipeline with a run loader,
- diffing in polars,
- the snapshot store: pushing builds and resolving baselines,
- a Starlette dev server,
- the prebuilt viewer in `blicket/_viewer/`.

Node is needed only to build the viewer, by the tool's maintainers in their release CI.
JupyterLab extensions, marimo and Gradio ship their frontends the same way, through a
build-backend hook; blicket uses meson-python for this.

**Registration and discovery.** Blicks use decorators. Discovery imports the modules listed
in `[tool.blicket] blicks = ["blicks/**/*.py"]`, the way pytest collects tests. An
AST-based index (CSF-like, without executing anything) is possible later, for a sidebar that
appears before anything is built. v0 does not need it if loaders are lazy.

**Plot types.** The Python half (control rules, magnitude) runs at build time. The browser
half is either a Vega-Lite template or an ESM module, loaded with a dynamic `import()`. The
details follow in §4.3.

**Hot reload.** watchfiles drives the rebuild inside the dev process (§4.9). The viewer is not
rebuilt; it refetches data after server-sent events.

**Where the diff runs.** The magnitude is computed in Python (polars) at build time. The
comparison rendering happens in the browser, from the current table and the baseline table.

**R path.** This needs the protocol from strategy C. Without it, R users would have to
reimplement the internals.

| Strengths | Weaknesses |
|---|---|
| One runtime for users: `uv tool install` or `pip install` and nothing else. No Node on HPC clusters. | Project plot types that want npm dependencies need their own bundling step (esbuild or Vite) to produce one ESM file. |
| The dev loop needs a Python process anyway, so no cross-language orchestration is needed for v0. | Python-specific internals unless a protocol is enforced. Lock-in risk for R. |
| The diff runs in the same dataframe engine that users already know. | Two codebases (Python, TS), although the TS one is a self-contained app. |
| Lowest effort to reach jobs 1 and 2. | |

### B. TypeScript-centric, modelled on Storybook

**Architecture.** A Node CLI distributed on npm, with a Vite 8 dev server and a Vite build
for the static site. A project config such as `.blicket/main.ts` mirrors Storybook's
`main.ts`. A Vite plugin serves Blick data, watches Python files and talks to a language
runner (a Python or R process) over JSON-RPC on stdio. It pushes updates with
`server.ws.send({type: 'custom', event: 'blicket:blick-updated', ...})`, received through
`import.meta.hot.on(...)` in the client; this API was verified for Vite 8. The SDKs for
Python and R run transformations and write Parquet or Arrow IPC.

**Registration and discovery.** There are two options, and both are uncomfortable.

1. Python decorators produce a manifest that the Node core reads through a custom indexer.
2. CSF-like TS Blick files declare the plot and the mapping and reference a transformation
   by name, for example `transform: py("figs.emissions:co2")`.

Option 2 splits one Blick across two languages, which is bad for Python users. Option 1 makes
the Node side a manifest consumer, which is essentially strategy C with a Node core.

**Plot types.** This is B's real advantage. The whole contract is written in TypeScript with
npm dependencies and native Vite HMR. The magnitude runs in Node at build time, with Arquero
or Flechette, so one implementation serves the browser and CI.

**R path.** Symmetric: the R SDK is just another runner.

**Precedents.** Observable Framework (Node core with polyglot data loaders; 1.13.4, last
release March 2026), Evidence, and Quarto (Deno core with Jupyter and knitr engines,
distributed on PyPI as `quarto-cli`). Node could be supplied to Python users through
`nodejs-wheel` (24.19 on PyPI).

| Strengths | Weaknesses |
|---|---|
| Best plugin experience. The contract lives in one language. Closest to Storybook, so concepts transfer directly. | Two runtimes for every user, in CI, and on clusters. More moving parts and harder debugging for scientists. |
| Language SDKs are symmetric from day one. | Cross-process runner orchestration is needed from day one, even for Python-only v0. |
| Vite gives HMR for free for the UI and plugins. | Blick code, the main thing being edited in job 1, is Python anyway. Vite HMR does not help there. |
| | The core contributor pool is TypeScript, but the users write Python and R. |

### C. Protocol-first, language-agnostic

**Architecture.** A specification comes first. It covers:

- a manifest JSON Schema,
- conventions for Blick tables in Parquet (dimension and measure columns, units and labels
  in Parquet key-value metadata),
- plot-type definitions (declarative JSON plus an optional ESM module),
- the store layout: immutable builds, and how a baseline is resolved from them.

The viewer is a static web app that reads only these files, and the SDKs are thin.

**The open question is where diff, check and serve live.** There are three options:

1. In every SDK. This duplicates the semantics and invites inconsistent magnitudes.
2. In the viewer (JS). CI would then need Node or a headless browser.
3. In one reference core. That brings us back to A (Python), B (Node) or D (native binary).

**Assessment.** C is a design principle rather than a complete strategy, and it is the right
principle. A spec designed before any working tool tends to be designed in a vacuum, so the
spec should come out of a reference implementation and be versioned from the first release.

| Strengths | Weaknesses |
|---|---|
| No lock-in. The viewer can be reused and R support is natural. Third parties (Julia, GAMS post-processing, shell scripts) can produce catalogs. | Not runnable by itself. Something must implement the dev loop, diff and the store. |
| Forces clarity on the data model at the Blick-output level, exactly where the concept says it is unavoidable. | Designing the spec up front is slow, and a premature freeze is a risk. |

### D. (Additional) Native core binary with thin SDKs

**Architecture.** A Rust binary implements the protocol: diff with polars-rs or arrow-rs, an
axum dev server, file watching with notify, and the viewer embedded with rust-embed. It is
distributed like ruff and uv: on PyPI through maturin `bindings = "bin"`, on npm, and as
standalone binaries. The Python and R SDKs only register Blicks and run transformations
through a stdio runner protocol.

| Strengths | Weaknesses |
|---|---|
| Identical semantics in every language. R users need no Python. One file to install in CI. | Highest effort. Rust skills are rare among the target contributors. Diff semantics are slower to iterate on while they are still being discovered. |
| Fast. | Custom magnitude hooks must call back into the host SDK or embed a JS engine. |

**Verdict.** This is a credible end state if R adoption turns out to be large and the Python
dependency becomes the main obstacle. The protocol-first design keeps it possible without
committing now.

### Considered and rejected

- **Building on Observable Framework, Evidence or Quarto.** All three give a static site and
  build-time data loaders, but none has a catalog with inferred controls, snapshots or a
  review flow. These would have to be bent around page-oriented generators. Observable
  Framework's release cadence has also slowed (1.13.4, March 2026).
- **Server-rendered apps (Panel, Streamlit, Shiny).** They contradict the static-site
  requirement and job 3.
- **Host-rendered images only (matplotlib, plotnine).** Controls would require pre-rendering
  every combination of control values. Host-side rendering is still useful for *thumbnails
  and CI report images* (see vl-convert in §4.4).

## 4. Cross-cutting design

This section describes the recommended A+C design. Most of it holds for the other
strategies as well.

### 4.1 Blick registration and identity

```python
# blicks/emissions.py
import polars as pl
import blicket as bk

bk.group("Emissions", tags=["emissions"])        # module-level meta, like CSF's default export

@bk.blick(
    id="emissions/co2-by-sector",                # stable id; default: "<group>/<function name>"
    title="CO2 emissions by sector",
    plot=bk.plots.stacked_area(x="year", y="value", color="variable"),
    controls={"region": "split"},                # optional; the plot type's rules give defaults
    defaults={"scenario": "SSP2-NPi"},
    aliases=["emissions/co2_sectors"],           # earlier ids, so renames keep their baseline
)
def co2_by_sector(run: bk.Run) -> pl.DataFrame:
    return (run.iamc()                           # project loader, memoised per run
              .filter(pl.col("variable").str.starts_with("Emissions|CO2|"))
              .select("scenario", "region", "variable", "year", "value"))

# Parametrised families (compareScenarios-style), with explicit ids:
for var in ["Final Energy|Electricity", "Final Energy|Hydrogen"]:
    bk.register(id=f"final-energy/{bk.slug(var)}", title=var,
                plot=bk.plots.line(x="year", y="value", color="scenario"),
                transform=lambda run, v=var: run.iamc().filter(pl.col("variable") == v))
```

- **Inputs from any dataframe library.** The transformation result may be anything that
  implements the Arrow PyCapsule interface (`__arrow_c_stream__`: pandas, polars, pyarrow,
  duckdb relations). Built-in adapters cover pyam `IamDataFrame` (`.data`), xarray
  (`.to_dataframe().reset_index()`) and flodym arrays (`.to_df()`). Internally everything
  becomes a polars DataFrame. narwhals is an alternative if the transformation API ever needs
  to work on native frames.
- **Dimensions and measures.** Dimension columns are those that are not floating point by
  default, and an explicit `dims=` or `measures=` overrides that. Units, as in IAMC's `unit`
  column, are kept as a dimension so that they appear in the data. The manifest also records
  them for axis titles.
- **Identity.** The id is explicit or derived from the group and the function name, never
  from the file path, so moving a module does not orphan its Blicks. On rename, `aliases`
  maps the old id. Rename detection by content hash was considered and is not planned. This
  addresses the open question about Blick identity across refactors.

### 4.2 The on-disk protocol

```
my-model/
  pyproject.toml                    # [tool.blicket]: Blick globs, loader, store path, tolerance
  blicks/…                          # Blick code
  blicks/plot_types/sankey.js       # project plot type (ESM)
  .blicket/                         # gitignored
    build/<build-id>/manifest.json, blicks/**.parquet, baseline/**.parquet, viewer assets
    store/builds/<build-id>/…       # default store; teams point the store at a shared path
```

Nothing but Blick code, plot types and config lives in git. A build is immutable; its id is a
content hash over the Blick definitions, the per-Blick table hashes, the run fingerprint and
the commit. The store keeps every pushed build, and any two builds can be diffed.

An excerpt of the manifest, versioned with `spec` and described by a JSON Schema generated
from pydantic models. TypeScript types for the viewer can be generated from the same schema:

```json
{
  "spec": "0.1",
  "run": {"id": "remind-2026-10-22-a", "profile": "baseline", "path": "output/SSP2", "fingerprint": "…",
          "commit": "a1b2c3", "branch": "feature/steel", "dirty": false},
  "baseline": {"build": "7f3e…", "commit": "9c1d…"},
  "plot_types": {"line": {"builtin": true}, "sankey": {"module": "plot_types/sankey.js", "hash": "…"}},
  "blicks": [{
    "id": "emissions/co2-by-sector", "title": "CO2 emissions by sector",
    "group": ["Emissions"], "tags": ["emissions"], "source": {"file": "blicks/emissions.py", "line": 7},
    "plot": {"type": "stacked_area", "channels": {"x": "year", "y": "value", "color": "variable"}},
    "schema": {"dimensions": [{"name": "scenario", "values": ["SSP1-NPi", "SSP2-NPi"]}, "…"],
               "measures": [{"name": "value"}]},
    "controls": [{"dimension": "scenario", "kind": "filter", "default": "SSP2-NPi"},
                 {"dimension": "region", "kind": "split"}],
    "data": "blicks/emissions/co2-by-sector.parquet",
    "baseline": "baseline/emissions/co2-by-sector.parquet",
    "flags": ["value"],
    "change": {"magnitude": 0.12, "value_max": 0.12, "structural": 0.0,
               "counts": {"same": 1310, "changed": 130},
               "top_panels": [{"scenario": "SSP2-NPi", "region": "IND", "dev": 0.12}]},
    "timing_ms": 140, "error": null
  }]
}
```

`top_panels` lets the overview open a changed Blick directly at the combination of control
values that changed most.

### 4.3 Project-defined plot types when rendering happens in the browser

Every plot type, built in or project defined, implements the full contract: `controls` and
`diff` on the build side in Python, `render` and `renderComparison` in the browser as one ESM
module, plus a declaration of its channels. The pieces:

1. **How the built-ins render: Vega-Lite templates.** A template is a Vega-Lite spec with
   channel placeholders, declared in Python as a dict or built with Altair 6, and serialised
   into the manifest. The built-in vocabulary (line, stacked area, bar, scatter, heat map,
   table) renders this way. Split-by injects a `facet` with `columns`, and filtering happens
   before the data reaches Vega. The comparison view layers the baseline as a dashed or grey
   ghost, or shows a difference chart. DVC plots uses the same template idea. A side benefit is
   that Python can render these templates to SVG or PNG with vl-convert, for thumbnails and CI
   report images, without a browser. A declarative tier for project plot types without any JS,
   with the core deriving controls from declared rules, was considered and set aside; it could
   return as a helper layer once project plot types ask for it.
2. **The browser half: an ESM file.** It is loaded by dynamic `import()` from the build output,
   with a cache-busting query in dev. Its shape is close to anywidget's front-end module
   contract:

   ```ts
   export default {
     render({ el, table, mapping, state, theme }) { /* draw; may return a cleanup function */ },
     renderComparison({ el, current, baseline, mapping, state, change }) { /* overlay, delta or side by side */ },
   } satisfies PlotTypeModule;
   ```

   The viewer provides an import map to the libraries it vendors (`vega-embed`, `d3`,
   `d3-sankey-diagram`), so simple plugins need no build step. Plugins with other npm
   dependencies bundle themselves into one ESM file with esbuild or Vite.
3. **The build half: a Python class.** It declares the channels as data, so the dev-mode
   Blick builder can offer them, and implements `controls` and `diff`:

   ```python
   @bk.plot_type("sankey", module="plot_types/sankey.js")
   class Sankey(bk.PlotType):
       channels = {"source": bk.dim(), "target": bk.dim(), "value": bk.measure(),
                   "material": bk.dim(optional=True)}

       def controls(self, schema, mapping):            # unbound dimensions become filters; no split for Sankey
           return [bk.Control(d, "filter") for d in schema.dimensions if d not in mapping.values()]

       def diff(self, baseline, current, mapping, controls):
           return bk.diff.generic(baseline, current, mapping, controls, scale="panel_sum")
   ```

   The core computes nothing chart-specific. The routines the built-ins share (the generic
   magnitude, the Vega-Lite template renderer with its ghost overlay) can be promoted to public
   helpers once two project plot types want the same thing.

**Sankey for MFA.** MFA systems contain loops such as recycling and reuse.

- ECharts' sankey rejects cycles ("Sankey is a DAG, the original data has cycle!").
- Plotly and the original `d3-sankey` (last release 2019) do not route back-links well.
- `d3-sankey-diagram` (Rick Lupton; 0.9.4, August 2026) supports loops, reversed flows and
  typed flows, for example several materials between the same nodes.

It should therefore be the basis of an official `sankey` plot type, shipped as a first-party
plugin. That also tests the plugin path.

### 4.4 Library choices

**Python side**

| Concern | Choice (version) | Why | Alternatives |
|---|---|---|---|
| Internal dataframe engine | **polars 2.0** | Fast joins for diffing, native Parquet writing, `round_sig_figs`, no pyarrow needed. polars 2.0 made the streaming engine the default, and joins no longer guarantee order, so outputs must be sorted explicitly by dimensions. That is required for determinism anyway. | duckdb 2.0 (SQL diffs; good for loaders over large raw files), pandas 3.1 (accepted as input, not used internally) |
| Inputs | Arrow PyCapsule, plus adapters for **pyam 4.0** (pandas-3 compatible), **xarray 2026.9**, **flodym 1.1** | Meet the users where their data lives: IAMC through pyam or ixmp4, MFA through flodym or xarray. | narwhals 2.27 for dataframe-agnostic code |
| Raw data access | Project-defined loader in the adapter, memoised in the dev process; a disk cache (Arrow IPC keyed by input fingerprints) only if measured loader time demands it | Answers the open question about loaders and caching. Lazy access through `pl.scan_*` or duckdb for big files. | — |
| CLI | **typer 0.27** | Type-hint-based, built on click 8.5, good help output. | cyclopts 5.3, click |
| Dev server | **Starlette 1.9 + uvicorn 0.54**, with server-sent events | Static files, SSE and a few JSON endpoints are all that is needed. FastAPI (0.161) adds little. | aiohttp |
| Watching | **watchfiles 1.3** (`awatch`, `run_process`) | Rust `notify` backend, debounce, filters, a process-restart helper. | watchdog |
| Schemas | **pydantic 2.14** | Manifest models and JSON Schema export; TS types for the viewer can be generated from it later. This is the single source of truth for the protocol. | msgspec 0.22 (faster, smaller) |
| Static chart images | **vl-convert-python 1.9** (bundles Vega-Lite 5.8 to 6.4) | SVG in about 12 ms per chart after a 0.4 s warm-up, measured. Useful for thumbnails, PR comments and paper export. | headless browser (heavy) |
| Packaging | **meson-python** with a custom target that runs the viewer build and installs the generated files into the wheel | Chosen over hatchling. Shipping a prebuilt frontend in the wheel is the pattern used by JupyterLab extensions, marimo and Gradio. | hatchling 1.32 with a build hook |

**Browser side**

| Concern | Choice (version) | Why | Alternatives |
|---|---|---|---|
| Build tooling | **Vite 8.3** | Standard choice; library and app builds; the dev server is used only by viewer and plugin developers. | — |
| UI framework | **Nuxt 4 (Vue)**, client-only: `ssr: false`, hash router, relative base URL, generated to static files | The author's preferred stack; a catalog shell (tree, grid, Blick page, forms, the Blick builder) in little code. Plugins are framework-agnostic, so this choice can be reversed. | Svelte 5.57 (smallest bundle), React 19.3 (largest contributor pool; Storybook itself) |
| Charts, built-ins | **Vega-Lite 6.5, Vega 6.4, vega-embed 7.3** | Specs are JSON, so plot types can be data, which fits the language-agnostic goal. Altair 6.3 can author them from Python. Facets for split-by, layers for overlays, CSP-safe interpreter, rendering in Python through vl-convert. Released actively (6.5.0 on 2026-10-08). | Observable Plot 0.6.17: nicer defaults and smaller, but no npm release since February 2025 and no JSON spec. ECharts 6.1: strong interactivity and large data, Sankey without cycles. Plotly.js 4.1: familiar to Python users but heavy. These can be adapter plugins later. |
| Sankey | **d3-sankey-diagram 0.9.4** | Loops and reversed flows; see §4.3. | ECharts sankey (DAG only) |
| Reading data | **hyparquet 1.31** (pure JS, no dependencies) with **hyparquet-compressors 1.1** for zstd | One format for the store and the site data, no WASM, small. Blick tables are small by design. | Flechette 2.7 (Arrow IPC, about 16 KB gzip versus about 43 KB for apache-arrow 21.2), parquet-wasm 0.9 (WASM, larger) |
| Filtering and split-by | Plain typed-array filtering in JS (Arquero 8 if group-bys are needed) | Tables are at most around 10^5 rows, and the controls only filter and partition. | **DuckDB-WASM 1.33**: powerful, but the package has several megabytes of WASM per variant. Lazy-load it later for the exploration job or oversized Blicks, possibly through Mosaic 0.34. |
| Routing | Hash router | Works on GitHub Pages, Zenodo-hosted sites and plain file servers without rewrites. | — |

### 4.5 Snapshot format: experiment

The question was whether snapshots could live in git next to the code. An IAMC-like Blick
table with 6 scenarios, 12 regions, 10 variables and 20 years (14,400 rows) went through 20
successive accepts, each committed to a fresh repository followed by `git gc --aggressive`,
with two change patterns: *local*, where 2 of 10 variables shift by up to 5% after 2030, and
*global*, where every value after 2030 changes.

| Format | File size | Repo growth per accept, local | Repo growth per accept, global |
|---|---:|---:|---:|
| Parquet, zstd (polars default) | 108 KB | 108 KB | 108 KB |
| Parquet, zstd, 6 significant digits | 59 KB | 59 KB | 59 KB |
| Parquet, uncompressed, 6 significant digits | 125 KB | 16 KB | 59 KB |
| CSV, 6 significant digits | 661 KB | 32 KB | 94 KB |
| Arrow IPC, uncompressed | 397 KB | 26 KB | 90 KB |

Findings, and what they decided:

- Compression inside the file blocks git's delta compression, so every accept stores a full
  new blob. Even the best case, uncompressed and rounded Parquet, grows the history by about
  4 bytes per row and accept for a global change. At REMIND scale (about 1,000 Blicks of
  1,500 rows or more, and most model changes are global) that is tens of megabytes per accept,
  plus snapshot conflicts that serialise concurrent pull requests. This is why snapshots live
  in a store and not in git.
- In the store, git's delta compression is irrelevant, so tables are Parquet with zstd, sorted
  by dimensions and rounded to a configurable number of significant digits (default 6).
  Rounding also suppresses floating-point noise across platforms and solvers, which otherwise
  shows up as spurious changes.
- polars writes byte-identical files for identical data, but the Parquet `created_by` field
  carries the exact polars version and build hash. Build and table hashes are therefore
  computed over the canonical table content, never over file bytes, so a library upgrade
  changes no hash.

### 4.6 Diff: where it is computed and a generic change magnitude

**Where.** The magnitude is computed at build time in Python, because the terminal summary,
the manifest and CI all need it. The comparison rendering happens in the browser from both
tables: the site ships `blicks/<id>.parquet` and `baseline/<id>.parquet`. Detailed per-cell
diffs, such as a "changed rows" table, can be computed on demand in the browser.

**Generic magnitude for labelled long tables.** Inputs:

- the baseline table A and the current table B,
- dimension columns K,
- a measure y,
- the panel dimensions P, meaning the dimensions not bound to a channel, which become
  controls. One combination of P values is one view of the chart.

Steps:

1. Full outer join of A and B on K. Each row is *added*, *removed*, *same* (within
   `atol + rtol·|a|`, defaults `rtol=1e-6`, `atol=0`) or *changed*. A null on one side counts
   as added or removed.
2. Panel scale: s_p = max over rows in panel p of max(|a|, |b|). This is the extent of the
   y axis the reader sees for that control selection.
3. Row deviation: d = |b − a| / s_p. Then `value_max` = min(1, max d over changed rows).
4. `structural` = (added + removed) / rows in the union. New or vanished dimension values,
   such as a newly added scenario, show up here, and the diagnostics name them.
5. **magnitude = max(value_max, structural)**, set to 1 when the schema changes. It is 0 if
   and only if nothing changed within tolerance.

Why this definition:

- It is unit-free, so Mt CO2/yr and EJ/yr rank together.
- It is bounded, so it can colour the overview.
- It matches what the eye sees on the chart.
- It does not blow up near zero. Per-point relative differences become meaningless when
  emissions cross zero in 1.5 °C scenarios.

Using the maximum keeps a single large local change from being diluted. A mean can be
reported alongside it.

Plot types override only the scale:

- stacked area and stacked bar: the panel's maximum stack total,
- Sankey: the panel's total throughput, with deviation per link,
- log axes: log differences.

A prototype (polars 2.0, tested on identical tables, a near-zero change and an added
scenario):

```python
def change_magnitude(base, cur, keys, value, panel, rtol=1e-6, atol=0.0):
    if set(base.columns) != set(cur.columns):
        return {"magnitude": 1.0, "schema_changed": True}
    a, b = pl.col(value), pl.col(f"{value}_cur")
    j = base.join(cur, on=keys, how="full", coalesce=True, suffix="_cur", nulls_equal=True)
    by = panel or pl.lit(1)
    j = j.with_columns(
        status=pl.when(a.is_null() & b.is_not_null()).then(pl.lit("added"))
                 .when(a.is_not_null() & b.is_null()).then(pl.lit("removed"))
                 .when((b - a).abs() <= atol + rtol * a.abs()).then(pl.lit("same"))
                 .otherwise(pl.lit("changed")),
        scale=pl.max_horizontal(a.abs().max().over(by), b.abs().max().over(by)),
    ).with_columns(dev=((b - a).abs() / pl.col("scale")).fill_nan(0.0))
    counts = dict(j["status"].value_counts().iter_rows())
    structural = (counts.get("added", 0) + counts.get("removed", 0)) / max(j.height, 1)
    value_max = min(1.0, j.filter(pl.col("status") == "changed")["dev"].max() or 0.0)
    return {"magnitude": max(structural, value_max), "value_max": value_max,
            "structural": structural, "counts": counts}
```

New Blicks, removed Blicks and Blicks whose transformation raised an error get their own
statuses outside the magnitude scale.

### 4.7 Review and accept: input for the open design

How changes are accepted and managed is deliberately undecided. The direction is a UI plus
PR-first interaction, as in Chromatic. What is fixed: a human decides, with a recorded reason,
individually or in bulk; CI never accepts; builds are immutable, so acceptance is data attached
to builds; the baseline is resolved from accepted builds along git ancestry and by run profile.
The material below is input for that design, not the design.

- **Selectors.** Accepting by ids, all, everything below a magnitude, by tag or by change type,
  always with a reason, is the shape every precedent converges on (Chromatic, insta, testthat).
  Bulk accept with one reason per batch is the common case after a model change.
- **The accept record is data.** One record per batch, carrying the reason, the author, the run
  id and fingerprint, and per Blick the baseline hash, the accepted hash and the change, is the
  shape that survives squash merges and never conflicts between branches (the changesets
  argument). Over time the records form a **results changelog** that can be summarised per
  model release, which is valuable for scientific provenance.
- **Staleness.** An accept should name the exact build and baseline it was made against;
  Histoire and OWID treat anything else as stale. Immutable builds make this cheap: the UI
  sends the id of the build it displayed.
- **Where acceptance state could live.** In the store next to the builds, on GitHub (a check
  run or comment carrying the record), or in a small service. The UI must reach a cluster
  store either way, which is what decides the first remote store backend.
- **If the dev server exposes accept,** it binds to localhost and requires a per-session token,
  like Jupyter, so other sites cannot trigger writes. A static shared site stays read-only.
- **Precedents.** Insta's pending candidates versus accepted baselines, testthat's `.new` files,
  Chromatic's carry-over of accepts across branches, OWID's chart-diff.

### 4.8 CI integration

There are two modes, mirroring Chromatic's *UI Tests* and *UI Review*. Both read the store and
neither accepts anything.

| Mode | Needs run data | What it does | Typical place |
|---|---|---|---|
| **Guard** (`blicket check --push`) | yes | Build, resolve the baseline from the store, report changes and errors, push the build. | After every model run on the cluster (SLURM post-run hook); in PR CI for fast models (MFA) or reduced test configurations |
| **Review** (`blicket review`) | no | Take the build already pushed for the PR's head commit, compare it with its resolved baseline, and report. Whether unreviewed changes fail the check depends on the accept design. | Every PR, including those of models that cannot run in CI |

Any two builds in the store can be diffed (`blicket diff <build> <build>`), which covers part
of the deferred "arbitrary run against run" comparison for free.

Outputs:

- exit codes: 0 clean, 1 changes, 2 errors; what counts as a change once acceptance exists is
  part of that design,
- `report.json`, `report.md` (written to `$GITHUB_STEP_SUMMARY`), JUnit XML for GitLab and
  GitHub test reporters,
- later, a sticky PR comment listing the top movers with vl-convert thumbnails, accept reasons
  and deep links into a deployed preview (GitHub Pages, Netlify or Cloudflare Pages, or a CI
  artifact).

A configurable policy (`[tool.blicket.ci] on_change = "warn"|"fail"`, per tag later) is the
likely shape; the default follows from the accept design.

For CI-run models the store must be reachable from the runner. That is where the first remote
store backend (fsspec over SFTP or S3) comes in. Projects without run data in CI can still use
guard mode by fetching a reference run (`blicket fetch-run` from DVC, S3 or Zenodo, keyed by
commit) or by keeping a reduced test configuration of the model. Baseline resolution needs git
history: `git merge-base --is-ancestor` fails in shallow checkouts, so CI fetches enough
history or resolves against an explicit build.

### 4.9 Hot reload mechanics (strategy A)

`blicket dev` runs the Starlette app (viewer, data, SSE), a watcher task (watchfiles `awatch`
over Blick code, plot-type files, the run directory and the config) and the build, all in one
process.

- **The process keeps loaded raw data in memory.** It imports the project once and keeps the
  memoised run loader's results, so editing a Blick does not re-read a large `.mif`, `.gdx`
  or pickle.
- **A change to a Blick or helper module reloads code, not data.** Project modules are
  reloaded in import order except the loader, the memoised run object survives, and only the
  affected Blicks are rebuilt, diffed and written. Then an SSE event
  `{"type": "blick", "id": …, "flags": …, "magnitude": …}` goes out, and the browser
  refetches that Blick while keeping its control state. The loader output is fingerprinted
  before and after a build, so a transformation that mutates the shared run object in place
  is reported instead of silently diverging from a clean `check`.
- **A change to the loader or the config restarts the process.** A disk cache of loader
  outputs (Arrow IPC keyed by input fingerprints) is added only if measured loader time
  demands it; otherwise the warm process is the cache.
- **A new run in the run directory triggers a full rebuild** under a new build id. The run
  directory is polled with a quiet period, because inotify is unreliable on cluster
  filesystems and fires mid-write. Per-Blick cache keys (function source, plot config, run
  fingerprint) are a TurboSnap-like option to skip unchanged Blicks later.
- **A change to a plot-type JS file** sends an SSE `plugin` event, and the browser re-imports
  the module with `?t=<timestamp>`.
- **Errors** appear as a per-Blick error state with a traceback in the UI and the terminal,
  and never abort the build. A module that fails to import marks the build incomplete, so
  its Blicks are not reported as removed.

A target to aim for: under 1 s from saving a Blick file to an updated chart, for typical
transformations.

### 4.10 Path to R

R comes after milestone 4. The steps, in order:

1. **Protocol.** The manifest schema, table conventions and store layout are documented and
   versioned. This alone lets R users produce builds with a script that writes Parquet
   (nanoparquet 0.5.2 has no dependencies; arrow 25 is the alternative) plus a manifest
   fragment. The Python CLI then handles diff, the store and serve.
2. **R SDK (`blicket` for R).** `blick()` registration mirrors the Python decorator, and a
   runner entry point `blicket::run_blicks(ids, run)` writes outputs. The Python core calls
   it through `Rscript` (runner protocol: JSON on stdio). R users get the core either through
   `reticulate::py_require("…")`, which since reticulate 1.41 provisions an ephemeral
   uv-managed Python environment automatically, or through `uv tool install`.
3. **Persistent R runner.** A long-lived R process (callr or processx) keeps raw data loaded,
   which makes hot reload in R as good as in Python.
4. **Plot types from R** are the open problem, because the build half of the contract is
   Python. R Blicks that use the built-in plot types are the realistic first step.

This matters concretely: REMIND's comparison tooling (`piamPlotComparison::compareScenarios`,
`mip`, `quitte`) is R, while the MFA stack (flodym, REMIND-MFA) is Python.

## 5. Comparison

Ratings: ++ very good, + good, o neutral or depends, − weak.

| Criterion | A: Python-centric | B: TS core (Storybook-like) | C: Protocol only | D: Native core | **A+C (recommended)** |
|---|---|---|---|---|---|
| Job 1: development companion (hot reload of Blick code) | ++ the Python process already holds the data | + Vite HMR helps the UI and plugins, but Blick code still needs a Python runner across a process boundary | o needs some implementation | + | ++ |
| Job 2: automated guard in CI | ++ `pip install`, one runtime | + needs Node and Python | o | ++ single binary | ++ plus review mode without run data |
| Job 3: communication artifact (static site) | ++ | ++ | ++ | ++ | ++ |
| Job 4: exploration | + | + | + | + | + (the dev-mode Blick builder; DuckDB-WASM later) |
| Project plot types (developer experience) | + Python class plus ESM | ++ one language, npm, HMR | + declarative plus ESM | o hooks need callbacks | + one Python class plus one ESM module, the same contract as the built-ins |
| Deferred: data model | + labelled long table at Blick output, raw data opaque | + | + must be fixed in the spec early | + | + fixed only at Blick output, as the concept suggests |
| Deferred: language (R) | − alone | ++ symmetric SDKs | ++ | ++ no Python needed | + R SDK writes the same files; core through reticulate or uv |
| Install friction for scientists (laptop, HPC) | ++ | − two runtimes | depends | ++ | ++ |
| Effort to v0 | ++ lowest | − runner protocol and two runtimes from day one | − spec designed up front | −− | + (+ schema discipline) |
| Contributor pool among target users | + Python, some TS | o TS core | + | − Rust | + |
| Lock-in and evolution | − | + | ++ | + | ++ can move the core to D later without breaking projects |

## 6. Recommendation

**Build strategy A with C's discipline.** That means a Python reference core, a prebuilt
Nuxt and Vega-Lite viewer in the wheel, and a versioned file protocol between them from
day one.

Rationale:

1. **The highest-priority loop is Python-shaped.** Job 1 is "edit Blick code, see the
   change". That code is Python, and fast reload needs a warm Python process that holds the
   raw data. Strategy B would still need that process, plus Node.
2. **One runtime for users and CI.** Model developers on HPC clusters and in CI only need
   `uv` or `pip`. Node is a maintainer-only build dependency, as in marimo or JupyterLab.
3. **The contract split is natural.** Build-time halves (controls, magnitude) run in Python,
   and view-time halves (render, comparison) run in the browser. Every plot type implements
   both; the built-ins render through Vega-Lite templates, and project plot types such as
   Sankey bring their own JS module.
4. **The protocol keeps R and the future open.** The R SDK writes the same files. A native
   core (D) or a Node core (B) could replace the Python core later without breaking user
   projects or the viewer.
5. **What to take from B:** Storybook's concepts (CSF-like modules, an index, URL-state
   controls, a prebuilt shell, an embed route, Chromatic's baseline model and, as the stated
   direction, its UI-and-PR-first accept flow) rather than its runtime. Plugin authors who want TypeScript and npm can bundle with Vite themselves.

**What would change the recommendation.** If R becomes the primary audience and Python in
the loop proves to be a real barrier despite reticulate and uv, move the core to D. If
project plot types turn out to be the main activity, more than the built-in vocabulary,
reconsider B's single-language contract by running the magnitude for JS plot types in Node.

## 7. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Large Blick tables | Blick authors control granularity, and a soft limit warns on large tables (for example above 100k rows or 5 MB) for the browser's sake; DuckDB-WASM loaded lazily later. Storage in the store is no constraint, and every build is kept. |
| CI cannot run the model (hours of runtime, solver licences) | Review mode needs no run data; it reads the build a cluster post-run hook pushed. Reduced test configurations, or reference runs fetched by commit. |
| Floating-point noise creates spurious changes | A project-wide tolerance relative to the panel scale, overridable per Blick, rounding to significant digits, deterministic sorting. Defaults are measured on real reruns across machines. Polars 2's join order is not guaranteed, so sort explicitly. |
| Generic magnitude misranks some Blicks (log scales, shares, Sankey) | The magnitude is for ranking only, as the concept says. Plot types own their `diff`, Blicks can set `diff=` options, and diagnostics (counts, top panels) are shown next to the number. |
| The plot type contract spans two languages and confuses plugin authors | One Python class plus one ESM module, with the built-ins as worked examples and Sankey as a first-party project plot type. Shared routines become public helpers once two plot types want them. |
| Python module reload is subtly wrong (stale state, helpers) | Reload code, not data: project modules are reloaded in import order except the loader; a restart only when the loader or config changes; the loader output is fingerprinted before and after a build to catch in-place mutation. |
| Blick identity breaks on refactors | Explicit ids independent of the file path, and `aliases`. |
| Viewer and core drift apart, or third-party producers break | The manifest has a `spec` version, the viewer supports N−1, and JSON Schema validation runs in `blicket build` and in the viewer's tests. |
| Charting library stagnates | Vega-Lite is actively released. Plot types isolate the library choice, and ECharts or Plot adapters can be added as plugins. |
| Baseline resolution needs git history | `git merge-base --is-ancestor` fails in shallow CI checkouts; fetch enough history, or resolve against an explicit build. |
| A static site opened from `file://` cannot fetch data | Hash routing, `blicket serve` for local viewing; a folder picker or an inline-data single-file build later. |
| Writes from the dev UI are a security exposure | Bind to localhost, use a per-session token, write only to the store. |
| Scope drifts into a dashboard builder | Keep the concept's rule: a Blick builder, not a dashboard builder. One Blick at a time, and ad hoc Blicks are not saved. |

## 8. Milestones

The smallest version that does jobs 1 and 2 for one Python project, cut into steps that are
each useful on their own. The first project is remind-mfa, whose runs are folders containing a
`model.pickle`; its adapter and Blicks live under `examples/` in the blicket repository.

- **M0 Headless build and compare.** `@bk.blick` and `bk.register`, module discovery from
  `[tool.blicket]`, the adapter and loader protocol with `RunInfo` (run id, profile,
  fingerprint, commit), canonical tables, the `PlotType` contract with the Python halves of
  line, stacked area and bar, the store with push and baseline resolution against an explicit
  build or a branch, flags and magnitude, `blicket check`, `blicket diff <build> <build>`,
  `report.md`, exit codes. Two measurements on remind-mfa: loader time, and noise across reruns
  and machines, which sets the tolerance defaults.
- **M1 Catalog.** The Nuxt viewer: an overview ranked by magnitude, the Blick page with
  controls and the comparison toggle, the browser halves of the built-ins, `blicket build`,
  `blicket serve`.
- **M2 Dev loop.** `blicket dev` with code reload, SSE and run-directory polling; scatter and
  table plot types; the Blick builder (run picker, variable picker, channel mapping, item
  selection) over the adapter's dataset protocol.
- **M3 Review and accept.** Its own design session first (UI plus PR-first). Then the UI, the
  link from a cluster run to a branch or PR, the PR comment and commit status, and the store
  backend the UI needs.
- **M4 Plugins and hardening.** A project plot type end to end (an MFA Sankey on
  `d3-sankey-diagram`), the `spec` version documented as the protocol, a difference chart,
  store `gc`.
- **Later.** R SDK and runner; composition (several models per repository); DuckDB-WASM for
  large tables; preview deploys; the deferred items: variants, checks, auto-accept, grouping
  by shared inputs.

## 9. Effect on the concept's open questions

- **Snapshot size and storage.** Builds live in a store where storage is no constraint; the
  only size concern left is the browser, handled by soft limits and lazy DuckDB-WASM later.
- **Dimension values appearing or disappearing.** A `schema` flag per Blick, with diagnostics
  that name the new or vanished values; the magnitude is computed on the common keys.
- **Blick identity.** Explicit ids independent of the file path, plus aliases.
- **Raw data access.** A project-defined loader in the adapter, memoised in the dev process;
  a disk cache only if measured loader time demands it. Lazy scans for big files.
- **Several runs per branch.** Run profiles in `RunInfo`; each profile resolves its own
  baseline. Several models per repository: Storybook-style composition later.
- **Static-first and exploration.** Per-Blick tables keep the site static. The dev-mode Blick
  builder covers exploration; DuckDB-WASM is the upgrade path if the static site needs more.

## Sources

- Storybook 10 release (ESM-only, CSF Factories in preview): https://catalog.js.org/blog/catalog-10/ ; https://catalog.js.org/releases/10.0
- Storybook indexers: https://catalog.js.org/docs/api/main-config/main-config-indexers
- Storybook addons and manager/preview architecture: https://catalog.js.org/docs/10.4/addons.md
- Chromatic branching and baselines, TurboSnap: https://www.chromatic.com/docs/branching-and-baselines ; https://chromatic.com/docs/turbosnap
- Chromatic Visual Tests addon: https://www.chromatic.com/docs/visual-tests-addon
- Insta CLI review flow: https://insta.rs/docs/cli/
- Vega-Lite parameters, binding and facets: https://vega.github.io/vega-lite/docs/bind.html ; https://vega.github.io/vega-lite/docs/facet.html
- Observable Plot facets and Arrow input: https://github.com/observablehq/plot/blob/main/docs/features/facets.md ; https://github.com/observablehq/plot/blob/main/docs/features/marks.md
- DuckDB-WASM: https://github.com/duckdb/duckdb-wasm
- hyparquet and hyparquet-compressors: https://github.com/hyparam/hyparquet ; https://unpkg.com/hyparquet-compressors@1.1.1/README.md
- Flechette: https://github.com/uwdata/flechette
- Vite plugin API (configureServer, server.ws.send, handleHotUpdate): https://github.com/vitejs/vite/blob/v8.0.10/docs/guide/api-plugin.md
- polars `write_parquet` and joins: https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html ; https://docs.pola.rs/api/python/stable/reference/lazyframe/api/polars.LazyFrame.join.html
- polars 2.0 changes (streaming default, join order): https://www.kunalganglani.com/blog/polars-2-0-upgrade-guide
- pyam release notes: https://github.com/IAMconsortium/pyam/blob/main/RELEASE_NOTES.md
- flodym: https://flodym.readthedocs.io/
- watchfiles: https://github.com/samuelcolvin/watchfiles
- vl-convert: https://pypi.org/project/vl-convert-python
- anywidget front-end module: https://deepwiki.com/manzt/anywidget
- ECharts Sankey cycle limitation: https://git.tdem.in/openobserve/openobserve/issues/3426 (refers to apache/echarts#19505)
- Plotly Sankey circularity: https://community.plotly.com/t/sankey-diagram-handling-circularity-error/15102
- d3-sankey-diagram (loops, reversed flows): https://cdn.jsdelivr.net/npm/d3-sankey-diagram@0.9.4/README.md
- nanoparquet: https://nanoparquet.r-lib.org/
- reticulate `py_require` (uv-managed environments): https://posit.co/blog/reticulate-1-41 ; https://rdrr.io/pkg/reticulate/man/py_require.html
- Observable Framework data loaders: https://observablehq.com/framework/loaders
- REMIND compareScenarios: https://pik-piam.r-universe.dev/piamPlotComparison/doc/compareScenarios.html
- Version numbers: npm registry, PyPI JSON API and crandb, queried 2026-10-22.
