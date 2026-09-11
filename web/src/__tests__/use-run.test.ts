// @vitest-environment happy-dom
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Intake, IntakeFile } from '@/intake'
import { useRun } from '@/run/use-run'
import type { Proposal } from '@/types'
import type { FileBytes, FromWorker, WriteOutcome } from '@/worker/protocol'

type Broadcast = Extract<FromWorker, { type: 'loading' | 'ready' | 'failed' | 'answer' }>
type Proposed = Extract<FromWorker, { type: 'proposed' }>

// Hoisted with the mock below: vi.mock runs before any import, so the fake
// must exist before use-run.ts asks for its Client.
const { FakeClient, script, FACTS } = vi.hoisted(() => {
  const FACTS = { author: 'Ada Example', title: 'Sample', series: null, series_index: null }
  // What the fake worker answers, set per test. A propose that is never
  // answered leaves the run mid-book, which is how stop is exercised.
  const script = {
    propose: (_stem: string, _files: FileBytes): Promise<Omit<Proposed, 'type' | 'id'>> =>
      Promise.resolve({ facts: FACTS, proposal: null, pause: 0, unavailable: [] }),
    apply: (
      _stem: string,
      _files: FileBytes,
      _proposal: Proposal,
    ): Promise<{ files: FileBytes; writes: WriteOutcome[] }> =>
      Promise.resolve({ files: {}, writes: [] }),
  }
  class FakeClient {
    static instances: FakeClient[] = []
    live = 0
    terminated = false
    resets = 0
    onEvent: (event: Broadcast) => void
    private nextId = 1
    constructor(onEvent: (event: Broadcast) => void) {
      FakeClient.instances.push(this)
      this.onEvent = onEvent
    }
    ready() {
      return Promise.resolve()
    }
    reset() {
      this.resets++
    }
    async propose(stem: string, files: FileBytes) {
      const id = this.nextId++
      this.live = id
      const reply = await script.propose(stem, files)
      return { type: 'proposed' as const, id, ...reply }
    }
    apply(stem: string, files: FileBytes, proposal: Proposal) {
      return script.apply(stem, files, proposal)
    }
    terminate() {
      this.terminated = true
    }
  }
  return { FakeClient, script, FACTS }
})

vi.mock('@/run/client', () => ({ Client: FakeClient, RuntimeFailed: class extends Error {} }))

const high = (stem: string): Proposal => ({
  stem,
  files: {},
  conf: 'HIGH',
  sources: ['apple', 'openlib'],
  gains: { tags: ['Essays'] },
  merged: empty(),
  fn_score: 1,
  au_score: 1,
  src_titles: {},
  scores: [],
  current: empty(),
  unreadable: false,
})

function empty() {
  return {
    title: '',
    authors: [],
    publisher: '',
    description: '',
    tags: [],
    series: null,
    sidx: null,
    isbn: '',
  }
}

function file(path: string, bytes = 'x', handle?: FileSystemFileHandle): IntakeFile {
  const name = path.slice(path.lastIndexOf('/') + 1)
  return { path, file: new File([bytes], name), handle }
}

function intake(files: IntakeFile[]): Intake {
  return { books: files, others: 0, folders: [] }
}

// A writable file handle that records what was written to it.
function fakeHandle(written: Record<string, Uint8Array>, name: string, permission = 'granted') {
  return {
    kind: 'file',
    name,
    queryPermission: () => Promise.resolve(permission),
    requestPermission: () => Promise.resolve(permission),
    getFile: () => Promise.resolve(new File(['old'], name)),
    createWritable: () =>
      Promise.resolve({
        write: (data: ArrayBuffer) => {
          written[name] = new Uint8Array(data)
          return Promise.resolve()
        },
        close: () => Promise.resolve(),
      }),
  } as unknown as FileSystemFileHandle
}

const downloads: { name: string; blob: Blob }[] = []

