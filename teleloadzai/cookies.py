"""The cookie file: import it, describe it, hand it to the tools that can take it.

A cookie is the proof that you are logged in. Some links need it: a private
Instagram post, an age-restricted YouTube video, a Kuaishou video. (Weibo was
named here until 2026-09-27; it works with no log-in -- §4 audit.)

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
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .paths import DATA_DIR

# Our copy. `.gitignore` excludes it -- it holds live sessions.
COOKIE_FILE = DATA_DIR / "cookies.txt"

# One short-lived copy per tool run (`for_one_run`), inside `data/` too.
RUN_DIR = DATA_DIR / "cookie-runs"

# Every change WE make to the file (import, log-in, forget, clean-up) moves
# this on. A tool's write-back is kept only if nothing moved it meanwhile.
_lock = threading.RLock()
_generation = 0


def _changed() -> None:
    global _generation
    with _lock:
        _generation += 1


def _writes(change):
    """For every function that changes our cookie file: one at a time, and a
    tool run that started before it does not write its older jar back."""
    import functools

    @functools.wraps(change)
    def wrapped(*args, **kwargs):
        with _lock:
            try:
                return change(*args, **kwargs)
            finally:
                _changed()
    return wrapped


@contextmanager
def for_one_run(path: Path | None) -> Iterator[Path | None]:
    """The cookie file to hand ONE tool run: a copy of ours, gone afterwards.

    yt-dlp and gallery-dl write their whole jar back into the file they are
    given, when they exit. Given our file itself, a run that had started
    before "Forget them" wrote every log-in back after it, and a log-in made
    during a long download was erased the same way (found by the silent-
    failure hunt, 2026-10-18; yt-dlp's write-back proven with a fake jar).

    What the tool wrote back is still kept -- a site renews its cookies, and
    losing that would end a log-in sooner -- but only when nothing else
    changed our file during the run. Otherwise the user's newer choice wins.
    """
    if path is None:
        yield None
        return
    with _lock:
        started = _generation
        if not Path(path).is_file():
            # Forgotten between Add and the start: never run on as if there
            # were none without saying so (round 2 of the hunt, 2026-10-18).
            raise CookieFileError(
                "Your log-ins were forgotten after this download was added. "
                "Press Retry to download without them.")
        copy = RUN_DIR / f"{uuid.uuid4().hex}.txt"
        try:
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, copy)
        except OSError as problem:
            copy.unlink(missing_ok=True)
            # Never run on as if there were no cookies: the user turned them on.
            raise CookieFileError(
                f"The cookies could not be prepared for this download: {problem.strerror}"
            ) from problem
    try:
        yield copy
    finally:
        with _lock:
            try:
                if (_generation == started and COOKIE_FILE.is_file()
                        and copy.is_file() and copy.stat().st_size > 0):
                    copy.replace(COOKIE_FILE)
                    _changed()          # a second run's older jar must not win
            except OSError:
                pass                    # ours stays as it was: nothing lost
            finally:
                copy.unlink(missing_ok=True)


def clear_run_copies() -> None:
    """Delete every run copy -- at start (a crash leaves them) and when the
    user forgets the cookies."""
    with _lock:
        if RUN_DIR.is_dir():
            # Every file: gallery-dl saves its jar as `<copy>.txt.tmp` first,
            # and one killed during that save left a whole jar behind.
            for leftover in RUN_DIR.iterdir():
                try:
                    leftover.unlink()
                except OSError:
                    pass                # deleted at the next start

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
}

# TikTokDownloader takes the cookie in the BODY of a request to its own local
# server, not on a command line -- so it is safe to give it one, and it is not
# in the list above. It needs the cookie as a header string rather than a
# file, which is what `header_for` is for. KS-Downloader (2026-09-23) is the
# same: `/detail/` has a `cookies` field, read from its own /openapi.json.
HEADER_CAPABLE = ("tiktokdownloader", "ks-downloader")

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
    # Only sites with a tool. A site listed to be REFUSED (Netflix, decision
    # 10) or with no link-driven tool (WeChat Channels) is not a site we
    # download from, and its cookies have no business in our file.
    return {domain.lower() for platform in PLATFORMS if platform.is_supported
            for domain in platform.domains}


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


def inspect(path: Path) -> dict:
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
                "That file is JSON, not the format the download programs read. In "
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
    soonest_site = ""                    # whose cookie ends first -- said by name

    for domain, when, raw in rows:
        clean = domain.lstrip(".").lower()
        site = _known_match(clean, known)
        if site is None:
            dropped_domains[clean] = dropped_domains.get(clean, 0) + 1
            continue

        kept.append(raw)
        label = site
        kept_domains[label] = kept_domains.get(label, 0) + 1
        if when is None or when == 0:
            continue                     # session cookie: dies with the browser
        if when < now:
            expired += 1
        elif soonest_useful is None or when < soonest_useful:
            soonest_useful = when
            soonest_site = label

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
        "expires_site": soonest_site,
        # What never entered the app. Counted, so the card can prove it.
        "ignored": sum(dropped_domains.values()),
        "ignored_sites": len(dropped_domains),
        "lines": kept,
    }


# --------------------------------------------------------------------------
# what the app does with it
# --------------------------------------------------------------------------

@_writes
def import_file(chosen: Path) -> dict:
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

    There is no way round the filter. A "keep every site" option existed
    until 2026-10-23 and was removed by the user: it saved a whole browser
    export, bank and mail included, and drop_unsupported deleted what it
    kept at the next start anyway. A site outside our table still downloads
    through yt-dlp; only a log-in there is not offered.
    """
    chosen = Path(chosen)
    if not chosen.is_file():
        raise CookieFileError("That file no longer exists. Choose it again.")

    summary = inspect(chosen)     # raises with a reason

    # Added to what is there, not written over it -- as the in-app log-in
    # does (merge_lines). The file replaced the whole store: a TikTok log-in
    # made in the window was erased in silence by a cookies.txt with no
    # TikTok in it (proven 2026-10-23 on a scratch store, made-up cookies).
    # A cookie the file carries again (same site, path, name) is replaced.
    keeping: dict[tuple[str, str, str], str] = {}
    if have_file():
        for _domain, _when, raw in _rows(COOKIE_FILE.read_text(encoding="utf-8").splitlines()):
            keeping[_key(raw)] = raw
    for raw in summary["lines"]:
        keeping[_key(raw)] = raw

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        COOKIE_FILE.write_text(
            "# Netscape HTTP Cookie File\n"
            "# Written by Teleloadzai. Only the sites it can download from.\n"
            + "\n".join(keeping.values()) + "\n",
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


@_writes
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


@_writes
def clear() -> bool:
    """Forget the cookies. Returns True when a file was really removed."""
    clear_run_copies()          # the copies a running tool holds go too
    if not COOKIE_FILE.exists():
        return False
    COOKIE_FILE.unlink()
    return True


def have_file() -> bool:
    return COOKIE_FILE.is_file() and COOKIE_FILE.stat().st_size > 0


def site_dates() -> dict[str, dict]:
    """For each site in our file: how many cookies, and their latest end date.

    `latest` is the furthest expiry among cookies that HAVE one (0 = only
    session cookies, whose end nobody can tell). Dates and counts only --
    never a name or a value -- for the log-in buttons' signs.
    """
    if not have_file():
        return {}
    known = known_domains()
    found: dict[str, dict] = {}
    for domain, when, _raw in _rows(COOKIE_FILE.read_text(encoding="utf-8").splitlines()):
        site = _known_match(domain.lstrip(".").lower(), known)
        if site is None:
            continue
        entry = found.setdefault(site, {"count": 0, "latest": 0.0})
        entry["count"] += 1
        if when:
            entry["latest"] = max(entry["latest"], when)
    return found


def badge_dates(domains: tuple[str, ...], names: tuple[str, ...]) -> list[float] | None:
    """The end dates of a site's log-in cookies, or None when there is none.

    A "badge" is a cookie a site hands only to a logged-in user. 0 in the
    list means a session cookie: the site gave no end date. Names and dates
    are looked at -- never a value (hard rule 1).
    """
    if not have_file():
        return None
    wanted = {d.lower() for d in domains}
    found: list[float] = []
    for domain, when, raw in _rows(COOKIE_FILE.read_text(encoding="utf-8").splitlines()):
        host = domain.lstrip(".").lower()
        if not any(host == d or host.endswith("." + d) for d in wanted):
            continue
        row = raw[len("#HttpOnly_"):] if raw.startswith("#HttpOnly_") else raw
        if row.split("\t")[5] in names:
            found.append(when or 0.0)
    return found or None


@_writes
def drop_unsupported() -> int:
    """Remove the cookies of sites we no longer download from. Returns how many.

    The filter only guards what COMES IN. A site refused later (Netflix,
    decision 10, refused from 2026-09-24) kept the cookies it already had:
    5 netflix.com cookies were found in the user's file on 2026-09-25.
    Run at every start, so the file always matches today's list.

    Written to a temporary file first, and put in place only once complete:
    a failure half-way must never leave the user with an empty file.
    """
    if not have_file():
        return 0
    known = known_domains()
    lines = COOKIE_FILE.read_text(encoding="utf-8").splitlines()
    keep = [raw for domain, _when, raw in _rows(lines)
            if _known_match(domain, known) is not None]
    dropped = len(_rows(lines)) - len(keep)
    if not dropped:
        return 0
    temporary = COOKIE_FILE.with_name(COOKIE_FILE.name + ".tmp")
    temporary.write_text(
        "# Netscape HTTP Cookie File\n"
        "# Written by Teleloadzai. Only the sites it can download from.\n"
        + "\n".join(keep) + ("\n" if keep else ""),
        encoding="utf-8",
    )
    temporary.replace(COOKIE_FILE)
    return dropped


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
        # "The soonest expires today" named no site (review of 2026-09-28).
        "expires_site": summary.get("expires_site", ""),
        # Both roads: the file tools AND the server tools. Until 2026-09-25
        # this named the file tools only, while TikTokDownloader and
        # KS-Downloader received the cookies too (seen by the critique).
        # Their display names, not our ids.
        "used_by": [_tool_name(t) for t in FILE_CAPABLE + HEADER_CAPABLE],
    }


def _tool_name(tool_id: str) -> str:
    from .platforms import tool_name      # imported late, like known_domains
    return tool_name(tool_id)
