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


class SourceUnavailable(RuntimeError):
    """A configured plugin is not installed, so this source cannot answer.

    Raised rather than returning None. Silence here looks exactly like "no such
    book", which is how a missing plugin went unnoticed while every decision was
    quietly made on a single source.
    """


def require_plugin(plugin: str) -> None:
    available = calibre.installed_metadata_plugins()
    if available and plugin not in available:
        raise SourceUnavailable(
            f'the {plugin!r} metadata plugin is not installed. '
            f'Install it with: calibre-customize -a <plugin>.zip'
        )


def fetch_plugin(
    title: str, author: str, plugin: str, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any] | None:
    require_plugin(plugin)
    xml = calibre.fetch_metadata(title, author, plugin, timeout)
    return opf.parse(xml) if xml else None


def fetch_kobo(title: str, author: str) -> dict[str, Any] | None:
    return fetch_plugin(title, author, KOBO_PLUGIN)


def fetch_google(title: str, author: str) -> dict[str, Any] | None:
    return fetch_plugin(title, author, GOOGLE_PLUGIN)
