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
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        return PREFIX_SCORE if long.startswith(short) else CONTAINED_SCORE
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_title_score(titles: list[str], filename_title: str) -> float:
    """How well the best source title matches the filename."""
    return max((sim(t, filename_title) for t in titles), default=0.0)


def best_author_score(author_lists: list[list[str]], filename_author: str) -> float:
    """How well the best source author matches the filename's author.

    A hallucinated match usually has the wrong author too, which is what makes
    this a useful second signal rather than a formality.
    """
    return max(
        (max((sim(a, filename_author) for a in authors), default=0.0) for authors in author_lists),
        default=0.0,
    )


def count_agreements(titles: list[str]) -> int:
    """Pairs of sources whose titles agree with each other."""
    return sum(
        1
        for i in range(len(titles))
        for j in range(i + 1, len(titles))
        if sim(titles[i], titles[j]) >= CROSS_SOURCE_AGREE
    )


def classify(title_score: float, author_score: float, agreements: int) -> str:
    """HIGH, MED or LOW. Only HIGH is written without an explicit override.

    Note that cross-source agreement alone never reaches HIGH. Two sources can be
    wrong together, so agreement with the *filename* is the stronger signal.
    """
    if title_score >= TITLE_STRONG and author_score >= AUTHOR_STRONG:
        return 'HIGH'
    if (
        title_score >= TITLE_STRONG
        or (title_score >= TITLE_WEAK and author_score >= AUTHOR_STRONG)
        or (agreements >= 1 and author_score >= AUTHOR_STRONG)
    ):
        return 'MED'
    return 'LOW'
