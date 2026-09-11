import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'

import mark from '../../assets/brand/icon/icon-square-512.png'
import wordmark from '../../assets/brand/wordmark/wordmark-white-on-transparent-800w.png'
import { Sketches } from '@/components/sketches'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
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
              <Results books={visible} active={state.active} onSelect={setSelected} />
              <Actions counts={counts} done={state.phase === 'done'} onReset={reset} />
            </>
          )}

          <Explainer />
          <Footer />
        </div>
      </LayoutGroup>

      <Detail book={selected} onClose={() => setSelected(null)} />
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

function Loading({ progress, label }: { progress: number; label: string }) {
  return (
    <section className="mt-20 flex flex-col items-center text-center" aria-live="polite">
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
  onSelect,
}: {
  books: BookResult[]
  active: string | null
  onSelect: (b: BookResult) => void
}) {
  const reduced = useReducedMotion()
  return (
    <ol className="bp-panel mt-6 px-4 pt-3 md:px-6">
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
    <section className="mt-8 flex flex-wrap items-center gap-3 border-t border-[var(--bp-line-strong)] pt-6">
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
        existing value is ever blanked.{' '}
        {canWriteInPlace
          ? 'This browser can write repairs straight back into the folder you chose.'
          : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
      </p>
    </section>
  )
}

function Detail({ book, onClose }: { book: BookResult | null; onClose: () => void }) {
  const p = book?.proposal ?? null
  return (
    <Sheet open={book !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-l-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-0 text-[var(--bp-ink)] sm:max-w-xl"
      >
        {book && (
          <div className="p-6 md:p-8">
            <span className="bp-dim w-48">sheet detail</span>
            <SheetTitle className="bp-display mt-4 text-2xl leading-tight text-[var(--bp-ink)]">
              {book.facts.title}
            </SheetTitle>
            <SheetDescription className="text-[var(--bp-muted)]">
              {book.facts.author}
              {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
            </SheetDescription>

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
      </SheetContent>
    </Sheet>
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
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_22rem] lg:gap-16">
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

// The rule as a drawing: the filename in the middle, three catalogues around it.
// Two agree and their lines light up; the third answered something else and
// stays a dashed hairline. Draws itself when scrolled into view.
function Agreement() {
  const reduced = useReducedMotion()
  const draw = (delay: number) => ({
    initial: reduced ? false : { pathLength: 0, opacity: 0 },
    whileInView: { pathLength: 1, opacity: 1 },
    viewport: { once: true, margin: '-80px' },
    transition: { duration: 0.9, delay, ease: EASE },
  })
  const fade = (delay: number) => ({
    initial: reduced ? false : { opacity: 0 },
    whileInView: { opacity: 1 },
    viewport: { once: true, margin: '-80px' },
    transition: { duration: 0.5, delay },
  })
  const nodes = [
    { name: 'Apple Books', x: 30, y: 44, agrees: true },
    { name: 'Open Library', x: 230, y: 44, agrees: true },
    { name: 'Inventaire', x: 130, y: 240, agrees: false },
  ]
  return (
    <svg
      viewBox="0 0 320 300"
      className="bp-mono w-full max-w-sm self-center justify-self-center text-[10px]"
      role="img"
      aria-label="Diagram: the filename in the centre, three catalogues around it, two agreeing"
    >
      <motion.line x1="160" y1="150" x2="60" y2="76" className="bp-wire" {...draw(0.2)} />
      <motion.line x1="160" y1="150" x2="260" y2="76" className="bp-wire" {...draw(0.4)} />
      <motion.line x1="160" y1="150" x2="160" y2="240" className="bp-wire-dashed" {...draw(0.6)} />
      <motion.path d="M 90 44 Q 160 4 230 44" className="bp-wire" {...draw(0.9)} />

      <motion.g {...fade(0)}>
        <rect x="100" y="132" width="120" height="36" className="bp-node-core" />
        <text x="160" y="149" textAnchor="middle" className="fill-[var(--bp-ink)]">
          filename
        </text>
        <text x="160" y="161" textAnchor="middle" className="fill-[var(--bp-muted)]">
          author · title
        </text>
      </motion.g>

      {nodes.map((n, i) => (
        <motion.g key={n.name} {...fade(0.3 + i * 0.2)}>
          <rect
            x={n.x}
            y={n.y}
            width="60"
            height="32"
            className={n.agrees ? 'bp-node' : 'bp-node-dim'}
          />
          <text x={n.x + 30} y={n.y + 14} textAnchor="middle" className="fill-[var(--bp-ink)]">
            {n.name}
          </text>
          <text
            x={n.x + 30}
            y={n.y + 26}
            textAnchor="middle"
            className={n.agrees ? 'fill-[var(--bp-cyan)]' : 'fill-[var(--bp-muted)]'}
          >
            {n.agrees ? 'agrees' : 'another book'}
          </text>
        </motion.g>
      ))}
      <motion.text
        x="160"
        y="22"
        textAnchor="middle"
        className="fill-[var(--bp-cyan)]"
        {...fade(1.2)}
      >
        two agree: HIGH
      </motion.text>
    </svg>
  )
}

function Footer() {
  return (
    <footer className="bp-mono mt-14 flex flex-wrap gap-x-8 gap-y-2 border-t border-[var(--bp-line)] pt-5 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase md:mt-20">
      <span>Files stay in this tab.</span>
      <span>
        Apple Books, Open Library and Inventaire receive the title and author from the filename,
        nothing else.
      </span>
      <a className="bp-link" href="https://github.com/OffCrazyFreak/eBook-Metamend">
        Source on GitHub
      </a>
      <span>MIT licence</span>
    </footer>
  )
}
