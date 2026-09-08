# Security Policy

## Reporting a vulnerability

Please **do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Instead, use GitHub's private reporting channel: the
[Report a vulnerability](https://github.com/OffCrazyFreak/ebook-metamend/security/advisories/new)
button under the repository's **Security** tab. The report stays private between
you and the maintainer.

Please include as much detail as you can:

- The type of issue.
- The affected script and the commit or version you tested.
- Steps to reproduce, and a proof of concept if possible.
- The potential impact.

## Scope

ebook-metamend is a local command line tool. It has no server, no accounts and no
stored credentials. The realistic risk surface is:

- **Writes to your files.** The tool invokes Calibre to modify EPUB and PDF
  metadata in place. A flaw that causes it to write to the wrong file, write
  attacker-controlled content, or destroy existing metadata is in scope.
- **Untrusted input from metadata sources.** Responses from Kobo, Google Books and
  Open Library are parsed as XML and JSON, and values from them are passed to a
  subprocess. Injection or parser issues there are in scope.
- **Path handling.** The library path comes from the `EBOOK_LIBRARY` environment
  variable and filenames are used to build queries. Path traversal is in scope.

Vulnerabilities in Calibre itself belong to
[the Calibre project](https://github.com/kovidgoyal/calibre), not here.

## What to expect

- This is a personal project maintained in spare time, so please allow a few days
  for an acknowledgement.
- You will be kept informed while a fix is worked on.
- Please allow reasonable time for a fix before public disclosure.

Responsible disclosure is appreciated, and reporters who want credit will get it.
