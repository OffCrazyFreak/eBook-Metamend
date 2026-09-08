"""Paths and the Calibre subprocess environment.

Previously duplicated verbatim across every script, with the library root
hardcoded in nine places.
"""

from __future__ import annotations

import os
import stat
import sys

#: Root of the ebook library. Every book path is derived from this.
LIBRARY = os.environ.get('EBOOK_LIBRARY', os.path.expanduser('~/eBooks'))


def _default_cal_root() -> str:
    """Where a portable Calibre is expected, under the user's own cache.

    Deliberately not a shared temporary directory. The binaries under this root
    are executed, and ``LD_LIBRARY_PATH`` is pointed at its ``lib``, so anyone
    able to write there can run code as you (CWE-426, untrusted search path).
    ``/tmp`` is world-writable, so a path under it is the wrong default even
    though it is convenient.
    """
    cache = os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')
    return os.path.join(cache, 'ebook-metamend', 'calibre')


#: Where a portable Calibre is unpacked. Not a system install.
CAL_ROOT = os.environ.get('CAL_ROOT') or _default_cal_root()

EBOOK_META = os.path.join(CAL_ROOT, 'bin', 'ebook-meta')
FETCH_METADATA = os.path.join(CAL_ROOT, 'bin', 'fetch-ebook-metadata')


def unsafe_cal_root(root: str | None = None) -> str | None:
    """Why the Calibre root is unsafe to execute from, or None if it is fine.

    Checked rather than assumed, because the whole point of the default above is
    that this path gets executed.
    """
    root = root or CAL_ROOT
    try:
        info = os.stat(root)
    except OSError:
        return None  # Missing is a separate problem, reported when it is used.

    if info.st_uid not in (os.getuid(), 0):
        return f'{root} is owned by uid {info.st_uid}, not you'
    if info.st_mode & stat.S_IWOTH and not info.st_mode & stat.S_ISVTX:
        return f'{root} is world-writable'
    return None


def warn_if_unsafe_cal_root() -> None:
    """Print a warning once, for CLI entry points. Does not refuse to run: the
    user may knowingly be using a shared path, and refusing would be worse than
    telling them."""
    reason = unsafe_cal_root()
    if reason:
        print(
            f'warning: {reason}. Anyone who can write there can run code as you. '
            'Set CAL_ROOT to a directory only you control.',
            file=sys.stderr,
        )


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
