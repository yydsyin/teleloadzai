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
    # yt-dlp: "Unable to extract initial state" without a log-in on
    # 2026-10-24; on 2026-11-09 (2026.11.04) 11 of 12 qualities came whole
    # with NO cookies (docs/HISTORY.md) -- nothing is needed any more.
    "bilibili|yt-dlp": ("none", "2026-11-09"),
    # yutto 2.3.1 with no cookies: a whole 480p video, 2026-11-09 (1080p
    # needs the log-in, said on the card: runners.TOP_WITHOUT_LOGIN).
    "bilibili|yutto": ("none", "2026-11-09"),
    # The quality check (dev/quality_check.py), 2026-11-15, reviewed by the
    # user: yt-dlp asked for an account on every public link, with no cookies
    # and with a visit's ("Account authentication is required" / "only works
    # when logged-in"). Reddit worked with none on 2026-09-26.
    "reddit|yt-dlp": ("account", "2026-11-15"),
    "vimeo|yt-dlp": ("account", "2026-11-15"),
}

# What a log-in does NOT unlock in the qualities a site offers -- one line
# under Quality on the card. Filled ONLY from quality-check results the user
# reviewed (dev/quality_check.py, data/quality-check/), each with its date:
# sites change what they offer, and the date says how fresh the line is.
QUALITY_SEEN = {
    # yt-dlp, BV1Gsnj6XE9M: "Format(s) 1080P 高码率 are missing; you have to
    # become a premium member", with no cookies AND with a non-premium
    # log-in; 360p to 1080p came either way. yutto: not checked.
    "bilibili|yt-dlp": ("Bilibili keeps “1080p high bitrate” for its premium members: "
                        "a normal log-in did not unlock it.", "2026-11-15"),
}


def quality_note(site: str, program: str) -> str:
    """The card's line under Quality for this site and program, or ""."""
    seen = QUALITY_SEEN.get(f"{site}|{program}")
    return f"{seen[0]} (checked {seen[1]})" if seen else ""


# What the quality check's DOWNLOAD TEST saw failing (dev/quality_check.py,
# its "Does not download" section), filled ONLY after the user's review,
# each with its date and its evidence. The app reads it so it does not pick
# what fails (the user's plan, 2026-11-16).
#   "avoid" + "height" -- yt-dlp: a codec family its "Best" (or that height
#                         chosen) must not take while another file of the
#                         same height exists
#   "fails"            -- another program: it fails on this site
# An entry with "version" applies only while the program is at that version:
# an update may fix it, and the check tests it again (a new version is due).
DOWNLOAD_FAILS: dict[str, dict] = {
    # BV1Gsnj6XE9M: Bilibili's main server cuts the AV1 1080p file (format
    # 100026) -- 5.2 MB of 23.6 MB, "383 bytes read, 22199763 more expected.
    # Giving up after 10 retries", on 2026-11-09 and 2026-11-16; the H.264
    # 1080p (30080) came whole both times (88.6 MB, ffprobe 1080p, 257 s).
    # 3 other videos' AV1 1080p came whole (11-09): H.264 is taken on every
    # Bilibili video at 1080p -- the same height, a bigger file. AV1 720p came
    # whole, so only 1080p. Not tied to a yt-dlp version: the cut is Bilibili's.
    "bilibili|yt-dlp": {"avoid": "av01", "prefer": "h264", "height": 1080, "seen": "2026-11-16"},
    # Rumble refused both test links, with and without cookies: "HTTP Error
    # 403: Forbidden" (RumbleEmbed), on 2026-11-15 and 2026-11-16 (yt-dlp
    # 2026.11.14.232655). Reviewed by the user 2026-11-16. Not tied to a
    # yt-dlp version: the next check after a Rumble change in yt-dlp's
    # release notes reads it again, and this line is reviewed then.
    "rumble|yt-dlp": {"fails": True, "seen": "2026-11-16",
                      "next": "Rumble refused it (403). It may work again after an update."},
    # XHS-Downloader V2.8 crashes reading Xiaohongshu's page, which now holds
    # JavaScript (`new Set([])`): "yaml.parser.ParserError … expected ',' or
    # '}', but got '['", on both test links, 2026-11-16. Its authors: issue
    # #497, opened 2026-10-17, closed as done 2026-10-23, no release after 2.8
    # (2026-09-12; read the same day).
    "xiaohongshu|xhs-downloader": {"fails": True, "version": "XHS-Downloader V2.8 Stable",
                                   "seen": "2026-11-16", "who": "XHS-Downloader 2.8",
                                   "next": "Its authors fixed it: the fix comes with its next version."},
}


