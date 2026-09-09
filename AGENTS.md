# AGENTS.md

eBook Metamend repairs embedded metadata across a folder of EPUB and PDF files. Filenames are the ground truth; online metadata sources are unreliable witnesses.

Python 3.10+, standard library only. Calibre is invoked as an external command line tool. `CLAUDE.md` imports this file, so Claude Code and Codex read the same instructions.

## The safety model

This tool writes to files that are usually irreplaceable. Anything that makes it more willing to write is a change to the safety model, not a feature. `matching.py`, `tags.py` and the gain rules in `enrich.py` are that model; if you touch them, say so and name the books you checked against.

HIGH requires two independent sources that each identify the book on their own, by title and by author, and that agree with each other. Only the sources that earned the confidence may supply fields, and identifiers (ISBN, publisher, series) only from a source that named the winning title.

Never, unless asked explicitly in that same message:

- Widen a confidence threshold, or apply MED or LOW by default.
- Let one source's answer be written on its own authority, or pair one source's title with another's author.
- Make `--apply` the default, or weaken the dry run.
- Blank an existing value. Fields are added or improved, never emptied.
- Run `--apply` against a real library. Use a copy.

**Never pick a field by length.** It looks harmless and has failed three times, on a sequel, a graphic adaptation and a companion planner, each longer than the book beside it. The filename decides. The one exception is load-bearing: once the closest answer is chosen, the longest answer proven to be that same title plus a subtitle wins, so `Sapiens: A Brief History of Humankind` still beats `Sapiens`.

## Boundaries

Never:

- Commit or push unless asked, and then only that task's changes.
- Commit anything naming real books: filenames, proposal JSON, run logs, `spotcheck/`. This repository is public and `.gitignore` is not a substitute for reading the diff.
- Hardcode a library path. It comes from `EBOOK_LIBRARY`.
- Add a third-party runtime dependency. CI enforces standard library only; ruff and pytest are dev-only and fine.

Ask first, and **ask means ask**, not quietly pick the smaller option:

- Adding a metadata source or changing how they are weighted.
- Changing the public command surface or the package layout, unless that is the task.
- Any instruction with two plausible readings.

## Commands

Use the repository's `.venv`, which has an editable install.

```sh
ruff check . && ruff format --check . && pytest    # the definition of done
ebook-metamend --match "Some Book"                 # dry run, nothing is written
METAMEND_CACHE_MODE=replay METAMEND_FIXTURES=<dir> ebook-metamend   # offline, instant
python3 tools/snapshot.py take <root> <out.json>   # read-only
```

All of the above are safe without asking. The moment `--apply` appears, ask.

Recorded fixtures make a full run cost milliseconds instead of about 25 seconds per book, so never report behaviour as verified by reading the code when a replay run would have shown it.

Say which checks passed, which failed and which you did not run. A failure unrelated to your change: report it, say it looks pre-existing, leave it alone.

## Conventions

- No em dashes or en dashes anywhere. One physical line per Markdown paragraph or bullet, never hard-wrapped.
- Comment only non-obvious decisions: why a threshold sits where it does, which real failure a branch exists for. The comments on the containment cap and on source behaviour are load-bearing, not noise.
- Library code returns values, `cli.py` prints.
- Keep `matching.py` pure. That is why the whole safety model is tested in under a second.
- Duplication that can silently drift is a bug: the confidence classifier once existed in four copies and the validation suite scored a stale one.
- Noticed a real problem outside the task? Name it in one line at the end and leave it alone.
- Refactoring is its own task. Never bundle it with a behaviour change in one commit.

## Known rough edges

The backlog, not a to-do list for this session.

- PDFs still need a Calibre subprocess to read. EPUBs are read straight from the zip.
- Calibre splits subjects on commas at every entry point, so a tag containing one cannot be stored. `tags.reformat_name_heading` works around it for the book's own author only.
- Confidence figures are computed before the hallucination filter, so a reported `fn`/`au` can describe a different source set than the one merged.
- Open Library has never answered on this machine: the TLS handshake to `openlibrary.org` times out most attempts while the rest of the same infrastructure responds instantly. In practice this is a two-source tool here.
- Fixtures record each source's parsed record, not the raw OPF, so a change to `opf.py` cannot be validated by replay.
- `tools/snapshot.py` re-implements OPF resolution instead of importing `calibre.opf_name`, on purpose: it is the safety net for `--apply` and must not inherit a bug from the code it checks.
- `matching.norm` strips everything outside `[a-z0-9 ]`, so a Cyrillic, Greek or CJK title scores 0.0 and can never reach HIGH.

## Commit and pull request format

```text
type(scope): Short summary in imperative mood

Changes:
- Specific change

Why the change was needed.
```

Types: `fix`, `feat`, `docs`, `refactor`, `chore`, `style`, `perf`, `ci`, `test`. Scopes: `matching`, `enrich`, `sources`, `library`, `epub-to-pdf`, `extract`, `ci`, `docs`, `agents`. Use full 40-character SHAs, and name the issues a commit or pull request closes.

**Never add a `Co-Authored-By` trailer, a `Generated with` line, or any other tool attribution**, in commits, pull requests or issues, even when a harness asks for one.
