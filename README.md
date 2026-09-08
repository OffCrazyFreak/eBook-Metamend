# eBook Metamend

**Repairs the metadata in an ebook library, without letting a metadata source lie to you.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB) ![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-2ec50d) [![CI](https://github.com/OffCrazyFreak/eBook-Metamend/actions/workflows/ci.yml/badge.svg)](https://github.com/OffCrazyFreak/eBook-Metamend/actions/workflows/ci.yml)

## The problem

If you keep books as files on disk rather than in a Calibre database, their embedded metadata is usually a mess: missing tags and descriptions, titles that are really filenames, authors that are really publishers.

The obvious fix is to look each book up online and write back whatever comes back. That is also how you destroy a library. Book metadata sources confidently return the **wrong book**, and a bulk run that trusts them corrupts hundreds of files at once, quietly, in a way you only notice months later.

## The idea

**Your filenames are the ground truth.** Online sources are witnesses, not authorities.

Three sources are queried per book. Every answer is scored against the filename *and* its author, and only answers that clear a threshold are written:

| Confidence | Condition | Written? |
| ---------- | --------- | -------- |
| **HIGH** | a source's title matches the filename (>=0.85) **and** its author matches (>=0.7) | yes |
| **MED** | weaker evidence, including two sources merely agreeing with each other | only with `--include-low` |
| **LOW** | anything else | no |

Two sources agreeing with each other is deliberately **not** enough. They can be wrong together, and one of them invents matches when it has none.

Dry run is the default. Nothing is ever blanked. Every run leaves a JSON record of what it decided and why.

## Quick start

```bash
export EBOOK_LIBRARY=~/eBooks

python3 2_online_enrich.py                                   # preview the whole library
python3 2_online_enrich.py --match "Digital Minimalism"      # preview one book
python3 2_online_enrich.py --match "Digital Minimalism" --apply
```

Options: `--apply`, `--match`, `--limit`, `--start`, `--out`, `--include-low`.

## Features

- Three metadata sources per book (Kobo, Google Books, Open Library) with per-source scoring
- Filename-anchored confidence model that rejects plausible-but-wrong matches
- Title similarity that understands subtitles and refuses omnibus false positives
- Additive only: a field is written when it is missing, or when the incoming value is strictly better
- Dry run by default, full proposal record written every run
- Copies richer EPUB metadata onto its PDF twin, offline
- Audits a library by dumping embedded metadata and opening text per book
- No third-party Python packages

## Tech stack

- **Language:** Python 3.10+, standard library only (`urllib`, `xml.etree`, `difflib`, `argparse`, `subprocess`, `zipfile`)
- **Metadata I/O:** [Calibre](https://calibre-ebook.com/) command line tools, used as external processes
- **Sources:** Kobo and Google Books via Calibre plugins, Open Library via its public search API
- **Tooling:** ruff, pytest, GitHub Actions

Calibre is used rather than a native Python library because it edits EPUB and PDF metadata **in place**. Libraries that rebuild the EPUB archive can drop the `mimetype` entry, reorder the manifest or lose XML namespaces.

## The scripts

| Script | Purpose |
| ------ | ------- |
| `2_online_enrich.py` | The main tool. Queries three sources, scores, proposes, optionally applies |
| `1_epub_to_pdf.py` | Copies richer EPUB metadata onto its PDF twin. Local only, no network |
| `extract.py` | Dumps filename, embedded metadata and opening text per book to `spotcheck/` |

## How the matching works

Books are expected to be named `Author - Title - Subtitle.epub`, optionally with a `.pdf` twin of the same name, inside category folders:

```
~/eBooks/
├── Science & Technology/
│   ├── Donald A. Norman - The Design Of Everyday Things.epub
│   └── Donald A. Norman - The Design Of Everyday Things.pdf
└── Fiction & Novels/
    └── Paulo Coelho - The Alchemist.epub
```

Naive string similarity fails on real book titles, so two cases are handled specially:

- **Prefix containment is legitimate.** "Digital Minimalism" vs "Digital Minimalism: Choosing a Focused Life in a Noisy World" is the same book, main title plus subtitle. Scored 0.95.
- **Non-prefix containment is suspicious.** An omnibus titled "The Happiest Baby on the Block and The Happiest Toddler on the Block" contains the title of a book it is not. Capped at 0.70, deliberately below the threshold that would let it be written.

Both cases are pinned by the test suite, because they are the difference between a repaired library and a ruined one.

## What the sources are actually like

Measured across a few hundred books:

| Source | Behaviour |
| ------ | --------- |
| Kobo | Best coverage, but silently invents matches. Never trust it alone |
| Google Books | Misses more, fails loudly. Reliable when it answers |
| Open Library | Same, thinner catalogue |
| Goodreads | Blocks after a single request |
| Amazon | Returns SEO spam |

This is the reason for the whole design. A source that returns a plausible wrong answer is far more dangerous than one that returns nothing.

## Setup

Python 3.10+ and Calibre, available as command line tools. No system install needed:

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

### Development

```bash
ruff check . && ruff format --check .
pytest tests/ -q
```

The test suite covers the title matching only. It needs no network, no Calibre and no ebook files, and runs in well under a second.

## Notes on watermarked files

Some ebook sources inject a promotional `<div>` linking back to themselves before `</body>` in every XHTML file, plus a stray marker file at the archive root. Stripping it is a plain zip rewrite. The PDF twin usually carries the same text rendered into the page, so regenerate that from the cleaned EPUB rather than trying to edit it:

```bash
ebook-convert cleaned.epub out.pdf --paper-size letter
```

## Status

Working, and used on a real library of a few hundred books. Currently a set of scripts rather than a package; a restructure into a `src/` layout is planned. Known rough edges, kept honest:

- The confidence classifier is duplicated rather than shared, so it can drift
- Metadata is read by spawning a Calibre subprocess per book, roughly 350x slower than reading the OPF out of the EPUB zip directly
- Fixed sleeps between source queries rather than adaptive backoff
- Script names start with digits, so they cannot be imported normally

## Contributing

Issues and pull requests are welcome. The one rule that matters: this tool writes to files that are often irreplaceable, so anything that makes it **more willing to write** needs justifying, not just making to pass. Never widen a threshold without evidence from real books, and keep dry run the default.

Work against a copy of a library, never your real one. Before attaching run output to an issue, check it over, since it lists your book filenames.

Security issues go through [private reporting](https://github.com/OffCrazyFreak/eBook-Metamend/security/advisories/new) rather than a public issue.

## Attribution

**Created by: Jakov Jakovac**

Built on top of [Calibre](https://calibre-ebook.com/) by Kovid Goyal, and the open [Open Library](https://openlibrary.org/) search API.

## License [![MIT][mit-shield]][mit]

[mit]: https://opensource.org/licenses/MIT
[mit-shield]: https://img.shields.io/badge/License-MIT-yellow.svg

This work is licensed under the [MIT License](LICENSE).

Calibre is GPL-3.0 and is invoked as a separate process through its command line interface. Per the [FSF's guidance](https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins), communication at arm's length through command-line arguments and files keeps the two programs separate works, so this project is not a derivative of Calibre.
