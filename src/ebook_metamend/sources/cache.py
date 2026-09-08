"""Record and replay source responses.

Source answers vary between runs and a live run costs about 63 seconds per book,
which makes any before/after comparison meaningless and any test suite slow and
flaky. Recording every response once turns both problems into a file read.

Enable with two environment variables::

    METAMEND_FIXTURES=/path/to/fixtures
    METAMEND_CACHE_MODE=record   # query live, save every response
    METAMEND_CACHE_MODE=replay   # fixtures only, never touch the network

Unset, sources behave normally.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

MODE = os.environ.get('METAMEND_CACHE_MODE', '')
FIXTURES = Path(os.environ.get('METAMEND_FIXTURES', 'fixtures'))


class MissingFixture(RuntimeError):
    """Replay hit a key that was never recorded.

    Raised rather than returning None, because None is indistinguishable from
    "the source had no answer" and would quietly change the result.
    """


def fixture_path(source: str, title: str, author: str) -> Path:
    digest = hashlib.sha256(f'{source}\x00{title}\x00{author}'.encode()).hexdigest()[:16]
    return FIXTURES / f'{source}-{digest}.json'


def wrap(source: str, fetch: Callable[[str, str], Any]) -> Callable[[str, str], Any]:
    """Wrap a source function with the cache, if a mode is set."""
    if MODE not in ('record', 'replay'):
        return fetch

    def cached(title: str, author: str) -> Any:
        path = fixture_path(source, title, author)
        if path.exists():
            with path.open(encoding='utf8') as fh:
                return json.load(fh)['response']
        if MODE == 'replay':
            raise MissingFixture(f'{source} / {title!r} / {author!r} -> {path.name}')

        response = fetch(title, author)
        FIXTURES.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf8') as fh:
            json.dump(
                {'source': source, 'title': title, 'author': author, 'response': response},
                fh,
                indent=1,
                ensure_ascii=False,
            )
        return response

    return cached


def replaying() -> bool:
    """True when no network will be touched, so pauses are pointless."""
    return MODE == 'replay'
