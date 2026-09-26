"""Drive the tools whose only door is a local server: TikTokDownloader, and
KS-Downloader (Kuaishou, same author) since 2026-09-23.

`_Server` is the machine both share -- start per job, stop after, name who
holds the port, keep the tool's last words. Only what differs (port, how to
start it, what it asks) is per tool. The file was `tiktokserver.py` until
2026-09-23: one copy of the machine instead of two, so a fix cannot land in
one and be forgotten in the other.

**KS-Downloader**, read from the program itself 2026-09-23: `main.exe api`
starts the server straight away on port 5557, with no menu to answer; its
`/openapi.json` lists `/share` and `/detail/`, and `/detail/` takes
``{"text": url}`` and returns the post with a direct `download` link. It also
binds `0.0.0.0` -- the same danger as below, the same answer.

Every other tool takes flags and prints progress. TikTokDownloader is a menu
you talk to, and its only machine-readable door is a local HTTP server.
Verified 2026-09-21 and again 2026-09-22: `--help` opens a language menu, so
there is nothing to pass on a command line at all.

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

from . import explain, tools

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HOST = "127.0.0.1"

# What TikTokDownloader asks, and what we answer. Matched on everything
# printed so far, so a prompt that arrives without a newline still counts.
_PROMPTS: tuple[tuple[str, str], ...] = (
    ("please select language", "2"),        # 2 = English
    ("(yes/no)", "YES"),                    # the disclaimer, asked once ever
    ("feature options", "7"),               # 7 = Web API Mode
)

_READY = "uvicorn running"
_START_TIMEOUT = 120.0                      # it unpacks itself on a cold start
# curl's own error, printed by TikTokDownloader when a connection fails while
# it starts -- and then it waits forever. Seen with a dead proxy 2026-09-23
# and 2026-09-26 (the line at 4.2 s, the wait ended by our limit at 122 s);
# never printed on a normal start. The port gets a few more seconds after it,
# in case a start ever goes on past such a line.
_STUCK = "curl: ("
_STUCK_GRACE = 10.0


class ToolServerError(RuntimeError):
    """The server could not be started or answered badly, with the reason."""


class _Server:
    """The running program, started on demand and stopped when nobody needs it."""

    def __init__(self, tool_id: str, name: str, port: int,
                 args: tuple[str, ...] = (),
                 prompts: tuple[tuple[str, str], ...] = ()) -> None:
        self.tool_id = tool_id
        self.name = name
        self.port = port                    # fixed in the tool's own code
        self.base = f"http://{HOST}:{port}"
        self._args = args
        self._prompts = prompts
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._users = 0                     # how many jobs are using it now
        # The last lines it printed while starting. When it cannot start, the
        # reason is in there -- with the proxy cut it printed "curl: (7) Failed
        # to connect ... over proxy" and waited forever (2026-09-23), and we
        # only said "did not open port 5555 within 120 seconds".
        self._said: list[str] = []

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
            if chunk == "\n":
                last = seen.rstrip().rsplit("\n", 1)[-1].strip()
                if last:
                    self._said.append(last)
                    del self._said[:-30]
            low = seen.lower()
            if _READY in low:
                return
            for needle, reply in self._prompts:
                if needle in low and needle not in answered:
                    answered.add(needle)
                    try:
                        assert process.stdin is not None
                        process.stdin.write(reply + "\n")
                        process.stdin.flush()
                    except OSError as problem:
                        raise ToolServerError(
                            f"{self.name} stopped listening while starting: {problem}"
                        ) from problem
                    seen = ""               # do not answer the same prompt twice
                    break
            if len(seen) > 8000:            # never grow without bound
                seen = seen[-2000:]

    def _wait_for_port(self, deadline: float) -> None:
        stuck_at = None
        while time.time() < deadline:
            if stuck_at is None and any(_STUCK in line for line in list(self._said)):
                stuck_at = time.time()
            if stuck_at is not None and time.time() - stuck_at > _STUCK_GRACE:
                raise ToolServerError(
                    f"{self.name} could not connect while starting, and did not go on."
                    + self._last_words()
                )
            if not self._alive():
                # The disclaimer advice is TikTokDownloader's own case; for
                # another tool we know nothing more than that it stopped.
                advice = (" Open it once by hand to accept its disclaimer, then "
                          "try again." if self._prompts else "")
                raise ToolServerError(
                    f"{self.name} closed itself while starting." + advice
                    + self._last_words()
                )
            with socket.socket() as probe:
                probe.settimeout(1.0)
                if probe.connect_ex((HOST, self.port)) == 0:
                    return
            time.sleep(0.4)
        raise ToolServerError(
            f"{self.name} did not start within {int(_START_TIMEOUT)} seconds."
            + self._last_words()
        )

    def _last_words(self) -> str:
        """Its most useful recent line, washed of secrets -- or nothing."""
        from . import cookies
        for line in reversed(self._said):
            low = line.lower()
            if line.startswith(("File ", "Traceback")):
                continue
            if any(w in low for w in ("error", "failed", "exception", "失败")):
                return " Its last words: " + cookies.redact(line[:220])
        return ""

    def start(self) -> None:
        """Make sure the server is running, and count one more user."""
        with self._lock:
            if self._alive():
                self._users += 1
                return

            exe = tools.installed_path(self.tool_id)
            if exe is None:
                raise ToolServerError(f"{self.name} is not installed")

            # Something else may already hold the port, and the tool cannot
            # move: TikTokDownloader's is a constant in its code
            # (`SERVER_PORT = 5555`, src/custom/static.py, read 2026-09-23).
            # Name the holder -- "the port is busy" alone leaves the user
            # nothing to act on.
            with socket.socket() as probe:
                probe.settimeout(1.0)
                if probe.connect_ex((HOST, self.port)) == 0:
                    holder = port_holder(self.port)
                    raise ToolServerError(
                        f"Port {self.port}, which {self.name} must use, is taken by "
                        + (holder if holder else "another program")
                        + ". Close it and try again, or use another tool."
                    )

            self._said = []
            self._process = subprocess.Popen(
                [str(exe), *self._args],
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


TIKTOK = _Server("tiktokdownloader", "TikTokDownloader", 5555, prompts=_PROMPTS)
KS = _Server("ks-downloader", "KS-Downloader", 5557, args=("api",))
ALL = (TIKTOK, KS)


# Programs we have actually met on this port, with what they are. Only seen
# ones (decision 38): any other holder is named by its file name and nothing
# is guessed about it.
_KNOWN_HOLDERS = {
    # 2026-09-23, on the developer's PC: D:\Program Files\Tencent\Androws\
    # ...\AndrowsBox\ABoxHeadless.exe, child of ABoxSVC.exe. 5555 is the port
    # Android's debug bridge uses, which is why an Android tool sits on it.
    "aboxheadless.exe": "Tencent Androws (it runs Android apps on Windows)",
}


def port_holder(port: int) -> str:
    """The name of the program listening on this port, or "".

    `netstat` and `tasklist` print in the language of Windows -- the state
    column says LISTENING here, but not on every PC -- so a listening line is
    recognised by its shape instead: our port on the local side, and an empty
    remote side (`0.0.0.0:0` or `[::]:0`).
    """
    try:
        table = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
            errors="replace", timeout=15, creationflags=_NO_WINDOW).stdout
    except Exception:
        return ""
    pid = ""
    for line in table.splitlines():
        cols = line.split()
        if (len(cols) >= 5 and cols[1].endswith(f":{port}")
                and cols[2] in ("0.0.0.0:0", "[::]:0")):
            pid = cols[-1]
            break
    if not pid.isdigit():
        return ""
    try:
        row = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=15,
            creationflags=_NO_WINDOW).stdout.strip()
    except Exception:
        return ""
    name = row.split('","')[0].strip('"') if row.startswith('"') else ""
    if not name:
        return ""
    known = _KNOWN_HOLDERS.get(name.lower())
    return f"{name} — {known}" if known else name


# --------------------------------------------------------------------------
# talking to it
# --------------------------------------------------------------------------

def _post(path: str, body: dict, timeout: float = 90.0,
          server: _Server = TIKTOK) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        server.base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except urllib.error.URLError as problem:
        raise ToolServerError(
            f"{server.name} did not answer: {problem.reason}") from problem
    except json.JSONDecodeError as problem:
        raise ToolServerError(
            f"{server.name} answered something that is not JSON") from problem


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
        raise ToolServerError(
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
        # Its own words, nothing added. What they mean is explain.py's job,
        # and only for causes we have seen (decision 38). This used to add
        # "the cookies may have expired, or the site is refusing this
        # network" -- a guess, written as if it were known.
        said = answer.get("message")
        problem = ToolServerError("TikTokDownloader: " + (said or "no answer about this video"))
        raise explain.from_tool(problem) if said else problem
    return data


def ks_detail(url: str, cookie: str = "") -> dict:
    """Ask KS-Downloader for one Kuaishou post.

    Seen 2026-09-23 on a real video, with no cookie at all: "Successfully
    fetched posts data!", `photoType` "Video", `caption`, `name` (the author)
    and `download`, a direct link on kwaicdn.com. It accepts the full link as
    copied, `?authorId=...` included.

    ⚠️ That worked ONCE. Half an hour later the same link failed ("Failed to
    retrieve posts data", 3 of 3), and Kuaishou's own front page answered any
    program with `{"result":2}` -- while it still opened in a real browser. So
    the cookie is passed, like TikTokDownloader's, in the request body to
    127.0.0.1 (hard rule 1). PROVISIONAL until its effect is seen.
    """
    body = {"text": url}
    if cookie:
        body["cookies"] = cookie
    answer = _post("/detail/", body, server=KS)
    data = answer.get("data")
    if not isinstance(data, dict):
        said = answer.get("message")
        problem = ToolServerError("KS-Downloader: " + (said or "no answer about this post"))
        raise explain.from_tool(problem) if said else problem
    return data

