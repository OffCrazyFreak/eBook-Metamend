"""The enrichment pipeline: query, score, decide, optionally write.

Returns values. Nothing here prints, so the decisions can be tested offline and
the CLI owns presentation.
"""

from __future__ import annotations

import functools
import re
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from . import calibre, matching, tags
from .library import Book, FilenameFacts, books
from .sources import SOURCES, Pacer, Source, cache
from .sources.errors import SourceError, SourceUnavailable
from .writers import epub, pdf

#: Sources disagreeing with the filename by more than this are dropped before
#: merging, so a hallucinated match cannot contribute fields.
HALLUCINATION_FLOOR = matching.TITLE_WEAK
#: Merged tag lists get long and unranked. Only the head is useful.
MAX_MERGED_TAGS = 12
#: A source that fails this many books in a row is shelved for the rest of the
#: run. Backing off is right for a source having a bad minute, but wrong for one
#: whose network path is simply broken: measured on this machine, Open Library
#: failed its TLS handshake on every book and charged the full timeout for each,
#: which was the largest single cost in a run and never produced an answer.
MAX_CONSECUTIVE_FAILURES = 3


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
    #: Every source's score, including the ones that earned no say. Reporting only.
    scores: list[matching.SourceScore] = field(default_factory=list, repr=False)
    #: The reading of the filename the verdict was scored against. Reporting only.
    facts: FilenameFacts | None = field(default=None, repr=False)

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
#: Consecutive transport failures per source, for the shelving rule above.
_failures: dict[str, int] = {}


def reset_run_state() -> None:
    """Forget what the last run learned.

    Module state that survives between runs means a source that was unavailable
    once is never retried, and back-off from a previous run still applies. Fine
    for a single CLI invocation, wrong for anything longer lived.
    """
    global _pacer
    unavailable_sources.clear()
    _failures.clear()
    _pacer = Pacer()


