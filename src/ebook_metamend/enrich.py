"""The enrichment pipeline: query, score, decide, optionally write.

Returns values. Nothing here prints, so the decisions can be tested offline and
the CLI owns presentation.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from . import calibre, matching
from .library import Book, books
from .sources import SOURCES, cache

#: A merged title has to beat the existing one by more than this to be worth
#: writing. Stops churn on trivially different punctuation.
TITLE_IMPROVEMENT_MARGIN = 3
#: Sources disagreeing with the filename by more than this are dropped before
#: merging, so a hallucinated match cannot contribute fields.
HALLUCINATION_FLOOR = matching.TITLE_WEAK
#: Merged tag lists get long and unranked. Only the head is useful.
MAX_MERGED_TAGS = 12


@dataclass
class Proposal:
    """What was decided for one book, and why.

    Field order is the serialisation order of the proposals JSON.
    """

    stem: str
    files: dict[str, str]
    conf: str
    sources: list[str]
    gains: dict[str, Any]
    merged: dict[str, Any]
    fn_score: float
    au_score: float
    src_titles: dict[str, str]
    #: The book's existing metadata. Kept for reporting, not serialised.
    current: dict[str, Any] = field(default_factory=dict, repr=False)
    #: True when the existing metadata could not be read, so nothing is proposed.
    unreadable: bool = field(default=False, repr=False)
    #: Populated only when a write was attempted. Not serialised.
    writes: list[tuple[str, bool, str]] = field(default_factory=list, repr=False)

    @property
    def applicable(self) -> bool:
        return bool(self.gains)

    def to_dict(self) -> dict[str, Any]:
        """The serialised form. Explicit rather than ``asdict`` so that adding a
        reporting field can never change the on-disk record."""
        return {
            'stem': self.stem,
            'files': self.files,
            'conf': self.conf,
            'sources': self.sources,
            'gains': self.gains,
            'merged': self.merged,
            'fn_score': self.fn_score,
            'au_score': self.au_score,
            'src_titles': self.src_titles,
        }


def query_sources(title: str, author: str, *, pause: bool = True) -> dict[str, dict[str, Any]]:
    """Ask every source about one book. Absent and failed sources are omitted."""
    answers: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        answer = source.fetch(title, author)
        if answer:
            answers[source.name] = answer
        if pause and not cache.replaying():
            time.sleep(source.pause)
    return answers


def score(answers: dict[str, dict[str, Any]], facts) -> tuple[float, float, str]:
    """Score every answer against the filename, and classify the result."""
    titles = [a['title'] for a in answers.values() if a.get('title')]
    title_score = matching.best_title_score(titles, facts.title)
    author_score = matching.best_author_score(
        [a.get('authors') or [] for a in answers.values()], facts.author
    )
    agreements = matching.count_agreements(titles)
    return title_score, author_score, matching.classify(title_score, author_score, agreements)


def merge(answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combine surviving answers into one candidate record.

    Longest wins for free text, first non-empty for identifiers. Tags are the
    union, because sources cover different vocabularies.
    """
    values = list(answers.values())
    return {
        'title': max((a['title'] for a in values), key=len, default=''),
        'tags': sorted({t for a in values for t in (a.get('tags') or [])})[:MAX_MERGED_TAGS],
        'description': max((a.get('description') or '' for a in values), key=len, default=''),
        'series': next((a['series'] for a in values if a.get('series')), None),
        'sidx': next((a['sidx'] for a in values if a.get('sidx')), None),
        'publisher': next((a['publisher'] for a in values if a.get('publisher')), ''),
        'isbn': next((a['isbn'] for a in values if a.get('isbn')), ''),
    }


