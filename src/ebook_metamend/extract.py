"""Dump what every book actually contains, for auditing a library by eye.

Writes one JSON per top-level category: the filename's claim, the embedded
metadata, and the opening text. Useful for spotting books whose metadata and
contents disagree, which no automated score reliably catches.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from . import calibre, opf
from .config import LIBRARY
from .library import parse_filename

#: Enough opening text to recognise a book, not enough to be a copy of it.
TEXT_LIMIT = 1600
MAX_DOCUMENTS = 6
PDF_PAGES = 6

_SCRIPT_OR_STYLE = re.compile(r'<(script|style)[^>]*>.*?</\1>', re.S | re.I)
_TAG = re.compile(r'<[^>]+>')
_UNSAFE = re.compile(r'[^A-Za-z0-9]+')


def epub_meta_and_text(path: str) -> tuple[dict[str, Any], str]:
    meta: dict[str, Any] = {}
    text = ''
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
        opf_name = calibre.opf_name(z)
        if opf_name:
            root = ET.fromstring(calibre.read_limited(z, opf_name).decode('utf8', 'ignore'))
            record = opf.parse_root(root)
            meta = {
                'title': record['title'],
                'authors': record['authors'],
                'publisher': record['publisher'],
                'tags': record['tags'],
                'desc_len': len(record['description']),
                'series': record['series'],
            }
        documents = sorted(n for n in names if n.lower().endswith(('.xhtml', '.html', '.htm')))
        for name in documents[:MAX_DOCUMENTS]:
            # Bounded like the OPF above: an EPUB is an untrusted archive and a
            # deflate-bombed chapter would otherwise be expanded in full. Caught
            # per document, because the loop sits inside the outer try and one
            # refused chapter would otherwise discard the metadata already parsed.
            try:
                data = calibre.read_limited(z, name)
            except ValueError:
                continue
            raw = _SCRIPT_OR_STYLE.sub(' ', data.decode('utf8', 'ignore'))
            chunk = re.sub(r'\s+', ' ', html.unescape(_TAG.sub(' ', raw))).strip()
            if len(chunk) > 40:
                text += ' ' + chunk
            if len(text) > TEXT_LIMIT:
                break
    except Exception as exc:
        meta = {'error': str(exc)[:60]}
    return meta, text[:TEXT_LIMIT]


def pdf_meta_and_text(path: str) -> tuple[dict[str, Any], str]:
    meta: dict[str, Any] = {}
    text = ''
    try:
        # poppler, not Calibre, so deliberately without the Calibre environment.
        info = subprocess.run(['pdfinfo', path], capture_output=True, text=True, timeout=40)
        if info.returncode != 0:
            return {'error': f'pdfinfo exit {info.returncode}: {info.stderr.strip()[:60]}'}, ''
        for line in info.stdout.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                meta[key.strip()] = value.strip()
        dump = subprocess.run(
            ['pdftotext', '-f', '1', '-l', str(PDF_PAGES), path, '-'],
            capture_output=True,
            text=True,
            timeout=90,
        )
        # A nonzero exit means the text is partial or absent. Recording it as an
        # empty opening would look like a book with no extractable text, which is
        # a real and different condition worth telling apart.
        if dump.returncode != 0:
            meta['text_error'] = f'pdftotext exit {dump.returncode}'
        text = re.sub(r'\s+', ' ', dump.stdout).strip()[:TEXT_LIMIT]
    except Exception as exc:
        meta = {'error': str(exc)[:60]}
    return meta, text


def run(out_dir: str, root: str | None = None) -> list[tuple[str, int]]:
    """Write one JSON per top-level category. Returns (filename, count) pairs."""
    root = root or LIBRARY
    folders: dict[str, list[dict[str, Any]]] = {}

    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            ext = os.path.splitext(name)[1].lower()
            if ext not in ('.epub', '.pdf'):
                continue
            relative = os.path.relpath(path, root)
            facts = parse_filename(os.path.splitext(name)[0])
            meta, text = epub_meta_and_text(path) if ext == '.epub' else pdf_meta_and_text(path)
            folders.setdefault(relative.split(os.sep)[0], []).append(
                {
                    'file': relative,
                    'ext': ext,
                    'filename_author': facts.author,
                    'filename_title': facts.title or facts.stem,
                    'embedded': meta,
                    'content_opening': text,
                    'content_chars': len(text),
                }
            )

    os.makedirs(out_dir, exist_ok=True)
    written = []
    used: dict[str, str] = {}
    for category, records in folders.items():
        safe = _UNSAFE.sub('_', category).strip('_') or 'root'
        # "A & B" and "A - B" both flatten to "A_B", which would silently
        # overwrite one category's dump with another's.
        if used.setdefault(safe, category) != category:
            digest = hashlib.sha256(category.encode('utf8')).hexdigest()[:8]
            safe = f'{safe}_{digest}'
            used[safe] = category
        with open(os.path.join(out_dir, f'{safe}.json'), 'w', encoding='utf8') as fh:
            json.dump(records, fh, indent=1, ensure_ascii=False)
        written.append((f'{safe}.json', len(records)))
    return written
