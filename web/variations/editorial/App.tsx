import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { AnimatePresence, animate, motion, useReducedMotion } from 'motion/react'

import wordmark from '../../../assets/brand/wordmark/wordmark-navy-on-transparent-800w.png'
import { canWriteInPlace, hasFiles, namesFromDrop, namesFromFileList } from '@/intake'
import { useRun } from '@/mock/use-run'
import {
  SOURCE_LABEL,
  verdict,
  willWrite,
  type BookResult,
  type Confidence,
  type Metadata,
} from '@/types'

type Verdict = Confidence | 'NONE' | 'UNREADABLE'

const COLOR: Record<Verdict, string> = {
  HIGH: 'var(--ed-high)',
  MED: 'var(--ed-med)',
  LOW: 'var(--ed-low)',
  NONE: 'var(--ed-muted)',
  UNREADABLE: 'var(--ed-low)',
}
const LABEL: Record<Verdict, string> = {
  HIGH: 'High',
  MED: 'Med',
  LOW: 'Low',
  NONE: 'None',
  UNREADABLE: 'Unread',
}

export function App() {
  const { state, start, reset } = useRun()
  const [selected, setSelected] = useState<BookResult | null>(null)
  const [sort, setSort] = useState<'order' | 'verdict'>('order')

  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: done.filter(willWrite).length,
      none: done.filter((b) => verdict(b) === 'NONE').length,
    }
  }, [state.books])

  const RANK: Record<Verdict, number> = { HIGH: 0, MED: 1, LOW: 2, UNREADABLE: 3, NONE: 4 }
  const visible =
    sort === 'order'
      ? state.books
      : [...state.books].sort((a, b) => {
          if (a.status !== 'done' || b.status !== 'done') return a.status === 'done' ? -1 : 1
          return RANK[verdict(a)] - RANK[verdict(b)]
        })

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-6 md:px-10">
        <header className="ed-rule flex flex-wrap items-baseline justify-between gap-4 pt-4">
          <img src={wordmark} alt="eBook Metamend" className="h-6 w-auto md:h-7" />
          <span className="ed-label text-[var(--ed-soft)]">
            Metadata repair, in the browser, no. 1
          </span>
        </header>

        <div className="grid gap-12 md:grid-cols-[1fr_20rem]">
          <div className="min-w-0">
            {state.phase === 'idle' && <Intake onStart={start} />}
            {state.phase === 'loading' && <Loading {...state.loading} />}
            {(state.phase === 'running' || state.phase === 'done') && (
              <>
                <Standfirst
                  counts={counts}
                  running={state.phase === 'running'}
                  elapsedMs={state.elapsedMs}
                />
                <div className="ed-rule mt-10 flex items-center justify-between pt-3">
                  <span className="ed-label">The run</span>
                  <div className="ed-label flex gap-4" role="group" aria-label="Sort">
                    {(['order', 'verdict'] as const).map((s) => (
                      <button
                        key={s}
                        aria-pressed={sort === s}
                        onClick={() => setSort(s)}
                        className="text-[var(--ed-muted)] aria-pressed:text-[var(--ed-ink)] aria-pressed:underline aria-pressed:underline-offset-4"
                      >
                        {s === 'order' ? 'In order' : 'By verdict'}
                      </button>
                    ))}
                  </div>
                </div>
                <Table
                  books={visible}
                  active={state.active}
                  selected={selected}
                  onSelect={setSelected}
                />
                <Actions writes={counts.writes} done={state.phase === 'done'} onReset={reset} />
              </>
            )}
          </div>
          <aside className="hidden md:block">
            {(state.phase === 'running' || state.phase === 'done') && (
              <Side book={selected} onClose={() => setSelected(null)} counts={counts} />
            )}
          </aside>
        </div>

        <MobileDetail book={selected} onClose={() => setSelected(null)} />
        <Explainer />
        <footer className="ed-rule mt-24 flex flex-wrap gap-x-8 gap-y-2 pt-4 text-sm text-[var(--ed-soft)]">
          <span>Your files stay in this tab. Only three catalogue searches leave it.</span>
          <a
            className="underline underline-offset-4 hover:text-[var(--ed-accent)]"
            href="https://github.com/OffCrazyFreak/eBook-Metamend"
          >
            Source on GitHub
          </a>
          <span>MIT licence</span>
        </footer>
      </div>
    </div>
  )
}

