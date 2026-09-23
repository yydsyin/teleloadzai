"""Run the specialist tools: one engine, one recipe per tool.

`ytdlp.py` stays on its own, because yt-dlp lets us choose the shape of its
progress and tell us the exact file it wrote. None of the others do. So this
module works the other way round:

**Watch the folder.** We note what is in the output folder before the tool
runs, and look again afterwards. What appeared or changed is what the tool
downloaded. That works for every tool, whatever it prints, and it answers
the question of decision 24 for free: if nothing changed, nothing was
downloaded, and we must not claim a success.

Two things every tool gets, and both were learned the hard way:

* **UTF-8 forced in its environment.** f2 printed a rocket and crashed,
  because this machine's console speaks GBK (checked 2026-09-21).
* **stdin closed.** A tool that decides to ask a question must fail, not
  wait forever for a human who is not watching.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cookies, explain, tiktokserver, tools
from .paths import BIN_DIR

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Most tools print a percentage somewhere. Those that do not simply show
# "working" -- we do not invent a number we cannot measure.
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Request:
    url: str
    out_dir: Path               # the folder the file must land in
    out_name: str = ""          # wanted base name; some tools ignore it
    mode: str = "mp4"
    quality: str = "best"
    # A live stream has no end. Without a limit the recording stops only when
    # the user presses Stop, or when the disk is full (2026-09-22).
    limit_minutes: int = 60
    # The user has asked again for something the tool believes it already has.
    force: bool = False
    # Teleloadzai's own copy of the cookie file, or None. Only the tools in
    # `cookies.FILE_CAPABLE` ever receive it -- the others take a cookie only
    # as text on a command line, which hard rule 1 forbids.
    cookie_file: Path | None = None
    # True when this job may use cookies at all. TikTokDownloader wants them
    # as a header string, not a file, so it cannot use `cookie_file`.
    cookie_header: bool = False


@dataclass
class RunResult:
    files: list[Path] = field(default_factory=list)
    log_tail: list[str] = field(default_factory=list)

    @property
    def nothing_downloaded(self) -> bool:
        return not self.files


@dataclass(frozen=True)
class Recipe:
    """How to drive one tool."""

    tool_id: str
    build: Callable[[Path, Request], list[str]]
    module: str = ""            # run as `python -m <module>` instead of an exe
    note: str = ""              # shown to the user when it matters
    # Runs after the tool, on the files it produced, and returns the final
    # list. Used to repackage a recording into something that plays anywhere.
    after: Callable[[list[Path]], list[Path]] | None = None
    # Files the tool writes for its own bookkeeping. They are NOT downloads,
    # and counting them means reporting a success that never happened:
    # XHS-Downloader skipped a note it had already seen, wrote only its own
    # database, and that alone looked like a download (2026-09-22).
    ignore: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# the recipes -- every command line below was read from the tool itself
# --------------------------------------------------------------------------

def _gallery_dl(_exe: Path, r: Request) -> list[str]:
    # -D is the exact folder, no category sub-folders.
    command = [r.url, "-D", str(r.out_dir), "--windows-filenames"]
    # `-C FILE` reads the same Netscape file yt-dlp does (read from its own
    # --help, 2026-09-22). This is what opens a private Instagram post.
    if r.cookie_file:
        command += ["--cookies", str(r.cookie_file)]
    return command


# Our quality names are not streamlink's. It calls them 1080p60, 720p, worst,
# and a comma list is tried in order, so the last entry is always a safe net.
_STREAMLINK_QUALITY = {
    "best": "best",
    "1080": "1080p60,1080p,best",
    "720": "720p60,720p,best",
    "480": "480p,best",
    "360": "360p,worst,best",
}


def _streamlink(exe: Path, r: Request) -> list[str]:
    # A recording arrives as .ts; `after` repackages it to .mp4.
    name = (r.out_name or "stream") + ".ts"
    wanted = "audio_only,worst" if r.mode == "mp3" else _STREAMLINK_QUALITY.get(r.quality, "best")

    command = [str(exe), r.url, wanted, "-o", str(r.out_dir / name), "--progress", "force"]
    # streamlink spells it differently from the other two, and it does NOT
    # rewrite the file (both checked 2026-09-22). Subscriber-only streams need
    # it; a public Twitch channel does not.
    if r.cookie_file:
        command += ["--http-cookies-file", str(r.cookie_file)]
    if r.limit_minutes > 0:
        # Without this a live stream records until the disk is full.
        command += ["--stream-segmented-duration", f"{r.limit_minutes}m"]
    return command


def _xhs(exe: Path, r: Request) -> list[str]:
    # It builds its own folder under --work_path, so we give it ours.
    command = [str(exe), "--url", r.url,
               "--work_path", str(r.out_dir.parent),
               "--folder_name", r.out_dir.name]
    # It keeps a history of everything it has ever fetched, beside its own
    # program, and silently refuses a note it has seen before. Only when the
    # user asks for it again do we switch that history off.
    if r.force:
        command += ["--download_record", "false"]
    return command


def _n_m3u8dl_re(exe: Path, r: Request) -> list[str]:
    # --auto-select is not optional: a stream with several qualities makes it
    # stop and ask which one, and with stdin closed it crashes (2026-09-21).
    # --tmp-dir is not optional either: without it the pieces of the video
    # pile up beside the program (28 MB found in bin/ the same day).
    return [str(exe), r.url,
            "--auto-select",
            "--tmp-dir", str(r.out_dir),
            "--save-dir", str(r.out_dir),
            "--save-name", r.out_name or "stream"]


def _f2(_exe: Path, r: Request) -> list[str]:
    """f2 has one sub-command per site, and it needs a cookie for most of them.

    ⚠️ It has **no Kuaishou**. This line used to build `ks`, which was never
    checked against the program. Asked on 2026-09-22:

        $ python -m f2 ks --help
        Error: 没有找到 ks 应用          ("the ks app was not found")

    Its own help lists eleven apps and Kuaishou is not among them, and the
    installed package ships five: bark, douyin, tiktok, twitter, weibo. So
    `wb` is the only one of ours that exists here.
    """
    return ["wb", "-u", r.url, "-p", str(r.out_dir)]


def _repackage_to_mp4(files: list[Path]) -> list[Path]:
    """Turn a .ts recording into a .mp4, without touching the video itself.

    streamlink writes .ts, which plays in VLC but is not what a user expects
    to find in his folder. ffmpeg copies the streams into an mp4 container:
    no re-encoding, nothing lost, a few seconds at most.

    If anything goes wrong the .ts is kept. A playable file with the wrong
    extension beats no file at all.
    """
    ffmpeg = tools.installed_path("ffmpeg")
    if ffmpeg is None:
        return files

    final: list[Path] = []
    for path in files:
        if path.suffix.lower() != ".ts" or not path.is_file():
            final.append(path)
            continue

        target = path.with_suffix(".mp4")
        try:
            done = subprocess.run(
                [str(ffmpeg), "-y", "-i", str(path), "-c", "copy",
                 "-movflags", "+faststart", str(target)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, timeout=1800, creationflags=_NO_WINDOW,
            )
        except Exception:
            final.append(path)
            continue

        if done.returncode == 0 and target.is_file() and target.stat().st_size > 0:
            path.unlink(missing_ok=True)
            final.append(target)
        else:
            target.unlink(missing_ok=True)      # never leave a broken mp4
            final.append(path)
    return final


RECIPES: dict[str, Recipe] = {
    "gallery-dl": Recipe("gallery-dl", _gallery_dl, module="gallery_dl"),
    "streamlink": Recipe("streamlink", _streamlink, after=_repackage_to_mp4),
    "xhs-downloader": Recipe("xhs-downloader", _xhs, ignore=("*.db",)),
    "n-m3u8dl-re": Recipe("n-m3u8dl-re", _n_m3u8dl_re),
    "f2": Recipe("f2", _f2, module="f2",
                 note="f2 needs a cookie in its own config file for most sites."),
}


def _tiktok(request: Request, on_progress: Callable[[int], None] | None) -> RunResult:
    """TikTokDownloader: ask its local server where the file is, then fetch it.

    It has no command line, so there is no recipe to build. Its Web API hands
    back an address, not a file (checked 2026-09-22 against a real Douyin
    work: 32 fields, `downloads` holding a direct link). Fetching it ourselves
    is what gives this tool a real percentage instead of the empty bar that
    decision 33 forbids -- a direct link carries its length.

    The server is started here and released in `finally`, so it is never
    listening longer than one job needs. That is deliberate: it binds
    `0.0.0.0` and asks for no token.
    """
    douyin = "douyin.com" in request.url or "iesdouyin" in request.url
    site = "douyin.com" if douyin else "tiktok.com"

    # One site's cookies only, and only when this job may use cookies at all.
    cookie = cookies.header_for(site, True) if request.cookie_header else ""

    tiktokserver.SERVER.start()
    try:
        data = tiktokserver.detail(request.url, douyin, cookie)
    finally:
        tiktokserver.SERVER.release()

    address = data.get("downloads") or ""
    if request.mode == "mp3":
        address = data.get("music_url") or address
    if not isinstance(address, str) or not address.startswith("http"):
        raise RunnerError(
            "TikTokDownloader found the work but gave no file to download. "
            "It may be a photo post, or a live stream that has ended.")

    name = request.out_name or _clean_name(data)
    suffix = ".mp3" if request.mode == "mp3" and data.get("music_url") else ".mp4"
    target = request.out_dir / (name + suffix)
    _fetch(address, target, site, on_progress, cookie)
    return RunResult([target], [f"TikTokDownloader: {data.get('desc', '')[:80]}"])


def _clean_name(data: dict) -> str:
    """A file name from what the site says, safe for Windows."""
    raw = f"{data.get('nickname', '')} {data.get('desc', '')}".strip() or "video"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)[:120].strip() or "video"


def _fetch(address: str, target: Path, site: str,
           on_progress: Callable[[int], None] | None, cookie: str = "") -> None:
    """Download a direct link, reporting a real percentage.

    What the file servers demand, measured 2026-09-23 on a real TikTok video
    (a 1 KB range request each time):

        User-Agent + Referer             -> 403
        User-Agent + cookies             -> 403
        User-Agent + Referer + cookies   -> 206 video/mp4

    Douyin's server was content with the Referer alone; TikTok's wants both,
    exactly as a browser sends them.

    ⚠️ The cookie is sent ONLY when the file's server belongs to the same site
    (`v16-webapp-prime.tiktok.com` belongs to `tiktok.com`). A link handed to
    us can point anywhere, and a session cookie sent to a stranger's server is
    the account given away (hard rule 1).
    """
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0 Safari/537.36"),
        "Referer": f"https://www.{site}/",
    }
    host = (urllib.parse.urlsplit(address).hostname or "").lower()
    if cookie and (host == site or host.endswith("." + site)):
        headers["Cookie"] = cookie
    request = urllib.request.Request(address, headers=headers)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            total = int(answer.headers.get("Content-Length") or 0)
            done = 0
            with open(partial, "wb") as out:
                while True:
                    block = answer.read(256 * 1024)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if on_progress and total:
                        on_progress(min(100, int(done * 100 / total)))
        if partial.stat().st_size == 0:
            raise RunnerError("The download came back empty.")
        partial.replace(target)
    except urllib.error.URLError as problem:
        partial.unlink(missing_ok=True)     # never leave half a file behind
        raise RunnerError(f"The video could not be downloaded: {problem.reason}") from problem
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def can_run(tool_id: str) -> bool:
    """True when we know how to drive this tool at all."""
    return tool_id in RECIPES or tool_id in ("yt-dlp", "tiktokdownloader")


# A tool can be installed and still be useless to us today. Offering it and
# failing on the button is a dead end, which decisions 6 and 15 forbid: a
# TikTok link proposed TikTokDownloader, looked ready, and answered "no
# runner" when pressed (found 2026-09-22 by the audit).
NOT_READY: dict[str, str] = {
    "f2":
        "it needs a cookie in its own settings file, which comes with step 5",
}


def unavailable_reason(tool_id: str) -> str | None:
    """Why this tool cannot be used right now, or None when it can."""
    if tool_id in NOT_READY:
        return NOT_READY[tool_id]
    if not can_run(tool_id):
        return "Teleloadzai does not know how to drive this tool yet"
    return None


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

def _snapshot(folder: Path) -> dict[Path, tuple[int, float]]:
    """Every file under a folder, with its size and date."""
    if not folder.is_dir():
        return {}
    found = {}
    for path in folder.rglob("*"):
        if path.is_file():
            try:
                info = path.stat()
                found[path] = (info.st_size, info.st_mtime)
            except OSError:
                pass
    return found


def _child_environment(module: str) -> dict:
    """UTF-8 forced, and our own package folder when we run a module."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if module:
        libs = str(tools.libs_dir())
        env["PYTHONPATH"] = libs + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run(
    tool_id: str,
    request: Request,
    on_progress: Callable[[int], None] | None = None,
    on_start: Callable[[subprocess.Popen], None] | None = None,
) -> RunResult:
    """Run one specialist tool and report what it actually wrote."""
    if tool_id == "tiktokdownloader":
        # No command line exists for this one; it is driven over HTTP.
        return _tiktok(request, on_progress)

    recipe = RECIPES.get(tool_id)
    if recipe is None:
        raise RunnerError(f"no recipe for {tool_id}")

    if recipe.module:
        exe = Path(sys.executable)
        head = [str(exe), "-m", recipe.module]
        if tools.installed_path(tool_id) is None:
            raise RunnerError(f"{tool_id} is not installed")
    else:
        found = tools.installed_path(tool_id)
        if found is None:
            raise RunnerError(f"{tool_id} is not installed")
        exe, head = found, []

    request.out_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(request.out_dir)

    command = head + recipe.build(exe, request)
    tail: list[str] = []

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,        # never wait for a human
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_child_environment(recipe.module),
        # A program run from our own folder drops its logs there: f2 wrote a
        # `logs/` folder straight into the project (2026-09-21). A module has
        # no folder of its own, so it works from the download folder instead.
        # A real program keeps its own folder, where its settings live.
        cwd=str(exe.parent) if not recipe.module else str(request.out_dir),
        creationflags=_NO_WINDOW,
    )
    if on_start:
        on_start(process)

    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        if on_progress:
            found_percent = _PERCENT.search(line)
            if found_percent:
                try:
                    on_progress(min(100, int(float(found_percent.group(1).replace(",", ".")))))
                except ValueError:
                    pass
        tail.append(line)
        del tail[:-40]

    code = process.wait()

    # What is new or changed since before the tool ran.
    #
    # ⚠️ Do NOT also test the file's date. gallery-dl keeps the date the web
    # server sent, so a picture from 2005 lands with a 2005 date, and a
    # "newer than the start" filter threw away the only file it downloaded
    # (found 2026-09-21). Comparing before and after needs no clock.
    afterwards = _snapshot(request.out_dir)
    written = sorted(
        path for path, stamp in afterwards.items()
        if (path not in before or before[path] != stamp)
        and not any(path.match(pattern) for pattern in recipe.ignore)
    )

    # A tool can end badly and still have written something useful, and it
    # can end well having written nothing. Both are reported honestly.
    if code != 0 and not written:
        said = _short_error(tail)
        if said:
            raise explain.from_tool(RunnerError(said))      # its words (decision 38)
        raise RunnerError(f"{tool_id} stopped with code {code}")

    if written and recipe.after:
        written = recipe.after(written)
    return RunResult(written, tail)


def _short_error(tail: list[str]) -> str:
    """The line worth showing, washed of anything that could be a cookie.

    This returns raw output from somebody else's program straight onto the
    screen. Decision 34 wants those words; hard rule 1 forbids one kind of
    word inside them. `redact` is what lets both be true (added 2026-09-22).
    """
    for line in reversed(tail):
        clean = line.strip()
        if any(word in clean.lower() for word in ("error", "失败", "错误", "traceback")):
            return cookies.redact(clean[:200])
    return cookies.redact(tail[-1][:200]) if tail else ""
