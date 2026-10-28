import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { latest, type Outcome } from '../app/lib/latest'

/** A request whose answer comes when the test says. */
function deferred() {
  const calls: { request: string, signal: AbortSignal, resolve: (value: string) => void, reject: (error: unknown) => void }[] = []
  const work = (request: string, signal: AbortSignal) => new Promise<string>((resolve, reject) => {
    calls.push({ request, signal, resolve, reject })
  })
  return { calls, work }
}

describe('running the latest request only', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('waits the delay, so a burst of requests runs once', async () => {
    const { calls, work } = deferred()
    const settled: Outcome<string>[] = []
    const runner = latest(work, outcome => settled.push(outcome), () => 300)
    runner.ask('a')
    runner.ask('b')
    await vi.advanceTimersByTimeAsync(299)
    expect(calls).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls.map(call => call.request)).toEqual(['b'])
    calls[0]!.resolve('answer b')
    await vi.runAllTimersAsync()
    expect(settled).toEqual([{ value: 'answer b' }])
  })

  it('aborts the running request and ignores its late answer', async () => {
    const { calls, work } = deferred()
    const settled: Outcome<string>[] = []
    const runner = latest(work, outcome => settled.push(outcome), () => 0)
    runner.ask('a')
    await vi.advanceTimersByTimeAsync(0)
    runner.ask('b')
    await vi.advanceTimersByTimeAsync(0)
    expect(calls[0]!.signal.aborted).toBe(true)
    calls[1]!.resolve('answer b')
    calls[0]!.resolve('answer a') // after b's: out of order
    await vi.runAllTimersAsync()
    expect(settled).toEqual([{ value: 'answer b' }])
  })

  it('settles an error, but not the abort of a request asked again', async () => {
    const { calls, work } = deferred()
    const settled: Outcome<string>[] = []
    const runner = latest(work, outcome => settled.push(outcome), () => 0)
    runner.ask('a')
    await vi.advanceTimersByTimeAsync(0)
    runner.ask('b')
    await vi.advanceTimersByTimeAsync(0)
    calls[0]!.reject(new DOMException('aborted', 'AbortError'))
    calls[1]!.reject(new Error('down'))
    await vi.runAllTimersAsync()
    expect(settled).toEqual([{ error: new Error('down') }])
  })

  it('settles nothing once cancelled', async () => {
    const { calls, work } = deferred()
    const settled: Outcome<string>[] = []
    const runner = latest(work, outcome => settled.push(outcome), () => 100)
    runner.ask('a')
    runner.cancel()
    await vi.runAllTimersAsync()
    expect(calls).toHaveLength(0)
    runner.ask('b')
    await vi.advanceTimersByTimeAsync(100)
    runner.cancel()
    calls[0]!.resolve('answer b')
    await vi.runAllTimersAsync()
    expect(settled).toEqual([])
  })
})
