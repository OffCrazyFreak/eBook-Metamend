// Invented books for the design round. None of these exist. Every state the real
// tool can produce appears at least once: HIGH with gains, HIGH with nothing to
// add, MED, LOW, no answer, an unreadable file, a series book, co-authors, a
// PDF-only stem and a long title.

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
  sea: ['Sailing', 'Navigation', 'Voyages', 'Memoir'],
  cities: ['Urban planning', 'Transport policy', 'Housing', 'Public space'],
  mind: ['Attention', 'Habits', 'Cognitive psychology', 'Self-management'],
  fantasy: ['Fantasy fiction', 'Epic', 'Series fiction'],
  bread: ['Bread', 'Baking', 'Fermentation', 'Home cooking'],
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
    stem: 'Tomas Vell - Salt and Latitude - A Small Boat Across the North Sea',
    conf: 'HIGH',
    scores: [
      score('apple', 'Salt and Latitude: A Small Boat Across the North Sea', 0.95, 1.0),
      score('openlib', 'Salt and Latitude', 0.95, 1.0),
    ],
    current: { tags: ['Memoir'] },
    gains: { tags: TAGS.sea, publisher: 'Longshore Books' },
    merged: { publisher: 'Longshore Books' },
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
    stem: 'Ruth Calder and Ben Adeyemi - The Attention Ledger',
    conf: 'HIGH',
    scores: [
      score('apple', 'The Attention Ledger', 1.0, 0.88),
      score('openlib', 'The Attention Ledger', 1.0, 0.88),
    ],
    gains: { tags: TAGS.mind, isbn: '9781940000029' },
    merged: { authors: ['Ruth Calder', 'Ben Adeyemi'], isbn: '9781940000029' },
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
    stem: 'Corin Ashby - The Emberwake Cycle - 02 - Ash Tide',
    conf: 'HIGH',
    scores: [score('apple', 'Ash Tide', 1.0, 1.0), score('inventaire', 'Ash Tide', 1.0, 1.0)],
    gains: { tags: TAGS.fantasy, series: 'The Emberwake Cycle' },
    merged: { series: 'The Emberwake Cycle', sidx: '2' },
  }),
  build({
    stem: 'Corin Ashby - The Emberwake Cycle - 02.5 - A Lantern for the Ferry',
    conf: 'MED',
    scores: [score('apple', 'A Lantern for the Ferry', 1.0, 1.0)],
    gains: { tags: TAGS.fantasy },
  }),
  build({
    stem: 'Hanne Lisker - Crumb - The Long Ferment',
    conf: 'HIGH',
    scores: [
      score('apple', 'Crumb: The Long Ferment', 0.95, 1.0),
      score('openlib', 'Crumb', 0.95, 1.0),
    ],
    current: { title: 'crumb_final_v3' },
    gains: { title: 'Crumb: The Long Ferment', tags: TAGS.bread },
  }),
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
    stem: 'Pieter Kroon - Small Engines, Kept Running',
    conf: 'MED',
    scores: [
      score('apple', 'Small Engines, Kept Running', 1.0, 1.0),
      score('inventaire', 'Small Engines', 0.69, 0.4),
    ],
    gains: { tags: ['Engines', 'Maintenance and repair', 'Small engines'] },
  }),
  build({
    stem: 'Lena Faroe - The Sisters of Gull Rock',
    conf: 'LOW',
    scores: [score('inventaire', 'Gull Rock Lighthouse: A History', 0.42, 0.2)],
    gains: {},
  }),
  build({
    stem: 'Joss Weatherby - Notes Toward a Kinder Spreadsheet',
    conf: 'LOW',
    scores: [score('apple', 'Spreadsheets for Kind People', 0.38, 0.0)],
    gains: {},
  }),
  build({ stem: 'Osei Bright - Unlisted', none: true }),
  build({ stem: 'Tamsin Rook - Winter Studio Journal 2019', files: ['.pdf'], none: true }),
  build({
    stem: 'Anneli Dorn - Fieldwork on the Ice Shelf',
    files: ['.pdf'],
    conf: 'HIGH',
    scores: [
      score('apple', 'Fieldwork on the Ice Shelf', 1.0, 1.0),
      score('openlib', 'Fieldwork on the Ice Shelf', 1.0, 1.0),
    ],
    gains: { tags: ['Antarctica', 'Glaciology', 'Field research'], publisher: 'Polar Row' },
    merged: { publisher: 'Polar Row' },
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
  build({
    stem: 'Greta Moss - What the Orchard Knew About Time - Seasons, Grafting and the Patience of Trees',
    conf: 'HIGH',
    scores: [
      score(
        'apple',
        'What the Orchard Knew About Time: Seasons, Grafting and the Patience of Trees',
        0.95,
        1.0,
      ),
      score('openlib', 'What the Orchard Knew About Time', 0.95, 1.0),
    ],
    gains: { tags: ['Orchards', 'Grafting', 'Horticulture', 'Nature writing'] },
  }),
  build({
    stem: 'Elias Thorne - The Cartographer of Small Hours',
    conf: 'HIGH',
    scores: [
      score('apple', 'The Cartographer of Small Hours', 1.0, 1.0),
      score('inventaire', 'The Cartographer of Small Hours', 1.0, 1.0),
    ],
    gains: {
      tags: ['Fiction', 'Insomnia', 'Maps'],
      description: 'A night watchman maps the city by the sounds it makes between two and four.',
    },
  }),
  build({
    stem: 'Noor Haddad - Concrete Poems for Bridge Engineers',
    conf: 'MED',
    scores: [score('openlib', 'Concrete Poems for Bridge Engineers', 1.0, 1.0)],
    gains: { tags: ['Poetry', 'Engineering'] },
  }),
  build({
    stem: 'Bram Ulvik - The Herring Years',
    conf: 'HIGH',
    scores: [
      score('apple', 'The Herring Years', 1.0, 1.0),
      score('openlib', 'The Herring Years', 1.0, 1.0),
      score('inventaire', 'The Herring Years', 1.0, 1.0),
    ],
    current: { description: 'Short.', tags: ['Fishing'] },
    gains: {
      description:
        'Forty seasons on the Lofoten boats, told by the last skipper to work under sail.',
      tags: ['Fishing', 'Norway', 'Maritime history', 'Memoir'],
    },
  }),
  build({
    stem: 'Sable Quint - The Lockpick Cookbook',
    conf: 'LOW',
    scores: [score('apple', 'Cooking Under Lock and Key', 0.3, 0.0)],
    gains: {},
  }),
  build({
    stem: 'Femi Adebayo - Ten Thousand Ordinary Mornings',
    conf: 'HIGH',
    scores: [
      score('apple', 'Ten Thousand Ordinary Mornings', 1.0, 1.0),
      score('openlib', 'Ten Thousand Ordinary Mornings', 1.0, 1.0),
    ],
    gains: { tags: TAGS.mind, publisher: 'Larkspur' },
    merged: { publisher: 'Larkspur' },
  }),
  build({
    stem: 'Ivo Brandt - Manual for a Dying Language',
    conf: 'MED',
    scores: [
      score('inventaire', 'Manual for a Dying Language', 1.0, 1.0),
      score('apple', 'A Dying Language: Field Manual', 0.62, 1.0),
    ],
    gains: { tags: ['Linguistics', 'Endangered languages'] },
  }),
  build({ stem: 'Wren Castellan - Draft Seven', files: ['.epub'], none: true }),
]
