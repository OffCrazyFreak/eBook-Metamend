# Description

<!-- What does this change and why? Link any related issue. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor (no behaviour change)
- [ ] Change to the matching or confidence model

## Does this make the tool more willing to write?

<!--
A new source, a looser threshold, a new auto-apply path, or anything that turns a
LOW/MED into a HIGH. If yes, say which real books you verified it against and what
stops a wrong match getting through. If no, just say "no".
-->

## Verification

- [ ] Ran a dry run over a test library before and after; proposals are unchanged,
      or changed only in the way this PR intends
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] Runs on Python 3.10+ with no third-party imports
- [ ] No personal paths, filenames or library contents in the diff

<!--
Reminder: work against a copy of a library, never your real one.
-->
