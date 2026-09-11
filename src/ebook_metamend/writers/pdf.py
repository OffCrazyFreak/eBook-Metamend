"""PDF metadata through pypdf.

Calibre keeps the interesting fields in the XMP packet, not the Info
dictionary: description, publisher, subjects, the ISBN (an ``xmp:Identifier``
with scheme ``isbn``) and the series (``calibre:series`` holding an
``rdf:value`` and a ``calibreSI:series_index``). The Info dictionary carries
only ``/Title``, ``/Author`` and ``/Keywords``. Both are written so Calibre and
plain PDF readers see the same record.

Writing is incremental: the original bytes stay a prefix of the new file and
only the changed objects plus a new cross-reference section are appended.
That is the whole reason pypdf is the one allowed dependency. A file whose
cross-reference table pypdf cannot follow gets a full rewrite instead.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any
from xml.dom import minidom

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, TextStringObject
from pypdf.xmp import XmpInformation

CALIBRE_NS = 'http://calibre-ebook.com/xmp-namespace'
CALIBRE_SI_NS = 'http://calibre-ebook.com/xmp-namespace-series-index'
XMP_NS = 'http://ns.adobe.com/xap/1.0/'
XMPIDQ_NS = 'http://ns.adobe.com/xmp/Identifier/qual/1.0/'
RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'

#: Calibre joins tags into /Keywords with this, and splits on it when reading.
KEYWORD_SEPARATOR = ', '


def _text(node: minidom.Element) -> str:
    return ''.join(
        child.data for child in node.childNodes if child.nodeType == child.TEXT_NODE
    ).strip()


def _first_lang(values: dict[str, str] | None) -> str:
    """The x-default entry of a language alternative, or whatever is first."""
    if not values:
        return ''
    return (values.get('x-default') or next(iter(values.values()), '')).strip()


def _series(xmp: XmpInformation) -> tuple[str | None, str | None]:
    for node in xmp.get_element('', CALIBRE_NS, 'series'):
        name = index = None
        for child in node.childNodes:
            if child.nodeType != child.ELEMENT_NODE:
                continue
            if child.namespaceURI == RDF_NS and child.localName == 'value':
                name = _text(child)
            if child.namespaceURI == CALIBRE_SI_NS and child.localName == 'series_index':
                index = _text(child)
        if name:
            return name, index
    return None, None


def _isbn(xmp: XmpInformation) -> str:
    for ident in xmp.get_element('', XMP_NS, 'Identifier'):
        for li in ident.getElementsByTagNameNS(RDF_NS, 'li'):
            scheme = value = ''
            for child in li.childNodes:
                if child.nodeType != child.ELEMENT_NODE:
                    continue
                if child.namespaceURI == XMPIDQ_NS and child.localName == 'Scheme':
                    scheme = _text(child).lower()
                if child.namespaceURI == RDF_NS and child.localName == 'value':
                    value = _text(child)
            if scheme == 'isbn' and value:
                return value
    return ''


def read(path: str) -> dict[str, Any] | None:
    """A record shaped like ``opf.parse``. ``None`` when the file cannot be read.

    XMP wins over the Info dictionary field by field, which is the order Calibre
    uses, so the values match what ``ebook-meta --to-opf`` reported before.
    """
    try:
        reader = PdfReader(path)
        info = reader.metadata or {}
        xmp = reader.xmp_metadata
    except Exception:  # noqa: BLE001 - pypdf raises a wide family for a broken file
        return None

    def info_str(key: str) -> str:
        value = info.get(key)
        return str(value).strip() if value is not None else ''

    record: dict[str, Any] = {
        'title': info_str('/Title'),
        'authors': [info_str('/Author')] if info_str('/Author') else [],
        'publisher': '',
        'description': '',
        'tags': [t.strip() for t in info_str('/Keywords').split(',') if t.strip()],
        'series': None,
        'sidx': None,
        'isbn': '',
    }
    if xmp is None:
        return record
    try:
        title = _first_lang(xmp.dc_title)
        if title:
            record['title'] = title
        creators = [c.strip() for c in (xmp.dc_creator or []) if c and c.strip()]
        if creators:
            record['authors'] = creators
        record['publisher'] = next((p.strip() for p in (xmp.dc_publisher or []) if p.strip()), '')
        record['description'] = _first_lang(xmp.dc_description)
        subjects = [s.strip() for s in (xmp.dc_subject or []) if s and s.strip()]
        if subjects:
            record['tags'] = subjects
        record['series'], record['sidx'] = _series(xmp)
        record['isbn'] = _isbn(xmp)
    except Exception:  # noqa: BLE001 - a malformed packet is not a missing book
        pass
    return record


def _description_node(xmp: XmpInformation, namespace: str, prefix: str) -> minidom.Element:
    """The rdf:Description that declares a namespace, created if absent."""
    for desc in xmp.rdf_root.getElementsByTagNameNS(RDF_NS, 'Description'):
        if desc.getAttribute(f'xmlns:{prefix}') == namespace:
            return desc
    doc = xmp.rdf_root.ownerDocument
    desc = doc.createElementNS(RDF_NS, 'rdf:Description')
    desc.setAttribute(f'xmlns:{prefix}', namespace)
    desc.setAttributeNS(RDF_NS, 'rdf:about', '')
    xmp.rdf_root.appendChild(desc)
    return desc


def _remove_children(parent: minidom.Element, namespace: str, local: str) -> None:
    for node in list(parent.childNodes):
        if (
            node.nodeType == node.ELEMENT_NODE
            and node.namespaceURI == namespace
            and node.localName == local
        ):
            parent.removeChild(node)


def _set_series(xmp: XmpInformation, name: str, index: str | None) -> None:
    doc = xmp.rdf_root.ownerDocument
    desc = _description_node(xmp, CALIBRE_NS, 'calibre')
    desc.setAttribute('xmlns:calibreSI', CALIBRE_SI_NS)
    _remove_children(desc, CALIBRE_NS, 'series')
    series = doc.createElementNS(CALIBRE_NS, 'calibre:series')
    series.setAttributeNS(RDF_NS, 'rdf:parseType', 'Resource')
    value = doc.createElementNS(RDF_NS, 'rdf:value')
    value.appendChild(doc.createTextNode(name))
    series.appendChild(value)
    if index:
        si = doc.createElementNS(CALIBRE_SI_NS, 'calibreSI:series_index')
        si.appendChild(doc.createTextNode(str(index)))
        series.appendChild(si)
    desc.appendChild(series)


def _set_isbn(xmp: XmpInformation, isbn: str) -> None:
    doc = xmp.rdf_root.ownerDocument
    desc = _description_node(xmp, XMP_NS, 'xmp')
    desc.setAttribute('xmlns:xmpidq', XMPIDQ_NS)
    ident = next(iter(desc.getElementsByTagNameNS(XMP_NS, 'Identifier')), None)
    if ident is None:
        ident = doc.createElementNS(XMP_NS, 'xmp:Identifier')
        desc.appendChild(ident)
    bag = next(iter(ident.getElementsByTagNameNS(RDF_NS, 'Bag')), None)
    if bag is None:
        bag = doc.createElementNS(RDF_NS, 'rdf:Bag')
        ident.appendChild(bag)
    # read() takes the first isbn entry, so a stale one must not stay in front.
    for old in list(bag.getElementsByTagNameNS(RDF_NS, 'li')):
        schemes = old.getElementsByTagNameNS(XMPIDQ_NS, 'Scheme')
        if any(_text(s) == 'isbn' for s in schemes):
            bag.removeChild(old)
    li = doc.createElementNS(RDF_NS, 'rdf:li')
    li.setAttributeNS(RDF_NS, 'rdf:parseType', 'Resource')
    scheme = doc.createElementNS(XMPIDQ_NS, 'xmpidq:Scheme')
    scheme.appendChild(doc.createTextNode('isbn'))
    value = doc.createElementNS(RDF_NS, 'rdf:value')
    value.appendChild(doc.createTextNode(isbn))
    li.appendChild(scheme)
    li.appendChild(value)
    bag.appendChild(li)


def _apply(writer: PdfWriter, gains: dict[str, Any], merged: dict[str, Any]) -> None:
    info: dict[str, Any] = {}
    if 'title' in gains:
        info[NameObject('/Title')] = TextStringObject(gains['title'])
    if 'authors' in gains:
        info[NameObject('/Author')] = TextStringObject(' & '.join(gains['authors']))
    if 'tags' in gains:
        info[NameObject('/Keywords')] = TextStringObject(KEYWORD_SEPARATOR.join(gains['tags']))
    if info:
        writer.add_metadata(info)

    xmp = writer.xmp_metadata
    if xmp is None:
        xmp = XmpInformation.create()
        writer.xmp_metadata = xmp
        xmp = writer.xmp_metadata
    if 'title' in gains:
        xmp.dc_title = {'x-default': gains['title']}
    if 'authors' in gains:
        xmp.dc_creator = list(gains['authors'])
    if 'tags' in gains:
        xmp.dc_subject = list(gains['tags'])
    if 'description' in gains:
        xmp.dc_description = {'x-default': gains['description']}
    if 'publisher' in gains:
        xmp.dc_publisher = [gains['publisher']]
    if 'isbn' in gains:
        _set_isbn(xmp, gains['isbn'])
    if 'series' in gains:
        _set_series(xmp, gains['series'], merged.get('sidx'))
    # The dc setters serialise for us; the raw DOM edits above need it done once.
    xmp._update_stream()


def write(path: str, gains: dict[str, Any], merged: dict[str, Any]) -> tuple[bool, str]:
    """Add the gains to the PDF in place. Returns (ok, reason).

    Incremental when pypdf can follow the file's cross-reference chain, a full
    rewrite otherwise. The result is read back before it replaces the original,
    and an incremental result must still start with the original bytes.
    """
    if not gains:
        return True, ''
    with open(path, 'rb') as fh:
        original = fh.read()
    incremental = True
    tmp = None
    try:
        try:
            writer = PdfWriter(path, incremental=True)
        except PdfReadError:
            incremental = False
            writer = PdfWriter(clone_from=path)
        _apply(writer, gains, merged)
        pages = len(writer.pages)
        fd, tmp = tempfile.mkstemp(suffix='.pdf', dir=os.path.dirname(path) or '.')
        with os.fdopen(fd, 'wb') as out:
            writer.write(out)
        check = PdfReader(tmp)
        if len(check.pages) != pages:
            raise ValueError(f'page count changed: {pages} to {len(check.pages)}')
        if incremental:
            with open(tmp, 'rb') as fh:
                if fh.read(len(original)) != original:
                    raise ValueError('incremental write did not keep the original bytes')
        # mkstemp creates 0600; the book keeps whatever access it had.
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except Exception as error:  # noqa: BLE001 - the reason goes back to the caller
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False, f'{type(error).__name__}: {error}'
    return True, '' if incremental else 'rewritten'
