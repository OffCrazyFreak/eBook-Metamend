"""Native EPUB and PDF metadata I/O, replacing the ``ebook-meta`` subprocess.

Each module reads a record shaped like ``opf.parse`` and writes the gains that
``enrich.compute_gains`` produced. Both write a sibling temporary file, read it
back, and only then replace the original, so a crash mid-write leaves the book
untouched.
"""
