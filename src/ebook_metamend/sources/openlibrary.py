"""Open Library's public search API. No key, no plugin, just HTTP."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from .errors import SourceError

SEARCH_URL = 'https://openlibrary.org/search.json'
#: Open Library's published policy: a request identifying the application and
#: a contact gets 3 requests per second, an anonymous one gets 1. The project
#: URL is the contact, so nothing personal ships in a public repository.
USER_AGENT = 'eBook-Metamend/1.0 (+https://github.com/OffCrazyFreak/eBook-Metamend)'
#: Only what is actually read below. first_publish_year was requested and
#: never used.
#: Deliberately no isbn or publisher. search.json answers at *work* level, so
#: those lists hold every edition ever published, unordered, and taking [0] wrote
#: an arbitrary edition's identifier: for a well-known novel that can be the
#: Italian paperback. The catalogue is still useful for titles and subjects.
FIELDS = 'title,author_name,subject'

#: Short on purpose. When this host is reachable it answers in about two
#: seconds; when it is not, it fails its TLS handshake and a long timeout just
#: buys silence at full price. Failing fast and retrying is strictly better than
#: waiting once for a long time.
TIMEOUT = 5
ATTEMPTS = 2
RETRY_PAUSE = 1
#: Subjects come back long and unranked, so only the head is useful.
MAX_SUBJECTS = 25


def fetch_openlibrary(title: str, author: str) -> dict[str, Any] | None:
    """Top hit for a title/author pair, shaped like a parsed OPF record.

    Returns the same keys as ``opf.parse`` so every source is interchangeable
    downstream. Descriptions, series, publisher and ISBN are always empty rather
    than absent: the first two are not in this API, the last two are, but only at
    work level, which makes them wrong more often than right.
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
        # OSError covers URLError, socket timeouts and TLS errors; ValueError
        # covers a truncated or non-JSON body. A bare Exception here would
        # also swallow a programming mistake into three retries with sleeps.
        except (OSError, ValueError) as exc:
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
        'publisher': '',
        'description': '',
        'tags': (doc.get('subject') or [])[:MAX_SUBJECTS],
        'series': None,
        'sidx': None,
        'isbn': '',
    }
