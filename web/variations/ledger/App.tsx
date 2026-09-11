import { useMemo, useRef, useState, type DragEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

import lockup from '../../../assets/brand/lockup-horizontal/lockup-horizontal-navy-on-transparent-1200w.png'
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

const INK: Record<Verdict, string> = {
  HIGH: 'var(--lg-high)',
  MED: 'var(--lg-med)',
  LOW: 'var(--lg-low)',
  NONE: 'var(--lg-muted)',
  UNREADABLE: 'var(--lg-low)',
}
const STAMP: Record<Verdict, string> = {
  HIGH: 'Verified',
  MED: 'One witness',
  LOW: 'Unmatched',
  NONE: 'No record',
  UNREADABLE: 'Unreadable',
}

// Switches the visible card with the browser's page transition where it exists.
function turnPage(update: () => void) {
  if (typeof document.startViewTransition === 'function') document.startViewTransition(update)
  else update()
}

export function App() {
  const { state, start, reset } = useRun()
  const [open, setOpen] = useState<BookResult | null>(null)
  const [tab, setTab] = useState<'all' | 'HIGH' | 'MED' | 'LOW'>('all')

  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: done.filter(willWrite).length,
    }
  }, [state.books])

  const visible = tab === 'all' ? state.books : state.books.filter((b) => verdict(b) === tab)

  return (
    <div className="lg-page">
      <div className="mx-auto max-w-5xl px-5 pb-24 pt-8 md:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--lg-rule)] pb-5">
          <img src={lockup} alt="eBook Metamend" className="h-12 w-auto md:h-14" />
          <span className="lg-display-italic text-lg text-[var(--lg-ink-soft)]">
            a card catalogue that checks its sources
          </span>
        </header>

        {open ? (
          <DetailCard book={open} onBack={() => turnPage(() => setOpen(null))} />
        ) : (
          <>
            {state.phase === 'idle' && <Intake onStart={start} />}
            {state.phase === 'loading' && <Loading {...state.loading} />}
            {(state.phase === 'running' || state.phase === 'done') && (
              <>
                <Ledger
                  counts={counts}
                  running={state.phase === 'running'}
                  elapsedMs={state.elapsedMs}
                />
                <div className="mt-10 flex gap-1 px-2" role="group" aria-label="Filter by verdict">
                  {(['all', 'HIGH', 'MED', 'LOW'] as const).map((t) => (
                    <button
                      key={t}
                      className="lg-tab"
                      aria-pressed={tab === t}
                      onClick={() => setTab(t)}
                    >
                      {t === 'all' ? 'All cards' : STAMP[t]}
                    </button>
                  ))}
                </div>
                <Cards
                  books={visible}
                  active={state.active}
                  onOpen={(b) => turnPage(() => setOpen(b))}
                />
                <Actions writes={counts.writes} done={state.phase === 'done'} onReset={reset} />
              </>
            )}
          </>
        )}

        <Explainer />
        <footer className="mt-24 flex flex-wrap gap-x-8 gap-y-2 border-t border-[var(--lg-rule)] pt-5 text-sm text-[var(--lg-muted)]">
          <span>Your files stay in this tab. Only three catalogue searches leave it.</span>
          <a
            className="underline underline-offset-4 hover:text-[var(--lg-ink)]"
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

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    onStart(await namesFromDrop(event))
  }

  return (
    <section className="mt-14 grid gap-10 md:mt-20 md:grid-cols-[1.1fr_1fr] md:items-center">
      <div>
        <motion.h1
          className="lg-display text-[2.6rem] leading-[1.02] font-medium md:text-6xl"
          initial={reduced ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: 'easeOut' }}
        >
          Every book gets a card. Every card gets checked twice.
        </motion.h1>
        <motion.p
          className="mt-6 max-w-md text-lg leading-relaxed text-[var(--lg-ink-soft)]"
          initial={reduced ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.1, ease: 'easeOut' }}
        >
          The filename on your disk is the ground truth. Three catalogues are asked about each book,
          and a card is only stamped when two of them name the same book and agree.
        </motion.p>
      </div>

      <motion.div
        className="lg-drawer p-3"
        data-over={over}
        initial={reduced ? false : { opacity: 0, rotate: -1.5, y: 20 }}
        animate={{ opacity: 1, rotate: 0, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
      >
        <div
          role="region"
          aria-label="Drop EPUB or PDF files or a folder here"
          className="lg-card flex min-h-[300px] flex-col justify-between px-8 py-6"
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
          <p className="lg-display text-2xl">
            {over ? 'Let go to file them' : 'File your books here'}
          </p>
          <div>
            <div className="flex flex-wrap gap-3">
              <button className="lg-button" onClick={() => fileInput.current?.click()}>
                Choose files
              </button>
              <button className="lg-button" onClick={() => folderInput.current?.click()}>
                Choose a folder
              </button>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-[var(--lg-ink-soft)]">
              EPUB and PDF, or drop them here.{' '}
              {canWriteInPlace
                ? 'Repairs can be written straight back into the folder.'
                : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
            </p>
            <button
              className="mt-2 text-sm text-[var(--lg-ink-soft)] underline underline-offset-4 hover:text-[var(--lg-ink)]"
              onClick={() => onStart([])}
            >
              Or play the invented sample
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
        </div>
      </motion.div>
    </section>
  )
}

function Loading({ progress, label }: { progress: number; label: string }) {
  return (
    <section className="mx-auto mt-20 max-w-md text-center" aria-live="polite">
      <p className="lg-display-italic text-2xl">{label}</p>
      <div className="mt-6 h-1.5 w-full rounded-full bg-[var(--lg-paper-deep)]">
        <motion.div
          className="h-full rounded-full bg-[var(--lg-ink)]"
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(progress * 100)}%` }}
          transition={{ ease: 'linear', duration: 0.4 }}
        />
      </div>
      <p className="mt-3 text-sm text-[var(--lg-muted)]">
        Fetching about 6 MB of Python, once. Your browser keeps it for next time.
      </p>
    </section>
  )
}

function Ledger({
  counts,
  running,
  elapsedMs,
}: {
  counts: { done: number; total: number; high: number; writes: number }
  running: boolean
  elapsedMs: number
}) {
  return (
    <section
      className="mt-12 flex flex-wrap items-baseline justify-between gap-4"
      aria-live="polite"
    >
      <h2 className="lg-display text-3xl md:text-4xl">
        {counts.done} of {counts.total} cards checked
        {running && <span className="lg-pulse ml-1">…</span>}
      </h2>
      <p className="text-[var(--lg-ink-soft)]">
        <strong className="font-semibold text-[var(--lg-high)]">{counts.high}</strong> verified,{' '}
        <strong className="font-semibold">{counts.writes}</strong> would be written
        {!running && ` in ${(elapsedMs / 1000).toFixed(1)} s`}.
      </p>
    </section>
  )
}

function Cards({
  books,
  active,
  onOpen,
}: {
  books: BookResult[]
  active: string | null
  onOpen: (b: BookResult) => void
}) {
  const reduced = useReducedMotion()
  return (
    <ul className="grid gap-5 border-t border-[var(--lg-rule)] pt-6 md:grid-cols-2">
      <AnimatePresence initial={false}>
        {books.map((book) => {
          const v = verdict(book)
          const done = book.status === 'done'
          return (
            <motion.li
              key={book.stem}
              layout={!reduced}
              initial={reduced ? false : { opacity: 0, y: 24, rotate: -1 }}
              animate={{ opacity: 1, y: 0, rotate: 0 }}
              exit={reduced ? undefined : { opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            >
              <button
                disabled={!done}
                onClick={() => onOpen(book)}
                className="lg-card block w-full px-6 pb-5 pt-4 text-left transition-transform hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--lg-electric)] disabled:cursor-default disabled:hover:translate-y-0"
              >
                <div className="flex items-start justify-between gap-4">
                  <span className="min-w-0">
                    <span className="lg-display block truncate text-xl leading-7">
                      {book.facts.title}
                    </span>
                    <span className="block truncate text-sm leading-7 text-[var(--lg-ink-soft)]">
                      {book.facts.author}
                      {book.facts.series && `, ${book.facts.series} ${book.facts.series_index}`}
                    </span>
                  </span>
                  <span className="shrink-0 pt-1">
                    {done ? (
                      <motion.span
                        className="lg-stamp"
                        style={{ color: INK[v] }}
                        initial={reduced ? false : { scale: 1.8, opacity: 0, rotate: -12 }}
                        animate={{ scale: 1, opacity: 1, rotate: -4 }}
                        transition={{ type: 'spring', stiffness: 380, damping: 18 }}
                      >
                        {STAMP[v]}
                      </motion.span>
                    ) : (
                      <span
                        className={`text-xs text-[var(--lg-muted)] ${active === book.stem ? 'lg-pulse' : ''}`}
                      >
                        {active === book.stem ? 'checking' : 'queued'}
                      </span>
                    )}
                  </span>
                </div>
                <p className="mt-1 text-sm leading-7 text-[var(--lg-ink-soft)]">
                  {done && book.proposal && !book.proposal.unreadable
                    ? Object.keys(book.proposal.gains).length
                      ? `Would add ${Object.keys(book.proposal.gains).join(', ')}`
                      : v === 'HIGH'
                        ? 'Nothing missing'
                        : 'Nothing written at this confidence'
                    : done
                      ? 'Nothing proposed'
                      : `${book.files.map((f) => f.slice(1)).join(' and ')} on file`}
                </p>
              </button>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ul>
  )
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
    <section className="mt-10 flex flex-wrap items-center gap-3 border-t border-[var(--lg-rule)] pt-6">
      <button className="lg-button" data-primary="true" disabled={!done || writes === 0}>
        Download {writes} repaired {writes === 1 ? 'file' : 'files'}
      </button>
      {canWriteInPlace && (
        <button className="lg-button" disabled={!done || writes === 0}>
          Write into the folder
        </button>
      )}
      <button className="lg-button ml-auto" onClick={onReset}>
        Empty the drawer
      </button>
      <p className="w-full text-sm text-[var(--lg-muted)]">
        Dry run by default. Only verified cards are written, only missing fields are filled, and no
        existing value is ever blanked.
      </p>
    </section>
  )
}

function DetailCard({ book, onBack }: { book: BookResult; onBack: () => void }) {
  const p = book.proposal
  const v = verdict(book)
  return (
    <section className="mt-10">
      <button
        className="text-sm text-[var(--lg-ink-soft)] underline underline-offset-4 hover:text-[var(--lg-ink)]"
        onClick={onBack}
      >
        Back to the drawer
      </button>
      <article className="lg-card mt-4 px-6 py-5 md:px-10 md:py-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="lg-display text-3xl leading-tight md:text-4xl">{book.facts.title}</h2>
            <p className="mt-1 text-[var(--lg-ink-soft)]">
              {book.facts.author}
              {book.facts.series && `, ${book.facts.series} ${book.facts.series_index}`}
            </p>
          </div>
          <span className="lg-stamp text-base" style={{ color: INK[v] }}>
            {STAMP[v]}
          </span>
        </div>

        {p === null ? (
          <p className="mt-8 leading-7 text-[var(--lg-ink-soft)]">
            No catalogue answered for this filename. Nothing is proposed.
          </p>
        ) : p.unreadable ? (
          <p className="mt-8 leading-7 text-[var(--lg-ink-soft)]">
            The file's existing metadata could not be read, so nothing is proposed. A failed read is
            not an empty book.
          </p>
        ) : (
          <div className="mt-8 grid gap-10 md:grid-cols-2">
            <div>
              <h3 className="lg-display-italic text-xl">What each catalogue said</h3>
              <ul className="mt-2">
                {p.scores.map((s) => {
                  const trusted = p.sources.includes(s.name)
                  return (
                    <li
                      key={s.name}
                      className="grid grid-cols-[6.5rem_1fr] gap-3 text-sm leading-7"
                    >
                      <span className="text-[var(--lg-ink-soft)]">{SOURCE_LABEL[s.name]}</span>
                      <span
                        className={
                          trusted
                            ? ''
                            : 'text-[var(--lg-muted)] line-through decoration-[var(--lg-low)]'
                        }
                      >
                        {s.title}
                        <span className="ml-2 text-xs text-[var(--lg-muted)]">
                          {s.title_score.toFixed(2)} / {s.author_score.toFixed(2)}
                        </span>
                      </span>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-3 text-xs leading-5 text-[var(--lg-muted)]">
                Scores are title and author against the filename. Struck through: answered, but did
                not identify this book on its own, so it may not supply a field.
              </p>
            </div>
            <div>
              <h3 className="lg-display-italic text-xl">
                {Object.keys(p.gains).length ? 'Would be written' : 'Nothing to add'}
              </h3>
              <dl className="mt-2">
                {Object.entries(p.gains).map(([field, value]) => (
                  <div key={field} className="grid grid-cols-[6.5rem_1fr] gap-3 text-sm leading-7">
                    <dt className="text-[var(--lg-ink-soft)] capitalize">{field}</dt>
                    <dd>
                      {currentValue(p.current, field) && (
                        <span className="block text-[var(--lg-muted)] line-through">
                          {currentValue(p.current, field)}
                        </span>
                      )}
                      {Array.isArray(value) ? value.join(', ') : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        )}
      </article>
    </section>
  )
}

function currentValue(meta: Metadata, field: string) {
  const value = (meta as unknown as Record<string, unknown>)[field]
  if (Array.isArray(value)) return value.join(', ')
  return value ? String(value) : ''
}

function Explainer() {
  return (
    <section className="mt-28 grid gap-8 md:grid-cols-[1fr_2fr]">
      <h2 className="lg-display text-3xl leading-tight">How a card earns its stamp</h2>
      <div className="space-y-5 text-lg leading-8">
        <p>
          The obvious fix for messy ebook metadata is to look each book up online and write back
          whatever comes back. That is also how you destroy a library. Catalogues confidently return
          the wrong book, and a bulk run that trusts them corrupts hundreds of files at once,
          quietly.
        </p>
        <p>
          So the filename is the ground truth. Every answer is scored against the title and the
          author in it. A card is stamped{' '}
          <em className="lg-display-italic text-[var(--lg-high)]">verified</em> only when two
          catalogues each identify the book on their own and agree with each other, and only those
          catalogues may fill in a field. One witness is never enough: on a real library a single
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
