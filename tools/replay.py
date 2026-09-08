#!/usr/bin/env python3
"""Run the enricher with its metadata sources recorded to, or replayed from, disk.

The enricher's output depends on live Kobo, Google Books and Open Library
responses, and a run costs about 63 seconds per book. That makes any before/after
comparison worthless: you cannot tell a refactoring bug from source drift.

This wraps the source functions in a cache keyed on (source, title, author).

    record   query live, write every response to the fixture directory
    replay   read fixtures only, never touch the network, no sleeps

Record once, then every later run is deterministic and takes seconds.

The enricher itself is imported and monkey-patched rather than edited, so the code
under measurement is exactly the code in the repository.

    METAMEND_FIXTURES=<dir> python3 tools/replay.py record <script.py> [args...]
    METAMEND_FIXTURES=<dir> python3 tools/replay.py replay <script.py> [args...]
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

FIXTURES = Path(os.environ.get('METAMEND_FIXTURES', 'fixtures'))


class MissingFixture(RuntimeError):
    """Replay hit a key that was never recorded. Loud, because a silent None would
    look exactly like 'the source had no answer' and quietly change the result."""


def _key(source: str, title: str, author: str) -> str:
    raw = f'{source}\x00{title}\x00{author}'
    digest = hashlib.sha256(raw.encode('utf8')).hexdigest()[:16]
    return f'{source}-{digest}'


def _load(path: str):
    """Import a module whose filename is not a valid identifier."""
    spec = importlib.util.spec_from_file_location('_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, ['_under_test']
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


class _NoSleep:
    """Proxy for the time module with sleep disabled, so replay is instant."""

    def __init__(self, real):
        self._real = real

    def sleep(self, _seconds):
        return None

    def __getattr__(self, name):
        return getattr(self._real, name)


def install(mod, mode: str) -> dict:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    stats = {'hit': 0, 'miss': 0, 'recorded': 0}

    def cached(source_name, real, arg_names):
        def wrapper(*args, **kwargs):
            bound = dict(zip(arg_names, args, strict=False))
            bound.update(kwargs)
            title, author = bound.get('title', ''), bound.get('author', '')
            source = source_name(bound)
            path = FIXTURES / f'{_key(source, title, author)}.json'

            if path.exists():
                stats['hit'] += 1
                with path.open() as fh:
                    return json.load(fh)['response']

            if mode == 'replay':
                raise MissingFixture(f'{source} / {title!r} / {author!r} -> {path.name}')

            stats['miss'] += 1
            response = real(*args, **kwargs)
            with path.open('w') as fh:
                json.dump(
                    {'source': source, 'title': title, 'author': author, 'response': response},
                    fh,
                    indent=1,
                    ensure_ascii=False,
                )
            stats['recorded'] += 1
            return response

        return wrapper

    # Source names must match src/ebook_metamend/sources/cache.py exactly, or the
    # package cannot replay fixtures recorded through this wrapper.
    plugin_names = {'Kobo Metadata': 'kobo', 'Google': 'google'}

    if hasattr(mod, 'calibre_src'):
        mod.calibre_src = cached(
            lambda b: plugin_names.get(b.get('plugin', ''), b.get('plugin', 'calibre')),
            mod.calibre_src,
            ('title', 'author', 'plugin', 'tmo', 'retries'),
        )
    if hasattr(mod, 'openlib'):
        mod.openlib = cached(lambda _b: 'openlib', mod.openlib, ('title', 'author'))

    if mode == 'replay' and hasattr(mod, 'time'):
        mod.time = _NoSleep(mod.time)

    return stats


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in ('record', 'replay'):
        print(__doc__)
        return 2

    mode, script = sys.argv[1], sys.argv[2]
    mod = _load(script)
    stats = install(mod, mode)

    print(f'[replay] mode={mode} fixtures={FIXTURES}', file=sys.stderr)
    sys.argv = [script] + sys.argv[3:]
    try:
        mod.main()
    finally:
        print(
            f"[replay] fixture hits={stats['hit']} recorded={stats['recorded']}",
            file=sys.stderr,
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
