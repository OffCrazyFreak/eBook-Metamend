# Contributing to ebook-metamend

Thanks for taking a look. This is a small, focused tool, and contributions of any
size are welcome.

## Ways to contribute

- **Report a bug.** Open an issue describing what you ran, what you expected and
  what happened. The proposals JSON from the run is usually the most useful thing
  to attach, but check it first and redact anything you would rather not publish -
  it lists your book filenames.
- **Report a bad match.** If a source returned the wrong book and it was written
  anyway, that is the most valuable bug report this project can get. Include the
  filename, the title that was written, and the confidence line from the output.
- **Suggest a source.** Another metadata provider with decent coverage and honest
  failure behaviour would be genuinely useful.
- **Improve the docs.** Corrections and clarifications are welcome.
- **Send code.** See below.

## Before you start

For anything beyond a small fix, open an issue first so the approach can be agreed
before you spend time on it.

## Development setup

There are no Python dependencies. You need Python 3.10+ and Calibre available as
command line tools:

```bash
mkdir -p /tmp/cal
curl -fL -o /tmp/calibre.txz https://calibre-ebook.com/dist/linux64
tar xJf /tmp/calibre.txz -C /tmp/cal
export LD_LIBRARY_PATH=/tmp/cal/lib
export OPENSSL_MODULES=/tmp/cal/lib/ossl-modules
export EBOOK_LIBRARY=/path/to/a/test/library
```

Work against a **copy** of a library, never your real one, and keep a backup.

## The one rule that matters

This tool writes to files that are often irreplaceable. Anything that makes it
more willing to write is a change to its safety model and needs to be justified,
not just made to pass.

Concretely:

- Never widen a confidence threshold without evidence from real books.
- Never let a single source's answer be written on its own authority.
- Keep dry run the default. `--apply` must stay explicit.
- Never blank an existing value. Fields are added or improved, never emptied.

## Pull request workflow

1. Fork and branch from `main`.
2. Make your change.
3. Run a dry run over a test library before and after, and confirm the proposals
   are identical unless your change was meant to alter them.
4. Open a pull request describing what changed and, if it touches matching or
   confidence, which books you verified it against.

### Before you request review

- The code runs on Python 3.10+ with no third-party imports.
- `ruff check .` and `ruff format --check .` pass.
- No personal paths, filenames or library contents are committed. The `.gitignore`
  covers the usual output, but check your diff.

## Review process

This is maintained in spare time, so reviews may take a few days. Small, focused
pull requests get merged much faster than large ones.
