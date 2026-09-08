# ebook-metamend

**Mend the metadata in your ebook library, without letting a metadata source lie to you.** ebook-metamend fills in missing titles, authors, publishers, ISBNs, tags and descriptions across a folder of EPUBs and PDFs, and refuses to write anything a source cannot back up against your own filenames.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB) ![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-2ec50d) ![Calibre](https://img.shields.io/badge/Calibre-CLI-red)

## Description

If you keep books as files on disk rather than in a Calibre database, their embedded metadata is usually a mess: missing tags, missing descriptions, titles that are really filenames, authors that are really publishers. The obvious fix is to look each book up online and write back whatever comes back. The problem is that book metadata sources will confidently return the *wrong book*, and a bulk run that trusts them will quietly corrupt a library you cannot easily rebuild.

ebook-metamend starts from a different assumption: **your filenames are the ground truth.** Three sources are queried per book, every answer is scored against the filename and its author, and only answers that clear a confidence threshold are written. Dry run is the default, nothing is ever blanked, and every run leaves a JSON record of what it decided and why.

## Features

- Three metadata sources per book (Kobo, Google Books, Open Library) with per-source scoring
- Filename-anchored confidence model that rejects plausible-but-wrong matches
- Title similarity that understands subtitles and refuses omnibus false positives
- Additive only: a field is written when it is missing or when the incoming value is strictly better
- Dry run by default, `--apply` to write, `--match` to work on a single book
- Full proposal record written every run, whether or not anything was applied
- Copies richer EPUB metadata onto its PDF twin, offline
- Dumps embedded metadata and opening text per book, for auditing what a library actually contains
- No third-party Python packages

## How it works

Books are expected to be named `Author - Title - Subtitle.epub`, optionally with a `.pdf` twin of the same name, inside category folders:

```
~/eBooks/
├── Science & Technology/
│   ├── Donald A. Norman - The Design Of Everyday Things.epub
│   └── Donald A. Norman - The Design Of Everyday Things.pdf
└── Fiction & Novels/
    └── Paulo Coelho - The Alchemist.epub
```

Each source's answer is scored, and a confidence level decides what happens:

| Level | Condition | Applied? |
| ----- | --------- | -------- |
| HIGH | a source's title matches the filename (>=0.85) **and** its author matches (>=0.7) | yes |
| MED | weaker evidence, including two sources merely agreeing with each other | only with `--include-low` |
| LOW | anything else | no |

Two sources agreeing with each other is deliberately **not** enough. They can be wrong together, and one of them invents matches when it has none.

### Title matching

Naive string similarity fails on real book titles, so two cases are handled specially:

- **Prefix containment is legitimate.** "Digital Minimalism" vs "Digital Minimalism: Choosing a Focused Life in a Noisy World" is the same book, main title plus subtitle. Scored 0.95.
- **Non-prefix containment is suspicious.** An omnibus titled "The Happiest Baby on the Block and The Happiest Toddler on the Block" contains the title of a book it is not. Capped at 0.70, deliberately below the threshold that would let it be written.

### What the sources are actually like

Measured across a few hundred books:

| Source | Behaviour |
| ------ | --------- |
| Kobo | Best coverage, but silently invents matches. Never trust it alone |
| Google Books | Misses more, fails loudly. Reliable when it answers |
| Open Library | Same, thinner catalogue |
| Goodreads | Blocks after a single request |
| Amazon | Returns SEO spam |

This is the reason for the whole design. A source that returns a plausible wrong answer is far more dangerous than one that returns nothing.

## Tech stack

- **Language:** Python 3.10+, standard library only (`urllib`, `xml.etree`, `difflib`, `argparse`, `subprocess`, `zipfile`)
- **Metadata I/O:** [Calibre](https://calibre-ebook.com/) command line tools (`ebook-meta`, `fetch-ebook-metadata`), used as external processes
- **Sources:** Kobo and Google Books via Calibre plugins, Open Library via its public search API

Calibre is used rather than a native Python library because it edits EPUB and PDF metadata **in place**. Libraries that rebuild the EPUB archive can drop the `mimetype` entry, reorder the manifest or lose XML namespaces.

## How to run

```bash
export EBOOK_LIBRARY=~/eBooks           # defaults to ~/eBooks

python3 2_online_enrich.py                                   # preview the whole library
python3 2_online_enrich.py --match "Digital Minimalism"      # preview one book
python3 2_online_enrich.py --match "Digital Minimalism" --apply
```

Options: `--apply`, `--match`, `--limit`, `--start`, `--out`, `--include-low`.

### Prerequisites

- Python 3.10+
- Calibre, available as command line tools. No system install needed:

```bash
mkdir -p /tmp/cal
curl -fL -o /tmp/calibre.txz https://calibre-ebook.com/dist/linux64
tar xJf /tmp/calibre.txz -C /tmp/cal
```

On some systems Calibre 9.x needs two environment variables or its binaries fail:

```bash
export LD_LIBRARY_PATH=/tmp/cal/lib                 # else: libcalibre-launcher.so not found
export OPENSSL_MODULES=/tmp/cal/lib/ossl-modules    # else: PDF output crashes in PoDoFo
```

The scripts set both internally. Set `CAL_ROOT` if you unpack Calibre somewhere other than `/tmp/cal`.

### The other scripts

| Script | Purpose |
| ------ | ------- |
| `2_online_enrich.py` | The main tool. Queries the three sources, scores, proposes, optionally applies |
| `1_epub_to_pdf.py` | Copies richer EPUB metadata onto its PDF twin. Local only, no network |
| `extract.py` | Dumps filename, embedded metadata and opening text per book to `spotcheck/` |

## Notes on watermarked files

Some ebook sources inject a promotional `<div>` linking back to themselves before `</body>` in every XHTML file, plus a stray marker file at the archive root. Stripping it is a plain zip rewrite. The PDF twin usually carries the same text rendered into the page, so regenerate that from the cleaned EPUB rather than trying to edit it:

```bash
ebook-convert cleaned.epub out.pdf --paper-size letter
```

## Status

Working, and used on a real library of a few hundred books. Currently a set of scripts rather than a package; a restructure into a proper `src/` layout is in progress. Known rough edges:

- The confidence classifier is duplicated rather than shared, so it can drift
- Metadata is read by spawning a Calibre subprocess per book, roughly 350x slower than reading the OPF out of the EPUB zip directly
- Fixed sleeps between source queries rather than adaptive backoff
- No test suite yet

## Attribution

**Created by: Jakov Jakovac**

Built on top of [Calibre](https://calibre-ebook.com/) by Kovid Goyal, and the open [Open Library](https://openlibrary.org/) search API.

## License [![MIT][mit-shield]][mit]

[mit]: https://opensource.org/licenses/MIT
[mit-shield]: https://img.shields.io/badge/License-MIT-yellow.svg

This work is licensed under the [MIT License](LICENSE).

Calibre is GPL-3.0 and is invoked as a separate process via its command line interface. Per the [FSF's guidance](https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins), communication at arm's length through command-line arguments and files keeps the two programs separate works, so this project is not a derivative of Calibre.

## How to contribute

Contributions are welcome, whether it's a bug report, a feature idea, a documentation fix or code. See the **[Contributing guide](.github/CONTRIBUTING.md)** for how to report issues and open a pull request.

Please also review the **[Code of Conduct](.github/CODE_OF_CONDUCT.md)**. To report a security vulnerability, follow the **[Security Policy](.github/SECURITY.md)** rather than opening a public issue.
