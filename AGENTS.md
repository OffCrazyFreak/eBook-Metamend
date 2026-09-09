# AGENTS.md

eBook Metamend repairs embedded metadata across a folder of EPUB and PDF files, using the filenames as ground truth and treating online metadata sources as unreliable witnesses.
`CLAUDE.md` imports this file, so Claude Code and Codex read the same instructions.

Python 3.10+, standard library only. Calibre is invoked as an external command line tool. MIT licensed and genuinely open source, so it can be described that way.

## The rule that outranks the others

This tool writes to files that are usually irreplaceable. Anything that makes it more willing to write is a change to the safety model, not a feature.

Never, without being asked explicitly and in that same message:

- Widen a confidence threshold, or add a path that applies MED or LOW confidence by default.
- Let a single source's answer be written on its own authority.
- Make `--apply` the default, or weaken the dry run.
- Add code that blanks an existing metadata value. Fields are added or improved, never emptied.
- Run anything with `--apply` against a real library. Use a copy.

If a change touches anything in `matching.py` or `tags.py`, say so plainly in your summary and name the books you checked it against. Those modules are the safety model.

HIGH requires two independent sources that each identify the book on their own and agree with each other. Do not relax that to one source, and do not let a title from one source pair with an author from another.

## Boundaries

Never:

- Commit or push unless I ask. When asked, include only that task's changes.
- Commit anything naming real books from my library: filenames, proposal JSON, run logs, `spotcheck/` output. The `.gitignore` covers the usual paths, but check the diff. This repository is public.
- Commit personal paths. The library location comes from `EBOOK_LIBRARY`, never a hardcoded path.
- Add a third-party Python dependency. The tool is standard library only and CI enforces it. Dev tools (ruff, pytest) are fine and are not imported by the scripts.
- Touch unrelated changes already in the worktree. Do not revert, reformat, or stage them.

Ask first:

- Adding a metadata source, or changing how existing ones are weighted.
- Adding a dependency the task does not strictly require.
- Changing the public command surface or the package layout, unless that is the task.
- Any instruction of mine with two plausible readings. Ask before you edit, do not pick one and start.

**Ask means ask.** Every item above is a question to put to me, not a reason to quietly pick the smaller option. If you cannot stop mid-task, do the parts that do not depend on the answer, then ask before you finish.

## Safe without asking

```sh
ruff check .
ruff format .
pytest
ebook-metamend --match "Some Book"                 # dry run, no --apply
METAMEND_CACHE_MODE=replay METAMEND_FIXTURES=<dir> ebook-metamend   # offline, instant
python3 tools/snapshot.py take <root> <out.json>   # read-only
```

Use the repository's `.venv`, which has an editable install. Sources are recorded
and replayed from fixtures, so a dry run costs milliseconds rather than 63 seconds
per book.

Dry runs are safe because nothing is written. The moment `--apply` appears, ask.

## Definition of done

`ruff check .`, `ruff format --check .` and `pytest` must all pass. CI also enforces that the package imports only the standard library.

Say which checks passed, which failed, and which you did not run. If a check fails for a reason unrelated to your change, report the command and the error, say it looks pre-existing, and leave it alone.

Never report behaviour as verified by reading the code when you could have run a dry run against a test library.

## How I want you to work

- Explain what you changed and why at the end. I am still learning, so the explanation is the point, not a formality.
- Never use em dashes or en dashes, anywhere: chat, code comments, docs, commit messages, PR text. Use a comma, a colon, parentheses, or rewrite the sentence.
- In Markdown, write one physical line per paragraph and per bullet. Never hard-wrap prose to a column width.
- Write code that explains itself. Comment only non-obvious decisions: why a threshold is where it is, why the simpler approach is unsafe, which real failure a branch exists for. Never restate the code.
- The comments explaining the containment cap and the source behaviour are load-bearing. Do not delete them as noise.
- If a task has a standard-but-optional dimension, either do it or name it with a one-line recommendation and rough effort. Do not quietly drop it.
- For library APIs, read the current official documentation rather than recalling it.

