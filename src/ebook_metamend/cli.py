"""Command line entry points. Parsing and printing only; decisions live in the
library modules so they can be tested without a terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import config, enrich, epub_to_pdf, extract
from .enrich import Proposal
from .library import Book
from .sources import SOURCES


def _write_json(path: str, payload) -> None:
    """Write atomically, so an interrupted run cannot truncate a good previous one."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = f'{path}.tmp'
    with open(tmp, 'w') as fh:
        json.dump(payload, fh, indent=1)
    os.replace(tmp, path)


def _report(index: int, total: int, book: Book, proposal: Proposal | None) -> None:
    if proposal is None:
        print(f'[{index}/{total}] {book.stem[:60]:<60} no source answered')
        return

    sources = ','.join(proposal.sources)
    gains = ','.join(proposal.gains) or '-'
    print(
        f'[{index}/{total}] {proposal.stem[:50]:<50} {proposal.conf:<4} '
        f'fn={proposal.fn_score:.2f} au={proposal.au_score:.2f} '
        f'src:{sources:<20} gains:{gains}'
    )
    if proposal.gains.get('title'):
        was = (proposal.current.get('title') or '')[:40]
        print(f"        title    {was} -> {proposal.gains['title'][:60]}")
    if proposal.gains.get('series'):
        print(f"        series   -> {proposal.gains['series']} #{proposal.merged['sidx']}")
    if proposal.gains.get('tags'):
        print(f"        tags     -> {', '.join(proposal.gains['tags'][:8])}")
    if proposal.unreadable:
        print('        existing metadata could not be read, so nothing is proposed')
    for ext, ok, err in proposal.writes:
        print(f"        wrote {ext} {'ok' if ok else 'FAILED ' + err}")


def enrich_command(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='ebook-metamend',
        description='Fill in missing ebook metadata, without trusting a source that '
        'disagrees with your filenames.',
    )
    parser.add_argument('--apply', action='store_true', help='write changes (default: dry run)')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--match', default='', help='only books whose name contains this')
    parser.add_argument('--out', default='proposals.json')
    parser.add_argument(
        '--include-low',
        action='store_true',
        help='also apply MED and LOW confidence results (not recommended)',
    )
    args = parser.parse_args(argv)
    config.warn_if_unsafe_cal_root()

    selected = enrich.select(match=args.match, limit=args.limit, start=args.start)
    print(f"{len(selected)} unique books | mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    written: list[Proposal] = []

    def report_and_record(index, total, book, proposal):
        _report(index, total, book, proposal)
        if proposal is not None:
            written.append(proposal)
            # Rewritten after every book. The whole file each time is wasteful,
            # but an interrupted --apply must not lose the record of what it
            # already changed, and the write is atomic so it cannot truncate.
            _write_json(args.out, [p.to_dict() for p in written])

    proposals = enrich.run(
        selected,
        do_apply=args.apply,
        include_low=args.include_low,
        on_book=report_and_record,
    )

    for name, why in enrich.unavailable_sources.items():
        print(f'warning: source {name!r} was unavailable for this run: {why}', file=sys.stderr)
    if enrich.unavailable_sources:
        print(
            f'warning: {len(enrich.unavailable_sources)} of {len(SOURCES)} sources were '
            'unavailable, so cross-checking was weaker than intended',
            file=sys.stderr,
        )

    high = sum(1 for p in proposals if p.conf == 'HIGH')
    unreadable = sum(1 for p in proposals if p.unreadable)
    print(f'\nHIGH: {high}   MED/LOW (review): {len(proposals) - high}')
    if unreadable:
        print(f'{unreadable} book(s) had unreadable metadata and were left alone')
    _write_json(args.out, [p.to_dict() for p in proposals])
    print(f'proposals written to {args.out}')
    if not args.apply:
        print('dry run: nothing was written to your files')
    return 0


def epub_to_pdf_command(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='ebook-metamend-epub-to-pdf',
        description="Copy an EPUB's richer metadata onto its PDF twin. Local only.",
    )
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args(argv)
    config.warn_if_unsafe_cal_root()

    mode = 'APPLY (writes to PDFs)' if args.apply else 'DRY RUN (no writes)'
    print(f'mode: {mode}\n')
    results = epub_to_pdf.run(limit=args.limit, do_apply=args.apply, on_line=print)
    print(f'{results.total} EPUB+PDF pairs')
    verb = 'updated' if args.apply else 'would gain metadata'
    print(f'\n{results.changed}/{results.total} PDFs {verb}')
    return 0


def extract_command(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='ebook-metamend-extract',
        description='Dump filename, embedded metadata and opening text per book.',
    )
    parser.add_argument('--out', default='spotcheck', help='output directory')
    args = parser.parse_args(argv)
    written = extract.run(args.out)
    for name, count in written:
        print(f'WROTE {name}  ({count} files)')
    print('DONE')
    return 0


if __name__ == '__main__':
    sys.exit(enrich_command())
