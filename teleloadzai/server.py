"""The window of Teleloadzai: a tiny local web server.

Two safety rules, because a web page is easy to reach by accident:

* the server listens on 127.0.0.1 only, never on the network;
* every ``/api/`` call must carry the secret token created at startup, so
  another site open in the same browser cannot drive Teleloadzai.
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import cookies, dialogs, explain, login, runners, toolservers, tools, ytdlp
from .config import APP_NAME, APP_VERSION
from .detect import Detection, detect
from .jobs import Queue
from .paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR, WEB_DIR, ensure_dirs
from .platforms import PLATFORMS, tool_name

SETTINGS_FILE = DATA_DIR / "settings.json"
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
    }


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
    """The sites where there is a real choice: more than one usable tool."""
    rows = []
    for platform in PLATFORMS:
        offered = usable_tools(platform)
        if len(offered) < 2:
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
    ensure_dirs()
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


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


def queue_download(url: str, mode: str, quality: str, title: str, target: str,
                   tool: str, platform: str, force: bool = False,
                   replace: str = "") -> tuple[dict, int]:
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
    # Cookies, when the user has them on AND this tool can take them. `note`
    # is the sentence for the case where it cannot -- it travels with the job
    # so the row can say it instead of failing in silence.
    on = load_settings()["cookies_enabled"]
    job = QUEUE.add(url, mode, quality, title or url, download_folder(),
                    Path(target) if target else None, force=force, tool=tool,
                    limit_minutes=record_minutes(),
                    cookie_file=cookies.path_for(tool, on),
                    cookie_note=cookies.unusable_reason(tool, on) or "",
                    platform=platform,
                    cookie_header=on and tool in cookies.HEADER_CAPABLE,
                    replace=replace)
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


QUEUE = Queue(max_parallel)


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

    def work() -> None:
        try:
            tools.install(tool_id, lambda stage, pct: _set_install(
                tool_id, stage=stage, percent=pct))
            _set_install(tool_id, state="done", stage="done", percent=100)
        except tools.InstallError as exc:
            # "python_missing" is not a failure, it is a question for the user.
            _set_install(tool_id, state="error", error=str(exc))
        except Exception as exc:
            _set_install(tool_id, state="error", error=f"{type(exc).__name__}: {exc}")

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
                    if any(o.tool_id == "yt-dlp" for o in offered)
                    else {"id": offered[0].tool_id, "name": tool_name(offered[0].tool_id)}
                    if offered and platform.id in _READ_BY_TOOL else None),
        "final_url": result.final_url,
        "was_shortened": result.was_shortened,
        "redirect_error": result.redirect_error,
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
                })
                return

            if path == "/api/tool-choices":
                self._json({"sites": tool_choices()})
                return

            if path == "/api/qualities":
                self._json({
                    "mp3": list(ytdlp.AUDIO_QUALITIES),
                    "mp4": list(ytdlp.VIDEO_QUALITIES),
                })
                return

            if path == "/api/jobs":
                jobs = QUEUE.all()
                for job in jobs:
                    job["other_tool"] = other_tool(job)
                self._json({"jobs": jobs})
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
        path = urlsplit(self.path).path
        if not path.startswith("/api/") or not self._authorised():
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
            if platform_id in _READ_BY_TOOL:
                self._json(tool_probe(platform_id, url))
                return
            try:
                # A private post has no readable title without the cookies,
                # and the window would show "(no title)" with no reason why.
                info = ytdlp.probe(
                    url,
                    cookie_file=cookies.path_for("yt-dlp", load_settings()["cookies_enabled"]),
                )
            except ytdlp.ToolMissing as exc:
                self._json({"error": str(exc), "kind": "tool_missing"})
                return
            except Exception as exc:
                said = cookies.redact(str(exc))
                self._json({"error": said, "kind": "probe_failed",
                            "explain": explain.explain(said, "yt-dlp"),
                            "from_tool": explain.said_by_tool(exc)})
                return
            self._json({
                "title": info.title, "uploader": info.uploader,
                "duration": info.duration, "thumbnail": info.thumbnail,
                "extractor": info.extractor, "is_playlist": info.is_playlist,
                "entries": info.entries,
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
                chosen = dialogs.save_file(body.get("suggested") or "", mode, download_folder())
            except dialogs.DialogError as problem:
                # Not a cancel. Until 2026-09-22 these looked identical.
                self._json({"error": str(problem)}, 500)
                return
            self._json({"cancelled": True} if chosen is None else {"path": str(chosen)})
            return

        if path == "/api/download":
            answer, status = queue_download(
                url=(body.get("url") or "").strip(),
                mode=body.get("mode") or "mp4",
                quality=str(body.get("quality") or "best"),
                title=body.get("title") or "",
                target=(body.get("target") or "").strip(),
                tool=(body.get("tool") or "yt-dlp").strip(),
                platform=(body.get("platform") or "").strip(),
            )
            self._json(answer, status)
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
                target=old.target, tool=(body.get("tool") or "").strip(),
                platform=old.platform, replace=old.id,
            )
            self._json(answer, status)
            return

        if path.startswith("/api/job/") and path.endswith("/cancel"):
            job_id = path[len("/api/job/"):-len("/cancel")]
            self._json({"cancelled": QUEUE.cancel(job_id)})
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
                target=old.target, tool=old.tool, platform=old.platform,
                force=bool(body.get("force")), replace=old.id,
            )
            self._json(answer, status)
            return

        if path == "/api/jobs/clear":
            self._json({"removed": QUEUE.clear_finished()})
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
                # keep_all is the way out for a site our table does not list.
                # yt-dlp handles far more sites than we name, and refusing
                # those would be the dead end decision 15 forbids.
                summary = cookies.import_file(chosen, keep_all=bool(body.get("keep_all")))
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
            if body.get("cookies_keep") in ("keep", "once"):
                settings["cookies_keep"] = body["cookies_keep"]
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


def start_background(port: int = 8777) -> tuple[ThreadingHTTPServer, str]:
    """Start the server in a thread and return it with its address.

    The native window (see ``__main__``) needs the server running while it
    keeps the main thread for itself, so starting must not block.
    """
    ensure_dirs()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/"


def serve(port: int = 8777, open_browser: bool = True) -> None:
    """Run in a browser tab instead of the native window."""
    httpd, url = start_background(port)
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
