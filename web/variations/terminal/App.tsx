import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

import icon from '../../../assets/brand/icon/icon-circle-128.png'
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
  HIGH: 'var(--tm-high)',
  MED: 'var(--tm-med)',
  LOW: 'var(--tm-low)',
  NONE: 'var(--tm-dim)',
  UNREADABLE: 'var(--tm-low)',
}
const LABEL: Record<Verdict, string> = {
  HIGH: 'HIGH',
  MED: 'MED',
  LOW: 'LOW',
  NONE: 'NONE',
  UNREADABLE: 'UNREAD',
}

export function App() {
  const { state, start, reset } = useRun({ perBookMs: 380 })
  const [openStem, setOpenStem] = useState<string | null>(null)
  const [onlyWrites, setOnlyWrites] = useState(false)

  const counts = useMemo(() => {
    const done = state.books.filter((b) => b.status === 'done')
    return {
      done: done.length,
      total: state.books.length,
      high: done.filter((b) => verdict(b) === 'HIGH').length,
      writes: done.filter(willWrite).length,
    }
  }, [state.books])

  const visible = onlyWrites ? state.books.filter(willWrite) : state.books

  return (
    <div className="tm-screen">
      <div className="mx-auto max-w-5xl px-4 pb-24 pt-6 md:px-8">
        <header className="flex items-center gap-3 border-b border-[var(--tm-rule)] pb-4">
          <img src={icon} alt="" className="h-8 w-8" />
          <span className="tm-display text-sm font-semibold">ebook-metamend</span>
          <span className="text-xs text-[var(--tm-dim)]">v1.1.0 · browser build · session log</span>
        </header>

        {state.phase === 'idle' && <Intake onStart={start} />}
        {state.phase === 'loading' && <Loading {...state.loading} />}
        {(state.phase === 'running' || state.phase === 'done') && (
          <>
            <Status
              counts={counts}
              running={state.phase === 'running'}
              elapsedMs={state.elapsedMs}
            />
            <div className="mt-6 flex items-center gap-4 text-xs text-[var(--tm-dim)]">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  className="accent-[var(--tm-cyan)]"
                  checked={onlyWrites}
                  onChange={(e) => setOnlyWrites(e.target.checked)}
                />
                --only-writes
              </label>
              <span>click a line to expand it</span>
            </div>
            <Log
              books={visible}
              active={state.active}
              openStem={openStem}
              onToggle={(stem) => setOpenStem((cur) => (cur === stem ? null : stem))}
            />
            <Actions writes={counts.writes} done={state.phase === 'done'} onReset={reset} />
          </>
        )}

        <Explainer />
        <footer className="mt-20 flex flex-wrap gap-x-6 gap-y-1 border-t border-[var(--tm-rule)] pt-4 text-xs text-[var(--tm-dim)]">
          <span># files stay in this tab; only three catalogue searches leave it</span>
          <a
            className="hover:text-[var(--tm-cyan)]"
            href="https://github.com/OffCrazyFreak/eBook-Metamend"
          >
            # source on github
          </a>
          <span># mit licence</span>
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
  const lines = [
    'filenames are the ground truth',
    'three catalogues are asked about every book',
    'a field is written only when two of them agree, on their own',
    'nothing is written until you say so',
  ]

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    onStart(await namesFromDrop(event))
  }

  return (
    <section className="mt-12 md:mt-16">
      <motion.h1
        className="tm-display text-3xl leading-tight font-semibold md:text-5xl"
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        Repair ebook metadata.
        <br />
        Trust no single catalogue.
      </motion.h1>
      <ol className="mt-6 space-y-1 text-sm text-[var(--tm-dim)] md:text-base">
        {lines.map((line, i) => (
          <motion.li
            key={line}
            className="tm-prompt"
            initial={reduced ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2, delay: 0.3 + i * 0.22 }}
          >
            {line}
          </motion.li>
        ))}
      </ol>

      <motion.div
        role="region"
        aria-label="Drop EPUB or PDF files or a folder here"
        className="tm-drop mt-10 border border-dashed border-[var(--tm-rule)] bg-[rgba(0,26,70,0.35)] p-6 md:p-8"
        data-over={over}
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 1.2 }}
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
        <p className="tm-display text-lg md:text-xl">
          <span className="tm-prompt" />
          {over
            ? 'release to start the dry run'
            : 'ebook-metamend --dry-run <drop files or a folder>'}
          <span className="tm-cursor" aria-hidden="true" />
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button className="tm-button" onClick={() => fileInput.current?.click()}>
            choose files
          </button>
          <button className="tm-button" onClick={() => folderInput.current?.click()}>
            choose a folder
          </button>
          <button className="tm-button" onClick={() => onStart([])}>
            play the sample
          </button>
        </div>
        <p className="mt-5 text-xs leading-relaxed text-[var(--tm-dim)]">
          # epub and pdf. nothing leaves this tab.{' '}
          {canWriteInPlace
            ? 'repairs can be written straight back into the folder.'
            : 'this browser cannot write into a folder, so repaired files come back as downloads.'}
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
      </motion.div>
    </section>
  )
}

