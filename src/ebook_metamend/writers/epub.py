"""EPUB metadata through the zip module.

The archive is copied member by member in its original order with its original
compression, and only the OPF bytes change. That keeps ``mimetype`` first and
stored, which rebuilding the archive from scratch tends to lose, and it keeps
every other member byte-identical.

Inside the OPF only the metadata element is touched. Namespace prefixes are
read off the document and registered before serialising so ``dc:`` stays
``dc:`` rather than becoming ``ns0:``.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from .. import opf
from ..calibre import opf_name, read_limited

_DECLARATION = re.compile(r'^\s*<\?xml[^>]*\?>')


def _register_prefixes(xml: str) -> None:
    for _event, (prefix, uri) in ET.iterparse(io.StringIO(xml), events=('start-ns',)):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            # ns0-style prefixes are reserved by ElementTree; it will invent one.
            pass


def _is_epub3(root: ET.Element) -> bool:
    return (root.get('version') or '2').strip().startswith('3')


def _child(parent: ET.Element, tag: str) -> ET.Element:
    """The first child with this tag, appended if there is none."""
    found = parent.find(tag)
    if found is None:
        found = ET.SubElement(parent, tag)
    return found


def edit(xml: str, gains: dict[str, Any], merged: dict[str, Any]) -> str:
    """The OPF text with the gains applied. Pure, so it is testable on a string."""
    _register_prefixes(xml)
    root = ET.fromstring(xml)
    metadata = root.find(f'{opf.OPF}metadata')
    if metadata is None:
        metadata = root.find('metadata')
    if metadata is None:
        raise ValueError('the OPF has no metadata element')

    if 'title' in gains:
        _child(metadata, f'{opf.DC}title').text = gains['title']
    for tag in gains.get('tags', []):
        ET.SubElement(metadata, f'{opf.DC}subject').text = tag
    if 'description' in gains:
        _child(metadata, f'{opf.DC}description').text = gains['description']
    if 'publisher' in gains:
        _child(metadata, f'{opf.DC}publisher').text = gains['publisher']
    if 'isbn' in gains:
        identifier = ET.SubElement(metadata, f'{opf.DC}identifier')
        # Each EPUB version has its own way of saying ISBN, and readers know both.
        if _is_epub3(root):
            identifier.text = f'urn:isbn:{gains["isbn"]}'
        else:
            identifier.set(f'{opf.OPF}scheme', 'ISBN')
            identifier.text = gains['isbn']
    if 'series' in gains:
        ET.SubElement(metadata, f'{opf.OPF}meta', name='calibre:series', content=gains['series'])
        if merged.get('sidx'):
            ET.SubElement(
                metadata,
                f'{opf.OPF}meta',
                name='calibre:series_index',
                content=str(merged['sidx']),
            )

    declaration = _DECLARATION.match(xml)
    body = ET.tostring(root, encoding='unicode')
    return (declaration.group(0) + '\n' if declaration else '') + body


def write(path: str, gains: dict[str, Any], merged: dict[str, Any]) -> tuple[bool, str]:
    """Add the gains to the EPUB in place. Returns (ok, reason).

    A sibling temporary archive is built, read back through the same parser the
    tool uses everywhere, and only then moved over the original.
    """
    if not gains:
        return True, ''
    tmp = None
    try:
        with zipfile.ZipFile(path) as source:
            name = opf_name(source)
            if name is None:
                return False, 'no OPF in the archive'
            new_opf = edit(read_limited(source, name).decode('utf8'), gains, merged).encode('utf8')
            fd, tmp = tempfile.mkstemp(suffix='.epub', dir=os.path.dirname(path) or '.')
            with os.fdopen(fd, 'wb') as out, zipfile.ZipFile(out, 'w') as target:
                for info in source.infolist():
                    if info.filename == name:
                        data = new_opf
                    else:
                        data = source.read(info)
                    # mimetype is stored by the spec; everything else keeps its own.
                    if info.filename == 'mimetype':
                        info.compress_type = zipfile.ZIP_STORED
                    target.writestr(info, data)
        with zipfile.ZipFile(tmp) as check:
            if check.testzip() is not None:
                raise ValueError('the rebuilt archive failed its CRC check')
            root = ET.fromstring(read_limited(check, name).decode('utf8'))
        after = opf.parse_root(root)
        for field in ('title', 'description', 'publisher', 'isbn'):
            if field in gains and after.get(field) != gains[field]:
                raise ValueError(f'{field} did not read back')
        os.replace(tmp, path)
    except Exception as error:  # noqa: BLE001 - the reason goes back to the caller
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False, f'{type(error).__name__}: {error}'
    return True, ''
