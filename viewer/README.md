# blicket viewer

The web viewer of a blicket build directory: a Nuxt 4 app in client-only mode with hash routing
and a relative base URL, generated to static files and shipped inside the blicket wheel. What it
shows and how a build directory is served is in the [root README](../README.md#looking-at-a-build);
the design is in [docs/plans/m1-viewer.md](../docs/plans/m1-viewer.md). Node and pnpm are needed
only to work on the viewer.

## Developing

With a build of the example (see [its README](../examples/remind-mfa/README.md)), and
`BLICKET_VIEWER` set for terminal 1 as the [root README](../README.md#development) shows (any
generated viewer will do: the dev server only takes the data from it):

```console
$ cd examples/remind-mfa && uv run blicket serve       # terminal 1, the data
$ cd viewer && pnpm install && pnpm dev                # terminal 2, the app
```

The dev server forwards `/manifest.json` and `/blicks/` to `blicket serve` at
`http://127.0.0.1:8765`, or the address in `BLICKET_SERVE`, so the app reads `./manifest.json`
as it does in a build directory, and nothing else on the machine can read the data.

```console
$ pnpm test         # vitest on app/lib and app/plots, without Nuxt
$ pnpm typecheck    # nuxt typecheck, tests included
$ pnpm lint         # oxlint; unused variables in .vue files are pnpm typecheck's
$ pnpm generate     # the site, in .output/public
```

How blicket from a checkout uses a generated viewer (`BLICKET_VIEWER`), and how the release wheel
bundles it, is in the [root README](../README.md#development).

`app/lib/manifest.ts` describes the manifest of the spec in its `SPEC` by hand; the Python models in
`src/blicket/manifest.py` and `model.py` are its source of truth, and the viewer refuses a build
of another spec. A plot type's browser half (`app/plots/`) is a Vega-Lite specification built from
the rows the controls select; its colours are the validated palette in `app/plots/theme.ts`.
`tests/table.parquet` is the one checked-in file: the Parquet reader must read a real zstd file,
and the test says how polars wrote it.