function Loading({ progress, label }: { progress: number; label: string }) {
  const width = 32
  const filled = Math.round(progress * width)
  return (
    <section className="mt-14 text-sm md:text-base" aria-live="polite">
      <p className="tm-prompt">loading python runtime</p>
      <p className="mt-2 whitespace-pre text-[var(--tm-cyan)]">
        [{'#'.repeat(filled)}
        {'.'.repeat(width - filled)}] {String(Math.round(progress * 100)).padStart(3)}%
      </p>
      <p className="mt-2 text-[var(--tm-dim)]">
        {label.toLowerCase()}
        <span className="tm-cursor" aria-hidden="true" />
      </p>
      <p className="mt-4 text-xs text-[var(--tm-dim)]">
        # about 6 MB, once. cached by the browser after that.
      </p>
    </section>
  )
}

function Status({
  counts,
  running,
  elapsedMs,
}: {
  counts: { done: number; total: number; high: number; writes: number }
  running: boolean
  elapsedMs: number
}) {
  return (
    <section className="mt-10" aria-live="polite">
      <p className="tm-prompt text-sm text-[var(--tm-dim)]">ebook-metamend --dry-run</p>
      <p className="tm-display mt-2 text-2xl md:text-3xl">
        {counts.done}/{counts.total} checked
        <span className="ml-4 text-[var(--tm-high)]">{counts.high} HIGH</span>
        <span className="ml-4 text-[var(--tm-text)]">{counts.writes} would write</span>
        {running ? (
          <span className="tm-cursor" aria-hidden="true" />
        ) : (
          <span className="ml-4 text-base text-[var(--tm-dim)]">
            done in {(elapsedMs / 1000).toFixed(1)}s
          </span>
        )}
      </p>
    </section>
  )
}

