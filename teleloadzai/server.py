"""The window of Teleloadzai: a tiny local web server.

Two safety rules, because a web page is easy to reach by accident:

* the server listens on 127.0.0.1 only, never on the network;
* every ``/api/`` call must carry the secret token created at startup, so
  another site open in the same browser cannot drive Teleloadzai.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import console, cookies, dialogs, explain, login, needs, notify, runners, toolservers, tools, ytdlp
from .config import APP_NAME, APP_VERSION
from .detect import Detection, detect
from .jobs import DONE, ERROR, Queue, TargetInUse, target_clashes
from .paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR, WEB_DIR, ensure_dirs
from .platforms import PLATFORMS, tool_name

SETTINGS_FILE = DATA_DIR / "settings.json"
_settings_lock = threading.Lock()
TOKEN = secrets.token_urlsafe(24)

MAX_PARALLEL_DEFAULT = 2
MAX_PARALLEL_LIMIT = 5


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        stored = {}
    return {
        "download_folder": stored.get("download_folder") or str(DEFAULT_DOWNLOAD_DIR),
        "max_parallel": stored.get("max_parallel") or MAX_PARALLEL_DEFAULT,
        # Ask where to save each file, like a browser does. On by default.
        "ask_where": bool(stored.get("ask_where", True)),
        # False until the first-launch screen has been answered once.
        "setup_done": bool(stored.get("setup_done", False)),
        # A live stream never ends by itself: stop recording after this long.
        "record_minutes": int(stored.get("record_minutes") or 60),
        # Log-in cookies. OFF by default (decision 9) -- they are as sensitive
        # as a password, and nothing here turns itself on.
        "cookies_enabled": bool(stored.get("cookies_enabled", False)),
        # "keep"  -- stay logged in, like a browser. The useful default once
        #            the user has taken the trouble to log in at all.
        # "once"  -- forget everything when Teleloadzai closes: the cookies
        #            AND the log-in window's profile. For a shared PC.
        "cookies_keep": "once" if stored.get("cookies_keep") == "once" else "keep",
        # The user's own default tool per site, {platform id: tool id}
        # (decision 13, first level). Only sites where he changed it.
        "tool_choice": {k: v for k, v in (stored.get("tool_choice") or {}).items()
                        if isinstance(k, str) and isinstance(v, str)},
        # Decision 19: "ask" (a bar, and "Update and retry" on a failed row)
        # is the default; "auto" updates and retries once by itself;
        # "manual" only shows the badges in Settings -> Tools.
        "update_mode": stored.get("update_mode") if stored.get("update_mode")
                       in ("ask", "auto", "manual") else "ask",
        # yt-dlp's release channel: "stable", or "preview" (nightly builds).
        "ytdlp_channel": "preview" if stored.get("ytdlp_channel") == "preview" else "stable",
        # Take a link the user copied when the window comes to the front
        # (Phase 2 item 3, 2026-10-24). On by default, as in Open Video
        # Downloader; only the links ever leave `clipboard_links`.
        "use_clipboard": bool(stored.get("use_clipboard", True)),
        # Read a link the moment it is pasted. OFF by default (the user,
        # 2026-10-26: a link to change was read before it could be changed);
        # off, the link waits in the box for Read or Enter.
        "auto_read": bool(stored.get("auto_read", False)),
        # Several links or a playlist: "same" (one set of choices for all) or
        # "each" (a row of choices per video). The user's own pick, kept
        # (asked 2026-10-24: "its users to choose what mode").
        "several_mode": "each" if stored.get("several_mode") == "each" else "same",
        # The Subtitles row's last choice (Phase 2 item 7): "" off by default.
        "subs_mode": stored.get("subs_mode") if stored.get("subs_mode") in ("embed", "file") else "",
        # A Windows message when a download ends and the window is not in
        # front (Phase 2 item 6). On by default; some people dislike them.
        "notify_done": bool(stored.get("notify_done", True)),
    }


# The same link shape as the page's `linksIn`.
_LINK = re.compile(r"https?://[^\s\"'<>，。！？、]+", re.IGNORECASE)


def clipboard_links() -> list[str]:
    """The links in the Windows clipboard -- and NOTHING else of it.

    A clipboard can hold a password or a private message: its text never
    leaves this function, is never stored and never printed. Read with
    Windows' own functions (ctypes, standard library: decision 20), only
    when the page asks -- the window came to the front, or Paste was pressed.
    Raises OSError when another program holds the clipboard.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(10):                 # another program may hold it a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("another program is using the clipboard")
    try:
        handle = user32.GetClipboardData(13)        # CF_UNICODETEXT
        if not handle:
            return []                               # a picture, a file, nothing
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return []
        try:
            text = ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return list(dict.fromkeys(_LINK.findall(text)))


def usable_tools(platform) -> list:
    """The tools we can drive for this site, the user's choice first.

    Order is the whole mechanism: the first one is what the download page
    picks. A saved choice that is no longer usable (removed from the table,
    or blocked) is ignored rather than obeyed into a dead end.
    """
    offered = [o for o in platform.tools if runners.unavailable_reason(o.tool_id) is None]
    chosen = load_settings()["tool_choice"].get(platform.id)
    return sorted(offered, key=lambda o: o.tool_id != chosen)


def tool_choices() -> list[dict]:
    """Every site with a usable tool, and its tools. A choice exists only
    where there are two or more; the page draws a list there and the
    program's name elsewhere (Settings -> Sites, 2026-10-22: one row per
    site, its program and its log-in)."""
    rows = []
    for platform in PLATFORMS:
        offered = usable_tools(platform)
        if not offered:
            continue
        # The default the user really gets: our first USABLE tool. Weibo's
        # first is f2, which cannot run yet, so "(default)" was drawn on no
        # row at all (seen on screen 2026-09-24).
        usable_default = next(o.tool_id for o in platform.tools
                              if runners.unavailable_reason(o.tool_id) is None)
        rows.append({
            "id": platform.id, "name": platform.name,
            "chosen": offered[0].tool_id,
            "default": usable_default,
            "tools": [{"id": o.tool_id, "name": tool_name(o.tool_id), "why": o.why}
                      for o in platform.tools
                      if runners.unavailable_reason(o.tool_id) is None],
        })
    return rows


