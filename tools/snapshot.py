#!/usr/bin/env python3
"""Snapshot a library tree, and compare two snapshots.

Replaces the old finalcheck.py / titlediff.py pair, which could only run while a
backup directory existed, never actually compared EPUB content (zip CRC only, so
a wholly replaced EPUB passed), compared PDF text by character *count*, and could
not see added or removed files at all.

Snapshot before a run, snapshot after, compare. No backup tree required.

    python3 tools/snapshot.py take   <root> <out.json>
    python3 tools/snapshot.py compare <before.json> <after.json>
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

DC = '{http://purl.org/dc/elements/1.1/}'
CAL_ROOT = os.environ.get('CAL_ROOT', '/tmp/cal')

# Fields that describe the book, versus the bytes that are the book. A change to
# the first set is the tool doing its job; a change to the second set is damage.
META_FIELDS = ('title', 'authors', 'tags', 'publisher', 'isbn', 'series', 'description_len')
CONTENT_FIELDS = ('text_sha256', 'page_count', 'zip_ok')


def _norm_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def _epub(path: str) -> dict:
    out = {'format': 'epub', 'zip_ok': False}
    try:
        z = zipfile.ZipFile(path)
        out['zip_ok'] = z.testzip() is None
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out

    try:
        opf = next(n for n in z.namelist() if n.lower().endswith('.opf'))
        root = ET.fromstring(z.read(opf).decode('utf8', 'ignore'))

        def g(tag):
            return [(e.text or '').strip() for e in root.iter(DC + tag) if (e.text or '').strip()]

        out['title'] = (g('title') or [''])[0]
        out['authors'] = g('creator')
        out['tags'] = g('subject')
        out['publisher'] = (g('publisher') or [''])[0]
        out['description_len'] = len((g('description') or [''])[0])
        out['isbn'] = next(
            (t.split(':', 1)[1] for t in g('identifier') if t.lower().startswith('isbn:')), ''
        )
        out['series'] = next(
            (
                m.get('content')
                for m in root.iter('{http://www.idpf.org/2007/opf}meta')
                if m.get('name') == 'calibre:series'
            ),
            None,
        )
    except Exception as e:
        out['meta_error'] = f'{type(e).__name__}: {e}'

    # Content hash: every text document, not a character count.
    try:
        h = hashlib.sha256()
        for n in sorted(z.namelist()):
            if n.lower().endswith(('.xhtml', '.html', '.htm')):
                text = re.sub(r'<[^>]+>', ' ', z.read(n).decode('utf8', 'ignore'))
                h.update(_norm_text(text).encode('utf8'))
        out['text_sha256'] = h.hexdigest()
    except Exception as e:
        out['text_error'] = f'{type(e).__name__}: {e}'
    return out


def _pdf(path: str) -> dict:
    out = {'format': 'pdf'}
    # One pdfinfo call, not the three the old finalcheck.py spawned per file.
    try:
        r = subprocess.run(['pdfinfo', path], capture_output=True, text=True, timeout=60)
        out['syntax_error'] = 'Syntax Error' in r.stderr
        info = {}
        for line in r.stdout.splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                info[k.strip()] = v.strip()
        out['page_count'] = int(info.get('Pages', 0) or 0)
        out['title'] = info.get('Title', '')
        out['authors'] = [a for a in [info.get('Author', '')] if a]
        out['tags'] = [t.strip() for t in info.get('Keywords', '').split(',') if t.strip()]
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
        return out

    try:
        r = subprocess.run(['pdftotext', path, '-'], capture_output=True, text=True, timeout=180)
        out['text_sha256'] = hashlib.sha256(_norm_text(r.stdout).encode('utf8')).hexdigest()
    except Exception as e:
        out['text_error'] = f'{type(e).__name__}: {e}'
    return out


def take(root: str) -> dict:
    snap = {}
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(dirpath, f)
            ext = os.path.splitext(f)[1].lower()
            if ext not in ('.epub', '.pdf'):
                continue
            rec = _epub(p) if ext == '.epub' else _pdf(p)
            rec['size'] = os.path.getsize(p)
            snap[os.path.relpath(p, root)] = rec
    return snap


def compare(before: dict, after: dict) -> dict:
    """Classify every path. Walks the union, so additions and removals are visible."""
    result = {
        'added': [],
        'removed': [],
        'unchanged': [],
        'meta_changed': [],
        'content_changed': [],
        'corrupt': [],
    }
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        if b is None:
            result['added'].append(path)
            continue
        if a is None:
            result['removed'].append(path)
            continue

        if a.get('error') or a.get('syntax_error') or a.get('zip_ok') is False:
            result['corrupt'].append(path)
            continue

        content_diff = {
            f: (b.get(f), a.get(f)) for f in CONTENT_FIELDS if f in b and b.get(f) != a.get(f)
        }
        if content_diff:
            result['content_changed'].append({'path': path, 'diff': content_diff})
            continue

        meta_diff = {
            f: (b.get(f), a.get(f)) for f in META_FIELDS if f in b and b.get(f) != a.get(f)
        }
        if meta_diff:
            result['meta_changed'].append({'path': path, 'diff': meta_diff})
        else:
            result['unchanged'].append(path)
    return result


def _print_report(r: dict) -> None:
    print(
        f"unchanged {len(r['unchanged'])} | meta-changed {len(r['meta_changed'])} | "
        f"content-changed {len(r['content_changed'])} | corrupt {len(r['corrupt'])} | "
        f"added {len(r['added'])} | removed {len(r['removed'])}"
    )
    for key in ('corrupt', 'added', 'removed'):
        for p in r[key]:
            print(f'  {key.upper():<16} {p}')
    for item in r['content_changed']:
        print(f"  CONTENT-CHANGED  {item['path']}")
        for f, (was, now) in item['diff'].items():
            print(f'      {f}: {str(was)[:40]} -> {str(now)[:40]}')
    for item in r['meta_changed']:
        print(f"  meta-changed     {item['path']}")
        for f, (was, now) in item['diff'].items():
            print(f'      {f}: {str(was)[:60]} -> {str(now)[:60]}')


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == 'take':
        root, out = sys.argv[2], sys.argv[3]
        snap = take(root)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, 'w') as fh:
            json.dump(snap, fh, indent=1, sort_keys=True, ensure_ascii=False)
        print(f'snapshot: {len(snap)} files -> {out}')
        return 0
    if cmd == 'compare':
        with open(sys.argv[2]) as fh:
            before = json.load(fh)
        with open(sys.argv[3]) as fh:
            after = json.load(fh)
        r = compare(before, after)
        _print_report(r)
        return 1 if (r['corrupt'] or r['content_changed']) else 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
