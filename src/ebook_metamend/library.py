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

#: "Series Name - 02.5 - Book Title". The number is the boundary: everything
#: before it names the series, everything after it is the book's own title.
_SERIES_PART = re.compile(r'^(?P<series>.+?)\s*-\s*(?P<index>\d+(?:\.\d+)?)\s*-\s*(?P<title>.+)$')
#: Where a search query should stop: a subtitle separator or a parenthesis.
_QUERY_TAIL = re.compile(r'\s+-\s+|\s*:\s*|\s*\(')


@dataclass(frozen=True)
class FilenameFacts:
    """What the filename asserts. Treated as ground truth: it is the one piece of
    metadata a human curated, so online sources are scored against it."""

    stem: str
    author: str
    #: The book's own title, without the series name or its number.
    title: str
    #: Shortened form used to query sources, which do badly with long subtitles.
    query: str
    #: The series named in the filename, if it names one.
    series: str | None = None
    #: Its position in that series, as written.
    series_index: str | None = None


def parse_filename(stem: str) -> FilenameFacts:
    """Split "Author - Series - 02 - Title" into the parts that mean something.

    The series is kept apart from the title rather than folded into it. Glued
    together they read "The Ravenhood Flock", which no catalogue has ever
    returned, so every book named this way scored 0.69 on the title and could
    never reach HIGH however exactly the sources agreed. Roughly one book in ten
    here is named that way.
    """
    author, _, rest = stem.partition(' - ')
    series = index = None
    match = _SERIES_PART.match(rest)
    if match:
        series = match.group('series').strip()
        index = match.group('index')
        rest = match.group('title')
    title = rest.strip()
    query = _QUERY_TAIL.split(title)[0].strip() or title
    return FilenameFacts(
        stem=stem, author=author, title=title, query=query, series=series, series_index=index
    )


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
    """Group every book file under ``root``, keyed by its root-relative stem.

    Keying on the full relative path rather than the basename matters: two books
    with the same filename in different category folders are different books. A
    basename key silently merges them, which can pair one book's EPUB with
    another's PDF and write metadata to the wrong file.
    """
    root = root or LIBRARY
    found: dict[str, Book] = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            stem, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in BOOK_EXTENSIONS:
                continue
            path = os.path.join(dirpath, name)
            key = os.path.join(os.path.relpath(dirpath, root), stem)
            found.setdefault(key, Book(stem=stem)).formats[ext] = path
    return found


def books(root: str | None = None) -> list[Book]:
    """Every book, ordered by filename. Includes books with only one format."""
    # Sorted by basename, not by the relative key, so ordering does not depend on
    # which category folder a book happens to live in.
    return sorted(walk(root).values(), key=lambda b: b.stem)


def pairs(root: str | None = None) -> list[Book]:
    """Only stems that have both an EPUB and a PDF."""
    return [b for b in books(root) if b.epub and b.pdf]
