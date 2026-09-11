"""Record and replay source responses.

Source answers vary between runs and a live run costs about 63 seconds per book,
which makes any before/after comparison meaningless and any test suite slow and
flaky. Recording every response once turns both problems into a file read.

Enable with two environment variables::

    METAMEND_FIXTURES=/path/to/fixtures
    METAMEND_CACHE_MODE=record   # query live, save every response
    METAMEND_CACHE_MODE=replay   # fixtures only, never touch the network

Unset, sources behave normally.

Two layers are recorded. The parsed record each source returns is what a replay
serves when nothing else is there; the raw body behind it (the JSON a catalogue
sent, the OPF a Calibre plugin printed) is recorded beside it, and a replay
prefers the raw body so that a change to a parser is exercised by the replay
rather than hidden by it. Fixture sets recorded before the raw layer existed
keep working: they simply replay the parsed record.
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


class MissingRaw(MissingFixture):
    """Replay needed a raw body that was never recorded.

    Caught by ``wrap``, which then falls back to the parsed record; it only
    surfaces when neither layer has the answer.
    """


def raw_path(kind: str, key: str) -> Path:
    digest = hashlib.sha256(f'{kind}\x00{key}'.encode()).hexdigest()[:16]
    return FIXTURES / f'raw-{kind}-{digest}.json'


def raw(kind: str, key: str, fetch: Callable[[], str]) -> str:
    """Fetch a raw body through the cache, if a mode is set.

    ``kind`` names the layer ("http", "plugin") and ``key`` identifies the call
    within it (the URL; the plugin, title and author). Failures are not stored
    here: the parsed layer records them, so a failed call simply has no raw file
    and replays from that record.
    """
    if MODE not in ('record', 'replay'):
        return fetch()
    path = raw_path(kind, key)
    if _consumed is not None:
        _consumed.append(path.name)
    if path.exists():
        with path.open(encoding='utf8') as fh:
            return json.load(fh)['body']
    if MODE == 'replay':
        raise MissingRaw(f'{kind} / {key!r} -> {path.name}')
    body = fetch()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf8') as fh:
        json.dump({'kind': kind, 'key': key, 'body': body}, fh, indent=1, ensure_ascii=False)
    return body


#: The raw files the fetch being recorded has read, so its parsed record can
#: name them. A replay runs the fetch only when every named file is present:
#: that is what keeps a source that bypasses the raw layer, or a set recorded
#: before it existed, from ever reaching the network during a replay.
_consumed: list[str] | None = None


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
        global _consumed
        if MODE == 'replay':
            if not path.exists():
                raise MissingFixture(f'{source} / {title!r} / {author!r} -> {path.name}')
            with path.open(encoding='utf8') as fh:
                record = json.load(fh)
            # The raw layer first, so the parser in the checked-out code runs
            # over what the catalogue actually sent. Only when every raw file
            # the recording read is present, or a fetch would touch the network.
            if record.get('raw') and all((FIXTURES / name).exists() for name in record['raw']):
                # A SourceError here can only come from a stored body the
                # parser rejects (no network is reached), so the parsed record
                # is the better answer.
                try:
                    return fetch(title, author)
                except (MissingRaw, SourceError):
                    pass
            # A failure is part of what happened and has to replay as one.
            # Recording only successes meant a run where a source was unreachable
            # could not be replayed at all: the key was never written, so replay
            # raised MissingFixture and went back to the network.
            if 'error' in record:
                raise SourceError(record['error'])
            return record['response']

        # Record mode always runs the fetch: the raw layer serves a body it
        # already has and only goes to the network for one it lacks, so a
        # stored failure (transient by definition) is retried rather than
        # frozen in, and a set recorded before the raw layer existed fills in.
        _consumed = []
        try:
            response = fetch(title, author)
        except SourceError as exc:
            # A good record already on disk outlives a bad minute; the failure
            # is still raised so the run reports it.
            if not _has_response(path):
                save(path, title, author, {'error': str(exc)})
            raise
        finally:
            consumed, _consumed = _consumed, None
        save(path, title, author, {'response': response, 'raw': consumed})
        return response

    return cached


def _has_response(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding='utf8') as fh:
        return 'error' not in json.load(fh)


def replaying() -> bool:
    """True when no network will be touched, so pauses are pointless."""
    return MODE == 'replay'
