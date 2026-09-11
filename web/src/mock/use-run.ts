import { useCallback, useEffect, useRef, useState } from 'react'

import type { BookResult, RunEvent } from '@/types'

import { applyEvent, fromFileNames, simulateRun, type Simulation } from './simulate'

export type Phase = 'idle' | 'loading' | 'failed' | 'running' | 'done'

export interface RunState {
  phase: Phase
  loading: { progress: number; label: string }
  // Why the runtime did not load, shown under the half-drawn mark.
  error: string | null
  books: BookResult[]
  elapsedMs: number
  // Which stem is being queried right now, for the row that gets the cursor.
  active: string | null
}

const INITIAL: RunState = {
  phase: 'idle',
  loading: { progress: 0, label: '' },
  error: null,
  books: [],
  elapsedMs: 0,
  active: null,
}

// One state machine for every variation. Phase 2 swaps simulateRun for the
// worker and nothing above this line changes.
export function useRun(
  options: { perBookMs?: number; loadingMs?: number; failLoad?: boolean } = {},
) {
  const [state, setState] = useState<RunState>(INITIAL)
  const simulation = useRef<Simulation | null>(null)

  const handle = useCallback((event: RunEvent) => {
    setState((prev) => {
      const books = applyEvent(prev.books, event)
      switch (event.type) {
        case 'loading':
          return {
            ...prev,
            phase: 'loading',
            loading: { progress: event.progress, label: event.label },
          }
        case 'failed':
          return { ...prev, phase: 'failed', error: event.message }
        case 'ready':
          return { ...prev, phase: 'running', books }
        case 'querying':
        case 'answer':
          return { ...prev, books, active: event.stem }
        case 'book':
          return { ...prev, books, active: prev.active === event.result.stem ? null : prev.active }
        case 'done':
          return { ...prev, phase: 'done', books, active: null, elapsedMs: event.elapsedMs }
      }
    })
  }, [])

  const lastNames = useRef<string[]>([])
  const start = useCallback(
    (names: string[]) => {
      simulation.current?.cancel()
      lastNames.current = names
      const books = names.length ? fromFileNames(names) : undefined
      setState({ ...INITIAL, phase: 'loading' })
      simulation.current = simulateRun(handle, { ...options, books })
    },
    [handle, options.perBookMs, options.loadingMs, options.failLoad],
  )

  // Same files, another go at the runtime. The mock succeeds on the retry.
  const retry = useCallback(() => {
    simulation.current?.cancel()
    const names = lastNames.current
    const books = names.length ? fromFileNames(names) : undefined
    setState({ ...INITIAL, phase: 'loading' })
    simulation.current = simulateRun(handle, { ...options, books, failLoad: false })
  }, [handle, options.perBookMs, options.loadingMs])

  const reset = useCallback(() => {
    simulation.current?.cancel()
    setState(INITIAL)
  }, [])

  // Keeps every verdict already reached; the rest are marked skipped.
  const stop = useCallback(() => {
    simulation.current?.cancel()
    setState((prev) => ({
      ...prev,
      phase: 'done',
      active: null,
      books: prev.books.map((b) => (b.status === 'done' ? b : { ...b, status: 'skipped' })),
    }))
  }, [])

  useEffect(() => () => simulation.current?.cancel(), [])

  return { state, start, reset, stop, retry }
}
