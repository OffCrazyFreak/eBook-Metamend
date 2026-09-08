"""Finding books on disk, and reading what the filename claims about them.

One walker, replacing seven copies. ``books()`` and ``pairs()` deliberately keep
their different contracts: the enricher wants every stem including single-format
ones, the EPUB-to-PDF copier only wants stems that have both.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .config import LIBRARY

BOOK_EXTENSIONS = ('.epub', '.pdf')

#: A series number embedded in a filename, as in "Series - 02.5 - Title".
_SERIES_NUMBER = re.compile(r'\s*-\s*\d+(\.\d+)?\s*-\s*')
#: Where a search query should stop: a subtitle separator or a parenthesis.
_QUERY_TAIL = re.compile(r'\s+-\s+|\s*:\s*|\s*\(')


@dataclass(frozen=True)
class FilenameFacts:
    """What the filename asserts. Treated as ground truth: it is the one piece of
    metadata a human curated, so online sources are scored against it."""

    stem: str
    author: str
    #: Full title with any embedded series number removed.
    title: str
    #: Shortened form used to query sources, which do badly with long subtitles.
    query: str


def parse_filename(stem: str) -> FilenameFacts:
    author, _, rest = stem.partition(' - ')
    title = _SERIES_NUMBER.sub(' ', rest).strip()
    query = _QUERY_TAIL.split(title)[0].strip() or title
    return FilenameFacts(stem=stem, author=author, title=title, query=query)


@dataclass
class Book:
    stem: str
    #: Extension (with dot, lowercased) to absolute path.
    formats: dict[str, str] = field(default_factory=dict)

    @property
    def epub(self) -> str | None:
        return self.formats.get('.epub')

    @property
    def pdf(self) -> str | None:
        return self.formats.get('.pdf')

    @property
    def any_path(self) -> str | None:
        """A path to read existing metadata from, preferring the richer EPUB."""
        return self.epub or self.pdf

    def facts(self) -> FilenameFacts:
        return parse_filename(self.stem)


def walk(root: str | None = None) -> dict[str, Book]:
    """Group every book file under ``root`` by filename stem.

    Note the stem is the basename only, so two identically named files in
    different category folders collapse into one entry. That matches the original
    behaviour and has not bitten this library, but it is a real limitation.
    """
    root = root or LIBRARY
    found: dict[str, Book] = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            stem, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in BOOK_EXTENSIONS:
                continue
            found.setdefault(stem, Book(stem=stem)).formats[ext] = os.path.join(dirpath, name)
    return found


def books(root: str | None = None) -> list[Book]:
    """Every stem, sorted. Includes stems with only one format."""
    return [book for _, book in sorted(walk(root).items())]


def pairs(root: str | None = None) -> list[Book]:
    """Only stems that have both an EPUB and a PDF."""
    return [b for b in books(root) if b.epub and b.pdf]
