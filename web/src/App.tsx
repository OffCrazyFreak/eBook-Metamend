import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { flushSync } from 'react-dom'
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'

import mark from '../../assets/brand/icon/icon-square-512.png'
import wordmark from '../../assets/brand/wordmark/wordmark-white-on-transparent-800w.png'
import { Sketches } from '@/components/sketches'
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

type Verdict = Confidence | 'NONE' | 'UNREADABLE'

const VERDICT_LABEL: Record<Verdict, string> = {
  HIGH: 'HIGH',
  MED: 'MED',
  LOW: 'LOW',
  NONE: 'NO ANSWER',
  UNREADABLE: 'UNREADABLE',
}

const EASE = [0.2, 0.8, 0.2, 1] as const

export function App() {
  const { state, start, reset } = useRun()
  const [selected, setSelected] = useState<BookResult | null>(null)
  const [origin, setOrigin] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'writes'>('all')
  const reduced = useReducedMotion()
  const morph = !reduced && typeof document.startViewTransition === 'function'

  // The dialog grows out of the clicked row and shrinks back into it. The row
  // must carry the transition name before the old snapshot is taken, and the
  // dialog must be in the DOM before the new one is, hence the flushSync pairs.
  const open = useCallback(
    (book: BookResult) => {
      if (!morph) {
        setSelected(book)
        return
      }
      flushSync(() => setOrigin(book.stem))
      document.startViewTransition(() => flushSync(() => setSelected(book)))
    },
    [morph],
  )
  const close = useCallback(() => {
    if (!morph) {
      setSelected(null)
      return
    }
    const transition = document.startViewTransition(() => flushSync(() => setSelected(null)))
    transition.finished.finally(() => setOrigin(null))
  }, [morph])

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
  const wide = useMediaQuery('(min-width: 768px)')
  const scrolled = useScrolledPast(140)
  // The hero owns the lockup until it scrolls away or the run replaces the hero;
  // then the header picks it up. Narrow screens have no hero mark, so the header
  // always carries the name there.
  const heroHasLockup = wide && state.phase === 'idle' && !scrolled

  return (
    <div className="bp-sheet">
      <Sketches />
      <LayoutGroup>
        <Header showLockup={!heroHasLockup} scrolled={scrolled} />
        <div className="mx-auto max-w-6xl px-4 pb-8 sm:px-6 md:px-10">
          {state.phase === 'idle' && <Hero onStart={start} showLockup={heroHasLockup} />}
          {state.phase === 'loading' && (
            <Loading progress={state.loading.progress} label={state.loading.label} />
          )}
          {(state.phase === 'running' || state.phase === 'done') && (
            <>
              <Summary
                books={state.books}
                counts={counts}
                phase={state.phase}
                elapsedMs={state.elapsedMs}
                filter={filter}
                onFilter={setFilter}
              />
              <Results
                books={visible}
                active={state.active}
                origin={selected === null ? origin : null}
                onSelect={open}
              />
              <Actions counts={counts} done={state.phase === 'done'} onReset={reset} />
            </>
          )}

          <Explainer />
          <Footer />
        </div>
      </LayoutGroup>

      <Detail book={selected} morph={morph} onClose={close} />
    </div>
  )
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const list = window.matchMedia(query)
    const update = () => setMatches(list.matches)
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [query])
  return matches
}

function useScrolledPast(offset: number) {
  const [past, setPast] = useState(() => window.scrollY > offset)
  useEffect(() => {
    const update = () => setPast(window.scrollY > offset)
    window.addEventListener('scroll', update, { passive: true })
    return () => window.removeEventListener('scroll', update)
  }, [offset])
  return past
}

// Sticky, and it catches the lockup from the hero as the page scrolls: the same
// layoutId on both ends makes Motion fly the mark and name up into the bar.
function Header({ showLockup, scrolled }: { showLockup: boolean; scrolled: boolean }) {
  return (
    <header className="bp-bar sticky top-0 z-40" data-scrolled={scrolled}>
      <div className="mx-auto flex h-12 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 md:h-14 md:px-10">
        <a href="#top" className="flex h-full items-center">
          {showLockup ? <Lockup size="bar" /> : <span aria-hidden="true" />}
        </a>
        <nav className="bp-mono flex gap-4 text-[11px] tracking-wider uppercase sm:gap-6 md:text-xs">
          <a className="bp-link" href="#how-it-decides">
            How it decides
          </a>
          <a className="bp-link" href="https://github.com/OffCrazyFreak/eBook-Metamend">
            GitHub
          </a>
        </nav>
      </div>
    </header>
  )
}