beforeEach(() => {
  FakeClient.instances = []
  downloads.length = 0
  script.propose = () =>
    Promise.resolve({ facts: FACTS, proposal: null, pause: 0, unavailable: [] })
  script.apply = () => Promise.resolve({ files: {}, writes: [] })
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL(blob: Blob) {
        downloads.push({ name: '', blob })
        return 'blob:fake'
      }
      static revokeObjectURL() {}
    },
  )
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloads[downloads.length - 1].name = this.download
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useRun start', () => {
  it('walks a book from pending to done with the proposal the worker returns', async () => {
    script.propose = (stem) =>
      Promise.resolve({ facts: FACTS, proposal: high(stem), pause: 0, unavailable: [] })
    const { result } = renderHook(() => useRun())
    expect(result.current.state.phase).toBe('idle')
    await act(() => result.current.start(intake([file('Ada Example - Sample.epub')])))
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    const [book] = result.current.state.books
    expect(book.stem).toBe('Ada Example - Sample')
    expect(book.files).toEqual(['.epub'])
    expect(book.status).toBe('done')
    expect(book.proposal?.conf).toBe('HIGH')
    expect(result.current.state.active).toBeNull()
    expect(result.current.state.sample).toBe(false)
    expect(FakeClient.instances).toHaveLength(1)
    expect(FakeClient.instances[0].resets).toBe(1)
  })

  it('groups an EPUB and a PDF with one stem into one row', async () => {
    const { result } = renderHook(() => useRun())
    await act(() =>
      result.current.start(
        intake([file('a/Ada Example - Sample.pdf'), file('a/Ada Example - Sample.epub')]),
      ),
    )
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    expect(result.current.state.books).toHaveLength(1)
    expect(result.current.state.books[0].files).toEqual(['.epub', '.pdf'])
  })

  it('turns a book the worker cannot read into an unreadable row and carries on', async () => {
    script.propose = (stem) =>
      stem.endsWith('Broken')
        ? Promise.reject(new Error('Not a zip'))
        : Promise.resolve({ facts: FACTS, proposal: high(stem), pause: 0, unavailable: [] })
    const { result } = renderHook(() => useRun())
    await act(() =>
      result.current.start(
        intake([file('Ada Example - Broken.epub'), file('Ada Example - Fine.epub')]),
      ),
    )
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    const [broken, fine] = result.current.state.books
    expect(broken.proposal?.unreadable).toBe(true)
    expect(broken.proposal?.conf).toBe('LOW')
    expect(broken.proposal?.current.title).toBe('Not a zip')
    expect(fine.proposal?.conf).toBe('HIGH')
  })

  it('records the catalogues the worker shelved', async () => {
    script.propose = () =>
      Promise.resolve({ facts: FACTS, proposal: null, pause: 0, unavailable: ['openlib'] })
    const { result } = renderHook(() => useRun())
    await act(() => result.current.start(intake([file('Ada Example - Sample.epub')])))
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    expect(result.current.state.unavailable).toEqual(['openlib'])
  })

  it('forwards loading and answer events for the live request only', async () => {
    let release!: () => void
    script.propose = () =>
      new Promise((resolve) => {
        release = () => resolve({ facts: FACTS, proposal: null, pause: 0, unavailable: [] })
      })
    const { result } = renderHook(() => useRun())
    // Not awaited: the run is parked on the held propose.
    act(() => void result.current.start(intake([file('Ada Example - Sample.epub')])))
    await waitFor(() => expect(FakeClient.instances[0].live).toBe(1))
    const client = FakeClient.instances[0]
    act(() => client.onEvent({ type: 'loading', progress: 0.5, label: 'Unpacking' }))
    expect(result.current.state.loading).toEqual({ progress: 0.5, label: 'Unpacking' })
    act(() =>
      client.onEvent({ type: 'answer', id: 1, stem: 'Ada Example - Sample', source: 'apple' }),
    )
    act(() =>
      client.onEvent({ type: 'answer', id: 9, stem: 'Ada Example - Sample', source: 'openlib' }),
    )
    expect(result.current.state.books[0].answered).toEqual(['apple'])
    await act(async () => {
      release()
    })
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
  })
})

