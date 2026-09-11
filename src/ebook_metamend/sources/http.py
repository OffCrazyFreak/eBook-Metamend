"""One HTTP GET for every direct source, with the transport swappable.

On the desktop the transport is urllib. In the browser build the worker
replaces it with a synchronous XMLHttpRequest through Pyodide's ``js`` module,
which is the only way a Python source can call out from a Web Worker without
being rewritten. Nothing above this function knows which one is in use.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from .errors import SourceError

#: The contact every catalogue asks for is the project URL, so nothing personal
#: ships in a public repository. Browsers set their own User-Agent and ignore
#: this header; that is why Open Library's anonymous rate applies there.
USER_AGENT = 'eBook-Metamend/1.0 (+https://github.com/OffCrazyFreak/eBook-Metamend)'

Transport = Callable[[str, dict[str, str], float], bytes]


def _urllib(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


_transport: Transport = _urllib


def set_transport(transport: Transport | None) -> None:
    """Replace how bytes are fetched. ``None`` restores urllib."""
    global _transport
    _transport = transport or _urllib


def get_json(
    url: str,
    *,
    timeout: float = 5,
    attempts: int = 2,
    retry_pause: float = 1,
    accept: str = 'application/json',
) -> Any:
    """GET and decode JSON, retrying transient failures.

    Raises ``SourceError`` when every attempt failed, never returns ``None`` for
    it: a catalogue that is down must not read as "no such book".
    """
    headers = {'User-Agent': USER_AGENT, 'Accept': accept}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return json.loads(_transport(url, headers, timeout))
        # OSError covers URLError, socket timeouts and TLS errors; ValueError
        # covers a truncated or non-JSON body. A bare Exception here would also
        # swallow a programming mistake into retries with sleeps.
        except (OSError, ValueError) as exc:
            last_error = exc
            # No point pausing after the last attempt; it only delays the caller.
            if attempt < attempts - 1:
                time.sleep(retry_pause * (attempt + 1))
    raise SourceError(
        f'{attempts} attempts failed ({type(last_error).__name__}: {str(last_error)[:80]})'
    )
