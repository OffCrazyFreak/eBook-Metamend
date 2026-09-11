import { describe, expect, it } from 'vitest'

import { groupBooks, sortIntake, type IntakeFile } from '@/intake'

const file = (path: string): IntakeFile => ({ path, file: new File([], path) })

describe('sortIntake', () => {
  it('keeps ebooks and counts the rest', () => {
    const intake = sortIntake([file('a.epub'), file('b.PDF'), file('notes.txt'), file('cover.jpg')])
    expect(intake.books.map((b) => b.path)).toEqual(['a.epub', 'b.PDF'])
    expect(intake.others).toBe(2)
  })
})

describe('groupBooks', () => {
  it('pairs an EPUB with its PDF twin by path', () => {
    const books = groupBooks([file('x/Author - Title.epub'), file('x/Author - Title.pdf')])
    expect(books).toHaveLength(1)
    expect(books[0].stem).toBe('x/Author - Title')
    expect(Object.keys(books[0].files).sort()).toEqual(['.epub', '.pdf'])
  })

  it('keeps the same name in two folders apart', () => {
    const books = groupBooks([file('a/Author - Title.epub'), file('b/Author - Title.epub')])
    expect(books.map((b) => b.stem)).toEqual(['a/Author - Title', 'b/Author - Title'])
  })

  it('lowercases the extension key but not the path', () => {
    const [book] = groupBooks([file('Author - Title.EPUB')])
    expect(book.files['.epub']?.path).toBe('Author - Title.EPUB')
  })
})