describe('useRun stop, reset and retry', () => {
  it('keeps the verdicts reached, marks the rest skipped and drops the late answer', async () => {
    const answered: string[] = []
    let release!: () => void
    script.propose = (stem) => {
      answered.push(stem)
      if (answered.length === 1) {
        return Promise.resolve({ facts: FACTS, proposal: high(stem), pause: 0, unavailable: [] })
      }
      return new Promise((resolve) => {
        release = () => resolve({ facts: FACTS, proposal: high(stem), pause: 0, unavailable: [] })
      })
    }
    const { result } = renderHook(() => useRun())
    act(
      () =>
        void result.current.start(
          intake([
            file('Ada Example - One.epub'),
            file('Ada Example - Two.epub'),
            file('Ada Example - Three.epub'),
          ]),
        ),
    )
    await waitFor(() => expect(answered).toHaveLength(2))
    act(() => result.current.stop())
    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.books.map((b) => b.status)).toEqual(['done', 'skipped', 'skipped'])
    expect(FakeClient.instances[0].live).toBe(0)
    await act(async () => {
      release()
    })
    expect(result.current.state.books[1].status).toBe('skipped')
    expect(result.current.state.books[1].proposal).toBeNull()
  })

  it('reset returns to idle with no books', async () => {
    const { result } = renderHook(() => useRun())
    await act(() => result.current.start(intake([file('Ada Example - Sample.epub')])))
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    act(() => result.current.reset())
    expect(result.current.state.phase).toBe('idle')
    expect(result.current.state.books).toEqual([])
  })

  it('retry replaces the worker and runs the same files again', async () => {
    const { result } = renderHook(() => useRun())
    await act(() => result.current.start(intake([file('Ada Example - Sample.epub')])))
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    await act(async () => {
      result.current.retry()
    })
    await waitFor(() => expect(result.current.state.phase).toBe('done'))
    expect(FakeClient.instances).toHaveLength(2)
    expect(FakeClient.instances[0].terminated).toBe(true)
    expect(result.current.state.books[0].stem).toBe('Ada Example - Sample')
  })

  it('the sample plays without a worker and cannot be written', () => {
    const { result } = renderHook(() => useRun())
    act(() => result.current.playSample())
    expect(result.current.state.sample).toBe(true)
    expect(result.current.state.phase).toBe('loading')
    expect(FakeClient.instances).toHaveLength(0)
    expect(result.current.writable([])).toBe(true)
  })
})

