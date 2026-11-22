import { describe, expect, it } from 'vitest'
import { Unreachable } from '../app/lib/dev'
import { failureState, reloadable } from '../app/lib/resource'

/** A read whose answers come when the test says, in any order, of the revision `revision`, if any. */
function reads<T>(revision?: number) {
  const pending: { resolve: (value: T) => void, reject: (cause: unknown) => void }[] = []
  const revisions = revision === undefined ? [] : [revision]
  const read = () => new Promise<T>((resolve, reject) => pending.push({ resolve, reject })).then(data => ({ data, revisions }))
  return { read, pending }
}

describe('a resource read again', () => {
  it('says why the first read failed, and shows the next', async () => {
    const { read, pending } = reads<string>()
    const resource = reloadable(read)
    const first = resource.reload()
    pending[0]!.reject(new Error('manifest.json: 500'))
    expect(await first).toBe(false)
    expect([resource.data.value, resource.error.value, resource.loading.value]).toEqual([null, 'manifest.json: 500', false])
    const second = resource.reload()
    pending[1]!.resolve('a')
    expect(await second).toBe(true)
    expect([resource.data.value, resource.error.value]).toEqual(['a', null])
  })

  it('keeps what it shows when a read again fails, says so, and that what it shows is older', async () => {
    const { read, pending } = reads<string>()
    const resource = reloadable(read, (before, next) => `${before}+${next}`)
    const first = resource.reload()
    pending[0]!.resolve('a')
    await first
    const again = resource.reload()
    pending[1]!.reject(new Error('compare/index.json: 503'))
    expect(await again).toBe(false)
    expect([resource.data.value, resource.stale.value, resource.error.value]).toEqual(['a', 'compare/index.json: 503', null])
    const third = resource.reload()
    pending[2]!.resolve('b')
    expect(await third).toBe(true)
    expect([resource.data.value, resource.stale.value]).toEqual(['a+b', null])
  })

  it('lets only the latest read count, though an older one answers later', async () => {
    const { read, pending } = reads<string>()
    const resource = reloadable(read)
    const older = resource.reload()
    const newer = resource.reload()
    pending[1]!.resolve('new')
    pending[0]!.resolve('old')
    expect([await older, await newer]).toEqual([false, true])
    expect(resource.data.value).toBe('new')
  })
})

describe('resources read again together', () => {
  it('show nothing of a read until it is shown, so that several change at one moment', async () => {
    const { read, pending } = reads<string>()
    const resource = reloadable(read)
    const first = resource.reload()
    pending[0]!.resolve('a')
    await first
    const fetched = resource.fetch()
    pending[1]!.resolve('b')
    const done = await fetched
    expect(resource.data.value).toBe('a')
    done!.show()
    expect(resource.data.value).toBe('b')
  })

  it('say which revision of blicket dev a read is of, so that reads of one revision are shown together', async () => {
    const { read, pending } = reads<string>(3)
    const resource = reloadable(read)
    const fetched = resource.fetch()
    pending[0]!.resolve('a')
    expect((await fetched)!.revisions).toEqual([3])
  })

  it('show nothing of a read that a later one overtook, and give nothing for a read that failed', async () => {
    const { read, pending } = reads<string>()
    const resource = reloadable(read)
    const older = resource.fetch()
    pending[0]!.resolve('a')
    const done = await older
    const newer = resource.fetch()
    done!.show() // too late: a later read was asked for
    expect(resource.data.value).toBeNull()
    pending[1]!.reject(new Error('gone'))
    expect(await newer).toBeNull()
  })
})

describe('a request that fails', () => {
  it('counts the failures in a row, says when the last was, and whether the server answered', () => {
    const state = failureState()
    state.fail(new Unreachable())
    state.fail(new Error('no Blick to build'))
    expect([state.message.value, state.unreachable.value, state.failures.value]).toEqual(['no Blick to build', false, 2])
    expect(state.failedAt.value).toBeInstanceOf(Date)
    state.clear()
    expect([state.message.value, state.failures.value]).toEqual([null, 0])
  })
})