def save_settings(settings: dict) -> None:
    """To a temporary file first, then put in place: a reader meeting half a
    file got the defaults, and its next save wrote them over every setting
    (hunt of 2026-10-31)."""
    ensure_dirs()
    with _settings_lock:
        temp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        temp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(temp, SETTINGS_FILE)


def forget_if_once() -> bool:
    """On the way out, honour "forget when I close Teleloadzai".

    Called when the app shuts down. "Once" is worth nothing if it only means
    a label in the settings: the cookie file AND the log-in window's browser
    profile both have to go, or the next start opens still logged in.

    Returns True when something was really removed.
    """
    if load_settings()["cookies_keep"] != "once":
        return False
    gone = cookies.clear()
    login.forget_history()
    # This runs after the window engine has stopped, which is the one moment
    # Windows lets the profile folder go (it stays locked while the app runs).
    if login.forget_browser() in ("now", "later"):
        gone = True
    settings = load_settings()
    settings["cookies_enabled"] = False
    save_settings(settings)
    return gone


def _login_saved(kept: int) -> None:
    """A log-in window saved cookies by itself: switch them on.

    The same rule as the "I have logged in" button and the file import --
    logging in IS the consent. Without this, a window that finished on its
    own would leave the switch off, and the next download would run without
    the cookies the user has just logged in for.
    """
    settings = load_settings()
    settings["cookies_enabled"] = True
    save_settings(settings)


login.on_saved = _login_saved


def _retry_folder(old) -> str:
    """The folder a Retry goes to: the first try's, when it still exists.
    A row from several links went to the folder chosen for them; its Retry
    must not land in the Settings folder instead (2026-10-24)."""
    return str(old.folder) if old.folder and Path(old.folder).is_dir() else ""


def _retry_target(old, replace_own: bool = False) -> str:
    """The "Save as" path a Retry or "Download again" may reuse.

    Windows asked about replacing that name BEFORE the first attempt. If the
    first attempt left a file under it -- a recording kept by Stop -- that
    file is not what Windows asked about: "Download again" replaced it
    without a word (round 4 of the hunt, 2026-10-18). Then the same folder,
    with the next free name ("my live (2).mp4").
    The same when ANOTHER download wrote that name since, or will: a failed
    "unknown.mp4", then a second untitled video saved as "unknown.mp4"
    (Windows could not ask, the first had left nothing), then Retry on the
    first -- the second video was replaced (hunt of 2026-10-31, round 2).
    `replace_own`: a FINISHED row's "Download again", confirmed by its second
    click ("Replace the file? Click again"), replaces that row's own file,
    as it says -- it made "name (2)" while saying "Replace" (same hunt).
    """
    if not old.target:
        return old.target
    chosen = Path(old.target)
    taken = QUEUE.targets_in_use(besides=old.id)
    mine = {os.path.normcase(os.path.abspath(f)) for f in old.files}
    if replace_own and old.state == DONE and not target_clashes(old.target, taken) \
            and os.path.normcase(os.path.abspath(chosen)) in mine:
        return old.target
    if not any(Path(f).is_file() for f in old.files) and not chosen.exists() \
            and not target_clashes(old.target, taken):
        return old.target
    ending = chosen.suffix.lstrip(".")
    return str(chosen.with_name(dialogs.free_name(chosen.parent, chosen.stem, ending, taken)
                                + chosen.suffix))


def queue_download(url: str, mode: str, quality: str, title: str, target: str,
                   tool: str, platform: str, force: bool = False,
                   replace: str = "", folder: str = "",
                   subs: str = "", sub_lang: str = "",
                   items: list[str] | None = None) -> tuple[dict, int]:
    """Check a download request and put it in the queue. Returns (json, status).

    ``replace`` is the id of a finished job this one takes the place of --
    Retry, "Download again", "Try with another tool". The cookies are decided
    NOW, from the current settings, never copied from the old attempt: a job
    that failed with cookies off, followed by a log-in, must retry WITH them
    (found 2026-09-23 -- the old Retry copied the failed attempt's choice).
    """
    allowed = ytdlp.AUDIO_QUALITIES if mode == "mp3" else ytdlp.VIDEO_QUALITIES
    if mode not in ("mp3", "mp4") or quality not in allowed:
        return {"error": "bad mode or quality"}, 400
    # Only a tool we know how to drive, and only one that is here.
    if not runners.can_run(tool):
        return {"error": f"no runner for {tool}"}, 400
    # Only a choice this tool really makes (runners.CHOICES). A quality it
    # never receives is not carried as if it were: "best" is what happens.
    can = runners.CHOICES.get(tool, {})
    if mode not in can:
        return {"error": f"{tool_name(tool)} cannot make an MP3. Choose MP4, or another tool."}, 400
    if not can[mode]:
        quality = "best"
    if tools.installed_path(tool) is None:
        return {"error": f"{tool} is not installed"}, 400
    # Subtitles (Phase 2 item 7): only in MP4, only for a program that makes
    # them (runners.CHOICES "subs"), only a code shaped like one. Anything
    # else is dropped, never passed on as if it would happen.
    if subs not in ("embed", "file") or mode != "mp4" or not can.get("subs") \
            or not ytdlp.SUB_LANG.fullmatch(sub_lang or ""):
        subs, sub_lang = "", ""
    # Several links go to ONE folder chosen in the Windows window (the user's
    # choice, 2026-10-24), and a Retry goes back to where its first try
    # went. Only a folder that exists: never one made up by a page.
    if folder and not Path(folder).is_dir():
        return {"error": f"The folder {folder} does not exist."}, 400
    # Cookies, when the user has them on AND this tool can take them. `note`
    # is the sentence for the case where it cannot -- it travels with the job
    # so the row can say it instead of failing in silence.
    on = load_settings()["cookies_enabled"]
    # "" when nobody could read the title: the row says so, and the file is
    # named "unknown" -- never the raw link (the user, 2026-09-26).
    # A file another download in the list will write is refused (checked in
    # the same step as the add): Windows could not ask about it (not on the
    # disk yet), and the second would replace the first.
    try:
        job = QUEUE.add(url, mode, quality, title, Path(folder) if folder else download_folder(),
                        Path(target) if target else None, force=force, tool=tool,
                        limit_minutes=record_minutes(),
                        cookie_file=cookies.path_for(tool, on),
                        cookie_note=cookies.unusable_reason(tool, on) or "",
                        platform=platform,
                        cookie_header=on and tool in cookies.HEADER_CAPABLE,
                        replace=replace, subs=subs, sub_lang=sub_lang, items=items)
    except TargetInUse as taken:
        return {"error": f"Another download in the list is already saving to “{taken}”. "
                         "Choose another name."}, 409
    if job is None:
        return {"error": "that download is still running, or no longer exists"}, 409
    return job.as_dict(), 200


