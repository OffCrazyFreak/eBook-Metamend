"""Calibre command line wrappers, plus the zip-level EPUB reader.

Calibre is only asked for what nothing else can give: its metadata source
plugins (Kobo, Google Books) and their plugin list. Reading and writing the
books themselves is native now, in ``writers``; spawning a subprocess per book
cost about 0.47 s against 0.0013 s for reading the OPF out of the zip directly.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import time
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from . import opf
from .config import CAL_ROOT, FETCH_METADATA, calibre_env

#: Pause between source retries. Kept as the original fixed value for now;
#: adaptive backoff is a deliberate later change.
RETRY_PAUSE = 5


#: An EPUB is an untrusted archive. A metadata file has no legitimate reason to
#: be large, so refuse to expand one that is, rather than decompressing whatever
#: a crafted file claims (CWE-409).
MAX_METADATA_BYTES = 8 * 1024 * 1024

CONTAINER = 'META-INF/container.xml'
_CONTAINER_NS = '{urn:oasis:names:tc:opendocument:xmlns:container}'


def read_limited(archive: zipfile.ZipFile, name: str) -> bytes:
    """Read a member, refusing one that expands beyond MAX_METADATA_BYTES."""
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA_BYTES:
        raise ValueError(f'{name} expands to {info.file_size} bytes, refusing to read')
    with archive.open(name) as handle:
        data = handle.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError(f'{name} exceeds {MAX_METADATA_BYTES} bytes, refusing to read')
    return data


def opf_name(archive: zipfile.ZipFile) -> str | None:
    """The OPF an EPUB actually declares.

    An EPUB may contain several .opf members, and zip order is not meaningful, so
    picking the first one can read a different package than the reader does. The
    container declares the real one; falling back to the first .opf only when the
    container is missing or unreadable.
    """
    try:
        container = ET.fromstring(read_limited(archive, CONTAINER).decode('utf8', 'ignore'))
        rootfile = container.find(f'.//{_CONTAINER_NS}rootfile')
        declared = rootfile is not None and rootfile.get('full-path')
        if declared and declared in archive.namelist():
            return declared
    except (KeyError, ValueError, ET.ParseError):
        pass
    return next((n for n in archive.namelist() if n.lower().endswith('.opf')), None)


@functools.lru_cache(maxsize=1)
def installed_metadata_plugins() -> frozenset[str]:
    """Names of the metadata source plugins Calibre can actually use.

    Worth checking, because ``fetch-ebook-metadata -p`` accepts a plugin name it
    does not have, runs with no plugins at all, burns its full timeout and exits
    successfully with no results. That is indistinguishable from "the book is not
    in this catalogue" unless you ask.
    """
    customize = os.path.join(CAL_ROOT, 'bin', 'calibre-customize')
    try:
        result = subprocess.run(
            [customize, '--list-plugins'],
            capture_output=True,
            text=True,
            timeout=120,
            env=calibre_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    names = set()
    for line in result.stdout.splitlines():
        if line.startswith('Metadata source'):
            # "Metadata source   <name>   (1, 2, 3)   False"
            rest = line[len('Metadata source') :].strip()
            names.add(re.split(r'\s{2,}', rest)[0].strip())
    return frozenset(names)


def read_epub_metadata(path: str, *, bare_isbn_fallback: bool = False) -> dict[str, Any] | None:
    """Read an EPUB's OPF straight out of the zip.

    Roughly 350x faster than asking Calibre because it spawns nothing.
    """
    try:
        with zipfile.ZipFile(path) as z:
            name = opf_name(z)
            if name is None:
                return None
            root = ET.fromstring(read_limited(z, name).decode('utf8', 'ignore'))
    except (OSError, KeyError, ValueError, StopIteration, zipfile.BadZipFile, ET.ParseError):
        return None
    return opf.parse_root(root, bare_isbn_fallback=bare_isbn_fallback)


def fetch_metadata(
    title: str, author: str, plugin: str, timeout: int, *, retries: int = 1
) -> str | None:
    """Ask one Calibre metadata plugin about a book. Returns raw OPF text.

    Parsing is left to the caller so a recorded response can be replayed.
    """
    for _attempt in range(retries + 1):
        try:
            result = subprocess.run(
                [
                    FETCH_METADATA,
                    '-t',
                    title,
                    '-a',
                    author,
                    '-p',
                    plugin,
                    '-o',
                    '-d',
                    str(timeout),
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 20,
                env=calibre_env(),
            )
        except subprocess.TimeoutExpired:
            time.sleep(RETRY_PAUSE)
            continue
        if '<package' in result.stdout:
            return result.stdout
        time.sleep(RETRY_PAUSE)
    return None


def read_book_metadata(path: str, *, bare_isbn_fallback: bool = False) -> dict[str, Any] | None:
    """Read a book's embedded metadata without spawning anything.

    EPUBs are read straight from the zip, PDFs through pypdf. Both are more
    faithful than Calibre's ``--to-opf`` was: that normalised on the way out,
    dropping the series index and splitting tags on commas before you ever saw
    them.
    """
    if path.lower().endswith('.epub'):
        return read_epub_metadata(path, bare_isbn_fallback=bare_isbn_fallback)
    from .writers import pdf

    return pdf.read(path)
