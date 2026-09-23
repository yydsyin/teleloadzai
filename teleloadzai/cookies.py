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

# TikTokDownloader takes the cookie in the BODY of a request to its own local
# server, not on a command line -- so it is safe to give it one, and it is not
# in the list above. It needs the cookie as a header string rather than a
# file, which is what `header_for` is for.
HEADER_CAPABLE = ("tiktokdownloader",)

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


def known_domains() -> set[str]:
    """The sites Teleloadzai can actually download from.

    Read from `platforms.py` rather than written again here, so a platform
    added there is covered without anyone remembering this file.

    ⚠️ `google.com` is deliberately NOT in this list, although YouTube log-in
    cookies also exist there. Gmail's session lives on `.google.com` too, and
    keeping that domain would put a mail account inside the very file this
    filter exists to shrink. yt-dlp's own advice is to export from
    youtube.com, which carries its own copy. **Not verified with a real
    Google log-in** -- if YouTube ever needs the google.com cookies, that is a
    probe to run then, not a guess to make now.
    """
    from .platforms import PLATFORMS      # imported late: platforms is heavier
    return {domain.lower() for platform in PLATFORMS for domain in platform.domains}


def _known_match(domain: str, known: set[str]) -> str | None:
    """The site this cookie belongs to, or None when we do not know it.

    Returns the site from `platforms.py`, not the raw domain, so
    `.www.instagram.com` and `.instagram.com` count as one site instead of
    appearing twice on the card.
    """
    clean = domain.lstrip(".").lower()
    for site in known:
        if clean == site or clean.endswith("." + site):
            return site
    return None


def _rows(lines: list[str]) -> list[tuple[str, float | None, str]]:
    """Every cookie line, as (domain, expiry, the original line).

    The original line is kept whole so a file we write back is byte-for-byte
    what the tools already accept -- we are filtering, not reformatting.
    """
    found: list[tuple[str, float | None, str]] = []
    for line in lines:
        # ⚠️ Strip the LINE ENDING only, never the whitespace.
        # A cookie may have an empty value, and then the line ends with the
        # tab that separates the name from it. `.strip()` ate that tab, the
        # line came back with six fields instead of seven, and it was thrown
        # away in silence. Found 2026-09-22 by the audit: a real YouTube
        # `PREF` cookie vanished, and the card said 6 where the file had 7.
        row = line.rstrip("\r\n")
        if not row.strip():
            continue
        if row.startswith("#"):
            # `#HttpOnly_.example.com` is a real cookie line wearing a comment
            # hat. Skipping it silently would undercount a working file.
            if not row.startswith("#HttpOnly_"):
                continue
            row = row[len("#HttpOnly_"):]

        parts = row.split("\t")
        if len(parts) < 7:
            continue
        try:
            when: float | None = float(parts[4])
        except ValueError:
            when = None
        found.append((parts[0], when, line.rstrip("\r\n")))
    return found


