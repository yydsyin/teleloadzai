"""The Console page's lines: what each program says while it works.

Asked by the user 2026-10-25 (model S1, a Console page like the launcher
they showed): read-only -- nobody types a command here. Each line is washed
by `cookies.redact` before it is kept (hard rule 1, decision 37), kept in
memory only, the last LIMIT lines, and gone when Teleloadzai closes: never
written to disk by us (the page's "Save as file" is the user's own act).
"""

from __future__ import annotations

import threading
import time
from collections import deque

from . import cookies

LIMIT = 2000

_lock = threading.Lock()
_lines: deque[dict] = deque(maxlen=LIMIT)
_next = 0


def add(job_id: str, text: str, kind: str = "out") -> None:
    """One line. ``kind``: "head" (a download, a title read or an install
    starts), "out" (the program's own words, or a step), "end" (how it ended,
    our words), "err" (how it failed), "note" (a message the page showed).
    Since 2026-10-26 the Console is not only downloads (the user's request)."""
    global _next
    clean = cookies.redact(text.rstrip())
    if not clean.strip():
        return
    with _lock:
        _lines.append({"n": _next, "at": time.time(), "job": job_id, "kind": kind, "text": clean})
        _next += 1


def since(n: int) -> tuple[list[dict], int]:
    """The lines numbered n and after, and the number the next call starts at."""
    with _lock:
        return [line for line in _lines if line["n"] >= n], _next


def clear() -> None:
    with _lock:
        _lines.clear()
