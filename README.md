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
| **HIGH** | **two** sources each match the filename's title (>=0.85) **and** its author (>=0.7) **on their own**, and agree with each other | yes |
| **MED** | one source manages that, or the evidence is weaker | only with `--include-low` |
| **LOW** | anything else | no |

**One source is never enough.** Measured on a real library, a single source returned an abridgement (`On Liberty (Squashed Edition)`), a translation (`Atomic Habits (Tamil)`) and a different book entirely (`Revenge of the Tipping Point`) for three correctly named files. Each would have been written. A second source disagreed with all three.

Both signals must also come from the *same* source. Taking the best title from one answer and the best author from another can manufacture confidence that neither source actually had.

The cost is deliberate: a book only one source knows, typically self-published or niche, cannot reach HIGH and needs `--include-low`.

Dry run is the default. Nothing is ever blanked. Every run leaves a JSON record of what it decided and why.

## Quick start

```bash
pip install -e .
export EBOOK_LIBRARY=~/eBooks

ebook-metamend                                   # preview the whole library
ebook-metamend --match "Digital Minimalism"      # preview one book
ebook-metamend --match "Digital Minimalism" --apply
```

Options: `--apply`, `--match`, `--limit`, `--start`, `--out`, `--include-low`.

## Features

- Three metadata sources per book (Kobo, Google Books, Open Library), each scored on its own
- Filename-anchored confidence model requiring two independent sources to agree
- Rejects adaptations, translations and omnibus false positives
- Title similarity that understands subtitles and refuses omnibus false positives
- Additive only: a field is written when it is missing, or when the incoming value is strictly better
- Dry run by default, full proposal record written every run
- Copies richer EPUB metadata onto its PDF twin, offline
- Audits a library by dumping embedded metadata and opening text per book
- No third-party Python packages

## Tech stack

- **Language:** Python 3.10+, standard library only, `src/` layout (`urllib`, `xml.etree`, `difflib`, `argparse`, `subprocess`, `zipfile`)
- **Metadata I/O:** [Calibre](https://calibre-ebook.com/) command line tools, used as external processes
- **Sources:** Kobo and Google Books via Calibre plugins, Open Library via its public search API
- **Tooling:** ruff, pytest, GitHub Actions. CI enforces the no-dependencies promise

Calibre is used rather than a native Python library because it edits EPUB and PDF metadata **in place**. Libraries that rebuild the EPUB archive can drop the `mimetype` entry, reorder the manifest or lose XML namespaces.

## The commands

| Command | Purpose |
| ------- | ------- |
| `ebook-metamend` | The main tool. Queries three sources, scores, proposes, optionally applies |
| `ebook-metamend-epub-to-pdf` | Copies richer EPUB metadata onto its PDF twin. Local only, no network |
| `ebook-metamend-extract` | Dumps filename, embedded metadata and opening text per book |

Layout:

```
src/ebook_metamend/
├── matching.py    the safety model: norm, sim, classify
├── enrich.py      the pipeline, returns values
├── cli.py         argument parsing and printing only
├── library.py     finding books, reading what the filename claims
├── opf.py         one OPF parser
├── calibre.py     ebook-meta and fetch-ebook-metadata wrappers
├── config.py      paths and the Calibre environment
└── sources/       kobo, google, openlibrary, and the record/replay cache
tools/             snapshot, strip and replay harnesses for measuring a change
```

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

A third case is handled separately. **Adaptations and translations are different books that share a title**, so `On Liberty (Squashed Edition)`, `Atomic Habits (Tamil)`, `The Alchemist Graphic Novel` and `Man's Search for Meaning adapted for Young Adults` are capped at 0.60, below the writing threshold. Every one of those was returned by a live source for the correctly named file.

All three cases are pinned by the test suite, because they are the difference between a repaired library and a ruined one.

## What the sources are actually like

Measured across a few hundred books:

| Source | Answered | Behaviour |
| ------ | -------- | --------- |
| Kobo | 10/10 | Best coverage and the most accurate on editions. Invents a match when it has none, so never trust it alone |
| Google Books | 8/10 | Answers confidently with adaptations, translations and sequels. Needs a second opinion |
| Open Library | varies | Thinner catalogue, and prone to SSL timeouts under rapid queries |
| Goodreads | - | Blocks after a single request. Not used |
| Amazon | - | Returns SEO spam. Not used |

Kobo comes from a plugin that is **not** installed with Calibre by default. Without it the tool silently runs on one source, which is exactly how the three failures above happened. It now refuses quietly to pretend: a missing plugin is reported, not treated as "no such book".

This is the reason for the whole design. A source that returns a plausible wrong answer is far more dangerous than one that returns nothing.

## Setup

Python 3.10+ and Calibre, available as command line tools. No system install needed:

```bash
CAL_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/ebook-metamend/calibre"
mkdir -p "$CAL_ROOT"
curl -fL -o /tmp/calibre.txz https://calibre-ebook.com/dist/linux64
tar xJf /tmp/calibre.txz -C "$CAL_ROOT"
```

On some systems Calibre 9.x needs two environment variables or its binaries fail:

```bash
export LD_LIBRARY_PATH="$CAL_ROOT/lib"                 # else: libcalibre-launcher.so not found
export OPENSSL_MODULES="$CAL_ROOT/lib/ossl-modules"    # else: PDF output crashes in PoDoFo
```

Then add the Kobo metadata plugin, which Calibre does not ship:

```bash
curl -fsSL -o /tmp/kobo-metadata.zip https://plugins.calibre-ebook.com/355983.zip
"$CAL_ROOT/bin/calibre-customize" -a /tmp/kobo-metadata.zip
```

The tool sets both variables internally. `CAL_ROOT` defaults to `~/.cache/ebook-metamend/calibre`; set it if you unpack Calibre elsewhere.

It is deliberately not under `/tmp`. These binaries get executed with `LD_LIBRARY_PATH` pointed at the same root, so a world-writable location would let any local process run code as you. The tool warns if the root it is given is unsafe.

### Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```

The tests cover the matching model, the gain rules, filename and OPF parsing, and
junk-title detection. They need no network, no Calibre and no ebook files, and run
in well under a second.

Source responses can be recorded once and replayed offline, which makes a run
deterministic and turns 63 seconds per book into milliseconds:

```bash
METAMEND_CACHE_MODE=record METAMEND_FIXTURES=./fixtures ebook-metamend --match "Some Book"
METAMEND_CACHE_MODE=replay METAMEND_FIXTURES=./fixtures ebook-metamend --match "Some Book"
```

`tools/snapshot.py` records a library's metadata and content hashes before and
after a run and classifies every file as unchanged, meta-changed, content-changed
or corrupt, so a change can be proven not to have damaged anything.

## Notes on watermarked files

Some ebook sources inject a promotional `<div>` linking back to themselves before `</body>` in every XHTML file, plus a stray marker file at the archive root. Stripping it is a plain zip rewrite. The PDF twin usually carries the same text rendered into the page, so regenerate that from the cleaned EPUB rather than trying to edit it:

```bash
ebook-convert cleaned.epub out.pdf --paper-size letter
```

## Status

Working, and used on a real library of a few hundred books. Packaged as a `src/` layout with tests. Known rough edges, kept honest:

- PDFs still need a Calibre subprocess to read; EPUBs are read from the zip directly
- Calibre splits subjects on commas at every entry point, so a tag containing one cannot be stored at all. Name headings are rewritten to avoid it; other commas still split
- Open Library times out under rapid queries more often than it should

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