// Three arrangements. Phones: headline, standfirst, intake, no mark. Tablets: the
// mark on the left, headline beside it, intake full width below. Desktop: a
// two-thirds column with mark and wordmark stacked over the headline, intake in
// the remaining third.
function Hero({
  onStart,
  showLockup,
}: {
  onStart: (names: string[]) => void
  showLockup: boolean
}) {
  const reduced = useReducedMotion()
  const rise = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.55, delay, ease: EASE },
  })

  return (
    <section
      id="top"
      className="mt-5 grid gap-y-6 sm:mt-8 md:mt-10 md:gap-y-8 lg:grid-cols-[2fr_1fr] lg:items-center lg:gap-x-14"
    >
      <div className="md:grid md:grid-cols-[10rem_1fr] md:items-center md:gap-x-8 lg:block">
        <div className="hidden md:block">
          {showLockup ? <Lockup size="hero" /> : <LockupSpace />}
        </div>
        <div className="min-w-0">
          <motion.h1
            className="bp-display max-w-2xl text-[1.45rem] leading-[1.14] font-semibold text-balance sm:text-2xl md:text-3xl lg:mt-7 lg:text-[2.6rem] lg:leading-[1.1]"
            {...rise(0.1)}
          >
            Repair the metadata in your ebooks without letting a catalogue lie to you.
          </motion.h1>
          <motion.p
            className="mt-2.5 max-w-xl text-sm text-[var(--bp-muted)] sm:mt-3 md:text-base lg:mt-4"
            {...rise(0.2)}
          >
            Your filenames are the ground truth. Three catalogues are asked about each book, and a
            field is written only when two of them identify the same book on their own and agree.
          </motion.p>
        </div>
      </div>

      <Intake onStart={onStart} />
    </section>
  )
}

// The mark with its drifting cubes, and on desktop the wordmark beside it at
// half the mark's height. In the bar it shrinks to a badge and the name.
function Lockup({ size }: { size: 'hero' | 'bar' }) {
  const reduced = useReducedMotion()
  const hero = size === 'hero'
  return (
    <motion.div
      layoutId="lockup"
      layout
      className={hero ? 'flex items-end gap-5 lg:gap-6' : 'flex items-center gap-2.5'}
      transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 30 }}
    >
      <motion.div
        layout
        className={`bp-mark relative aspect-square shrink-0 ${hero ? 'w-40' : 'w-9 md:w-10'}`}
        aria-hidden="true"
      >
        <img src={mark} alt="" className="bp-mark-image h-full w-full" />
        {hero && (
          <>
            <span className="bp-cube" style={{ top: '4%', left: '2%', animationDelay: '0s' }} />
            <span
              className="bp-cube"
              style={{ top: '16%', right: '0%', animationDelay: '-2.5s' }}
            />
            <span className="bp-cube" style={{ bottom: '8%', left: '8%', animationDelay: '-5s' }} />
          </>
        )}
      </motion.div>
      <motion.img
        layout
        src={wordmark}
        alt="eBook Metamend"
        className={hero ? 'mb-6 hidden h-20 w-auto lg:block' : 'h-5 w-auto md:h-6'}
      />
    </motion.div>
  )
}

