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


def _say(text: str) -> None:
    """A problem with this file, said in the Console (decision 34)."""
    from . import console
    console.add("app", f"Teleloadzai: {text}", "err")


def _read(strict: bool = False) -> dict | None:
    """The file's lines; {} when there is none. With `strict`: a damaged file
    is set aside under a name of its own and said, then {} (learning goes
    on); a file another program holds gives None (this line waits)."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a table")
    except FileNotFoundError:
        return {}
    except ValueError:
        if not strict:
            return {}
        aside, number = FILE.with_name("needs (unreadable).json"), 2
        while aside.exists():
            aside, number = FILE.with_name(f"needs (unreadable {number}).json"), number + 1
        try:
            os.replace(FILE, aside)
        except OSError:
            _say(f"{FILE.name} is damaged and could not be set aside: what each site "
                 "needs is not updated.")
            return None
        _say(f"{FILE.name} was damaged. It was kept as {aside.name}; the Sites page "
             "starts again from what Teleloadzai knew before.")
        return {}
    except OSError as problem:
        if strict:
            _say(f"{FILE.name} could not be read ({problem.strerror}): this download's "
                 "result is not kept on the Sites page.")
        return None if strict else {}
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
        data = _read(strict=True)
        # A file there but unreadable is never written over with this one
        # line: everything learned before was lost that way (hunt of
        # 2026-10-31). This line is dropped instead, and said.
        if data is None:
            return
        data[f"{site}|{program}"] = {"need": need, "seen": time.strftime("%Y-%m-%d")}
        temp = FILE.with_name(FILE.name + ".tmp")
        try:
            temp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(temp, FILE)
        except OSError as problem:
            # A line not updated, never a crash of the job -- but said, and
            # no half-written .tmp left behind.
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            _say(f"{FILE.name} could not be written ({problem.strerror}): this "
                 "download's result is not kept on the Sites page.")
