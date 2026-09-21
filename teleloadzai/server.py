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

from . import dialogs, tools, ytdlp
from .config import APP_NAME, APP_VERSION
from .detect import Detection, detect
from .jobs import Queue
from .paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR, WEB_DIR, ensure_dirs
from .platforms import tool_name

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
    }


def save_settings(settings: dict) -> None:
    ensure_dirs()
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def download_folder() -> Path:
    return Path(load_settings()["download_folder"])


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


# --------------------------------------------------------------------------
# JSON shapes
# --------------------------------------------------------------------------

def detection_json(result: Detection) -> dict:
    platform = result.platform
    return {
        "platform": platform.name,
        "platform_id": platform.id,
        "supported": platform.is_supported,
        "note": platform.note,
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
            }
            for option in platform.tools
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

            if path == "/api/qualities":
                self._json({
                    "mp3": list(ytdlp.AUDIO_QUALITIES),
                    "mp4": list(ytdlp.VIDEO_QUALITIES),
                })
                return

            if path == "/api/jobs":
                self._json({"jobs": QUEUE.all()})
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
            try:
                info = ytdlp.probe(url)
            except ytdlp.ToolMissing as exc:
                self._json({"error": str(exc), "kind": "tool_missing"})
                return
            except Exception as exc:
                self._json({"error": str(exc), "kind": "probe_failed"})
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
            chosen = dialogs.save_file(body.get("suggested") or "", mode, download_folder())
            self._json({"cancelled": True} if chosen is None else {"path": str(chosen)})
            return

        if path == "/api/download":
            url = (body.get("url") or "").strip()
            mode = body.get("mode") or "mp4"
            quality = str(body.get("quality") or "best")
            title = body.get("title") or url
            target = (body.get("target") or "").strip()
            allowed = ytdlp.AUDIO_QUALITIES if mode == "mp3" else ytdlp.VIDEO_QUALITIES
            if mode not in ("mp3", "mp4") or quality not in allowed:
                self._json({"error": "bad mode or quality"}, 400)
                return
            job = QUEUE.add(url, mode, quality, title, download_folder(),
                            Path(target) if target else None)
            self._json(job.as_dict())
            return

        if path.startswith("/api/job/") and path.endswith("/cancel"):
            job_id = path[len("/api/job/"):-len("/cancel")]
            self._json({"cancelled": QUEUE.cancel(job_id)})
            return

        if path.startswith("/api/job/") and path.endswith("/retry"):
            job_id = path[len("/api/job/"):-len("/retry")]
            again = QUEUE.retry(job_id, force=bool(body.get("force")))
            self._json(again.as_dict() if again else {"error": "cannot retry"},
                       200 if again else 400)
            return

        if path == "/api/jobs/clear":
            self._json({"removed": QUEUE.clear_finished()})
            return

        if path == "/api/browse":
            chosen = dialogs.pick_folder(download_folder())
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
