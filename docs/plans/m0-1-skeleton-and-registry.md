# M0.1 Skeleton and Blick registry

Status: plan, 2026-10-23, revised the same day after an independent review that tested the
packaging and import mechanics on a toy project. First task of [m0-tasks.md](m0-tasks.md).
Companion to [architecture.md](../architecture.md), which decides the layout, the Blick
definition and the tooling; this plan only fills in what that document leaves to the
implementation.

## Goal

An installable `blicket` package in this repository with the Blick definition API, discovery
of a project's Blick modules from its `[tool.blicket]` config, and a `blicket list` command.
No tables, no loader, no store: the scaffold every later M0 task adds to, verified with fixture
projects and tests.

## The flow this task enables

1. A project puts `[tool.blicket]` into its `pyproject.toml`:

   ```toml
   [tool.blicket]
   blicks = ["blicks/**/*.py"]
   ```

2. It writes Blick modules:

   ```python
   # blicks/flows.py
   import blicket as bk

   bk.group("flows", title="Material flows", tags=["mfa"])

   @bk.blick(
       title="Steel flows by process",
       plot=bk.plots.stacked_area(x="year", y="value", color="process"),
       controls={"region": "split"},
       aliases=["flows/steel_process"],
   )
   def steel_by_process(run):
       ...

   for flow in ["scrap", "slag"]:
       bk.register(
           id=f"flows/{bk.slug(flow)}", title=flow.capitalize(),
           plot=bk.plots.line(x="year", y="value", color="region"),
           transform=lambda run, f=flow: ...,
       )
   ```

3. `blicket list` in the project prints

   ```
   flows  Material flows  [mfa]
     flows/steel_by_process   Steel flows by process   stacked_area   aliases: flows/steel_process
     flows/scrap              Scrap                    line
     flows/slag               Slag                     line
   stocks
     stocks/in_use            In use                   line

   2 groups · 4 Blicks · 1 error

   errors
     blicks/broken.py:1  import failed   (-v for the traceback)
       ModuleNotFoundError: No module named 'nothere'
       is 'nothere' installed in /path/to/.venv?
       the Blicks in this file were skipped
   ```

   and exits with 2 because of the error, 0 otherwise. (Output as implemented; the plan's
   original sketch had one-line errors.)

## Approach

### Repository layout

```
pyproject.toml  meson.build  LICENSE  README.md  .python-version  uv.lock
.github/workflows/ci.yml
src/blicket/
  __init__.py          public API: group, blick, register, slug, plots, PlotType, Channel, PlotSpec,
                       Blick, FailedBlick, Group, Registry, Problem, DefinitionError, ConfigError,
                       discover, Config, load_config, find_project_root
  errors.py            leaf: Problem, Source, Kind, DefinitionError, ConfigError, display_path
  model.py             Blick, FailedBlick, Group, Registry and their JSON form
  _validation.py       field checks for definitions and groups
  definitions.py       group, blick, register, slug and the per-module definition records
  assembly.py          records → Registry: ids, duplicates, aliases, group merging
  discovery.py         globs → purge → import, then assembly
  config.py            [tool.blicket] model, project root lookup
  plots/_base.py       PlotType, Channel, PlotSpec, the built-in base
  plots/__init__.py    the four factories and the built-in lookup by name
  plots/line.py  plots/stacked_area.py  plots/bar.py  (bar and stacked_bar)
  cli.py               typer app: list, --version, exit-code policy
tests/
  projects/minimal/    the golden `blicket list` output, also used by the CI smoke test
  projects/name_clash/ a real package that must shadow the project's namespace directory
  conftest.py          autouse isolation of sys.modules, sys.path and the definition records
  support.py           make_project (writes a project into tmp_path) and small helpers
  test_config.py  test_definitions.py  test_assembly.py  test_discovery.py  test_errors.py
  test_plots.py  test_cli.py  test_packaging.py
```

(Layout as implemented after four review rounds; the plan's original sketch had a single
`registry.py` and one fixture directory per scenario. Every other scenario is generated in the
test with `make_project`, per AGENTS.md.)

`examples/` and `viewer/` arrive with M0.3 and M1. The `src/` layout keeps the repository root
from shadowing the installed package.

### Packaging and tooling

