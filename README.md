# blicket

Storybook for scientific model outputs. A *Blick* is a named view on a model run: a function that
turns the run into a table, and how to plot that table. blicket discovers a project's Blicks and
lists them, with every problem it finds in their definitions. The idea behind it is in
[docs/concept.md](docs/concept.md), the design in [docs/architecture.md](docs/architecture.md).

## Defining Blicks

```toml
# pyproject.toml
[tool.blicket]
blicks = ["blicks/**/*.py"]  # the default
```

```python
# blicks/flows.py
import blicket as bk

bk.group("flows", title="Material flows", tags=["mfa"])


@bk.blick(
    title="Steel flows by process",
    plot=bk.plots.stacked_area(x="year", y="value", color="process"),
)
def steel_by_process(run): ...
```

```console
$ blicket list
flows  Material flows  [mfa]
  flows/steel_by_process   Steel flows by process   stacked_area

1 group · 1 Blick
```

`blicket list` looks for the project by walking up from the working directory; `--project PATH`
names the project directory instead. Exit codes: 0 success, 2 errors of any kind. `-v` shows
tracebacks, `--json` prints the report as JSON.

## Development

```console
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

blicket is built with meson-python without build isolation, so that the editable install made by
`uv sync` can rebuild on import. The build tools therefore live in the `build` dependency group,
which is installed by default; `uv sync --no-default-groups` is not supported for development.
Every module under `src/blicket` must be listed in `meson.build` (a test checks this). `uv build`
packs only committed files; use `uv build --wheel` to try uncommitted work.

## License

MIT
