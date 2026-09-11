"""Open Library's public search API. No key, no plugin, just HTTP."""

from __future__ import annotations

import urllib.parse
from typing import Any

from . import http

SEARCH_URL = 'https://openlibrary.org/search.json'
#: Open Library's published policy: a request identifying the application and
#: a contact (http.USER_AGENT) gets 3 requests per second, an anonymous one 1.
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
    payload = http.get_json(
        f'{SEARCH_URL}?{query}', timeout=TIMEOUT, attempts=ATTEMPTS, retry_pause=RETRY_PAUSE
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
