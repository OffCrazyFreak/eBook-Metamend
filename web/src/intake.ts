// Getting files in, the same way in every variation. Design owns the look;
// this owns what a drop, a file picker and a folder picker actually yield.

import type { DragEvent } from 'react'

export const BOOK_FILE = /\.(epub|pdf)$/i

// Writing back into the chosen folder needs the File System Access API, which
// Chrome and Edge ship and Firefox and Safari do not. Everyone else gets the
// repaired files as downloads. Detected, never sniffed from the user agent.
export const canWriteInPlace = typeof window !== 'undefined' && 'showDirectoryPicker' in window

// What a drop or a picker yielded: the ebook paths, and how many other files
// came along and are left alone.
export interface Intake {
  books: string[]
  others: number
}

export function sortIntake(names: string[]): Intake {
  const books = names.filter((name) => BOOK_FILE.test(name))
  return { books, others: names.length - books.length }
}

export function namesFromFileList(files: FileList | null): Intake {
  if (!files) return { books: [], others: 0 }
  return sortIntake(Array.from(files).map((f) => f.webkitRelativePath || f.name))
}

// A dropped folder arrives as a directory entry; walk it so the tree survives
// the way it does with the folder picker. Chrome, Firefox and Safari all
// expose webkitGetAsEntry on dropped items.
export async function namesFromDrop(event: DragEvent | globalThis.DragEvent): Promise<Intake> {
  const transfer = event.dataTransfer
  if (!transfer) return { books: [], others: 0 }
  const items = Array.from(transfer.items)
  const entries = items
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null)
  if (!entries.length) return namesFromFileList(transfer.files)
  const names: string[] = []
  for (const entry of entries) await walk(entry, '', names)
  return sortIntake(names)
}

async function walk(entry: FileSystemEntry, prefix: string, out: string[]): Promise<void> {
  if (entry.isFile) {
    out.push(prefix + entry.name)
    return
  }
  if (!entry.isDirectory) return
  const reader = (entry as FileSystemDirectoryEntry).createReader()
  // readEntries returns batches; an empty batch means the end.
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
      reader.readEntries(resolve, reject),
    )
    if (!batch.length) break
    for (const child of batch) await walk(child, `${prefix}${entry.name}/`, out)
  }
}

export function hasFiles(event: DragEvent | globalThis.DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}
