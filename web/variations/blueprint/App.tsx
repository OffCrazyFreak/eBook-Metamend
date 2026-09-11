import { useMemo, useRef, useState, type DragEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

import lockup from '../../../assets/brand/lockup-horizontal/lockup-horizontal-white-on-transparent-1200w.png'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
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

const VERDICT_COLOR: Record<Confidence | 'NONE' | 'UNREADABLE', string> = {
  HIGH: 'var(--bp-high)',
  MED: 'var(--bp-med)',
  LOW: 'var(--bp-low)',
  NONE: 'var(--bp-muted)',
  UNREADABLE: 'var(--bp-low)',
}

const VERDICT_LABEL: Record<Confidence | 'NONE' | 'UNREADABLE', string> = {
  HIGH: 'HIGH',
  MED: 'MED',
  LOW: 'LOW',
  NONE: 'NO ANSWER',
  UNREADABLE: 'UNREADABLE',
}

export function App() {
  const { state, start, reset } = useRun()
  const [selected, setSelected] = useState<BookResult | null>(null)
  const [filter, setFilter] = useState<'all' | 'writes'>('all')

  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: done.filter(willWrite).length,
    }
  }, [state.books])

  const visible = filter === 'writes' ? state.books.filter(willWrite) : state.books

  return (
    <div className="bp-sheet">
      <div className="mx-auto max-w-6xl px-6 pb-24 pt-8 md:px-10">
        <Header />

        {state.phase === 'idle' && <Intake onStart={start} />}
        {state.phase === 'loading' && (
          <Loading progress={state.loading.progress} label={state.loading.label} />
        )}
        {(state.phase === 'running' || state.phase === 'done') && (
          <>
            <Summary
              counts={counts}
              phase={state.phase}
              elapsedMs={state.elapsedMs}
              filter={filter}
              onFilter={setFilter}
            />
            <Results books={visible} active={state.active} onSelect={setSelected} />
            <Actions counts={counts} done={state.phase === 'done'} onReset={reset} />
          </>
        )}

        <Explainer />
        <Footer />
      </div>

      <Detail book={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

function Header() {
  return (
    <header className="flex flex-wrap items-end justify-between gap-6">
      <img src={lockup} alt="eBook Metamend" className="h-14 w-auto md:h-16" />
      <p className="bp-mono max-w-xs text-[11px] leading-relaxed tracking-wider text-[var(--bp-muted)] uppercase">
        sheet 01 / metadata repair / runs in your browser
      </p>
    </header>
  )
}

function Intake({ onStart }: { onStart: (names: string[]) => void }) {
  const [over, setOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const reduced = useReducedMotion()

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    onStart(await namesFromDrop(event))
  }

  return (
    <section className="mt-16 md:mt-24">
      <motion.h1
        className="bp-display max-w-3xl text-4xl leading-[1.05] font-semibold md:text-6xl"
        initial={reduced ? false : { opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.2, 0.8, 0.2, 1] }}
      >
        Repair the metadata in your ebooks without letting a catalogue lie to you.
      </motion.h1>
      <motion.p
        className="mt-5 max-w-2xl text-lg text-[var(--bp-muted)]"
        initial={reduced ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.12, ease: [0.2, 0.8, 0.2, 1] }}
      >
        Your filenames are the ground truth. Three catalogues are asked about each book, and a field
        is written only when two of them identify the same book on their own and agree.
      </motion.p>

      <motion.div
        className="bp-brackets mt-14 md:mt-20"
        data-over={over}
        initial={reduced ? false : { opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="bp-corner" />
        <div
          role="region"
          aria-label="Drop EPUB or PDF files or a folder here"
          className="flex min-h-[260px] flex-col items-center justify-center gap-6 border border-[var(--bp-line-strong)] bg-[rgba(0,15,44,0.55)] px-6 py-12 text-center backdrop-blur-[1px]"
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
          <span className="bp-dim w-48 self-start">intake</span>
          <p className="bp-display text-2xl md:text-3xl">
            {over ? 'Release to start the dry run' : 'Drop files or a folder here'}
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <button className="bp-button" onClick={() => fileInput.current?.click()}>
              Choose files
            </button>
            <button className="bp-button" onClick={() => folderInput.current?.click()}>
              Choose a folder
            </button>
          </div>
          <p className="bp-mono text-xs text-[var(--bp-muted)]">
            EPUB and PDF. Nothing leaves this browser tab.{' '}
            {canWriteInPlace
              ? 'Repairs can be written straight back into the folder.'
              : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
          </p>
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
        </div>
      </motion.div>
      <p className="bp-mono mt-4 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase">
        No files to hand?{' '}
        <button
          className="underline decoration-[var(--bp-line-strong)] underline-offset-4 hover:text-[var(--bp-cyan)]"
          onClick={() => onStart([])}
        >
          Play the invented sample
        </button>
      </p>
    </section>
  )
}

function Loading({ progress, label }: { progress: number; label: string }) {
  return (
    <section className="mt-24 flex flex-col items-center text-center" aria-live="polite">
      <span className="bp-dim w-64">loading python</span>
      <p className="bp-display mt-6 text-3xl">{label}</p>
      <div className="mt-8 h-[2px] w-full max-w-lg bg-[var(--bp-line)]">
        <motion.div
          className="h-full bg-[var(--bp-cyan)]"
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(progress * 100)}%` }}
          transition={{ ease: 'linear', duration: 0.4 }}
        />
      </div>
      <p className="bp-mono mt-3 text-xs text-[var(--bp-muted)]">
        {Math.round(progress * 100)}% of about 6 MB, once. Cached after that.
      </p>
    </section>
  )
}

function Summary({
  counts,
  phase,
  elapsedMs,
  filter,
  onFilter,
}: {
  counts: { done: number; total: number; high: number; writes: number }
  phase: 'running' | 'done'
  elapsedMs: number
  filter: 'all' | 'writes'
  onFilter: (f: 'all' | 'writes') => void
}) {
  return (
    <section className="mt-14 grid gap-6 md:grid-cols-[1fr_auto] md:items-end" aria-live="polite">
      <div>
        <span className="bp-dim w-64">{phase === 'done' ? 'dry run complete' : 'dry run'}</span>
        <p className="bp-display mt-4 text-3xl md:text-4xl">
          <span className="bp-mono">{counts.done}</span> of{' '}
          <span className="bp-mono">{counts.total}</span> books checked
          {phase === 'running' && <span className="bp-cursor" aria-hidden="true" />}
        </p>
        <p className="mt-2 text-[var(--bp-muted)]">
          <span className="bp-mono text-[var(--bp-high)]">{counts.high}</span> identified with high
          confidence, <span className="bp-mono text-[var(--bp-ink)]">{counts.writes}</span> would be
          written
          {phase === 'done' && (
            <span className="bp-mono"> in {(elapsedMs / 1000).toFixed(1)} s</span>
          )}
          .
        </p>
      </div>
      <div className="bp-mono flex gap-1 text-xs" role="group" aria-label="Filter">
        {(['all', 'writes'] as const).map((f) => (
          <button
            key={f}
            aria-pressed={filter === f}
            onClick={() => onFilter(f)}
            className="border border-[var(--bp-line-strong)] px-3 py-1.5 tracking-wider uppercase aria-pressed:bg-[var(--bp-cyan)] aria-pressed:text-[var(--bp-deep)]"
          >
            {f === 'all' ? 'all books' : 'would write'}
          </button>
        ))}
      </div>
    </section>
  )
}

function Results({
  books,
  active,
  onSelect,
}: {
  books: BookResult[]
  active: string | null
  onSelect: (b: BookResult) => void
}) {
  const reduced = useReducedMotion()
  return (
    <ol className="mt-8">
      <li className="bp-mono grid grid-cols-[2.5rem_1fr_auto] items-center gap-4 pb-2 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase md:grid-cols-[2.5rem_1fr_10rem_7rem_8rem]">
        <span>no.</span>
        <span>file</span>
        <span className="hidden md:block">sources</span>
        <span className="hidden md:block">gains</span>
        <span className="text-right">verdict</span>
      </li>
      <AnimatePresence initial={false}>
        {books.map((book, i) => {
          const v = verdict(book)
          const done = book.status === 'done'
          return (
            <motion.li
              key={book.stem}
              layout={!reduced}
              initial={reduced ? false : { opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
              className="bp-row"
            >
              <button
                disabled={!done}
                onClick={() => onSelect(book)}
                className="grid w-full grid-cols-[2.5rem_1fr_auto] items-center gap-4 py-3 text-left transition-colors hover:bg-[rgba(53,198,255,0.06)] focus-visible:bg-[rgba(53,198,255,0.1)] focus-visible:outline-none disabled:cursor-default md:grid-cols-[2.5rem_1fr_10rem_7rem_8rem]"
              >
                <span className="bp-mono text-xs text-[var(--bp-muted)]">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="min-w-0">
                  <span className="block truncate">{book.facts.title}</span>
                  <span className="block truncate text-sm text-[var(--bp-muted)]">
                    {book.facts.author}
                    {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
                    <span className="bp-mono">
                      {' '}
                      · {book.files.map((f) => f.slice(1)).join(' + ')}
                    </span>
                  </span>
                </span>
                <span className="bp-mono hidden text-xs text-[var(--bp-muted)] md:block">
                  {done && book.proposal
                    ? book.proposal.sources.map((s) => SOURCE_LABEL[s].split(' ')[0]).join(', ')
                    : ''}
                </span>
                <span className="bp-mono hidden text-xs text-[var(--bp-muted)] md:block">
                  {done && book.proposal
                    ? Object.keys(book.proposal.gains).join(', ') || 'none'
                    : ''}
                </span>
                <span className="text-right">
                  {done ? (
                    <motion.span
                      className="bp-stamp"
                      style={{ color: VERDICT_COLOR[v] }}
                      initial={reduced ? false : { scale: 1.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 420, damping: 22 }}
                    >
                      {VERDICT_LABEL[v]}
                    </motion.span>
                  ) : (
                    <span
                      className={`bp-mono text-xs text-[var(--bp-muted)] ${active === book.stem ? 'bp-cursor' : ''}`}
                    >
                      {active === book.stem ? 'asking' : 'queued'}
                    </span>
                  )}
                </span>
              </button>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ol>
  )
}

function Actions({
  counts,
  done,
  onReset,
}: {
  counts: { writes: number }
  done: boolean
  onReset: () => void
}) {
  return (
    <section className="mt-10 flex flex-wrap items-center gap-3 border-t border-[var(--bp-line-strong)] pt-6">
      <button className="bp-button" data-primary="true" disabled={!done || counts.writes === 0}>
        Download {counts.writes} repaired {counts.writes === 1 ? 'file' : 'files'}
      </button>
      {canWriteInPlace && (
        <button className="bp-button" disabled={!done || counts.writes === 0}>
          Write into the folder
        </button>
      )}
      <button className="bp-button ml-auto" onClick={onReset}>
        Start over
      </button>
      <p className="bp-mono w-full text-xs text-[var(--bp-muted)]">
        Dry run by default. Only HIGH verdicts are written, only missing fields are filled, and no
        existing value is ever blanked.
      </p>
    </section>
  )
}

function Detail({ book, onClose }: { book: BookResult | null; onClose: () => void }) {
  const p = book?.proposal ?? null
  return (
    <Dialog open={book !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto border-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-0 text-[var(--bp-ink)] sm:max-w-2xl">
        {book && (
          <div className="p-6 md:p-8">
            <span className="bp-dim w-48">sheet detail</span>
            <DialogTitle className="bp-display mt-4 text-2xl leading-tight">
              {book.facts.title}
            </DialogTitle>
            <DialogDescription className="text-[var(--bp-muted)]">
              {book.facts.author}
              {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
            </DialogDescription>

            {p === null ? (
              <p className="mt-6 text-[var(--bp-muted)]">
                No catalogue answered for this filename. Nothing is proposed.
              </p>
            ) : p.unreadable ? (
              <p className="mt-6 text-[var(--bp-muted)]">
                The file's existing metadata could not be read, so nothing is proposed. A failed
                read is not an empty book.
              </p>
            ) : (
              <>
                <div className="mt-6 flex items-center gap-4">
                  <span className="bp-stamp text-base" style={{ color: VERDICT_COLOR[p.conf] }}>
                    {p.conf}
                  </span>
                  <span className="bp-mono text-xs text-[var(--bp-muted)]">
                    title {p.fn_score.toFixed(2)} · author {p.au_score.toFixed(2)} against the
                    filename
                  </span>
                </div>

                <h3 className="bp-dim mt-8 w-full">what each catalogue said</h3>
                <ul className="mt-3 divide-y divide-[var(--bp-line)]">
                  {p.scores.map((s) => {
                    const trusted = p.sources.includes(s.name)
                    return (
                      <li
                        key={s.name}
                        className="grid grid-cols-[7rem_1fr_auto] gap-3 py-2 text-sm"
                      >
                        <span className="text-[var(--bp-muted)]">{SOURCE_LABEL[s.name]}</span>
                        <span
                          className={
                            trusted
                              ? ''
                              : 'text-[var(--bp-muted)] line-through decoration-[var(--bp-low)]'
                          }
                        >
                          {s.title}
                        </span>
                        <span className="bp-mono text-xs text-[var(--bp-muted)]">
                          {s.title_score.toFixed(2)} / {s.author_score.toFixed(2)}
                        </span>
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-2 text-xs text-[var(--bp-muted)]">
                  Struck through: answered, but did not identify this book on its own, so it may not
                  supply a field.
                </p>

                <h3 className="bp-dim mt-8 w-full">
                  {Object.keys(p.gains).length ? 'would be written' : 'nothing to add'}
                </h3>
                <dl className="mt-3 grid gap-3">
                  {Object.entries(p.gains).map(([field, value]) => (
                    <div key={field} className="grid gap-1 md:grid-cols-[7rem_1fr]">
                      <dt className="bp-mono text-xs tracking-wider text-[var(--bp-cyan)] uppercase">
                        {field}
                      </dt>
                      <dd className="text-sm">
                        {field in p.current && current(p.current, field) && (
                          <span className="block text-[var(--bp-muted)] line-through">
                            {current(p.current, field)}
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
        )}
      </DialogContent>
    </Dialog>
  )
}

function current(meta: Metadata, field: string) {
  const value = (meta as unknown as Record<string, unknown>)[field]
  if (Array.isArray(value)) return value.join(', ')
  return value ? String(value) : ''
}

function Explainer() {
  return (
    <section className="mt-32 grid gap-10 md:grid-cols-[14rem_1fr]">
      <span className="bp-dim self-start">how it decides</span>
      <div className="max-w-2xl space-y-6 text-lg leading-relaxed">
        <p>
          The obvious fix for messy ebook metadata is to look each book up online and write back
          whatever comes back. That is also how you destroy a library. Catalogues confidently return
          the wrong book, and a bulk run that trusts them corrupts hundreds of files at once,
          quietly.
        </p>
        <p>
          So the filename is the ground truth. Every answer is scored against the title and the
          author in it. A book reaches <span className="bp-mono text-[var(--bp-high)]">HIGH</span>{' '}
          only when two catalogues each identify it on their own and agree with each other, and only
          those catalogues may supply fields. One source is never enough: on a real library a single
          source returned an abridgement, a translation and a different book entirely for three
          correctly named files.
        </p>
        <p>
          Fields are added or improved, never emptied. Dry run is the default. And the files never
          leave your browser: the Python that does this work runs inside the page.
        </p>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="bp-mono mt-24 flex flex-wrap gap-x-8 gap-y-2 border-t border-[var(--bp-line)] pt-6 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase">
      <span>Files stay in this tab. Only three catalogue searches leave it.</span>
      <a
        className="hover:text-[var(--bp-cyan)]"
        href="https://github.com/OffCrazyFreak/eBook-Metamend"
      >
        Source on GitHub
      </a>
      <span>MIT licence</span>
    </footer>
  )
}
