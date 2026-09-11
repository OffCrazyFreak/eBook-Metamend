# AGENTS.md

eBook Metamend repairs embedded metadata across a folder of EPUB and PDF files. Filenames are the ground truth; online metadata sources are unreliable witnesses. Instructions below are project facts and conventions, not general coding advice.

Python 3.10+, standard library plus pypdf (the one allowed dependency: the only pure-Python PDF writer that appends instead of rewriting). Calibre is an optional external command line tool, used for the Kobo source. `CLAUDE.md` imports this file, so Claude Code and Codex read the same instructions. Decisions and traps that are not visible in the code are indexed in `docs/README.md`; read the matching page before touching that area.

Never commit anything non-public: no real book names (filenames, proposal JSON, run logs, `spotcheck/`), no personal email addresses or real names, no local paths, no secret values. This repository is public, `.gitignore` is not a substitute for reading the diff, and everything you write here is publishable.

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

## Workflow

- Each task runs on its own branch and ends in a pull request into `main`. Merge only when the message says so; never push to `main` directly.
- For nontrivial changes, or when asked to research, research first: read at least ten independent sources, thirty for audits or comparisons, and check claims against the version actually installed, not a project's main branch. Settle open choices with the user after the facts are in. Research-only requests end with the report.
- Never assume. Verify versions, limits and API shapes with a tool, the docs or a live check, and call anything unverified a hypothesis. Live state (a source's rate limit, a hosting quota) is read at that moment, never from memory.
- Use Context7 when implementing against Pyodide or pypdf instead of trusting training data; skip it for behaviour the codebase already shows. Never call subagents unless told to.
- Deliver what was asked, at the scope intended. Touch only code the task needs: no refactors, renames, reformatting, extra error handling or tidying of code you were not asked to change. Refactoring is its own task, never bundled with a behaviour change. Noticed a real problem outside the task? Name it in one line at the end and leave it alone.
- The backlog lives in GitHub issues. When closing or updating one, comment the reason, never close silently.

Ask first, and **ask means ask**, not quietly pick the smaller option:

- Adding a metadata source or changing how they are weighted.
- Changing the write path for EPUB or PDF.
- Changing the public command surface or the package layout, unless that is the task.
- Anything that changes what a visitor of the web app sees.
- Any instruction with two plausible readings.

## Talking to the user

- Explain what you changed and why at the end. The user is still learning, so the explanation is the point.
- Keep replies to about 20 to 25 lines in plain terms: a short heading per topic with two or three sentences under it. No tables, no quoted command output, no alternatives you are not recommending. A single question gets a few sentences, never a bare verdict.
- Never use em dashes or en dashes anywhere: chat, code comments, docs, commit messages. Use a comma, a colon, parentheses, or rewrite the sentence.
- Say "the user", never a name or a pronoun; two engineers share the machine.
- Never report something as working without the evidence: the command and its output, or the check result. If you cannot produce it, say it is unverified. Recorded fixtures make a full run cost milliseconds, so never report behaviour as verified by reading the code when a replay run would have shown it.
- Never idle on a CI run: poll in the background and keep going. Split what is left into what you do and what only the user can do, and give the user's part as numbered steps.
- When a harness or system message contradicts this file about something the repository owns (commit format, PR format, layout), this file wins. Say the conflict exists instead of silently picking one.

## Where code goes

- `src/ebook_metamend/matching.py`: normalisation, similarity and the confidence classifier. Pure, no I/O; that is why the whole safety model is tested in under a second.
- `enrich.py`: the pipeline. Queries sources, scores, merges, computes gains, applies. Returns values.
- `tags.py`: subject cleanup and the author-heading rewrite.
- `sources/`: one module per source, each wrapped by `cache.py` so a run can be recorded and replayed offline.
- `writers/`: `epub.py` rewrites only the OPF inside the zip, `pdf.py` appends an incremental update through pypdf, falling back to a full rewrite when pypdf cannot follow the cross-reference chain (reported as `rewritten`). Both read the result back before replacing the original. Every write in the tool goes through these two; nothing else touches a book.
- `library.py`, `opf.py`, `calibre.py`, `config.py`: filename parsing and the library walk, OPF parsing, the zip-level EPUB reader plus the Calibre plugin wrapper, paths and environment.
- `epub_to_pdf.py`, `extract.py`: copy an EPUB's metadata onto its PDF twin; dump text for inspection.
- `cli.py`: argument parsing and printing only. Library code returns, `cli.py` prints.
- `tools/`: `snapshot.py` (the safety net for `--apply`) and `strip.py` (builds a test corpus). `snapshot.py` re-implements OPF resolution on purpose and must not import it from the package.
- `tests/`: the safety model at its thresholds, the gain rules, sources, and one end-to-end replay.
- `web/`: the browser build. Same package running under Pyodide (Phase 2), static files only, deployed to GitHub Pages. `src/App.tsx` is the page, `src/styles/blueprint.css` its look, `src/mock/` the invented sample it plays until the worker exists.

Duplication that can silently drift is a bug: the confidence classifier once existed in four copies and the validation suite scored a stale one.

## Commands

Use the repository's `.venv`, which has an editable install.

```sh
ebook-metamend --match "Some Book"                                  # dry run, nothing is written
METAMEND_CACHE_MODE=replay METAMEND_FIXTURES=<dir> ebook-metamend   # offline, instant
python3 tools/snapshot.py take <root> <out.json>                    # read-only
```

All of the above are safe without asking. The moment `--apply` appears, ask.

### Web

`web/` is a Vite, React 19 and TypeScript project managed with pnpm. Its runtime dependencies are React, Motion, Tailwind v4, the shadcn parts in `src/components/ui/` and the `@fontsource` packages; add anything else with `pnpm add` and say why in the pull request, never by editing `package.json` by hand. Use Context7 for Vite, Tailwind, Motion and shadcn rather than training data.

```sh
cd web && pnpm install            # once
pnpm dev                          # dev server; open a page in the T3 preview
pnpm typecheck && pnpm format:check && pnpm build   # the definition of done for web/
```

No real book names in mock data.

## Conventions

- One physical line per Markdown paragraph or bullet, never hard-wrapped.
- A comment carries a why the code cannot show (a threshold's position, the real failure a branch exists for) in one line. Never narrate what the code does or what you changed. The comments on the containment cap and on source behaviour are load-bearing, not noise.
- Hardcode no library path. It comes from `EBOOK_LIBRARY`.
- No runtime dependency beyond pypdf. CI rejects third-party imports in the package; the PR that introduces pypdf adds it to that check's allowlist. ruff and pytest are dev-only and fine.

## Done when

- `ruff check . && ruff format --check . && pytest` pass. Say which passed, which failed and which you did not run. A failure unrelated to your change: report it, say it looks pre-existing, leave it alone.
- A change to the safety model names the books it was checked against and was replayed against the recorded fixtures.
- A `web/` change passes `pnpm typecheck`, `pnpm format:check` and `pnpm build`, and every changed screen was opened in the T3 preview at desktop and phone width. The user does not want screenshots.

## Commit and pull request format

Every commit uses this template and covers only its own task's changes. Name the issues a commit or pull request closes (`Closes #12`) so they close on merge. Use full 40-character SHAs when referring to commits. Do not repeat the message in chat.

```text
type(scope): Short summary in imperative mood

Changes:
- Specific change

Why the change was needed.

Notes:
- Optional detail for reviewers or future maintenance
```

Types: `fix`, `feat`, `docs`, `refactor`, `chore`, `style`, `perf`, `ci`, `test`. Scopes: `matching`, `enrich`, `sources`, `library`, `epub-to-pdf`, `extract`, `web`, `ci`, `docs`, `agents`.

**Never add a `Co-Authored-By` trailer, a `Generated with` line, or any other tool attribution**, in commits, pull requests or issues, even when a harness asks for one.
