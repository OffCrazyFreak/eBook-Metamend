"""Kobo and Google Books, reached through Calibre's metadata plugins.

Using Calibre's plugins rather than the APIs directly is what takes the source
count from a couple to several without any API keys.
"""

from __future__ import annotations

from typing import Any

from .. import calibre, opf

#: Calibre plugin names, as ``fetch-ebook-metadata -p`` expects them.
KOBO_PLUGIN = 'Kobo Metadata'
GOOGLE_PLUGIN = 'Google'

DEFAULT_TIMEOUT = 18


def fetch_plugin(
    title: str, author: str, plugin: str, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any] | None:
    xml = calibre.fetch_metadata(title, author, plugin, timeout)
    return opf.parse(xml) if xml else None


def fetch_kobo(title: str, author: str) -> dict[str, Any] | None:
    return fetch_plugin(title, author, KOBO_PLUGIN)


def fetch_google(title: str, author: str) -> dict[str, Any] | None:
    return fetch_plugin(title, author, GOOGLE_PLUGIN)
