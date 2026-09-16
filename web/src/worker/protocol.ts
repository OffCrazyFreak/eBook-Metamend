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
  // A new run: shelved catalogues and back-off from the last one are forgotten.
  | { type: 'reset' }
  // What each filename claims, read by the same parser the verdicts use, so the
  // rows never show a second parser's reading while they wait.
  | { type: 'facts'; id: number; stems: string[] }
  | { type: 'propose'; id: number; stem: string; files: FileBytes }
  | { type: 'apply'; id: number; stem: string; files: FileBytes; proposal: Proposal }

export type FromWorker =
  | { type: 'loading'; progress: number; label: string }
  | { type: 'ready' }
  | { type: 'failed'; message: string }
  // id names the propose request, so an answer for a stopped one can be told apart.
  | { type: 'answer'; id: number; stem: string; source: SourceName }
  | { type: 'facts'; id: number; facts: FilenameFacts[] }
  | {
      type: 'proposed'
      id: number
      facts: FilenameFacts
      proposal: Proposal | null
      // Seconds to wait before the next book, so every catalogue keeps its rate.
      pause: number
      // Catalogues shelved after failing several books in a row.
      unavailable: SourceName[]
    }
  | { type: 'applied'; id: number; files: FileBytes; writes: WriteOutcome[] }
  | { type: 'error'; id: number; message: string }
