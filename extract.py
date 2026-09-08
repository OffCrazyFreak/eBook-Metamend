#!/usr/bin/env python3
"""For every book: filename, embedded metadata, and text pulled from the opening pages.
Writes one JSON per top-level folder for review."""

import html
import json
import os
import re
import subprocess
import zipfile
from xml.etree import ElementTree as ET

LIB = os.environ.get('EBOOK_LIBRARY', os.path.expanduser('~/eBooks'))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spotcheck')
DC = '{http://purl.org/dc/elements/1.1/}'
OPF = '{http://www.idpf.org/2007/opf}'


def epub_meta_and_text(p):
    meta = {}
    text = ''
    try:
        z = zipfile.ZipFile(p)
        names = z.namelist()
        opf = [n for n in names if n.lower().endswith('.opf')]
        if opf:
            blob = z.read(opf[0]).decode('utf8', 'ignore')
            r = ET.fromstring(blob)

            def g(t):
                return [(e.text or '').strip() for e in r.iter(DC + t) if (e.text or '').strip()]

            meta = {
                'title': (g('title') or [''])[0],
                'authors': g('creator'),
                'publisher': (g('publisher') or [''])[0],
                'tags': g('subject'),
                'desc_len': len((g('description') or [''])[0]),
                'series': None,
            }
            for m in r.iter(OPF + 'meta'):
                if m.get('name') == 'calibre:series':
                    meta['series'] = m.get('content')
        docs = [n for n in names if n.lower().endswith(('.xhtml', '.html', '.htm'))]
        docs.sort()
        for n in docs[:6]:
            raw = z.read(n).decode('utf8', 'ignore')
            raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', raw, flags=re.S | re.I)
            t = html.unescape(re.sub(r'<[^>]+>', ' ', raw))
            t = re.sub(r'\s+', ' ', t).strip()
            if len(t) > 40:
                text += ' ' + t
            if len(text) > 1600:
                break
    except Exception as e:
        meta = {'error': str(e)[:60]}
    return meta, text[:1600]


def pdf_meta_and_text(p):
    meta = {}
    text = ''
    try:
        out = subprocess.run(['pdfinfo', p], capture_output=True, text=True, timeout=40).stdout
        for l in out.splitlines():
            if ':' in l:
                k, v = l.split(':', 1)
                meta[k.strip()] = v.strip()
        text = subprocess.run(
            ['pdftotext', '-f', '1', '-l', '6', p, '-'], capture_output=True, text=True, timeout=90
        ).stdout
        text = re.sub(r'\s+', ' ', text).strip()[:1600]
    except Exception as e:
        meta = {'error': str(e)[:60]}
    return meta, text


folders = {}
for r, _, fs in os.walk(LIB):
    for f in sorted(fs):
        p = os.path.join(r, f)
        rel = os.path.relpath(p, LIB)
        top = rel.split(os.sep)[0]
        stem, ext = os.path.splitext(f)
        fauthor, _, ftitle = stem.partition(' - ')
        rec = {
            'file': rel,
            'ext': ext.lower(),
            'filename_author': fauthor,
            'filename_title': ftitle or stem,
        }
        if ext.lower() == '.epub':
            m, t = epub_meta_and_text(p)
        elif ext.lower() == '.pdf':
            m, t = pdf_meta_and_text(p)
        else:
            continue
        rec['embedded'] = m
        rec['content_opening'] = t
        rec['content_chars'] = len(t)
        folders.setdefault(top, []).append(rec)
        print(f"  {rel[:78]}", flush=True)

os.makedirs(OUT, exist_ok=True)
for k, v in folders.items():
    safe = re.sub(r'[^A-Za-z0-9]+', '_', k).strip('_')
    json.dump(v, open(os.path.join(OUT, f"{safe}.json"), 'w'), indent=1, ensure_ascii=False)
    print(f"WROTE {safe}.json  ({len(v)} files)")
print("DONE")
