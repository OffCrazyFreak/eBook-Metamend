// Getting files in, the same way in every variation. Design owns the look;
// this owns what a drop, a file picker and a folder picker actually yield.

import type { DragEvent } from 'react'

export const BOOK_FILE = /\.(epub|pdf)$/i

// Writing back into the chosen folder needs the File System Access API, which
// Chrome and Edge ship and Firefox and Safari do not. Everyone else gets the
// repaired files as downloads. Detected, never sniffed from the user agent.
export const canWriteInPlace = typeof window !== 'undefined' && 'showDirectoryPicker' in window

export function namesFromFileList(files: FileList | null): string[] {
  if (!files) return []
  return Array.from(files)
    .map((f) => f.webkitRelativePath || f.name)
    .filter((name) => BOOK_FILE.test(name))
}

// A dropped folder arrives as a directory entry; walk it so the tree survives
// the way it does with the folder picker. Chrome, Firefox and Safari all
// expose webkitGetAsEntry on dropped items.
export async function namesFromDrop(event: DragEvent): Promise<string[]> {
  const items = Array.from(event.dataTransfer.items)
  const entries = items
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => e !== null)
  if (!entries.length) return namesFromFileList(event.dataTransfer.files)
  const names: string[] = []
  for (const entry of entries) await walk(entry, '', names)
  return names.filter((name) => BOOK_FILE.test(name))
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

export function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer.types).includes('Files')
}