def other_tool(job: dict) -> dict | None:
    """The next tool worth trying on a failed job, or None.

    Only a tool the platform lists, that we can drive, and that is installed
    -- offering one that cannot run would be the dead end decision 15
    forbids, dressed up as a way out.
    """
    if job.get("state") != "error" or not job.get("platform"):
        return None
    platform = next((p for p in PLATFORMS if p.id == job["platform"]), None)
    if platform is None:
        return None
    for option in platform.tools:
        tid = option.tool_id
        if (tid != job.get("tool") and runners.unavailable_reason(tid) is None
                and tools.installed_path(tid) is not None
                # an MP3 job is never sent to a tool that makes no MP3
                and job.get("mode") in runners.CHOICES.get(tid, {})):
            return {"id": tid, "name": tool_name(tid)}
    return None


def download_folder() -> Path:
    return Path(load_settings()["download_folder"])


def record_minutes() -> int:
    """How long a live recording may last. 0 means no limit, at the user's risk."""
    try:
        value = int(load_settings()["record_minutes"])
    except (TypeError, ValueError):
        return 60
    return max(0, min(24 * 60, value))


def max_parallel() -> int:
    try:
        value = int(load_settings()["max_parallel"])
    except (TypeError, ValueError):
        return MAX_PARALLEL_DEFAULT
    return max(1, min(MAX_PARALLEL_LIMIT, value))


# The list survives closing (Phase 2 item 2, 2026-10-24): data/jobs.json,
# in the folder .gitignore already keeps out of git. Loaded by __main__
# AFTER the port is claimed (decision 21), never at import.
QUEUE = Queue(max_parallel, store=DATA_DIR / "jobs.json")
# The end-of-download message asks the setting at the moment it would show,
# so switching it off works at once.
notify.enabled = lambda: load_settings()["notify_done"]
# ...and only once nothing waits or runs: one message for a whole playlist.
notify.busy = lambda: QUEUE.unfinished() > 0
tools.set_preview("yt-dlp", load_settings()["ytdlp_channel"] == "preview")


# --------------------------------------------------------------------------
# installing a tool, watched from the Tools page
# --------------------------------------------------------------------------

_installs: dict[str, dict] = {}
_installs_lock = threading.Lock()


def _set_install(tool_id: str, **fields) -> None:
    with _installs_lock:
        _installs.setdefault(tool_id, {}).update(fields)


def start_install(tool_id: str) -> dict:
    """Install one tool in the background so the window stays alive."""
    with _installs_lock:
        current = _installs.get(tool_id)
        if current and current.get("state") == "running":
            return current
        _installs[tool_id] = {"state": "running", "stage": "starting",
                              "percent": 0, "error": ""}

    # The Console shows installs and updates too (the user, 2026-10-26): a
    # title line, each step once (never every percent), then the result.
    line_id = f"install-{tool_id}-{next(_read_numbers)}"
    spec = tools.spec(tool_id)
    name = spec.name if spec else tool_id
    said = {"stage": ""}

    def step(stage: str, pct) -> None:
        _set_install(tool_id, stage=stage, percent=pct)
        if stage and stage != said["stage"]:
            said["stage"] = stage
            console.add(line_id, stage[:1].upper() + stage[1:] + "…")

    def work() -> None:
        try:
            console.add(line_id, f"{'Updating' if tools.status(tool_id, check_online=False)['installed'] else 'Installing'} {name}", "head")
            # Never while this tool downloads (decision 19): it waits, and
            # says so. Its new downloads do not start meanwhile.
            while QUEUE.busy(tool_id):
                count = QUEUE.busy(tool_id)
                _set_install(tool_id, stage=f"waits for {count} download"
                             f"{'s' if count > 1 else ''} to finish", percent=0)
                time.sleep(2)
            QUEUE.hold(tool_id)
            try:
                before = tools.status(tool_id, check_online=False)
                tools.install(tool_id, step)
                after = tools.status(tool_id, check_online=False)
            finally:
                QUEUE.release(tool_id)
            # "Updated" only when the version really changed: read from the
            # tool itself, or the release we installed when it prints none.
            old = before["version"] or before["release_installed"]
            new = after["version"] or after["release_installed"]
            _set_install(tool_id, state="done", stage="done", percent=100,
                         before=old if before["installed"] else "", after=new,
                         changed=(not before["installed"]) or old != new
                         or before["channel"] != after["channel"],
                         switched=before["installed"] and before["channel"] != after["channel"],
                         channel=after["channel"])
            # Our words, the same as the page's (installSentence): "updated"
            # only when the version read really changed.
            console.add(line_id, f"{name} installed: {new}." if not before["installed"]
                        else f"Updated: {old} → {new}." if old != new
                        else f"Switched to its {after['channel']} builds: {new}." if before["channel"] != after["channel"]
                        else f"The update did not change {name}: {new} is kept.", "end")
        except tools.InstallError as exc:
            # "python_missing" is not a failure, it is a question for the user.
            _set_install(tool_id, state="error", error=str(exc))
            console.add(line_id, f"Failed: {exc}", "err")
        except Exception as exc:
            _set_install(tool_id, state="error", error=f"{type(exc).__name__}: {exc}")
            console.add(line_id, f"Failed: {type(exc).__name__}: {exc}", "err")

    threading.Thread(target=work, daemon=True).start()
    with _installs_lock:
        return dict(_installs[tool_id])


