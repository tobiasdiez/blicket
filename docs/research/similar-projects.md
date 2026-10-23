# Prior art for blicket: similar and adjacent projects

Status: research note, written 2026-10-22. Companion to [concept.md](../concept.md), which it does not change.

## Purpose and method

This note surveys existing tools that overlap with blicket, the "Storybook for data projects".
It asks three questions about each one: which of its features are worth adopting in some
form, what should be avoided, and whether it already does what blicket plans to do.

The survey covered seven areas:

- UI component catalogs and visual review services.
- Snapshot testing.
- Table diffing and data validation.
- Experiment tracking, pipeline tools and benchmark trackers.
- Reports, notebooks and dashboards.
- Declarative plot vocabularies.
- Tooling from the IAM, energy and MFA modelling communities.

Facts were checked against documentation and source code on 2026-10-22. Star counts and version
numbers come from GitHub, PyPI and npm on that day and are approximate. Features documented
only for unreleased versions are marked as such.

**How each section is laid out:** what the tool is, how mature it is, its top three features
for blicket, what to avoid, and how much it overlaps with blicket. Under each feature, the line
starting "→ blicket:" says what the feature would become in blicket's terms. Part 8 covers
further projects briefly. Part 9 is the synthesis.

## Short answer

- **No existing tool covers the concept.** The individual pieces all exist: a catalog with
  controls, stored baselines with review and accept, table diffs, and domain reports. Nothing
  combines them for data. The missing combination is a snapshot of each Blick's table in a
  build store, a change size computed per plot type, and a ranked review with recorded reasons.
- **Closest prior art**, in order of relevance:
  1. Our World in Data's **chart-diff**: a review-and-accept flow for charts driven by data.
     It is bound to a server and cannot be reused.
  2. **Histoire 1.0's visual testing**: the best design for local review with baselines in
     git, but for UI pixels.
  3. **Observable Plot's test harness**: charts as functions, snapshots in git, and a browser
     view during development.
  4. **Recce**: data review at pull-request time, with sign-off.
  5. The archived **pypsa-validator**: pull-request comments ranking IAMC variables by how much
     they changed.
  6. The `run_comparison` module in **remind-mfa**, written by the concept's author.
- **Strongest ideas not yet in the concept:**
  - A taxonomy of change types, instead of a single magnitude.
  - A build that always runs to the end, is pushed as an immutable candidate, and is never
    accepted by CI.
  - A review path for runs made on a cluster.
  - Fingerprinting each change, so identical changes are grouped and accepted once.
  - Accept records tied to content hashes.
- **Genuinely new territory:** I found no prior art for comparing two Sankey diagrams, and no
  catalog that works on data and knows about its dimensions.

---

## Part 1. Closest prior art for the review flow

### 1. Our World in Data: ETL, Grapher and chart-diff

- **Links:** https://github.com/owid/etl (chart-diff lives under `apps/wizard/app_pages/chart_diff`),
  docs at https://docs.owid.io/projects/etl/guides/wizard/, Grapher at https://github.com/owid/owid-grapher
- **Maturity:** MIT. owid/etl has about 160 stars but gets many commits a day. It is the
  production system of a major data publisher. It is tied to OWID's own stack (MySQL, one
  staging server per pull request, Grapher), so it cannot be reused as a library.

**What it is.**
- Charts are defined as config (`.chart.yml`, validated against a JSON schema) and linked to
  the data steps of the ETL through a dependency graph.
- Every pull request gets a staging server.
- The Wizard, a Streamlit app, has a chart-diff page listing every chart that differs between
  staging and production. Each one has to be approved or rejected before merge.

**Top 3 features**

1. **Typed changes and a CI gate that passes once everything is reviewed.**
   - Each chart diff is tagged with what changed (`data`, `metadata`, `config`, new), computed
     from checksums.
   - The GitHub check `owidbot/chart-diff` fails while any chart is unreviewed. It passes once
     all charts are reviewed, not when nothing has changed.
   - After merge, only approved charts are synced to production.
   - → blicket: label every change with its cause (data, Blick code, plot config, new,
     removed). The CI check means "every change is reviewed", not "nothing changed".
2. **A ranked review queue with bulk approve and history.**
   - The queue is sorted by a relevance score that weights chart views, references and an
     anomaly score. It can be filtered by change type, and reviewed charts can be hidden.
   - One click approves every pending chart that has no conflict.
   - Each chart has tabs for the side-by-side view, the config diff, and the approval history.
   - An approval goes stale when either side changes, tracked by timestamps.
   - There is no free-text reason field (`ChartDiffApprovals` in `etl/grapher/model.py`).
   - → blicket: this is nearly blicket's overview and review page. For the review-flow design:
     add the reason, and tie approvals to the hash of the accepted build instead of timestamps.
     Optionally let Blicks carry an importance weight (for example "used in the paper") that
     is multiplied into the ranking.
3. **Automatic approval within tolerances, and a usable anomaly metric.**
   - `etl approve --allow-small-changes` has four knobs:
     - relative tolerance per point (default 1%);
     - absolute floor (default 1e-6), so tiny values near zero don't look like huge changes;
     - maximum number of changed points per dimension (default 5);
     - maximum number of new points (default 1000).
   - The Anomalist's version-change detector uses
     BARD = |a−b| / (|a|+|b|+ε), with ε = (P95−P5)/10 of the series (`apps/anomalist/detectors.py`).
     The score lies between 0 and 1, is symmetric, and is robust near zero.
   - → blicket: four ready-made knobs for the deferred tolerance decision, and BARD as the
     per-point measure in the generic diff.

**Avoid**
- The baseline is the live production database, mutable server state that needs its own
  conflict machinery. blicket's builds are immutable, which avoids this.
- Changes caused by data cannot really be rejected, so the review drifts towards a rubber stamp.

**Overlap.** It covers blicket's review half, for one organisation's charts. It has no catalog
with dimension controls. The ideas transfer; the code does not.

### 2. Storybook

