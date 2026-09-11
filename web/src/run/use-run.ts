import { downloadZip } from 'client-zip'
import { useCallback, useEffect, useRef, useState } from 'react'

import { groupBooks, type Intake, type IntakeBook } from '@/intake'
import { parseStem } from '@/mock/books'
import { applyEvent, simulateRun, type Simulation } from '@/mock/simulate'
import type { BookResult, Extension, RunEvent, SourceName } from '@/types'
import type { FileBytes } from '@/worker/protocol'

import { Client } from './client'

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
  // The invented sample plays without files, so nothing can be written or downloaded.
  sample: boolean
  // Catalogues the worker shelved after repeated failures during this run.
  unavailable: SourceName[]
}

const INITIAL: RunState = {
  phase: 'idle',
  loading: { progress: 0, label: '' },
  error: null,
  books: [],
  elapsedMs: 0,
  active: null,
  sample: false,
  unavailable: [],
}

export type Outcome = 'written' | 'downloaded'

// Files a repair produced but could not place: returned so the page can say so.
export interface RepairResult {
  outcomes: Map<string, Outcome>
  failures: string[]
}

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

// Beyond this many files a download becomes one zip; a browser prompts per file otherwise.
const LOOSE_DOWNLOADS = 5

export function useRun(options: { failLoad?: boolean } = {}) {
  const [state, setState] = useState<RunState>(INITIAL)
  const simulation = useRef<Simulation | null>(null)
  const client = useRef<Client | null>(null)
  // The books of the current real run, by stem, with their bytes and handles.
  const intake = useRef<Map<string, IntakeBook>>(new Map())
  const folders = useRef<FileSystemDirectoryHandle[]>([])
  // Bumped on every start, stop and reset so a stale run's events are dropped.
  const token = useRef(0)
  const readyAt = useRef(0)

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
          readyAt.current = Date.now()
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

  // One worker for the page's whole life; its callback reads the live run's
  // state through refs rather than closing over the run that created it.
  const runtime = useCallback(() => {
    if (client.current) return client.current
    client.current = new Client((event) => {
      if (event.type === 'ready') return
      // An answer for a request that was stopped belongs to no row on screen.
      if (event.type === 'answer' && event.id !== client.current?.live) return
      handle(event)
    })
    return client.current
  }, [handle])

  const lastIntake = useRef<Intake | null>(null)
  const start = useCallback(
    async (chosen: Intake) => {
      simulation.current?.cancel()
      const mine = ++token.current
      lastIntake.current = chosen
      const books = groupBooks(chosen.books)
      intake.current = new Map(books.map((b) => [b.stem, b]))
      folders.current = chosen.folders
      const rows: BookResult[] = books.map((b) => ({
        stem: b.stem,
        files: Object.keys(b.files).sort() as Extension[],
        facts: parseStem(b.stem.slice(b.stem.lastIndexOf('/') + 1)),
        status: 'pending',
        proposal: null,
      }))
      setState({ ...INITIAL, phase: 'loading', books: rows })
      const py = runtime()
      try {
        await py.ready()
      } catch {
        // The client already reported the failure through the event stream.
        return
      }
      if (token.current !== mine) return
      py.reset()
      handle({ type: 'ready', books: rows })
      for (const row of rows) {
        if (token.current !== mine) return
        const book = intake.current.get(row.stem)!
        handle({ type: 'querying', stem: row.stem })
        let result: BookResult
        let pause = 0
        let unavailable: SourceName[] = []
        try {
          const reply = await py.propose(row.stem, await bytesOf(book))
          pause = reply.pause
          unavailable = reply.unavailable
          result = { ...row, facts: reply.facts, status: 'done', proposal: reply.proposal }
        } catch (error) {
          // One book failing to be read or scored must not end the run.
          result = { ...row, status: 'done', proposal: unreadable(row, describe(error)) }
        }
        if (token.current !== mine) return
        handle({ type: 'book', result })
        if (unavailable.length) setState((prev) => ({ ...prev, unavailable }))
        if (pause > 0 && row !== rows[rows.length - 1]) await sleep(pause * 1000)
      }
      if (token.current !== mine) return
      handle({ type: 'done', elapsedMs: Date.now() - readyAt.current })
    },
    [handle, runtime],
  )

  const playSample = useCallback(() => {
    simulation.current?.cancel()
    ++token.current
    intake.current = new Map()
    setState({ ...INITIAL, phase: 'loading', sample: true })
    simulation.current = simulateRun(handle, { failLoad: options.failLoad })
  }, [handle, options.failLoad])

  // Same files, another go at the runtime. A fresh worker, since the old one
  // may be half loaded.
  const retry = useCallback(() => {
    if (state.sample) {
      simulation.current?.cancel()
      ++token.current
      setState({ ...INITIAL, phase: 'loading', sample: true })
      simulation.current = simulateRun(handle, { failLoad: false })
      return
    }
    client.current?.terminate()
    client.current = null
    if (lastIntake.current) void start(lastIntake.current)
  }, [handle, start, state.sample])

  const reset = useCallback(() => {
    simulation.current?.cancel()
    ++token.current
    intake.current = new Map()
    setState(INITIAL)
  }, [])

  // Keeps every verdict already reached; the rest are marked skipped. A book
  // mid-query finishes in the worker and its answer is dropped.
  const stop = useCallback(() => {
    simulation.current?.cancel()
    ++token.current
    // Whatever the worker is still answering belongs to nobody now.
    if (client.current) client.current.live = 0
    setState((prev) => ({
      ...prev,
      phase: 'done',
      active: null,
      elapsedMs: Date.now() - readyAt.current,
      books: prev.books.map((b) => (b.status === 'done' ? b : { ...b, status: 'skipped' })),
    }))
  }, [])

  // Write the gains into the chosen books and hand them out: back into their
  // files when the browser gave handles, otherwise as downloads.
  const repair = useCallback(
    async (books: BookResult[], mode: Outcome): Promise<RepairResult> => {
      const outcomes = new Map<string, Outcome>()
      const failures: string[] = []
      if (state.sample || !client.current) {
        for (const b of books) outcomes.set(b.stem, mode)
        return { outcomes, failures }
      }
      const py = client.current
      if (mode === 'written') {
        // Permission prompts need the click that started this; ask before any work.
        const granted = await requestWrite(
          books.map((b) => intake.current.get(b.stem)!),
          folders.current,
        )
        if (!granted) return { outcomes, failures: ['Write access was not granted.'] }
      }
      const chosen = books.filter((b) => b.proposal)
      // One book's bytes at a time: the zip pulls each book as it is written,
      // so nothing is held for the whole selection.
      async function* repaired(): AsyncGenerator<{ name: string; input: ArrayBuffer }> {
        for (const b of chosen) {
          const book = intake.current.get(b.stem)!
          try {
            const { files, writes } = await py.apply(b.stem, await bytesOf(book), b.proposal!)
            const failed = writes.filter((w) => !w.ok)
            if (failed.length) {
              failures.push(`${b.stem}: ${failed.map((w) => `${w.ext} ${w.reason}`).join(', ')}`)
              continue
            }
            for (const [ext, data] of Object.entries(files) as [Extension, ArrayBuffer][]) {
              const source = book.files[ext]!
              if (mode === 'written') {
                const writable = await source.handle!.createWritable()
                await writable.write(data)
                await writable.close()
              } else {
                yield { name: source.path, input: data }
              }
            }
            outcomes.set(b.stem, mode)
          } catch (error) {
            failures.push(`${b.stem}: ${describe(error)}`)
          }
        }
      }
      const count = chosen.reduce(
        (n, b) => n + Object.keys(intake.current.get(b.stem)!.files).length,
        0,
      )
      if (mode === 'downloaded' && count > LOOSE_DOWNLOADS) {
        // A Response body becomes a Blob the browser may keep on disk, unlike an ArrayBuffer.
        const zip = await downloadZip(repaired(), { buffersAreUTF8: true }).blob()
        download('ebook-metamend-repaired.zip', zip)
      } else {
        for await (const { name, input } of repaired()) {
          download(name.slice(name.lastIndexOf('/') + 1), new Blob([input]))
        }
      }
      return { outcomes, failures }
    },
    [state.sample],
  )

  // Whether every file of these books came with a handle to write back through.
  const writable = useCallback(
    (books: BookResult[]) =>
      state.sample ||
      books.every((b) =>
        Object.values(intake.current.get(b.stem)?.files ?? {}).every((f) => f?.handle),
      ),
    [state.sample],
  )

  useEffect(
    () => () => {
      simulation.current?.cancel()
      client.current?.terminate()
    },
    [],
  )

  return { state, start, playSample, reset, stop, retry, repair, writable }
}

