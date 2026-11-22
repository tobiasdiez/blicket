// Requests to `blicket dev`: what a failed one says, and the shapes of what it answers.
import type { BuilderOptions, BuilderRequest } from './builder'
import { isStatus, type BlickEntry } from './manifest'

/** `blicket dev` did not answer; the message is what the page says under "Cannot reach blicket dev". */
export class Unreachable extends Error {
  constructor() {
    super('It may have stopped; check the terminal.')
    this.name = 'Unreachable'
  }
}

/**
 * A Blick that builds, or that a page asked for and waits to, `Job` in src/blicket/serve.py:
 * whether a page asked for it, not the background, whose Blicks that wait are not listed; since
 * when, in ISO 8601, and for how many seconds, when `dev/info` answered, which the viewer counts
 * on from, whatever its clock says. A Blick that builds while a rebuild of it waits is listed
 * twice.
 */
export interface Job {
  id: string
  state: 'building' | 'queued'
  asked: boolean
  since: string
  seconds: number
}

/**
 * What `dev/info` says, `Info` in src/blicket/serve.py: the project root, and whether the project
 * has a dataset, why not, and whether because `dataset(run)` failed; `session` names the session,
 * which a restart of `blicket dev` and the load of another run change. `revision` rises whenever
 * the manifest or the comparison changed, `jobs` are the Blick building and the Blicks a page
 * asked for that wait, in the order they are built, and `stopped` why the worker that builds them
 * stopped, if it did.
 */
export interface DevInfo {
  root: string
  dataset: boolean
  message: string | null
  failed: boolean
  session: string
  revision: number
  jobs: Job[]
  stopped: string | null
}

/**
 * What `dev/build` says of the Blick asked for: it waits, it builds, or it is done, and nothing was
 * to do. A client that waits for the build waits until the Blick has left the jobs of `dev/info`.
 */
export type BuildAnswer = 'queued' | 'building' | 'done'

/**
 * A run folder to pick, `RunFolder` in src/blicket/serve.py: its path, name and last change, in
 * ISO 8601; or, `project`, the project itself, whose run is computed from its code, without a
 * time. `served` says that the run served was loaded from it.
 */
export interface RunFolder {
  path: string
  name: string
  modified: string | null
  project: boolean
  served: boolean
}

/**
 * What `dev/runs` says, `RunList` in src/blicket/serve.py: the globs of `runs` in `[tool.blicket]`
 * and the folders they match, the project itself first, then newest first.
 */
export interface RunList {
  patterns: string[]
  runs: RunFolder[]
}

const isObject = (body: unknown): body is Record<string, unknown> => typeof body === 'object' && body !== null

const isJob = (job: unknown): job is Job => isObject(job) && typeof job.id === 'string' && (job.state === 'building' || job.state === 'queued')
  && typeof job.asked === 'boolean' && typeof job.since === 'string' && typeof job.seconds === 'number'

/** Whether a body is what `dev/info` answers. */
export function isInfo(body: unknown): body is DevInfo {
  return isObject(body) && typeof body.root === 'string' && typeof body.dataset === 'boolean' && typeof body.session === 'string'
    && typeof body.revision === 'number' && Array.isArray(body.jobs) && body.jobs.every(isJob)
}

/** Whether a body is what `dev/build` answers. */
export function isBuildAnswer(body: unknown): body is { state: BuildAnswer } {
  return isObject(body) && (body.state === 'queued' || body.state === 'building' || body.state === 'done')
}

/**
 * The revision of a session that an answer of `blicket dev` is of, as its header
 * `Blicket-Revision` names it: one, or none for an answer that names none.
 */
export function revisionsOf(response: Response): number[] {
  const named = response.headers.get('Blicket-Revision')
  return named === null ? [] : [Number(named)]
}

/** Whether an answer comes from `blicket dev`, which marks `manifest.json` with a header. */
export function isDevAnswer(response: Response): boolean {
  return response.headers.get('Blicket-Dev') === '1'
}