function Log({
  books,
  active,
  openStem,
  onToggle,
}: {
  books: BookResult[]
  active: string | null
  openStem: string | null
  onToggle: (stem: string) => void
}) {
  const reduced = useReducedMotion()
  const end = useRef<HTMLDivElement>(null)
  const doneCount = books.filter((b) => b.status === 'done').length
  // Follow the log like a terminal does, unless the visitor has opened a line.
  useEffect(() => {
    if (openStem === null && !reduced)
      end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [doneCount, openStem, reduced])

  return (
    <div className="mt-4 text-sm">
      <div className="tm-line text-xs text-[var(--tm-dim)]">
        <span>time</span>
        <span>file</span>
        <span className="hidden md:block">sources</span>
        <span className="text-right">verdict</span>
      </div>
      <AnimatePresence initial={false}>
        {books.map((book, i) => {
          const v = verdict(book)
          const done = book.status === 'done'
          const open = openStem === book.stem
          return (
            <motion.div
              key={book.stem}
              layout={!reduced}
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.15 }}
            >
              <button
                disabled={!done}
                aria-expanded={open}
                onClick={() => onToggle(book.stem)}
                className="tm-line w-full text-left hover:bg-[rgba(0,26,70,0.5)] focus-visible:bg-[rgba(0,26,70,0.7)] focus-visible:outline-none disabled:cursor-default"
              >
                <span className="text-xs text-[var(--tm-dim)]">{stamp(i)}</span>
                <span className={`min-w-0 truncate ${done && !reduced ? 'tm-typed' : ''}`}>
                  {book.stem}
                  <span className="text-[var(--tm-dim)]">{book.files.join('')}</span>
                </span>
                <span className="hidden truncate text-xs text-[var(--tm-dim)] md:block">
                  {done && book.proposal ? book.proposal.sources.join(',') || '-' : ''}
                </span>
                <span className="text-right">
                  {done ? (
                    <span className="tm-verdict" style={{ color: COLOR[v] }}>
                      [{LABEL[v]}]
                    </span>
                  ) : (
                    <span
                      className={`text-xs text-[var(--tm-dim)] ${active === book.stem ? 'tm-cursor' : ''}`}
                    >
                      {active === book.stem ? 'asking' : 'queued'}
                    </span>
                  )}
                </span>
              </button>
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div
                    initial={reduced ? false : { height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={reduced ? undefined : { height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <Detail book={book} />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )
        })}
      </AnimatePresence>
      <div ref={end} />
    </div>
  )
}

function stamp(i: number) {
  const s = i * 3
  return `00:${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function Detail({ book }: { book: BookResult }) {
  const p = book.proposal
  return (
    <div className="tm-panel my-2 px-4 py-4 text-xs leading-6 md:px-6 md:text-sm">
      <p className="text-[var(--tm-dim)]">
        filename says: <span className="text-[var(--tm-text)]">{book.facts.title}</span> by{' '}
        <span className="text-[var(--tm-text)]">{book.facts.author}</span>
        {book.facts.series && (
          <>
            , series{' '}
            <span className="text-[var(--tm-text)]">
              {book.facts.series} #{book.facts.series_index}
            </span>
          </>
        )}
      </p>
      {p === null ? (
        <p className="mt-3 text-[var(--tm-dim)]"># no catalogue answered. nothing proposed.</p>
      ) : p.unreadable ? (
        <p className="mt-3 text-[var(--tm-dim)]">
          # existing metadata could not be read, so nothing is proposed. a failed read is not an
          empty book.
        </p>
      ) : (
        <>
          <p className="mt-3 text-[var(--tm-dim)]">
            # title {p.fn_score.toFixed(2)} author {p.au_score.toFixed(2)} against the filename
          </p>
          <table className="mt-2 w-full">
            <tbody>
              {p.scores.map((s) => {
                const trusted = p.sources.includes(s.name)
                return (
                  <tr key={s.name} className={trusted ? '' : 'text-[var(--tm-dim)]'}>
                    <td className="w-28 pr-3 align-top">{SOURCE_LABEL[s.name]}</td>
                    <td
                      className={`pr-3 ${trusted ? '' : 'line-through decoration-[var(--tm-low)]'}`}
                    >
                      {s.title}
                    </td>
                    <td className="w-24 text-right whitespace-nowrap text-[var(--tm-dim)]">
                      {s.title_score.toFixed(2)} {s.author_score.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-3 text-[var(--tm-dim)]">
            {Object.keys(p.gains).length ? '# would write' : '# nothing to add'}
          </p>
          {Object.entries(p.gains).map(([field, value]) => (
            <p key={field}>
              <span className="text-[var(--tm-cyan)]">{field.padEnd(12, ' ')}</span>
              {currentValue(p.current, field) && (
                <span className="text-[var(--tm-low)]">- {currentValue(p.current, field)} </span>
              )}
              <span className="text-[var(--tm-high)]">
                + {Array.isArray(value) ? value.join(', ') : String(value)}
              </span>
            </p>
          ))}
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
    <section className="mt-8 flex flex-wrap items-center gap-3 border-t border-[var(--tm-rule)] pt-5">
      <button className="tm-button" data-primary="true" disabled={!done || writes === 0}>
        download {writes} repaired
      </button>
      {canWriteInPlace && (
        <button className="tm-button" disabled={!done || writes === 0}>
          --apply into folder
        </button>
      )}
      <button className="tm-button ml-auto" onClick={onReset}>
        clear
      </button>
      <p className="w-full text-xs text-[var(--tm-dim)]">
        # dry run by default. only HIGH is written, only missing fields are filled, nothing is ever
        blanked.
      </p>
    </section>
  )
}

function Explainer() {
  return (
    <section className="mt-24 max-w-3xl">
      <p className="tm-prompt text-sm text-[var(--tm-dim)]">man ebook-metamend</p>
      <div className="mt-4 space-y-4 text-sm leading-7 md:text-base md:leading-8">
        <p>
          The obvious fix for messy ebook metadata is to look each book up online and write back
          whatever comes back. That is also how you destroy a library. Catalogues confidently return
          the wrong book, and a bulk run that trusts them corrupts hundreds of files at once,
          quietly.
        </p>
        <p>
          So the filename is the ground truth. Every answer is scored against the title and the
          author in it. A book reaches <span className="text-[var(--tm-high)]">HIGH</span> only when
          two catalogues each identify it on their own and agree with each other, and only those
          catalogues may supply fields. One source is never enough: on a real library a single
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
