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
- OceanofPDF, `_OceanofPDF.com_Title_-_Author.ext`, underscores for spaces, a colon left as a double underscore (`Title__Subtitle`), the title cut at about 40 characters, dots dropped from initials, hyphens inside words kept (`Domain-Driven`) (three independent renaming scripts on GitHub and the files that started this).
- Renaming tools, `Title by Author.ext` (ebook-rename's README).

Title only:

- PDFDrive, `Title ( PDFDrive ).pdf` and `Title ( PDFDrive.com ).pdf`, spaces inside the brackets, `_ ` for `: `, a dash inside is a subtitle and never an author (filenames quoted on GitHub).
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
2. Undoes the site's encoding: underscores or dots for spaces, `_ ` for `: `, `.-.` for ` - `, Anna's Archive's `_` for `.`, Z-Library's double space and OceanofPDF's double underscore for `: `, slugs back into words, Springer's CamelCase into words, `Last, First` into `First Last` (never `Smith, Jr.`, never `Mara Voss, Ann Person`).
3. Recognises the order when the scheme fixes it. A plain `A - B` is read author first, as the README asks, unless B reads more like a person than A (two or three capitalised words, an initial, no digits, no colon). When the name could be read either way and the other half could be a person at all, the other reading travels along as `FilenameFacts.alternate`.
4. Series shapes from other tools are read too: `[Series #2]` as its own segment and `Title (Series Book 2)`.
5. A name that carries no title (`pg1342`, an ISBN) is reported as such, in the CLI line and on the page, instead of "no source answered".

`FilenameFacts.scheme` names what was recognised, so the CLI prints `read as Author / Title (scheme name)` and the page can say the same.

## What the pipeline does with the other reading

Only when no source identifies the book as first read does `enrich.propose` ask the catalogues about the alternate reading, and it keeps that reading only if a source then identifies the book. A wrong reading cannot score: a source would have to name a book whose title is the author's name and whose author is the title, and two of them would have to agree. The bar for writing is unchanged; the cost is one extra round of queries for a book that was going to be LOW anyway.

A retry with the head of a long title (asking for `Quiet Orchard` when the name says `Quiet Orchard The Year Of Pruning`) was built, measured and removed. It did rescue a name whose colon had been dropped, because Open Library answers nothing for the glued form. It also manufactured a HIGH for the wrong book: a series name glued to a title (`The Dark Tower The Waste Lands`) drew the volume called `The Dark Tower` out of two sources, and a source title that is a strict prefix of the filename title scores 0.95 under the prefix rule, so volume VII's ISBN and series index were proposed for volume III. Anything that makes the tool more willing to write is a change to the safety model, so the retry is gone; a glued subtitle now stays at whatever the full query earns, usually MED, which is honest. The prefix rule has since been made one-directional: a source that stops short of the filename's main title is capped at the containment score (`matching.title_sim`), measured against the same fixtures with no verdict changing, so the volume-VII case can no longer reach HIGH by any route.

The page paces between books, not inside one, so `web.pause_after` multiplies the wait by the rounds the last book took (`enrich.last_rounds`); Apple's twenty calls a minute hold even when every book is read both ways. In replay mode a fixture set recorded before names had two readings has no key for the second one; that round reports the missing recording and is skipped, while a missing key in the first round stays loud as before.

## Checked against

- The two OceanofPDF pairs that started this, live with the three web sources: one HIGH (Apple and Open Library agreeing), one LOW. The LOW is correct: that file is a publisher's summary edition of a well-known book, its own metadata names the summary publisher as the first author, and the author score of 0.26 against the original is the safety model refusing to dress a summary up as the book it summarises.
- The same book renamed the Anna's Archive way, the Z-Library way and the Calibre way (`Title - Author`): HIGH each time, with the reading printed.
- The pristine ten-book sample replayed against `fixtures-v2` (Kobo, Google, Open Library) and `fixtures-wide-raw` (the web sources): every verdict, source list, gain and figure identical to the code before this change, and no extra query asked.