def query_sources(
    title: str,
    author: str,
    *,
    pause: bool = True,
    sources: tuple[Source, ...] | None = None,
    on_answer: Callable[[str, bool], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Ask every source about one book. Sources with no answer are omitted.

    ``on_answer`` hears each source as it replies (name, whether it had the
    book), which is how a progress display keeps up with a run it cannot see.

    A source that cannot run at all is recorded separately. Folding it in with
    "no answer" is how a missing plugin stayed invisible while it silently
    reduced a three-source cross-check to a single source.
    """
    answers: dict[str, dict[str, Any]] = {}
    for source in SOURCES if sources is None else sources:
        if source.name in unavailable_sources:
            continue
        try:
            answer = source.fetch(title, author)
        except SourceUnavailable as exc:
            unavailable_sources[source.name] = str(exc)
            continue
        except SourceError as exc:
            # Transient, so back off and keep asking. Unless it keeps happening,
            # in which case it is not transient and every further attempt is a
            # timeout charged to the user for nothing.
            print(f'{source.name}: {exc}', file=sys.stderr)
            _pacer.record(source.name, answered=False)
            _failures[source.name] = _failures.get(source.name, 0) + 1
            if _failures[source.name] >= MAX_CONSECUTIVE_FAILURES:
                unavailable_sources[source.name] = (
                    f'failed {_failures[source.name]} books in a row, last error: {exc}'
                )
            answer = None
        else:
            # Having no entry for a book is not a failure. Google misses by
            # design, and treating that as rate-limiting used to escalate its
            # pause to the ceiling and keep it there.
            _failures[source.name] = 0
            _pacer.record(source.name, answered=True)

        if answer:
            answers[source.name] = answer
        if on_answer is not None:
            on_answer(source.name, bool(answer))
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
            author_score=matching.best_author_score(answer.get('authors') or [], facts.author),
        )
        for name, answer in answers.items()
    ]
    return scores, matching.classify(scores)


def trusted_names(scores: list[matching.SourceScore]) -> list[str]:
    """Which sources may contribute metadata, not merely confidence.

    The answers that earn the confidence are the answers that supply the fields.
    Returning every *strong* source was not enough: strength is measured against
    the filename alone, so a sequel whose title extends the real one scores 0.95
    and is strong while agreeing with nobody. Measured live, that let Open
    Library write "Foundation and Empire", and its ISBN, onto "Foundation" at
    HIGH with no override.

    So when a pair has agreed, only the members of that agreement may
    contribute. Weaker sources get a say only when none is strong, and a
    recognised adaptation never does, even if it is the only answer there is.
    """
    strong = [s for s in scores if s.strong]
    agreeing = [
        one.name
        for index, one in enumerate(strong)
        if any(
            matching.sim(one.title, other.title) >= matching.CROSS_SOURCE_AGREE
            for position, other in enumerate(strong)
            if position != index
        )
    ]
    if agreeing:
        return agreeing
    if strong:
        return [s.name for s in strong]
    # No fallback to "everything". When every answer is a recognised adaptation
    # this is empty, nothing is merged and nothing is proposed, which is the
    # correct outcome: an abridgement's ISBN and publisher are not the book's.
    # Comparison matches classify(), which uses >= on the same constant.
    return [
        s.name
        for s in scores
        if s.title_score >= HALLUCINATION_FLOOR and not matching.looks_derived(s.title)
    ]


def reported_scores(scores: list[matching.SourceScore], trusted: list[str]) -> tuple[float, float]:
    """The one title and one author figure printed for a book.

    They decide nothing; ``classify`` works per source. They are read next to the
    source list, so they come from the same answers: the best of the trusted set.
    Taken over every answer, a sequel that scored 0.95 and was then excluded for
    agreeing with nobody still printed as ``fn=0.95`` beside sources it was not
    among.

    The trusted set is used only when it holds a strong source, because then it
    is the set that earned the verdict. Otherwise every answer counts: a
    recognised adaptation can earn MED on its author alone while being barred
    from contributing, and figures taken from the weak survivors would print
    ``MED au=0.00``; and when nothing survives at all, a rejected book still
    shows how close it came rather than ``0.00``.
    """
    pool = [s for s in scores if s.name in trusted]
    if not any(s.strong for s in pool):
        pool = scores
    return (
        max((s.title_score for s in pool), default=0.0),
        max((s.author_score for s in pool), default=0.0),
    )


def _ranked_tags(answers: list[dict[str, Any]]) -> list[str]:
    """Tags most sources agreed on first, then first seen.

    Sorting alphabetically and taking the first twelve took an alphabetical
    head, not a useful one: Dewey and Library of Congress call numbers sort
    early and were written as subjects, while the real headings were cut.
    """
    votes: dict[str, int] = {}
    order: dict[str, int] = {}
    for position, answer in enumerate(answers):
        for tag in answer.get('tags') or []:
            key = tag.strip()
            if not key:
                continue
            votes[key] = votes.get(key, 0) + 1
            order.setdefault(key, position * 1000 + len(order))
    return sorted(votes, key=lambda t: (-votes[t], order[t]))


#: Where a subtitle begins: a colon, or a dash with space either side. The
#: spaces matter, or "Twenty-One" splits.
_SUBTITLE_BREAK = re.compile(r':\s*|\s+[-\u2013\u2014]\s+')


def _adds_only_a_subtitle(core: str, longer: str) -> bool:
    """True when ``longer`` is ``core`` plus a subtitle, not a longer title.

    This is the whole difference between an improvement and a different book,
    and length cannot tell them apart. Measured on this library, Kobo answered
    "Essentialism" and Google answered "The Essentialism Planner: A 90-Day Guide
    to Accomplishing More by Doing Less", a separate companion volume. Both name
    the real author, both are strong, and a planner is a legitimate prefix, so
    it agreed, reached HIGH and won on length.

    Splitting at the subtitle separator tells them apart: "Sapiens" is the head
    of "Sapiens: A Brief History of Humankind", but "Essentialism" is not the
    head of "The Essentialism Planner", because "Planner" is title, not subtitle.
    """
    if not matching.norm(core) or matching.norm(longer) == matching.norm(core):
        return False
    head = _SUBTITLE_BREAK.split(longer, 1)[0]
    return matching.norm(head) == matching.norm(core)


def _best_title(titles: list[str], filename_title: str) -> str:
    """The answer matching the filename best, plus a subtitle if one is offered.

    The filename is the ground truth everywhere else in this tool, so it decides
    here too. Preferring the longest answer instead is what let a sequel and a
    companion volume be written over the book itself.

    Derived works are dropped first, unless every answer is one.
    """
    genuine = [t for t in titles if not matching.looks_derived(t)] or titles
    if not genuine:
        return ''
    closest = max(matching.sim(t, filename_title) for t in genuine)
    # Shortest of the equally close. A subtitle is added back below, on evidence
    # rather than on length.
    core = min((t for t in genuine if matching.sim(t, filename_title) == closest), key=len)
    extensions = [t for t in genuine if _adds_only_a_subtitle(core, t)]
    return max(extensions, key=len) if extensions else core


def merge(
    answers: dict[str, dict[str, Any]], author: str = '', *, filename_title: str
) -> dict[str, Any]:
    """Combine surviving answers into one candidate record.

    ``author`` is passed through to the tag cleaner, which needs it to tell a
    person's name apart from an identically shaped place-and-period heading.
    ``filename_title`` is required rather than defaulted: an empty one scores
    0.0 against every candidate, which would silently put title selection back
    on length.

    Fields are taken from two different pools on purpose:

    - **Identifiers** (ISBN, publisher, series) describe one specific edition, so
      they may only come from a source that named the winning title. Measured
      live, taking the first non-empty across every answer wrote a sequel's ISBN
      onto a book whose title had been decided correctly by the other two.
    - **Descriptions and tags** are additive and not edition-specific, so every
      trusted answer contributes.
    """
    values = list(answers.values())
    title = _best_title([a['title'] for a in values if a.get('title')], filename_title)
    # Exact after normalising, not merely similar: 0.95 similarity is precisely
    # what a sequel scores against the book it follows.
    same_book = [a for a in values if matching.norm(a.get('title')) == matching.norm(title)]

    return {
        'title': title,
        'tags': tags.clean(_ranked_tags(values), author)[:MAX_MERGED_TAGS],
        'description': max((a.get('description') or '' for a in values), key=len, default=''),
        'series': next((a['series'] for a in same_book if a.get('series')), None),
        'sidx': next((a['sidx'] for a in same_book if a.get('sidx')), None),
        'publisher': next((a['publisher'] for a in same_book if a.get('publisher')), ''),
        'isbn': next((a['isbn'] for a in same_book if a.get('isbn')), ''),
    }


_MARKUP = re.compile(r'<[^>]+>|&[#\w]+;')


def _text_length(description: str) -> int:
    """Length of the words, not the markup. Descriptions arrive as HTML from
    some sources and as text from others, and a blurb wrapped in tags is not
    longer in any sense that should replace the same blurb without them."""
    return len(' '.join(_MARKUP.sub(' ', description).split()))


def compute_gains(merged: dict[str, Any], current: dict[str, Any], conf: str) -> dict[str, Any]:
    """Only what the book is actually missing, or what is strictly better.

    Never returns a value that would blank an existing field.
    """
    gains: dict[str, Any] = {}
    # LOW means no source cleared both signals: not one of them identified the
    # book. Under --include-low it may still contribute a subject list, which is
    # additive and easy to eyeball, but not an identifier. An ISBN or publisher
    # landing in an empty field is exactly the value you will later trust.
    identified = conf != 'LOW'

    if merged['tags'] and not current.get('tags'):
        gains['tags'] = merged['tags']
    if identified and merged['series'] and not current.get('series'):
        gains['series'] = merged['series']
    if merged['description']:
        # Filling an empty description is always safe. Replacing one is not:
        # "longer" is not "better", and this is the only non-title path that can
        # destroy existing content, so it needs the same confidence the title does.
        existing = current.get('description') or ''
        if not existing:
            gains['description'] = merged['description']
        elif conf == 'HIGH' and _text_length(merged['description']) > _text_length(existing):
            gains['description'] = merged['description']
    if identified and merged['isbn'] and not current.get('isbn'):
        gains['isbn'] = merged['isbn']
    if identified and merged['publisher'] and not current.get('publisher'):
        gains['publisher'] = merged['publisher']
    # A title is filled, never traded for a longer one. Length used to decide
    # that longer meant better, and measured across the library it never did: it
    # wrote "On Liberty (Squashed Edition)" over "On Liberty", and a publisher's
    # strapline, "Flock: The Hottest, Most Addictive Enemies to Lovers Romance
    # You'll Read All Year", over the perfectly good "Flock: Ravenhood Book 1".
    # No length limit separates those from real subtitles, which run to 78
    # characters in this library while that strapline is 80. So a title that is
    # already a title is left alone, and only a missing or plainly fake one is
    # replaced.
    if conf == 'HIGH' and merged['title'] and matching.junky(current.get('title')):
        gains['title'] = merged['title']
    return gains


#: Words a subtitle tends to open with when its colon has been lost.
_SUBTITLE_STARTERS = frozenset({'the', 'a', 'an', 'how', 'why', 'what'})
#: Words a title never ends on. A starter after one of these is mid-phrase
#: ("Baby On | The Block", "Gone with | the Wind"), not a subtitle's first word.
_PHRASE_WORDS = frozenset(
    'and or of on in to for with from at by the a an into onto over under about as'.split()
)


def _head(query: str) -> str:
    """The title before a subtitle whose colon a download site dropped, or ''.

    Cut only before a word a subtitle opens with, only when a phrase follows
    it, and never mid-phrase, so "Thinking Fast and Slow", "Gone with the Wind"
    and an omnibus "A On The Block And B On The Block" are left alone while
    "Sapiens A Brief History of Humankind" becomes "Sapiens". Never the first
    word: "The Design of Everyday Things" has no subtitle.
    """
    words = query.split()
    for position, word in enumerate(words[1:], 1):
        if word.casefold() not in _SUBTITLE_STARTERS:
            continue
        # A subtitle is a phrase of its own, and the title before it does not
        # end mid-phrase. Measured: cutting "The Happiest Baby On The Block And
        # The Happiest Toddler On The Block" at "On | The" drew the single volume
        # out of Open Library, a strict prefix of the omnibus that the prefix
        # rule scores 0.95, and the two-book bundle reached HIGH on its strength.
        if len(words) - position >= 3 and words[position - 1].casefold() not in _PHRASE_WORDS:
            return ' '.join(words[:position])
    return ''


def _better_answers(
    first: dict[str, dict[str, Any]], second: dict[str, dict[str, Any]], facts
) -> dict[str, dict[str, Any]]:
    """Per source, whichever of its two answers fits the filename better."""
    merged = dict(first)
    for name, answer in second.items():
        if name not in merged:
            merged[name] = answer
            continue
        old, new = score({name: merged[name]}, facts)[0][0], score({name: answer}, facts)[0][0]
        if (new.title_score, new.author_score) > (old.title_score, old.author_score):
            merged[name] = answer
    return merged


def propose(
    book: Book,
    *,
    sources: tuple[Source, ...] | None = None,
    pause: bool = True,
    on_answer: Callable[[str, bool], None] | None = None,
) -> Proposal | None:
    """Decide what, if anything, should be written to one book.

    ``None`` means no source answered, which is a normal outcome and not a failure.
    ``pause=False`` leaves the pacing to the caller; the browser build cannot
    sleep inside Python and waits between books in JavaScript instead.
    """
    facts = book.facts()
    # A stem that names no title (a Gutenberg number, a bare ISBN) leaves nothing
    # to score against: every title score would be 0.0 against an empty string
    # and any answer at all would look equally (un)related. So do not ask.
    if not facts.query:
        return None
    ask = functools.partial(query_sources, sources=sources, pause=pause, on_answer=on_answer)
    answers = ask(facts.query, facts.author)
    scores, conf = score(answers, facts) if answers else ([], 'LOW')
    if facts.alternate is not None and not any(s.strong for s in scores):
        # Nothing identified the book as first read, and the name could be read
        # the other way round: half the tools out there write the title first.
        # The catalogues settle it. A wrong reading cannot score: a source would
        # have to name a book whose title is the author's name and whose author
        # is the title, twice over, so the bar for writing is unchanged.
        other = facts.alternate
        if other.query:
            other_answers = ask(other.query, other.author)
            other_scores, other_conf = score(other_answers, other) if other_answers else ([], 'LOW')
            if any(s.strong for s in other_scores):
                facts, answers, scores, conf = other, other_answers, other_scores, other_conf
    if conf != 'HIGH' and (head := _head(facts.query)):
        # A subtitle glued on without its colon ("Quiet Orchard The Year Of
        # Pruning", as OceanofPDF writes it) is a query Open Library answers with
        # nothing at all, measured live, while the head alone finds the book. The
        # answers are still scored against the whole filename reading; a source
        # only trades its answer for one that fits the filename better.
        answers = _better_answers(answers, ask(head, facts.author), facts)
        scores, conf = score(answers, facts) if answers else ([], 'LOW')
    if not answers:
        return None

    trusted = trusted_names(scores)
    title_score, author_score = reported_scores(scores, trusted)
    surviving = {name: answers[name] for name in trusted}

    # A failed read is not an empty book. Treating it as one makes every field
    # look missing, and --apply would then overwrite a title, publisher and tags
    # that were there all along. Propose nothing instead.
    current = calibre.read_book_metadata(book.any_path)
    unreadable = current is None
    merged = merge(surviving, facts.author, filename_title=facts.title)

    return Proposal(
        stem=book.stem,
        files=book.formats,
        conf=conf,
        sources=sorted(surviving),
        gains={} if unreadable else compute_gains(merged, current, conf),
        merged=merged,
        fn_score=round(title_score, 3),
        au_score=round(author_score, 3),
        src_titles={name: a.get('title', '') for name, a in surviving.items()},
        current=current or {},
        unreadable=unreadable,
        scores=scores,
        facts=facts,
    )


def pause_after(sources: tuple[Source, ...] | None = None) -> float:
    """How long a caller that paces itself should wait before the next book.

    The longest of the sources' current delays, so every catalogue stays under
    its own rate even though they are asked back to back.
    """
    chosen = SOURCES if sources is None else sources
    return max((_pacer.delay(s) for s in chosen), default=0.0)


WRITERS = {'.epub': epub.write, '.pdf': pdf.write}


def apply(proposal: Proposal) -> None:
    """Write the gains to every format of the book. Records the outcome."""
    if not proposal.gains:
        return
    for ext, write in WRITERS.items():
        path = proposal.files.get(ext)
        if not path:
            continue
        ok, reason = write(path, proposal.gains, proposal.merged)
        proposal.writes.append((ext, ok, reason[:60]))


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
    sources: tuple[Source, ...] | None = None,
) -> list[Proposal]:
    """Enrich the given books. Returns one proposal per book that got an answer.

    ``sources`` narrows the catalogues asked; ``None`` means all of them.
    """
    reset_run_state()
    proposals: list[Proposal] = []
    for index, book in enumerate(selected, 1):
        proposal = propose(book, sources=sources)
        if proposal is not None:
            if do_apply and proposal.gains and (proposal.conf == 'HIGH' or include_low):
                apply(proposal)
            proposals.append(proposal)
        if on_book:
            on_book(index, len(selected), book, proposal)
    return proposals
