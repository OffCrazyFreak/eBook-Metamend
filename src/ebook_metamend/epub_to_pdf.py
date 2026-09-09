"""Copy an EPUB's richer metadata onto its PDF twin.

Local only, no network. Only ever adds or improves a field, never blanks one.

The two formats of the same book are usually converted from each other, and the
EPUB almost always carries the better record, because PDF metadata tends to come
from whatever produced the file (InDesign, a converter) rather than a publisher.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from . import calibre
from .library import pairs

#: Author values that mean "nobody filled this in", seen in real files.
PLACEHOLDER_AUTHORS = (['Unknown'], ['dam'])
#: A title has to beat the existing one by more than this to be worth copying.
TITLE_IMPROVEMENT_MARGIN = 3

_EXTENSION_TITLE = re.compile(r'\.(pdf|indd|qxd|doc|docx|tex)$', re.I)
_PLACEHOLDER_TITLE = re.compile(r'(untitled|microsoft word|book\d*)', re.I)
#: A short all-caps code such as NBRT_A01. Case sensitive on purpose, so that a
#: real title like "Artemis" is not mistaken for one.
_CODE_TITLE = re.compile(r'[A-Z0-9_\-]{1,14}')


def junky(title: str | None) -> bool:
    """True if a title is not really a title.

    Note that an empty title counts as junk. That is the case that makes the
    copy rule work on PDFs carrying no title at all, and it is why this cannot be
    replaced by the regexes alone.
    """
    title = (title or '').strip()
    if not title:
        return True
    if _EXTENSION_TITLE.search(title):
        return True
    if _PLACEHOLDER_TITLE.fullmatch(title):
        return True
    return bool(_CODE_TITLE.fullmatch(title))


@dataclass
class Results:
    total: int = 0
    changed: int = 0


def _emit(results: Results, on_line: Callable[[str], None] | None, line: str) -> None:
    """Report a line as it happens. Buffering the whole run meant an interrupted
    --apply lost the record of PDFs it had already written."""
    if on_line:
        on_line(line)


def plan(epub_meta: dict, pdf_meta: dict) -> tuple[list[tuple[str, str, str]], list[str]]:
    """What the PDF is missing that the EPUB has. Returns (described ops, args)."""
    ops: list[tuple[str, str, str]] = []
    args: list[str] = []

    epub_title = epub_meta.get('title') or ''
    pdf_title = pdf_meta.get('title') or ''
    # Never copy a junk EPUB title onto the PDF; those books need the online path.
    if (
        epub_title
        and not junky(epub_title)
        and (junky(pdf_title) or len(epub_title) > len(pdf_title) + TITLE_IMPROVEMENT_MARGIN)
    ):
        ops.append(('title', pdf_title, epub_title))
        args += ['-t', epub_title]

    epub_authors = epub_meta.get('authors') or []
    pdf_authors = pdf_meta.get('authors') or []
    if epub_authors and (not pdf_authors or pdf_authors in PLACEHOLDER_AUTHORS):
        value = ' & '.join(epub_authors)
        ops.append(('author', ', '.join(pdf_authors) or '-', value))
        args += ['-a', value]

    for key, flag, describe in (
        ('publisher', '--publisher', lambda v: v),
        ('description', '-c', lambda v: f'{len(v)} chars'),
        ('isbn', '--isbn', lambda v: v),
    ):
        value = epub_meta.get(key)
        if value and not pdf_meta.get(key):
            ops.append((key, '-', describe(value)))
            args += [flag, value]

    epub_tags = epub_meta.get('tags') or []
    if epub_tags and not pdf_meta.get('tags'):
        ops.append(('tags', '-', ', '.join(epub_tags[:6])))
        args += ['--tags', calibre.TAG_SEPARATOR.join(epub_tags)]

    return ops, args


def run(
    *,
    limit: int = 0,
    do_apply: bool = False,
    root: str | None = None,
    on_line: Callable[[str], None] | None = None,
) -> Results:
    selected = pairs(root)
    if limit:
        selected = selected[:limit]
    results = Results(total=len(selected))

    for index, book in enumerate(selected, 1):
        # The bare-ISBN fallback is enabled here and not in the enricher, which is
        # a real difference in what counts as an ISBN, preserved deliberately.
        epub_meta = calibre.read_book_metadata(book.epub, bare_isbn_fallback=True) or {}
        pdf_meta = calibre.read_book_metadata(book.pdf, bare_isbn_fallback=True) or {}
        if not epub_meta:
            continue

        ops, args = plan(epub_meta, pdf_meta)
        if not ops:
            continue

        results.changed += 1
        _emit(results, on_line, f'[{index}/{len(selected)}] {os.path.basename(book.pdf)[:72]}')
        for field_name, was, now in ops:
            _emit(
                results, on_line, f'      {field_name:<12} {str(was)[:34]:<34} -> {str(now)[:60]}'
            )
        if do_apply:
            ok, stderr = calibre.write_metadata(book.pdf, args, timeout=90)
            _emit(results, on_line, f"      {'written' if ok else 'FAILED: ' + stderr[:80]}")
        _emit(results, on_line, '')

    return results
