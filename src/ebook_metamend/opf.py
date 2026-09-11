"""One OPF parser, replacing three that disagreed.

The three originals differed in ways a naive merge would have silently changed:

- Failure contract: ``{}``, ``None`` and ``{'error': ...}``. A caller testing
  ``if not meta`` behaved differently against each. This module always returns
  ``None`` on failure and callers add their own ``or {}`` where they want it.
- Field set: only one read ``series``/``series_index``; only one read ``isbn``;
  ``extract.py`` returned ``desc_len`` rather than ``description``. Unified to a
  superset, so no caller loses a field.
- ISBN detection: ``1_epub_to_pdf.py`` accepted a bare ``97[89]``-prefixed
  13-digit identifier, ``2_online_enrich.py`` accepted only an ``isbn:`` prefix.
  That difference is preserved behind ``bare_isbn_fallback`` rather than quietly
  resolved, because turning it on changes which books gain an ISBN.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

DC = '{http://purl.org/dc/elements/1.1/}'
OPF = '{http://www.idpf.org/2007/opf}'

#: ``ebook-meta --to-opf`` writes log lines around the XML, so the package
#: element has to be cut out before ElementTree will accept it.
_PACKAGE = re.compile(r'<package\b.*?</package>', re.S)
_BARE_ISBN13 = re.compile(r'97[89]\d{10}')


def dc_values(root: ET.Element, tag: str) -> list[str]:
    """Every non-empty Dublin Core value for a tag. Triplicated in the originals."""
    return [(e.text or '').strip() for e in root.iter(DC + tag) if (e.text or '').strip()]


def parse_root(root: ET.Element, *, bare_isbn_fallback: bool = False) -> dict[str, Any]:
    """Build the metadata record from an already-parsed OPF root element."""
    record: dict[str, Any] = {
        'title': (dc_values(root, 'title') or [''])[0],
        'authors': dc_values(root, 'creator'),
        'publisher': (dc_values(root, 'publisher') or [''])[0],
        'description': (dc_values(root, 'description') or [''])[0],
        'tags': dc_values(root, 'subject'),
        'series': None,
        'sidx': None,
        'isbn': '',
    }
    for meta in root.iter(OPF + 'meta'):
        if meta.get('name') == 'calibre:series':
            record['series'] = meta.get('content')
        if meta.get('name') == 'calibre:series_index':
            record['sidx'] = meta.get('content')

    for element in root.iter(DC + 'identifier'):
        text = (element.text or '').strip()
        lowered = text.lower()
        scheme = (element.get(OPF + 'scheme') or element.get('scheme') or '').lower()
        # Three spellings of the same thing: Calibre's isbn:, EPUB 3's urn:isbn:
        # and EPUB 2's scheme attribute with a bare number.
        if lowered.startswith('urn:isbn:'):
            record['isbn'] = text.split(':', 2)[2]
        elif lowered.startswith('isbn:'):
            record['isbn'] = text.split(':', 1)[1]
        elif scheme == 'isbn' and text:
            record['isbn'] = text
        elif bare_isbn_fallback and _BARE_ISBN13.fullmatch(text.replace('-', '')):
            record['isbn'] = text
    return record


def parse(xml: str, *, bare_isbn_fallback: bool = False) -> dict[str, Any] | None:
    """Parse OPF text, tolerating surrounding log noise. ``None`` if unusable."""
    match = _PACKAGE.search(xml)
    if not match:
        return None
    try:
        root = ET.fromstring(match.group(0))
    except ET.ParseError:
        return None
    return parse_root(root, bare_isbn_fallback=bare_isbn_fallback)
