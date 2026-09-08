"""Kobo and Google Books, reached through Calibre's metadata plugins.

Using Calibre's plugins rather than the APIs directly is what takes the source
count from a couple to several without any API keys.
"""

from __future__ import annotations

from typing import Any

from .. import calibre, opf
from .errors import SourceUnavailable

#: Calibre plugin names, as ``fetch-ebook-metadata -p`` expects them.
KOBO_PLUGIN = 'Kobo Metadata'
GOOGLE_PLUGIN = 'Google'

DEFAULT_TIMEOUT = 18


def require_plugin(plugin: str) -> None:
    """Refuse to pretend a missing plugin simply had no answer.

    Fails open when the plugin list is empty, because that means the listing
    itself did not work (calibre-customize missing, or output we could not
    parse). Guessing "unavailable" from a failed probe would be worse than
    trying and getting a real error.
    """
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
