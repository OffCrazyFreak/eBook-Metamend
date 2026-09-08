"""Open Library's public search API. No key, no plugin, just HTTP."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from .errors import SourceError

SEARCH_URL = 'https://openlibrary.org/search.json'
USER_AGENT = 'ebook-metamend/1.0 (personal library)'
#: Only what is actually read below. first_publish_year was requested and
#: never used.
FIELDS = 'title,author_name,subject,publisher,isbn'

TIMEOUT = 25
ATTEMPTS = 3
RETRY_PAUSE = 3
#: Subjects come back long and unranked, so only the head is useful.
MAX_SUBJECTS = 25


def fetch_openlibrary(title: str, author: str) -> dict[str, Any] | None:
    """Top hit for a title/author pair, shaped like a parsed OPF record.

    Returns the same keys as ``opf.parse`` so every source is interchangeable
    downstream. Open Library's search has no descriptions and no series, so those
    are always empty rather than absent.
    """
    query = urllib.parse.urlencode(
        {'title': title, 'author': author, 'fields': FIELDS, 'limit': '1'}
    )
    request = urllib.request.Request(f'{SEARCH_URL}?{query}', headers={'User-Agent': USER_AGENT})

    payload = None
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.load(response)
                break
        except Exception as exc:
            last_error = exc
            # No point pausing after the last attempt; it only delays the caller.
            if attempt < ATTEMPTS - 1:
                time.sleep(RETRY_PAUSE * (attempt + 1))

    if payload is None:
        # Raised, not returned as None. Open Library returns 500s, resets
        # connections and times out its TLS handshake often enough to matter,
        # and reporting that as "no such book" is how a source silently stops
        # contributing.
        raise SourceError(
            f'{ATTEMPTS} attempts failed ({type(last_error).__name__}: {str(last_error)[:80]})'
        )

    if not payload.get('docs'):
        return None

    doc = payload['docs'][0]
    return {
        'title': doc.get('title', ''),
        'authors': doc.get('author_name') or [],
        'publisher': (doc.get('publisher') or [''])[0],
        'description': '',
        'tags': (doc.get('subject') or [])[:MAX_SUBJECTS],
        'series': None,
        'sidx': None,
        'isbn': (doc.get('isbn') or [''])[0],
    }
