"""What can go wrong with a source, and the difference that matters.

Three outcomes look identical if you only return ``None``, and conflating them
is how this tool silently ran on one source for weeks:

- **No answer.** The source works and does not have this book. Normal, common,
  and not a reason to slow down.
- **A transient failure.** The server errored, reset the connection or timed
  out. Worth backing off for; not worth giving up on.
- **Unavailable.** The source cannot run at all, typically a plugin that is not
  installed. No amount of waiting fixes it, and every book after the first will
  fail the same way.
"""

from __future__ import annotations


class SourceError(RuntimeError):
    """A transient failure. The source may answer if asked again later."""


class SourceUnavailable(RuntimeError):
    """The source cannot run at all. Retrying is pointless."""