def install_progress() -> dict:
    with _installs_lock:
        return {k: dict(v) for k, v in _installs.items()}


# Sites where yt-dlp cannot read a link, so the title comes from the tool that
# downloads it (asked by the user 2026-09-26). Seen, not assumed: Douyin ->
# yt-dlp "Fresh cookies ... are needed" after 7.5 s; Kuaishou -> "Unsupported
# URL". Their own tools answered: 22 s and 12.5 s. Everywhere else yt-dlp
# reads faster and stays (the user's choice, the same day).
_READ_BY_TOOL = ("douyin", "kuaishou")

# Sites where yt-dlp is not a download tool but DOES read the title: the card
# said "no preview" there. Xiaohongshu, 2026-09-26, the user's own note: title
# read in 6.8 s, while XHS-Downloader downloaded it (198 MB, 1280p).
_READ_BY_YTDLP = ("xiaohongshu",)


_read_numbers = itertools.count(1)


def _console_read(read_id: str, answer: dict) -> None:
    """How a title read by the site's own tool ended, in the Console: the
    title or the error (its first line is written as the read starts)."""
    if answer.get("error"):
        console.add(read_id, f"Could not read the title: {answer['error']}", "err")
    else:
        console.add(read_id, f"Title: {answer['title']}" if answer.get("title")
                    else "No title in the answer.", "end")


def tool_probe(platform_id: str, url: str) -> dict:
    """The card's title, picture and length, read by the site's own tool."""
    cookies_on = bool(load_settings()["cookies_enabled"])
    if platform_id == "douyin":
        server, name = toolservers.TIKTOK, "TikTokDownloader"
        read = lambda: toolservers.detail(url, True, cookies.header_for("douyin.com", cookies_on))
        fields = ("desc", "nickname", "static_cover")
    else:
        server, name = toolservers.KS, "KS-Downloader"
        read = lambda: toolservers.ks_detail(url, cookies.header_for("kuaishou.com", cookies_on))
        fields = ("caption", "name", "coverUrl")
    try:
        server.start()
        try:
            data = read()
        finally:
            server.release()      # its door is 0.0.0.0: open only while used
    except Exception as exc:
        said = cookies.redact(str(exc))
        return {"error": said, "kind": "probe_failed",
                "explain": explain.explain(said, server.tool_id),
                "from_tool": explain.said_by_tool(exc)}
    seconds = None
    try:                          # both say "00:04:46"
        h, m, s = (int(x) for x in str(data.get("duration", "")).split(":"))
        seconds = h * 3600 + m * 60 + s
    except ValueError:
        pass
    title, uploader, picture = (data.get(f) or "" for f in fields)
    return {"title": title, "uploader": uploader, "duration": seconds,
            "thumbnail": picture, "extractor": name, "is_playlist": False, "entries": 0}


# --------------------------------------------------------------------------
# JSON shapes
# --------------------------------------------------------------------------

