#!/usr/bin/env python3
"""Clear the enrichable metadata fields from a copy of a library.

Used to build a baseline corpus: a library with fields missing gives the enricher
something to propose, so a run actually measures something.

Clears tags, description, publisher, ISBN and series. Deliberately leaves title
and author alone, because the tool derives its query from the filename and scores
candidates against it, so blanking them would measure a path no real library hits.

Two mechanisms, because one is not enough. Passing an empty string to ebook-meta
clears PDFs reliably but silently leaves publisher, comments and ISBN on EPUBs
(measured: 7 of 19 files were not fully cleared). EPUBs are therefore edited at
the OPF level inside the zip, which is exact.

Every file is read back afterwards. A field that is still present is reported as
a failure rather than assumed cleared.

    python3 tools/strip.py <root> [--dry-run]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile

CAL_ROOT = os.environ.get('CAL_ROOT', '/tmp/cal')
EM = os.path.join(CAL_ROOT, 'bin', 'ebook-meta')
ENV = dict(
    os.environ,
    CALIBRE_CONFIG_DIRECTORY=CAL_ROOT + '/config',
    QT_QPA_PLATFORM='offscreen',
    LD_LIBRARY_PATH=CAL_ROOT + '/lib',
    OPENSSL_MODULES=CAL_ROOT + '/lib/ossl-modules',
)

PDF_CLEAR_ARGS = ['--tags', '', '-c', '', '-p', '', '--isbn', '', '-s', '']

# Whole elements to drop from the OPF.
_DROP = [
    re.compile(r'<dc:subject\b[^>]*>.*?</dc:subject>\s*', re.S | re.I),
    re.compile(r'<dc:description\b[^>]*>.*?</dc:description>\s*', re.S | re.I),
    re.compile(r'<dc:publisher\b[^>]*>.*?</dc:publisher>\s*', re.S | re.I),
    re.compile(r'<dc:subject\b[^>]*/>\s*', re.I),
    re.compile(r'<meta[^>]*name=["\']calibre:series(?:_index)?["\'][^>]*/?>\s*', re.I),
]
# An ISBN identifier is neutralised rather than deleted: it is often the package's
# unique-identifier (Karp's is), and removing that element makes the EPUB invalid.
# Two spellings occur in practice, an opf:scheme attribute carrying bare digits and
# an isbn: prefix in the element text. Both have to be caught.
_IDENTIFIER = re.compile(r'<dc:identifier\b([^>]*)>(.*?)</dc:identifier>', re.S | re.I)
_SCHEME_ISBN = re.compile(r'scheme\s*=\s*(["\'])isbn\1', re.I)
_TEXT_ISBN = re.compile(r'^\s*(?:urn:)?isbn[:\s]', re.I)


def _neutralise_isbn(match: re.Match) -> str:
    attrs, value = match.group(1), match.group(2)
    if not (_SCHEME_ISBN.search(attrs) or _TEXT_ISBN.match(value)):
        return match.group(0)
    attrs = _SCHEME_ISBN.sub(r'scheme=\1uuid\1', attrs)
    return f'<dc:identifier{attrs}>urn:uuid:stripped-for-baseline</dc:identifier>'


def strip_epub(path: str) -> bool:
    """Rewrite the OPF inside the EPUB. Everything else is copied byte for byte."""
    try:
        zin = zipfile.ZipFile(path)
        names = zin.namelist()
        opf_names = [n for n in names if n.lower().endswith('.opf')]
        if not opf_names:
            return False
        blobs = {n: zin.read(n) for n in names}
        zin.close()
    except Exception:
        return False

    for opf in opf_names:
        text = blobs[opf].decode('utf8', 'ignore')
        for pattern in _DROP:
            text = pattern.sub('', text)
        text = _IDENTIFIER.sub(_neutralise_isbn, text)
        blobs[opf] = text.encode('utf8')

    tmp = path + '.tmp'
    order = (['mimetype'] if 'mimetype' in blobs else []) + [n for n in names if n != 'mimetype']
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n in order:
            info = zipfile.ZipInfo(n)
            info.compress_type = zipfile.ZIP_STORED if n == 'mimetype' else zipfile.ZIP_DEFLATED
            zout.writestr(info, blobs[n])
    os.replace(tmp, path)
    return True


def strip_pdf(path: str) -> bool:
    r = subprocess.run(
        [EM, path, *PDF_CLEAR_ARGS], capture_output=True, text=True, timeout=300, env=ENV
    )
    return r.returncode == 0


def remaining(path: str) -> list[str]:
    """Which target fields survived. An identifier only counts if it is an ISBN,
    since calibre cannot remove a package identifier and a uuid is harmless."""
    r = subprocess.run([EM, path], capture_output=True, text=True, timeout=120, env=ENV)
    found = []
    for line in r.stdout.splitlines():
        if ':' not in line:
            continue
        field, value = (part.strip() for part in line.split(':', 1))
        if field in ('Tags', 'Publisher', 'Series', 'Comments'):
            found.append(field)
        elif field == 'Identifiers' and 'isbn' in value.lower():
            found.append('ISBN')
    return sorted(found)


def main() -> int:
    root = sys.argv[1]
    dry = '--dry-run' in sys.argv

    targets = [
        os.path.join(d, f)
        for d, _, fs in os.walk(root)
        for f in sorted(fs)
        if f.lower().endswith(('.epub', '.pdf'))
    ]
    print(f"{len(targets)} files | {'DRY RUN' if dry else 'CLEARING'}\n")

    failures = []
    for n, p in enumerate(targets, 1):
        before = remaining(p)
        if dry:
            print(f'[{n}/{len(targets)}] {os.path.basename(p)[:66]}  has: {before or "-"}')
            continue

        ok = strip_epub(p) if p.lower().endswith('.epub') else strip_pdf(p)
        after = remaining(p)
        if after or not ok:
            failures.append((p, after))
        print(
            f'[{n}/{len(targets)}] {os.path.basename(p)[:58]:<58} '
            f'{before or "-"} -> {after or "clean"}'
            f'{"" if not after else "   !! NOT CLEARED"}'
        )

    if not dry:
        print(f'\n{len(targets) - len(failures)}/{len(targets)} fully cleared')
        for p, after in failures:
            print(f'  FAILED {os.path.basename(p)}: {after}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