def inspect(path: Path, keep_all: bool = False) -> dict:
    """Describe a Netscape cookie file: how many, for which sites, until when.

    Also splits it in two: the cookies for sites we can download from, and
    everything else. A browser export usually holds every site you are logged
    into -- yt-dlp's own FAQ warns not to let such a file fall into the wrong
    hands -- and there is no reason for a bank or a mailbox to enter this app.

    Raises ``CookieFileError`` with a sentence the user can act on. Never
    returns, logs or keeps a cookie value.
    """
    lines = _read_lines(path)
    rows = _rows(lines)

    if not rows:
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

    known = known_domains()
    now = time.time()

    kept: list[str] = []
    kept_domains: dict[str, int] = {}
    dropped_domains: dict[str, int] = {}
    expired = 0
    soonest_useful: float | None = None

    for domain, when, raw in rows:
        clean = domain.lstrip(".").lower()
        site = _known_match(clean, known)
        if site is None and not keep_all:
            dropped_domains[clean] = dropped_domains.get(clean, 0) + 1
            continue

        kept.append(raw)
        label = site or clean          # keep_all: show the raw domain
        kept_domains[label] = kept_domains.get(label, 0) + 1
        if when is None or when == 0:
            continue                     # session cookie: dies with the browser
        if when < now:
            expired += 1
        elif soonest_useful is None or when < soonest_useful:
            soonest_useful = when

    if not kept:
        others = sorted(dropped_domains)[:4]
        raise CookieFileError(
            "That file has no cookies for a site Teleloadzai can download from"
            + (f" — it holds {', '.join(others)} and others" if others else "")
            + ". Log in to the site you want, then export again. If you need a "
              "site Teleloadzai does not know yet, tick \"keep every site\"."
        )

    if expired == len(kept):
        raise CookieFileError(
            "Every usable cookie in that file has expired. Log in to the site "
            "again in your browser, then export a fresh file."
        )

    top = sorted(kept_domains.items(), key=lambda pair: (-pair[1], pair[0]))
    return {
        "total": len(kept),
        "expired": expired,
        "sites": [name for name, _count in top],
        "expires_at": soonest_useful,
        # What never entered the app. Counted, so the card can prove it.
        "ignored": sum(dropped_domains.values()),
        "ignored_sites": len(dropped_domains),
        "lines": kept,
    }


# --------------------------------------------------------------------------
# what the app does with it
# --------------------------------------------------------------------------

def import_file(chosen: Path, keep_all: bool = False) -> dict:
    """Check the user's file, then write our own SHORTER copy of it.

    Two things happen here, and neither is a copy:

    * **The file is filtered.** Only cookies for sites Teleloadzai can
      download from are written. A browser export usually carries every site
      you are logged into; none of the rest has any business being here, and
      dropping it before writing means it never lands on our disk at all.
    * **We write our own file.** yt-dlp rewrites the jar it is given
      (measured 2026-09-22: a 2-line probe file came back with 12), so the
      file the user picked is never handed to a tool and never opened for
      writing. It is read once and closed.

    ``keep_all`` is the way out for a site we do not know yet -- yt-dlp
    handles far more sites than our table lists, and refusing those would be
    the dead end decision 15 forbids. The user asks for it explicitly.
    """
    chosen = Path(chosen)
    if not chosen.is_file():
        raise CookieFileError("That file no longer exists. Choose it again.")

    summary = inspect(chosen, keep_all=keep_all)     # raises with a reason

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        COOKIE_FILE.write_text(
            "# Netscape HTTP Cookie File\n"
            "# Written by Teleloadzai. Only the sites it can download from.\n"
            + "\n".join(summary["lines"]) + "\n",
            encoding="utf-8",
        )
    except OSError as problem:
        raise CookieFileError(
            f"The cookies could not be saved: {problem.strerror}"
        ) from problem

    summary.pop("lines", None)          # never hand cookie lines back upwards
    return summary


# Phrases that mean "this failed because you are not logged in".
#
# ✅ SEEN, 2026-09-22, from yt-dlp 2026.08.19 on a private Instagram post:
#     "Check if this post is accessible in your browser without being
#      logged-in. If it is not, then use --cookies-from-browser or --cookies
#      for the authentication."
#
# ⚠️ Nothing else is on the list. Until 2026-09-23 nine usual wordings were
# here too, never seen, on the idea that a false match only offers a log-in
# the user can ignore. That was wrong: a match makes the page say "<tool>
# says you need to be logged in" -- a claim about what the tool said
# (decision 38). A phrase joins only when it has really been seen.
#
# ⚠️ And the important negative, also seen: a **private YouTube video** says
# only "This video is unavailable" -- word for word what a **deleted** video
# says. There is nothing to match. That is why a failed download offers the
# log-in as a WAY OUT (decision 15) and only *claims* an account is needed
# when the tool itself said so.
_LOGIN_WORDS = (
    # ONLY what was seen. The page turns a match into "<tool> says you need
    # to be logged in" -- a statement about what the tool said -- so a phrase
    # we have not seen would make the app put words in the tool's mouth
    # (decision 38). Nine unseen phrases were removed on 2026-09-23; "log in"
    # alone would have matched "failed to log in to the proxy".
    "--cookies",                    # seen 2026-09-22, Instagram post C1234567890
                                    # -- an invented id, so a post that does not
                                    # exist. "Log in" is yt-dlp's own advice.
    "for the authentication",       # same message
)


