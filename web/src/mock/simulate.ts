// Plays the invented books back with the timing of a real run, so each
// variation shows live behaviour. Phase 2 replaces this with the worker.

import type { BookResult, RunEvent } from '@/types'

import { MOCK_BOOKS, parseStem } from './books'

const LOADING_STEPS = [
  'Fetching the Python runtime',
  'Unpacking the standard library',
  'Installing eBook Metamend',
  'Installing pypdf',
]

export interface Simulation {
  cancel(): void
}

export function simulateRun(
  onEvent: (event: RunEvent) => void,
  options: {
    books?: BookResult[]
    perBookMs?: number
    loadingMs?: number
    // Stop the runtime fetch partway, to show the failure screen.
    failLoad?: boolean
  } = {},
): Simulation {
  const books = (options.books ?? MOCK_BOOKS).map((b) => ({ ...b, status: 'pending' as const }))
  const perBook = options.perBookMs ?? 600
  const loadingMs = options.loadingMs ?? 1800
  const timers: number[] = []
  const at = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms))

  LOADING_STEPS.forEach((label, i) => {
    at((loadingMs * i) / LOADING_STEPS.length, () =>
      onEvent({ type: 'loading', progress: i / LOADING_STEPS.length, label }),
    )
  })
  if (options.failLoad) {
    at(loadingMs * 0.6, () =>
      onEvent({
        type: 'failed',
        message: 'The Python runtime could not be fetched. Check the connection and try again.',
      }),
    )
    return { cancel: () => timers.forEach((t) => window.clearTimeout(t)) }
  }
  at(loadingMs, () => {
    onEvent({ type: 'loading', progress: 1, label: 'Ready' })
    onEvent({ type: 'ready', books })
  })

  books.forEach((book, i) => {
    const start = loadingMs + 200 + i * perBook
    at(start, () => onEvent({ type: 'querying', stem: book.stem }))
    const sources = book.proposal?.sources ?? []
    sources.forEach((source, n) => {
      at(start + (perBook * 0.8 * (n + 1)) / (sources.length + 1), () =>
        onEvent({ type: 'answer', stem: book.stem, source }),
      )
    })
    at(start + perBook * 0.8, () => onEvent({ type: 'book', result: { ...book, status: 'done' } }))
  })
  const end = loadingMs + 200 + books.length * perBook
  at(end, () => onEvent({ type: 'done', elapsedMs: end - loadingMs }))

  return { cancel: () => timers.forEach((t) => window.clearTimeout(t)) }
}

// The shared list reducer every variation uses; keeps the ordering stable.
export function applyEvent(list: BookResult[], event: RunEvent): BookResult[] {
  switch (event.type) {
    case 'ready':
      return event.books
    case 'querying':
      return list.map((b) => (b.stem === event.stem ? { ...b, status: 'querying' } : b))
    case 'answer':
      return list.map((b) =>
        b.stem === event.stem ? { ...b, answered: [...(b.answered ?? []), event.source] } : b,
      )
    case 'book':
      return list.map((b) => (b.stem === event.result.stem ? event.result : b))
    default:
      return list
  }
}

// Files chosen by the visitor become pending rows; the simulation then plays
// the invented verdicts over them so the intake feels real in the design round.
export function fromFileNames(names: string[]): BookResult[] {
  const stems = new Map<string, BookResult>()
  for (const name of names) {
    const match = /^(.*)\.(epub|pdf)$/i.exec(name)
    if (!match) continue
    const stem = match[1]
    const ext = `.${match[2].toLowerCase()}` as '.epub' | '.pdf'
    const existing = stems.get(stem)
    if (existing) {
      if (!existing.files.includes(ext)) existing.files.push(ext)
      continue
    }
    const template = MOCK_BOOKS[stems.size % MOCK_BOOKS.length]
    stems.set(stem, {
      ...template,
      stem,
      facts: parseStem(stem),
      files: [ext],
      status: 'pending',
      proposal: template.proposal ? { ...template.proposal, stem } : null,
    })
  }
  return [...stems.values()]
}
