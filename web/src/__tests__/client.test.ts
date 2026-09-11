// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Client, RuntimeFailed } from '@/run/client'
import type { Proposal } from '@/types'
import type { FromWorker, ToWorker } from '@/worker/protocol'

type Posted = { message: ToWorker; transfer: Transferable[] }

// Stands in for the browser's Worker: records what the page posts and lets a
// test post replies back, so the protocol can be walked without Pyodide.
class FakeWorker {
  static instances: FakeWorker[] = []
  posted: Posted[] = []
  onmessage: ((event: MessageEvent<FromWorker>) => void) | null = null
  onerror: ((event: ErrorEvent) => void) | null = null
  terminated = false
  constructor() {
    FakeWorker.instances.push(this)
  }
  postMessage(message: ToWorker, transfer: Transferable[] = []) {
    this.posted.push({ message, transfer })
  }
  terminate() {
    this.terminated = true
  }
  reply(message: FromWorker) {
    this.onmessage?.({ data: message } as MessageEvent<FromWorker>)
  }
  fail(message: string) {
    this.onerror?.({ message } as ErrorEvent)
  }
}

const proposal = { stem: 'A - B', conf: 'HIGH' } as unknown as Proposal

function make() {
  const events: FromWorker[] = []
  const client = new Client((event) => events.push(event))
  const worker = FakeWorker.instances[FakeWorker.instances.length - 1]
  return { client, worker, events }
}

beforeEach(() => {
  FakeWorker.instances = []
  vi.stubGlobal('Worker', FakeWorker)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('Client', () => {
  it('starts the worker with the base the page is served from', () => {
    vi.stubEnv('BASE_URL', '/eBook-Metamend/')
    const { worker } = make()
    expect(worker.posted).toHaveLength(1)
    expect(worker.posted[0].message).toEqual({
      type: 'init',
      base: 'http://localhost:3000/eBook-Metamend/',
    })
  })

  it('resolves ready once the worker says so and forwards the loading events', async () => {
    const { client, worker, events } = make()
    worker.reply({ type: 'loading', progress: 0.5, label: 'Unpacking' })
    worker.reply({ type: 'ready' })
    await expect(client.ready()).resolves.toBeUndefined()
    expect(events.map((e) => e.type)).toEqual(['loading', 'ready'])
  })

  it('rejects ready with the worker reason when the runtime fails to load', async () => {
    const { client, worker, events } = make()
    const ready = client.ready()
    worker.reply({ type: 'failed', message: 'No wheel' })
    await expect(ready).rejects.toBeInstanceOf(RuntimeFailed)
    await expect(ready).rejects.toThrow('No wheel')
    expect(events).toEqual([{ type: 'failed', message: 'No wheel' }])
  })

  it('rejects ready when the worker itself cannot start', async () => {
    const { client, worker, events } = make()
    const ready = client.ready()
    worker.fail('')
    await expect(ready).rejects.toThrow('The worker could not start.')
    expect(events).toEqual([{ type: 'failed', message: 'The worker could not start.' }])
  })

  it('matches a proposal to its request by id and transfers the bytes', async () => {
    const { client, worker } = make()
    const epub = new ArrayBuffer(4)
    const pending = client.propose('A - B', { '.epub': epub })
    const sent = worker.posted[1]
    expect(sent.message).toMatchObject({ type: 'propose', id: 1, stem: 'A - B' })
    expect(sent.transfer).toEqual([epub])
    expect(client.live).toBe(1)
    // Another request's reply must not settle this one.
    worker.reply({
      type: 'proposed',
      id: 2,
      facts: {} as never,
      proposal,
      pause: 0,
      unavailable: [],
    })
    worker.reply({
      type: 'proposed',
      id: 1,
      facts: {} as never,
      proposal,
      pause: 3,
      unavailable: ['openlib'],
    })
    await expect(pending).resolves.toMatchObject({ id: 1, pause: 3, unavailable: ['openlib'] })
  })

  it('gives each request a fresh id', () => {
    const { client, worker } = make()
    void client.propose('one', {})
    void client.propose('two', {})
    const ids = worker.posted.slice(1).map((p) => (p.message as { id: number }).id)
    expect(ids).toEqual([1, 2])
    expect(client.live).toBe(2)
  })

  it('rejects a request the worker answers with an error', async () => {
    const { client, worker } = make()
    const pending = client.apply('A - B', {}, proposal)
    worker.reply({ type: 'error', id: 1, message: 'Not an EPUB' })
    await expect(pending).rejects.toThrow('Not an EPUB')
  })

  it('resolves apply with the repaired bytes and the write outcomes', async () => {
    const { client, worker } = make()
    const pending = client.apply('A - B', { '.pdf': new ArrayBuffer(2) }, proposal)
    const repaired = new ArrayBuffer(8)
    worker.reply({
      type: 'applied',
      id: 1,
      files: { '.pdf': repaired },
      writes: [{ ext: '.pdf', ok: true, reason: '' }],
    })
    const reply = await pending
    expect(reply.files['.pdf']).toBe(repaired)
    expect(reply.writes).toEqual([{ ext: '.pdf', ok: true, reason: '' }])
  })

  it('forwards answers with the id of the request they belong to', () => {
    const { worker, events } = make()
    worker.reply({ type: 'answer', id: 1, stem: 'A - B', source: 'apple' })
    expect(events).toEqual([{ type: 'answer', id: 1, stem: 'A - B', source: 'apple' }])
  })

  it('posts reset and terminates the worker on request', () => {
    const { client, worker } = make()
    client.reset()
    expect(worker.posted[1].message).toEqual({ type: 'reset' })
    client.terminate()
    expect(worker.terminated).toBe(true)
  })
})
