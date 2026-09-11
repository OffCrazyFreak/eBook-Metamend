import { useCallback, useEffect, useRef, useState } from 'react'

import type { BookResult, RunEvent } from '@/types'

import { applyEvent, fromFileNames, simulateRun, type Simulation } from './simulate'

export type Phase = 'idle' | 'loading' | 'running' | 'done'

export interface RunState {
  phase: Phase
  loading: { progress: number; label: string }
  books: BookResult[]
  elapsedMs: number
  // Which stem is being queried right now, for the row that gets the cursor.
  active: string | null
}

const INITIAL: RunState = {
  phase: 'idle',
  loading: { progress: 0, label: '' },
  books: [],
  elapsedMs: 0,
  active: null,
}

// One state machine for every variation. Phase 2 swaps simulateRun for the
// worker and nothing above this line changes.
export function useRun(options: { perBookMs?: number; loadingMs?: number } = {}) {
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

  const start = useCallback(
    (names: string[]) => {
      simulation.current?.cancel()
      const books = names.length ? fromFileNames(names) : undefined
      setState({ ...INITIAL, phase: 'loading' })
      simulation.current = simulateRun(handle, { ...options, books })
    },
    [handle, options.perBookMs, options.loadingMs],
  )

  const reset = useCallback(() => {
    simulation.current?.cancel()
    setState(INITIAL)
  }, [])

  useEffect(() => () => simulation.current?.cancel(), [])

  return { state, start, reset }
}
