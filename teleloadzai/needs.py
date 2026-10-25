"""What each site needs, per program: a visit, nothing, or an account.

The user's idea, 2026-10-25: say it on the Sites page -- and since "the needs
may change with the updates", keep it true with the real results of the
downloads on this PC, each with its date. Nothing is guessed (decision 38):
a line exists only where something was seen.

  "visit"   -- a download worked with only visitor cookies, no account
  "none"    -- a download worked with no cookies at all
  "account" -- the program itself asked for a log-in (its own error)

A download made while logged in proves nothing about what is needed, and
changes nothing. data/needs.json holds site, program, result and date only,
never a cookie.
"""

from __future__ import annotations

import json
import os
import threading
import time

from .paths import DATA_DIR

FILE = DATA_DIR / "needs.json"
KINDS = ("visit", "none", "account")

# The proofs written in CLAUDE.md before this file existed, with their dates.
SEEN_BEFORE = {
    # A visit is enough: 9 visit cookies, no sid_tt, the whole video (§4).
    "tiktok|tiktokdownloader": ("visit", "2026-09-26"),
    # 35 visit cookies and no sessionid: the user's 4 downloads worked (§4).
    "douyin|tiktokdownloader": ("visit", "2026-09-26"),
    # gallery-dl: "redirect to login page" with no log-in (the audit, §4).
    "instagram|gallery-dl": ("account", "2026-09-26"),
    # KS-Downloader: "Failed to retrieve posts data"; worked with a log-in.
    "kuaishou|ks-downloader": ("account", "2026-09-26"),
    # yt-dlp: "Unable to extract initial state" without; read with one (§4).
    "bilibili|yt-dlp": ("account", "2026-10-24"),
}

_lock = threading.Lock()


def _read() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(v, dict) and v.get("need") in KINDS and isinstance(v.get("seen"), str)}


def all_needs() -> dict[str, dict]:
    """{"site|program": {"need": ..., "seen": "YYYY-MM-DD"}} -- what was seen
    last, the file over the proofs it started from."""
    merged = {k: {"need": n, "seen": d} for k, (n, d) in SEEN_BEFORE.items()}
    merged.update(_read())
    return merged


def record(site: str, program: str, need: str) -> None:
    """One real result. Written to a temporary file first, then put in place."""
    if not site or not program or need not in KINDS:
        return
    with _lock:
        data = _read()
        data[f"{site}|{program}"] = {"need": need, "seen": time.strftime("%Y-%m-%d")}
        temp = FILE.with_name(FILE.name + ".tmp")
        try:
            temp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(temp, FILE)
        except OSError:
            pass                # a line not updated, never a crash of the job
