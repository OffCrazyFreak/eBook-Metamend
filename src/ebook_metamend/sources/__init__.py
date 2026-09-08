"""Metadata sources, and what each of them is actually like.

Measured across a few hundred books:

============  ==========================================================
Kobo          Best coverage, but silently invents matches. Never alone.
Google Books  Misses more, fails loudly. Reliable when it answers.
Open Library  Same, thinner catalogue.
Goodreads     Blocks after a single request. Not used.
Amazon        Returns SEO spam. Not used.
============  ==========================================================

This is the reason for the whole design. A source that returns a plausible wrong
answer is far more dangerous than one that returns nothing, which is why no
single source can write on its own authority.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import cache
from .calibre_plugin import fetch_google, fetch_kobo
from .errors import SourceError, SourceUnavailable
from .openlibrary import fetch_openlibrary


@dataclass(frozen=True)
class Source:
    name: str
    fetch: Callable[[str, str], dict[str, Any] | None]
    #: Seconds to wait after a *successful* query, to stay welcome.
    pause: float


@dataclass
class Pacer:
    """How long to wait after querying one source.

    The original paused a fixed 11 seconds per book across the three sources
    whether or not anything had gone wrong, which is most of the 63 seconds a
    book used to cost. This backs off only when a source actually stops
    answering, and returns to the polite baseline as soon as it does.
    """

    #: Longest we will ever wait, so a persistently dead source cannot stall a run.
    ceiling: float = 60.0
    #: Misses are capped before they become an exponent. Without this a source
    #: that never answers builds an astronomically large power of two, which is
    #: slow to compute long before the ceiling clamps the result.
    max_misses: int = 8
    _misses: dict[str, int] = field(default_factory=dict)

    def record(self, source: str, answered: bool) -> None:
        if answered:
            self._misses[source] = 0
        else:
            self._misses[source] = min(self._misses.get(source, 0) + 1, self.max_misses)

    def delay(self, source: Source) -> float:
        misses = self._misses.get(source.name, 0)
        if not misses:
            return source.pause
        return min(source.pause * (2**misses), self.ceiling)


#: Query order matters only for the pauses; scoring is order independent.
#: Each fetch is wrapped so a run can be recorded and replayed offline.
SOURCES: tuple[Source, ...] = (
    Source('kobo', cache.wrap('kobo', fetch_kobo), pause=2),
    Source('google', cache.wrap('google', fetch_google), pause=8),
    Source('openlib', cache.wrap('openlib', fetch_openlibrary), pause=1),
)

__all__ = [
    'SOURCES',
    'Pacer',
    'Source',
    'SourceError',
    'SourceUnavailable',
    'cache',
    'fetch_google',
    'fetch_kobo',
    'fetch_openlibrary',
]
