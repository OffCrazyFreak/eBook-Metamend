# Filenames in the wild

What ebook files are actually called when they arrive from a store, a library manager or a download site, measured on 2026-09-16, and how `library.parse_filename` reads each shape. The filename stays the ground truth; this page is about reading it correctly when another tool wrote it. Nothing here changes what a source must prove before a field is written.

## Why

A file named `_OceanofPDF.com_The_Quiet_Orchard_-_Mara_Voss.epub` has no ` - ` in it, so the old parser read the whole stem as an author with no title, asked nobody, and the page reported "no source answered". That report was false: no source was asked. Renamed to `Author - Title` the same three web sources reached HIGH. The user should not have to rename anything, so the parser now recognises the shapes below.

## The shapes, with their sources

Author first:

- This tool's own convention, `Author - Title` and `Author - Series - 02 - Title` (README).
- Readarr, default `{Author Name} - {Book Title}{ (PartNumber)}` (`NamingConfig.cs` in the Readarr repository).
- Library Genesis mirrors, `Author - Title (2020, Publisher) - libgen.li`, also dotted `Author.-.Title.2020.Publisher.-.libgen.lc.1`, and `_ ` standing for `: ` inside a title (filenames quoted in GitHub issues; a third-party parser documents the `_ ` convention).
- Scene release folders, `Author.Name.-.Title.Of.Book.2021.RETAIL.EPUB.eBook-GROUP` (shelfmark pull request 19).
- IRC sharing channels, `Author - Title [RSC] (retail).epub` (the Shadow Libraries IRC guide).
- ebook-tools output, `Author - [Series #1] - Title (2008) [ISBN].ext` (its README).
- Standard Ebooks, `author-name_title-of-book.epub`, `_advanced.epub`, `.kepub.epub` (checked live on standardebooks.org).

Title first:

