"""Inventaire, a book catalogue built on Wikidata. No key, allows browser calls.

Its search answers with works, not editions, and a work hit carries no author:
that takes a second call for the entity and a third for the labels of whatever
the entity points at (authors, genres, subjects, series). Three calls per book
at most, because the candidates are batched into one request each.

It always returns something, even for a book it does not have, so its answers
lean on the safety model to be rejected when they are wrong.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from .. import matching
from . import http

SEARCH_URL = 'https://inventaire.io/api/search'
ENTITIES_URL = 'https://inventaire.io/api/entities'
PAUSE = 1
LIMIT = 5
#: Work hits worth the entity round trip. Below this the title is not the book.
CANDIDATES = 3
TIMEOUT = 10

AUTHOR = 'wdt:P50'
GENRE = 'wdt:P136'
SUBJECT = 'wdt:P921'
SERIES = 'wdt:P179'
SERIES_ORDINAL = 'wdt:P1545'


def _entities(uris: list[str]) -> dict[str, Any]:
    if not uris:
        return {}
    query = urllib.parse.urlencode({'action': 'by-uris', 'uris': '|'.join(uris)})
    return http.get_json(f'{ENTITIES_URL}?{query}', timeout=TIMEOUT).get('entities') or {}


def _label(entity: dict[str, Any] | None) -> str:
    if not entity:
        return ''
    labels = entity.get('labels') or {}
    return (labels.get('en') or next(iter(labels.values()), '')).strip()


def _claim(entity: dict[str, Any], prop: str) -> list[str]:
    return list((entity.get('claims') or {}).get(prop) or [])


def fetch_inventaire(title: str, author: str) -> dict[str, Any] | None:
    """Best work for a title/author pair, shaped like a parsed OPF record."""
    query = urllib.parse.urlencode(
        {'types': 'works', 'search': f'{title} {author}', 'limit': LIMIT}
    )
    hits = http.get_json(f'{SEARCH_URL}?{query}', timeout=TIMEOUT).get('results') or []
    scored = sorted(
        ((round(matching.sim(title, h.get('label') or ''), 2), h) for h in hits if h.get('uri')),
        key=lambda pair: pair[0],
        reverse=True,
    )
    candidates = [(s, h) for s, h in scored[:CANDIDATES] if s >= matching.TITLE_WEAK]
    if not candidates:
        return None

    works = _entities([h['uri'] for _, h in candidates])
    wanted: list[str] = []
    for _, hit in candidates:
        work = works.get(hit['uri']) or {}
        for prop in (AUTHOR, GENRE, SUBJECT, SERIES):
            wanted += _claim(work, prop)
    labels = _entities(sorted(set(wanted)))

    def names(work: dict[str, Any], prop: str) -> list[str]:
        return [n for n in (_label(labels.get(uri)) for uri in _claim(work, prop)) if n]

    best_score, best_hit, best_work = None, None, None
    for title_score, hit in candidates:
        work = works.get(hit['uri']) or {}
        author_score = matching.best_author_score(names(work, AUTHOR), author)
        key = (title_score, author_score)
        if best_score is None or key > best_score:
            best_score, best_hit, best_work = key, hit, work
    assert best_hit is not None and best_work is not None

    series = names(best_work, SERIES)
    ordinal = _claim(best_work, SERIES_ORDINAL)
    return {
        'title': best_hit.get('label') or '',
        'authors': names(best_work, AUTHOR),
        'publisher': '',
        'description': '',
        'tags': names(best_work, GENRE) + names(best_work, SUBJECT),
        'series': series[0] if series else None,
        'sidx': ordinal[0] if series and ordinal else None,
        'isbn': '',
    }
