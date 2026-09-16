"""What the browser worker calls. One book at a time, from bytes, back to bytes.

The worker hands over a book's files, gets the proposal, and later hands the
same files back with the proposal to have the gains written. Nothing here
knows about Pyodide beyond ``install_transport``; the rest runs under pytest.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from . import enrich
from .library import Book, FilenameFacts, parse_filename
from .sources import WEB_SOURCE_NAMES, http, select

WEB_SOURCES = select(WEB_SOURCE_NAMES)


def install_transport(fetch: Callable[[str, str, float], Any]) -> None:
    """Route every catalogue call through a function the worker supplies.

    The worker hands in a synchronous XMLHttpRequest wrapper: (url, headers as
    JSON, timeout in seconds) to the body's bytes, raising on any failure. The
    package itself never imports anything from the browser, so the same code
    runs under pytest with a plain Python function in that seat. Browsers own
    the User-Agent header, so it is dropped rather than refused.
    """

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        sent = {k: v for k, v in headers.items() if k.lower() != 'user-agent'}
        try:
            body = fetch(url, json.dumps(sent), timeout)
        except Exception as exc:  # noqa: BLE001 - the browser's error type is not ours
            # OSError is what get_json retries and the pacer counts as a miss.
            raise OSError(str(exc)[:120]) from exc
        return bytes(body.to_py() if hasattr(body, 'to_py') else body)

    http.set_transport(transport)


def begin_run() -> None:
    """Forget the last run's shelved sources and back-off; a page lives long."""
    enrich.reset_run_state()


def _place(stem: str, files: dict[str, bytes], root: str) -> Book:
    """Write the visitor's files where the pipeline expects a library.

    The page keys a book by its folder and name so two books with one name
    stay apart; the filename facts come from the name alone, as on the desktop.
    """
    formats: dict[str, str] = {}
    for ext, data in files.items():
        path = os.path.join(root, f'{stem}{ext}')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data)
        formats[ext] = path
    return Book(stem=os.path.basename(stem), formats=formats)


def _remove(book: Book, root: str) -> None:
    for path in book.formats.values():
        try:
            os.unlink(path)
        except OSError:
            pass
    # The folders were made for this book; an empty one left behind is a leak
    # in a file system that lives as long as the page.
    folder = os.path.dirname(next(iter(book.formats.values()), ''))
    while folder and os.path.abspath(folder) != os.path.abspath(root):
        try:
            os.rmdir(folder)
        except OSError:
            break
        folder = os.path.dirname(folder)


def _facts(f: FilenameFacts) -> dict[str, Any]:
    return {
        'author': f.author,
        'title': f.title,
        'series': f.series,
        'series_index': f.series_index,
        'scheme': f.scheme,
    }


def facts(stem: str) -> dict[str, Any]:
    """The filename's claims, in the shape the page shows."""
    return _facts(parse_filename(os.path.basename(stem)))


def propose(
    stem: str,
    files: dict[str, bytes],
    root: str,
    on_answer: Callable[[str, bool], None] | None = None,
) -> dict[str, Any] | None:
    """Run the safety model on one book. ``None`` when no catalogue had it.

    The result is ``Proposal.to_dict()`` plus the reporting fields the page
    needs: the book's current metadata, every source's score, and whether the
    file could be read at all.
    """
    book = _place(stem, files, root)
    try:
        proposal = enrich.propose(book, sources=WEB_SOURCES, pause=False, on_answer=on_answer)
    finally:
        _remove(book, root)
    if proposal is None:
        return None
    return {
        **proposal.to_dict(),
        'stem': stem,
        # Paths inside the worker's file system mean nothing to the page.
        'files': {ext: os.path.basename(path) for ext, path in proposal.files.items()},
        'current': proposal.current,
        'unreadable': proposal.unreadable,
        # The reading the verdict was scored against, which may be the name the
        # other way round from what the page showed while it waited.
        'facts': _facts(proposal.facts) if proposal.facts else facts(stem),
        'scores': [
            {
                'name': s.name,
                'title': s.title,
                'title_score': s.title_score,
                'author_score': s.author_score,
            }
            for s in proposal.scores
        ],
    }


def apply(
    stem: str, files: dict[str, bytes], root: str, proposal: dict[str, Any]
) -> dict[str, Any]:
    """Write a proposal's gains into the files and hand the bytes back.

    Only what ``enrich.apply`` writes on the desktop, through the same writers,
    and only at HIGH: the page's own gate is not the last word on writing.
    """
    if proposal.get('conf') != 'HIGH':
        raise ValueError(f'only HIGH proposals are written, not {proposal.get("conf")!r}')
    book = _place(stem, files, root)
    # The page's copy carries reporting extras; only the serialised fields build a Proposal.
    keys = enrich.Proposal(stem, {}, '', [], {}, {}, 0, 0, {}).to_dict().keys() - {'files'}
    record = enrich.Proposal(**{k: proposal[k] for k in keys}, files=book.formats)
    try:
        enrich.apply(record)
        written = {}
        for ext, path in book.formats.items():
            with open(path, 'rb') as fh:
                written[ext] = fh.read()
    finally:
        _remove(book, root)
    return {
        'files': written,
        'writes': [{'ext': ext, 'ok': ok, 'reason': reason} for ext, ok, reason in record.writes],
    }


def unavailable() -> list[str]:
    """Catalogues shelved after repeated failures, so the page can say why a
    row has fewer witnesses than it should, even when no source answered."""
    return sorted(enrich.unavailable_sources)


def pause_after() -> float:
    """Seconds the worker should wait before the next book."""
    return enrich.pause_after(WEB_SOURCES)
