# To do

What the reviews of [on-demand-blicks.md](on-demand-blicks.md) found, in its first version (lazy
runs) and in the revision (on-demand Blicks), and left for later, one line each, and what its
implementation left undone on purpose.

## Bugs

- `PUT` and `DELETE` on the server of `serve`, and on paths of `dev` outside its routes, answer the stdlib's HTML 501 instead of a 405 (older than on-demand Blicks; `dev`'s routes answer a JSON 405).
- What a transformation's subprocess writes to file descriptor 1 lands on stdout, between the build lines of a session of `blicket dev` and in the reports of `build` and `check`: `redirect_stdout` replaces `sys.stdout` only.
- The messages of `baseline.resolve` word `--against` unclearly (older than on-demand Blicks); `blicket dev` prints a baseline that cannot be resolved as `error: no baseline: …` on stdout among its start lines and serves on, where `baseline: none (…)` would fit.
- With stdout on `/dev/full`, `blicket dev` exits 2 at the start with "unexpected OSError … this is a bug in blicket": `cli._echo` handles `BrokenPipeError` only (older than on-demand Blicks).
- `pnpm generate` writes an `index.html` of "Redirecting..." with the relative base URL `./` under Node 26, at the base commit too; `NUXT_APP_BASE_URL=/` avoids it.
- `check` stops with an unexpected exception when a plot type's `diff` raises anything but `ValueError` or `TypeError`; a session of `blicket dev` makes it the Blick's comparison error.
- A transformation that raises an exception without a message says `raised ValueError: ` with a stray colon in `build` and `check`; a session of `blicket dev` names it alone.
- After a reload during a rebuild, a Blick's page shows the Blick at full opacity and without its status line for a moment, until the first answer of `dev/info` is shown.
- The jobs a page shows can be one poll newer than its manifest (a Blick `building` whose entry is already built, or the reverse), until the next poll.
- `dev/runs` names a run folder reached through a link after the link and lists its resolved path; `dev/run` refuses the path of the link itself.

## Possible next features

- An explicit `served` flag in `dev/info`, instead of the client inferring from the manifest's 404 that no run is served yet.
- `Retry-After` on the 409 of `dev/query` while an expensive Blick builds.
- `prefers-reduced-motion` for the spinners and pulses, which the viewer honours nowhere yet.
- With many tabs open on Blicks, a restart of `blicket dev` queues each of their Blicks again: revisit with m2-2's code reload.
- Touch targets of the header's buttons (32 px) and of `Pick another run` (28 px high) under the 44 px a coarse pointer wants.
- A hint for a loader or a Blick that still passes the first version's `lazy=True`: today it is a plain unknown-option or extra-field error.

## Left undone on purpose

- One content-addressed table store per session: the builder's tables (an LRU) and the run's (its snapshots) stay two stores behind the one route `dev/tables/<sha256>.parquet`. In the viewer they share the table cache's budget, whose eviction only drops cached bytes; a chart keeps the rows it shows.
- The split of what the definitions give a run of `blicket dev` (the registry, its expensive Blicks, the background's order, the baseline) from what it built (tables, snapshots, revision), so that m2-2's code reload keeps the tables: it is m2-2's, and needs a second kind of `Task` in `jobs.Worker`.
- The worker takes no job while a load holds or waits for the session's lock, and `Session.load`, the one caller of `RunLock.load`, wakes it afterwards (`worker.wake()`). Another caller, such as an m2-2 reload taking the lock that way, must wake it too, or the pause moves into the worker (`with worker.paused():`, which wakes it on exit).
- A Blick whose definition is invalid is told apart in the viewer by an entry in error without a timing (`isInvalid`), which a Python test pins, not by a field the server sends.
