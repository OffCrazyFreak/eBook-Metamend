import { useMemo, useRef, useState, type DragEvent } from 'react'
import { useReducedMotion } from 'motion/react'

import icon from '../../../assets/brand/icon/icon-square-512.png'
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

const BG: Record<Verdict, string> = {
  HIGH: 'var(--fd-high)',
  MED: 'var(--fd-med)',
  LOW: 'var(--fd-low)',
  NONE: 'var(--fd-grey)',
  UNREADABLE: 'var(--fd-low)',
}
const LABEL: Record<Verdict, string> = {
  HIGH: 'HIGH',
  MED: 'MED',
  LOW: 'LOW',
  NONE: 'NONE',
  UNREADABLE: 'UNREAD',
}

const MARQUEE = [
  'Apple Books',
  'Open Library',
  'Inventaire',
  'two must agree',
  'filenames are ground truth',
  'dry run by default',
  'nothing is ever blanked',
]

export function App() {
  const { state, start, reset } = useRun({ perBookMs: 340 })
  const [selected, setSelected] = useState<BookResult | null>(null)
  const [hideNone, setHideNone] = useState(false)

  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: done.filter(willWrite).length,
    }
  }, [state.books])

  const visible = hideNone
    ? state.books.filter((b) => b.status !== 'done' || verdict(b) !== 'NONE')
    : state.books

  return (
    <div className="min-h-screen">
      <div className="fd-marquee" aria-hidden="true">
        <span className="fd-display text-sm">
          {[...MARQUEE, ...MARQUEE].map((t, i) => (
            <span key={i} className="mx-6">
              {t}
              <span className="ml-6 text-[var(--fd-electric)]">■</span>
            </span>
          ))}
        </span>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-24 pt-6 md:px-8">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={icon} alt="" className="h-10 w-10 border-2 border-[var(--fd-ink)]" />
            <span className="fd-display text-xl">eBook-Metamend</span>
          </div>
          <span className="text-sm font-medium text-[var(--fd-grey)]">
            Metadata repair. Runs in your browser.
          </span>
        </header>

        {state.phase === 'idle' && <Intake onStart={start} />}
        {state.phase === 'loading' && <Loading {...state.loading} />}
        {(state.phase === 'running' || state.phase === 'done') && (
          <>
            <Board
              counts={counts}
              running={state.phase === 'running'}
              elapsedMs={state.elapsedMs}
            />
            <label className="mt-8 flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[var(--fd-navy)]"
                checked={hideNone}
                onChange={(e) => setHideNone(e.target.checked)}
              />
              Hide books no catalogue knew
            </label>
            <Grid books={visible} active={state.active} onSelect={setSelected} />
            <Actions writes={counts.writes} done={state.phase === 'done'} onReset={reset} />
          </>
        )}

        <Explainer />
        <footer className="fd-rule mt-24 flex flex-wrap gap-x-8 gap-y-2 pt-4 text-sm font-medium">
          <span>Files stay in this tab. Only three catalogue searches leave it.</span>
          <a
            className="underline underline-offset-4 hover:text-[var(--fd-electric)]"
            href="https://github.com/OffCrazyFreak/eBook-Metamend"
          >
            Source on GitHub
          </a>
          <span>MIT licence</span>
        </footer>
      </div>
      <Detail book={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

function Intake({ onStart }: { onStart: (names: string[]) => void }) {
  const [over, setOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    onStart(await namesFromDrop(event))
  }

  return (
    <section className="fd-rule-thick mt-8 pt-6 md:mt-12">
      <h1 className="fd-display text-[3rem] md:text-[5.5rem]">
        Fix the metadata.
        <br />
        <span className="text-[var(--fd-navy)]">Keep the truth.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg font-medium leading-relaxed md:text-xl">
        Your filenames are the ground truth. Three catalogues are asked about each book. A field is
        written only when two of them identify the same book on their own and agree.
      </p>

      <div className="fd-block mt-10 bg-white">
        <div
          role="region"
          aria-label="Drop EPUB or PDF files or a folder here"
          className="fd-hatch flex min-h-[240px] flex-col justify-between gap-6 p-6 md:flex-row md:items-end md:p-8"
          data-over={over}
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
            <p className="fd-display bg-[var(--fd-bone)] px-2 py-1 text-2xl md:text-3xl">
              {over ? 'RELEASE TO START THE DRY RUN' : 'DROP FILES OR A FOLDER'}
            </p>
            <p className="mt-3 max-w-md bg-[var(--fd-bone)] px-2 py-1 text-sm font-medium">
              EPUB and PDF. Nothing leaves this browser tab.{' '}
              {canWriteInPlace
                ? 'Repairs can be written straight back into the folder.'
                : 'This browser cannot write into a folder, so repaired files come back as downloads.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-4">
            <button className="fd-button" onClick={() => fileInput.current?.click()}>
              Choose files
            </button>
            <button className="fd-button" onClick={() => folderInput.current?.click()}>
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
        </div>
      </div>
      <p className="mt-6 text-sm font-medium">
        No files to hand?{' '}
        <button
          className="underline decoration-2 underline-offset-4 hover:text-[var(--fd-electric)]"
          onClick={() => onStart([])}
        >
          Play the invented sample.
        </button>
      </p>
    </section>
  )
}

function Loading({ progress, label }: { progress: number; label: string }) {
  const on = Math.round(progress * 20)
  return (
    <section className="fd-rule-thick mt-12 pt-6" aria-live="polite">
      <p className="fd-display text-3xl md:text-5xl">LOADING PYTHON</p>
      <div className="fd-segments mt-6">
        {Array.from({ length: 20 }, (_, i) => (
          <span key={i} data-on={i < on} />
        ))}
      </div>
      <p className="mt-4 font-medium">
        {label}. {Math.round(progress * 100)}% of about 6 MB, once. Cached after that.
      </p>
    </section>
  )
}

function Board({
  counts,
  running,
  elapsedMs,
}: {
  counts: { done: number; total: number; high: number; writes: number }
  running: boolean
  elapsedMs: number
}) {
  return (
    <section className="fd-rule-thick mt-8 grid pt-4 md:grid-cols-3 md:gap-0" aria-live="polite">
      {[
        { n: counts.done, of: counts.total, label: 'CHECKED', bg: 'var(--fd-navy)' },
        { n: counts.high, label: 'HIGH CONFIDENCE', bg: 'var(--fd-high)' },
        {
          n: counts.writes,
          label: running ? 'WOULD WRITE' : `WOULD WRITE · ${(elapsedMs / 1000).toFixed(1)} S`,
          bg: 'var(--fd-electric)',
        },
      ].map((item, i) => (
        <div
          key={item.label}
          className={`border-2 border-[var(--fd-ink)] p-4 text-white md:border-l-0 ${i === 0 ? 'md:border-l-2' : ''} ${running && i === 0 ? 'fd-flash' : ''}`}
          style={{ background: item.bg }}
        >
          <p className="fd-display text-5xl md:text-7xl">
            {item.n}
            {'of' in item && <span className="text-2xl opacity-70"> / {item.of}</span>}
          </p>
          <p className="mt-1 text-xs font-bold tracking-wide">{item.label}</p>
        </div>
      ))}
    </section>
  )
}

function Grid({
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
    <div className="fd-block mt-4 bg-white">
      <div className="fd-tr bg-[var(--fd-bone)] text-xs font-bold tracking-wide">
        <span className="fd-cell">#</span>
        <span className="fd-cell">FILE</span>
        <span className="fd-cell hidden md:block">SOURCES</span>
        <span className="fd-cell hidden md:block">GAINS</span>
        <span className="fd-cell">VERDICT</span>
      </div>
      {books.map((book, i) => {
        const v = verdict(book)
        const done = book.status === 'done'
        return (
          <button
            key={book.stem}
            disabled={!done}
            onClick={() => onSelect(book)}
            className={`fd-tr w-full text-left hover:bg-[var(--fd-bone)] focus-visible:bg-[#e9f1ff] focus-visible:outline-none disabled:cursor-default ${done && !reduced ? 'fd-land' : ''}`}
          >
            <span className="fd-cell text-sm font-bold text-[var(--fd-grey)]">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span className="fd-cell min-w-0">
              <span className="block truncate font-bold">{book.facts.title}</span>
              <span className="block truncate text-sm text-[var(--fd-grey)]">
                {book.facts.author}
                {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`} ·{' '}
                {book.files.map((f) => f.slice(1)).join('+')}
              </span>
            </span>
            <span className="fd-cell hidden truncate text-sm md:block">
              {done && book.proposal
                ? book.proposal.sources.map((s) => SOURCE_LABEL[s]).join(', ')
                : ''}
            </span>
            <span className="fd-cell hidden truncate text-sm md:block">
              {done && book.proposal && !book.proposal.unreadable
                ? Object.keys(book.proposal.gains).join(', ') || 'none'
                : ''}
            </span>
            <span className="fd-cell">
              {done ? (
                <span className="fd-verdict" style={{ background: BG[v] }}>
                  {LABEL[v]}
                </span>
              ) : (
                <span
                  className={`inline-block text-xs font-bold text-[var(--fd-grey)] ${active === book.stem ? 'fd-flash bg-[var(--fd-bone)] px-1' : ''}`}
                >
                  {active === book.stem ? 'ASKING' : 'QUEUED'}
                </span>
              )}
            </span>
          </button>
        )
      })}
    </div>
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
    <section className="mt-10 flex flex-wrap items-center gap-5">
      <button className="fd-button" data-primary="true" disabled={!done || writes === 0}>
        Download {writes} repaired {writes === 1 ? 'file' : 'files'}
      </button>
      {canWriteInPlace && (
        <button className="fd-button" disabled={!done || writes === 0}>
          Write into the folder
        </button>
      )}
      <button className="fd-button ml-auto" onClick={onReset}>
        Start over
      </button>
      <p className="w-full text-sm font-medium">
        Dry run by default. Only HIGH is written, only missing fields are filled, and no existing
        value is ever blanked.
      </p>
    </section>
  )
}

function Detail({ book, onClose }: { book: BookResult | null; onClose: () => void }) {
  const p = book?.proposal ?? null
  const v = book ? verdict(book) : 'NONE'
  return (
    <Dialog open={book !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto rounded-none border-2 border-[var(--fd-ink)] bg-white p-0 shadow-[8px_8px_0_var(--fd-navy)] sm:max-w-2xl">
        {book && (
          <div className="p-6 md:p-8">
            <span className="fd-verdict" style={{ background: BG[v] }}>
              {LABEL[v]}
            </span>
            <DialogTitle className="fd-display mt-3 text-2xl md:text-3xl">
              {book.facts.title}
            </DialogTitle>
            <DialogDescription className="mt-1 font-medium text-[var(--fd-grey)]">
              {book.facts.author}
              {book.facts.series && ` · ${book.facts.series} ${book.facts.series_index}`}
            </DialogDescription>
            {p === null ? (
              <p className="mt-6 font-medium">
                No catalogue answered for this filename. Nothing is proposed.
              </p>
            ) : p.unreadable ? (
              <p className="mt-6 font-medium">
                The file's existing metadata could not be read, so nothing is proposed. A failed
                read is not an empty book.
              </p>
            ) : (
              <>
                <p className="fd-rule mt-6 pt-3 text-xs font-bold tracking-wide">
                  WHAT EACH CATALOGUE SAID
                </p>
                <ul className="mt-2 divide-y-2 divide-[var(--fd-ink)] border-2 border-[var(--fd-ink)] text-sm">
                  {p.scores.map((s) => {
                    const trusted = p.sources.includes(s.name)
                    return (
                      <li key={s.name} className="grid grid-cols-[7rem_1fr_auto] gap-3 px-3 py-2">
                        <span className="font-bold">{SOURCE_LABEL[s.name]}</span>
                        <span
                          className={
                            trusted
                              ? ''
                              : 'text-[var(--fd-grey)] line-through decoration-[var(--fd-low)] decoration-2'
                          }
                        >
                          {s.title}
                        </span>
                        <span className="text-xs font-bold text-[var(--fd-grey)]">
                          {s.title_score.toFixed(2)} / {s.author_score.toFixed(2)}
                        </span>
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-2 text-xs font-medium text-[var(--fd-grey)]">
                  Title and author scores against the filename. Struck through: answered, but did
                  not identify this book on its own, so it may not supply a field.
                </p>
                <p className="fd-rule mt-6 pt-3 text-xs font-bold tracking-wide">
                  {Object.keys(p.gains).length ? 'WOULD BE WRITTEN' : 'NOTHING TO ADD'}
                </p>
                <dl className="mt-2 divide-y-2 divide-[var(--fd-ink)] border-2 border-[var(--fd-ink)] text-sm">
                  {Object.entries(p.gains).map(([field, value]) => (
                    <div key={field} className="grid grid-cols-[7rem_1fr] gap-3 px-3 py-2">
                      <dt className="font-bold capitalize">{field}</dt>
                      <dd>
                        {currentValue(p.current, field) && (
                          <span className="block text-[var(--fd-grey)] line-through decoration-2">
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
        )}
      </DialogContent>
    </Dialog>
  )
}

function currentValue(meta: Metadata, field: string) {
  const value = (meta as unknown as Record<string, unknown>)[field]
  if (Array.isArray(value)) return value.join(', ')
  return value ? String(value) : ''
}

function Explainer() {
  return (
    <section className="fd-rule-thick mt-28 grid gap-8 pt-6 md:grid-cols-[1fr_2fr]">
      <h2 className="fd-display text-4xl md:text-5xl">How it decides</h2>
      <div className="space-y-5 text-lg font-medium leading-relaxed">
        <p>
          The obvious fix for messy ebook metadata is to look each book up online and write back
          whatever comes back. That is also how you destroy a library. Catalogues confidently return
          the wrong book, and a bulk run that trusts them corrupts hundreds of files at once,
          quietly.
        </p>
        <p>
          So the filename is the ground truth. Every answer is scored against the title and the
          author in it. A book reaches{' '}
          <span className="fd-verdict" style={{ background: 'var(--fd-high)' }}>
            HIGH
          </span>{' '}
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
