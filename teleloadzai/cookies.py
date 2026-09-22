"""The cookie file: import it, describe it, hand it to the tools that can take it.

A cookie is the proof that you are logged in. Some links need it: a private
Instagram post, an age-restricted YouTube video, anything on Weibo.

**Why a file and not the browser.** yt-dlp can read a browser directly, and on
this developer's PC it failed on all four browsers installed (2026-09-22):

    chrome, edge  ERROR: Could not copy Chrome cookie database   -- browser open
    brave         ERROR: Failed to decrypt with DPAPI            -- app-bound keys
    opera         could not find opera cookies database          -- it is Opera GX

Brave was closed and still refused: Chromium now seals its cookies with a key
Windows only gives back to the browser itself. yt-dlp issue 10927 is still open
and yt-dlp is already the newest version, so there is nothing to update. The
file is therefore the main road, not the fallback. Reading the browser comes
later, for the people whose PC allows it.

**Hard rule 1 shapes everything here.** A cookie value is a password:

* It never travels on a command line. Three of our tools only accept a cookie
  that way -- XHS-Downloader `--cookie`, N_m3u8DL-RE `-H "Cookie: ..."`, f2
  `-k` -- and on Windows any process can read another process's command line.
  So those three get no cookie at all, and `unusable_reason` says so plainly
  rather than letting the user believe it worked.
* It is never printed. `redact()` cleans anything a tool writes before it can
  reach the screen, a log or an error message. That is the answer to the
  collision the audit found: decision 34 says say every failure in plain words,
  hard rule 1 says never print a cookie, and a tool that fails on a cookie can
  put it in the line it prints.
* This module reads names, domains and dates. It never returns a value, and
  nothing here writes one anywhere except the copy on disk.

**Why we copy the file instead of using the one the user chose.** yt-dlp writes
the cookie jar back. Measured 2026-09-22 with a two-line probe file:

    before: 87 bytes, 2 lines   ->   after: 969 bytes, 12 lines

It had added YouTube's own cookies. Pointing that at the user's own export
would quietly grow and rewrite a file he did not ask us to touch. So the import
takes a copy, and every tool is given the copy. (streamlink, probed the same
day, does not rewrite. yt-dlp does.)
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from .paths import DATA_DIR

# Our copy. `.gitignore` excludes it -- it holds live sessions.
COOKIE_FILE = DATA_DIR / "cookies.txt"

# The three tools that accept a cookie FILE. Probed one by one, 2026-09-22:
#   yt-dlp      --cookies FILE
#   gallery-dl  -C / --cookies FILE
#   streamlink  --http-cookies-file PATH
# All three want the same Netscape format, so one file serves all three.
FILE_CAPABLE = ("yt-dlp", "gallery-dl", "streamlink")

# The three that only take a cookie as text on the command line. Windows shows
# a process's command line to any other process, so this is a refusal, not an
# oversight. The reason is shown to the user, never swallowed (decision 34).
COMMAND_LINE_ONLY = {
    "xhs-downloader":
        "XHS-Downloader only takes a cookie typed on the command line, "
        "where another program on this PC could read it",
    "n-m3u8dl-re":
        "N_m3u8DL-RE only takes a cookie inside a command-line header, "
        "where another program on this PC could read it",
    "f2":
        "f2 only takes a cookie on the command line or in its own settings "
        "file, which Teleloadzai does not write yet",
}

_MAX_BYTES = 8 * 1024 * 1024        # a real export is a few kB; 8 MB is absurd


# --------------------------------------------------------------------------
# hiding values
# --------------------------------------------------------------------------

# A cookie value is a long run of the characters base64 and hex use. Names are
# short and wordy; values are not. Matching the shape means we do not have to
# hold a single real value in memory to hide it.
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=.%|]{24,}")

# "Cookie: a=b; c=d", "set-cookie: ...", "cookie=..." -- everything after the
# marker goes, whatever shape it has.
_COOKIE_LINE = re.compile(r"((?:set-)?cookie\s*[:=]\s*).*", re.IGNORECASE)

_HIDDEN = "[hidden]"


def redact(text: str) -> str:
    """Remove anything that could be a cookie value from text we will show.

    Decision 34 says every failure reaches the user in plain words. Hard rule 1
    says a cookie value is never printed. Both hold only if the words are
    cleaned first, so this runs on every line of tool output that can reach the
    screen, and on the path of the cookie file itself -- a path can carry the
    account name.

    It hides more than it must. A download that fails with a slightly shortened
    message is a small cost; a session token on screen, in a screenshot, or in
    a bug report the user pastes into an issue, is not.
    """
    if not text:
        return text
    cleaned = _COOKIE_LINE.sub(lambda m: m.group(1) + _HIDDEN, text)
    return _LONG_TOKEN.sub(_HIDDEN, cleaned)


# --------------------------------------------------------------------------
# reading a file without keeping what is in it
# --------------------------------------------------------------------------

class CookieFileError(ValueError):
    """The chosen file cannot be used, with a sentence saying why and what to do."""


def _read_lines(path: Path) -> list[str]:
    size = path.stat().st_size
    if size == 0:
        raise CookieFileError(
            "That file is empty. Export your cookies again — the extension may "
            "have saved nothing."
        )
    if size > _MAX_BYTES:
        raise CookieFileError(
            f"That file is {size // (1024 * 1024)} MB, far too big for a cookie "
            "export. Check you picked the right file."
        )
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as problem:
        raise CookieFileError(f"That file could not be read: {problem.strerror}") from problem
    return raw.splitlines()


def inspect(path: Path) -> dict:
    """Describe a Netscape cookie file: how many, for which sites, until when.

    Raises ``CookieFileError`` with a sentence the user can act on. Never
    returns, logs or keeps a cookie value.
    """
    lines = _read_lines(path)

    domains: dict[str, int] = {}
    total = 0
    expired = 0
    soonest_useful: float | None = None
    now = time.time()

    for line in lines:
        row = line.strip()
        if not row or row.startswith("#"):
            # `#HttpOnly_.example.com` is a real cookie line wearing a comment
            # hat. Skipping it silently would undercount a working file.
            if not row.startswith("#HttpOnly_"):
                continue
            row = row[len("#HttpOnly_"):]

        parts = row.split("\t")
        if len(parts) < 7:
            continue

        domain, _flag, _path, _secure, expiry, _name, _value = parts[:7]
        total += 1
        clean_domain = domain.lstrip(".").lower()
        domains[clean_domain] = domains.get(clean_domain, 0) + 1

        try:
            when = float(expiry)
        except ValueError:
            continue
        if when == 0:
            continue                     # session cookie: dies with the browser
        if when < now:
            expired += 1
        elif soonest_useful is None or when < soonest_useful:
            soonest_useful = when

    if total == 0:
        if any("{" in line for line in lines[:5]):
            raise CookieFileError(
                "That file is JSON, not the format the download tools read. In "
                "your cookie extension, choose the export called "
                "\"Netscape\" or \"cookies.txt\"."
            )
        raise CookieFileError(
            "No cookies were found in that file. It should start with "
            "\"# Netscape HTTP Cookie File\" and have one cookie per line."
        )

    if expired == total:
        raise CookieFileError(
            "Every cookie in that file has expired. Log in to the site again in "
            "your browser, then export a fresh file."
        )

    top = sorted(domains.items(), key=lambda pair: (-pair[1], pair[0]))
    return {
        "total": total,
        "expired": expired,
        "sites": [name for name, _count in top],
        "expires_at": soonest_useful,
    }


# --------------------------------------------------------------------------
# what the app does with it
# --------------------------------------------------------------------------

def import_file(chosen: Path) -> dict:
    """Check the user's file, then keep our own copy of it.

    The file the user picked is never opened for writing and never handed to a
    tool: yt-dlp rewrites the jar it is given (measured 2026-09-22), and that
    is not our file to grow.
    """
    chosen = Path(chosen)
    if not chosen.is_file():
        raise CookieFileError("That file no longer exists. Choose it again.")

    summary = inspect(chosen)           # raises with a reason if unusable

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(chosen, COOKIE_FILE)
    except OSError as problem:
        raise CookieFileError(
            f"The file could not be copied into Teleloadzai: {problem.strerror}"
        ) from problem

    return summary


def clear() -> bool:
    """Forget the cookies. Returns True when a file was really removed."""
    if not COOKIE_FILE.exists():
        return False
    COOKIE_FILE.unlink()
    return True


def have_file() -> bool:
    return COOKIE_FILE.is_file() and COOKIE_FILE.stat().st_size > 0


def path_for(tool_id: str, enabled: bool) -> Path | None:
    """The cookie file to give this tool, or None.

    None has three different meanings and the caller must not confuse them:
    the user has cookies off, there is no file, or this tool cannot take one.
    ``unusable_reason`` is what turns the third into words.
    """
    if not enabled or not have_file():
        return None
    if tool_id not in FILE_CAPABLE:
        return None
    return COOKIE_FILE


def unusable_reason(tool_id: str, enabled: bool) -> str | None:
    """Why this download will run without the cookies, although they are on.

    Silence here is exactly the bug decision 34 forbids: the user turns cookies
    on, presses Add, the download fails for not being logged in, and nothing
    ever said that this tool was never given them.
    """
    if not enabled or not have_file():
        return None
    if tool_id in COMMAND_LINE_ONLY:
        return COMMAND_LINE_ONLY[tool_id]
    if tool_id not in FILE_CAPABLE:
        return f"Teleloadzai cannot give cookies to {tool_id} yet"
    return None


def state(enabled: bool) -> dict:
    """Everything the page needs to draw the cookie card. No value, ever."""
    if not have_file():
        return {"enabled": enabled, "have_file": False}

    try:
        summary = inspect(COOKIE_FILE)
    except CookieFileError as problem:
        # The file was fine when imported and is not any more -- expired, or
        # edited outside. Say it instead of showing a healthy-looking card.
        return {
            "enabled": enabled,
            "have_file": True,
            "broken": redact(str(problem)),
        }

    saved = COOKIE_FILE.stat().st_mtime
    return {
        "enabled": enabled,
        "have_file": True,
        "total": summary["total"],
        "expired": summary["expired"],
        "sites": summary["sites"][:6],
        "more_sites": max(0, len(summary["sites"]) - 6),
        "imported_at": saved,
        "expires_at": summary["expires_at"],
        "used_by": list(FILE_CAPABLE),
    }