def detection_json(result: Detection) -> dict:
    platform = result.platform
    # The user's saved choice first: the page picks the first one.
    offered = usable_tools(platform)
    cookies_on = bool(load_settings()["cookies_enabled"])
    blocked = [
        {"name": tool_name(o.tool_id), "why": runners.unavailable_reason(o.tool_id)}
        for o in platform.tools if runners.unavailable_reason(o.tool_id) is not None
    ]

    # A platform whose tools all exist but none of which we can drive is not
    # "supported": saying so would promise a download we cannot make.
    note = platform.note
    if platform.tools and not offered:
        note = (note + " " if note else "") + " · ".join(
            f"{b['name']}: {b['why']}" for b in blocked)

    return {
        "platform": platform.name,
        "platform_id": platform.id,
        "supported": bool(offered),
        "note": note,
        "blocked": blocked,
        # Who reads the title for the card: yt-dlp where it is one of the
        # site's tools, the site's own tool on Douyin and Kuaishou, nobody
        # elsewhere (Xiaohongshu: not tested).
        "read_by": ({"id": "yt-dlp", "name": "yt-dlp"}
                    if any(o.tool_id == "yt-dlp" for o in offered) or platform.id in _READ_BY_YTDLP
                    else {"id": offered[0].tool_id, "name": tool_name(offered[0].tool_id)}
                    if offered and platform.id in _READ_BY_TOOL else None),
        "final_url": result.final_url,
        "was_shortened": result.was_shortened,
        "redirect_error": result.redirect_error,
        # FFmpeg is every download's base (decision 28): missing, the card
        # offers it like a missing tool -- never a Download that must fail.
        "ffmpeg_missing": tools.installed_path("ffmpeg") is None,
        "ffmpeg_size": (tools.latest_release("ffmpeg").get("size", 0)
                        if tools.installed_path("ffmpeg") is None else 0),
        "tools": [
            {
                "id": option.tool_id,
                "name": tool_name(option.tool_id),
                "why": option.why,
                # So the window can offer to install it instead of refusing
                # (decision 6). Never a dead end.
                "installed": tools.installed_path(option.tool_id) is not None,
                "size": tools.latest_release(option.tool_id).get("size", 0),
                "needs_python": bool(getattr(tools.spec(option.tool_id), "needs_python", False)),
                # A log-in or a visit this tool needs here, said BEFORE the
                # download (the 2026-09-26 audit). None when nothing is proven.
                "need": login.need(platform.id, option.tool_id, cookies_on),
                # The buttons the window may show for this tool, and no other.
                "choices": runners.CHOICES.get(option.tool_id, {"mp4": ""}),
                # Formats where it names the file itself: asked a folder.
                "names_itself": list(runners.NAMES_ITSELF.get(option.tool_id, ())),
            }
            for option in offered
        ],
    }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):      # keep the console quiet
        pass

    # -- helpers -----------------------------------------------------------

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self._answered = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _authorised(self) -> bool:
        """Local host + secret token. Blocks other pages and DNS rebinding."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        return secrets.compare_digest(self.headers.get("X-App-Token", ""), TOKEN)

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:
        path = urlsplit(self.path).path

        if path == "/":
            page = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            # The app name lives only in config.py (decision 1), so it is
            # injected here instead of being written inside the page.
            page = page.replace("__APP_TOKEN__", TOKEN).replace("__APP_NAME__", APP_NAME)
            self._send(page.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path.startswith("/api/"):
            if not self._authorised():
                self._json({"error": "not allowed"}, 403)
                return

            if path == "/api/settings":
                self._json(load_settings())
                return

            if path == "/api/cookies":
                self._json({
                    "cookies": cookies.state(load_settings()["cookies_enabled"]),
                    "login_platforms": login.choices(),
                    # Why the in-app log-in cannot run, when it cannot. Said,
                    # not hidden behind a button that does nothing.
                    "login_blocked": login.unavailable_reason(),
                    # What each site needs per program, last seen (needs.py).
                    "needs": needs.all_needs(),
                })
                return

            if path == "/api/tool-choices":
                self._json({"sites": tool_choices()})
                return

            if path == "/api/sites":
                # The empty main screen said nothing about which sites work
                # (review of 2026-09-27). Counted from the table, never
                # written by hand.
                self._json({"sites": [p.name for p in PLATFORMS
                                      if p.is_supported and p.domains]})
                return

            if path == "/api/qualities":
                self._json({
                    "mp3": list(ytdlp.AUDIO_QUALITIES),
                    "mp4": list(ytdlp.VIDEO_QUALITIES),
                })
                return

            if path == "/api/console":
                # The Console page (2026-10-25): the lines since `since`, and
                # what runs now, for its state line. Washed when kept.
                try:
                    start = int(parse_qs(urlsplit(self.path).query).get("since", ["0"])[0])
                except ValueError:
                    start = 0
                lines, upto = console.since(start)
                running = [{"title": j["title"] or j["url"], "tool": tool_name(j["tool"])}
                           for j in QUEUE.all() if j["state"] == "running"]
                self._json({"lines": lines, "next": upto, "running": running})
                return

            if path == "/api/jobs":
                jobs = QUEUE.all()
                for job in jobs:
                    job["other_tool"] = other_tool(job)
                    # Said with its real name: rows read "Update
                    # tiktokdownloader" (review of 2026-09-28).
                    job["tool_name"] = tool_name(job["tool"])
                self._json({"jobs": jobs, "load_problem": QUEUE.load_problem})
                return

            if path == "/api/tools":
                self._json({
                    "tools": tools.status_all(),
                    "python": tools.python_state(),
                    "progress": install_progress(),
                })
                return

            if path == "/api/tools/progress":
                self._json({"progress": install_progress()})
                return

            if path == "/api/python":
                self._json(tools.python_state())
                return

        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        """Every request gets an answer. An unexpected error used to close
        the connection with none, and the button pressed did nothing, with
        no word (decision 34; hunt of 2026-10-31: a damaged cookie store
        under "Import")."""
        self._answered = False
        try:
            self._do_post()
        except (BrokenPipeError, ConnectionError):
            pass                # the page went away: nobody to tell
        except Exception as problem:
            traceback.print_exc()
            if not self._answered:
                words = cookies.redact(str(problem))[:300]
                self._json({"error": f"Teleloadzai hit an unexpected problem "
                                     f"({type(problem).__name__}: {words})."}, 500)

    def _do_post(self) -> None:
        path = urlsplit(self.path).path
        if not path.startswith("/api/") or not self._authorised():
            # Its body is never read: the connection is closed, or those bytes
            # began the next request on it ('{"asked":false}GET' -> 501), and
            # a tab holding an old token showed an empty list (2026-10-31).
            self.close_connection = True
            self._json({"error": "not allowed"}, 403)
            return

        body = self._body()

        if path == "/api/detect":
            url = (body.get("url") or "").strip()
            if not url:
                self._json({"error": "no link"}, 400)
                return
            self._json(detection_json(detect(url)))
            return

        if path == "/api/probe":
            url = (body.get("url") or "").strip()
            platform_id = detect(url).platform.id
            # The Console shows title reads too, not only downloads (the
            # user, 2026-10-26): a failed read kept only one line on the card.
            read_id = f"read-{next(_read_numbers)}"
            if platform_id in _READ_BY_TOOL:
                # The line first, as for yt-dlp: these reads take 12-22 s,
                # and the Console said nothing until the end (grids of
                # 2026-10-26).
                name = "TikTokDownloader" if platform_id == "douyin" else "KS-Downloader"
                console.add(read_id, f"Reading the title · {name} · {url}", "head")
                answer = tool_probe(platform_id, url)
                _console_read(read_id, answer)
                self._json(answer)
                return
            console.add(read_id, f"Reading the title · yt-dlp · {url}", "head")
            try:
                # A private post has no readable title without the cookies,
                # and the window would show "(no title)" with no reason why.
                # A copy of the cookie file, like every run: yt-dlp writes
                # its jar back when it exits (cookies.for_one_run).
                with cookies.for_one_run(cookies.path_for(
                        "yt-dlp", load_settings()["cookies_enabled"])) as run_cookies:
                    info = ytdlp.probe(url, cookie_file=run_cookies)
            except ytdlp.ToolMissing as exc:
                console.add(read_id, f"Could not read the title: {exc}", "err")
                self._json({"error": str(exc), "kind": "tool_missing"})
                return
            except Exception as exc:
                said = cookies.redact(str(exc))
                console.add(read_id, f"Could not read the title: {said}", "err")
                self._json({"error": said, "kind": "probe_failed",
                            "explain": explain.explain(said, "yt-dlp"),
                            "from_tool": explain.said_by_tool(exc)})
                return
            console.add(read_id, f"Title: {info.title}" if info.title else "No title in the answer.", "end")
            self._json({
                "title": info.title, "uploader": info.uploader,
                "duration": info.duration, "thumbnail": info.thumbnail,
                "extractor": info.extractor, "is_playlist": info.is_playlist,
                "entries": info.entries, "max_height": info.max_height,
                "heights": list(info.heights),
                "items": [{"url": u, "title": t, "duration": d} for u, t, d in info.items],
                "subtitles": [{"code": c, "name": n, "auto": a} for c, n, a in info.subtitles],
                "language": info.language,
            })
            return

        if path == "/api/tools/install":
            tool_id = (body.get("id") or "").strip()
            if tools.spec(tool_id) is None:
                self._json({"error": "unknown tool"}, 400)
                return
            self._json(start_install(tool_id))
            return

        if path == "/api/tools/remove":
            tool_id = (body.get("id") or "").strip()
            removed = tools.remove(tool_id)
            with _installs_lock:
                _installs.pop(tool_id, None)
            self._json({"removed": removed, "tool": tools.status(tool_id)})
            return

        if path == "/api/tools/check":
            # After a failed download: is there a fix? GitHub is asked at
            # once if the last answer is over an hour old (decision 18).
            tool_id = (body.get("id") or "").strip()
            if tools.spec(tool_id) is None:
                self._json({"error": "unknown tool"}, 400)
                return
            tools.latest_release(tool_id, max_age_hours=1)
            self._json({"tool": tools.status(tool_id)})
            return

        if path == "/api/tools/refresh":
            for tool in tools.SPECS:
                tools.latest_release(tool.id, force=True)
            self._json({"tools": tools.status_all(), "python": tools.python_state()})
            return

        if path == "/api/python/install":
            # winget shows its own window; this can take minutes.
            self._json(tools.install_python_with_winget())
            return

        if path == "/api/save-as":
            # The "Save as" window. It runs when the job is ADDED, never when
            # it starts, so a queue left alone never blocks on a dialog.
            mode = body.get("mode") or "mp4"
            try:
                chosen = dialogs.save_file(body.get("suggested") or "", mode, download_folder(),
                                           taken=QUEUE.targets_in_use())
            except dialogs.DialogError as problem:
                # Not a cancel. Until 2026-09-22 these looked identical.
                self._json({"error": str(problem)}, 500)
                return
            self._json({"cancelled": True} if chosen is None else {"path": str(chosen)})
            return

        if path == "/api/download":
            # "Read the link again" on a failed row (the user, 2026-10-26):
            # the card's Download takes that row's place, like Retry -- only
            # while the row is still there and still failed; else a new row.
            replace = (body.get("replace") or "").strip()
            old = QUEUE.get(replace) if replace else None
            answer, status = queue_download(
                replace=replace if old is not None and old.state == ERROR else "",
                url=(body.get("url") or "").strip(),
                mode=body.get("mode") or "mp4",
                quality=str(body.get("quality") or "best"),
                title=body.get("title") or "",
                target=(body.get("target") or "").strip(),
                tool=(body.get("tool") or "yt-dlp").strip(),
                platform=(body.get("platform") or "").strip(),
                folder=(body.get("folder") or "").strip(),
                subs=str(body.get("subs") or ""),
                sub_lang=str(body.get("sub_lang") or ""),
                # A playlist's titles as the card read them: each video is
                # listed on its row from the start (2026-10-31). Text only.
                items=[str(t) for t in body["items"]]
                      if isinstance(body.get("items"), list) else None,
            )
            self._json(answer, status)
            return

        if path == "/api/clipboard":
            # Only links come back (clipboard_links). "asked" = the Paste
            # button: it works even with the switch off; the window coming to
            # the front only when the user left the switch on.
            if not body.get("asked") and not load_settings()["use_clipboard"]:
                self._json({"links": []})
                return
            try:
                self._json({"links": clipboard_links()})
            except OSError as problem:
                self._json({"links": [], "error": f"The clipboard could not be read: {problem}."})
            return

        if path == "/api/console/clear":
            console.clear()
            self._json({"ok": True})
            return

        if path == "/api/console/note":
            # What the page itself said at the bottom of the window, so it
            # stays readable after it fades (the user, 2026-10-26). Washed by
            # console.add like every line; one line, 500 characters at most.
            text = " ".join(str(body.get("text") or "").split())[:500]
            if text:
                console.add("app", f"Teleloadzai: {text}", "note")
            self._json({"ok": True})
            return

        if path == "/api/console/save":
            # "Save as file": the Windows window, then the lines the SERVER
            # kept (already washed) -- never text the page sends.
            try:
                chosen = dialogs.save_file("Teleloadzai console", "txt", download_folder())
            except dialogs.DialogError as problem:
                self._json({"error": str(problem)}, 500)
                return
            if chosen is None:
                self._json({"cancelled": True})
                return
            lines, _ = console.since(0)
            text = "\n".join(time.strftime("%H:%M:%S", time.localtime(l["at"])) + "  " + l["text"]
                             for l in lines)
            try:
                chosen.write_text(text + "\n", encoding="utf-8")
            except OSError as problem:
                self._json({"error": f"Windows could not write the file: {problem}"}, 500)
                return
            self._json({"path": str(chosen), "lines": len(lines)})
            return

        if path == "/api/pick-folder":
            # One folder for several links: the Windows window, and the answer
            # -- the Settings folder is NOT changed (Browse… does that).
            try:
                chosen = dialogs.pick_folder(download_folder())
            except dialogs.DialogError as problem:
                self._json({"error": str(problem)}, 500)
                return
            self._json({"cancelled": True} if chosen is None else {"folder": str(chosen)})
            return

        if path.startswith("/api/job/") and path.endswith("/switch"):
            # "Try with <another tool>" on a failed job (decision 15). It goes
            # through queue_download like a new download, because the cookie
            # road depends on the tool: yt-dlp takes a FILE, TikTokDownloader
            # a header. Copying the old job's cookie fields would hand the new
            # tool the wrong kind.
            old = QUEUE.get(path[len("/api/job/"):-len("/switch")])
            if old is None:
                self._json({"error": "that download no longer exists"}, 404)
                return
            answer, status = queue_download(
                url=old.url, mode=old.mode, quality=old.quality, title=old.title,
                target=_retry_target(old), tool=(body.get("tool") or "").strip(),
                platform=old.platform, replace=old.id, folder=_retry_folder(old),
                subs=old.subs, sub_lang=old.sub_lang,
            )
            self._json(answer, status)
            return

        if path.startswith("/api/job/") and path.endswith("/cancel"):
            job_id = path[len("/api/job/"):-len("/cancel")]
            self._json({"cancelled": QUEUE.cancel(job_id)})
            return

        if path.startswith("/api/job/") and path.endswith("/remove"):
            job_id = path[len("/api/job/"):-len("/remove")]
            self._json({"removed": QUEUE.remove(job_id)})
            return

        if path.startswith("/api/job/") and path.endswith(("/open", "/reveal")):
            # Only a file this job itself saved -- never a path the page
            # sends, or any web page could make us open anything.
            job_id, _, action = path[len("/api/job/"):].rpartition("/")
            job = QUEUE.get(job_id)
            saved = [Path(f) for f in (job.files if job else []) if Path(f).is_file()]
            # A failed row with no file shows its unfinished pieces -- only
            # in the folder, never opened (they are half a video).
            if not saved and job and action == "reveal" and job.state == ERROR:
                saved = [Path(p) for p in job.pieces if Path(p).is_file()]
            if not saved:
                self._json({"error": "The file is no longer where it was saved: "
                                     "it may have been moved or deleted."}, 404)
                return
            try:
                if action == "open":
                    os.startfile(saved[0])          # the program Windows uses for it
                else:
                    # One string, the path in its own quotes: as a list item
                    # the whole "/select,C:\Users\WINDOWS 10\..." got quoted,
                    # and Explorer opened Documents instead (seen 2026-09-26).
                    # A Windows path cannot contain a quote.
                    subprocess.Popen(f'explorer /select,"{saved[0]}"')
            except OSError as problem:
                self._json({"error": f"Windows could not open it: {problem}"}, 500)
                return
            self._json({"ok": True})
            return

        if path.startswith("/api/job/") and path.endswith("/retry"):
            # Retry and "Download again" take the failed row's place instead
            # of stacking a new row under it (asked 2026-09-23).
            old = QUEUE.get(path[len("/api/job/"):-len("/retry")])
            if old is None:
                self._json({"error": "that download no longer exists"}, 404)
                return
            answer, status = queue_download(
                url=old.url, mode=old.mode, quality=old.quality, title=old.title,
                target=_retry_target(old, replace_own=bool(body.get("force"))),
                tool=old.tool, platform=old.platform,
                force=bool(body.get("force")), replace=old.id, folder=_retry_folder(old),
                subs=old.subs, sub_lang=old.sub_lang,
            )
            self._json(answer, status)
            return

        if path == "/api/jobs/clear":
            self._json({"removed": QUEUE.clear_finished()})
            return

        if path == "/api/jobs/clear-all":
            self._json({"removed": QUEUE.clear_all()})
            return

        if path == "/api/cookies/import":
            # The user points at the cookies.txt his browser extension wrote.
            try:
                chosen = dialogs.open_file("Choose your cookies.txt", download_folder())
            except dialogs.DialogError as problem:
                self._json({"error": str(problem)}, 500)
                return
            if chosen is None:
                self._json({"cancelled": True})
                return
            try:
                # Only the sites we download from are kept. "Keep every site"
                # was removed on 2026-10-23 (the user's decision): it saved a
                # whole browser export, bank and mail included, and the
                # start-up clean-up deleted what it kept anyway.
                summary = cookies.import_file(chosen)
            except cookies.CookieFileError as problem:
                # A refusal the user can act on, never a bare "failed".
                self._json({"error": cookies.redact(str(problem))}, 400)
                return
            settings = load_settings()
            settings["cookies_enabled"] = True      # importing IS the consent
            save_settings(settings)
            self._json({"imported": summary["total"],
                        "ignored": summary["ignored"],
                        "ignored_sites": summary["ignored_sites"],
                        "cookies": cookies.state(True)})
            return

        if path == "/api/cookies/clear":
            removed = cookies.clear()
            login.forget_history()
            # The log-in window's folder is tidied too. It holds no log-in --
            # the window runs in private mode (found 2026-09-26) -- so this is
            # housekeeping, and the page no longer claims otherwise.
            wiped = login.forget_browser()       # "", "now" or "later"
            settings = load_settings()
            settings["cookies_enabled"] = False
            save_settings(settings)
            self._json({"removed": removed, "browser_wiped": wiped,
                        "cookies": cookies.state(False)})
            return

        if path == "/api/login/open":
            try:
                self._json(login.open_for((body.get("platform") or "").strip()))
            except login.LoginError as problem:
                self._json({"error": str(problem)}, 400)
            return

        if path == "/api/login/finish":
            try:
                kept = login.finish()
            except login.LoginError as problem:
                self._json({"error": str(problem)}, 400)
                return
            except Exception as problem:
                # Never a silent failure here: the user has just typed a
                # password somewhere and is waiting to be told it worked.
                self._json({"error": cookies.redact(
                    f"The log-in window could not be read: {problem}")}, 500)
                return
            settings = load_settings()
            if kept:
                settings["cookies_enabled"] = True
                save_settings(settings)
            self._json({"kept": kept, "cookies": cookies.state(bool(kept))})
            return

        if path == "/api/login/state":
            # Polled by the page while a log-in window is open, so it can say
            # how it ended -- finished by itself, or closed by the user.
            self._json(login.state())
            return

        if path == "/api/login/cancel":
            self._json({"closed": login.close()})
            return

        if path == "/api/browse":
            try:
                chosen = dialogs.pick_folder(download_folder())
            except dialogs.DialogError as problem:
                self._json({"error": str(problem)}, 500)
                return
            if chosen is None:
                self._json({"cancelled": True})
                return
            settings = load_settings()
            settings["download_folder"] = str(chosen)
            save_settings(settings)
            self._json(settings)
            return

        if path == "/api/settings":
            settings = load_settings()
            folder = (body.get("download_folder") or "").strip()
            if folder:
                settings["download_folder"] = folder
            if body.get("max_parallel"):
                settings["max_parallel"] = body["max_parallel"]
            if "ask_where" in body:          # False is a real value, not "missing"
                settings["ask_where"] = bool(body["ask_where"])
            if "setup_done" in body:
                settings["setup_done"] = bool(body["setup_done"])
            if "record_minutes" in body:
                settings["record_minutes"] = body["record_minutes"]
            if body.get("update_mode") in ("ask", "auto", "manual"):
                settings["update_mode"] = body["update_mode"]
            if body.get("ytdlp_channel") in ("stable", "preview"):
                settings["ytdlp_channel"] = body["ytdlp_channel"]
                tools.set_preview("yt-dlp", body["ytdlp_channel"] == "preview")
            if body.get("cookies_keep") in ("keep", "once"):
                settings["cookies_keep"] = body["cookies_keep"]
            if "use_clipboard" in body:      # False is a real value, not "missing"
                settings["use_clipboard"] = bool(body["use_clipboard"])
            if "auto_read" in body:
                settings["auto_read"] = bool(body["auto_read"])
            if body.get("several_mode") in ("same", "each"):
                settings["several_mode"] = body["several_mode"]
            if body.get("subs_mode") in ("", "embed", "file"):
                settings["subs_mode"] = body["subs_mode"]
            if "notify_done" in body:        # False is a real value, not "missing"
                settings["notify_done"] = bool(body["notify_done"])
            if isinstance(body.get("tool_choice"), dict):
                # One site at a time from the page. Only a tool that site
                # really lists; choosing the default removes the entry, so
                # a later change of our default still reaches this user.
                for pid, tid in body["tool_choice"].items():
                    platform = next((p for p in PLATFORMS if p.id == pid), None)
                    if platform is None or tid not in [o.tool_id for o in platform.tools]:
                        continue
                    usable_default = next((o.tool_id for o in platform.tools
                                           if runners.unavailable_reason(o.tool_id) is None), None)
                    if tid == usable_default:
                        settings["tool_choice"].pop(pid, None)
                    else:
                        settings["tool_choice"][pid] = tid
            if "cookies_enabled" in body:
                # The switch can only be turned ON when a file is really here,
                # otherwise the card would claim cookies we do not have.
                settings["cookies_enabled"] = bool(body["cookies_enabled"]) and cookies.have_file()
            save_settings(settings)
            self._json(load_settings())
            return

        self._json({"error": "not found"}, 404)


class _OwnPort(ThreadingHTTPServer):
    """A server whose port is ours alone.

    Python's server asks for "reuse address", and on Windows that lets a
    SECOND program take a port already in use: a second Teleloadzai started
    without an error, and netstat showed two listeners on 8777 (seen
    2026-09-27). Windows' own option refuses it.
    """
    allow_reuse_address = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def claim(port: int = 8777) -> ThreadingHTTPServer:
    """Take the port, or raise OSError when something else holds it.

    Done FIRST, before anything touches the data folder: a second copy used
    to run "forget the log-ins" at start, under the first copy's feet.
    """
    ensure_dirs()
    return _OwnPort(("127.0.0.1", port), Handler)


def holder_is_us(port: int) -> bool:
    """Is the program on this port another Teleloadzai? Asked, not guessed."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as answer:
            return f"<title>{APP_NAME}".encode() in answer.read(4096)
    except Exception:
        return False


def start_background(port: int = 8777,
                     httpd: ThreadingHTTPServer | None = None) -> tuple[ThreadingHTTPServer, str]:
    """Start the server in a thread and return it with its address.

    The native window (see ``__main__``) needs the server running while it
    keeps the main thread for itself, so starting must not block.
    """
    httpd = httpd or claim(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def serve(port: int = 8777, open_browser: bool = True,
          httpd: ThreadingHTTPServer | None = None) -> None:
    """Run in a browser tab instead of the native window."""
    httpd, url = start_background(port, httpd)
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"  open: {url}")
    print("  stop: Ctrl+C")
    if open_browser:
        import webbrowser

        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.shutdown()
        httpd.server_close()
