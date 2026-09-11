// Seven invented books for the design round. None of these exist. Every state
// the real tool can produce appears once: HIGH with gains, HIGH with nothing to
// add, a HIGH series book, MED, LOW, no answer, and an unreadable file.

import type {
  BookResult,
  Confidence,
  Extension,
  FilenameFacts,
  Gains,
  Metadata,
  Proposal,
  SourceName,
  SourceScore,
} from '@/types'

const SERIES = /^(?<series>.+?)\s*-\s*(?<index>\d+(?:\.\d+)?)\s*-\s*(?<title>.+)$/

export function parseStem(stem: string): FilenameFacts {
  const [author, ...rest] = stem.split(' - ')
  let remainder = rest.join(' - ')
  let series: string | null = null
  let index: string | null = null
  const match = SERIES.exec(remainder)
  if (match?.groups) {
    series = match.groups.series.trim()
    index = match.groups.index
    remainder = match.groups.title
  }
  return { author, title: remainder.trim(), series, series_index: index }
}

function meta(partial: Partial<Metadata> = {}): Metadata {
  return {
    title: '',
    authors: [],
    publisher: '',
    description: '',
    tags: [],
    series: null,
    sidx: null,
    isbn: '',
    ...partial,
  }
}

function score(name: SourceName, title: string, t: number, a: number): SourceScore {
  return { name, title, title_score: t, author_score: a }
}

interface Spec {
  stem: string
  files?: Extension[]
  conf?: Confidence
  current?: Partial<Metadata>
  scores?: SourceScore[]
  gains?: Gains
  merged?: Partial<Metadata>
  unreadable?: boolean
  none?: boolean
}

function build(spec: Spec): BookResult {
  const files = spec.files ?? ['.epub', '.pdf']
  const facts = parseStem(spec.stem)
  if (spec.none) {
    return { stem: spec.stem, files, facts, status: 'pending', proposal: null }
  }
  const scores = spec.scores ?? []
  const trusted = scores.filter((s) => s.title_score >= 0.85 && s.author_score >= 0.7)
  const sources = (trusted.length ? trusted : scores).map((s) => s.name)
  const best = scores.reduce<SourceScore | null>(
    (acc, s) => (acc === null || s.title_score > acc.title_score ? s : acc),
    null,
  )
  const proposal: Proposal = {
    stem: spec.stem,
    files: Object.fromEntries(files.map((ext) => [ext, `/library/${spec.stem}${ext}`])),
    conf: spec.conf ?? 'LOW',
    sources,
    gains: spec.gains ?? {},
    merged: meta({ title: best?.title ?? facts.title, authors: [facts.author], ...spec.merged }),
    fn_score: best?.title_score ?? 0,
    au_score: best?.author_score ?? 0,
    src_titles: Object.fromEntries(scores.map((s) => [s.name, s.title])),
    scores,
    current: meta({ title: facts.title, authors: [facts.author], ...spec.current }),
    unreadable: spec.unreadable ?? false,
  }
  return { stem: spec.stem, files, facts, status: 'pending', proposal }
}

const TAGS = {
  craft: ['Woodworking', 'Hand tools', 'Furniture making', 'Workshop practice'],
  cities: ['Urban planning', 'Transport policy', 'Housing', 'Public space'],
  fantasy: ['Fantasy fiction', 'Epic', 'Series fiction'],
}

export const MOCK_BOOKS: BookResult[] = [
  build({
    stem: 'Ilse Marrow - The Quiet Lathe',
    conf: 'HIGH',
    scores: [
      score('apple', 'The Quiet Lathe', 1.0, 1.0),
      score('openlib', 'The Quiet Lathe', 1.0, 1.0),
      score('inventaire', 'The Quiet Lathe', 1.0, 0.92),
    ],
    gains: {
      tags: TAGS.craft,
      description:
        'A year at the bench with a treadle lathe, and what patience does to a maker who thought she was in a hurry.',
      publisher: 'Hollow Beech Press',
      isbn: '9781940000012',
    },
    merged: { publisher: 'Hollow Beech Press', isbn: '9781940000012' },
  }),
  build({
    stem: 'Ada Okonkwo - Streets That Remember',
    conf: 'HIGH',
    scores: [
      score('apple', 'Streets That Remember', 1.0, 1.0),
      score('inventaire', 'Streets That Remember', 1.0, 1.0),
      score('openlib', 'Streets That Remember: Cities and Their Ghosts', 0.95, 1.0),
    ],
    current: {
      description: 'How cities keep the shape of decisions nobody remembers making.',
      tags: TAGS.cities,
      publisher: 'Meridian House',
    },
    gains: {},
  }),
  build({
    stem: 'Lena Faroe - The Sisters of Gull Rock',
    conf: 'LOW',
    scores: [score('inventaire', 'Gull Rock Lighthouse: A History', 0.42, 0.2)],
    gains: {},
  }),
  build({ stem: 'Osei Bright - Unlisted', none: true }),
  build({
    stem: 'Mira Solano - Ninety Days of Rain',
    conf: 'MED',
    scores: [
      score('openlib', 'Ninety Days of Rain', 1.0, 1.0),
      score('apple', 'Ninety Days of Rain (Illustrated Adaptation)', 0.55, 1.0),
    ],
    gains: { tags: ['Fiction', 'Literary fiction'] },
  }),
  build({
    stem: 'Corin Ashby - The Emberwake Cycle - 01 - The Last Kiln',
    conf: 'HIGH',
    scores: [
      score('apple', 'The Last Kiln', 1.0, 1.0),
      score('inventaire', 'The Last Kiln (The Emberwake Cycle, #1)', 0.95, 1.0),
    ],
    gains: { tags: TAGS.fantasy, series: 'The Emberwake Cycle' },
    merged: { series: 'The Emberwake Cycle', sidx: '1' },
  }),
  build({
    stem: 'Yusuf Adler - Broken Archive',
    files: ['.epub'],
    unreadable: true,
    scores: [
      score('apple', 'Broken Archive', 1.0, 1.0),
      score('openlib', 'Broken Archive', 1.0, 1.0),
    ],
    conf: 'HIGH',
    gains: {},
  }),
]
