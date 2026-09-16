import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { flushSync } from 'react-dom'
import { Check, FolderPen, X } from 'lucide-react'
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'

import mark from '../../assets/brand/icon/icon-square-512.png'
import wordmark from '../../assets/brand/wordmark/wordmark-white-on-transparent-800w.png'
import { Sketches } from '@/components/sketches'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  canWriteInPlace,
  hasFiles,
  intakeFromDrop,
  intakeFromFileList,
  intakeFromFilePicker,
  intakeFromPicker,
  type Intake as IntakeResult,
} from '@/intake'
import { useRun, type Outcome } from '@/run/use-run'
import {
  DEFAULT_SELECTION,
  PRESET_LABEL,
  isSelected,
  matchingPreset,
  preset,
  toggled,
  type Preset,
  type Selection,
} from '@/selection'
import {
  SOURCE_LABEL,
  verdict,
  willWrite,
  type BookResult,
  type Confidence,
  type Metadata,
  type SourceName,
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
  // ?fail on the URL plays the runtime failure screen for design review.
  const {
    state,
    start,
    playSample: sample,
    reset,
    stop,
    retry,
    repair,
    writable,
  } = useRun({
    failLoad: new URLSearchParams(window.location.search).has('fail'),
  })
  const [selected, setSelected] = useState<BookResult | null>(null)
  const [origin, setOrigin] = useState<string | null>(null)
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
  const [flash, setFlash] = useState<string | null>(null)
  const jump = useCallback(
    (stem: string) => {
      setFlash(stem)
      requestAnimationFrame(() => {
        document
          .querySelector(`[data-stem="${CSS.escape(stem)}"]`)
          ?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' })
      })
      window.setTimeout(() => setFlash((f) => (f === stem ? null : f)), 1600)
    },
    [reduced],
  )
  const close = useCallback(() => {
    if (!morph) {
      setSelected(null)
      return
    }
    const transition = document.startViewTransition(() => flushSync(() => setSelected(null)))
    transition.finished.finally(() => setOrigin(null))
  }, [morph])

  const [selection, setSelection] = useState<Selection>(DEFAULT_SELECTION)
  // What happened to a book after the run, from the download and write-back paths.
  const [outcome, setOutcome] = useState<Map<string, Outcome>>(() => new Map())
  // Books a repair could not place, in one line under the actions.
  const [trouble, setTrouble] = useState<string[]>([])
  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    const writes = done.filter(willWrite)
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: writes.length,
      // Files the download would hold, and whether every repairable one is in.
      picked: writes.filter((b) => isSelected(selection, b) && !outcome.has(b.stem)).length,
      allWrites: writes.every((b) => isSelected(selection, b)),
      written: [...outcome.values()].filter((o) => o === 'written').length,
      downloaded: [...outcome.values()].filter((o) => o === 'downloaded').length,
    }
  }, [state.books, selection, outcome])
  const toggle = useCallback((book: BookResult) => setSelection((s) => toggled(s, book)), [])
  const choose = useCallback(
    (name: Preset) => setSelection(preset(name, state.books)),
    [state.books],
  )
  const [confirming, setConfirming] = useState(false)
  const [legend, setLegend] = useState(false)

  // Row shortcuts while results are up and no dialog or field has the keys.
  useEffect(() => {
    if (state.phase !== 'running' && state.phase !== 'done') return
    const onKey = (e: KeyboardEvent) => {
      const target = e.target
      if (target instanceof Element && target.closest('input, textarea, [role="dialog"]')) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const rows = [...document.querySelectorAll<HTMLButtonElement>('.bp-row-button')]
      const at = rows.findIndex((r) => r === document.activeElement)
      const focusRow = (i: number) => {
        rows[Math.max(0, Math.min(rows.length - 1, i))]?.focus()
        e.preventDefault()
      }
      switch (e.key) {
        case 'ArrowDown':
        case 'j':
          return focusRow(at + 1)
        case 'ArrowUp':
        case 'k':
          return focusRow(at < 0 ? 0 : at - 1)
        case ' ': {
          const stem = rows[at]?.closest<HTMLElement>('[data-stem]')?.dataset.stem
          const book = state.books.find((b) => b.stem === stem)
          if (book && book.status === 'done') {
            setSelection((sel) => toggled(sel, book))
            e.preventDefault()
          }
          return
        }
        case 'a':
          return choose('all')
        case 'n':
          return choose('none')
        case '?':
          return setLegend((l) => !l)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state.phase, state.books, choose])
  // Books already written or downloaded are done; a second pass would re-apply.
  const pickedBooks = useCallback(
    () =>
      state.books.filter((b) => willWrite(b) && isSelected(selection, b) && !outcome.has(b.stem)),
    [state.books, selection, outcome],
  )
  const [busy, setBusy] = useState(false)
  const place = useCallback(
    async (books: BookResult[], mode: Outcome) => {
      setBusy(true)
      try {
        const result = await repair(books, mode)
        setOutcome((prev) => new Map([...prev, ...result.outcomes]))
        setTrouble(result.failures)
      } catch (error) {
        // A refused permission or a failed zip must say so, not look like nothing happened.
        setTrouble([error instanceof Error ? error.message : String(error)])
      } finally {
        setBusy(false)
      }
    },
    [repair],
  )
  const download = useCallback((books: BookResult[]) => void place(books, 'downloaded'), [place])
  const write = useCallback(() => {
    setConfirming(false)
    void place(pickedBooks(), 'written')
  }, [pickedBooks, place])
  const [others, setOthers] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  // Only the sample link may start a run with no files; an empty drop or an
  // empty folder gets a line instead.
  const begin = useCallback(
    (intake: IntakeResult) => {
      if (intake.books.length === 0) {
        setNotice(
          intake.others === 0
            ? 'Nothing to check: no files came through.'
            : intake.others === 1
              ? 'That file is not an EPUB or a PDF.'
              : `None of those ${intake.others} files are EPUB or PDF.`,
        )
        return
      }
      setNotice(null)
      setOthers(intake.others)
      void start(intake)
    },
    [start],
  )
  // The dev server exposes the intake so an automated check can hand in
  // files with handles; the built site never has this.
  useEffect(() => {
    if (!import.meta.env.DEV) return
    ;(window as unknown as { __metamend?: unknown }).__metamend = { begin }
  }, [begin])
  const playSample = useCallback(() => {
    setNotice(null)
    setOthers(0)
    sample()
  }, [sample])
  const restart = useCallback(() => {
    setSelection(DEFAULT_SELECTION)
    setOutcome(new Map())
    setTrouble([])
    setOthers(0)
    reset()
  }, [reset])

  // A visitor parked on another tab can read the count off the title.
  useEffect(() => {
    document.title =
      state.phase === 'running'
        ? `${counts.done} of ${counts.total} \u00b7 eBook Metamend`
        : 'eBook Metamend'
  }, [state.phase, counts.done, counts.total])

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
        <Header
          showLockup={!heroHasLockup}
          scrolled={scrolled}
          progress={state.phase === 'running' && scrolled ? counts : null}
        />
        <div className="mx-auto max-w-6xl px-4 pb-8 sm:px-6 md:px-10">
          {state.phase === 'idle' && (
            <Hero
              onStart={begin}
              onSample={playSample}
              notice={notice}
              showLockup={heroHasLockup}
            />
          )}
          {(state.phase === 'loading' || state.phase === 'failed') && (
            <Loading
              progress={state.loading.progress}
              label={state.loading.label}
              error={state.error}
              onRetry={retry}
            />
          )}
          {(state.phase === 'running' || state.phase === 'done') && (
            <>
              <Summary
                books={state.books}
                counts={counts}
                phase={state.phase}
                elapsedMs={state.elapsedMs}
                others={others}
                sample={state.sample}
                pressed={matchingPreset(selection, state.books)}
                onPreset={choose}
                onJump={jump}
              />
              <Results
                books={state.books}
                active={state.active}
                origin={selected === null ? origin : null}
                flash={flash}
                outcome={outcome}
                selection={selection}
                onToggle={toggle}
                onToggleAll={(on) => choose(on ? 'all' : 'none')}
                onSelect={open}
                onLegend={() => setLegend(true)}
              />
              <Actions
                counts={counts}
                done={state.phase === 'done'}
                busy={busy}
                canWrite={canWriteInPlace && writable(pickedBooks())}
                trouble={trouble}
                unavailable={state.unavailable}
                onDownload={() => download(pickedBooks())}
                onWrite={() => setConfirming(true)}
                onReset={restart}
                onStop={stop}
              />
            </>
          )}

          <Explainer />
          <Footer />
        </div>
      </LayoutGroup>

      <Detail
        book={selected}
        morph={morph}
        outcome={selected ? outcome.get(selected.stem) : undefined}
        busy={busy}
        onDownload={() => selected && download([selected])}
        onClose={close}
      />
      <Legend open={legend} onClose={() => setLegend(false)} />
      <WriteConfirm
        open={confirming}
        count={counts.picked}
        onCancel={() => setConfirming(false)}
        onConfirm={write}
      />
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
function Header({
  showLockup,
  scrolled,
  progress,
}: {
  showLockup: boolean
  scrolled: boolean
  // Shown while a run is live and its summary has scrolled out of view.
  progress: { done: number; total: number } | null
}) {
  return (
    <header className="bp-bar sticky top-0 z-40" data-scrolled={scrolled}>
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 md:h-[4.5rem] md:px-10">
        <div className="flex h-full items-center gap-4">
          <a href="#top" className="flex h-full items-center">
            {showLockup ? <Lockup size="bar" /> : <span aria-hidden="true" />}
          </a>
          <AnimatePresence>
            {progress && (
              <motion.span
                className="bp-mono text-xs text-[var(--bp-muted)]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <span className="text-[var(--bp-cyan)]">{progress.done}</span> of {progress.total}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
        <nav className="bp-mono flex gap-4 text-[11px] tracking-wider whitespace-nowrap uppercase sm:gap-6 md:text-xs">
          <a className="bp-link hidden sm:inline" href="#how-it-decides">
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
  onSample,
  notice,
  showLockup,
}: {
  onStart: (intake: IntakeResult) => void
  onSample: () => void
  notice: string | null
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
            Repair ebook metadata, safely.
          </motion.h1>
          <motion.p
            className="mt-2.5 max-w-xl text-sm text-[var(--bp-muted)] sm:mt-3 md:text-base lg:mt-4"
            {...rise(0.2)}
          >
            Your filenames are the ground truth. Three catalogues are asked about each book, and a
            field is written only when two of them identify the same book on their own and agree. No
            catalogue gets to lie to you.
          </motion.p>
        </div>
      </div>

      <Intake onStart={onStart} onSample={onSample} notice={notice} />
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
      className={hero ? 'flex items-center gap-5 lg:gap-6' : 'flex items-center gap-3'}
      transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 30 }}
    >
      <motion.div
        layout
        className={`bp-mark relative aspect-square shrink-0 ${hero ? 'w-40' : 'w-[3.375rem] md:w-[3.75rem]'}`}
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
        className={hero ? 'hidden h-20 w-auto lg:block' : 'h-10 w-auto md:h-12'}
      />
    </motion.div>
  )
}

// Holds the hero's lockup slot open while the bar has the lockup, so the
// headline does not jump when the lockup leaves.
function LockupSpace() {
  return <div className="h-40 w-40" aria-hidden="true" />
}

function Intake({
  onStart,
  onSample,
  notice,
}: {
  onStart: (intake: IntakeResult) => void
  onSample: () => void
  notice: string | null
}) {
  const [over, setOver] = useState(false)
  // Files dragged anywhere over the page light the panel up and land here.
  const [pageOver, setPageOver] = useState(false)
  useEffect(() => {
    let depth = 0
    const enter = (e: globalThis.DragEvent) => {
      if (!hasFiles(e)) return
      depth += 1
      setPageOver(true)
    }
    const leave = () => {
      depth = Math.max(0, depth - 1)
      if (depth === 0) setPageOver(false)
    }
    const over = (e: globalThis.DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const drop = async (e: globalThis.DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      setPageOver(false)
      onStart(await intakeFromDrop(e))
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('dragover', over)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', drop)
    }
  }, [onStart])
  // Where the crosshair sits, as a fraction of the zone; centre when idle.
  const [aim, setAim] = useState({ x: 0.5, y: 0.5 })
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const reduced = useReducedMotion()

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    // The page-wide listener would otherwise start the same run twice.
    event.stopPropagation()
    setOver(false)
    setPageOver(false)
    setAim({ x: 0.5, y: 0.5 })
    onStart(await intakeFromDrop(event))
  }

  // The pickers that hand back handles, where the browser has them, so files
  // chosen either way can be written back; the plain inputs elsewhere.
  async function chooseFolder() {
    if (!canWriteInPlace) {
      folderInput.current?.click()
      return
    }
    const picked = await intakeFromPicker()
    if (picked) onStart(picked)
  }

  async function chooseFiles() {
    if (!canWriteInPlace) {
      fileInput.current?.click()
      return
    }
    const picked = await intakeFromFilePicker()
    if (picked) onStart(picked)
  }

  function track(event: DragEvent<HTMLDivElement>) {
    const r = event.currentTarget.getBoundingClientRect()
    setAim({
      x: Math.min(1, Math.max(0, (event.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (event.clientY - r.top) / r.height)),
    })
  }

  return (
    <div>
      <motion.div
        className="bp-brackets"
        data-over={over || pageOver}
        initial={reduced ? false : { opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="bp-corner" />
        <div
          role="region"
          aria-label="Drop EPUB or PDF files or a folder here"
          className="bp-panel bp-target relative flex min-h-[9.5rem] flex-col items-center justify-center gap-3 overflow-hidden px-4 py-5 text-center sm:gap-4 sm:px-5 sm:py-6 md:min-h-[13rem]"
          onDragEnter={(e) => hasFiles(e) && setOver(true)}
          onDragOver={(e) => {
            if (hasFiles(e)) {
              e.preventDefault()
              setOver(true)
              track(e)
            }
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) {
              setOver(false)
              setAim({ x: 0.5, y: 0.5 })
            }
          }}
          onDrop={onDrop}
        >
          <Crosshair aim={aim} live={over} />
          <span className="bp-dim w-fit min-w-28 self-start">intake</span>
          <p className="bp-display text-base sm:text-lg md:text-xl">
            {over || pageOver ? 'Release to start checking' : 'Drop files or a folder here'}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <button className="bp-button" onClick={() => void chooseFiles()}>
              Choose files
            </button>
            <button className="bp-button" onClick={() => void chooseFolder()}>
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
            onChange={(e) => onStart(intakeFromFileList(e.target.files))}
          />
          <input
            ref={folderInput}
            type="file"
            // @ts-expect-error webkitdirectory is not in the React types yet
            webkitdirectory=""
            className="sr-only"
            onChange={(e) => onStart(intakeFromFileList(e.target.files))}
          />
        </div>
      </motion.div>
      {notice && (
        <p className="bp-mono mt-3 text-xs text-[var(--bp-cyan)]" role="status">
          {notice}
        </p>
      )}
      <p className="bp-mono mt-3 text-[11px] tracking-wider text-[var(--bp-muted)] uppercase sm:mt-4">
        No files to hand?{' '}
        <button className="bp-link underline underline-offset-4" onClick={onSample}>
          Play the invented sample
        </button>
      </p>
    </div>
  )
}

// The mark draws itself in as the runtime downloads: the book's outline follows
// the progress, and the wrench drops in when it reaches the end.
// Hairlines across the whole zone follow the pointer while files are dragged
// over it; at rest only a faint ring marks the centre.
function Crosshair({ aim, live }: { aim: { x: number; y: number }; live: boolean }) {
  const reduced = useReducedMotion()
  const follow =
    live || reduced ? { duration: 0 } : { type: 'spring' as const, stiffness: 220, damping: 26 }
  const left = `${aim.x * 100}%`
  const top = `${aim.y * 100}%`
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <motion.div
        className="bp-aim-line absolute inset-x-0 h-px"
        animate={{ top, opacity: live ? 1 : 0 }}
        transition={follow}
      />
      <motion.div
        className="bp-aim-line absolute inset-y-0 w-px"
        animate={{ left, opacity: live ? 1 : 0 }}
        transition={follow}
      />
      <motion.div
        className="bp-aim-ring absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full"
        data-live={live}
        animate={{ left, top }}
        transition={follow}
      />
    </div>
  )
}

function Loading({
  progress,
  label,
  error,
  onRetry,
}: {
  progress: number
  label: string
  error: string | null
  onRetry: () => void
}) {
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
            className={error ? 'bp-wire-dashed' : 'bp-wire'}
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
      <span className="bp-dim mt-4 w-64">{error ? 'runtime not loaded' : 'loading python'}</span>
      {error ? (
        <>
          <p className="bp-display mt-4 text-2xl md:text-3xl">
            Stopped at {Math.round(progress * 100)}%
          </p>
          <p className="bp-mono mt-3 max-w-md text-xs text-[var(--bp-muted)]" role="alert">
            {error}
          </p>
          <button className="bp-mono bp-link mt-4 text-xs text-[var(--bp-cyan)]" onClick={onRetry}>
            [ retry ]
          </button>
        </>
      ) : (
        <>
          <p className="bp-display mt-4 text-2xl md:text-3xl">{label}</p>
          <p className="bp-mono mt-3 text-xs text-[var(--bp-muted)]">
            {Math.round(progress * 100)}% of about 6 MB, once. Cached after that.
          </p>
        </>
      )}
    </section>
  )
}

// The label over the count says what has happened to the files so far. "Dry
// run" read as a mode the visitor had chosen, when it is only the state before
// anything is written.
function stage(
  phase: 'running' | 'done',
  counts: { written: number; downloaded: number },
  sample: boolean,
): string {
  if (phase === 'running') return 'checking'
  // The invented sample pretends to write; there is no folder for it to touch.
  if (sample && (counts.written > 0 || counts.downloaded > 0)) return 'sample, nothing was written'
  if (counts.written > 0) return 'written into the folder'
  if (counts.downloaded > 0) return 'repairs downloaded'
  return 'checked, nothing written yet'
}

function Summary({
  books,
  counts,
  phase,
  elapsedMs,
  others,
  sample,
  pressed,
  onPreset,
  onJump,
}: {
  books: BookResult[]
  counts: {
    done: number
    total: number
    high: number
    writes: number
    written: number
    downloaded: number
  }
  phase: 'running' | 'done'
  elapsedMs: number
  others: number
  sample: boolean
  pressed: Preset | null
  onPreset: (name: Preset) => void
  onJump: (stem: string) => void
}) {
  const [hover, setHover] = useState<number | null>(null)
  return (
    <section className="mt-10" aria-live="polite">
      <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <span className="bp-dim w-fit min-w-64">{stage(phase, counts, sample)}</span>
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
            {counts.written > 0 && (
              <>
                {' '}
                <span className="bp-mono text-[var(--bp-cyan)]">{counts.written}</span> written.
              </>
            )}
            {counts.downloaded > 0 && (
              <>
                {' '}
                <span className="bp-mono text-[var(--bp-cyan)]">{counts.downloaded}</span>{' '}
                downloaded.
              </>
            )}
          </p>
          {others > 0 && (
            <p className="bp-mono mt-2 text-xs text-[var(--bp-muted)]">
              {others} {others === 1 ? 'file was' : 'files were'} not EPUB or PDF and{' '}
              {others === 1 ? 'was' : 'were'} left alone.
            </p>
          )}
        </div>
        <div
          className="bp-mono flex flex-wrap items-center gap-1 text-xs"
          role="group"
          aria-label="Select books"
        >
          <span className="mr-2 text-[var(--bp-muted)]">select</span>
          {(['all', 'writes', 'high', 'none'] as const).map((name) => (
            <button
              key={name}
              aria-pressed={pressed === name}
              onClick={() => onPreset(name)}
              className="border border-[var(--bp-line-strong)] px-3 py-1.5 tracking-wider uppercase aria-pressed:bg-[var(--bp-cyan)] aria-pressed:text-[var(--bp-deep)]"
            >
              {PRESET_LABEL[name]}
            </button>
          ))}
        </div>
      </div>

      {/* One segment per book, filled in the verdict's tone as it lands; reads as
          the run's summary once it is over. */}
      <ol className="relative mt-6 flex h-2 gap-[2px]" aria-label="Progress by book">
        {books.map((b, i) => (
          <li key={b.stem} className="relative flex-1">
            <button
              type="button"
              className="bp-segment block h-full w-full"
              data-verdict={b.status === 'done' ? verdict(b) : 'PENDING'}
              aria-label={`${b.facts.title}: ${b.status === 'done' ? VERDICT_LABEL[verdict(b)] : 'not checked yet'}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              onClick={() => onJump(b.stem)}
            />
          </li>
        ))}
        {hover !== null && books[hover] && (
          <span
            role="presentation"
            className="bp-mono bp-panel pointer-events-none absolute bottom-full mb-2 px-2 py-1 text-xs whitespace-nowrap text-[var(--bp-ink)]"
            style={{
              left: `${((hover + 0.5) / books.length) * 100}%`,
              transform:
                hover < books.length / 4
                  ? 'translateX(-0.5rem)'
                  : hover > (books.length * 3) / 4
                    ? 'translateX(calc(-100% + 0.5rem))'
                    : 'translateX(-50%)',
            }}
          >
            {books[hover].facts.title}
          </span>
        )}
      </ol>
    </section>
  )
}

function Results({
  books,
  active,
  origin,
  flash,
  outcome,
  selection,
  onToggle,
  onToggleAll,
  onSelect,
  onLegend,
}: {
  books: BookResult[]
  active: string | null
  // The row the open dialog grew out of; it carries the view transition name
  // until the dialog is up, and again while the dialog shrinks back into it.
  origin: string | null
  // The row a segment click jumped to; it flashes its rule once.
  flash: string | null
  outcome: Map<string, Outcome>
  selection: Selection
  onToggle: (book: BookResult) => void
  onToggleAll: (include: boolean) => void
  onSelect: (b: BookResult) => void
  onLegend: () => void
}) {
  const reduced = useReducedMotion()
  const checked = books.filter((b) => b.status === 'done')
  const picked = checked.filter((b) => isSelected(selection, b)).length
  return (
    <ol className="bp-panel mt-6 px-4 pt-3 [--row-inset:1rem] md:px-6 md:[--row-inset:1.5rem]">
      <li className="bp-mono grid grid-cols-[1.25rem_2.5rem_1fr_auto] items-center gap-4 pb-3 text-xs tracking-wider text-[var(--bp-muted)] uppercase lg:grid-cols-[1.25rem_2.5rem_1fr_10rem_7rem_8rem]">
        <Tick
          label="Select every checked book"
          checked={checked.length > 0 && picked === checked.length}
          indeterminate={picked > 0 && picked < checked.length}
          disabled={checked.length === 0}
          onChange={(on) => onToggleAll(on)}
        />
        <span>no.</span>
        <span>file</span>
        <span className="hidden lg:block">sources</span>
        <span className="hidden lg:block">gains</span>
        <span className="flex items-center justify-end gap-3">
          <button
            type="button"
            className="bp-link hidden normal-case lg:inline"
            onClick={() => onLegend()}
            aria-label="Keyboard shortcuts"
          >
            [ ? ]
          </button>
          verdict
        </span>
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
              data-stem={book.stem}
              data-flash={flash === book.stem ? 'true' : undefined}
              data-inking={done && !reduced ? 'true' : undefined}
              initial={reduced ? false : { clipPath: 'inset(0 100% 0 0)' }}
              animate={{ clipPath: 'inset(0 0% 0 0)' }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <div className="grid grid-cols-[1.25rem_1fr] items-center gap-4">
                {done ? (
                  <Tick
                    label={`Select ${book.facts.title}`}
                    checked={isSelected(selection, book)}
                    idle={!willWrite(book)}
                    onChange={() => onToggle(book)}
                  />
                ) : (
                  <span />
                )}
                <button
                  disabled={!done}
                  onClick={() => onSelect(book)}
                  style={origin === book.stem ? { viewTransitionName: 'detail' } : undefined}
                  className="bp-row-button grid w-full grid-cols-[2.5rem_1fr_auto] items-center gap-4 py-3 text-left focus-visible:outline-none disabled:cursor-default lg:grid-cols-[2.5rem_1fr_10rem_7rem_8rem]"
                >
                  <span className="bp-mono text-xs text-[var(--bp-muted)]">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="min-w-0">
                    <span className="bp-row-title line-clamp-2">{book.facts.title}</span>
                    <span className="line-clamp-2 text-sm text-[var(--bp-muted)]">
                      {book.facts.author}
                      {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
                      <span className="bp-mono">
                        {' '}
                        · {book.files.map((f) => f.slice(1)).join(' + ')}
                      </span>
                    </span>
                    {done && book.proposal && (
                      <span className="bp-mono line-clamp-2 text-xs text-[var(--bp-muted)] lg:hidden">
                        <Gains book={book} outcome={outcome.get(book.stem)} prefix="gains: " />
                      </span>
                    )}
                  </span>
                  <span className="bp-mono hidden text-xs text-[var(--bp-muted)] lg:block">
                    {(done ? (book.proposal?.sources ?? []) : (book.answered ?? [])).map(
                      (s, n, all) => (
                        <motion.span
                          key={s}
                          className="inline-block"
                          initial={
                            reduced || done ? false : { opacity: 0, x: -8, color: '#35c6ff' }
                          }
                          animate={{ opacity: 1, x: 0, color: '#a7b6d9' }}
                          transition={{ duration: 0.5, ease: EASE, color: { duration: 0.9 } }}
                        >
                          {SOURCE_LABEL[s].split(' ')[0]}
                          {n < all.length - 1 ? ',\u00a0' : ''}
                        </motion.span>
                      ),
                    )}
                  </span>
                  <span className="bp-mono hidden text-xs text-[var(--bp-muted)] lg:block">
                    {done && book.proposal && (
                      <Gains book={book} outcome={outcome.get(book.stem)} />
                    )}
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
                        {book.status === 'skipped'
                          ? 'skipped'
                          : active === book.stem
                            ? 'asking'
                            : 'queued'}
                      </span>
                    )}
                  </span>
                </button>
              </div>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ol>
  )
}

// The gains column once a file has gone out: a drawn check and the outcome
// replace the field list, which now lives in the file itself.
function Gains({
  book,
  outcome,
  prefix = '',
}: {
  book: BookResult
  outcome?: Outcome
  prefix?: string
}) {
  const reduced = useReducedMotion()
  if (!outcome)
    return <>{prefix + (Object.keys(book.proposal?.gains ?? {}).join(', ') || 'none')}</>
  return (
    <motion.span
      className="inline-flex items-center gap-1 text-[var(--bp-cyan)]"
      initial={reduced ? false : { opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, ease: EASE }}
    >
      <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
      {outcome}
    </motion.span>
  )
}

const KEYS: [string, string][] = [
  ['\u2191 \u2193 or j k', 'move between rows'],
  ['space', 'tick or untick the row'],
  ['enter', 'open the row'],
  ['a', 'select all'],
  ['n', 'select none'],
  ['?', 'this legend'],
]

function Legend({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="max-w-xs border-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-6 text-[var(--bp-ink)]"
      >
        <DialogClose className="bp-mono bp-link absolute top-5 right-5 text-xs text-[var(--bp-muted)]">
          [ close ]
        </DialogClose>
        <DialogTitle className="bp-dim w-40 text-xs">keys</DialogTitle>
        <DialogDescription className="sr-only">
          Keyboard shortcuts for the results list
        </DialogDescription>
        <dl className="bp-mono mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-xs">
          {KEYS.map(([key, what]) => (
            <div key={key} className="contents">
              <dt className="text-[var(--bp-cyan)]">{key}</dt>
              <dd className="text-[var(--bp-muted)]">{what}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}

// Writing changes files in place, so it gets a stop: the hero icon settles in
// with a spring, Cancel sits left and Write right, and Enter never confirms
// (the dialog focuses its container, so two stray Enters would run it).
function WriteConfirm({
  open,
  count,
  onCancel,
  onConfirm,
}: {
  open: boolean
  count: number
  onCancel: () => void
  onConfirm: () => void
}) {
  const reduced = useReducedMotion()
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent
        showCloseButton={false}
        className="max-w-sm border-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-0 text-[var(--bp-ink)]"
      >
        <div className="flex flex-col items-center px-6 pt-8 text-center">
          <motion.div
            className="relative flex size-14 items-center justify-center"
            initial={reduced ? false : { scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 20 }}
            aria-hidden="true"
          >
            <span className="absolute inset-0 rounded-full bg-[rgba(53,198,255,0.1)]" />
            <span className="absolute inset-1.5 rounded-full bg-[rgba(53,198,255,0.15)]" />
            <FolderPen className="relative size-6 text-[var(--bp-cyan)]" strokeWidth={2.2} />
          </motion.div>
          <DialogTitle className="bp-display mt-4 text-xl text-[var(--bp-ink)]">
            Write {count} {count === 1 ? 'file' : 'files'} into the folder?
          </DialogTitle>
          <DialogDescription className="mt-2 text-sm text-[var(--bp-muted)]">
            Only missing fields are added. Nothing is blanked, and every other file is left alone.
          </DialogDescription>
        </div>
        <div className="flex items-center justify-between gap-2 px-6 pt-3 pb-6">
          <button className="bp-button inline-flex items-center gap-2" onClick={onCancel}>
            <X className="size-4" aria-hidden="true" />
            Cancel
          </button>
          <button
            className="bp-button inline-flex items-center gap-2"
            data-primary="true"
            onClick={onConfirm}
          >
            <Check className="size-4" aria-hidden="true" />
            Write
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// A drafted checkbox: a square that fills cyan and gets a two-stroke tick.
function Tick({
  label,
  checked,
  indeterminate = false,
  disabled = false,
  idle = false,
  onChange,
}: {
  label: string
  checked: boolean
  indeterminate?: boolean
  disabled?: boolean
  // Nothing to write for this book: the box is dimmed but still works.
  idle?: boolean
  onChange: (checked: boolean) => void
}) {
  const box = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (box.current) box.current.indeterminate = indeterminate
  }, [indeterminate])
  return (
    <label className="bp-tick" data-disabled={disabled || undefined} data-idle={idle || undefined}>
      <input
        ref={box}
        type="checkbox"
        className="sr-only"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="bp-tick-box" aria-hidden="true">
        <svg viewBox="0 0 16 16" className="bp-tick-mark">
          <path d="M 3.5 8.5 L 6.5 11.5 L 12.5 4.5" pathLength={1} />
        </svg>
        <span className="bp-tick-dash" />
      </span>
    </label>
  )
}

function Actions({
  counts,
  done,
  busy,
  canWrite,
  trouble,
  unavailable,
  onDownload,
  onWrite,
  onReset,
  onStop,
}: {
  counts: { picked: number; allWrites: boolean }
  done: boolean
  // A repair is in flight: the buttons wait rather than start a second one.
  busy: boolean
  // Every picked file came with a handle the browser can write through.
  canWrite: boolean
  trouble: string[]
  unavailable: SourceName[]
  onDownload: () => void
  onWrite: () => void
  onReset: () => void
  onStop: () => void
}) {
  const some = counts.allWrites ? '' : ' selected'
  const idle = done && !busy && counts.picked > 0
  return (
    <section className="mt-8 grid gap-3 border-t border-[var(--bp-line-strong)] pt-6 md:flex md:flex-wrap md:items-center">
      <button
        className="bp-button w-full md:w-auto"
        data-primary="true"
        disabled={!idle}
        onClick={onDownload}
      >
        {busy ? 'Working' : `Download${some}`}
      </button>
      {canWriteInPlace && (
        <button
          className="bp-button w-full md:w-auto"
          disabled={!idle || !canWrite}
          title={canWrite ? undefined : 'Choose or drop a folder to write back into it.'}
          onClick={onWrite}
        >
          Write{some} into the folder
        </button>
      )}
      {done ? (
        <button className="bp-button w-full md:ml-auto md:w-auto" onClick={onReset}>
          Start over
        </button>
      ) : (
        <button className="bp-button w-full md:ml-auto md:w-auto" onClick={onStop}>
          Stop
        </button>
      )}
      {trouble.length > 0 && (
        <p className="bp-mono w-full text-xs text-[var(--bp-cyan)]" role="status">
          Not placed: {trouble.join('; ')}
        </p>
      )}
      {unavailable.length > 0 && (
        <p className="bp-mono w-full text-xs text-[var(--bp-cyan)]" role="status">
          {unavailable.map((s) => SOURCE_LABEL[s]).join(' and ')} could not be reached and{' '}
          {unavailable.length === 1 ? 'was' : 'were'} left out for the rest of the run.
        </p>
      )}
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
  outcome,
  busy,
  onDownload,
  onClose,
}: {
  book: BookResult | null
  morph: boolean
  outcome: Outcome | undefined
  // A repair is already running from the actions bar; one at a time.
  busy: boolean
  onDownload: () => void
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
        showCloseButton={false}
        className="max-h-[90vh] max-w-2xl overflow-y-auto border-[var(--bp-line-strong)] bg-[var(--bp-deep)] p-0 text-[var(--bp-ink)] sm:max-w-2xl"
      >
        {book && (
          <div className="p-6 md:p-8">
            <DialogClose className="bp-mono bp-link absolute top-5 right-5 text-xs text-[var(--bp-muted)] md:top-7 md:right-7">
              [ close ]
            </DialogClose>
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
                {Object.keys(p.gains).length > 0 && (
                  <p className="bp-mono mt-3 text-xs text-[var(--bp-muted)]">
                    {book.files.length === 2
                      ? 'Written to both the EPUB and the PDF.'
                      : `Written to the ${book.files[0].slice(1).toUpperCase()}, the only file for this book.`}
                  </p>
                )}
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
                {willWrite(book) &&
                  (outcome ? (
                    <p className="bp-mono mt-8 inline-flex items-center gap-1 text-xs text-[var(--bp-cyan)]">
                      <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
                      {outcome}
                    </p>
                  ) : (
                    <button
                      className="bp-button mt-8"
                      data-primary="true"
                      disabled={busy}
                      onClick={onDownload}
                    >
                      Download this file
                    </button>
                  ))}
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
          <p className="text-[var(--bp-muted)]">
            The desktop tool also asks Kobo and Google Books, which cannot be reached from a
            browser. See the{' '}
            <a
              className="bp-link underline underline-offset-4"
              href="https://github.com/OffCrazyFreak/eBook-Metamend#readme"
            >
              README
            </a>
            .
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