- Calibre "Save to disk" and "Send to device", defaults `{author_sort}/{title}/{title} - {authors}` and `{author_sort}/{title} - {authors}`, authors joined by ` & ` (`save_to_disk.py`). Calibre's own guess-from-filename regex assumes the same, `(?P<title>.+) - (?P<author>[^_]+)` (`meta.py`, the manual).
- Calibre-Web downloads, `Title - FirstAuthor.ext` (`cps/helper.py`).
- LazyLibrarian, default `$Title - $Author` (`configdefs.py`).
- Anna's Archive, `Title -- Author -- Edition, Year -- Publisher -- ISBN -- md5 -- Anna’s Archive.ext`, every field at most 60 characters, the whole at most 150, and every `.` in the name turned into `_` so `Mara T. Voss` arrives as `Mara T_ Voss` (`allthethings/page/views.py`). Empty fields are dropped, so the second field is not always the author.
- Z-Library over the years, `Title (Author) (z-lib.org)`, `Title by Author (z-lib.org)`, `Title (Author)` followed by an em dash and `_Publisher_Language_ISBN (Z-Library)`, `Title (Last, First etc.) (z-library.sk, 1lib.sk, z-lib.sk)`. A colon in the title is dropped and leaves two spaces behind, which is how the subtitle boundary is recovered (filenames quoted in GitHub issues).
- OceanofPDF, `_OceanofPDF.com_Title_-_Author.ext`, underscores for spaces, the colon dropped without trace, hyphens inside words kept (`Domain-Driven`) (three independent renaming scripts on GitHub and the files that started this).
- Renaming tools, `Title by Author.ext` (ebook-rename's README).

Title only:

- PDFDrive, `Title ( PDFDrive ).pdf` and `Title ( PDFDrive.com ).pdf`, spaces inside the brackets, `_ ` for `: ` (filenames quoted on GitHub).
- Kindle "Download & transfer via USB", the title alone; Kindle for PC, `ASIN_EBOK.azw` (DeDRM issues).
- FanFicFare, default `${title}-${siteabbrev}_${storyId}` (`defaults.ini`).
- dokumen.pub, vdoc.pub, epdf.pub slugs, `the-title-of-the-book-9780465050659-9780465003945-2013024417`, `-1nbsped-` for "1st ed.", `-4u9bqm2ndpq0` record ids, `epdf-pub-...-pdf` (their page URLs).
- Springer, `2020_Book_IntroductionToScientificProgra.pdf`, CamelCase and cut at 30 characters (a Springer link in free-programming-books).
- Publishers and Humble Bundle, `Title_With_Underscores.pdf` (widely seen, not separately sourced).
- Scribd, `Document Title | PDF | Topic`.

No title at all:

- Project Gutenberg, `pg1342.epub`, `pg1342-images.epub`, `pg1342-images-3.epub` (checked live).
- Internet Archive, `atomichabitseasy0000clea_lcp.epub` (checked live).
- A bare ISBN, `978-1-4842-8853-5.pdf` (Springer's DOI links) or `9780465050659.epub`.

Other observations that shaped the rules: a spaced en dash, a spaced em dash, ` -- ` and ` _ ` all appear as the separator between the same two halves; browsers append ` (1)` to a second download; Kobo files carry `.kepub.epub`; Kavita, by contrast, reads the OPF first and uses the filename only as a fallback, the opposite of this tool's premise.

## What the parser does

1. Strips the site's own marks (`_OceanofPDF.com_`, `(z-lib.org)`, `( PDFDrive )`, `- libgen.li`, `-- Anna’s Archive`, `(retail)`, `(v5.0)`, `(epub)`), a trailing `(Year)` or `(Year, Publisher)`, a bracketed ISBN, a duplicate-download counter and `.kepub`.
2. Undoes the site's encoding: underscores or dots for spaces, `_ ` for `: `, `.-.` for ` - `, Anna's Archive's `_` for `.`, Z-Library's double space for `: `, slugs back into words, Springer's CamelCase into words, `Last, First` into `First Last` (never `Smith, Jr.`).
3. Recognises the order when the scheme fixes it. A plain `A - B` is read author first, as the README asks, unless B reads more like a person than A (two or three capitalised words, an initial, no digits, no colon). When the name could be read either way and the other half could be a person at all, the other reading travels along as `FilenameFacts.alternate`.
4. Series shapes from other tools are read too: `[Series #2]` as its own segment and `Title (Series Book 2)`.
5. A name that carries no title (`pg1342`, an ISBN) is reported as such, in the CLI line and on the page, instead of "no source answered".

`FilenameFacts.scheme` names what was recognised, so the CLI prints `read as Author / Title (scheme name)` and the page can say the same.

## What the pipeline does with the other reading

Only when no source identifies the book as first read does `enrich.propose` ask the catalogues about the alternate reading, and it keeps that reading only if a source then identifies the book. A wrong reading cannot score: a source would have to name a book whose title is the author's name and whose author is the title, and two of them would have to agree. The bar for writing is unchanged; the cost is one extra round of queries for a book that was going to be LOW anyway.

Separately, when a verdict is below HIGH and the title looks like a subtitle glued on without its colon (`Quiet Orchard The Year Of Pruning`), the head of the title (`Quiet Orchard`) is asked once more and each source keeps whichever of its two answers fits the whole filename better. Measured live: Open Library returns nothing for the glued form and finds the book with the head. The cut is made only before a word a subtitle opens with (the, a, an, how, why, what), only when a phrase follows, and never after a preposition or conjunction, because cutting `The Happiest Baby On | The Block And The Happiest Toddler On The Block` drew the single volume out of Open Library, a strict prefix of the omnibus that the prefix rule scores 0.95, and the two-book bundle reached HIGH on its strength. That prefix rule predates this page and still applies to any source that answers with a strict prefix of the filename title; the retry no longer goes looking for one.

## Checked against

- The two OceanofPDF pairs that started this, live with the three web sources: one HIGH (Apple and Open Library agreeing, after the head retry), one LOW. The LOW is correct: that file is a publisher's summary edition of a well-known book, its own metadata names the summary publisher as the first author, and the author score of 0.26 against the original is the safety model refusing to dress a summary up as the book it summarises.
- The same book renamed the Anna's Archive way, the Z-Library way and the Calibre way (`Title - Author`): HIGH each time, with the reading printed.
- The pristine ten-book sample replayed against `fixtures-v2` (Kobo, Google, Open Library) and `fixtures-wide-raw` (the web sources): every verdict, source list, gain and figure identical to the code before this change, and no extra query asked.
