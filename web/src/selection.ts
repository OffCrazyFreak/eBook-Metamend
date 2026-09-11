// Which books go into the download. Every book that would be written starts
// selected, so only the visitor's departures from that are stored: writable
// books they unticked and other books they ticked.

import { verdict, willWrite, type BookResult } from '@/types'

export interface Selection {
  excluded: Set<string>
  included: Set<string>
}

export type Preset = 'all' | 'writes' | 'high' | 'none'

export const PRESET_LABEL: Record<Preset, string> = {
  all: 'all',
  writes: 'would write',
  high: 'HIGH',
  none: 'none',
}

export const DEFAULT_SELECTION: Selection = { excluded: new Set(), included: new Set() }

export function isSelected(sel: Selection, book: BookResult): boolean {
  return willWrite(book) ? !sel.excluded.has(book.stem) : sel.included.has(book.stem)
}

export function toggled(sel: Selection, book: BookResult): Selection {
  const key = willWrite(book) ? 'excluded' : 'included'
  const next = new Set(sel[key])
  if (next.has(book.stem)) next.delete(book.stem)
  else next.add(book.stem)
  return { ...sel, [key]: next }
}

export function preset(name: Preset, books: BookResult[]): Selection {
  const done = books.filter((b) => b.status === 'done')
  const stems = (keep: (b: BookResult) => boolean) => new Set(done.filter(keep).map((b) => b.stem))
  switch (name) {
    case 'all':
      return { excluded: new Set(), included: stems((b) => !willWrite(b)) }
    case 'writes':
      return { excluded: new Set(), included: new Set() }
    case 'high':
      return { excluded: new Set(), included: stems((b) => !willWrite(b) && verdict(b) === 'HIGH') }
    case 'none':
      return { excluded: stems(willWrite), included: new Set() }
  }
}

// The preset the current selection matches exactly, if any, so its button can
// read as pressed.
export function matchingPreset(sel: Selection, books: BookResult[]): Preset | null {
  const done = books.filter((b) => b.status === 'done')
  for (const name of ['writes', 'high', 'all', 'none'] as const) {
    const p = preset(name, books)
    if (done.every((b) => isSelected(sel, b) === isSelected(p, b))) return name
  }
  return null
}
