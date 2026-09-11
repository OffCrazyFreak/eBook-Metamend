import { describe, expect, it } from 'vitest'

import { applyEvent } from '@/mock/simulate'
import type { BookResult } from '@/types'

const row = (stem: string): BookResult => ({
  stem,
  files: ['.epub'],
  facts: { author: 'A', title: stem, series: null, series_index: null },
  status: 'pending',
  proposal: null,
})

describe('applyEvent', () => {
  it('records answers per book in arrival order', () => {
    let list = [row('one'), row('two')]
    list = applyEvent(list, { type: 'querying', stem: 'one' })
    list = applyEvent(list, { type: 'answer', stem: 'one', source: 'apple' })
    list = applyEvent(list, { type: 'answer', stem: 'one', source: 'openlib' })
    expect(list[0].status).toBe('querying')
    expect(list[0].answered).toEqual(['apple', 'openlib'])
    expect(list[1].answered).toBeUndefined()
  })

  it('replaces a row with its result without reordering', () => {
    const list = applyEvent([row('one'), row('two')], {
      type: 'book',
      result: { ...row('two'), status: 'done' },
    })
    expect(list.map((b) => [b.stem, b.status])).toEqual([
      ['one', 'pending'],
      ['two', 'done'],
    ])
  })
})