- **meson-python** as the build backend, as decided; `meson-python >= 0.18` for PEP 639
  `license-files`. `meson.build` lists the package files with `py.install_sources(...,
  subdir: 'blicket/...')` per directory. The review showed that `install_subdir` with
  `exclude_directories: ['__pycache__']` only excludes the top-level cache directory and lets
  nested `.pyc` files and stray editor files into the wheel, so the file list wins. A test
  (`test_packaging.py`) checks that every `.py` under `src/blicket` appears in `meson.build`, so
  a forgotten file fails the test suite instead of silently missing from the wheel. The viewer
  later arrives as a `custom_target` installed next to the package.
- The version lives in `pyproject.toml` only, static. `dynamic = ["version"]` was tested and
  breaks a fresh `uv sync`: uv has to ask the backend for metadata before anything is installed,
  and with build isolation off that import fails. meson-python takes the pyproject version over
  `project(version:)`, so `meson.build` declares none.
- **uv** manages the environment. `[tool.uv] no-build-isolation-package = ["blicket"]`, with
  `meson-python`, `meson` and `ninja` in a `build` dependency group that is in `default-groups`
  (and included by `dev`), so that the editable install made by `uv sync` can rebuild on import.
  uv's two-phase install was verified to cover the root project: `uv sync` on a fresh clone works
  in one step. `uv sync --no-default-groups` is therefore unsupported for development and the
  README says so. `uv build` runs without isolation too, so CI runs `uv sync` first.
- `uv build` makes the sdist with `meson dist`, which packs only committed files, and builds the
  wheel from that sdist. Uncommitted modules are silently absent. Hence the "done when" below
  tests a fresh clone of the committed tree, and the implementer uses `uv build --wheel` while
  work is uncommitted.
- `requires-python = ">=3.14"` and `.python-version` 3.14, as decided on 2026-10-23 (the
  example project must share an environment with remind-mfa, whose dependency chain has no 3.15
  wheels yet). Raised to 3.15 later with a one-line change.
- Runtime dependencies for this task: `typer`, `pydantic`. polars and the rest join in M0.2.
- **ruff** for lint and format (line length 100), **pytest**, and **ty** for type checking since
  remind-mfa already uses it; ty finds `src/` on its own and is not affected by meson-python's
  import-hook editable install. A GitHub Actions workflow runs lint, types, tests, `uv build`
  and the wheel smoke test on Ubuntu; it covers the core package only, never `examples/`, which
  depends on a local checkout and gitignored runs. It cannot run until the repository is pushed.
- `[project.scripts] blicket = "blicket.cli:app"`. Licence MIT, `license-files = ["LICENSE"]`.
  `.gitignore` gets `/build/` and `/dist/` instead of the unanchored `build/` and `dist/`, which
  would otherwise swallow a future `src/blicket/build/` package.

### Config

`[tool.blicket]` is a pydantic model with `extra="forbid"`, so a typo in a key fails loudly:

| key | default | used from |
|---|---|---|
| `blicks` | `["blicks/**/*.py"]` | M0.1 |
| `loader` | none | M0.2 |
| `store` | `".blicket/store"` | M0.6 |
| `tolerance` | `1e-5` | M0.5 |
| `digits` | `6` | M0.4 |

The project root is the directory of the `pyproject.toml` that contains `[tool.blicket]`, found
by walking up from the working directory, or given with `--project`. No such file is an error.
The validator `tolerance >= 10 ** (1 - digits)` from the architecture is cheap and goes in now,
for the project value and for every per-Blick `tolerance=`.

### Blick definition

- `bk.group(name, title=None, tags=())` attaches group metadata to the calling Blick module.
  `@bk.blick(...)` and `bk.register(...)` record a Blick definition for the calling Blick module.
  The module is found by walking the stack outward from the call and taking the first frame whose
  module is one of the files discovery is importing. Helpers that build Blick families from
  `blicks/_helpers.py` or from the project's own package are therefore transparent, and a Blick
  module that imports another Blick module cannot swallow its Blicks, because the inner module's
  frame is met first. Outside discovery, in a notebook or a test, the immediate caller counts.
  Both decorator forms use the same rule; `fn.__module__` is not used.
