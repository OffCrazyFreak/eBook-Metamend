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
from dataclasses import dataclass
from typing import Any

from . import cache
from .calibre_plugin import fetch_google, fetch_kobo
from .openlibrary import fetch_openlibrary


@dataclass(frozen=True)
class Source:
    name: str
    fetch: Callable[[str, str], dict[str, Any] | None]
    #: Seconds to wait after querying, to stay welcome. Google is the strictest.
    pause: float


#: Query order matters only for the pauses; scoring is order independent.
#: Each fetch is wrapped so a run can be recorded and replayed offline.
SOURCES: tuple[Source, ...] = (
    Source('kobo', cache.wrap('kobo', fetch_kobo), pause=2),
    Source('google', cache.wrap('google', fetch_google), pause=8),
    Source('openlib', cache.wrap('openlib', fetch_openlibrary), pause=1),
)

__all__ = ['SOURCES', 'Source', 'cache', 'fetch_google', 'fetch_kobo', 'fetch_openlibrary']
