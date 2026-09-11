// The messages between the page and the Python worker. One book per request,
// so the worker holds one book's bytes at a time and the page keeps the list.

import type { Extension, FilenameFacts, Proposal, SourceName } from '@/types'

export type FileBytes = Partial<Record<Extension, ArrayBuffer>>

export interface WriteOutcome {
  ext: Extension
  ok: boolean
  reason: string
}

export type ToWorker =
  | { type: 'init'; base: string }
  | { type: 'propose'; id: number; stem: string; files: FileBytes }
  | { type: 'apply'; id: number; stem: string; files: FileBytes; proposal: Proposal }
  | { type: 'bundle'; id: number; files: Record<string, ArrayBuffer> }

export type FromWorker =
  | { type: 'loading'; progress: number; label: string }
  | { type: 'ready' }
  | { type: 'failed'; message: string }
  | { type: 'answer'; stem: string; source: SourceName }
  | {
      type: 'proposed'
      id: number
      facts: FilenameFacts
      proposal: Proposal | null
      // Seconds to wait before the next book, so every catalogue keeps its rate.
      pause: number
    }
  | { type: 'applied'; id: number; files: FileBytes; writes: WriteOutcome[] }
  | { type: 'bundled'; id: number; zip: ArrayBuffer }
  | { type: 'error'; id: number; message: string }