def download_fail(site: str, program: str) -> dict | None:
    """The reviewed entry for this site and program, or None. None too when it
    names a version and the program is no longer at it (updated, or removed);
    a version that cannot be read keeps the entry."""
    entry = DOWNLOAD_FAILS.get(f"{site}|{program}")
    if not entry:
        return None
    if entry.get("version"):
        from . import tools     # only this function needs it
        try:
            if tools.installed_path(program) is None:
                return None                     # removed: nothing to warn about
            version = tools.installed_version(program)
            # "" is a version read that failed or timed out (tools.py keeps
            # only real answers): unknown, so the warning stays -- it vanished
            # while the broken 2.8 was still there (hunt, 2026-11-17).
            if version and version != entry["version"]:
                return None
        except Exception:
            # The version could not be read: the entry still applies -- a
            # known failure is avoided rather than offered on a doubt.
            pass
    return dict(entry)


def ytdlp_prefer(site: str, mode: str, quality: str) -> str:
    """The codec yt-dlp should prefer at the same height for this download
    ("h264" on Bilibili at 1080p and "Best"), or "". MP4 only: an MP3 takes
    no picture. Below the entry's height the usual rule stands (AV1 720p came
    whole on Bilibili, 2026-11-09)."""
    entry = download_fail(site, "yt-dlp") if mode == "mp4" else None
    if not entry or not entry.get("prefer"):
        return ""
    if quality == "best" or (str(quality).isdigit() and int(quality) >= entry.get("height", 0)):
        return entry["prefer"]
    return ""


def fails_note(site: str, program: str) -> str:
    """The sentence behind the program's warning sign, or "" -- the reviewed
    download test said this program fails on this site. A warning, never a
    block: Download stays pressable (the user, 2026-11-16)."""
    entry = download_fail(site, program)
    if not entry or not entry.get("fails"):
        return ""
    from .platforms import tool_name
    who = entry.get("who") or tool_name(program)
    return " ".join(filter(None, [f"{who} failed on this site in our last check ({entry['seen']}).",
                                  entry.get("next", "")]))


_lock = threading.Lock()


def _say(text: str) -> None:
    """A problem with this file, said in the Console (decision 34)."""
    from . import console
    console.add("app", f"Teleloadzai: {text}", "err")


_said_unreadable = False


def _read(strict: bool = False) -> dict | None:
    """The file's lines; {} when there is none. With `strict`: a damaged file
    is set aside under a name of its own and said, then {} (learning goes
    on); a file another program holds gives None (this line waits), and
    every line is kept as it is -- the save must not drop a line this
    version does not know (an older Teleloadzai after a newer one, hunt
    round 4, 2026-11-18). Without `strict` (the Sites page), a file that
    cannot be read is said once, not at every look."""
    global _said_unreadable
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a table")
    except FileNotFoundError:
        return {}
    except ValueError:
        if not strict:
            if not _said_unreadable:
                _said_unreadable = True
                _say(f"{FILE.name} is damaged: the Sites page shows only what Teleloadzai "
                     "knew before. It is set aside at the next download.")
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
            _say(f"{FILE.name} could not be read ({problem.strerror or problem}): this download's "
                 "result is not kept on the Sites page.")
        elif not _said_unreadable:
            _said_unreadable = True
            _say(f"{FILE.name} could not be read ({problem.strerror or problem}): the Sites page "
                 "shows only what Teleloadzai knew before.")
        return None if strict else {}
    _said_unreadable = False    # read again: a later damage is said again (hunt round 5)
    if strict:
        return data
    return {k: v for k, v in data.items()
            if isinstance(v, dict) and v.get("need") in KINDS and isinstance(v.get("seen"), str)}


def all_needs() -> dict[str, dict]:
    """{"site|program": {"need": ..., "seen": "YYYY-MM-DD"}} -- what was seen
    last, the file over the proofs it started from."""
    merged = {k: {"need": n, "seen": d} for k, (n, d) in SEEN_BEFORE.items()}
    # Under the save's lock: on Windows a read and a replace of the same file
    # refuse each other (seen on this PC 2026-11-01): the Sites page would
    # lose what was learned for one look, and the result being saved be dropped.
    with _lock:
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
            _say(f"{FILE.name} could not be written ({problem.strerror or problem}): this "
                 "download's result is not kept on the Sites page.")