## Code quality

Hand it over the way a senior would: someone should be able to read one function, know what it does, and change it without reading the rest.

- Prefer the smallest change that does the job.
- DRY by meaning, not by shape. Merge two pieces of code because they encode the same rule and must change together, never because they look alike.
- Duplication that can silently drift is a bug, not a style preference. The confidence classifier used to exist in four copies here, and the validation suite scored a stale one, so the thing meant to catch drift was itself drifting.
- Do not abstract on the first repeat. A wrong abstraction costs more to undo than the duplication it replaced.
- One job per function, one reason to change per file. If you cannot name it without "and", split it.
- Keep logic pure where you can. `matching.py` and the gain rules touch nothing external, which is why the whole safety model is covered by tests that run in under a second.
- Library code returns values, the CLI layer prints. Do not bury output inside a function that computes something.
- Write for the reader. One statement per line, no semicolon stacking, no dense one-liners.
- Names say what, not how. Avoid `process`, `handle`, `data`, `manager`.

## Scope

- Do the task I asked for and finish it fully. Do not half-do it and add something I did not ask for.
- Noticed a real problem outside the task? Name it in one line at the end with a rough effort estimate, and leave it alone.
- "While I was in there" is not a reason. A diff touching files the task did not require is harder to review and harder to revert.
- Refactoring is its own task. Never bundle it with a behaviour change in the same commit.
- `## Known rough edges` is the backlog, not a to-do list for this session.

## Known rough edges

Do not treat these as bugs to fix mid-task. They are the backlog.

- PDFs still need a Calibre subprocess to read. EPUBs go through `calibre.read_book_metadata`, which reads the zip directly.
- Calibre splits subjects on commas at every entry point (`--tags`, `--from-opf`, all of them), so a tag containing a comma cannot be stored. `tags.reformat_name_heading` works around it for name headings only.
- The hallucination filter runs after the scores are computed, so a reported `fn`/`au` can describe a different source set than the one that was merged.
- Open Library has never answered on this machine: the TLS handshake to `openlibrary.org` times out most attempts while the rest of the same infrastructure responds instantly. It reports its failures and is shelved after a few in a row, so it costs a few seconds rather than a few minutes, but in practice this is a two-source tool here.
- Fixtures record each source's *parsed* record, not the raw OPF, so a change to `opf.py` cannot be validated by replay. Wrapping `calibre.fetch_metadata` instead would fix it.
- `tools/snapshot.py` deliberately re-implements OPF resolution rather than importing `calibre.opf_name`. It is the safety net for `--apply`, so it must not inherit a bug from the code it checks.
- `matching.norm` strips everything outside `[a-z0-9 ]`, so a Cyrillic, Greek or CJK title normalises to an empty string and scores 0.0. Those books can never reach HIGH.
- `TITLE_IMPROVEMENT_MARGIN` exists in both `enrich.py` and `epub_to_pdf.py` with the same value. They are not merged on purpose: one governs an online title against an embedded one, the other an EPUB's title against its PDF twin, and they can reasonably diverge.

## Commit message

End every response that changed code with a suggested message. Check `git status --short` and the diff first, and cover only this task's changes.

```text
type(scope): Short summary in imperative mood

Changes:
- Specific change

Brief explanation of why the change was needed.
```

Add a `Notes:` section only when there is something a reviewer would otherwise miss.

Types in use: `fix`, `feat`, `docs`, `refactor`, `chore`, `style`, `perf`, `ci`, `test`. Scope is the area: `matching`, `enrich`, `sources`, `epub-to-pdf`, `extract`, `ci`, `docs`, `agents`.

**Never add a `Co-Authored-By` trailer, a `Generated with` line, or any other tool attribution.** Not in commits, not in pull requests, not in issues.

Use full 40-character SHAs when referring to commits, and name the issues a commit or pull request closes.