describe('useRun repair', () => {
  async function run(files: IntakeFile[]) {
    script.propose = (stem) =>
      Promise.resolve({ facts: FACTS, proposal: high(stem), pause: 0, unavailable: [] })
    script.apply = (stem, bytes) =>
      Promise.resolve({
        files: Object.fromEntries(
          Object.keys(bytes).map((ext) => [ext, new TextEncoder().encode(`${stem}${ext}`).buffer]),
        ) as FileBytes,
        writes: Object.keys(bytes).map((ext) => ({ ext: ext as '.epub', ok: true, reason: '' })),
      })
    const hook = renderHook(() => useRun())
    await act(() => hook.result.current.start(intake(files)))
    await waitFor(() => expect(hook.result.current.state.phase).toBe('done'))
    return hook
  }

  it('downloads each file on its own up to five', async () => {
    const { result } = await run([
      file('lib/Ada Example - One.epub'),
      file('lib/Ada Example - One.pdf'),
      file('lib/Ada Example - Two.epub'),
    ])
    const outcome = await result.current.repair(result.current.state.books, 'downloaded')
    expect(downloads.map((d) => d.name)).toEqual([
      'Ada Example - One.epub',
      'Ada Example - One.pdf',
      'Ada Example - Two.epub',
    ])
    expect(await downloads[1].blob.text()).toBe('lib/Ada Example - One.pdf')
    expect([...outcome.outcomes]).toEqual([
      ['lib/Ada Example - One', 'downloaded'],
      ['lib/Ada Example - Two', 'downloaded'],
    ])
    expect(outcome.failures).toEqual([])
  })

  it('downloads one zip beyond five files, with every file under its own path', async () => {
    const names = ['One', 'Two', 'Three'].flatMap((n) => [
      `lib/Ada Example - ${n}.epub`,
      `lib/Ada Example - ${n}.pdf`,
    ])
    const { result } = await run(names.map((n) => file(n)))
    const outcome = await result.current.repair(result.current.state.books, 'downloaded')
    expect(downloads.map((d) => d.name)).toEqual(['ebook-metamend-repaired.zip'])
    expect(outcome.outcomes.size).toBe(3)
    const zip = new Uint8Array(await downloads[0].blob.arrayBuffer())
    expect([...zip.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04])
    const text = new TextDecoder('latin1').decode(zip)
    for (const name of names) expect(text).toContain(name)
    // Stored, not deflated: the central directory records method 0 for each entry.
    const central = text.indexOf('PK\x01\x02')
    expect(central).toBeGreaterThan(0)
    expect(zip[central + 10]).toBe(0)
    expect(zip[central + 11]).toBe(0)
  })

  it('writes back through the handles after permission is granted', async () => {
    const written: Record<string, Uint8Array> = {}
    const { result } = await run([
      file('Ada Example - One.epub', 'x', fakeHandle(written, 'Ada Example - One.epub')),
      file('Ada Example - One.pdf', 'x', fakeHandle(written, 'Ada Example - One.pdf')),
    ])
    expect(result.current.writable(result.current.state.books)).toBe(true)
    const outcome = await result.current.repair(result.current.state.books, 'written')
    expect(Object.keys(written).sort()).toEqual(['Ada Example - One.epub', 'Ada Example - One.pdf'])
    expect(new TextDecoder().decode(written['Ada Example - One.pdf'])).toBe('Ada Example - One.pdf')
    expect([...outcome.outcomes]).toEqual([['Ada Example - One', 'written']])
    expect(downloads).toEqual([])
  })

  it('does nothing when write permission is refused', async () => {
    const written: Record<string, Uint8Array> = {}
    const { result } = await run([
      file('Ada Example - One.epub', 'x', fakeHandle(written, 'Ada Example - One.epub', 'denied')),
    ])
    const outcome = await result.current.repair(result.current.state.books, 'written')
    expect(outcome.failures).toEqual(['Write access was not granted.'])
    expect(outcome.outcomes.size).toBe(0)
    expect(written).toEqual({})
  })

  it('reports a book the worker could not write and leaves it unplaced', async () => {
    const { result } = await run([file('Ada Example - One.epub'), file('Ada Example - Two.epub')])
    const good = script.apply
    script.apply = (stem, bytes, proposal) =>
      stem.endsWith('One')
        ? Promise.resolve({ files: {}, writes: [{ ext: '.epub', ok: false, reason: 'no OPF' }] })
        : good(stem, bytes, proposal)
    const outcome = await result.current.repair(result.current.state.books, 'downloaded')
    expect(outcome.failures).toEqual(['Ada Example - One: .epub no OPF'])
    expect([...outcome.outcomes.keys()]).toEqual(['Ada Example - Two'])
    expect(downloads.map((d) => d.name)).toEqual(['Ada Example - Two.epub'])
  })

  it('downloads no zip when every book failed to write', async () => {
    const names = ['One', 'Two', 'Three'].flatMap((n) => [
      `lib/Ada Example - ${n}.epub`,
      `lib/Ada Example - ${n}.pdf`,
    ])
    const { result } = await run(names.map((n) => file(n)))
    script.apply = () =>
      Promise.resolve({ files: {}, writes: [{ ext: '.epub', ok: false, reason: 'no OPF' }] })
    const outcome = await result.current.repair(result.current.state.books, 'downloaded')
    expect(outcome.failures).toHaveLength(3)
    expect(outcome.outcomes.size).toBe(0)
    expect(downloads).toEqual([])
  })

  it('is not writable when a file came without a handle', async () => {
    const written: Record<string, Uint8Array> = {}
    const { result } = await run([
      file('Ada Example - One.epub', 'x', fakeHandle(written, 'Ada Example - One.epub')),
      file('Ada Example - One.pdf'),
    ])
    expect(result.current.writable(result.current.state.books)).toBe(false)
  })
})
