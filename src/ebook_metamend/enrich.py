"""The enrichment pipeline: query, score, decide, optionally write.

Returns values. Nothing here prints, so the decisions can be tested offline and
the CLI owns presentation.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from . import calibre, matching, tags
from .library import Book, books
from .sources import SOURCES, Pacer, cache
from .sources.calibre_plugin import SourceUnavailable

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


#: Sources that could not be reached at all, as opposed to having no answer.
#: Collected across a run so it can be reported once rather than per book.
unavailable_sources: dict[str, str] = {}

#: Shared across a run so back-off carries between books. Reset by run().
_pacer = Pacer()


def reset_run_state() -> None:
    """Forget what the last run learned.

    Module state that survives between runs means a source that was unavailable
    once is never retried, and back-off from a previous run still applies. Fine
    for a single CLI invocation, wrong for anything longer lived.
    """
    global _pacer
    unavailable_sources.clear()
    _pacer = Pacer()


def query_sources(title: str, author: str, *, pause: bool = True) -> dict[str, dict[str, Any]]:
    """Ask every source about one book. Sources with no answer are omitted.

    A source that cannot run at all is recorded separately. Folding it in with
    "no answer" is how a missing plugin stayed invisible while it silently
    reduced a three-source cross-check to a single source.
    """
    answers: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        if source.name in unavailable_sources:
            continue
        try:
            answer = source.fetch(title, author)
        except SourceUnavailable as exc:
            unavailable_sources[source.name] = str(exc)
            continue
        if answer:
            answers[source.name] = answer
        _pacer.record(source.name, bool(answer))
        if pause and not cache.replaying():
            time.sleep(_pacer.delay(source))
    return answers


def score(answers: dict[str, dict[str, Any]], facts) -> tuple[list[matching.SourceScore], str]:
    """Score each source's answer on its own, then classify the set.

    Scoring per source rather than taking the best title and the best author
    across all of them is the point: those maxima can come from two different
    answers, neither of which identified the book.
    """
    scores = [
        matching.SourceScore(
            name=name,
            title=answer.get('title', ''),
            title_score=matching.sim(answer.get('title', ''), facts.title),
            author_score=matching.best_author_score([answer.get('authors') or []], facts.author),
        )
        for name, answer in answers.items()
    ]
    return scores, matching.classify(scores)


def merge(answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combine surviving answers into one candidate record.

    Longest wins for free text, first non-empty for identifiers. Tags are the
    union, because sources cover different vocabularies.
    """
    values = list(answers.values())

    # Longest-wins is right for subtitles and wrong for adaptations: "On Liberty
    # (Squashed Edition)" is longer than "On Liberty", so a plain max() picks the
    # abridgement over the real book even when another source got it right.
    # Prefer titles that are not derived works, and only fall back if every
    # source offered one.
    titles = [a['title'] for a in values if a.get('title')]
    genuine = [t for t in titles if not matching.looks_derived(t)]
    return {
        'title': max(genuine or titles, key=len, default=''),
        'tags': tags.clean(sorted({t for a in values for t in (a.get('tags') or [])}))[
            :MAX_MERGED_TAGS
        ],
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

    scores, conf = score(answers, facts)
    # Reported figures stay the best-of, so the output still reads as one number
    # per book, but they no longer decide anything.
    title_score = max((s.title_score for s in scores), default=0.0)
    author_score = max((s.author_score for s in scores), default=0.0)

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
    current = calibre.read_book_metadata(book.any_path)
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
    reset_run_state()
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
