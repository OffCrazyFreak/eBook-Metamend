"""Metadata sources, and what each of them is actually like.

Measured across a few hundred books, then on a 50-book sample (docs/sources.md):

============  ==========================================================
Kobo          Best coverage, but silently invents matches. Never alone.
              Scrapes through a bot-check bypass: desktop only.
Apple Books   Names the right book most often of all. Keyless, browser-safe.
Google Books  Misses more, fails loudly. Reliable when it answers.
Open Library  Same, thinner catalogue. Keyless, browser-safe.
Inventaire    Wikidata-backed; always answers, so it leans on the scoring.
Goodreads     Blocks after a single request. Not used.
Amazon        Returns SEO spam. Not used.
============  ==========================================================

This is the reason for the whole design. A source that returns a plausible wrong
answer is far more dangerous than one that returns nothing, which is why no
single source can write on its own authority.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from . import cache, http
from .apple import PAUSE as APPLE_PAUSE
from .apple import fetch_apple
from .calibre_plugin import fetch_google, fetch_kobo
from .errors import SourceError, SourceUnavailable
from .inventaire import PAUSE as INVENTAIRE_PAUSE
from .inventaire import fetch_inventaire
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
    Source('apple', cache.wrap('apple', fetch_apple), pause=APPLE_PAUSE),
    Source('inventaire', cache.wrap('inventaire', fetch_inventaire), pause=INVENTAIRE_PAUSE),
)

#: What a browser can reach: the three that answer keyless with a CORS header.
#: Kobo scrapes through a bot-check bypass and Google's keyless quota is shared
#: and exhausted daily, so neither can be hosted.
WEB_SOURCE_NAMES = ('apple', 'openlib', 'inventaire')


def select(names: Iterable[str]) -> tuple[Source, ...]:
    """The sources with these names, in SOURCES order. Unknown names raise."""
    wanted = set(names)
    unknown = wanted - {s.name for s in SOURCES}
    if unknown:
        known = ', '.join(s.name for s in SOURCES)
        raise ValueError(f'unknown source(s): {", ".join(sorted(unknown))}; known: {known}')
    return tuple(s for s in SOURCES if s.name in wanted)


__all__ = [
    'SOURCES',
    'WEB_SOURCE_NAMES',
    'Pacer',
    'Source',
    'SourceError',
    'SourceUnavailable',
    'cache',
    'fetch_apple',
    'fetch_google',
    'fetch_inventaire',
    'fetch_kobo',
    'fetch_openlibrary',
    'http',
    'select',
]