- **Links:** https://storybook.js.org, https://github.com/storybookjs/storybook
- **Maturity:** MIT, about 91k stars, v10.6.3 (2026-10-20). Versions 9 and 10 reduced bundle
  and install size after complaints about bloat
  (https://storybook.js.org/blog/storybook-bloat-fixed/).

**What it is.** A workshop for UI components in isolation. Files in Component Story Format (CSF)
export stories, which are fixed inputs ("args") for a component. It has a dev server with hot
reload, a static build, and addons.

**Top 3 features**

1. **Controls inferred from types, with overrides.**
   - argTypes are inferred from component types: boolean becomes a toggle, enum a select,
     number a range.
   - Manual settings override the inferred ones, an `if` field shows a control only under a
     condition, and args can be set in the URL (`&args=size:100`).
   - Docs: https://storybook.js.org/docs/api/arg-types
   - → blicket: `controls()` infers controls from column type and number of distinct values,
     the Blick can override them, and the control state lives in the URL so links to an
     exact view can be shared.
2. **Indexers and `index.json`.**
   - `experimental_indexers` (a `test` regex plus `createIndex(file)`) lists stories from
     non-CSF files without running them.
   - The static build publishes `index.json`.
   - Composition merges several published Storybooks through `refs`.
   - Docs: https://storybook.js.org/docs/api/main-config/main-config-indexers
   - → blicket: separate discovery (reading the manifest, no transformations run) from
     execution, and emit a stable `index.json`. This keeps definitions written in R possible
     later, and lets an IAM catalog and an MFA catalog share one sidebar.
3. **Tags and test hooks.**
   - Tags are set at project, component or story level, are inherited, and can be removed
     with `!tag`. Custom tags become sidebar filters.
   - The Vitest addon turns every story into a smoke test, and `play` functions add
     assertions.
   - Since 10.3 there is an MCP server and a component manifest for coding agents.
   - Docs: https://storybook.js.org/docs/writing-stories/tags
   - → blicket: tags such as `ci`, `paper` or `slow` select which Blicks CI guards and which
     the published build shows. A per-Blick checks slot can later host mass balance checks.
     A machine-readable change manifest lets agents answer "which Blicks changed and why".

**Avoid**
- A heavy dependency footprint and churn between major versions.
- Stories drifting away from real usage. blicket avoids this only if Blicks stay the real
  analysis code, with no wrapper layer that diverges from it.
- Composed Storybooks lose addon behaviour.

**Overlap.** None on the data side. The UX patterns can be reused directly.

### 3. Chromatic (and the Storybook visual tests addon)

- **Links:** https://www.chromatic.com, CLI at https://github.com/chromaui/chromatic-cli
- **Maturity:** the CLI is MIT, v18.13.3 (2026-10-22). The service is proprietary. The free
  tier is 5,000 snapshots a month; paid plans start at $179 a month.

**What it is.** A SaaS from the Storybook team. It snapshots every story in cloud browsers,
diffs each against its baseline, and runs a review-and-accept flow wired into pull-request
checks.

**Top 3 features**

1. **Accept or deny, with a build state.**
   - Accepting a change makes it the new baseline. Denying it marks a regression and fails
     the build. Anything unreviewed leaves the status check pending.
   - Keyboard: `a` accepts, `d` denies, `1` flips between baseline and new.
   - Batch accept works per component or for the whole build. The Storybook addon can accept
     locally, and its decisions sync with CI.
   - Docs: https://www.chromatic.com/docs/quickstart/
   - → blicket: three states (unreviewed, accepted, rejected), keyboard review, and accept at
     the level of a Blick, a group, or everything. Local review and CI share one source of
     truth, the store. How acceptance is recorded there is the open review-flow design, and
     Chromatic's states are its template.
2. **Baselines that follow git history.**
   - Baselines come from ancestor builds, with tie-breaking rules and a
     `preferMergedBaselines` flag. Squash and rebase merges are detected through the git
     provider's API, and `--auto-accept-changes` is used on main.
   - Chromatic's own docs call this "conceptually like storing a snapshot file in your
     repository" (https://www.chromatic.com/docs/branching-and-baselines/).
   - → blicket: this is blicket's design. Builds are pushed to a store, and the baseline for
     a build is resolved from ancestor builds by git ancestry and run profile. A store the
     project controls replaces Chromatic's SaaS. The tie-breaking rules and the detection of
     squash and rebase merges are the details to copy.
3. **TurboSnap and thresholds that inherit.**
   - Only stories whose dependency graph changed are captured. Changes to global files such as
     `preview.js` or the lockfile force a full rebuild.
   - `diffThreshold` (default 0.063) can be set per story, component or project. Flaky
     snapshots can be quarantined.
   - Docs: https://www.chromatic.com/docs/turbosnap/
   - → blicket: skip Blicks whose fingerprint (Blick code, imported helpers, inputs read) is
     unchanged, and invalidate everything when the shared loader changes. Tolerances inherit
     from project to group to Blick.

**Avoid**
- Per-snapshot billing and lock-in.
- Baseline rules that users cannot reason about.
- Auto-accept on main silently swallowing changes.
- The need for pixel "modes" that multiply stories by viewports and themes. One table snapshot
  covers every control state at once; keep that advantage.

**Overlap.** None: it works on pixels, for JavaScript UIs, as a SaaS.

### 4. Histoire (and Ladle)

- **Links:** https://histoire.dev, https://github.com/histoire-dev/histoire
- **Maturity:** MIT, about 3.6k stars. The last stable release is 0.17.17 (2024-04).
  1.0.0-beta.1 came out on 2026-01-07, and main is very active. Visual testing is documented for
  "1.0-beta.2+", so it is **not yet in a published release**.

**What it is.** A Storybook alternative built on Vite, for Vue, Svelte and React, with stories
and variants.

**Top 3 features**

1. **Local visual review with baselines in git.** The best local review design with baselines
   kept in the repository (docs: https://github.com/histoire-dev/histoire/blob/main/docs/guide/visual-testing.md).
   blicket keeps baselines in a store instead, but the CLI contract transfers.
   - Config: `baselineDir`, `baselineRef: 'main'`, `threshold`, `maxDiffPixelRatio`.
   - The workbench shows side by side, diff, and an opacity overlay. Results can be checked for
     bulk approval, and approving writes the exact captured image without capturing again.
   - "Compare to main" reads approved baselines from a git ref, resolved to a commit SHA,
     without a checkout.
   - CLI: `histoire visual [--incremental] [--baseline-ref main] [--update --case X | --update --all]`.
     `--update` requires an explicit filter or `--all`.
   - Exit codes are 0, 1, 2 and 130. "Ordinary runs never change approved baselines."
   - CI uploads a read-only HTML report that works offline.
   - → blicket: copy this CLI contract almost verbatim. Comparing against the latest build of
     a branch, `blicket check --against main`, answers "what changed compared with main"
     without a checkout, and also gives a cheap form of run-against-run comparison.
2. **Results go stale when their inputs change.**
   - Results live in an ignored `.histoire/visual/` folder, together with fingerprints of
     source, case, profile, baseline and comparison policy.
   - When any input changes, the result is marked "Stale" and cannot be approved until it is
     run again. `--incremental` captures only missing or stale results.
   - → blicket: for the review-flow design, never allow accepting a result computed from
     outdated Blick code or an outdated baseline. Immutable builds reduce this to a check of
     build ids. Incremental rebuilds follow for free.
3. **Props matrix.**
   - Two axes are rendered as a grid of all combinations, detected automatically for booleans
     and enums. Any cell can be saved as a variant.
   - → blicket: "split by two dimensions" (scenario × region) as a generic small-multiples
     control. Saving a cell is the deferred "variants" idea.

**Ladle**
- **Links:** https://ladle.dev
- **Maturity:** MIT, about 3k stars, 5.1.1 (2025-11), in maintenance mode.
- React only and CSF-compatible, with very small output.
- Its `meta.json` lists every story with id, file path, line range and metadata
  (https://ladle.dev/docs/meta).
- Visual snapshots take about ten lines of Playwright: read `meta.json`, wait for
  `[data-storyloaded]`, take a screenshot.
- → blicket: publish a machine-readable Blick manifest with source locations, and a "ready"
  signal so that pixel tests can be added outside the core. Split the code per Blick so a
  catalog of thousands stays fast.

**Avoid**
- Histoire spent two years without a stable release.
- Baselines must be split by operating system because rendering is not deterministic. The
  numerical equivalent is differences between BLAS libraries or solvers, so put tables into a
  canonical form (sorted, rounded) before snapshotting.

**Overlap.** None for data.

### 5. Visual regression services: Argos, Percy, Playwright, Lost Pixel, reg-suit

| Tool | Link | Licence and maturity |
|---|---|---|
| Argos | https://argos-ci.com, https://github.com/argos-ci/argos | MIT, about 650 stars, very active, SaaS with a free tier |
| Percy | (BrowserStack) | SaaS, MIT CLI |
| Playwright | https://playwright.dev | Apache-2.0, about 98k stars, v1.64.1 |
| Lost Pixel | https://github.com/lost-pixel/lost-pixel | MIT, **archived**: "joining Figma, we are sunsetting the product". Last release 2024-11 |
| reg-suit | https://github.com/reg-viz/reg-suit | MIT, about 1.3k stars, v0.14.6 (2026-03) |

**Top 3 features**

1. **Diff fingerprints (Argos) and grouped approvals (Percy).**
   - Argos gives each diff "a stable signature computed from the shape of its diff".
   - Identical diffs collapse into one row ("N similar"), and one accept covers all of them.
   - Approvals carry over when the fingerprint matches again.
   - "Ignore" suppresses that exact change in future builds. An automatic ignore rule kicks in
     after 3 occurrences in 7 days, and each test gets a flakiness score from 0 to 100.
   - Percy approves "groups of matching visual changes". Its 2025 review agent summarises each
     distinct change with the number of snapshots affected.
   - Docs: https://argos-ci.com/docs/learn/review-workflow/review-a-build.md
   - → blicket: a normalised hash of each Blick's delta table implements the deferred
     "grouping" decision. Accept a group once, carry the accept over when the same change
     reappears after a rerun, and quarantine known solver noise. Add a text summary per group,
     for example "Emissions|CO2 −3% in EU after 2040, 12 Blicks".
2. **Explicit update modes (Playwright).**
   - `--update-snapshots all|changed|missing|none`.
   - Tolerances: `threshold`, `maxDiffPixels`, `maxDiffPixelRatio`.
   - A path template puts the platform into the snapshot file name.
   - Docs: https://playwright.dev/docs/test-snapshots
   - → blicket: input for the review-flow design: selectors such as missing, changed and all,
     each with a recorded reason. A default reason may be acceptable for new Blicks only.
3. **Pluggable baseline source (reg-suit) and baseline updates by pull request (Lost Pixel).**
   - reg-suit has no approve step. The expected images are the snapshot at the merge base,
     fetched by a plugin that derives a key from the git hash.
   - It has three plugin slots: key generator, storage, and notifier.
   - Lost Pixel's open-source mode had a manually triggered CI job, run in update mode, that
     opened a pull request containing the new baselines.
   - → blicket: the store is the pluggable baseline source: a directory by default, remote
     backends later. reg-suit's key derived from the git hash is the same idea as resolving
     baselines by ancestry. When runs are too heavy for a laptop, the run machine pushes its
     build to the store and the review happens from the pull request.

**Also notable.** Since May 2026, Argos accepts text and JSON snapshots, but not CSV. A crude
data catalog could be put together on top of it, but without controls, diffs that know the
plot type, or ranking.

**Avoid**
- An open-source core whose review UX exists only in a SaaS. Lost Pixel died with its company.
- Pixel baselines as the main signal.

**Overlap.** None.

---

## Part 2. Snapshot testing

### 6. insta (Rust) and cargo-insta

- **Links:** https://insta.rs, https://github.com/mitsuhiko/insta
- **Maturity:** Apache-2.0, about 3k stars, 1.49.0 (2026-10-03).

It has the best review UX of any snapshot tool I found.

**Top 3 features**

1. **Pending files and a review CLI.**
   - A changed snapshot is written as `.snap.new` next to the `.snap` file.
   - `cargo insta review` steps through them: `a` accept, `r` reject, `s` skip (the pending
     file stays), `d` toggle the diff, `i` toggle extra info.
   - `accept` and `reject` act on everything at once. `pending-snapshots --as-json` feeds
     editors.
   - `cargo insta test --review` makes every assertion pass, so all changes are collected
     before review.
   - A VS Code extension shows pending snapshots in a sidebar.
   - Docs: https://insta.rs/docs/cli/
   - → blicket: `blicket build` always runs to the end and pushes an immutable candidate
     build. For the review-flow design: accept, reject and skip; accept all requires a reason;
     a JSON list of pending changes feeds editors and the UI.
2. **Metadata in the snapshot header, shown during review.**
   - The header records the source location, the expression, the input file, and a
     user-supplied description and info.
   - Docs: https://insta.rs/docs/snapshot-files/
   - → blicket: the build manifest carries per-Blick metadata: id, source location, hash of
     the transformation source, plot type and version, run id and commit. Acceptance metadata
     (reason, author, date) is attached to builds in the store and shown in review.
3. **Update modes that know about CI, and handling of orphaned snapshots.**
   - `INSTA_UPDATE=auto` writes nothing in CI and `.snap.new` files locally.
   - `--accept-unseen` accepts only new snapshots.
   - `--unreferenced=ignore|warn|reject|delete|auto`, where `auto` rejects in CI and deletes
     locally.
   - Redactions such as `rounded_redaction(n)` and `sorted_redaction` put values into a
     canonical form.
   - Docs: https://insta.rs/docs/redactions/
   - → blicket: express the CI policy as named modes. Offer a preset "accept new Blicks
     automatically, review changed ones". Orphans default to `auto`. Round and sort tables
     before hashing them.

**Avoid**
- YAML text does not scale to large numeric tables.
- Review goes in file order with no ranking, so you still step through everything.
- Detecting orphans is only safe on a full run.

**Overlap.** None. Use it as the UX template.

### 7. R: testthat 3rd edition snapshots and vdiffr

- **Links:** https://testthat.r-lib.org/articles/snapshotting.html, https://github.com/r-lib/vdiffr
- **Maturity:** testthat is MIT, about 940 stars, v3.3.2 (2026-01). vdiffr is MIT, about 200
  stars, v1.0.9 (2026-02). Both are core r-lib packages, and REMIND's community works in R.

**What it is.**
- `expect_snapshot()` stores output as Markdown in `_snaps/`.
- `expect_snapshot_file()` writes `name.new.ext` when a file changes.
- vdiffr's `expect_doppelganger()` writes plots as SVG snapshots.

**Top 3 features**

1. **A review app plus scoped accept and reject.**
   - `snapshot_review()` opens a Shiny app with accept, reject and skip.
   - It shows diffs through diffviewer: resemble.js for images, daff.js for data frames, and
     jsdiff for text.
   - `snapshot_accept(files=)` and `snapshot_reject()` act on any subset.
   - Docs: https://testthat.r-lib.org/reference/snapshot_accept.html
   - → blicket: the review UI lives in the catalog itself. Bulk accept can be scoped by a
     selector (group, tag, path pattern). Table diffs use daff style. R users already know
     these verbs, so reuse them.
2. **Candidates built in CI, pulled in locally.**
   - `snapshot_download_gh()` fetches snapshots produced on GitHub.
   - Since 3.3.0, creating a new snapshot fails on CI.
   - → blicket: crucial when model runs happen on a cluster or in CI. The store is this path:
     a build made there is pushed, and a person reviews it from wherever the store is
     reachable. Nobody has to rerun the model on a laptop.
3. **`variant`, `transform` and `cran = FALSE`.**
   - `variant` keeps parallel snapshot sets under `_snaps/{variant}/`.
   - `transform` scrubs volatile lines.
   - Snapshot tests are skipped on CRAN because they are "fragile".
   - → blicket: variants are run profiles, each resolving its own baseline in the store,
     which answers "several runs per repository". `transform` becomes a scrubber. Keep the
     guard out of release contexts.

**vdiffr's lesson**
- It snapshots SVG rather than PNG so that changes can be reviewed as text.
- It even embeds svglite and harfbuzz with precomputed font metrics, to stay independent of
  system fonts.
- It still warns that upstream changes cause "subtle differences … that are not actual
  failures", and ggplot2 4.0 forced users to re-accept snapshots en masse.
- This is the strongest available evidence for blicket's decision to snapshot tables, not
  pictures.

**Avoid**
- Image snapshots that break on dependency upgrades.
- Unused variants that must be cleaned up by hand.

**Overlap.** None. An R adapter that mirrors these verbs would make blicket feel native to
REMIND users.

### 8. Jest and the pytest snapshot plugins

| Tool | Link | Licence and maturity |
|---|---|---|
| Jest | https://jestjs.io/docs/snapshot-testing | MIT, about 45.5k stars, v30.5.2 |
| syrupy | https://github.com/syrupy-project/syrupy | MIT, about 890 stars, v6.1.1 (2026-09) |
| inline-snapshot | https://15r10nk.github.io/inline-snapshot/latest/ | MIT, about 760 stars, v0.36.1 (2026-10) |
| pytest-regressions | https://pytest-regressions.readthedocs.io | MIT, 220 stars, v2.11.0 (2026-05) |
| pytest-mpl | https://pytest-mpl.readthedocs.io | BSD-3, v0.19.0 (2026-03) |
| pytest-snapshot | | dormant since 2022 |
| ApprovalTests.Python | | Apache-2.0, v20.0.0 (2026-10) |

**Top 3 features**

1. **Categories of change, and CI that never writes.**
   - inline-snapshot sorts every change into one of four categories
     (https://15r10nk.github.io/inline-snapshot/latest/categories/):
     - create: a new snapshot;
     - fix: the value changed;
     - trim: unused parts are removed, which is only safe on a full run;
     - update: only the representation changed and the values are equal. Hidden by default.
   - Its interactive default is `create,review`, and its CI default is `disable`.
   - Jest's `--ci` never writes new snapshots, because "new snapshots automatically pass".
     Obsolete snapshots fail the run.
   - syrupy fails on unused snapshots by default. pytest-snapshot requires
     `--allow-snapshot-deletion`.
   - → blicket: adopt a taxonomy of changes. Changes of representation only (data type,
     column order, serializer version) are accepted automatically. Only changes of value need
     a reason. CI never accepts, and orphans are always visible.
2. **Per-column tolerances for tables (pytest-regressions).**
   - `dataframe_regression.check(df, tolerances={'col': dict(atol=…)}, default_tolerance=dict(atol=…, rtol=…))`.
   - `--force-regen` regenerates and still fails, while `--regen-all` regenerates and passes.
   - Its flaw: data is stored as CSV, rows are matched **by position**, and a change of shape
     is a hard error.
   - → blicket: `atol` and `rtol` per value column with a default. But rows are matched by
     dimension keys, never by position.
3. **Hash first, plus a summary report (pytest-mpl hybrid mode).**
   - A library of hashes in git decides pass or fail. The images live in a separate repository
     or at a URL, purely for humans.
   - Hash files are named after the library versions they were made with.
   - `--mpl-generate-summary=html,json` produces a searchable report showing baseline, result,
     diff and the size of the difference.
   - Docs: https://pytest-mpl.readthedocs.io/en/stable/hybrid_mode.html
   - → blicket: the build manifest carries a canonical content hash of each Blick table, so
     unchanged Blicks are detected without reading the tables. With tables in a store rather
     than in git, size is not a concern. Write a JSON summary next to the HTML.

**Also notable**
- inline-snapshot's `external()` names files by uuid, so they survive renames.
- ApprovalTests writes an approve-all script and log files, so bulk approval leaves a trace.

**Avoid**
- **Snapshot fatigue.** Jest's docs ask readers to "fight against the habit of regenerating
  snapshots". Thoughtworks Radar puts "snapshot testing only" on Hold
  (https://www.thoughtworks.com/radar/techniques/snapshot-testing-only).
- Pickle storage, which cannot be reviewed.
- Snapshot assertions scattered across tests with no overview.

**Overlap.** These tools cover the guard, one test at a time. A pytest plugin is a natural way
to hook blicket into CI, not a replacement for it.

---

## Part 3. Table diffing and data validation

### 9. datacompy (with SQLMesh table_diff and daff)

- **Links:** https://github.com/capitalone/datacompy, https://capitalone.github.io/datacompy/
- **Maturity:** Apache-2.0, about 660 stars, v1.1.0 (2026-09-30). Backends for pandas, Polars,
  Spark and Snowflake.

**Top 3 features**

1. **Comparison joined on keys, with a fixed report structure.**
   - You pass `join_columns`. The report covers:
     - a summary of both data frames;
     - columns in common and columns unique to each side;
     - rows found on only one side, and rows that differ;
     - per column: the number of unequal values, the maximum difference, and the difference
       in nulls;
     - sample rows.
   - Docs: https://capitalone.github.io/datacompy/pandas_usage.html
   - → blicket: this is the generic fallback diff, joined on the dimension columns. Consider
     using the Polars backend directly.
2. **Per-column tolerances.** `abs_tol` and `rel_tol` accept a float or a dict with a
   `"default"` entry.
   - → blicket: use the same configuration shape.
3. **Structured report data and exit codes.**
   - `build_report_data()` returns a `ReportData` object with `to_dict`, `render` and `save`.
   - The CLI exits 0 for a match, 1 for a difference and 2 for an error.
   - → blicket: write one JSON change record per Blick, which feeds the terminal summary,
     the overview and the pull-request comment. Use the same 0/1/2 exit codes.

**Related**
- **SQLMesh `table_diff`** (https://sqlmesh.readthedocs.io/en/stable/guides/tablediff/) runs a
  schema diff first, then an outer join on the key columns, and reports % match per column. It
  warns about null or duplicate keys.
- **daff** (https://github.com/paulfitz/daff, MIT, about 930 stars) defines the "highlighter"
  diff format for tables: `@@`, `+++`, `---`, `->`. It renders to HTML, works as a git diff
  driver, and has an R package.
- → blicket: use daff's format to show table diffs in the terminal and in the UI.

**Avoid.** Long reports with no ranking and no single number for the size of the change.

**Overlap.** None. A strong candidate dependency.

### 10. Recce (with Datafold and data-diff)

- **Links:** https://github.com/DataRecce/recce, https://docs.reccehq.com
- **Maturity:** Apache-2.0, about 480 stars, v1.69.1 (2026-10-22). Releases are nearly daily and
  a company backs it.

**What it is.** Recce compares a dbt development environment with production. The open-source
version is a local web app; Recce Cloud adds collaboration. It offers a lineage diff, data
diffs, and a checklist.

**Top 3 features**

1. **Lineage diff coloured by change.**
   - Added, removed, modified, and unchanged context are coloured differently. A filter shows
     "changed models (modified + downstream)", and icons flag changes in row count or schema.
   - → blicket: an overview coloured by change type and magnitude, with a "changed only"
     filter. Later, Blicks could be grouped by the inputs they share, which would be the
     deferred "grouping" idea expressed as lineage.
2. **Typed diffs.**
   - Value diff: primary keys are detected automatically from `unique` tests. It shows added
     and removed rows and % match per column.
   - Profile diff, top-K diff, and a histogram diff with base and current overlaid.
   - Docs: https://docs.reccehq.com/what-you-can-explore/data-diffing/
   - → blicket: a list of views for the generic fallback: value table, profile, overlay.
3. **A checklist with approval per check.** Recce Cloud can block a merge until every check is
   approved.
   - → blicket: accepted changes with their reasons *are* the checklist, kept in the store. A
     status check that fails on unreviewed changes is the equivalent of blocking the merge.

**Datafold and data-diff**
- data-diff was archived on 2024-05-17 (https://github.com/datafold/data-diff). Its fork
  reladiff (https://github.com/erezsh/reladiff) shows little activity. It finds differences by
  comparing hashes of ranges and splitting only the ranges that differ.
- Datafold Cloud posts a pull-request comment with a summary and a link to value-level detail.
  It requires unique keys: "null or duplicate primary keys will cause CI to fail".
- → blicket: compare hashes first. The pull-request comment links to the catalog built for
  that pull request. Dimension keys in Blick outputs must be unique.

**Avoid**
- Needing two live warehouse environments.
- Collaboration features that exist only in the cloud product.
- Recce's recent repositioning as an "AI review agent". Don't make review depend on summaries
  written by a language model.

**Overlap.** The closest in spirit: reviewing data changes at pull-request time. But it is tied
to dbt and warehouses and has no charts.

### 11. Evidently, Great Expectations and Pandera

| Tool | Link | Licence and maturity |
|---|---|---|
| Evidently | https://github.com/evidentlyai/evidently | Apache-2.0, about 8k stars, v0.7.23 (2026-09) |
| Great Expectations (GX Core) | https://github.com/fivetran/great_expectations | Apache-2.0, about 11.9k stars, 1.24.0 (2026-10) |
| Pandera | https://pandera.readthedocs.io | MIT, about 4.5k stars, v0.34.1 (2026-10) |

Fivetran became the steward of GX Core in May 2026, and GX Cloud went to FICO.

**Top 3 features**

1. **Change measured as a distance, and tests relative to a reference (Evidently).**
   - Each column gets a method chosen automatically. For large samples that is Wasserstein
     distance for numeric columns and Jensen-Shannon divergence for categorical ones, with a
     threshold of 0.1.
   - Tests are derived from the reference, for example "within ±10% of the reference".
     `is_critical=False` turns a failure into a warning.
   - Docs: https://docs.evidentlyai.com/metrics/explainer_drift
   - → blicket: Wasserstein or Jensen-Shannon as the magnitude for plot types that show
     distributions or shares. Default tolerances relative to the snapshot. A warn-or-fail
     setting per Blick.
2. **Output schemas (Pandera).**
   - `DataFrameModel` gives typed fields with checks.
   - Lazy validation collects every failure instead of stopping at the first.
   - `infer_schema()` drafts a schema to be edited.
   - → blicket: declare each Blick's output schema: which columns are dimensions and which
     are values, with units and data types. `controls()` and the diff need exactly this.
     `blicket init` could infer it from the first accepted run, and schema changes then
     become their own change type.
3. **Severity and static docs (GX).**
   - Data Docs, a static site, is rebuilt after each checkpoint.
   - Severity levels are critical, warning and info, and actions fire based on them.
   - → blicket: a severity per Blick decides whether CI fails or warns. A run hook rebuilds
     the site.

**Avoid**
- Drift tests based on p-values. They are meaningless for deterministic model outputs.
- GX's configuration sprawl, its API churn from 0.x to 1.0, and its turbulent ownership.
- Making Pandera a hard dependency, since many of its features work only with pandas.

**Overlap.** None.

---

## Part 4. Experiment tracking, pipelines and benchmarks

### 12. DVC plots

- **Links:** https://doc.dvc.org/user-guide/experiment-management/visualizing-plots, https://github.com/treeverse/dvc
- **Maturity:** Apache-2.0, about 15.9k stars, 3.67.1 (2026-03-31). lakeFS acquired DVC in
  November 2025.
- **CML**, which posts reports to pull requests, has about 4.2k stars. Its last release was in
  2024-10, and its default image server no longer accepts uploads.

**Top 3 features**

1. **Templates with placeholders.**
   - Templates are Vega-Lite files with `<DVC_METRIC_DATA>`, `<DVC_METRIC_X>`/`_Y` and
     `<DVC_METRIC_COLOR>` placeholders. DVC adds a `rev` field to every row.
   - Docs: https://doc.dvc.org/command-reference/plots/templates
   - → blicket: a plot type is a spec with parameters, whose channel slots are filled from
     the Blick's mapping. Adding a reserved `version` column (baseline or current) gives an
     overlay comparison for free for any Vega-Lite plot type.
2. **Plots as config, diffed against the last commit.**
   - `plots:` entries in `dvc.yaml` name x, y and a template.
   - `dvc plots diff` overlays any number of revisions. With no revision given, it compares
     the workspace with HEAD.
   - → blicket: workspace against the last revision is our default of current build against
     the resolved baseline.
3. **`dvc metrics diff --md` plus a single PR comment (CML).**
   - The table shows only changed metrics, with old, new and change, as Markdown or JSON.
   - `cml comment update` edits one pull-request comment in place.
   - → blicket: CI writes a Markdown table of changed Blicks sorted by magnitude and updates
     one comment that stays in place.

**Avoid**
- `plots diff` "does not calculate numeric differences". It only overlays and cannot rank.
- It needs old revisions checked out.
- All data is inlined into the HTML.
- It assumes flat x/y numeric series.
- The VS Code view is limited to 7 experiments.
- Relying on third-party image hosting.

**Overlap.** Partial: conceptually the closest tool from the machine-learning world (plots as
config, git revisions, static HTML). It has no magnitude, review, controls, or stored baseline.

### 13. Weights & Biases

- **Links:** https://wandb.ai, docs at https://docs.coreweave.com (CoreWeave acquired W&B in May 2025)
- **Maturity:** the SDK is MIT, about 11.3k stars, v0.31.0 (2026-10). The server and UI are
  proprietary.

**Top 3 features**

1. **Custom chart presets.**
   - A preset is a Vega spec with `${field:name}` placeholders. These become "chart fields"
     dropdowns bound to table columns.
   - From code: `wandb.plot_table(vega_spec_name, table, fields={...})`.
   - Docs: https://docs.coreweave.com/guides/app/features/custom-charts/
   - → blicket: almost exactly our plot type plus channel mapping. Plot types should declare
     their channel slots so the UI and validation can inspect them.
2. **Baseline run.**
   - One run is the baseline. The runs table shows deltas against it, coloured by whether
     higher or lower is better for that metric. Line plots draw the baseline dashed.
   - Several panel types ignore the baseline.
   - Docs: https://docs.coreweave.com/models/runs/compare-runs
   - → blicket: the default comparison for line types draws the snapshot as a muted dashed
     series. Optional direction metadata per Blick lets the overview say better or worse, not
     just bigger or smaller. Make comparison universal through the plot type contract.
3. **Table comparison.**
   - Two versions of a table are merged on a join key, colour-coded 0 and 1, with filters
     across both and histograms of numeric differences. The docs warn that a bad join key makes
     the result illegible.
   - → blicket: the generic diff joins on the dimension columns, which are known from the
     schema, so nobody has to pick a key. Show a histogram of relative changes.

**Avoid**
- SaaS lock-in.
- Comparison views that lose their state.
- A limit of 20 pinned runs.
- A baseline that only some panels support.

**Overlap.** None.

### 14. MLflow

- **Links:** https://mlflow.org
- **Maturity:** Apache-2.0, about 28.5k stars, v3.17.2 (2026-10-21), monthly releases.

**Top 3 features**

1. **Validation against a baseline with thresholds.**
   - `MetricThreshold(threshold, min_absolute_change, min_relative_change, greater_is_better)`.
   - All failures are collected into one exception, and a baseline of zero is handled as a
     special case.
   - → blicket: a tolerance object `{abs, rel, direction}`. Report all violations at once.
     Handle a zero baseline explicitly.
2. **Difference view.**
   - Charts have "Show change from baseline" and "Show differences only" toggles.
   - → blicket: a per-Blick toggle between absolute values and change from the snapshot, and
     a "changed only" filter on the overview.
3. **Review queues** (3.14, experimental).
   - Items are pending, complete or declined, shared across reviewers.
   - Answers follow reusable label schemas (pass or fail, categories, numbers, free text) and
     are attributed to the reviewer.
   - Docs: https://mlflow.org/docs/latest/genai/assessments/review-queues
   - → blicket: review states with reviewer and reason. A small schema for reasons (a category
     plus free text) makes reasons searchable later.

**Avoid**
- A tracking server and database.
- A focus on scalar metrics.
- The product's drift towards tracing language models, a cautionary tale of scope creep.

**Overlap.** None.

### 15. asv and benchmark trackers (Bencher, CodSpeed)

| Tool | Link | Licence and maturity |
|---|---|---|
| asv | https://asv.readthedocs.io | BSD-3, about 1k stars, v0.6.6 (2026-06); used by numpy, scipy and astropy |
| Bencher | https://bencher.dev | Apache-2.0 or MIT, with proprietary "plus" parts |
| CodSpeed | https://codspeed.io | SaaS with Apache-2.0 runners |
| github-action-benchmark | | MIT, about 1.3k stars |

**Top 3 features**

1. **Parameter grid, static site and a regression table (asv).**
   - `params` and `param_names` define a grid of benchmark parameters.
   - `asv publish` builds a static site whose Regressions tab is filled by step detection and
     sortable by factor.
   - "Ignore" buttons store their state in localStorage. The page then generates an
     `asv.conf.json` snippet (`regressions_first_commits`) to paste in and commit
     (`asv/www/regressions.js`).
   - Docs: https://asv.readthedocs.io/en/latest/step_detection.html
   - → blicket: a pattern for connecting a static site to an acknowledgement: the site collects
     decisions and exports them. For the review-flow design this is one option for accepting
     from a static catalog; the chosen direction is a UI tied to the pull request. The
     parameter grid also suggests computing magnitude per slice of a Blick and aggregating.
2. **Bulk acknowledge with merge blocking (CodSpeed).**
   - Each benchmark has "Acknowledge regression". Filter with `is:regression`, tick boxes, then
     "Acknowledge selected".
   - The status check blocks the merge until every regression is fixed or acknowledged. Only
     admins may acknowledge.
   - Impact is the relative change, against a default threshold of 10% that can be overridden
     per benchmark. The commit's impact is the geometric mean of the changes above the
     threshold.
   - Docs: https://codspeed.io/docs/features/performance-checks
   - → blicket: the filter, select and accept UX, plus a headline aggregate magnitude. The
     acknowledgement carries a reason and lives in a store the project controls, not in a
     vendor's database.
3. **Threshold models and CI reporting (Bencher, asv compare).**
   - Bencher's thresholds are a test plus boundaries: static, percentage, z-score, t-test or
     IQR. Branches inherit thresholds from their starting point.
   - `--ci-only-on-alert` comments only when something changed.
   - `asv compare` offers `--split`, `--only-changed` and `--sort ratio`.
   - → blicket: pluggable tolerance models, static and percentage first, statistical ones only
     for stochastic models. The terminal summary splits Blicks into changed, unchanged, new
     and removed, sorted by magnitude. Comment only when there are changes.

**Avoid**
- Scalar metrics only.
- Statistics for outputs that are deterministic anyway. CodSpeed's lesson is to make the
  measurement itself deterministic; for blicket that means sorted output and fixed float
  formatting.
- Acknowledgements kept only in localStorage, or only on a server the project does not control.

**Overlap.** None. asv is the closest structural analogue: a parameter grid, a static site,
ranked regressions, and an ignore list committed to config.

### 16. Dagster asset catalog

- **Links:** https://dagster.io, https://github.com/dagster-io/dagster
- **Maturity:** Apache-2.0, about 16.3k stars, 1.13.26 (2026-10-09).

**Top 3 features**

1. **Code version, data version and "unsynced".**
   - An asset becomes unsynced when its code version, its dependencies, or a parent's data
     version changes.
   - Users can set data versions themselves, so cosmetic refactors don't cascade.
   - Docs: https://dagster.io/docs/guides/build/assets/asset-versioning-and-caching
   - → blicket: the change report separates "Blick definition changed" from "input data
     changed". An explicit Blick ID keeps identity across refactors.
2. **Change tracking for branch deployments** (paid Dagster+).
   - It marks new assets and changed code versions, dependencies and metadata relative to a
     base deployment.
   - → blicket: the pull-request report lists changes to definitions (new or removed Blicks,
     changed mapping or plot type) separately from changes to values.
3. **Asset checks with severity and blocking.**
   - Severity is WARN or ERROR, with `blocking=True`.
   - Ready-made checks include `build_column_schema_change_checks`, which compares columns and
     types against the previous run.
   - Numeric metadata is plotted over time.
   - → blicket: schema changes are their own change type. Warn versus error maps onto the CI
     policy. A short history of each Blick's magnitude across accepted commits shows how
     often it moves.

**Avoid**
- A heavy orchestrator with a background daemon.
- Change review behind a paywall.
- History kept in an event database that only the orchestrator can read.

**Overlap.** None.

---

## Part 5. IAM, energy and MFA tooling

### 17. REMIND compareScenarios (piamPlotComparison, mip, remind2)

- **Links:** https://github.com/pik-piam/piamPlotComparison, vignette at
  https://pik-piam.r-universe.dev/piamPlotComparison/doc/compareScenarios.html, sections at
  https://github.com/pik-piam/remind2/tree/HEAD/inst/compareScenarios, profiles at
  https://github.com/remindmodel/remind/blob/HEAD/scripts/cs2/profiles.json
- **Maturity:** piamPlotComparison 0.2.0 (2026-10-07, LGPL-3), mip 0.157.0 (BSD-2).
- **History:** version 1 lived in mip. `remind2::compareScenarios2` came next and is now a
  deprecated wrapper around `piamPlotComparison::compareScenarios(projectLibrary="remind2")`.

**What it is.**
- `cs_main.Rmd` reads the scenario `.mif` files and one historical `.mif` into one long table
  (`model, scenario, region, variable, unit, period, value, varplus`).
- It then includes section files `cs_NN_name.Rmd` from a project package; remind2 has 11.
- Output is PDF, HTML, or a copy of the Rmd files.

**Top 3 features**

1. **One chunk per figure, with a path-like label.**
   - Example: chunk `{r 03_emissions/GHG total}` calls `showLinePlots(data, "Emi|GHG", histVars=...)`.
   - Sections are selected by number, and `userSectionPath` adds extra ones.
   - → blicket: stable hierarchical Blick IDs (`section/Blick`), separate from function
     names. The existing chunks are a migration corpus: an importer could turn each
     `show*Plots` call into Blick code, with the variable filter as the transformation and
     line, area or bar as the plot type.
2. **Profiles and defaults.**
   - There are 20 named profiles (H12, EU27, …). Each sets region subsets, year sets
     (`yearsScen`, `yearsHist`, `yearsBarPlot`) and a main region.
   - `showLinePlots` draws the main region large plus small multiples of the other regions, and
     overlays historical sources as extra "models".
   - → blicket: control defaults set for the whole catalog, as profiles. "Main value large
     plus small multiples" as the default layout for the region dimension. The historical
     overlay belongs inside the line plot type.
3. **mip::plotstyle.**
   - A CSV of about 810 entries maps each region or variable to a label, colour, marker and
     line style. Lookup works by regex, and unknown entities get generated colours.
   - → blicket: a project-wide style registry keyed by dimension value, so colours stay the
     same across Blicks and between baseline and current.

**Also notable**
- `calcTimeSeriesStats` computes custom statistics such as "Net 0 Period".
- `validationConfig` draws piamValidation threshold bands on plots.

**Avoid**
- Figure code, layout and narrative mixed in one Rmd file.
- Hidden global state through `options()`.
- Changing a section means reinstalling an R package.
- Free-text chunk labels serve as IDs.
- No diff at all: the result is the thousand-page PDF.

**Overlap.** None. It is the thing blicket replaces for REMIND.

### 18. piamValidation

- **Links:** https://github.com/pik-piam/piamValidation, vignette at
  https://pik-piam.r-universe.dev/piamValidation/doc/validateScenarios.html
- **Maturity:** 0.19.0 (2026-10-07), LGPL-3.

**What it is.** Validation rules are rows in a CSV. Each row sets:
- a metric: relative, difference, absolute or growth rate;
- wildcard filters on variable, model, scenario, region and period (`*` matches one level of
  the variable name, `**` any number);
- yellow and red thresholds;
- a reference, which can be another model, a scenario such as `historical`, another period, or
  a range or mean over several sources;
- a `critical` flag.

Results are shown as traffic lights and HTML heatmaps.

**Top 3 features**

1. **A rule table with wildcards and a critical flag.** `validationPass()` fails only on
   critical rules.
   - → blicket: a model for configuring tolerance and severity per Blick: tabular, reviewable
     in git, and addressable by wildcards on Blick paths.
2. **Reference data as a pseudo-scenario.** `scenario="historical"`, `model=<source>`, with
   ranges over several sources.
   - → blicket: the likely answer to the deferred reference-data decision for IAMC. Reference
     data is a dimension value with a role: plot types style it differently, and it is excluded
     from the magnitude.
3. **A heatmap overview** of variable × region × period.
   - → blicket: drilling into a Blick from the overview shows a heatmap of where in its own
     dimensions the change sits.

**Related evidence.** `validationReport_REMIND_compare_versions.Rmd` compares REMIND 3.5.2 with
3.5.1 by renaming the model column, with cluster paths written into the code. Version
comparison is done ad hoc today.

**Avoid**
- A complex configuration grammar.
- Very large reports.
- Thresholds are absolute expectations, not "change since the last accept".

**Overlap.** Complementary. It is the deferred "checks". blicket should display its results
rather than reimplement it.

### 19. pyam and the IIASA Scenario Explorer

- **Links:** pyam at https://github.com/IAMconsortium/pyam and https://pyam-iamc.readthedocs.io;
  Scenario Explorer at https://docs.ece.iiasa.ac.at/scenario-databases.html
- **Maturity:** pyam is Apache-2.0, about 290 stars, v4.0.0 (2026-10-15). The Scenario Explorer
  runs on ixmp4 (v0.17.0, MIT, 2026-10-16); the UI's source is not public.

**Top 3 features**

1. **Channels named by column.**
   - `df.plot.line(color="scenario", linestyle="model", marker=...)`, plus stack, bar, box,
     pie, scatter and sankey.
   - A global `run_control()` YAML sets colours, markers and order.
   - Docs: https://pyam-iamc.readthedocs.io/en/stable/api/plotting.html
   - → blicket: IAM users already think in "dimension → channel". Reuse the style-file idea.
2. **`pyam.compare(left, right, drop_close=True, **isclose_kw)`.**
   - It joins on the full index, keeping rows from both sides, and returns the rows that are
     not close, with left and right values side by side. Values present on only one side show
     up as NaN.
   - → blicket: a ready generic diff for Blick tables shaped like IAMC data, with magnitude
     and ranking added on top. `IamDataFrame` is the obvious IAMC adapter, converting wide
     `.mif` or xlsx files to long format.
3. **Versioned runs with messages (ixmp4).**
   - Each (model, scenario) pair has versions, one of them the default.
   - `run.transact("message")` creates a checkpoint with a message.
   - The Explorer has workspaces (shared boards of plots) and validates data at upload.
   - → blicket: an accepted snapshot is like the default version, and the accept reason is
     like the checkpoint message. Validate structure before diffing, so a renamed variable does
     not show up as a huge change.

**Avoid**
- pyam's plotting is static matplotlib only.
- `plot.sankey` raises an error unless every other dimension has a single value. A Sankey plot
  type must therefore filter or sum its unbound dimensions, never split them.
- The Scenario Explorer needs a server, database and authentication, and its charts are
  configured in the GUI. It has no diff between versions.

**Overlap.** None. pyam is the best IAMC adapter and diff building block.

### 20. nomenclature (IAMC)

- **Links:** https://github.com/IAMconsortium/nomenclature, https://nomenclature-iamc.readthedocs.io,
  https://github.com/IAMconsortium/common-definitions
- **Maturity:** Apache-2.0, v0.32.1 (2026-10-21).

**What it is.** YAML codelists under `definitions/<dimension>/` plus region mappings. Each
variable has attributes such as unit, aggregation rules and weight. Command-line validators
check projects and scenarios. A data validator supports tolerances and warning levels.

**Top 3 features**

1. **Definitions in git, validated in CI without data.** common-definitions runs
   `nomenclature validate-project .` in GitHub Actions.
   - → blicket: `blicket validate` checks Blick definitions without a run. This is a cheap
     pull-request check even when the model cannot run in CI.
2. **Tag templates.** `Variable|{Fuel}` is expanded from tag files.
   - → blicket: declare a family of Blicks (one per fuel or sector) without copy-paste. This
     addresses definitions drifting and being duplicated.
3. **Graded warning levels** (error, high, medium, low), and a unit attribute per variable.
   - → blicket: severity levels for the CI policy, and default tolerances and axis labels
     keyed by unit.

**Related.** scenariocompass publishes evaluation criteria with versions, and IAM COMPACT has a
Streamlit app for checking scenarios.

**Avoid.** A heavy dependency stack; use it only as an optional adapter.

**Overlap.** None.

### 21. PyPSA: pypsa-validator and the statistics API

- **Links:** https://github.com/PyPSA/pypsa-validator (archived, active August 2024 to March
  2025), https://github.com/PyPSA/PyPSA (MIT, about 2.2k stars)

**What it was.**
- pypsa-validator ran PyPSA-Eur on main and on the feature branch, on a self-hosted runner.
- It posted one pull-request comment and edited it on each commit.
- The comment held a config diff, plots side by side, and IAMC variables ranked by NRMSE
  (normalised by min and max) and Pearson correlation.
- It used a threshold of 0.1 and a noise floor that dropped values below 1e-3 on both sides.
- New and removed variables were listed separately.

**Top 3 features**

1. **Variables ranked by a normalised error with a noise floor.**
   - → blicket: a tested default for the generic magnitude.
2. **One PR comment, edited on each commit, with collapsible details.**
   - → blicket: the format for the CI report.
3. **Config diff shown next to the result changes.**
   - → blicket: show changes to inputs and config next to the Blick changes during review,
     to answer "what did I change that caused this".

**PyPSA core**
- `n.statistics.<metric>.plot.<type>()`: "any plot type can be used with any metric", and
  each metric has a default plot type.
- `NetworkCollection` turns runs into an index level.
- Docs: https://github.com/PyPSA/PyPSA/blob/HEAD/docs/user-guide/plotting/charts.md
- → blicket: keeping metric and plot type separate is the same as transformation plus plot
  type. Treating runs as a dimension is the cheap route to the deferred run-against-run
  comparison.

**Avoid**
- Rerunning main on every pull request was costly, a likely reason it was archived and an
  argument for stored snapshots.
- Hard-coded thresholds.
- Hiding everything below the threshold.
- PNG images only.

**Overlap.** A project-specific, partial version of blicket's second job (automated guard).
Archived.

### 22. flodym, ODYM and floweaver (MFA)

| Tool | Link | Licence and maturity |
|---|---|---|
| flodym | https://github.com/pik-piam/flodym, https://flodym.readthedocs.io, JOSS paper https://doi.org/10.21105/joss.10105 | MIT, 1.1.0 (2026-10-09) |
| ODYM | https://github.com/IndEcol/ODYM | Superseded; not on PyPI, last push 2025-09 |
| floweaver | https://github.com/ricklupton/floweaver | MIT, about 464 stars, last PyPI release 2.0.1 (2022-12), occasional commits |

**Top 3 features**

1. **Arrays that know their dimensions, with explicit binding (flodym).**
   - Building blocks: `Dimension(name, letter, items)`, `FlodymArray`, flows between processes,
     and stocks.
   - `PlotlyArrayPlotter` requires every dimension to be bound exactly once, to
     `intra_line_dim`, `linecolor_dim` or `subplot_dim`.
   - → blicket: the same idea, except that unbound dimensions become controls instead of
     errors. Support a short letter plus a long name per dimension.
2. **Sankey reduction (flodym).**
   - `PlotlySankeyPlotter(mfa, slice_dict, flow_color_dict, exclude_processes=["sysenv"])`:
     `slice_dict` picks values, and every other dimension is summed. Flows are coloured by one
     dimension.
   - → blicket: a Sankey Blick outputs one edge table: `source, target, flow, <shared dims>, value`.
     Each control is "pick one value or show the total". Colour is a channel. The system
     boundary is hidden by convention.
3. **A declarative Sankey definition with stable ordering (floweaver).**
   - A flow table plus a `SankeyDefinition` built from process groups, waypoints, bundles, an
     ordering, and partitions that group minor values into "other".
   - Docs: https://floweaver.readthedocs.io/en/latest/tutorials/quickstart.html
   - → blicket: the right shape for a Sankey channel mapping. A fixed ordering keeps baseline
     and current aligned, and grouping minor flows makes the diff readable.

**Also notable.** flodym's `check_mass_balance(tolerance)` is a candidate pluggable check.

**Avoid**
- flodym's plotting needs the live `MFASystem` object. The remind-mfa adapter loads the
  pickled system and lets Blicks build tables from it; the plotting code itself is not reused.
- floweaver is tied to Jupyter widgets and maintained sporadically, so use it as inspiration
  rather than a dependency.

**Overlap.** None.

### 23. remind-mfa `run_comparison` (in-house predecessor)

- **Link:** https://github.com/pik-piam/remind-mfa/blob/HEAD/remind_mfa/common/run_comparison.py
- Added in commit d69b800c on 2026-10-22: "add run comparison notebooks and PR baseline
  comparison to CI (#252)".

**What it does.**
- Loads several runs (pickled flodym systems plus IAMC exports).
- Reruns the model's own plotting code for each run.
- Merges the resulting plotly figures into overlay and difference figures by matching panels
  and traces.
- Also detects Sankey figures.

**Top 3 features**

1. **`peak_change`.** The largest absolute difference divided by the largest reference value,
   signed and in %, with a noise floor of 1e-9.
   - → blicket: a good default magnitude for line and area plot types. It is robust against
     years where the reference is close to zero.
2. **A change heatmap by region**, clipped at 50%.
   - → blicket: a drill-down view.
3. **`ChangeVerdict.as_markdown()`** for the pull-request comment.
   - → blicket: the CI report.

**Lesson.** Comparing at the level of plotly figures, by matching traces, is fragile. blicket's
plan to snapshot the transformed table is more robust. This module is a working prototype of
jobs 1 and 2 for one model, and the most direct evidence that the need is real.

---

## Part 6. Reports and notebooks

### 24. Quarto

- **Links:** https://quarto.org
- **Maturity:** MIT, about 6.1k stars, v1.11.6 (2026-10-14).

**Top 3 features**

1. **Freeze.**
   - With `freeze: auto`, a document is re-run only when its source changes.
   - The `_freeze/` folder is committed.
   - The docs warn that frozen results do not notice changed input data
     (https://quarto.org/docs/projects/code-execution.html).
   - → blicket: keeping outputs beside the code is accepted practice in this community;
     blicket keeps them in a store instead. Any cache key must include hashes of the run's
     data, exactly where `_freeze` falls short.
2. **Embedding outputs across documents.**
   - `{{< embed notebook.ipynb#fig-id >}}`, the backbone of Quarto Manuscripts
     (https://quarto.org/docs/authoring/notebook-embed.html).
   - → blicket: a Quarto shortcode such as `{{< blicket blick-id >}}` would let papers and
     supplements embed accepted Blicks, which makes the communication job cheap.
3. **Listings and Observable JS.**
   - Listings build catalog pages as grids or tables, with sorting and filtering.
   - `ojs_define()` hands data to Observable JS in the browser, where it can be filtered
     reactively without a server.
   - Docs: https://quarto.org/docs/websites/website-listings.html
   - → blicket: "small table plus controls in the browser" already works inside Quarto. The
     catalog could even be emitted as a Quarto site, though the core should not depend on
     Pandoc.

**Avoid**
- Quarto is built around documents: it has no Blick identity, baseline or diff.
- Rendering a thousand figures through Pandoc is slow.

**Overlap.** None. An integration target.

### 25. Observable Framework

- **Links:** https://observablehq.com/framework/, https://github.com/observablehq/framework
- **Maturity:** ISC, about 3.7k stars, v1.13.4 (2026-03-02). About 30 commits since November
  2024, the last in May 2026: in maintenance mode.

**Top 3 features**

1. **Data loaders in any language, run at build time.**
   - `data.csv.py` produces `data.csv`. Outputs are cached, and only they reach the browser.
     The loader reruns in preview when its source changes.
   - Docs: https://github.com/observablehq/framework/blob/main/docs/data-loaders.md
   - → blicket: proof of "transformations at build time, the browser never sees raw data".
     "Any executable that writes a tidy table" is a cheap, language-agnostic protocol for
     Blicks written in R and other languages, later.
2. **Parameterised routes**: a `[param].md` file plus `dynamicPaths` generates many pages.
   - → blicket: one page template per plot type, instantiated for each Blick.
3. **Dev server with live reload, plus a static build.**
   - → blicket: the same two-mode architecture blicket assumes.

**Avoid**
- The cache is invalidated by the loader file's modification time, not by input data.
- A loader that exits successfully with bad output is cached silently.
- Depending on a project in maintenance mode.

**Overlap.** None. Borrow its patterns rather than build on it.

### 26. Snakemake reports

- **Links:** https://snakemake.readthedocs.io/en/stable/snakefiles/reporting.html
- **Maturity:** MIT, about 2.9k stars, v9.27.1 (2026-10-21).

**Top 3 features**

1. **Report items are declared where they are produced.**
   - `report("fig.svg", caption=..., category=..., subcategory="{model}", labels={...})`.
   - → blicket: the manifest sits next to the Blick code, and the catalog is grouped by
     declared metadata.
2. **Labels become a table, and two-valued labels become toggles.**
   - → blicket: a precedent for dimensions becoming controls. Choose the control by the number
     of values: a toggle for two, buttons for a few, a dropdown for many.
3. **Provenance.** Reports include runtime statistics and the workflow graph, and captions link
   to rules.
   - → blicket: each Blick page shows its transformation and a link to its source, the inputs
     it read, the run id, and the code hash.

**Avoid**
- A static dump of pre-rendered files with no baseline.
- Controls that only exist by listing every file.

**Overlap.** None. Snakemake could host blicket as a rule that runs `blicket build` after the
model run.

---

## Part 7. Plot vocabularies

### 27. HoloViews and hvPlot

- **Links:** https://holoviews.org, https://hvplot.holoviz.org
- **Maturity:** BSD-3. HoloViews has about 2.9k stars, v1.23.2 (2026-08). hvPlot has about 1.4k
  stars, v0.12.2 (2025-12).

This is the strongest prior art for blicket's controls rule.

**Top 3 features**

1. **Every key dimension is plotted, aggregated, or becomes a widget.**
   - The docs: if a dimension "isn't somehow plotted or aggregated over, then HoloViews has to
     leave choosing a value for it to the user, hence the selection widget".
   - Numeric dimensions get sliders and categorical ones get dropdowns.
   - Dimension objects carry a label, unit, values and default.
   - Docs: https://github.com/holoviz/holoviews/blob/main/examples/user_guide/05-Dimensioned_Containers.ipynb
   - → blicket: the core rule already works in practice. Adopt the three-way choice (channel,
     aggregate, control), choose the widget by data type and number of values, and give
     dimensions metadata (label, unit, default, order).
2. **`by`, `groupby`, `row`, `col`.**
   - In hvPlot, `by=` overlays groups, `groupby=` creates widgets, and `row=`/`col=` create
     facets. `widgets={...}` overrides the choice.
   - → blicket: exactly "filter to one value, or split by the dimension". Borrow the names.
3. **Axes that are fixed or recomputed per frame (`framewise`).**
   - → blicket: each plot type defines whether axes stay fixed across control states and
     between baseline and current. The default is shared, fixed axes, so changes stay visible.

**Avoid**
- Static export pre-renders every combination; the docs warn that 100 values on 4 dimensions
  means 100 million elements.
- Panel's static embedding is capped at 1,000 states and three values per slider
  (https://panel.holoviz.org/how_to/export/embedding.html).
- blicket should ship the small table and filter it in the browser.
- Too many container types.

**Overlap.** None for baselines or review.

### 28. Vega-Lite and Altair

- **Links:** https://vega.github.io/vega-lite/, https://altair-viz.github.io
- **Maturity:** BSD-3. Vega-Lite has about 5.5k stars, v6.5.0 (2026-10-08). Altair has about
  10.5k stars, v6.3.0 (2026-09). vl-convert is at v1.9.0.

**Top 3 features**

1. **A complete, documented channel vocabulary in JSON.**
   - Channels: x, y, x2, y2, xOffset, color, fill, stroke, opacity, shape, size, strokeDash,
     text, tooltip, detail, key, order, facet, row, column.
   - Views combine with `layer`, `facet`, `concat` and `repeat`, and `resolve` decides whether
     scales are shared.
   - Docs: https://vega.github.io/vega-lite/docs/encoding.html
   - → blicket: borrow these channel names, with aliases (`colour`, `linetype`, `line_dash`,
     `group`). Overlay is `layer`, side by side is `facet` with shared scales, and difference
     is a calculated field on the joined table.
2. **Controls in a static page.**
   - Parameters bound to dropdowns, sliders, radio buttons and checkboxes drive filters
     (https://vega.github.io/vega-lite/docs/bind.html).
   - → blicket: one small table and one spec cover every control state in the browser. Better
     still, blicket draws its own controls and sets state through `view.signal()`, which keeps
     the contract independent of the backend.
3. **Static rendering without a browser (vl-convert).**
   - It embeds a JavaScript engine, so it needs no Chrome or Node, and produces SVG, PNG or
     PDF (https://github.com/vega/vl-convert).
   - → blicket: CI renders thumbnails and the images in the change report without Chrome. The
     spec is language-neutral JSON, so R can emit the same thing.

**Avoid**
- Snapshotting the spec: Altair inlines data under names derived from content hashes, so spec
  diffs are noisy.
- Plain built-in widgets (single select only).
- There is no Sankey.
- Altair's default limit of 5,000 rows.
- Vega cannot read Parquet, so the viewer parses the Parquet tables itself (hyparquet) and
  hands Vega plain arrays.

**Overlap.** None. The recommended renderer for the built-in plot types.

### 29. Observable Plot (and its test harness)

- **Links:** https://observablehq.com/plot/
- **Maturity:** ISC, about 5.4k stars, v0.6.17 (2025-02-14). Still before 1.0, with slow
  releases.

**Top 3 features**

1. **The difference mark (`differenceY`).**
   - It draws a metric line against a comparison line and shades gains and losses in different
     colours (https://github.com/observablehq/plot/blob/main/docs/marks/difference.md).
   - → blicket: the right default comparison view for line and area plot types: current as
     the line, snapshot as the comparison, shaded change.
2. **Facets (`fx`/`fy`).** A mark with different data is repeated on every facet.
   - → blicket: "split by dimension" becomes a facet, and reference data becomes a mark
     repeated on every panel.
3. **Its test harness is a de facto catalog of charts.**
   - Each chart is an exported async function registered in `test/plots/index.ts`.
   - About 830 SVG and HTML snapshots live in git under `test/output`.
   - `pnpm dev` opens a browser where a dropdown and the arrow keys cycle through charts, with
     hot reload.
   - Changed outputs are written next to the originals with a `-changed` suffix. CI fails if
     new snapshots were not committed. Seeded randomness keeps outputs deterministic.
   - Docs: https://github.com/observablehq/plot/blob/main/CONTRIBUTING.md
   - → blicket: validates "Blick = function + snapshot + development browser". What it
     lacks: controls, a diff on the data, ranking, and bulk accept with a reason.

**Avoid**
- Plot specs are JavaScript containing functions, not JSON, so they are neither
  language-neutral nor diffable.
- No widgets and no Sankey.
- Treat it as a design reference rather than a core dependency.

**Overlap.** None.

---

## Part 8. Further projects in brief

Each entry gives three features (fewer where only one idea transfers) and what to avoid.

**Hamilton UI** (Apache Hamilton; https://hamilton.apache.org/hamilton-ui/ui/; Apache-2.0, about 2.6k stars, in ASF incubation since 2025-04)
1. Functions are nodes, and inputs are declared by parameter name.
   → blicket: transformations declare the raw inputs they read, which enables caching, grouping
   by shared inputs, and rebuilds that follow dependencies.
2. The cache key is node name + code version (a hash of the source without comments) + data
   version of the inputs. Its documented blind spot: nested function calls are not versioned.
   → blicket: hash imported helper functions too, or fall back to a conservative rebuild.
3. Data summaries per node, compared across runs.
   → blicket: a compact profile of each Blick's table (rows, nulls, value ranges) next to the
   chart.

Avoid: the UI needs a server and database, and it requires adopting a pipeline framework.

**Kedro-Viz** (https://github.com/kedro-org/kedro-viz; Apache-2.0, about 760 stars, v12.5.0)
1. Preview protocol: datasets return typed previews (table, Plotly, image, JSON, HTML).
   → blicket: `render()` returns one of a few typed outputs, so built-in and custom plot types
   share one container.
2. `kedro viz build` makes a static site, and `--autoreload` gives a dev mode. The static site
   breaks when opened from `file://`.
   → blicket: the static build works from any plain file server and from `blicket serve <dir>`;
   `file://` blocks `fetch`, so that is not promised.
3. A workflow view of node status and tracebacks.
   → blicket: build status per Blick, so one broken Blick does not break the build.

Avoid: experiment tracking was bolted on and then removed in 11.0
(https://kedro.org/blog/deprecate-experiment-tracking-kedro-viz). Don't add run tracking.

**Evidence.dev** (https://docs.evidence.dev; MIT, about 7k stars; in 2026 it pivoted from a static build to "Evidence Core" with queries run on a server)
1. Declarative chart components, including a Sankey, plus an ECharts escape hatch.
   → blicket: a reference list for the built-in vocabulary, and a model for escape hatches.
2. Inputs filled from the distinct values of a column. The migration guide replaces "one page
   per value" with "one page driven by an input".
   → blicket: confirms one Blick with controls over one page per value.
3. Delta and "big value with comparison" components.
   → blicket: headline deltas on the overview cards.

Avoid: the legacy version topped out around 2 million rows. The pivot shows why the browser
should never query raw data.

**Rill** (https://github.com/rilldata/rill; Apache-2.0, about 3k stars, v0.90.7)
1. Leaderboards can be sorted by absolute or percent change.
   → blicket: within a Blick, rank which regions or variables moved most.
2. Dashboards are generated from declared dimensions and measures.
   → blicket: when the schema declares dimensions and values, controls need no authoring.
3. The full view state, including the comparison, lives in the URL.
   → blicket: links from a PR comment open an exact view, which also covers "saved presets"
   cheaply.

Avoid: it needs a server and is built around time-series aggregation.

**Vizro** (https://github.com/mckinsey/vizro; Apache-2.0, about 3.8k stars, 1.0.0 on 2026-10-20)
1. The filter type is inferred from the column type: a multi-select for categories, a range
   slider for numbers, a date picker for dates, a switch for booleans.
   → blicket: the default table that maps column type to control.
2. `@capture("graph")`: filters are applied *before* the chart function is called.
   → blicket: the framework applies control state, so `render()` never filters.
3. Pydantic models with an exported JSON schema.
   → blicket: validate the manifest against a published schema, which also helps coding agents.

Avoid: it needs a Dash server and has no static export. It has a dashboard-builder mindset.

**marimo** (https://github.com/marimo-team/marimo; Apache-2.0, about 23k stars, v0.25.2)
1. Session outputs are committed under `__marimo__/session/`.
   → blicket: a precedent for keeping results beside the code. blicket keeps them in a store
   as immutable builds; marimo's session outputs are not diffable data.
2. `pytest notebook.py` runs tests inside a notebook.
   → blicket: a pytest plugin that turns each Blick into a test item.
3. Reactive re-execution and a WebAssembly export.
   → blicket: hot reload re-runs only the dependent Blicks. WebAssembly is an escape hatch if
   static controls prove too limiting.

Avoid: it is shaped like a notebook, not a catalog.

**Panel and Streamlit** (Panel BSD-3, about 5.8k stars, v1.9.4; Streamlit Apache-2.0, about 46k stars, 1.66.1)
1. `panel convert --to pyodide-worker` turns an app into static WebAssembly.
   → blicket: possible, but heavy.
2. Streamlit's `st.cache_data` and `AppTest` for headless tests.
   → blicket: cache transformations by input and code hash, and test plot types through their
   contract rather than with screenshots.
3. OWID's chart-diff is itself a Streamlit app.
   → blicket: a quick way to prototype the review flow before building it into the Nuxt viewer.

Avoid: both need a server, and static embedding hits caps.

**Chartbook generators.**
- `chartbook` (https://github.com/backofficedev/chartbook; BSD-3, 0.1.1, one author, very early):
  1. Chart entries in the manifest carry units, frequency and source.
     → blicket: the manifest carries domain metadata for display and search.
  2. A strict vocabulary: "a manifest asks, a lockfile records what was got, a snapshot records
     what was made, and an index records what a site shows". Committed files contain no
     timestamps.
     → blicket: keep manifest, snapshots and build index separate, and make the site a view
     over the index.
  3. `chartbook check` validates that entries are complete.
     → blicket: `blicket validate` checks metadata such as units and descriptions.
- bdecon/US-chartbook (https://github.com/bdecon/US-chartbook) is economics' version of the
  thousand-page PDF.
- No chartbook tool I found diffs against a baseline.

**Plotly Express** (https://plotly.com/python/plotly-express/; MIT, about 18.9k stars, v7.1.0)
1. Dimensions map to arguments such as `color`, `line_dash`, `facet_row` and `animation_frame`.
   → blicket: confirms the channel set. `animation_frame` is a channel that is really a control.
2. `go.Sankey` with node positions that can be pinned.
   → blicket: the quickest Sankey backend that keeps one layout for baseline and current.
3. Dropdowns and sliders in static HTML.
   → blicket: fallback controls for custom plot types built on Plotly.

Avoid: a self-contained figure weighs 5 MB or more (load plotly.js once per site), and Kaleido
needs Chrome.

**ggplot2 and plotnine** (ggplot2 v4.0.3; plotnine MIT, v0.15.8)
1. `aes()` plus facets is the mental model REMIND users already have.
   → blicket: document a translation table (colour → color, linetype → strokeDash,
   group → detail, facet_grid → row/column).
2. Themes are a separate layer.
   → blicket: the project theme and style registry never live inside Blicks or snapshots.
3. The ggplot2 4.0 rewrite broke many dependent packages and forced snapshots to be re-accepted.
   → blicket: don't snapshot renderings.

Avoid: ggplot objects cannot be serialised, so they cannot be an interchange format.

**Mosaic** (https://idl.uw.edu/mosaic/; BSD-3, about 1.4k stars, v0.34.0 on 2026-10-21)
1. DuckDB-WASM queries Parquet in the browser.
   → blicket: an opt-in for larger Blick tables if static-first proves too limiting.
2. Inputs fill themselves from distinct column values.
   → blicket: controls get their options automatically.
3. Specs in JSON or YAML that include both inputs and charts.
   → blicket: controls can be overridden in the manifest.

Avoid: a large runtime that is slow to start, and an API that still changes.

**Datawrapper arrow and range plots** (https://www.datawrapper.de/blog/new-arrow-and-range-plots)
→ blicket: arrow or dumbbell plots as the comparison view for bar types, and for the overview's
top movers.

**Sankey libraries and Sankey diff.**
- d3-sankey (BSD-3, frozen since 2019) keeps input order when its sort functions are null.
- ECharts (Apache-2.0, about 67.6k stars) has `layoutIterations: 0` to keep data order and
  `renderToSVGString()` for rendering on the server.
- Plotly can pin node positions.
- Prior art for comparing two Sankeys is essentially absent. The closest is Vosough et al.
  (2018), "Mirroring Sankey Diagrams for Visual Comparison Tasks"
  (https://www.scitepress.org/papers/2018/66512/66512.pdf), which mirrors two diagrams on
  shared nodes and deliberately avoids overlaying them.
- → blicket: this is novel design work:
  - Compute the layout from the union of baseline and current nodes, then pin it.
  - Offer three comparison views: current widths coloured by signed relative change, a faint
    outline of the baseline, or mirrored side by side.
  - Always add a ranked table of edge changes, including new and removed links.
  - A candidate magnitude is Σ|Δ| / (Σbaseline + Σcurrent).

**MESSAGEix reporting with genno** (https://github.com/khaeru/genno; GPL-3, 1.31.0)
1. Figures are nodes in a computation graph.
   → blicket: shared inputs are computed once and cached.
2. A plot class declares its inputs and implements `generate()`.
   → blicket: matches transformation plus plot type.
3. Keys encode dimensions (`emi:nl-t-yv`).
   → blicket: output schemas can be declared before any run.

Avoid: abstract key syntax, and GPL-3 if code is reused.

**GCAM gcamdata old/new test** (https://github.com/JGCRI/gcam-core/blob/HEAD/input/gcamdata/tests/testthat/test_oldnew.R)
1. Comparison data is stored for every output.
   → blicket: the closest precedent for per-Blick snapshots.
2. The comparison ignores row order, uses a tolerance of 0.02, then falls back to rounding.
   → blicket: diff by key, not by position.
3. A `FLAG_NO_TEST` opt-out per output.
   → blicket: a Blick can be marked "not tracked".

Avoid: a comparison-data store nobody maintains (last push 2023) goes stale, and the test is
pass/fail only. "TEMPORARY FIX TO PASS CHECKS" hacks in the test show that people patch tests when
accepting a change is painful.

**GAMS MIRO** (https://www.gams.com/miro/; GPL-3, v2.13.5)
1. A custom renderer contract: two R functions per symbol, bound in JSON.
   → blicket: a precedent for a plugin contract.
2. Custom compare modules receive one data frame per scenario, the sandbox first.
   → blicket: `diff()` receives (baseline, current) in a fixed order.
3. Tabs stay synchronised between scenarios.
   → blicket: control state is shared between the current and baseline views.

Avoid: it needs a server, and comparison is side by side only. REMIND is written in GAMS, so
some users may know MIRO.

**TIMES Veda and VedaOnline** (https://veda-documentation.readthedocs.io/en/latest/pages/Results.html)
- Proprietary. Only one idea transfers: user-defined result tables saved per model, a GUI
  version of a Blick manifest. It documents no diff features.

**climate-assessment** (https://github.com/iiasa/climate-assessment; MIT)
- Regression tests compare IAMC outputs at rtol 1e-2, and an `update_expected_files` switch
  overwrites the expected files.
- → blicket: this is the plain "update snapshots" pattern that blicket improves on: whole
  files overwritten, no review, no reason.

**EnergyPlus Regression Tool** (https://github.com/NatLabRockies/EnergyPlusRegressionTool)
1. `math_diff.config` sets tolerances per unit and aggregation, for example `C, Hourly = 0.2, -1`.
   → blicket: default tolerances keyed by the IAMC unit column.
2. It counts small differences (within tolerance) and big ones separately.
   → blicket: two levels of change, noise and real change.

**memote** (https://github.com/opencobra/memote; Apache-2.0, dormant since 2024-01)
- A test suite for metabolic models with snapshot, diff and history reports, run in the model
  repository's CI and published to GitHub Pages.
- → blicket: confirms the "report per commit plus history" pattern for scientific models.

**Aim** (https://github.com/aimhubio/aim; Apache-2.0, about 6.3k stars)
- Any parameter can group runs by colour, stroke or facet, with aggregated bands.
- → blicket: split controls that map to colour, line style or facet.

**showyourwork** (https://github.com/showyourwork/showyourwork; about 670 stars)
- Links every figure in a paper to the script that made it and builds in CI.
- → blicket: figure provenance for the paper-supplement use case.

---

## Part 9. Synthesis

### 9.1 Ideas worth adopting, ranked by value

The ranking weighs three things: the value for the first two jobs (development companion and
automated guard), whether the idea is missing from the concept today, and how cheap it is to
build.

1. **Several types of change, not one magnitude.**
   - The types:
     - new Blick;
     - removed Blick (orphan);
     - definition changed (code, mapping or plot type);
     - schema changed (dimension values or columns appeared or vanished);
     - value changed (with a magnitude);
     - representation only (values equal).
   - Each type has its own default policy. Representation-only changes are accepted
     automatically. New and removed Blicks need an explicit decision. Value changes are ranked
     by magnitude.
   - This settles the open question about dimension values appearing or disappearing.
   - Sources: inline-snapshot, OWID, Dagster, pypsa-validator, Jest, syrupy and insta orphans.
2. **The build always finishes, becomes an immutable candidate, and CI never accepts.**
   - `blicket build` runs to the end and pushes the build to the store, the counterpart of
     insta's `.snap.new` or testthat's `.new` files, except that the candidate is a whole build.
   - Review and accept act on builds in the store. That flow is not designed yet; the direction
     is a UI tied to the pull request, as in Chromatic. Prior art for it: accept all without a
     selector is refused, exit codes 0/1/2 follow datacompy and Histoire, and policies are
     named modes, as in Playwright and insta.
3. **A review path for runs made elsewhere.**
   - IAM runs happen on HPC clusters. The store is that path: the run machine pushes its
     build, and the review happens wherever the store is reachable.
   - Prior art offers the alternatives: fetching candidates built in CI (testthat's
     `snapshot_download_gh`), an accept file exported from the static site (asv's ignore
     snippet), or a bot pull request (Lost Pixel).
   - Without such a path, the development companion only works for runs made on the laptop.
4. **A generic diff recipe with a bounded magnitude.**
   - The recipe:
     1. a schema diff;
     2. an outer join on the dimension keys, never by position;
     3. keys added and removed, cells changed, and maximum absolute and relative change per
        value column.
   - Magnitude candidates:
     - BARD with ε derived from the series' range (OWID);
     - `peak_change` normalised by the reference peak (remind-mfa);
     - NRMSE with a noise floor (pypsa-validator).
   - Tolerances are `{atol, rtol}` per value column, with defaults keyed by unit (EnergyPlus)
     and OWID's caps on changed and new points.
   - Tables are put in canonical form (sorted, rounded) before hashing.
   - datacompy and `pyam.compare` can implement much of this.
5. **Fingerprint each change.**
   - A normalised hash of each Blick's delta table groups identical changes, carries an accept
     over when the same change reappears after a rerun, and lets known noise be ignored (Argos,
     Percy).
   - A content hash of each table lets unchanged Blicks be skipped (pytest-mpl hybrid mode,
     data-diff).
   - This implements the deferred "grouping" decision without any lineage analysis.
6. **The accept record is data.** Input for the review-flow design.
   - It holds the reason, the person, the date, the hash of the accepted table, the code hash
     and the run id, attached to the build (insta keeps it in the snapshot header).
   - An accept is valid only for the exact pair of code hash and candidate hash; anything else
     is stale (Histoire, OWID).
   - Reasons follow a small schema, a category plus free text, so they can be searched later
     (MLflow).
7. **The controls rule from HoloViews, plus a table mapping column type to control.**
   - Each unbound dimension is plotted, aggregated, or becomes a control (HoloViews).
   - "Filter" versus "split", named after hvPlot's `groupby` and `by`/`row`/`col`.
   - The control is chosen by data type and number of values (Vizro, Storybook, Snakemake's
     two-value toggle), and Blicks can override it.
   - Control state lives in the URL (Storybook, Rill).
   - The browser receives the small table and filters it. Control states are never pre-rendered
     (Panel's caps).
8. **Stable identity and discovery without execution.**
   - Explicit hierarchical Blick IDs, like compareScenarios' chunk labels.
   - A manifest or index produced without running transformations (Storybook indexers, Ladle's
     `meta.json`).
   - An orphan policy (insta's `auto`).
   - Families of Blicks generated from templates (nomenclature's tags).
   - `index.json` also enables composing catalogs, for example IAM plus MFA.
9. **CI report conventions.**
   - One PR comment, updated in place and posted only when something changed: top movers plus
     a link to that pull request's catalog (CML, pypsa-validator, Bencher, Datafold).
   - The status check means "all changes reviewed" (OWID, Chromatic, CodSpeed).
   - Severity per Blick decides fail or warn (piamValidation's `critical`, nomenclature's
     levels, GX, Evidently).
   - `blicket validate` works without a run (nomenclature).
10. **A cache keyed by code and data.**
    - The key combines Blick code, imported helpers, and the hashes of the input data read
      (Hamilton, Dagster, TurboSnap, Histoire).
    - Avoid the blind spot of Quarto freeze and Observable Framework, whose caches ignore input
      data.
    - Inputs declared by parameter name enable grouping by shared inputs later.
11. **Details of the plot type contract.**
    - Plot types declare their channel slots (W&B presets, DVC templates).
    - `render` returns one of a few typed outputs (Kedro-Viz previews).
    - The framework applies control state before `render` (Vizro).
    - `diff` receives (baseline, current) in a fixed order (MIRO).
    - A reserved `version` column is how the built-in Vega-Lite plot types get their overlay
      comparison (DVC); project plot types implement their own.
    - Use Vega-Lite channel names with aliases, rendered in CI with vl-convert.
12. **Comparison views.**
    - The difference mark for lines (Observable Plot).
    - Arrow or dumbbell plots for bars (Datawrapper).
    - Top movers within a Blick (Rill).
    - A heatmap drill-down (piamValidation, remind-mfa).
    - The Sankey diff is new design work: a pinned layout from the union of nodes, plus a
      ranked table of edge changes.
13. **Domain conventions for IAM and MFA.** These belong in a project adapter, not in the core.
    - A style registry per dimension value (`mip::plotstyle`, pyam's `run_control`).
    - Reference data as a pseudo-scenario, excluded from the magnitude (piamValidation, pyam).
    - The variable hierarchy with `|+|` summation markers drives the children shown in stacked
      areas.
    - Units are part of the key, and periods of different lengths need aligning.
    - MFA Blicks output edge tables.
    - Profiles set control defaults.
14. **Integrate rather than compete.**
    - A pytest plugin (the marimo pattern).
    - An R adapter that mirrors testthat's verbs.
    - A Quarto shortcode for embedding accepted Blicks in papers.
    - A Snakemake rule.
    - An importer for compareScenarios sections, to seed REMIND's Blick code.

### 9.2 What prior art says about the concept's open and deferred questions

| Question in concept.md | What prior art suggests | Sources |
|---|---|---|
| Snapshot size | Not a concern with tables in a store rather than in git. The Blick author still controls granularity, and age cohorts are reduced before snapshotting. | pytest-mpl hybrid mode, reg-suit, flodym |
| Dimension values appearing or disappearing | A separate change type ("schema"), not part of the magnitude. Join on keys, keeping both sides. | inline-snapshot, pyam.compare, pypsa-validator, Dagster schema checks |
| Blick identity across renames | Explicit hierarchical IDs, independent of function names. Detect orphans on full builds and offer to delete them locally. | compareScenarios, inline-snapshot `external()`, insta `--unreferenced` |
| How transformations access raw data | Inputs declared by parameter name, a project-defined loader, and a cache keyed by code hash and input hash. | Hamilton, genno, Observable data loaders |
| Several runs or models per repository | Run profiles with their own baselines ("variants"), and composing catalogs through an index. | testthat `variant`, Storybook composition |
| Does static-first limit exploration? | Not for small tables filtered in the browser. DuckDB-WASM or WebAssembly is an opt-in escape hatch. | Vega-Lite params, Quarto OJS, Mosaic, marimo |
| Reference and historical data | A pseudo-scenario or pseudo-model, styled by the plot type and excluded from the magnitude. | piamValidation, pyam, compareScenarios |
| Tolerances | `{atol, rtol}` per value column, defaults by unit, OWID's caps on changed and new points, inherited from project to group to Blick. | pytest-regressions, datacompy, EnergyPlus, OWID, Chromatic |
| CI policy | Named modes. The check means "all changes reviewed". Severity per Blick. CI never accepts. | insta, Playwright, OWID, Chromatic, piamValidation |
| Variants (saved presets) | Control state in the URL covers most of the need cheaply. | Storybook args, Rill |
| Checks | Show results from existing validators, with a per-Blick checks slot. | piamValidation, nomenclature, pyam, flodym, Storybook `play` |
| Run against run | Any two builds in the store can be diffed, or runs become a dimension. | Histoire, reg-suit, PyPSA `NetworkCollection` |
| Grouping of changes | Fingerprint each change first; lineage of shared inputs later. | Argos, Percy, Recce |

### 9.3 Things to avoid

- **Pixels or rendered specs as the baseline.** vdiffr, pytest-mpl, Chromatic's "modes",
  Histoire's per-OS baselines, and Altair's hashed dataset names all show that renderings
  change for reasons that are not real changes.
- **Baselines, approvals or review UX that exist only in a service.**
  - Neptune's hosted service shut down in March 2026 and deleted its data
    (https://docs.neptune.ai/transition_hub).
  - Lost Pixel was discontinued.
  - CML's image server stopped accepting uploads.
  - Chromatic, Datafold and Recce keep merge gating in their clouds.
- **Accept all without a reason.** This breeds snapshot fatigue, which is why Thoughtworks
  Radar puts "snapshot testing only" on Hold.
- **Hiding changes below a threshold.** pypsa-validator did this. Rank changes and fold the
  small ones away, but never drop them.
- **Pre-rendering every control state** (Panel and HoloViews embedding).
- **Matching rows by position** (pytest-regressions).
- **Overlay-only diffs without a magnitude** (DVC plots).
- **Requiring a server or database** (MLflow, W&B, Hamilton UI, Dagster, the Scenario Explorer,
  MIRO).
- **Scope creep into run tracking or dashboard building.** Kedro-Viz removed experiment
  tracking, and Vizro, Evidence Studio and MLflow have all drifted.
- **Mixing Blick code, layout and narrative**, plus global options (compareScenarios).
- **Drift tests based on p-values** for deterministic outputs (Evidently).
- **Caches keyed only on source files** (Quarto freeze, Observable Framework).
- **A baseline store nobody maintains** (gcamdata's separate comparison-data repository went
  stale).

### 9.4 Does any existing tool already cover blicket?

No. I looked specifically for a tool that would make the concept redundant and found none.

The concept's parts each exist separately:
- a catalog with controls: Storybook, HoloViews;
- stored baselines with review and accept: Chromatic, Histoire, insta, testthat;
- table diffs: datacompy, Recce;
- standard domain figures: compareScenarios, pyam.

Nobody combines them on the level of data:
- a snapshot of each Blick's transformed table, kept as an immutable build in a store;
- a change magnitude that knows about the plot type;
- a review ranked by magnitude, with bulk accept and recorded reasons;
- dimension controls inferred from the table;
- all of it in a static site.

**Nearest misses:**
- **OWID's chart-diff** has most of the review flow, but it is internal to OWID. It is bound to
  their production database and has no catalog with controls.
- **Histoire's visual testing** has the best local review design, but it works on UI pixels and
  is not yet released.
- **Observable Plot's test harness** proves that "Blicks as functions with snapshots" is
  pleasant to work with, but it serves the library's own developers.

**Two "assemble it from parts" alternatives** deserve an honest look.
- **Argos with JSON snapshots, plus a pytest plugin.** This gives a decent review UX today, but
  it is SaaS, cannot rank by magnitude, and has no controls or diffs aware of the plot type.
- **pytest-regressions or syrupy, plus a Quarto site.** This gives a baseline and a static
  catalog, but no review flow and diffs that match rows by position.

Either would cover perhaps a third of jobs 1 and 2.

**The domain evidence points the same way.** Several modelling groups have built partial,
project-specific versions in the last two years: pypsa-validator (now archived), gcamdata's
old/new test, climate-assessment's expected files, piamValidation's version-comparison
template, and remind-mfa's `run_comparison`. The need is real and recurring. Each of these
attempts died or stayed local because it was tied to a single model. That supports the
concept's bet that generality comes from the data model and the plugin boundaries.
