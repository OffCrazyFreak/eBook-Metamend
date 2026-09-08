"""Open Library's public search API. No key, no plugin, just HTTP."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

SEARCH_URL = 'https://openlibrary.org/search.json'
USER_AGENT = 'ebook-metamend/1.0 (personal library)'
FIELDS = 'title,author_name,subject,publisher,isbn,first_publish_year'

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
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.load(response)
                break
        except Exception:
            # No point pausing after the last attempt; it only delays the caller.
            if attempt < ATTEMPTS - 1:
                time.sleep(RETRY_PAUSE * (attempt + 1))

    if not payload or not payload.get('docs'):
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
