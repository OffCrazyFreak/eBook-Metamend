#!/usr/bin/env python3
"""
Copy the richer EPUB metadata into its PDF twin, in place.
Local only, no network. Dry run by default; pass --apply to write.

Rules: only ever ADD or IMPROVE a PDF field. Never blank an existing value.
"""

import argparse
import os
import re
import subprocess
from xml.etree import ElementTree as ET

CAL_ROOT = os.environ.get('CAL_ROOT', '/tmp/cal')

CAL = CAL_ROOT + '/bin'
EM = os.path.join(CAL, 'ebook-meta')
LIB = os.environ.get('EBOOK_LIBRARY', os.path.expanduser('~/eBooks'))
env = dict(
    os.environ,
    CALIBRE_CONFIG_DIRECTORY=CAL_ROOT + '/config',
    QT_QPA_PLATFORM='offscreen',
    LD_LIBRARY_PATH=CAL_ROOT + '/lib',
    OPENSSL_MODULES=CAL_ROOT + '/lib/ossl-modules',
)
DC = '{http://purl.org/dc/elements/1.1/}'
OPF = '{http://www.idpf.org/2007/opf}'

# case-insensitive junk: file extensions and generic placeholders
JUNK_I = re.compile(r'\.(pdf|indd|qxd|doc|docx|tex)$|^(untitled|microsoft word|book\d*)$', re.I)
# case-SENSITIVE junk: short all-caps codes like NBRT_A01 (must not match 'Artemis')
JUNK_C = re.compile(r'^[A-Z0-9_\-]{1,14}$')


def run(args, t=90):
    return subprocess.run([EM] + args, capture_output=True, text=True, timeout=t, env=env)


def to_opf(path):
    """Read metadata as an OPF dict."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.opf', delete=False) as tf:
        tmp = tf.name
    try:
        run([path, '--to-opf', tmp])
        x = open(tmp, encoding='utf8', errors='ignore').read()
    finally:
        os.unlink(tmp)
    m = re.search(r'<package\b.*?</package>', x, re.S)
    if not m:
        return {}
    try:
        root = ET.fromstring(m.group(0))
    except Exception:
        return {}

    def g(t):
        return [(e.text or '').strip() for e in root.iter(DC + t) if (e.text or '').strip()]

    d = {
        'title': (g('title') or [''])[0],
        'authors': g('creator'),
        'publisher': (g('publisher') or [''])[0],
        'description': (g('description') or [''])[0],
        'tags': g('subject'),
        'isbn': '',
    }
    for e in root.iter(DC + 'identifier'):
        t = (e.text or '').strip()
        if t.lower().startswith('isbn:'):
            d['isbn'] = t.split(':', 1)[1]
        elif re.fullmatch(r'97[89]\d{10}', t.replace('-', '')):
            d['isbn'] = t
    return d


def junky(t):
    t = (t or '').strip()
    if not t:
        return True
    if re.search(r'\.(pdf|indd|qxd|doc|docx|tex)$', t, re.I):
        return True  # ends in a file extension
    if re.fullmatch(r'(untitled|microsoft word|book\d*)', t, re.I):
        return True
    if re.fullmatch(r'[A-Z0-9_\-]{1,14}', t):
        return True  # ALL-CAPS code, case sensitive
    return False


def pairs():
    seen = {}
    for r, _, fs in os.walk(LIB):
        for f in fs:
            s, e = os.path.splitext(f)
            seen.setdefault(s, {})[e.lower()] = os.path.join(r, f)
    return sorted(
        (s, v['.epub'], v['.pdf']) for s, v in seen.items() if '.epub' in v and '.pdf' in v
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()

    ps = pairs()
    if a.limit:
        ps = ps[: a.limit]
    print(
        f"{len(ps)} EPUB+PDF pairs\nmode: {'APPLY (writes to PDFs)' if a.apply else 'DRY RUN (no writes)'}\n"
    )

    changed = 0
    planned = {}
    for n, (_stem, ep, pd) in enumerate(ps, 1):
        e = to_opf(ep)
        p = to_opf(pd)
        if not e:
            continue
        ops = []
        args = []

        # title: take epub's if pdf is junk/empty or epub's is longer (has subtitle)
        # never copy a junk EPUB title onto the PDF (those books need the online path)
        if (
            e['title']
            and not junky(e['title'])
            and (junky(p['title']) or len(e['title']) > len(p['title']) + 3)
        ):
            ops.append(('title', p['title'], e['title']))
            args += ['-t', e['title']]
        # authors
        if e['authors'] and (not p['authors'] or p['authors'] in (['Unknown'], ['dam'])):
            v = ' & '.join(e['authors'])
            ops.append(('author', ', '.join(p['authors']) or '-', v))
            args += ['-a', v]
        # publisher / description / tags / isbn: only if PDF lacks them
        if e['publisher'] and not p['publisher']:
            ops.append(('publisher', '-', e['publisher']))
            args += ['--publisher', e['publisher']]
        if e['description'] and not p['description']:
            ops.append(('description', '-', f"{len(e['description'])} chars"))
            args += ['-c', e['description']]
        if e['tags'] and not p['tags']:
            ops.append(('tags', '-', ', '.join(e['tags'][:6])))
            args += ['--tags', ','.join(e['tags'])]
        if e['isbn'] and not p['isbn']:
            ops.append(('isbn', '-', e['isbn']))
            args += ['--isbn', e['isbn']]

        if not ops:
            continue
        changed += 1
        print(f"[{n}/{len(ps)}] {os.path.basename(pd)[:72]}")
        for f, old, new in ops:
            print(f"      {f:<12} {str(old)[:34]:<34} -> {str(new)[:60]}")
        planned[pd] = args
        if a.apply:
            r = run([pd] + args)
            print(f"      {'written' if r.returncode == 0 else 'FAILED: ' + r.stderr[:80]}")
        print()

    print(
        f"\n{changed}/{len(ps)} PDFs would gain metadata"
        if not a.apply
        else f"\n{changed}/{len(ps)} PDFs updated"
    )


main()