// Holds the hero's lockup slot open while the bar has the lockup, so the
// headline does not jump when the lockup leaves.
function LockupSpace() {
  return <div className="h-40 w-40" aria-hidden="true" />
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
    <div>
      <motion.div
        className="bp-brackets"
        data-over={over}
        initial={reduced ? false : { opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="bp-corner" />
        <div
          role="region"
          aria-label="Drop EPUB or PDF files or a folder here"
          className="bp-panel bp-target flex min-h-[9.5rem] flex-col items-center justify-center gap-3 px-4 py-5 text-center sm:gap-4 sm:px-5 sm:py-6 md:min-h-[13rem]"
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
          <span className="bp-dim w-28 self-start">intake</span>
          <p className="bp-display text-base sm:text-lg md:text-xl">
            {over ? 'Release to start the dry run' : 'Drop files or a folder here'}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <button className="bp-button" onClick={() => fileInput.current?.click()}>
              Choose files
            </button>
            <button className="bp-button" onClick={() => folderInput.current?.click()}>
              Choose a folder
            </button>
          </div>
          <p className="bp-mono text-[11px] text-[var(--bp-muted)]">
            EPUB and PDF. Files never leave this tab.
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
      <p className="bp-mono mt-3 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase sm:mt-4">
        No files to hand?{' '}
        <button className="bp-link underline underline-offset-4" onClick={() => onStart([])}>
          Play the invented sample
        </button>
      </p>
    </div>
  )
}

// The mark draws itself in as the runtime downloads: the book's outline follows
// the progress, and the wrench drops in when it reaches the end.
function Loading({ progress, label }: { progress: number; label: string }) {
  const reduced = useReducedMotion()
  const done = progress >= 1
  return (
    <section className="mt-16 flex flex-col items-center text-center md:mt-20" aria-live="polite">
      <svg viewBox="0 0 200 200" className="h-40 w-40 md:h-48 md:w-48" aria-hidden="true">
        {/* the book: a slab in isometric view, three faces */}
        {[
          'M 60 150 L 60 70 L 120 40 L 120 120 Z',
          'M 60 150 L 84 162 L 144 132 L 120 120',
          'M 120 40 L 144 52 L 144 132',
          'M 66 72 L 66 146 M 72 75 L 72 149 M 78 78 L 78 152',
        ].map((d, i) => (
          <motion.path
            key={i}
            d={d}
            className="bp-wire"
            pathLength={1}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: Math.max(0, Math.min(1, progress * 1.15 - i * 0.05)) }}
            transition={{ duration: 0.4, ease: 'linear' }}
          />
        ))}
        {/* the wrench, dropped in at the end */}
        <motion.g
          initial={{ opacity: 0, y: -40, rotate: -20 }}
          animate={done ? { opacity: 1, y: 0, rotate: 0 } : { opacity: 0, y: -40, rotate: -20 }}
          transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 320, damping: 18 }}
          style={{ originX: '90px', originY: '100px' }}
        >
          <path
            d="M 78 118 L 100 96 M 100 96 a 9 9 0 1 0 8 -8 l -4 4 l 4 4"
            className="bp-wire"
            style={{ strokeWidth: 3 }}
          />
        </motion.g>
        {/* three cubes, each lit when its share of the download lands */}
        {[
          [40, 60],
          [160, 60],
          [100, 176],
        ].map(([x, y], i) => (
          <motion.path
            key={i}
            d={`M ${x} ${y - 8} l 7 4 v 8 l -7 4 l -7 -4 v -8 z M ${x - 7} ${y - 4} l 7 4 l 7 -4 M ${x} ${y} v 8`}
            className="bp-wire"
            initial={{ opacity: 0.15 }}
            animate={{ opacity: progress > (i + 1) / 3 - 0.01 ? 1 : 0.15 }}
            transition={{ duration: 0.3 }}
          />
        ))}
      </svg>
      <span className="bp-dim mt-4 w-64">loading python</span>
      <p className="bp-display mt-4 text-2xl md:text-3xl">{label}</p>
      <p className="bp-mono mt-3 text-xs text-[var(--bp-muted)]">
        {Math.round(progress * 100)}% of about 6 MB, once. Cached after that.
      </p>
    </section>
  )
}

function Summary({
  books,
  counts,
  phase,
  elapsedMs,
  filter,
  onFilter,
}: {
  books: BookResult[]
  counts: { done: number; total: number; high: number; writes: number }
  phase: 'running' | 'done'
  elapsedMs: number
  filter: 'all' | 'writes'
  onFilter: (f: 'all' | 'writes') => void
}) {
  return (
    <section className="mt-10" aria-live="polite">
      <div className="grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <span className="bp-dim w-64">{phase === 'done' ? 'dry run complete' : 'dry run'}</span>
          <p className="bp-display mt-4 text-3xl md:text-4xl">
            <span className="bp-mono">{counts.done}</span> of{' '}
            <span className="bp-mono">{counts.total}</span> books checked
            {phase === 'running' && <span className="bp-cursor" aria-hidden="true" />}
          </p>
          <p className="mt-2 text-[var(--bp-muted)]">
            <span className="bp-mono text-[var(--bp-cyan)]">{counts.high}</span> identified with
            high confidence, <span className="bp-mono text-[var(--bp-ink)]">{counts.writes}</span>{' '}
            would be written
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
      </div>

      {/* One segment per book, filled in the verdict's tone as it lands; reads as
          the run's summary once it is over. */}
      <ol className="mt-6 flex h-2 gap-[2px]" aria-label="Progress by book">
        {books.map((b) => (
          <li
            key={b.stem}
            className="bp-segment flex-1"
            data-verdict={b.status === 'done' ? verdict(b) : 'PENDING'}
          />
        ))}
      </ol>
    </section>
  )
}

