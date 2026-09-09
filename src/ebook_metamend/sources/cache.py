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

from .errors import SourceError

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

    def save(path: Path, title: str, author: str, record: dict[str, Any]) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf8') as fh:
            json.dump(
                {'source': source, 'title': title, 'author': author, **record},
                fh,
                indent=1,
                ensure_ascii=False,
            )

    def cached(title: str, author: str) -> Any:
        path = fixture_path(source, title, author)
        if path.exists():
            with path.open(encoding='utf8') as fh:
                record = json.load(fh)
            # A failure is part of what happened and has to replay as one.
            # Recording only successes meant a run where a source was unreachable
            # could not be replayed at all: the key was never written, so replay
            # raised MissingFixture and went back to the network.
            if 'error' in record:
                raise SourceError(record['error'])
            return record['response']
        if MODE == 'replay':
            raise MissingFixture(f'{source} / {title!r} / {author!r} -> {path.name}')

        try:
            response = fetch(title, author)
        except SourceError as exc:
            save(path, title, author, {'error': str(exc)})
            raise
        save(path, title, author, {'response': response})
        return response

    return cached


def replaying() -> bool:
    """True when no network will be touched, so pauses are pointless."""
    return MODE == 'replay'
