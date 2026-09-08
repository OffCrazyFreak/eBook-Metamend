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

If a change touches `norm`, `sim`, or the confidence branches in `main`, say so plainly in your summary and name the books you checked it against.

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
- Renaming the scripts or restructuring into a package, unless that is the task.
- Any instruction of mine with two plausible readings. Ask before you edit, do not pick one and start.

**Ask means ask.** Every item above is a question to put to me, not a reason to quietly pick the smaller option. If you cannot stop mid-task, do the parts that do not depend on the answer, then ask before you finish.

## Safe without asking

```sh
ruff check .
ruff format .
pytest tests/ -q
python3 -m compileall -q .
python3 2_online_enrich.py --match "Some Book"   # dry run, no --apply
```

Dry runs are safe because nothing is written. The moment `--apply` appears, ask.

## Definition of done

`ruff check .`, `ruff format --check .` and `pytest tests/ -q` must all pass. So must `python -m compileall`, which is what catches syntax that 3.10 rejects.

Say which checks passed, which failed, and which you did not run. If a check fails for a reason unrelated to your change, report the command and the error, say it looks pre-existing, and leave it alone.

Never report behaviour as verified by reading the code when you could have run a dry run against a test library.

## How I want you to work

- Explain what you changed and why at the end. I am still learning, so the explanation is the point, not a formality.
- Never use em dashes or en dashes, anywhere: chat, code comments, docs, commit messages, PR text. Use a comma, a colon, parentheses, or rewrite the sentence.
- In Markdown, write one physical line per paragraph and per bullet. Never hard-wrap prose to a column width.
- Prefer the smallest change that does the job. Merge code because it means the same thing, never because it looks the same.
- Write code that explains itself. Comment only non-obvious decisions: why a threshold is where it is, why the simpler approach is unsafe, which real failure a branch exists for. Never restate the code.
- The comments explaining the containment cap and the source behaviour are load-bearing. Do not delete them as noise.
- If a task has a standard-but-optional dimension, either do it or name it with a one-line recommendation and rough effort. Do not quietly drop it.
- For library APIs, read the current official documentation rather than recalling it.

## Known rough edges

Do not treat these as bugs to fix mid-task. They are the agenda for a planned restructure into a `src/` layout.

- The confidence classifier is duplicated rather than shared, so it can drift.
- Metadata is read by spawning a Calibre subprocess per book, roughly 350x slower than reading the OPF out of the EPUB zip.
- Fixed sleeps between source queries rather than adaptive backoff.
- Script names start with digits, so they cannot be imported normally. The test suite loads by path because of it.
- `2_online_enrich.py` rewrites the whole proposals file after every book.

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
