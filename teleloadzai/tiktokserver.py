"""Drive TikTokDownloader, which has no command line.

Every other tool takes flags and prints progress. This one is a menu you talk
to, and its only machine-readable door is a local HTTP server. Verified
2026-09-21 and again 2026-09-22: `--help` opens a language menu, so there is
nothing to pass on a command line at all.

**What the server really is.** Menu option 7, "Web API Mode", starts a FastAPI
application on port 5555 with 19 endpoints, read from its own
`/openapi.json` rather than from documentation. The two we use return **data,
not files**:

    POST /douyin/detail  {"detail_id": "...", "cookie": "..."}
    -> {"message": "Successfully retrieved data!",
        "data": {"desc": ..., "duration": "00:01:05",
                 "downloads": "https://www.douyin.com/aweme/v1/play/?..."}}

So this module fetches the address of the file. Downloading it stays ours,
which is better anyway: a direct link has a length, and a length is a real
percentage instead of a bar that never moves (decision 33).

**Two dangers, and both shape the code.**

1. 🚨 **Their server listens on `0.0.0.0`, not on localhost, and asks for no
   token.** Measured 2026-09-22: called from this PC's own LAN address it
   answered HTTP 200, and `/token` replies "Verification successful!" with no
   token supplied. On a shared Wi-Fi anyone can reach it -- and it carries the
   user's cookie while it runs. Decision 21 forbids exactly this for our own
   server, so we do not leave theirs open: it is started when a job needs it
   and stopped the moment the last one finishes.
2. 🚨 **The menu is not a fixed sequence.** The language choice and the
   disclaimer are saved after the first run, so the keystrokes that work once
   are wrong the next time -- and a wrong keystroke here is not harmless:
   "2" is *Extracting cookie from clipboard*, which rewrites their settings.
   So we do not send a fixed script. We **read what it asks** and answer that
   question, which works on the first run and on the hundredth.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import tools

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HOST = "127.0.0.1"
PORT = 5555
BASE = f"http://{HOST}:{PORT}"

# What it asks, and what we answer. Matched on everything printed so far, so a
# prompt that arrives without a newline still counts.
_PROMPTS: tuple[tuple[str, str], ...] = (
    ("please select language", "2"),        # 2 = English
    ("(yes/no)", "YES"),                    # the disclaimer, asked once ever
    ("feature options", "7"),               # 7 = Web API Mode
)

_READY = "uvicorn running"
_START_TIMEOUT = 120.0                      # it unpacks itself on a cold start


class TikTokServerError(RuntimeError):
    """The server could not be started or answered badly, with the reason."""


class _Server:
    """The running program, started on demand and stopped when nobody needs it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._users = 0                     # how many jobs are using it now

    # -- starting and stopping ---------------------------------------------

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _answer_prompts(self, process: subprocess.Popen) -> None:
        """Read what the menu asks and answer it, until the server is up.

        A fixed script breaks the moment the program remembers the language,
        and the wrong key runs the wrong menu entry. Reading is the only way
        that is right on every run.
        """
        seen = ""
        answered: set[str] = set()
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(1)
            if not chunk:
                return
            seen += chunk
            low = seen.lower()
            if _READY in low:
                return
            for needle, reply in _PROMPTS:
                if needle in low and needle not in answered:
                    answered.add(needle)
                    try:
                        assert process.stdin is not None
                        process.stdin.write(reply + "\n")
                        process.stdin.flush()
                    except OSError as problem:
                        raise TikTokServerError(
                            f"TikTokDownloader stopped listening while starting: {problem}"
                        ) from problem
                    seen = ""               # do not answer the same prompt twice
                    break
            if len(seen) > 8000:            # never grow without bound
                seen = seen[-2000:]

    def _wait_for_port(self, deadline: float) -> None:
        while time.time() < deadline:
            if not self._alive():
                raise TikTokServerError(
                    "TikTokDownloader closed itself while starting. Open it once "
                    "by hand to accept its disclaimer, then try again."
                )
            with socket.socket() as probe:
                probe.settimeout(1.0)
                if probe.connect_ex((HOST, PORT)) == 0:
                    return
            time.sleep(0.4)
        raise TikTokServerError(
            f"TikTokDownloader did not open port {PORT} within "
            f"{int(_START_TIMEOUT)} seconds."
        )

    def start(self) -> None:
        """Make sure the server is running, and count one more user."""
        with self._lock:
            if self._alive():
                self._users += 1
                return

            exe = tools.installed_path("tiktokdownloader")
            if exe is None:
                raise TikTokServerError("TikTokDownloader is not installed")

            # Something else may already hold 5555 -- the user's own copy, or
            # ours left behind by a crash. Saying so beats a silent failure.
            with socket.socket() as probe:
                probe.settimeout(1.0)
                if probe.connect_ex((HOST, PORT)) == 0:
                    raise TikTokServerError(
                        f"Port {PORT} is already in use. TikTokDownloader may "
                        "already be open — close it and try again."
                    )

            self._process = subprocess.Popen(
                [str(exe)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                cwd=str(exe.parent),        # its Volume/ folder lives beside it
                creationflags=_NO_WINDOW,
            )
            reader = threading.Thread(
                target=self._answer_prompts, args=(self._process,), daemon=True)
            reader.start()
            try:
                self._wait_for_port(time.time() + _START_TIMEOUT)
            except Exception:
                self._kill()
                raise
            self._users = 1

    def _kill(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def release(self) -> None:
        """One job is finished. Stop the server when the last one leaves.

        This is the answer to their `0.0.0.0` binding: the door exists only
        while somebody is walking through it.
        """
        with self._lock:
            self._users = max(0, self._users - 1)
            if self._users == 0:
                self._kill()

    def stop_now(self) -> bool:
        """Shut it down whatever the count. Used when the app closes."""
        with self._lock:
            running = self._alive()
            self._users = 0
            self._kill()
            return running

    def running(self) -> bool:
        with self._lock:
            return self._alive()


SERVER = _Server()


# --------------------------------------------------------------------------
# talking to it
# --------------------------------------------------------------------------

def _post(path: str, body: dict, timeout: float = 90.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except urllib.error.URLError as problem:
        raise TikTokServerError(
            f"TikTokDownloader did not answer: {problem.reason}") from problem
    except json.JSONDecodeError as problem:
        raise TikTokServerError(
            "TikTokDownloader answered something that is not JSON") from problem


_ID_IN_URL = re.compile(r"/video/(\d{6,})")


def video_id(url: str, douyin: bool) -> str:
    """The numeric id inside a link, resolving a short link if needed.

    Their own `/share` endpoint follows short links (`v.douyin.com`,
    `vt.tiktok.com`) and needs no cookie -- checked 2026-09-22.
    """
    found = _ID_IN_URL.search(url)
    if found:
        return found.group(1)

    answer = _post(f"/{'douyin' if douyin else 'tiktok'}/share", {"text": url})
    full = answer.get("url") or ""
    found = _ID_IN_URL.search(full)
    if not found:
        raise TikTokServerError(
            "No video could be found in that link. Copy the address of the "
            "video itself, not of a profile or a search.")
    return found.group(1)


def detail(url: str, douyin: bool, cookie: str) -> dict:
    """Ask for one work, and return what it says about it.

    The cookie travels in the request body to 127.0.0.1, never on a command
    line: on Windows any process can read another's command line, and that is
    what kept this tool out of reach until now (hard rule 1).
    """
    site = "douyin" if douyin else "tiktok"
    answer = _post(f"/{site}/detail",
                   {"detail_id": video_id(url, douyin), "cookie": cookie or ""})
    data = answer.get("data")
    if not isinstance(data, dict):
        raise TikTokServerError(
            (answer.get("message") or "TikTokDownloader could not read that video")
            + _hint(site, bool(cookie)))
    return data


def _hint(site: str, had_cookie: bool) -> str:
    """Why it probably failed, in words the user can act on (decision 34)."""
    if not had_cookie:
        return (f". {site.capitalize()} needs cookies for this — turn on log-in "
                "cookies in Settings and log in to that site.")
    return (". The cookies may have expired, or the site is refusing this "
            "network. Log in again, then try once more.")