- Definitions are recorded first and finalised when the module import finishes: the group, the
  default ids and the tag union are computed then. So `bk.group()` may stand anywhere in the
  module, a second call is an error, and group metadata reaching a Blick from another module in
  the same group is handled. The decorator returns the function unchanged, so a Blick can still be
  called directly in a test or notebook.
- A module without a `bk.group()` call uses its file stem as the group name, as the architecture
  says; for a package `__init__.py` the package name. Two modules may contribute to one group;
  only one of them may give a title. If two do, the first in sorted path order wins and a warning
  names both files. Tags are the union.
- `Blick` is a frozen dataclass: `id`, `title`, `description` (the docstring), `group`, `tags`
  (own tags; the group's are added when read), `plot: PlotSpec`, `controls`, `defaults`,
  `tolerance`, `aliases`, `dims`, `measures`, `order`, `transform`, `module` (optional, since M2's
  transient Blicks have none), `source` (file and line). `dims`, `measures` and `order` are
  accepted and stored now and interpreted in M0.2, so Blick code written against this task does
  not change later.
- Validated at definition time: `controls` values are `"filter"` or `"split"`; `defaults` and
  `order` are JSON-serialisable with string keys, because they go into the manifest and the
  definition hash; `transform` takes exactly one positional parameter; `bk.register` requires
  `id=`, because a lambda or a `functools.partial` has no usable name.
- Ids are path-safe lowercase slugs separated by `/`, at least two segments:
  `^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)+$`. A group name is one or more such segments, so
  `bk.group("flows/steel")` nests. Ids become file names in build directories, hence lowercase,
  no dots, and the Windows-reserved names (`con`, `nul`, `aux`, `prn`, `com1`…) rejected. The
  default id is `<group>/<function name>`; a function name that is not already a valid segment
  (upper case, leading underscore, non-ASCII) is an error asking for an explicit `id=`, rather
  than silently lower-cased, which could make two functions collide. An explicit id need not
  start with the group; the id is identity, the group is organisation. `bk.slug(text)` turns
  arbitrary text into a valid segment (lowercase, non-alphanumerics to `-`, collapsed) for
  generated families. The default title is the function name with underscores as spaces and a
  capital first letter.

### Registry and discovery

- Definitions live in a process-wide store keyed by module name, and a module's record is reset
  when the module executes again. `discover(project)` imports the globbed files and then
  assembles a `Registry` (Blicks by id, groups by name, alias map, errors, warnings) from the
  records of exactly those modules. Discovery is therefore idempotent, a Blick module imported
  earlier by the loader or a conftest is not lost, and M2's reload needs nothing more than
  re-executing one module and reassembling. One project per process is the supported case; a
  second project in the same process re-imports only the modules under its root or sharing a
  Blick module's top-level name, so a helper package of the same name in both stays the first's.
- Files are matched by the `blicks` globs relative to the project root, sorted by their POSIX
  path, so import order and error messages are the same on every platform. Hidden directories,
  `.venv` and `__pycache__` are excluded from `**` matches; files whose stem starts with `_` are
  skipped as helpers. Zero matches is an error, because a glob typo would otherwise produce an
  empty build and, from M0.7, mark every baseline Blick as `removed`.
- Each file is imported with `importlib.import_module` under the dotted name of its path relative
  to the root (`blicks/flows/steel.py` → `blicks.flows.steel`, `blicks/__init__.py` → `blicks`),
  with the project root prepended to `sys.path` and left there, since transformations and the
  loader import lazily later in the process. Before importing, `sys.modules` entries whose file
  lies under the project root are dropped, so the modules execute. After importing, the module's
  `__file__` must be the globbed path; otherwise a `name clash` error says which file was imported
  instead (a `blicks/` directory without `__init__.py` is a namespace portion and loses against a
  regular package of the same name elsewhere on `sys.path`). A path segment that is not a Python
  identifier is an error for that file.
- Errors are structured: `Problem(kind, severity, message, source, module, ids, traceback)`
  (named `DiscoveryError` in the original sketch) with kinds `import`, `name_clash`,
  `bad_filename`, `no_match`, `no_blicks`, `invalid_definition`, `duplicate_id`,
  `alias_collision`, `group`; warnings are problems with severity `warning`. A doubly claimed id makes both Blicks `error` entries that are never
  compared, since "first in sorted order wins" would let a file rename move an id to another
  function and produce a spurious `value` change. An alias collision marks both Blicks. M0.2 reuses
  the kinds to mark single Blicks as `error` in the manifest, and M0.7 tells an `import` error,
  which makes the build incomplete and disables `removed`, from a bad single definition.
- Nothing raises out of `discover()` except `ConfigError` for a missing or invalid
  `[tool.blicket]` and programming errors in blicket itself.

### Plot types, declarations only

`PlotType` has a `name`, an optional `module` (the browser half's file, unused until M1), a tuple
of `Channel(name, kind, required, doc)` with kind `"dimension"` or `"measure"`, and abstract
`controls` and `diff` that M0.5 implements. Facets are not a channel: the `split` control is the
facet, and M0.5 defines panels by the filter controls. The built-in modules define:

| factory | channels |
|---|---|
| `bk.plots.line(x, y, color=None, linetype=None)` | x dimension required, y measure required, color dimension, linetype dimension |
| `bk.plots.stacked_area(x, y, color=None)` | x dimension required, y measure required, color dimension |
| `bk.plots.bar(x, y, color=None)` | grouped bars; same channels as stacked_area |
| `bk.plots.stacked_bar(x, y, color=None)` | same channels as stacked_area |

Stacked and grouped bars are two plot types rather than an option, because `diff` and
`controls` receive the mapping and not an options bag, and the stacked-scale rule in M0.5 differs
between them. A factory returns `PlotSpec(plot_type, mapping)` after checking that every mapped
channel exists, every required channel is mapped, and no column is bound to two channels. Column
names are not checked against a table here; that is M0.2, which also makes a measure column not
bound to any channel an `error`, so that nothing invisible is diffed. `bk.plots.builtin(name)`
looks a built-in up by name for the manifest.

### CLI

`blicket list [--project PATH] [--json] [-v]` prints the registry grouped as in the flow above,
then warnings and errors. `--json` dumps the definitions (ids, titles, groups, tags, plot type
and mapping, controls, defaults, aliases, source) plus errors and warnings in the JSON form the
M0.2 manifest reuses. `blicket --version` prints the version from package metadata.

Exit-code policy, set here because every later command uses it: 0 success, 1 reserved for
"changes flagged" (M0.7), 2 for errors of any kind. typer alone exits 1 on an uncaught exception,
which CI would read as "changes found", so a command class wraps command execution and maps
unexpected exceptions to 2 with the traceback under `-v`; every command is registered with that
class and takes `-v`, and a test guards it. click's usage errors already exit 2; an abort exits 2
as `error: aborted`; Ctrl-C keeps typer's 130.

## Testing

- Config: defaults, forbidden extra keys, missing section, root lookup from a nested directory,
  the tolerance-digits validator for the project value and a per-Blick value.
- Discovery, each scenario a project generated in the test (checked-in fixtures only for the
  golden output and the shadowing package): explicit id, default id, default title, aliases,
  group from file stem and from `__init__.py`, nested group, two modules in one group with a title
  warning, `bk.group` after the decorators, a family built through a `_helpers.py` module and
  through a function in the project package, broken module captured, duplicate id marking both,
  alias collision, non-identifier file name, zero matches, name clash with a module shadowing the
  `blicks` package, discovery run twice in one process, two projects in one process.
- Definitions: invalid ids and the "give an explicit id" message, `register` without `id`, bad
  `controls` values, non-serialisable `defaults`, a transform with two parameters, `bk.slug`.
- Plot specs: unknown channel, missing required channel, one column on two channels.
- CLI through `typer.testing.CliRunner`: text output, `--json`, exit 2 with errors, exit 2 on an
  injected unexpected exception, `--version`.
- Packaging: every `.py` under `src/blicket` is listed in `meson.build`; in CI, `uv sync`, then
  `uv build`, then the wheel installed into a clean virtual environment runs `blicket list` on a
  fixture project with the expected output.

## Affected areas

New files only, plus the two anchored lines in `.gitignore`. `docs/architecture.md` is not
changed by this task; the one amendment the split needs (comparison results outside the
manifest) is recorded in m0-tasks.md and lands with M0.2.

## Out of scope

Tables, `RunInfo` and the loader (M0.2); canonical form (M0.4); `controls` and `diff` (M0.5);
the store (M0.6); `check` (M0.7); the viewer (M1); reloading (M2). The per-module records, the
optional `module` field and the abstract methods on `PlotType` are the hooks these use.

## Decided by Tobias on 2026-10-23

1. **Python floor 3.14** for now.
2. **Default id spelling:** the function name as is, `flows/steel_by_process`. Ids are baseline
   keys forever; a reader can find the function from the id without a rule in mind.

## Decisions taken here, not asked

- `src/` layout; explicit `py.install_sources` lists guarded by a test; static version in
  `pyproject.toml`; build tools in a default dependency group; ty in the dev tools; a CI workflow
  added now for the core package.
- Stack-walk attribution to the nearest Blick module; definitions finalised after the module
  import; `_`-prefixed files skipped; process-wide module records instead of a context variable.
- Ids lowercase, path-safe and at least two segments; no automatic lower-casing; nested groups
  allowed; the id need not start with the group.
- Duplicate ids and alias collisions mark all involved Blicks as errors; conflicting group titles
  are a warning.
- Four built-in plot types with `bar` and `stacked_bar` separate; split is the facet; unbound
  measures become an error in M0.2.
- Uncaught exceptions exit 2.

## Deviations

Recorded on 2026-10-23 after five review rounds; the fourth simplified, the fifth verified.

- **Modules.** `errors.py` (a leaf: `Problem`, `Source`, `Kind`, `DefinitionError`,
  `ConfigError`), `model.py` (Blick, FailedBlick, Group, Registry), `definitions.py` (the
  definition API and per-module records; `registry.py` in the plan), `assembly.py` (records to
  `Registry`, ordered by file), `discovery.py` (globbing, importing, purging), `_validation.py`,
  `plots/_base.py`; the package ships `py.typed`.
- **Registry.** `blicks` holds only buildable Blicks; every Blick with a problem (invalid
  definition, no usable id, duplicate id, alias collision, tolerance) is in `failed`, named by
  its id, else its function name, else the id as given. `problems` holds the file- and
  project-level `Problem`s (errors and warnings by `severity`); `incomplete` is true when one of
  them is an error. `Problem` replaces `DiscoveryError`; every location is `Source.to_json()`.
- **Definitions.** `DefinitionError` is raised by the plot spec checks, `bk.slug`, a bare
  `@bk.blick` and `bk.group()` without a name; discovery reports it at the file and line. Outside
  discovery invalid definitions raise at once. `__init__.py` is exempt from the `_` helper rule;
  an empty one also from the "defines no Blicks" warning. Zero Blicks is an error unless another
  error explains it.
- **Purge.** Before importing, discovery drops modules whose file lies under the project root
  outside hidden directories, and modules sharing a top-level package with a Blick module, never
  the standard library or blicket. One project per process is the supported case: a second
  project re-imports only those modules, so a helper package of the same name in both projects
  stays the first project's.
- **CLI.** A found project's problems are the report on stdout (text or `--json`); a missing
  project or an invalid `[tool.blicket]` is one `error:` line on stderr; an unexpected exception
  is the `error:` line plus an advice line, with the traceback under `-v`. All exit 2. The policy
  lives on the command class (`cls=_Command`), which every command must use.
- **Tests.** `test_definitions.py`, `test_assembly.py` (in-memory records), `test_errors.py`,
  `test_discovery.py`, `test_config.py`, `test_plots.py`, `test_cli.py`, `test_packaging.py`,
  with `tests/__init__.py` and `tests/support.py`. Projects are generated in the tests; only
  `tests/projects/minimal` (the golden output, also used by CI) and `name_clash` (a real package
  shadowing a namespace directory) are checked in.
- **Dropped on purpose in round 4.** JSON on failures and the `error_count`, `internal`,
  `aborted` and `config` entries; exit 2 on Ctrl-C (typer's 130 applies; an explicit abort still
  exits 2); `--project` accepting a
  `pyproject.toml` path; purge guards for environments inside the project and for modules without
  a location; did-you-mean suggestions for ids and the descriptive names of failed Blicks; the
  list of files taken down by a raising package `__init__.py`; `DefinitionError` for a bad plot
  factory keyword (a `TypeError`, reported as an import error); `Registry.failed_ids`,
  `Problem.__str__` and the example file names in the no-match and no-Blicks messages.