def needs_login(error: str) -> bool:
    """True when the tool itself said the failure is a log-in problem.

    Deliberately narrow. Guessing "you must be logged in" at a video that was
    simply deleted sends the user to type a password for nothing, which is a
    worse answer than saying we do not know.
    """
    low = (error or "").lower()
    return any(word in low for word in _LOGIN_WORDS)


def _key(raw: str) -> tuple[str, str, str]:
    """What makes two cookie lines the same cookie: site, path and name."""
    row = raw[len("#HttpOnly_"):] if raw.startswith("#HttpOnly_") else raw
    parts = row.split("\t")
    if len(parts) < 7:
        return (raw, "", "")
    return (parts[0].lower(), parts[2], parts[5])


def merge_lines(fresh: list[str]) -> int:
    """Add cookie lines to our file, replacing the ones they update.

    Used by the in-app log-in. A merge, not a write: logging in to Instagram
    must not throw away yesterday's YouTube log-in, which a plain overwrite
    would do silently.

    The same filter as the import applies -- only sites Teleloadzai can
    download from. A log-in page can set cookies for a third party it happens
    to use, and those have no more business here than a bank's.

    Returns how many of the fresh lines were kept.
    """
    known = known_domains()
    keeping: dict[tuple[str, str, str], str] = {}

    if have_file():
        for _domain, _when, raw in _rows(COOKIE_FILE.read_text(encoding="utf-8").splitlines()):
            keeping[_key(raw)] = raw

    added = 0
    for raw in fresh:
        domain = _key(raw)[0]
        if _known_match(domain, known) is None:
            continue
        keeping[_key(raw)] = raw
        added += 1

    if not added:
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(
        "# Netscape HTTP Cookie File\n"
        "# Written by Teleloadzai. Only the sites it can download from.\n"
        + "\n".join(keeping.values()) + "\n",
        encoding="utf-8",
    )
    return added


def clear() -> bool:
    """Forget the cookies. Returns True when a file was really removed."""
    if not COOKIE_FILE.exists():
        return False
    COOKIE_FILE.unlink()
    return True


def have_file() -> bool:
    return COOKIE_FILE.is_file() and COOKIE_FILE.stat().st_size > 0


def header_for(site: str, enabled: bool) -> str:
    """The cookies of ONE site as `name=value; name=value`, or "".

    For a tool that wants a cookie string instead of a file. Only that site's
    cookies are returned -- handing TikTokDownloader the whole jar would give
    it every other log-in for nothing.

    ⚠️ The result IS secret. It goes straight into a request body to
    127.0.0.1 and nowhere else: never a command line, never a log, never an
    error message (hard rule 1).
    """
    if not enabled or not have_file():
        return ""
    site = site.lstrip(".").lower()
    pairs: list[str] = []
    for domain, _when, raw in _rows(COOKIE_FILE.read_text(encoding="utf-8").splitlines()):
        host = domain.lstrip(".").lower()
        if host != site and not host.endswith("." + site):
            continue
        row = raw[len("#HttpOnly_"):] if raw.startswith("#HttpOnly_") else raw
        parts = row.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


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
    if tool_id not in FILE_CAPABLE and tool_id not in HEADER_CAPABLE:
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
    # Our own file is already filtered, so this reads it only to count. The
    # cookie lines themselves stop here and never travel to the page.
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
