"""Cleaning tags before they are written.

Two problems, both measured on real files rather than imagined.

**Commas cannot survive.** Calibre splits subjects on commas at every entry
point: ``--tags``, ``--from-opf``, all of them. There is no escaping. So a
Library of Congress heading like ``Angelou, Maya, 1928-2014`` is stored as three
useless tags. Rather than lose the heading, it is rewritten to ``Maya Angelou``,
which says the same thing and contains no comma. Ordinary commas are left alone,
because splitting ``Fiction, general`` into two tags is harmless and arguably
right.

**Some tags are catalogue noise.** A small blocklist, deliberately small: only
entries that are provably not subjects at all. Anything that is a real subject
which merely happened to be wrong on one book is a per-book mistake, not a rule.
"""

from __future__ import annotations

import re

from .matching import AUTHOR_STRONG, sim

#: Provable noise. A piracy-site stamp and marketing or edition labels that are
#: not subjects in any catalogue. Kept short on purpose: every entry here is
#: applied to an entire library, so "it was wrong on one book" is not enough.
NOISE_TAGS = frozenset(
    {
        'mobilism',
        'new york times bestseller',
        'new york times reviewed',
        'large type books',
        'uncategorized',
        'unknown',
    }
)

#: "Surname, Given, 1928-2014" is how a person appears as a *subject* in MARC and
#: Library of Congress data. The life dates or a parenthetical are required, not
#: optional: without them the shape is indistinguishable from an ordinary
#: qualified subject like "Political Science, General".
#:
#: The dates are still not enough on their own, because a MARC *period*
#: subdivision has exactly the same shape: "United States, History, 1861-1865"
#: was being rewritten into "History United States" and written to real files.
#: Nothing about the string distinguishes the two, so the caller supplies the
#: book's author and only a heading naming that person is rewritten.
_NAME_HEADING = re.compile(
    r"""^
    (?P<surname>[^,()&]+?)              # Angelou
    ,\s*
    (?P<given>[^,()&]+?)                # Maya
    (?:\s*\((?P<expansion>[^)]*)\))?    # (Viktor Emil), discarded
    \s*,\s*\d{3,4}\s*-\s*\d{0,4}         # 1928-2014, required
    \s*$""",
    re.X,
)
#: The same heading with a parenthetical expansion but no dates.
_NAME_HEADING_PAREN = re.compile(r'^(?P<surname>[^,()&]+?),\s*(?P<given>[^,()&]+?)\s*\([^)]*\)\s*$')
#: A bare year or life-date range left behind by an earlier comma split.
_ORPHAN_DATES = re.compile(r'^\d{3,4}\s*-\s*\d{0,4}$')

#: A surname is one or two words; a given name is at most three.
_MAX_SURNAME_WORDS = 2
_MAX_GIVEN_WORDS = 3


def reformat_name_heading(tag: str, author: str) -> str:
    """``Angelou, Maya, 1928-2014`` becomes ``Maya Angelou``, for that author.

    ``author`` is the book's author, taken from the filename. Only a heading that
    names that person is rewritten. Everything else keeps its commas and is split
    by Calibre, which for "United States, History, 1861-1865" yields the tags
    "United States" and "History": two ordinary subjects, and a far better
    outcome than the "History United States" this used to produce.
    """
    text = tag.strip()
    match = _NAME_HEADING.match(text) or _NAME_HEADING_PAREN.match(text)
    if not match:
        return tag

    surname = match.group('surname').strip()
    given = match.group('given').strip()
    if not (surname and given):
        return tag
    if not (surname[:1].isupper() and given[:1].isupper()):
        return tag
    if len(surname.split()) > _MAX_SURNAME_WORDS or len(given.split()) > _MAX_GIVEN_WORDS:
        return tag

    name = f'{given} {surname}'
    # Fuzzy, because the catalogue form carries initials and expansions the
    # filename does not: "Frankl, Viktor E. (Viktor Emil)" against "Viktor Frankl".
    if sim(name, author, prefix_bonus=False) < AUTHOR_STRONG:
        return tag
    return name


def clean(tags: list[str], author: str = '') -> list[str]:
    """Reformat name headings, drop noise, de-duplicate, preserve order.

    ``author`` gates the name rewriting; without one, no heading is rewritten.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = ' '.join((raw or '').split())
        if not tag:
            continue
        if author:
            tag = reformat_name_heading(tag, author)
        if tag.lower() in NOISE_TAGS or _ORPHAN_DATES.match(tag):
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
    return cleaned
