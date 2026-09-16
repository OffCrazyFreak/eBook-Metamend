// The page's side of the worker protocol: one worker, requests matched to
// replies by id, and broadcast events (loading, answers) handed to a listener.

import type { FilenameFacts, Proposal } from '@/types'

import type { FileBytes, FromWorker, ToWorker, WriteOutcome } from '@/worker/protocol'

type Broadcast = Extract<FromWorker, { type: 'loading' | 'ready' | 'failed' | 'answer' }>
type Reply = Exclude<FromWorker, Broadcast>

export class RuntimeFailed extends Error {}

export class Client {
  private worker: Worker
  private nextId = 1
  private pending = new Map<number, (reply: Reply) => void>()
  private readyPromise: Promise<void>

  constructor(onEvent: (event: Broadcast) => void) {
    this.worker = new Worker(new URL('../worker/metamend.worker.ts', import.meta.url), {
      type: 'module',
    })
    let resolve!: () => void
    let reject!: (error: Error) => void
    this.readyPromise = new Promise<void>((res, rej) => {
      resolve = res
      reject = rej
    })
    this.worker.onmessage = (event: MessageEvent<FromWorker>) => {
      const message = event.data
      switch (message.type) {
        case 'ready':
          resolve()
          onEvent(message)
          return
        case 'failed':
          reject(new RuntimeFailed(message.message))
          onEvent(message)
          return
        case 'loading':
        case 'answer':
          onEvent(message)
          return
        default:
          this.pending.get(message.id)?.(message)
          this.pending.delete(message.id)
      }
    }
    this.worker.onerror = (event) => {
      reject(new RuntimeFailed(event.message || 'The worker could not start.'))
      onEvent({ type: 'failed', message: event.message || 'The worker could not start.' })
    }
    // Pyodide and the wheels live beside the page, whatever path it is served from.
    this.send({ type: 'init', base: new URL(import.meta.env.BASE_URL, window.location.href).href })
  }

  ready(): Promise<void> {
    return this.readyPromise
  }

  // Forget the last run's shelved catalogues and back-off before a new one.
  reset() {
    this.send({ type: 'reset' })
  }

  private send(message: ToWorker, transfer: Transferable[] = []) {
    this.worker.postMessage(message, transfer)
  }

  private request<T extends Reply>(
    build: (id: number) => ToWorker,
    transfer: Transferable[] = [],
  ): Promise<T> {
    const id = this.nextId++
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, (reply) => {
        if (reply.type === 'error') reject(new Error(reply.message))
        else resolve(reply as T)
      })
      this.send(build(id), transfer)
    })
  }

  // What each filename claims, from the parser inside the worker.
  async facts(stems: string[]): Promise<FilenameFacts[]> {
    const reply = await this.request<Extract<Reply, { type: 'facts' }>>((id) => ({
      type: 'facts',
      id,
      stems,
    }))
    return reply.facts
  }

  // The id of the propose request in flight, for telling its answers apart.
  live = 0

  propose(stem: string, files: FileBytes) {
    return this.request<Extract<Reply, { type: 'proposed' }>>((id) => {
      this.live = id
      return { type: 'propose', id, stem, files }
    }, Object.values(files))
  }

  apply(
    stem: string,
    files: FileBytes,
    proposal: Proposal,
  ): Promise<{ files: FileBytes; writes: WriteOutcome[] }> {
    return this.request<Extract<Reply, { type: 'applied' }>>(
      (id) => ({ type: 'apply', id, stem, files, proposal }),
      Object.values(files),
    )
  }

  terminate() {
    this.worker.terminate()
  }
}