/**
 * Whether the answer to `manifest.json` says that `blicket dev` serves no run yet: a 404 with the
 * header of `blicket dev`, where a static host's 404 has none.
 */
export function isNoRun(response: Response): boolean {
  return response.status === 404 && isDevAnswer(response)
}

const isRunFolder = (run: unknown): run is RunFolder => isObject(run) && typeof run.path === 'string' && typeof run.name === 'string'
  && (typeof run.modified === 'string' || run.modified === null) && typeof run.project === 'boolean' && typeof run.served === 'boolean'

/** Whether a body is what `dev/runs` answers. */
export function isRunList(body: unknown): body is RunList {
  return isObject(body) && Array.isArray(body.patterns) && Array.isArray(body.runs) && body.runs.every(isRunFolder)
}

/** Whether a body is what `dev/run` answers to a load: the id of the run loaded. */
export function isLoaded(body: unknown): body is { id: string } {
  return isObject(body) && typeof body.id === 'string'
}

/** The message of an error answer, `{"message": ...}`, if the body is one. */
export function messageOf(body: unknown): string | null {
  return isObject(body) && typeof body.message === 'string' ? body.message : null
}

/** Whether a body is a manifest entry, as `dev/query` answers one. */
export function isEntry(body: unknown): body is BlickEntry {
  return isObject(body) && typeof body.name === 'string' && isStatus(body.status) && Array.isArray(body.problems)
}

/** Whether a body is what the builder offers, as `dev/dataset` answers it. */
export function isOptions(body: unknown): body is BuilderOptions {
  return isObject(body) && Array.isArray(body.quantities) && Array.isArray(body.dimensions) && Array.isArray(body.plots)
}

/**
 * `fetch` of a path of `blicket dev`, with a failure to connect as `Unreachable`; an abort stays
 * an abort.
 */
export async function devFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init)
  }
  catch (cause) {
    // fetch rejects with a TypeError when the server cannot be reached.
    throw cause instanceof TypeError ? new Unreachable() : cause
  }
}

/**
 * The JSON body of `response` when it has the shape `is` checks; an error with the server's
 * message when it is an error, or with what was expected when the body has another shape.
 */
export async function bodyOf<T>(response: Response, is: (body: unknown) => body is T, what: string): Promise<T> {
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new Error(messageOf(body) ?? `${what}: ${response.status} ${response.statusText}`)
  if (!is(body)) throw new Error(`${what}: the answer is not what the viewer expects; is the viewer of another blicket?`)
  return body
}

/** The answer of `blicket dev` to a POST of `body` as JSON to `path`. */
function postJson(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  return devFetch(`./${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

/** The entry `dev/query` answers to `request`. */
export async function postQuery(request: BuilderRequest, signal?: AbortSignal): Promise<BlickEntry> {
  return bodyOf(await postJson('dev/query', request, signal), isEntry, 'dev/query')
}

/**
 * Load the run of the folders `paths`, which `dev/runs` lists, as one run, in place of the run
 * served, if any; its id once `blicket dev` serves it. The answer comes when the loader is done
 * and the baseline found, after a cheap Blick that builds is built.
 */
export async function postRun(paths: string[]): Promise<string> {
  return (await bodyOf(await postJson('dev/run', { paths }), isLoaded, 'dev/run')).id
}

/**
 * Ask `blicket dev` to build the Blick `id`, once more with `rebuild`; what it says of the Blick.
 * The answer comes at once: the build runs on its own, and `dev/info` follows it.
 */
export async function postBuild(id: string, rebuild = false): Promise<BuildAnswer> {
  return (await bodyOf(await postJson('dev/build', { id, rebuild }), isBuildAnswer, 'dev/build')).state
}

/** Why a request failed, as the page says it, and whether because the server did not answer. */
export function failure(cause: unknown): { message: string, unreachable: boolean } {
  const message = cause instanceof Error ? cause.message : String(cause)
  return { message: message || 'the request failed', unreachable: cause instanceof Unreachable }
}