function Results({
  books,
  active,
  origin,
  onSelect,
}: {
  books: BookResult[]
  active: string | null
  // The row the open dialog grew out of; it carries the view transition name
  // until the dialog is up, and again while the dialog shrinks back into it.
  origin: string | null
  onSelect: (b: BookResult) => void
}) {
  const reduced = useReducedMotion()
  return (
    <ol className="bp-panel mt-6 px-4 pt-3 [--row-inset:1rem] md:px-6 md:[--row-inset:1.5rem]">
      <li className="bp-mono grid grid-cols-[2.5rem_1fr_auto] items-center gap-4 pb-3 text-xs tracking-wider text-[var(--bp-muted)] uppercase md:grid-cols-[2.5rem_1fr_10rem_7rem_8rem]">
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
              className="bp-row"
              data-inking={done && !reduced ? 'true' : undefined}
              initial={reduced ? false : { clipPath: 'inset(0 100% 0 0)' }}
              animate={{ clipPath: 'inset(0 0% 0 0)' }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <button
                disabled={!done}
                onClick={() => onSelect(book)}
                style={origin === book.stem ? { viewTransitionName: 'detail' } : undefined}
                className="bp-row-button grid w-full grid-cols-[2.5rem_1fr_auto] items-center gap-4 py-3 text-left focus-visible:outline-none disabled:cursor-default md:grid-cols-[2.5rem_1fr_10rem_7rem_8rem]"
              >
                <span className="bp-mono text-xs text-[var(--bp-muted)]">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="min-w-0">
                  <span className="bp-row-title block truncate">{book.facts.title}</span>
                  <span className="block truncate text-sm text-[var(--bp-muted)]">
                    {book.facts.author}
                    {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
                    <span className="bp-mono">
                      {' '}
                      · {book.files.map((f) => f.slice(1)).join(' + ')}
                    </span>
                  </span>
                  {done && book.proposal && (
                    <span className="bp-mono block truncate text-xs text-[var(--bp-muted)] md:hidden">
                      gains: {Object.keys(book.proposal.gains).join(', ') || 'none'}
                    </span>
                  )}
                </span>
                <span className="bp-mono hidden text-xs text-[var(--bp-muted)] md:block">
                  {(done ? (book.proposal?.sources ?? []) : (book.answered ?? [])).map(
                    (s, n, all) => (
                      <motion.span
                        key={s}
                        className="inline-block"
                        initial={reduced || done ? false : { opacity: 0, x: -8, color: '#35c6ff' }}
                        animate={{ opacity: 1, x: 0, color: '#a7b6d9' }}
                        transition={{ duration: 0.5, ease: EASE, color: { duration: 0.9 } }}
                      >
                        {SOURCE_LABEL[s].split(' ')[0]}
                        {n < all.length - 1 ? ',\u00a0' : ''}
                      </motion.span>
                    ),
                  )}
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
                      data-verdict={v}
                      initial={reduced ? false : { scale: 1.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 420, damping: 22, delay: 0.25 }}
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
    <section className="mt-8 grid gap-3 border-t border-[var(--bp-line-strong)] pt-6 md:flex md:flex-wrap md:items-center">
      <button
        className="bp-button w-full md:w-auto"
        data-primary="true"
        disabled={!done || counts.writes === 0}
      >
        Download {counts.writes} repaired {counts.writes === 1 ? 'file' : 'files'}
      </button>
      {canWriteInPlace && (
        <button className="bp-button w-full md:w-auto" disabled={!done || counts.writes === 0}>
          Write into the folder
        </button>
      )}
      <button className="bp-button w-full md:ml-auto md:w-auto" onClick={onReset}>
        Start over
      </button>
      <p className="bp-mono w-full text-xs text-[var(--bp-muted)]">
        Dry run by default. Only HIGH verdicts are written, only missing fields are filled, and no
        existing value is ever blanked.{' '}
        {canWriteInPlace
          ? 'This browser can write repairs straight back into the folder you chose.'
          : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
      </p>
    </section>
  )
}

function Detail({
  book,
  morph,
  onClose,
}: {
  book: BookResult | null
  morph: boolean
  onClose: () => void
}) {
  const p = book?.proposal ?? null
  return (
    <Dialog open={book !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        // The view transition owns the entrance, so the stock zoom is switched off.
        style={morph ? { viewTransitionName: 'detail', animation: 'none' } : undefined}
        overlayStyle={
          morph ? { viewTransitionName: 'detail-overlay', animation: 'none' } : undefined
        }
        className="max-h-[90vh] max-w-2xl overflow-y-auto border-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-0 text-[var(--bp-ink)] sm:max-w-2xl"
      >
        {book && (
          <div className="p-6 md:p-8">
            <span className="bp-dim w-48">sheet detail</span>
            <DialogTitle className="bp-display mt-4 text-2xl leading-tight text-[var(--bp-ink)]">
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
                  <span className="bp-stamp text-base" data-verdict={p.conf}>
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
                              : 'text-[var(--bp-muted)] line-through decoration-[var(--bp-line-strong)]'
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
    <section id="how-it-decides" className="mt-20 scroll-mt-8 md:mt-32">
      <span className="bp-dim w-64">how it decides</span>
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_26rem] lg:gap-16">
        <div className="max-w-2xl space-y-6 text-base leading-relaxed md:text-lg">
          <p>
            The obvious fix for messy ebook metadata is to look each book up online and write back
            whatever comes back. That is also how you destroy a library. Catalogues confidently
            return the wrong book, and a bulk run that trusts them corrupts hundreds of files at
            once, quietly.
          </p>
          <p>
            So the filename is the ground truth. Every answer is scored against the title and the
            author in it. A book reaches{' '}
            <span className="bp-stamp align-middle" data-verdict="HIGH">
              HIGH
            </span>{' '}
            only when two catalogues each identify it on their own and agree with each other, and
            only those catalogues may supply fields. One source is never enough: on a real library a
            single source returned an abridgement, a translation and a different book entirely for
            three correctly named files.
          </p>
          <p>
            Fields are added or improved, never emptied. Dry run is the default. And the files never
            leave your browser: the Python that does this work runs inside the page.
          </p>
        </div>
        <Agreement />
      </div>
    </section>
  )
}

// The rule as a drawing: the filename in the middle, three catalogues around
// it. Two agree and their wires light up; the third answered another book and
// stays dashed. Draws itself when scrolled into view; hovering or focusing a
// catalogue shows what it answered for one invented book.
const DIAGRAM_ANSWERS = {
  apple: {
    name: 'Apple Books',
    answer: 'The Quiet Lathe, Ilse Marrow',
    scores: 'title 1.00 · author 1.00',
    agrees: true,
  },
  openlib: {
    name: 'Open Library',
    answer: 'The Quiet Lathe, Ilse Marrow',
    scores: 'title 1.00 · author 1.00',
    agrees: true,
  },
  inventaire: {
    name: 'Inventaire',
    answer: 'The Quiet Loom, Ilse Marrow',
    scores: 'title 0.62 · author 1.00',
    agrees: false,
  },
} as const

type DiagramNode = keyof typeof DIAGRAM_ANSWERS

function Agreement() {
  const reduced = useReducedMotion()
  const [active, setActive] = useState<DiagramNode | null>(null)
  const draw = (delay: number) => ({
    initial: reduced ? false : { pathLength: 0, opacity: 0 },
    whileInView: { pathLength: 1, opacity: 1 },
    viewport: { once: true, margin: '-40px' },
    transition: { duration: 0.9, delay, ease: EASE },
  })
  const fade = (delay: number) => ({
    initial: reduced ? false : { opacity: 0 },
    whileInView: { opacity: 1 },
    viewport: { once: true, margin: '-40px' },
    transition: { duration: 0.5, delay },
  })
  // Geometry in one place: the centre box and the three node boxes.
  const core = { x: 96, y: 150, w: 208, h: 44 }
  const nodes: Record<DiagramNode, { x: number; y: number }> = {
    apple: { x: 16, y: 40 },
    openlib: { x: 264, y: 40 },
    inventaire: { x: 140, y: 268 },
  }
  const box = { w: 120, h: 44 }
  const cx = core.x + core.w / 2
  const cy = core.y + core.h / 2
  const anchor = (id: DiagramNode) => {
    const n = nodes[id]
    return id === 'inventaire'
      ? { x: n.x + box.w / 2, y: n.y }
      : { x: n.x + box.w / 2, y: n.y + box.h }
  }
  const caption = active ? DIAGRAM_ANSWERS[active] : null

  return (
    <div className="w-full max-w-md self-start justify-self-center lg:justify-self-end">
      <svg
        viewBox="0 0 400 330"
        className="bp-mono w-full text-[11px]"
        role="img"
        aria-label="Diagram: the filename in the centre, three catalogues around it, two agreeing"
      >
        {(Object.keys(nodes) as DiagramNode[]).map((id, i) => {
          const a = anchor(id)
          const agrees = DIAGRAM_ANSWERS[id].agrees
          return (
            <motion.line
              key={id}
              x1={cx}
              y1={cy}
              x2={a.x}
              y2={a.y}
              className={agrees ? 'bp-wire' : 'bp-wire-dashed'}
              data-active={active === id}
              {...draw(0.2 + i * 0.2)}
            />
          )
        })}
        <motion.path
          d={`M ${nodes.apple.x + box.w} ${nodes.apple.y + 10} Q 200 -6 ${nodes.openlib.x} ${nodes.openlib.y + 10}`}
          className="bp-wire"
          {...draw(0.9)}
        />
        <motion.text
          x="200"
          y="14"
          textAnchor="middle"
          className="fill-[var(--bp-cyan)]"
          {...fade(1.2)}
        >
          two agree: HIGH
        </motion.text>

        <motion.g {...fade(0)}>
          <rect x={core.x} y={core.y} width={core.w} height={core.h} className="bp-node-core" />
          <text x={cx} y={cy - 3} textAnchor="middle" className="fill-[var(--bp-ink)]">
            the filename
          </text>
          <text x={cx} y={cy + 12} textAnchor="middle" className="fill-[var(--bp-muted)]">
            Ilse Marrow · The Quiet Lathe
          </text>
        </motion.g>

        {(Object.keys(nodes) as DiagramNode[]).map((id, i) => {
          const n = nodes[id]
          const info = DIAGRAM_ANSWERS[id]
          return (
            <motion.g
              key={id}
              role="button"
              tabIndex={0}
              aria-label={`${info.name} answered ${info.answer}`}
              className="cursor-pointer outline-none"
              data-active={active === id}
              onMouseEnter={() => setActive(id)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(id)}
              onBlur={() => setActive(null)}
              {...fade(0.3 + i * 0.2)}
            >
              <rect
                x={n.x}
                y={n.y}
                width={box.w}
                height={box.h}
                className={info.agrees ? 'bp-node' : 'bp-node-dim'}
              />
              <text
                x={n.x + box.w / 2}
                y={n.y + 18}
                textAnchor="middle"
                className="fill-[var(--bp-ink)]"
              >
                {info.name}
              </text>
              <text
                x={n.x + box.w / 2}
                y={n.y + 33}
                textAnchor="middle"
                className={info.agrees ? 'fill-[var(--bp-cyan)]' : 'fill-[var(--bp-muted)]'}
              >
                {info.agrees ? 'agrees' : 'another book'}
              </text>
            </motion.g>
          )
        })}
      </svg>
      <p className="bp-mono mt-2 min-h-[2.5rem] text-xs text-[var(--bp-muted)]" aria-live="polite">
        {caption ? (
          <>
            <span className="text-[var(--bp-ink)]">{caption.name}</span> answered{' '}
            <span className="text-[var(--bp-ink)]">{caption.answer}</span>. {caption.scores}.{' '}
            {caption.agrees
              ? 'Identifies the book on its own.'
              : 'Wrong book: no say in what is written.'}
          </>
        ) : (
          'Hover or focus a catalogue to see what it answered.'
        )}
      </p>
    </div>
  )
}

function Footer() {
  return (
    <footer className="bp-mono mt-14 flex flex-wrap gap-x-6 gap-y-2 border-t border-[var(--bp-line)] pt-5 text-xs text-[var(--bp-muted)] md:mt-20">
      <span>Files never leave this tab.</span>
      <a className="bp-link ml-auto" href="https://github.com/OffCrazyFreak/eBook-Metamend">
        GitHub
      </a>
      <span>MIT licence</span>
    </footer>
  )
}
