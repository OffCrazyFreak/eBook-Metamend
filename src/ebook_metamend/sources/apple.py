"""Apple Books through the iTunes Search API. No key, and it allows browser calls.

Measured on a 50-book sample it named the same book as the filename more often
than any other catalogue (36 of 50, against Kobo's 32). It answers at edition
level with a description and genres, and gives no publisher or ISBN.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

from .. import matching
from . import http

SEARCH_URL = 'https://itunes.apple.com/search'
#: Apple documents roughly 20 calls a minute per address; three seconds keeps
#: a whole library under that without a limiter.
PAUSE = 3
LIMIT = 5
TIMEOUT = 10
_TAG = re.compile(r'<[^>]+>')


def _plain(text: str) -> str:
    """Apple wraps descriptions in HTML; the OPF wants text."""
    return html.unescape(_TAG.sub('', text or '')).strip()


def _best(results: list[dict[str, Any]], title: str, author: str) -> dict[str, Any] | None:
    """The result that reads most like the filename: title first, author breaks ties."""
    ranked = []
    for hit in results:
        if hit.get('kind') != 'ebook':
            continue
        name = hit.get('trackName') or ''
        artist = hit.get('artistName') or ''
        ranked.append(
            (
                round(matching.sim(title, name), 2),
                matching.best_author_score([artist], author),
                hit,
            )
        )
    if not ranked:
        return None
    return max(ranked, key=lambda r: (r[0], r[1]))[2]


def fetch_apple(title: str, author: str) -> dict[str, Any] | None:
    """Best hit for a title/author pair, shaped like a parsed OPF record."""
    query = urllib.parse.urlencode(
        {'term': f'{title} {author}', 'media': 'ebook', 'entity': 'ebook', 'limit': LIMIT}
    )
    payload = http.get_json(f'{SEARCH_URL}?{query}', timeout=TIMEOUT)
    hit = _best(payload.get('results') or [], title, author)
    if hit is None:
        return None
    return {
        'title': hit.get('trackName') or '',
        'authors': [hit['artistName']] if hit.get('artistName') else [],
        'publisher': '',
        'description': _plain(hit.get('description') or ''),
        # "Books" is the storefront section, not a genre, and every hit has it.
        'tags': [g for g in (hit.get('genres') or []) if g != 'Books'],
        'series': None,
        'sidx': None,
        'isbn': '',
    }
