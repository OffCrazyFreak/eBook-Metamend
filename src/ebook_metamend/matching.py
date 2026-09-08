"""Title and author similarity, and the confidence decision.

This is the safety model. It decides whether a metadata source is trusted enough
to write to a file you cannot easily replace, so it is deliberately small, pure
and heavily tested.

It previously existed in four copies (the enricher plus three test scripts), which
meant the validation suite scored a stale duplicate rather than the real thing.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Scoring thresholds. Named because they were repeated as bare numbers in four
# files, so nudging one never propagated to the others.
TITLE_STRONG = 0.85  # title matches the filename well enough to trust
AUTHOR_STRONG = 0.70  # author agrees with the filename's author
TITLE_WEAK = 0.60  # weakest title score still worth reporting
CROSS_SOURCE_AGREE = 0.75  # two sources are talking about the same book

#: A shorter title that is a *prefix* of a longer one is the same book, listed
#: with and without its subtitle.
PREFIX_SCORE = 0.95
#: Contained but not a prefix. An omnibus contains the title of a volume it is
#: not, so this is capped below TITLE_STRONG and can never be written.
CONTAINED_SCORE = 0.70
#: An adaptation is a different book that shares a title. Capped below
#: TITLE_STRONG so it can never be written over the real edition.
ADAPTATION_SCORE = 0.60

#: Titles that describe a derived work rather than the book itself. Measured
#: failures, not guesses: a search for "On Liberty" returned "On Liberty
#: (Squashed Edition)", and one for "Atomic Habits" returned "Atomic Habits
#: (Tamil)". Both would have overwritten a correct title.
_ADAPTATION_MARKERS = re.compile(
    r'\b('
    r'abridge\w*|squashed|condensed|'
    r'graphic\s+novel|illustrated\s+adaptation|'
    r'adapted\s+for|young\s+(?:readers?|adults?)\s+edition|'
    r'summary|summaries|workbook|study\s+guide|'
    r'box(?:ed)?\s+set|'
    r'in\s+fifty\s+words'
    r')\b',
    re.I,
)
#: A parenthesised language, as publishers mark translations.
_TRANSLATION_MARKER = re.compile(
    r'\((?:'
    r'tamil|hindi|bengali|telugu|marathi|urdu|gujarati|kannada|malayalam|punjabi|'
    r'spanish|french|german|italian|portuguese|dutch|polish|russian|turkish|'
    r'arabic|chinese|japanese|korean|swedish|danish|norwegian|finnish|greek|'
    r'czech|hungarian|romanian|croatian|serbian|ukrainian|hebrew|thai|vietnamese'
    r')(?:\s+edition)?\)',
    re.I,
)


def looks_derived(title: str | None) -> bool:
    """True if a title describes an adaptation, abridgement or translation.

    These are real books, so a source is not lying when it returns one. They are
    simply not the book on disk, and writing their title over the original is the
    failure this library has already suffered once.
    """
    text = title or ''
    return bool(_ADAPTATION_MARKERS.search(text) or _TRANSLATION_MARKER.search(text))


def norm(s: str | None) -> str:
    """Lowercase, spell out % and &, drop punctuation and leading articles."""
    s = (s or '').lower().replace('%', ' percent ').replace('&', ' and ')
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\b(the|a|an)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def sim(a: str | None, b: str | None) -> float:
    """Similarity of two titles, 0.0 to 1.0.

    Containment is strong evidence but not proof, so it is split in two:

    - ``"Digital Minimalism"`` inside ``"Digital Minimalism: Choosing a Focused
      Life"`` is a prefix, main title plus subtitle, and scores PREFIX_SCORE.
    - ``"The Happiest Toddler on the Block"`` inside ``"The Happiest Baby on the
      Block and The Happiest Toddler on the Block"`` is contained but not a
      prefix. That is an omnibus mentioning another volume, and it is capped at
      CONTAINED_SCORE so it stays below the threshold that would overwrite the
      single volume's metadata.
    """
    # Checked before normalising, which strips the punctuation these rely on.
    derived = looks_derived(a) != looks_derived(b)

    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        score = 1.0
    elif a in b or b in a:
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        score = PREFIX_SCORE if long.startswith(short) else CONTAINED_SCORE
    else:
        score = difflib.SequenceMatcher(None, a, b).ratio()

    # One side is a derived work and the other is not, so they are different
    # books however similar the words are.
    return min(score, ADAPTATION_SCORE) if derived else score


def best_author_score(author_lists: list[list[str]], filename_author: str) -> float:
    """How well the best source author matches the filename's author.

    A hallucinated match usually has the wrong author too, which is what makes
    this a useful second signal rather than a formality.
    """
    return max(
        (max((sim(a, filename_author) for a in authors), default=0.0) for authors in author_lists),
        default=0.0,
    )


@dataclass(frozen=True)
class SourceScore:
    """How well one source's answer matches the filename."""

    name: str
    title: str
    title_score: float
    author_score: float

    @property
    def strong(self) -> bool:
        """Both signals clear their threshold, from this one source's answer.

        Taking the best title from one source and the best author from another
        was the old flaw: neither source actually identified the book, but the
        combined maxima looked like one had.
        """
        return self.title_score >= TITLE_STRONG and self.author_score >= AUTHOR_STRONG


def classify(scores: list[SourceScore]) -> str:
    """HIGH, MED or LOW. Only HIGH is written without an explicit override.

    HIGH needs two independent sources that each identify the book on their own,
    and that agree with each other. One source is never enough: measured on a
    real library, a lone source returned an abridgement, a translation and a
    different book entirely, and each would have been written.

    The cost is deliberate. A book only one source knows, typically
    self-published or niche, cannot reach HIGH and needs --include-low.
    """
    strong = [s for s in scores if s.strong]

    agreeing = sum(
        1
        for i in range(len(strong))
        for j in range(i + 1, len(strong))
        if sim(strong[i].title, strong[j].title) >= CROSS_SOURCE_AGREE
    )
    if len(strong) >= 2 and agreeing >= 1:
        return 'HIGH'

    if strong:
        return 'MED'
    if any(s.title_score >= TITLE_WEAK and s.author_score >= AUTHOR_STRONG for s in scores):
        return 'MED'
    return 'LOW'
