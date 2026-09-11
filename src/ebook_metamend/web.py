"""What the browser worker calls. One book at a time, from bytes, back to bytes.

The worker hands over a book's files, gets the proposal, and later hands the
same files back with the proposal to have the gains written. Nothing here
knows about Pyodide beyond ``install_transport``; the rest runs under pytest.
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Callable
from typing import Any

from . import enrich
from .library import Book, parse_filename
from .sources import WEB_SOURCE_NAMES, http, select

WEB_SOURCES = select(WEB_SOURCE_NAMES)


def install_transport() -> None:
    """Route every catalogue call through the browser's XMLHttpRequest.

    Synchronous XHR is allowed in a worker, which is what lets the sources stay
    plain blocking Python. Browsers own the User-Agent header, so it is dropped
    rather than refused.
    """
    from pyodide.http import pyxhr  # only exists inside Pyodide

    def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
        sent = {k: v for k, v in headers.items() if k.lower() != 'user-agent'}
        response = pyxhr.get(url, headers=sent)
        response.raise_for_status()
        return response.content

    http.set_transport(transport)


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


def _remove(book: Book) -> None:
    for path in book.formats.values():
        try:
            os.unlink(path)
        except OSError:
            pass


def facts(stem: str) -> dict[str, Any]:
    """The filename's claims, in the shape the page shows."""
    f = parse_filename(os.path.basename(stem))
    return {
        'author': f.author,
        'title': f.title,
        'series': f.series,
        'series_index': f.series_index,
    }


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
        _remove(book)
    if proposal is None:
        return None
    return {
        **proposal.to_dict(),
        'stem': stem,
        # Paths inside the worker's file system mean nothing to the page.
        'files': {ext: os.path.basename(path) for ext, path in proposal.files.items()},
        'current': proposal.current,
        'unreadable': proposal.unreadable,
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

    Only what ``enrich.apply`` writes on the desktop, through the same writers.
    """
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
        _remove(book)
    return {
        'files': written,
        'writes': [{'ext': ext, 'ok': ok, 'reason': reason} for ext, ok, reason in record.writes],
    }


def pause_after() -> float:
    """Seconds the worker should wait before the next book."""
    return enrich.pause_after(WEB_SOURCES)


def bundle(files: dict[str, bytes]) -> bytes:
    """One zip of repaired files, for a browser that cannot write into a folder.

    Stored, not deflated: EPUBs and PDFs are already compressed, and the
    visitor waits on this.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()
