import { afterEach, describe, expect, it, vi } from 'vitest'
import { Unreachable, bodyOf, failure, isEntry, isInfo, isOptions, postQuery } from '../app/lib/dev'

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
    expect(isEntry({ message: 'no dataset' })).toBe(false)
    expect(isInfo({ root: '/p', dataset: false, message: 'no dataset(run)', failed: false })).toBe(true)
    expect(isInfo({ message: 'no route' })).toBe(false)
    expect(failure(new Error('')).message).toBe('the request failed')
  })
})
