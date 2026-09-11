import { afterEach, describe, expect, it, vi } from 'vitest'

import { groupBooks, intakeFromDrop, sortIntake, type IntakeFile } from '@/intake'

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

describe('intakeFromDrop', () => {
  afterEach(() => vi.unstubAllGlobals())

  // Chrome answers null for a dropped file that has no path behind it; the
  // File is still in the transfer and must not be lost.
  it('keeps a file whose handle is null', async () => {
    vi.stubGlobal('DataTransferItem', { prototype: { getAsFileSystemHandle() {} } })
    const dropped = new File([], 'Author - Title.epub')
    const item = {
      kind: 'file',
      getAsFile: () => dropped,
      getAsFileSystemHandle: () => Promise.resolve(null),
    }
    const event = { dataTransfer: { items: [item], files: [dropped] } }
    const intake = await intakeFromDrop(event as unknown as DragEvent)
    expect(intake.books.map((b) => b.path)).toEqual(['Author - Title.epub'])
    expect(intake.books[0].handle).toBeUndefined()
    expect(intake.folders).toEqual([])
  })
})