def compute_gains(merged: dict[str, Any], current: dict[str, Any], conf: str) -> dict[str, Any]:
    """Only what the book is actually missing, or what is strictly better.

    Never returns a value that would blank an existing field.
    """
    gains: dict[str, Any] = {}
    if merged['tags'] and not current.get('tags'):
        gains['tags'] = merged['tags']
    if merged['series'] and not current.get('series'):
        gains['series'] = merged['series']
    if merged['description'] and len(merged['description']) > len(current.get('description') or ''):
        gains['description'] = merged['description']
    if merged['isbn'] and not current.get('isbn'):
        gains['isbn'] = merged['isbn']
    if merged['publisher'] and not current.get('publisher'):
        gains['publisher'] = merged['publisher']
    if (
        conf == 'HIGH'
        and merged['title']
        and len(merged['title']) > len(current.get('title') or '') + TITLE_IMPROVEMENT_MARGIN
    ):
        gains['title'] = merged['title']
    return gains


def build_write_args(gains: dict[str, Any], merged: dict[str, Any]) -> list[str]:
    """Turn gains into ebook-meta arguments."""
    args: list[str] = []
    if 'title' in gains:
        args += ['-t', gains['title']]
    if 'tags' in gains:
        args += ['--tags', calibre.TAG_SEPARATOR.join(gains['tags'])]
    if 'description' in gains:
        args += ['-c', gains['description']]
    if 'publisher' in gains:
        args += ['--publisher', gains['publisher']]
    if 'isbn' in gains:
        args += ['--isbn', gains['isbn']]
    if 'series' in gains:
        args += ['-s', gains['series']]
        if merged.get('sidx'):
            args += ['-i', str(merged['sidx'])]
    return args


def propose(book: Book) -> Proposal | None:
    """Decide what, if anything, should be written to one book.

    ``None`` means no source answered, which is a normal outcome and not a failure.
    """
    facts = book.facts()
    answers = query_sources(facts.query, facts.author)
    if not answers:
        return None

    title_score, author_score, conf = score(answers, facts)

    # Drop sources whose title does not resemble the filename, so a hallucinated
    # match cannot contribute fields. Falls back to the unfiltered set rather
    # than merging nothing.
    surviving = {
        name: a
        for name, a in answers.items()
        if matching.sim(a.get('title', ''), facts.title) >= HALLUCINATION_FLOOR
    } or answers

    # A failed read is not an empty book. Treating it as one makes every field
    # look missing, and --apply would then overwrite a title, publisher and tags
    # that were there all along. Propose nothing instead.
    current = calibre.read_metadata(book.any_path)
    unreadable = current is None
    merged = merge(surviving)

    return Proposal(
        stem=book.stem,
        files=book.formats,
        conf=conf,
        sources=sorted(surviving),
        gains={} if unreadable else compute_gains(merged, current, conf),
        merged=merged,
        fn_score=round(title_score, 3),
        au_score=round(author_score, 3),
        src_titles={name: a['title'] for name, a in surviving.items()},
        current=current or {},
        unreadable=unreadable,
    )


def apply(proposal: Proposal) -> None:
    """Write the gains to every format of the book. Records the outcome."""
    args = build_write_args(proposal.gains, proposal.merged)
    if not args:
        return
    for ext in ('.epub', '.pdf'):
        path = proposal.files.get(ext)
        if not path:
            continue
        ok, stderr = calibre.write_metadata(path, args)
        proposal.writes.append((ext, ok, stderr[:60]))


def select(
    *, match: str = '', limit: int = 0, start: int = 0, root: str | None = None
) -> list[Book]:
    """The books a run will visit. Separate so the caller can count them first."""
    selected: Iterable[Book] = books(root)
    if match:
        selected = [b for b in selected if match.lower() in b.stem.lower()]
    selected = list(selected)[start:]
    return selected[:limit] if limit else selected


def run(
    selected: list[Book],
    *,
    do_apply: bool = False,
    include_low: bool = False,
    on_book: Callable[[int, int, Book, Proposal | None], None] | None = None,
) -> list[Proposal]:
    """Enrich the given books. Returns one proposal per book that got an answer."""
    proposals: list[Proposal] = []
    for index, book in enumerate(selected, 1):
        proposal = propose(book)
        if proposal is not None:
            if do_apply and proposal.gains and (proposal.conf == 'HIGH' or include_low):
                apply(proposal)
            proposals.append(proposal)
        if on_book:
            on_book(index, len(selected), book, proposal)
    return proposals
