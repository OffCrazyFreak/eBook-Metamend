"""Paths and the Calibre subprocess environment.

Previously duplicated verbatim across every script, with the library root
hardcoded in nine places.
"""

from __future__ import annotations

import os

#: Root of the ebook library. Every book path is derived from this.
LIBRARY = os.environ.get('EBOOK_LIBRARY', os.path.expanduser('~/eBooks'))

#: Where a portable Calibre is unpacked. Not a system install.
CAL_ROOT = os.environ.get('CAL_ROOT', '/tmp/cal')

EBOOK_META = os.path.join(CAL_ROOT, 'bin', 'ebook-meta')
FETCH_METADATA = os.path.join(CAL_ROOT, 'bin', 'fetch-ebook-metadata')


def calibre_env() -> dict[str, str]:
    """Environment for Calibre's binaries.

    Calibre 9.x fails outright without the last two: the launcher cannot find
    libcalibre-launcher.so, and PDF output dies inside PoDoFo trying to load
    OpenSSL's legacy provider.

    Deliberately not applied to poppler tools (pdfinfo, pdftotext). Forcing
    Calibre's LD_LIBRARY_PATH onto them makes them load the wrong libraries.
    """
    return dict(
        os.environ,
        CALIBRE_CONFIG_DIRECTORY=os.path.join(CAL_ROOT, 'config'),
        QT_QPA_PLATFORM='offscreen',
        LD_LIBRARY_PATH=os.path.join(CAL_ROOT, 'lib'),
        OPENSSL_MODULES=os.path.join(CAL_ROOT, 'lib', 'ossl-modules'),
    )
