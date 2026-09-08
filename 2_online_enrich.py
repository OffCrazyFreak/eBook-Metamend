#!/usr/bin/env python3
"""
Query Kobo + Google + Open Library per book, cross-check, and propose metadata.
Dry run by default; --apply writes in place. Never blanks an existing value.

Confidence:
  HIGH  = 2+ sources agree on the title  -> safe to auto-apply
  LOW   = only one source answered, or they disagree -> review (Kobo invents matches)
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

CAL_ROOT = os.environ.get('CAL_ROOT', '/tmp/cal')

CAL = CAL_ROOT + '/bin'
FE = os.path.join(CAL, 'fetch-ebook-metadata')
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
OPFNS = '{http://www.idpf.org/2007/opf}'


def norm(s):
    s = (s or '').lower().replace('%', ' percent ').replace('&', ' and ')
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\b(the|a|an)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # containment is strong evidence, but NOT proof: an omnibus like
    # "happiest baby ... and happiest toddler ..." contains "happiest toddler ...".
    # Cap it by how much of the longer string is actually covered.
    if a in b or b in a:
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        # "Digital Minimalism" vs "Digital Minimalism: Choosing a Focused Life"
        # -> the short one is a PREFIX, i.e. main title + subtitle. Legitimate.
        if long.startswith(short):
            return 0.95
        # contained but not a prefix, e.g. an omnibus that merely mentions the
        # other volume's title. Suspicious -> keep below the HIGH threshold.
        return 0.70
    return difflib.SequenceMatcher(None, a, b).ratio()


def parse_opf(x):
    m = re.search(r'<package\b.*?</package>', x, re.S)
    if not m:
        return None
    try:
        r = ET.fromstring(m.group(0))
    except Exception:
        return None

    def g(t):
        return [(e.text or '').strip() for e in r.iter(DC + t) if (e.text or '').strip()]

    d = {
        'title': (g('title') or [''])[0],
        'authors': g('creator'),
        'publisher': (g('publisher') or [''])[0],
        'description': (g('description') or [''])[0],
        'tags': g('subject'),
        'series': None,
        'sidx': None,
        'isbn': '',
    }
    for m2 in r.iter(OPFNS + 'meta'):
        if m2.get('name') == 'calibre:series':
            d['series'] = m2.get('content')
        if m2.get('name') == 'calibre:series_index':
            d['sidx'] = m2.get('content')
    for e in r.iter(DC + 'identifier'):
        t = (e.text or '').strip()
        if t.lower().startswith('isbn:'):
            d['isbn'] = t.split(':', 1)[1]
    return d


def calibre_src(title, author, plugin, tmo, retries=1):
    for _attempt in range(retries + 1):
        try:
            r = subprocess.run(
                [FE, '-t', title, '-a', author, '-p', plugin, '-o', '-d', str(tmo)],
                capture_output=True,
                text=True,
                timeout=tmo + 20,
                env=env,
            )
        except subprocess.TimeoutExpired:
            time.sleep(5)
            continue
        if '<package' in r.stdout:
            return parse_opf(r.stdout)
        time.sleep(5)
    return None


def openlib(title, author):
    q = urllib.parse.urlencode(
        {
            'title': title,
            'author': author,
            'fields': 'title,author_name,subject,publisher,isbn,first_publish_year',
            'limit': '1',
        }
    )
    req = urllib.request.Request(
        'https://openlibrary.org/search.json?' + q,
        headers={'User-Agent': 'ebook-enrich/1.0 (personal library)'},
    )
    d = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.load(r)
                break
        except Exception:
            time.sleep(3 * (attempt + 1))
    if d is None:
        return None
    if not d.get('docs'):
        return None
    b = d['docs'][0]
    return {
        'title': b.get('title', ''),
        'authors': b.get('author_name') or [],
        'publisher': (b.get('publisher') or [''])[0],
        'description': '',
        'tags': (b.get('subject') or [])[:25],
        'series': None,
        'sidx': None,
        'isbn': (b.get('isbn') or [''])[0],
    }


def read_meta(path):
    tf = tempfile.NamedTemporaryFile(suffix='.opf', delete=False)
    tf.close()
    subprocess.run(
        [EM, path, '--to-opf', tf.name], capture_output=True, text=True, timeout=90, env=env
    )
    x = open(tf.name, encoding='utf8', errors='ignore').read()
    os.unlink(tf.name)
    return parse_opf(x) or {}


def books():
    seen = {}
    for r, _, fs in os.walk(LIB):
        for f in fs:
            s, e = os.path.splitext(f)
            seen.setdefault(s, {})[e.lower()] = os.path.join(r, f)
    return sorted(seen.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--match', default='', help='only books whose path contains this substring')
    ap.add_argument('--out', default='proposals.json')
    ap.add_argument(
        '--include-low', action='store_true', help='also apply LOW confidence (not recommended)'
    )
    a = ap.parse_args()

    bs = books()
    if a.match:
        bs = [b for b in bs if a.match.lower() in b[0].lower()]
    bs = bs[a.start :]
    if a.limit:
        bs = bs[: a.limit]
    print(f"{len(bs)} unique books | mode: {'APPLY' if a.apply else 'DRY RUN'}\n")

    props = []
    hi = 0
    lo = 0
    for n, (stem, fmts) in enumerate(bs, 1):
        author, _, rest = stem.partition(' - ')
        full = re.sub(r'\s*-\s*\d+(\.\d+)?\s*-\s*', ' ', rest).strip()
        query = re.split(r'\s+-\s+|\s*:\s*|\s*\(', full)[0].strip() or full

        src = {}
        src['kobo'] = calibre_src(query, author, 'Kobo Metadata', 18)
        time.sleep(2)
        src['google'] = calibre_src(query, author, 'Google', 18)
        time.sleep(8)
        src['openlib'] = openlib(query, author)
        time.sleep(1)
        got = {k: v for k, v in src.items() if v}

        if not got:
            print(f"[{n}/{len(bs)}] {stem[:60]:<60} no source answered")
            continue

        # Your filenames are already correct, so agreement with the FILENAME is the
        # strongest available signal. Cross-source agreement is a secondary boost.
        titles = [(k, v['title']) for k, v in got.items() if v.get('title')]
        agree = 0
        for i in range(len(titles)):
            for j in range(i + 1, len(titles)):
                if sim(titles[i][1], titles[j][1]) >= 0.75:
                    agree += 1
        fn = max((sim(v['title'], full) for v in got.values()), default=0.0)
        # author agreement: a hallucinated match usually has the wrong author too
        au = max(
            (
                max((sim(x, author) for x in (v.get('authors') or [])), default=0.0)
                for v in got.values()
            ),
            default=0.0,
        )
        if fn >= 0.85 and au >= 0.7:
            conf = 'HIGH'
        elif fn >= 0.85 or (fn >= 0.60 and au >= 0.7) or (agree >= 1 and au >= 0.7):
            conf = 'MED'
        else:
            conf = 'LOW'
        # drop sources whose title does not resemble the filename (hallucinated matches)
        got = {k: v for k, v in got.items() if sim(v.get('title', ''), full) >= 0.60} or got

        cur = read_meta(fmts.get('.epub') or fmts.get('.pdf'))
        merged = {
            'title': max((v['title'] for v in got.values()), key=len, default=''),
            'tags': sorted({t for v in got.values() for t in (v.get('tags') or [])})[:12],
            'description': max(
                (v.get('description') or '' for v in got.values()), key=len, default=''
            ),
            'series': next((v['series'] for v in got.values() if v.get('series')), None),
            'sidx': next((v['sidx'] for v in got.values() if v.get('sidx')), None),
            'publisher': next((v['publisher'] for v in got.values() if v.get('publisher')), ''),
            'isbn': next((v['isbn'] for v in got.values() if v.get('isbn')), ''),
        }
        # only propose fields the book actually lacks
        gains = {}
        if merged['tags'] and not cur.get('tags'):
            gains['tags'] = merged['tags']
        if merged['series'] and not cur.get('series'):
            gains['series'] = merged['series']
        if merged['description'] and len(merged['description']) > len(cur.get('description') or ''):
            gains['description'] = merged['description']
        if merged['isbn'] and not cur.get('isbn'):
            gains['isbn'] = merged['isbn']
        if merged['publisher'] and not cur.get('publisher'):
            gains['publisher'] = merged['publisher']
        if (
            conf == 'HIGH'
            and merged['title']
            and len(merged['title']) > len(cur.get('title') or '') + 3
        ):
            gains['title'] = merged['title']

        if conf == 'HIGH':
            hi += 1
        else:
            lo += 1
        srcs = ','.join(sorted(got))
        print(
            f"[{n}/{len(bs)}] {stem[:50]:<50} {conf:<4} fn={fn:.2f} au={au:.2f} src:{srcs:<20} gains:{','.join(gains) or '-'}"
        )
        if gains.get('title'):
            print(f"        title    {cur.get('title', '')[:40]} -> {gains['title'][:60]}")
        if gains.get('series'):
            print(f"        series   -> {gains['series']} #{merged['sidx']}")
        if gains.get('tags'):
            print(f"        tags     -> {', '.join(gains['tags'][:8])}")

        props.append(
            {
                'stem': stem,
                'files': fmts,
                'conf': conf,
                'sources': sorted(got),
                'gains': gains,
                'merged': merged,
                'fn_score': round(fn, 3),
                'au_score': round(au, 3),
                'src_titles': {k: v['title'] for k, v in got.items()},
            }
        )
        json.dump(props, open(a.out, 'w'), indent=1)

        if a.apply and gains and (conf == 'HIGH' or a.include_low):
            args = []
            if 'title' in gains:
                args += ['-t', gains['title']]
            if 'tags' in gains:
                args += ['--tags', ','.join(gains['tags'])]
            if 'description' in gains:
                args += ['-c', gains['description']]
            if 'publisher' in gains:
                args += ['--publisher', gains['publisher']]
            if 'isbn' in gains:
                args += ['--isbn', gains['isbn']]
            if 'series' in gains:
                args += ['-s', gains['series']]
                if merged.get('sidx'):
                    args += ['-i', str(merged['sidx'])]
            for ext in ('.epub', '.pdf'):
                if ext in fmts and args:
                    r = subprocess.run(
                        [EM, fmts[ext]] + args, capture_output=True, text=True, timeout=180, env=env
                    )
                    print(
                        f"        wrote {ext} {'ok' if r.returncode == 0 else 'FAILED ' + r.stderr[:60]}"
                    )
        elif a.apply and gains:
            print("        skipped (LOW confidence)")

    print(f"\nHIGH: {hi}   MED/LOW (review): {lo}")
    print(f"proposals written to {a.out}")
    if not a.apply:
        print("dry run: nothing was written to your files")


if __name__ == '__main__':
    main()