async function bytesOf(book: IntakeBook): Promise<FileBytes> {
  const out: FileBytes = {}
  for (const [ext, f] of Object.entries(book.files) as [
    Extension,
    IntakeBook['files']['.epub'],
  ][]) {
    if (!f) continue
    // A File snapshot goes stale once its file is written; the handle reads
    // the current bytes, so a book written once can still be read again.
    const file = f.handle ? await f.handle.getFile() : f.file
    out[ext] = await file.arrayBuffer()
  }
  return out
}

// A book the worker could not handle reads as unreadable, with the reason in
// the place a title would be, so the row says something rather than nothing.
function unreadable(row: BookResult, reason: string): BookResult['proposal'] {
  return {
    stem: row.stem,
    files: {},
    conf: 'LOW',
    sources: [],
    gains: {},
    merged: empty(),
    fn_score: 0,
    au_score: 0,
    src_titles: {},
    scores: [],
    current: empty(reason),
    unreadable: true,
  }
}

function empty(title = '') {
  return {
    title,
    authors: [],
    publisher: '',
    description: '',
    tags: [],
    series: null,
    sidx: null,
    isbn: '',
  }
}

// One prompt per dropped or picked folder (its files inherit), one per loose file.
async function requestWrite(
  books: IntakeBook[],
  folders: FileSystemDirectoryHandle[],
): Promise<boolean> {
  const handles = new Set<FileSystemHandle>(folders)
  for (const book of books) {
    for (const f of Object.values(book.files)) if (f?.handle) handles.add(f.handle)
  }
  for (const handle of handles) {
    if ((await handle.queryPermission({ mode: 'readwrite' })) === 'granted') continue
    if ((await handle.requestPermission({ mode: 'readwrite' })) !== 'granted') return false
  }
  return true
}

function download(name: string, data: Blob) {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