function Intake({ onStart }: { onStart: (names: string[]) => void }) {
  const [over, setOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const reduced = useReducedMotion()
  const lines = ['Your filenames', 'are the', 'ground truth.']

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    onStart(await namesFromDrop(event))
  }

  return (
    <section className="mt-16 md:mt-24">
      <h1 className="ed-display text-[3.4rem] font-bold text-[var(--ed-navy)] md:text-[7rem]">
        {lines.map((line, i) => (
          <motion.span
            key={line}
            className="block"
            initial={reduced ? false : { opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: i * 0.12, ease: [0.2, 0.8, 0.2, 1] }}
          >
            {i === 2 ? <span className="text-[var(--ed-accent)]">{line}</span> : line}
          </motion.span>
        ))}
      </h1>
      <motion.p
        className="mt-8 max-w-xl text-xl leading-relaxed md:text-2xl"
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.5 }}
      >
        Online catalogues are witnesses, not authorities. Three are asked about each book; a field
        is written only when two identify the same book on their own and agree.
      </motion.p>

      <motion.div
        role="region"
        aria-label="Drop EPUB or PDF files or a folder here"
        className="ed-drop mt-12 grid gap-6 p-6 md:grid-cols-[1fr_auto] md:items-center md:p-8"
        data-over={over}
        initial={reduced ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.7 }}
        onDragEnter={(e) => hasFiles(e) && setOver(true)}
        onDragOver={(e) => {
          if (hasFiles(e)) {
            e.preventDefault()
            setOver(true)
          }
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false)
        }}
        onDrop={onDrop}
      >
        <div>
          <p className="ed-display-narrow text-3xl font-semibold md:text-4xl">
            {over ? 'Release to start the dry run.' : 'Drop books or a folder here.'}
          </p>
          <p className="mt-3 text-[var(--ed-soft)]">
            EPUB and PDF. Nothing leaves this browser tab.{' '}
            {canWriteInPlace
              ? 'Repairs can be written straight back into the folder.'
              : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button className="ed-button" onClick={() => fileInput.current?.click()}>
            Choose files
          </button>
          <button className="ed-button" onClick={() => folderInput.current?.click()}>
            Choose a folder
          </button>
        </div>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".epub,.pdf"
          className="sr-only"
          onChange={(e) => onStart(namesFromFileList(e.target.files))}
        />
        <input
          ref={folderInput}
          type="file"
          // @ts-expect-error webkitdirectory is not in the React types yet
          webkitdirectory=""
          className="sr-only"
          onChange={(e) => onStart(namesFromFileList(e.target.files))}
        />
      </motion.div>
      <p className="mt-4 text-sm text-[var(--ed-soft)]">
        No files to hand?{' '}
        <button
          className="underline underline-offset-4 hover:text-[var(--ed-accent)]"
          onClick={() => onStart([])}
        >
          Play the invented sample.
        </button>
      </p>
    </section>
  )
}

