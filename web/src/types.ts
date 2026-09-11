// Mirrors what the Python side reports. Field names follow Proposal.to_dict()
// in src/ebook_metamend/enrich.py so Phase 2 can pass records through untouched.

export type Confidence = 'HIGH' | 'MED' | 'LOW'

export type SourceName = 'apple' | 'openlib' | 'inventaire'

export const SOURCE_LABEL: Record<SourceName, string> = {
  apple: 'Apple Books',
  openlib: 'Open Library',
  inventaire: 'Inventaire',
}

export type Extension = '.epub' | '.pdf'

export interface Metadata {
  title: string
  authors: string[]
  publisher: string
  description: string
  tags: string[]
  series: string | null
  sidx: string | null
  isbn: string
}

export interface Gains {
  title?: string
  tags?: string[]
  description?: string
  publisher?: string
  isbn?: string
  series?: string
}

export interface SourceScore {
  name: SourceName
  title: string
  title_score: number
  author_score: number
}

export interface Proposal {
  stem: string
  files: Partial<Record<Extension, string>>
  conf: Confidence
  sources: SourceName[]
  gains: Gains
  merged: Metadata
  fn_score: number
  au_score: number
  src_titles: Partial<Record<SourceName, string>>
  // Every source's answer, including the ones that did not earn a say.
  scores: SourceScore[]
  current: Metadata
  unreadable: boolean
}

// What the filename asserts, as library.parse_filename reads it.
export interface FilenameFacts {
  author: string
  title: string
  series: string | null
  series_index: string | null
}

// skipped: the visitor stopped the run before this book was checked.
export type BookStatus = 'pending' | 'querying' | 'done' | 'skipped'

export interface BookResult {
  stem: string
  files: Extension[]
  facts: FilenameFacts
  status: BookStatus
  // Catalogues that have replied so far while the book is being queried.
  answered?: SourceName[]
  // null once done means no source answered.
  proposal: Proposal | null
}

export type RunEvent =
  | { type: 'loading'; progress: number; label: string }
  | { type: 'ready'; books: BookResult[] }
  | { type: 'querying'; stem: string }
  | { type: 'answer'; stem: string; source: SourceName }
  | { type: 'book'; result: BookResult }
  | { type: 'done'; elapsedMs: number }

export function verdict(result: BookResult): Confidence | 'NONE' | 'UNREADABLE' {
  if (result.proposal === null) return 'NONE'
  if (result.proposal.unreadable) return 'UNREADABLE'
  return result.proposal.conf
}

export function willWrite(result: BookResult): boolean {
  const p = result.proposal
  return p !== null && !p.unreadable && p.conf === 'HIGH' && Object.keys(p.gains).length > 0
}
