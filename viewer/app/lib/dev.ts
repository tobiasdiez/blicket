// Requests to `blicket dev`: what a failed one says, and the shapes of what it answers.
import type { BuilderOptions, BuilderRequest } from './builder'
import type { BlickEntry } from './manifest'

/** `blicket dev` did not answer; the message is what the page says under "Cannot reach blicket dev". */
export class Unreachable extends Error {
  constructor() {
    super('It may have stopped; check the terminal.')
    this.name = 'Unreachable'
  }
}

/**
 * What `dev/info` says, `Info` in src/blicket/serve.py: the project root, and whether the project
 * has a dataset, why not, and whether because `dataset(run)` failed.
 */
export interface DevInfo {
  root: string
  dataset: boolean
  message: string | null
  failed: boolean
}

const isObject = (body: unknown): body is Record<string, unknown> => typeof body === 'object' && body !== null

/** Whether a body is what `dev/info` answers. */
export function isInfo(body: unknown): body is DevInfo {
  return isObject(body) && typeof body.root === 'string' && typeof body.dataset === 'boolean'
}

/** The message of an error answer, `{"message": ...}`, if the body is one. */
export function messageOf(body: unknown): string | null {
  return isObject(body) && typeof body.message === 'string' ? body.message : null
}

/** Whether a body is a manifest entry, as `dev/query` answers one. */
export function isEntry(body: unknown): body is BlickEntry {
  return isObject(body) && typeof body.name === 'string' && (body.status === 'ok' || body.status === 'error') && Array.isArray(body.problems)
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

/** The entry `dev/query` answers to `request`. */
export async function postQuery(request: BuilderRequest, signal?: AbortSignal): Promise<BlickEntry> {
  const response = await devFetch('./dev/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  return bodyOf(response, isEntry, 'dev/query')
}

/** Why a request failed, as the page says it, and whether because the server did not answer. */
export function failure(cause: unknown): { message: string, unreachable: boolean } {
  const message = cause instanceof Error ? cause.message : String(cause)
  return { message: message || 'the request failed', unreachable: cause instanceof Unreachable }
}