function Loading({ progress, label }: { progress: number; label: string }) {
  return (
    <section className="mt-24" aria-live="polite">
      <span className="ed-label">Loading Python</span>
      <p className="ed-display mt-4 text-5xl font-bold text-[var(--ed-navy)] md:text-7xl">
        {Math.round(progress * 100)}
        <span className="text-[var(--ed-accent)]">%</span>
      </p>
      <p className="mt-4 text-lg text-[var(--ed-soft)]">
        {label}. About 6 MB, once; cached after that.
      </p>
      <div className="mt-6 h-px w-full bg-[var(--ed-rule)]">
        <motion.div
          className="h-px bg-[var(--ed-ink)]"
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(progress * 100)}%` }}
          transition={{ ease: 'linear', duration: 0.4 }}
        />
      </div>
    </section>
  )
}

// Counts tick up like a cover line being set.
function Count({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const reduced = useReducedMotion()
  const previous = useRef(0)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (reduced) {
      node.textContent = String(value)
      previous.current = value
      return
    }
    const controls = animate(previous.current, value, {
      duration: 0.5,
      onUpdate: (v) => (node.textContent = String(Math.round(v))),
    })
    previous.current = value
    return () => controls.stop()
  }, [value, reduced])
  return <span ref={ref}>{value}</span>
}

function Standfirst({
  counts,
  running,
  elapsedMs,
}: {
  counts: { done: number; total: number; high: number; writes: number; none: number }
  running: boolean
  elapsedMs: number
}) {
  return (
    <section className="mt-12 grid gap-8 md:grid-cols-3" aria-live="polite">
      {[
        { n: counts.done, label: `of ${counts.total} checked`, color: 'var(--ed-navy)' },
        { n: counts.high, label: 'identified with high confidence', color: 'var(--ed-high)' },
        {
          n: counts.writes,
          label: running
            ? 'would be written'
            : `would be written, in ${(elapsedMs / 1000).toFixed(1)} s`,
          color: 'var(--ed-accent)',
        },
      ].map((item) => (
        <div key={item.label} className="ed-hair pt-3">
          <p
            className="ed-display text-[4.5rem] font-bold md:text-[6rem]"
            style={{ color: item.color }}
          >
            <Count value={item.n} />
          </p>
          <p className="mt-1 text-[var(--ed-soft)]">
            {item.label}
            {running && item.n === counts.done && (
              <span className="ed-live ml-1 text-[var(--ed-accent)]">●</span>
            )}
          </p>
        </div>
      ))}
    </section>
  )
}

function Table({
  books,
  active,
  selected,
  onSelect,
}: {
  books: BookResult[]
  active: string | null
  selected: BookResult | null
  onSelect: (b: BookResult) => void
}) {
  const reduced = useReducedMotion()
  return (
    <div className="mt-2">
      <AnimatePresence initial={false}>
        {books.map((book, i) => {
          const v = verdict(book)
          const done = book.status === 'done'
          const isSelected = selected?.stem === book.stem
          return (
            <motion.button
              key={book.stem}
              layout={!reduced}
              disabled={!done}
              aria-pressed={isSelected}
              onClick={() => onSelect(book)}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="ed-row w-full text-left hover:bg-[#f3f5fa] focus-visible:bg-[#e9f1ff] focus-visible:outline-none disabled:cursor-default aria-pressed:bg-[#e9f1ff]"
            >
              <span className="ed-label text-[var(--ed-muted)]">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className="min-w-0">
                <span className="ed-display-narrow block truncate text-xl font-semibold">
                  {book.facts.title}
                </span>
                <span className="block truncate text-[var(--ed-soft)]">
                  {book.facts.author}
                  {book.facts.series && `, ${book.facts.series} ${book.facts.series_index}`}
                </span>
              </span>
              <span className="hidden truncate text-sm text-[var(--ed-soft)] md:block">
                {done && book.proposal
                  ? book.proposal.sources.map((s) => SOURCE_LABEL[s]).join(', ')
                  : ''}
              </span>
              <span className="hidden truncate text-sm text-[var(--ed-soft)] md:block">
                {done && book.proposal && !book.proposal.unreadable
                  ? Object.keys(book.proposal.gains).join(', ') || 'nothing to add'
                  : ''}
              </span>
              <span className="text-right">
                {done ? (
                  <motion.span
                    className="ed-verdict"
                    style={{ color: COLOR[v] }}
                    initial={reduced ? false : { opacity: 0, x: 6 }}
                    animate={{ opacity: 1, x: 0 }}
                  >
                    {LABEL[v]}
                  </motion.span>
                ) : (
                  <span
                    className={`text-sm text-[var(--ed-muted)] ${active === book.stem ? 'ed-live' : ''}`}
                  >
                    {active === book.stem ? 'asking' : 'queued'}
                  </span>
                )}
              </span>
            </motion.button>
          )
        })}
      </AnimatePresence>
    </div>
  )
}

function Side({
  book,
  onClose,
  counts,
}: {
  book: BookResult | null
  onClose: () => void
  counts: { none: number; high: number }
}) {
  return (
    <div className="sticky top-6 mt-12">
      <AnimatePresence mode="wait" initial={false}>
        {book ? (
          <motion.div
            key={book.stem}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <DetailBody book={book} onClose={onClose} />
          </motion.div>
        ) : (
          <motion.div
            key="note"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <span className="ed-label">Margin note</span>
            <p className="mt-3 leading-relaxed text-[var(--ed-soft)]">
              Select a row to see what each catalogue said, and what would change. {counts.high}{' '}
              books reached high confidence so far
              {counts.none ? `; ${counts.none} had no record anywhere` : ''}.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MobileDetail({ book, onClose }: { book: BookResult | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {book && (
        <motion.div
          className="fixed inset-x-0 bottom-0 z-20 max-h-[80vh] overflow-y-auto border-t border-[var(--ed-ink)] bg-white p-5 shadow-[0_-12px_40px_-20px_rgba(11,18,48,0.4)] md:hidden"
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', stiffness: 320, damping: 32 }}
        >
          <DetailBody book={book} onClose={onClose} />
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function DetailBody({ book, onClose }: { book: BookResult; onClose: () => void }) {
  const p = book.proposal
  const v = verdict(book)
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <span className="ed-verdict" style={{ color: COLOR[v] }}>
          {LABEL[v]}
        </span>
        <button
          className="ed-label text-[var(--ed-muted)] hover:text-[var(--ed-ink)]"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <h2 className="ed-display-narrow mt-2 text-2xl font-semibold leading-tight">
        {book.facts.title}
      </h2>
      <p className="text-[var(--ed-soft)]">
        {book.facts.author}
        {book.facts.series && `, ${book.facts.series} ${book.facts.series_index}`}
      </p>
      {p === null ? (
        <p className="mt-5 text-[var(--ed-soft)]">
          No catalogue answered for this filename. Nothing is proposed.
        </p>
      ) : p.unreadable ? (
        <p className="mt-5 text-[var(--ed-soft)]">
          The file's existing metadata could not be read, so nothing is proposed. A failed read is
          not an empty book.
        </p>
      ) : (
        <>
          <p className="ed-label mt-6">What each catalogue said</p>
          <ul className="mt-2 space-y-2 text-sm">
            {p.scores.map((s) => {
              const trusted = p.sources.includes(s.name)
              return (
                <li key={s.name}>
                  <span className="text-[var(--ed-soft)]">{SOURCE_LABEL[s.name]}: </span>
                  <span
                    className={
                      trusted
                        ? ''
                        : 'text-[var(--ed-muted)] line-through decoration-[var(--ed-low)]'
                    }
                  >
                    {s.title}
                  </span>
                  <span className="ed-label ml-2 text-[var(--ed-muted)]">
                    {s.title_score.toFixed(2)} / {s.author_score.toFixed(2)}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="ed-label mt-6">
            {Object.keys(p.gains).length ? 'Would be written' : 'Nothing to add'}
          </p>
          <dl className="mt-2 space-y-2 text-sm">
            {Object.entries(p.gains).map(([field, value]) => (
              <div key={field}>
                <dt className="text-[var(--ed-soft)] capitalize">{field}</dt>
                <dd>
                  {currentValue(p.current, field) && (
                    <span className="block text-[var(--ed-muted)] line-through">
                      {currentValue(p.current, field)}
                    </span>
                  )}
                  {Array.isArray(value) ? value.join(', ') : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </div>
  )
}

function currentValue(meta: Metadata, field: string) {
  const value = (meta as unknown as Record<string, unknown>)[field]
  if (Array.isArray(value)) return value.join(', ')
  return value ? String(value) : ''
}

function Actions({
  writes,
  done,
  onReset,
}: {
  writes: number
  done: boolean
  onReset: () => void
}) {
  return (
    <section className="ed-rule mt-8 flex flex-wrap items-center gap-3 pt-6">
      <button className="ed-button" data-primary="true" disabled={!done || writes === 0}>
        Download {writes} repaired {writes === 1 ? 'file' : 'files'}
      </button>
      {canWriteInPlace && (
        <button className="ed-button" disabled={!done || writes === 0}>
          Write into the folder
        </button>
      )}
      <button className="ed-button ml-auto" onClick={onReset}>
        Start over
      </button>
      <p className="w-full text-sm text-[var(--ed-soft)]">
        Dry run by default. Only high-confidence books are written, only missing fields are filled,
        and no existing value is ever blanked.
      </p>
    </section>
  )
}

function Explainer() {
  return (
    <section className="ed-rule mt-28 grid gap-8 pt-4 md:grid-cols-[1fr_2fr]">
      <h2 className="ed-display text-4xl font-bold text-[var(--ed-navy)] md:text-5xl">
        Why two witnesses
      </h2>
      <div className="space-y-5 text-xl leading-relaxed">
        <p>
          The obvious fix for messy ebook metadata is to look each book up online and write back
          whatever comes back. That is also how you destroy a library. Catalogues confidently return
          the wrong book, and a bulk run that trusts them corrupts hundreds of files at once,
          quietly.
        </p>
        <p>
          So the filename is the ground truth. Every answer is scored against the title and the
          author in it. A book reaches{' '}
          <span className="ed-verdict text-[var(--ed-high)]">High</span> only when two catalogues
          each identify it on their own and agree with each other, and only those catalogues may
          supply fields. One source is never enough: on a real library a single source returned an
          abridgement, a translation and a different book entirely for three correctly named files.
        </p>
        <p>
          Fields are added or improved, never emptied. Dry run is the default. And the files never
          leave your browser: the Python that does this work runs inside the page.
        </p>
      </div>
    </section>
  )
}
