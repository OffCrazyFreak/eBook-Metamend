// Getting files in, the same way in every variation. Design owns the look;
// this owns what a drop, a file picker and a folder picker actually yield.

import type { DragEvent } from 'react'

export const BOOK_FILE = /\.(epub|pdf)$/i

// Writing back into the chosen folder needs the File System Access API, which
// Chrome and Edge ship and Firefox and Safari do not. Everyone else gets the
// repaired files as downloads. Detected, never sniffed from the user agent.
export const canWriteInPlace = typeof window !== 'undefined' && 'showDirectoryPicker' in window

// One ebook file as it came in: its path relative to what was chosen, the
// bytes, and a handle when the browser gave one, which is what write-back needs.
export interface IntakeFile {
  path: string
  file: File
  handle?: FileSystemFileHandle
}

// What a drop or a picker yielded: the ebook files, how many other files came
// along and are left alone, and any folder handles to ask write access of.
export interface Intake {
  books: IntakeFile[]
  others: number
  folders: FileSystemDirectoryHandle[]
}

const EMPTY: Intake = { books: [], others: 0, folders: [] }

export function sortIntake(files: IntakeFile[], folders: FileSystemDirectoryHandle[] = []): Intake {
  const books = files.filter((f) => BOOK_FILE.test(f.path))
  return { books, others: files.length - books.length, folders }
}

export function intakeFromFileList(files: FileList | null): Intake {
  if (!files) return EMPTY
  return sortIntake(
    Array.from(files).map((file) => ({ path: file.webkitRelativePath || file.name, file })),
  )
}

// The folder picker on browsers that have it: the handle it returns is what
// lets repairs go back into the same files. Read access only at this point;
// the dry run needs nothing more, and write access is asked for on Write.
export async function intakeFromPicker(): Promise<Intake | null> {
  if (!canWriteInPlace) return null
  try {
    const folder = await window.showDirectoryPicker({ mode: 'read' })
    const files: IntakeFile[] = []
    await walkHandle(folder, `${folder.name}/`, files)
    return sortIntake(files, [folder])
  } catch (error) {
    // Closing the picker is not an error worth a line.
    if (error instanceof DOMException && error.name === 'AbortError') return null
    throw error
  }
}

// A drop yields handles on Chrome and Edge, directory entries everywhere else.
// The handle calls must be made before the first await: the drag data store
// is readable only inside the event.
export async function intakeFromDrop(event: DragEvent | globalThis.DragEvent): Promise<Intake> {
  const transfer = event.dataTransfer
  if (!transfer) return EMPTY
  const items = Array.from(transfer.items).filter((item) => item.kind === 'file')
  if (items.length && 'getAsFileSystemHandle' in DataTransferItem.prototype) {
    const handles = await Promise.all(items.map((item) => item.getAsFileSystemHandle()))
    const files: IntakeFile[] = []
    const folders: FileSystemDirectoryHandle[] = []
    for (const handle of handles) {
      if (!handle) continue
      if (handle.kind === 'directory') {
        const folder = handle as FileSystemDirectoryHandle
        folders.push(folder)
        await walkHandle(folder, `${folder.name}/`, files)
      } else {
        const file = handle as FileSystemFileHandle
        files.push({ path: file.name, file: await file.getFile(), handle: file })
      }
    }
    return sortIntake(files, folders)
  }
  const entries = items
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null)
  if (!entries.length) return intakeFromFileList(transfer.files)
  const files: IntakeFile[] = []
  for (const entry of entries) await walkEntry(entry, '', files)
  return sortIntake(files)
}

async function walkHandle(
  dir: FileSystemDirectoryHandle,
  prefix: string,
  out: IntakeFile[],
): Promise<void> {
  for await (const child of dir.values()) {
    if (child.kind === 'file') {
      out.push({ path: prefix + child.name, file: await child.getFile(), handle: child })
    } else {
      await walkHandle(child, `${prefix}${child.name}/`, out)
    }
  }
}

async function walkEntry(entry: FileSystemEntry, prefix: string, out: IntakeFile[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject),
    )
    out.push({ path: prefix + entry.name, file })
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
    for (const child of batch) await walkEntry(child, `${prefix}${entry.name}/`, out)
  }
}

export function hasFiles(event: DragEvent | globalThis.DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

// Books are keyed by path without extension, so an EPUB and a PDF with the
// same name in the same folder are one book, and the same name in two folders
// is two.
export interface IntakeBook {
  stem: string
  files: Partial<Record<'.epub' | '.pdf', IntakeFile>>
}

export function groupBooks(files: IntakeFile[]): IntakeBook[] {
  const books = new Map<string, IntakeBook>()
  for (const f of files) {
    const match = /^(.*)\.(epub|pdf)$/i.exec(f.path)
    if (!match) continue
    const stem = match[1]
    const ext = `.${match[2].toLowerCase()}` as '.epub' | '.pdf'
    const book = books.get(stem) ?? { stem, files: {} }
    book.files[ext] = f
    books.set(stem, book)
  }
  return [...books.values()]
}
