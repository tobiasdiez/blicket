import { afterEach, describe, expect, it, vi } from 'vitest'
import { Unreachable, bodyOf, failure, isEntry, isInfo, isNoRun, isOptions, isRunList, postBuild, postQuery, postRun } from '../app/lib/dev'

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const request = { quantities: ['flows/a'], plot: 'line', mapping: { x: 'Time' }, keep: [], values: {} }

describe('requests to blicket dev', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls a server that does not answer unreachable, with a message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    const caught = await postQuery(request).catch((cause: unknown) => cause)
    expect(caught).toBeInstanceOf(Unreachable)
    const why = failure(caught)
    expect(why.unreachable).toBe(true)
    expect(why.message).toBe('It may have stopped; check the terminal.')
  })

  it('leaves an abort an abort', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('aborted', 'AbortError')
    }))
    const caught = await postQuery(request).catch((cause: unknown) => cause)
    expect(caught).not.toBeInstanceOf(Unreachable)
    expect(failure(caught).unreachable).toBe(false)
  })

  it('takes the message of an error answer, and refuses a body of another shape', async () => {
    await expect(bodyOf(answer({ message: 'no dataset' }, 404), isOptions, 'dev/dataset')).rejects.toThrow('no dataset')
    await expect(bodyOf(new Response('<html>', { status: 502, statusText: 'Bad Gateway' }), isOptions, 'dev/dataset')).rejects.toThrow('dev/dataset: 502 Bad Gateway')
    await expect(bodyOf(answer(null), isOptions, 'dev/dataset')).rejects.toThrow('dev/dataset: the answer is not what the viewer expects')
    const options = { quantities: [], dimensions: [], plots: [] }
    expect(await bodyOf(answer(options), isOptions, 'dev/dataset')).toEqual(options)
    expect(isEntry({ name: 'builder/query', status: 'error', problems: [] })).toBe(true)
    expect(isEntry({ name: 'builder/query', status: 'skipped', problems: [] })).toBe(true)
    expect(isEntry({ name: 'builder/query', status: 'broken', problems: [] })).toBe(false)
    expect(isEntry({ message: 'no dataset' })).toBe(false)
    const info = { root: '/p', dataset: false, message: 'no dataset(run)', failed: false, session: 's', revision: 0, jobs: [], stopped: null }
    expect(isInfo(info)).toBe(true)
    const job = { id: 'a/b', state: 'building', asked: true, since: '2026-11-11T12:01:05Z', seconds: 3 }
    expect(isInfo({ ...info, jobs: [job] })).toBe(true)
    expect(isInfo({ ...info, jobs: [{ ...job, asked: false }] })).toBe(true) // the background's
    expect(isInfo({ ...info, jobs: [{ ...job, state: 'done' }] })).toBe(false)
    expect(isInfo({ ...info, jobs: [{ ...job, seconds: undefined }] })).toBe(false)
    expect(isInfo({ ...info, jobs: [{ ...job, asked: undefined }] })).toBe(false)
    expect(isInfo({ message: 'no route' })).toBe(false)
    expect(failure(new Error('')).message).toBe('the request failed')
  })

  it('loads the runs picked with a POST to dev/run, and says why one cannot be loaded', async () => {
    const sent: { path: string, init: RequestInit | undefined }[] = []
    const answers = [answer({ id: 'b' }), answer({ message: 'loader blicketconf:load_run raised RuntimeError: old pickle' }, 422)]
    vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
      sent.push({ path, init })
      return answers.shift()!
    }))
    expect(await postRun(['/data/b'])).toBe('b')
    expect(sent[0]!.path).toBe('./dev/run')
    expect(sent[0]!.init?.method).toBe('POST')
    expect(new Headers(sent[0]!.init?.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(String(sent[0]!.init?.body))).toEqual({ paths: ['/data/b'] })
    await expect(postRun(['/data/a', '/data/b'])).rejects.toThrow('loader blicketconf:load_run raised RuntimeError: old pickle')
    expect(JSON.parse(String(sent[1]!.init?.body))).toEqual({ paths: ['/data/a', '/data/b'] })
  })

  it('asks for a build with a POST to dev/build, and says why it was refused', async () => {
    const sent: { path: string, init: RequestInit | undefined }[] = []
    const answers = [answer({ state: 'queued', revision: 0 }), answer({ message: 'no Blick steel/none to build' }, 404), answer({ state: 'built' })]
    vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
      sent.push({ path, init })
      return answers.shift()!
    }))
    expect(await postBuild('steel/trade')).toBe('queued')
    expect([sent[0]!.path, sent[0]!.init?.method]).toEqual(['./dev/build', 'POST'])
    expect(JSON.parse(String(sent[0]!.init?.body))).toEqual({ id: 'steel/trade', rebuild: false })
    await expect(postBuild('steel/none', true)).rejects.toThrow('no Blick steel/none to build')
    expect(JSON.parse(String(sent[1]!.init?.body))).toEqual({ id: 'steel/none', rebuild: true })
    await expect(postBuild('steel/trade')).rejects.toThrow('dev/build: the answer is not what the viewer expects')
  })

  it('checks the shape of dev/runs, with the project itself, which has no time', () => {
    const run = { path: '/data/b', name: 'b', modified: '2026-10-26T10:25:13Z', project: false, served: false }
    const project = { path: '/p', name: 'This project', modified: null, project: true, served: true }
    expect(isRunList({ patterns: ['.', '../data/*'], runs: [project, run] })).toBe(true)
    expect(isRunList({ patterns: [], runs: [] })).toBe(true)
    expect(isRunList({ patterns: [], runs: [{ ...run, modified: 1 }] })).toBe(false)
    expect(isRunList({ patterns: [], runs: [{ ...run, project: undefined }] })).toBe(false)
    expect(isRunList({ patterns: [], runs: [{ ...run, served: undefined }] })).toBe(false)
    expect(isRunList({ runs: [] })).toBe(false)
  })

  it('takes a 404 of manifest.json for no run only when blicket dev answers it', () => {
    const dev = { 'Blicket-Dev': '1' }
    expect(isNoRun(new Response('{}', { status: 404, headers: dev }))).toBe(true)
    expect(isNoRun(new Response('{}', { status: 404 }))).toBe(false) // a static host
    expect(isNoRun(new Response('{}', { status: 200, headers: dev }))).toBe(false)
    expect(isNoRun(new Response('{}', { status: 500, headers: dev }))).toBe(false)
  })
})
