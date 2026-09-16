"""Finding books on disk, and reading what the filename claims about them.

One walker, replacing seven copies. ``books()`` and ``pairs()` deliberately keep
their different contracts: the enricher wants every stem including single-format
ones, the EPUB-to-PDF copier only wants stems that have both.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace

from .config import LIBRARY

BOOK_EXTENSIONS = ('.epub', '.pdf')

#: "Series Name - 02.5 - Book Title". The number is the boundary: everything
#: before it names the series, everything after it is the book's own title.
_SERIES_PART = re.compile(r'^(?P<series>.+?)\s*-\s*(?P<index>\d+(?:\.\d+)?)\s*-\s*(?P<title>.+)$')
#: "[Series Name #2]" as its own segment, the shape ebook-tools writes.
_SERIES_SEGMENT = re.compile(r'^\[(?P<series>.+?)\s*#(?P<index>\d+(?:\.\d+)?)\]$')
#: "Title (Series Name Book 2)", the shape Amazon gives a title in a series.
_SERIES_SUFFIX = re.compile(r'^(?P<title>.+?)\s*\((?P<series>[^()]+?)\s+Book\s+(?P<index>\d+)\)$')
#: Where a search query should stop: a subtitle separator or a parenthesis.
_QUERY_TAIL = re.compile(r'\s+-\s+|\s*:\s*|\s*[(\[]')


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
    #: The naming scheme the stem was recognised as (see docs/filenames.md),
    #: '' for the plain "Author - Title" this tool asks for.
    scheme: str = ''
    #: The same name read the other way round, present only when nothing in the
    #: name says which side is the author. The pipeline falls back to it when no
    #: source identifies the book as first read.
    alternate: FilenameFacts | None = None


# The shapes below were measured on real download sites and library managers,
# not guessed; each rule names the scheme it exists for. docs/filenames.md has
# the sources and the examples.

#: "_OceanofPDF.com_Title_-_Author": underscores for spaces, title first.
_OCEANOFPDF = re.compile(r'^_?oceanofpdf\.com_(?P<rest>.+)$', re.I)
#: Z-Library over the years: "(z-lib.org)", "(Z-Library)", "(z-library.sk, 1lib.sk, z-lib.sk)".
_ZLIBRARY = re.compile(r'\s*\((?:z-?lib(?:rary)?\b[^)]*|1lib\b[^)]*)\)\s*$', re.I)
#: One Z-Library form glues publisher, language and ISBN on after an em dash.
_ZLIBRARY_TAIL = re.compile(r'\u2014_.*$')
#: "( PDFDrive )" and "( PDFDrive.com )", spaces inside the brackets and all.
_PDFDRIVE = re.compile(r'\s*\(\s*pdfdrive(?:\.com)?\s*\)\s*$', re.I)
#: "- libgen.li", ".-.libgen.lc", also with a duplicate counter: "libgen.lc.1".
_LIBGEN = re.compile(r'(?:\s+-\s+|\.-\.|\s+)libgen\.(?:li|lc|rs|is|st|gs)(?:\.\d+)?$', re.I)
#: "(2020)", "(2020, Manning Publications)", "[9780765333698]": trailing edition
#: facts that name the printing, not the book.
_TRAILING_YEAR = re.compile(r'\s*\((?:19|20)\d\d(?:\s*,\s*[^)]*)?\)\s*$')
_TRAILING_ISBN = re.compile(r'\s*\[(?:97[89])?\d{9}[\dXx]\]\s*$')
#: Format and quality tags from sharing channels: "(retail)", "(v5.0)", "(epub)".
_TRAILING_TAG = re.compile(
    r'(?:\s*[(\[](?:retail|v\d+(?:\.\d+)?|epub|mobi|azw3?|pdf|kindle|ebook)[)\]])+$', re.I
)
#: A browser's duplicate-download counter, "Name (1)"; also Readarr's part number.
_DUPLICATE_COUNTER = re.compile(r'\s*\((?:[1-9]|1\d)\)$')
#: Names that carry no title at all: a Project Gutenberg number, an Internet
#: Archive identifier, an ISBN, a Kindle ASIN. Reported rather than searched.
_NO_TITLE = (
    ('gutenberg', re.compile(r'^pg\d+(?:-images)?(?:-\d)?$', re.I)),
    ('internet-archive', re.compile(r'^[a-z0-9]+0000[a-z]{4}(?:_[a-z]+)?$')),
    ('isbn', re.compile(r'^(?:97[89][- ]?)?\d(?:[- ]?\d){8}[- ]?[\dXx]$')),
    ('kindle', re.compile(r'^B0[A-Z0-9]{8}_EBOK$')),
)
#: Springer: "2020_Book_IntroductionToScientificProgra", CamelCase and cut short.
_SPRINGER = re.compile(r'^(?:19|20)\d\d_Book_(?P<title>[A-Za-z0-9]+)$')
_CAMEL_BOUNDARY = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
#: Slug tails that identify a listing rather than the book: ISBNs and record ids
#: (dokumen.pub, vdoc.pub), "1nbsped" for "1st ed.", the format the site served.
_SLUG_ID = re.compile(r'^(?:\d{7,}|(?=.*\d)[a-z0-9]{10,}|\d*nbsped|pdf|epub)$')
#: Separators other tools write between the same two halves.
_OTHER_SEPARATORS = re.compile(r'\s+(?:--|\u2013|\u2014|_)\s+')
#: A comma-first person, "Zimmermann, Reinhard", as opposed to "Smith, Jr.".
_NAME_SUFFIXES = frozenset({'jr', 'sr', 'ii', 'iii', 'iv', 'phd', 'md', 'esq'})
#: Words that make a segment read as a title rather than a person.
_TITLE_WORDS = frozenset(
    'the a an of to in for on from at by how why what your you my is are '
    'guide edition handbook introduction book vol volume'.split()
)
#: How a filename names several authors; commas are absent, "Smith, Jr." is one person.
_CO_AUTHORS = re.compile(r'\s+(?:and|&)\s+')
_LOWER_NAME_PARTS = frozenset(
    {'van', 'von', 'de', 'da', 'del', 'di', 'la', 'le', 'du', 'der', 'den'}
)


def _person_first(author: str) -> str:
    """ "Last, First" written the way the catalogues answer, "First Last".

    Only the one-comma, short shape is turned round. "Smith, Jr." keeps its
    comma, and so does anything long enough to be a list rather than a person.
    """
    author = re.sub(r'\s+(?:etc\.?|et al\.?)$', '', author.strip(), flags=re.I)
    if author.count(',') != 1:
        return author
    last, first = (part.strip() for part in author.split(','))
    if not last or not first or first.rstrip('.').casefold() in _NAME_SUFFIXES:
        return author
    if len(last.split()) > 2 or len(first.split()) > 3:
        return author
    return f'{first} {last}'


def _name_likeness(segment: str) -> int:
    """How much a segment reads like a person's name rather than a title.

    A rough score, used only to pick which reading of "A - B" to try first; the
    sources decide in the end. Two or three capitalised words, an initial, no
    digits and no punctuation is what a name looks like on disk.
    """
    halves = _CO_AUTHORS.split(segment)
    if len(halves) in (2, 3) and all(1 < len(h.split()) < 4 and h[:1].isupper() for h in halves):
        # "Colin Bryar and Bill Carr": two names, not a five-word title.
        return 4
    words = segment.split()
    score = 0
    if len(words) in (2, 3):
        score += 2
    elif len(words) > 4:
        score -= 2
    if re.search(r'\b[A-Z]\.', segment):
        score += 2
    if re.search(r'\d', segment):
        score -= 3
    if re.search(r'[:?!]', segment):
        score -= 3
    lowered = {w.strip(".,'\"").casefold() for w in words}
    if len(words) > 1 and lowered & _TITLE_WORDS:
        score -= 2
    if lowered & _NAME_SUFFIXES:
        score += 1
    if words and all(w[:1].isupper() or w.casefold() in _LOWER_NAME_PARTS for w in words):
        score += 1
    else:
        score -= 1
    return score


def _split(text: str) -> list[str]:
    return [part.strip() for part in text.split(' - ') if part.strip()]


def _words(slug: str) -> str:
    return ' '.join(w.capitalize() for w in slug.split('-') if w)


def _read(stem: str) -> tuple[list[str], str, str | None]:
    """Undo what a download site or library manager did to the name.

    Returns the name's segments, the scheme recognised, and which side is the
    author when the scheme says so ('author-first', 'title-first') or None when
    the segments could be read either way.
    """
    s = stem.strip()
    # Kobo's "Title.kepub.epub" leaves ".kepub" on the stem.
    s = re.sub(r'\.kepub$', '', s, flags=re.I)
    s = _DUPLICATE_COUNTER.sub('', s)

    for scheme, pattern in _NO_TITLE:
        if pattern.match(s):
            return [], scheme, None
    match = _SPRINGER.match(s)
    if match:
        return [_CAMEL_BOUNDARY.sub(' ', match.group('title'))], 'springer', 'title-first'

    match = _OCEANOFPDF.match(s)
    if match:
        text = match.group('rest').replace('_-_', ' - ')
        # A dropped colon leaves a double underscore, so the subtitle boundary survives.
        text = re.sub(r'(?<=\w)__(?=\w)', ': ', text).replace('_', ' ')
        return _split(text), 'oceanofpdf', 'title-first'

    if ' -- ' in s:
        parts = [p.strip() for p in s.split(' -- ')]
        if re.search(r"anna.s\s+archive", parts[-1], re.I):
            parts.pop()
            parts = [p.replace('_', '.') for p in parts if not re.fullmatch(r'[0-9a-f]{32}', p)]
            title = parts[0] if parts else ''
            # The author is the second field only if there was one: the site drops
            # empty fields, so an edition or a publisher can move up into its place.
            author = parts[1] if len(parts) > 1 else ''
            if re.search(r'\b(?:19|20)\d\d\b|\bed(?:ition|\.)', author, re.I):
                author = ''
            return [title, author], 'annas-archive', 'title-first'

    if _ZLIBRARY.search(s):
        s = _ZLIBRARY_TAIL.sub('', _ZLIBRARY.sub('', s))
        # A dropped colon leaves two spaces behind, so the subtitle boundary survives.
        s = re.sub(r'(?<=\S)  (?=\S)', ': ', s).strip()
        match = re.match(r'^(?P<title>.+?)\s+\((?P<author>[^()]+)\)$', s)
        if match and not re.search(r'\d|\bed(?:ition|\.)', match.group('author'), re.I):
            return (
                [match.group('title'), _person_first(match.group('author'))],
                'z-library',
                'title-first',
            )
        if ' by ' in s:
            title, _, author = s.rpartition(' by ')
            return [title, _person_first(author)], 'z-library', 'title-first'
        return [s], 'z-library', 'title-first'

    scheme, order = '', None
    if _PDFDRIVE.search(s):
        s, scheme, order = _PDFDRIVE.sub('', s), 'pdfdrive', 'title-first'
    if _LIBGEN.search(s):
        s, scheme, order = _LIBGEN.sub('', s), 'libgen', 'author-first'

    if ' ' not in s and s.count('.') >= 3:
        # Scene and dotted libgen names: "Author.Name.-.Title.Of.Book.2021.RETAIL.EPUB.eBook-GRP".
        s = s.replace('.-.', ' - ').replace('.', ' ')
        parts = _split(s)
        if parts:
            trimmed = re.sub(r'\s+(?:19|20)\d\d(?:\s+.*)?$', '', parts[-1])
            parts[-1] = trimmed or parts[-1]
        return parts, scheme or 'dotted', order or 'author-first'

    if ' ' not in s and '-' in s and s == s.lower():
        # Slugs: "author-name_title-of-book" (Standard Ebooks), "title-of-book-9780000000000" (dokumen.pub).
        s = re.sub(r'^epdf-pub-', '', s)
        s = re.sub(r'_advanced$', '', s)
        if s.count('_') == 1 and all('-' in half or half.isalpha() for half in s.split('_')):
            author, title = s.split('_')
            return [_words(author), _words(title)], 'slug', 'author-first'
        tokens = s.split('-')
        while tokens and _SLUG_ID.match(tokens[-1]):
            tokens.pop()
        return [_words('-'.join(tokens))] if tokens else [], 'slug', 'title-first'

    if ' ' not in s and '_' in s:
        s = s.replace('_', ' ')
    s = _OTHER_SEPARATORS.sub(' - ', s)
    # libgen and PDFDrive write "_ " where the title had ": ".
    s = re.sub(r'_\s', ': ', s).replace('_', ' ')
    # Scribd: "Title | PDF | Topic".
    s = s.split(' | ', 1)[0]
    s = _TRAILING_TAG.sub('', s)
    s = _TRAILING_ISBN.sub('', s)
    s = _TRAILING_YEAR.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip(' -')

    if ' - ' not in s and ' by ' in s:
        title, _, author = s.rpartition(' by ')
        return [title, author], scheme or 'title-by-author', 'title-first'
    return _split(s), scheme, order


def _facts(stem: str, author: str, rest: str, scheme: str) -> FilenameFacts:
    series = index = None
    match = _SERIES_PART.match(rest)
    if match:
        series = match.group('series').strip()
        index = match.group('index')
        rest = match.group('title')
    title = rest.strip()
    match = _SERIES_SUFFIX.match(title)
    if match and series is None:
        series, index, title = match.group('series'), match.group('index'), match.group('title')
    query = _QUERY_TAIL.split(title)[0].strip() or title
    return FilenameFacts(
        stem=stem,
        author=_person_first(author),
        title=title,
        query=query,
        series=series,
        series_index=index,
        scheme=scheme,
    )


def _author_first(stem: str, parts: list[str], scheme: str) -> FilenameFacts:
    author, rest = parts[0], parts[1:]
    series = index = None
    if rest and (match := _SERIES_SEGMENT.match(rest[0])):
        series, index, rest = match.group('series'), match.group('index'), rest[1:]
    facts = _facts(stem, author, ' - '.join(rest), scheme)
    if series is not None and facts.series is None:
        facts = replace(facts, series=series, series_index=index)
    return facts


def _title_first(stem: str, parts: list[str], scheme: str) -> FilenameFacts:
    return _facts(stem, parts[-1], ' - '.join(parts[:-1]), scheme or 'title-first')


def parse_filename(stem: str) -> FilenameFacts:
    """Read "Author - Title" out of a stem, however a download site mangled it.

    "Author - Series - 02 - Title" keeps the series apart from the title rather
    than folding it in. Glued together they read "The Ravenhood Flock", which no
    catalogue has ever returned, so every book named this way scored 0.69 on the
    title and could never reach HIGH however exactly the sources agreed.

    Half the tools out there write the title first (Calibre, Calibre-Web,
    LazyLibrarian, Anna's Archive, Z-Library, OceanofPDF) and half the author
    first (this tool, Readarr, libgen, the sharing channels). Where the scheme is
    recognisable the order is known. A plain "A - B" is read author first, as
    the README asks, unless B reads more like a person than A; the other reading
    travels along as ``alternate`` for the pipeline to try when the first finds
    nothing, so the catalogues settle it rather than a guess.
    """
    parts, scheme, order = _read(stem)
    if not parts:
        return FilenameFacts(stem=stem, author='', title='', query='', scheme=scheme)
    if len(parts) == 1:
        # A title and nobody's name: nothing for a source's author to be scored
        # against, so it can never reach HIGH, but it is still worth reporting.
        return _facts(stem, '', parts[0], scheme)
    if scheme == 'title-by-author':
        # "Death by Black Hole" is a title with nobody's name in it.
        whole = _facts(stem, '', ' by '.join(parts), '')
        return replace(_title_first(stem, parts, scheme), alternate=whole)
    if order == 'title-first':
        return _title_first(stem, parts, scheme)
    if order == 'author-first':
        return _author_first(stem, parts, scheme)
    author_first = _author_first(stem, parts, scheme)
    if author_first.series is not None:
        # "Author - Series - 02 - Title" is this tool's own convention; no other reading fits.
        return author_first
    head, tail = _name_likeness(parts[0]), _name_likeness(parts[-1])
    # The other reading travels along only when the half it would make the
    # author could be a person at all; a subtitle or a product name cannot, and
    # asking the catalogues about it would cost a round for nothing.
    if tail > head:
        other = author_first if head >= 0 else None
        return replace(_title_first(stem, parts, scheme), alternate=other)
    other = _title_first(stem, parts, scheme) if tail >= 0 else None
    return replace(author_first, alternate=other)


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
