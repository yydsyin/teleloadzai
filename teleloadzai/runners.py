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

from . import cookies, explain, toolservers, tools
from .paths import BIN_DIR, make_folder

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Most tools print a percentage somewhere. Those that do not simply show
# "working" -- we do not invent a number we cannot measure.
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")

# What we say we are to a site's own servers: file servers refuse a request
# that does not look like a browser's.
_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0 Safari/537.36")


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
    # When nothing was written: the tool's OWN reason for skipping, in plain
    # words. Never inferred from "no new file" alone (decision 38).
    skip_reason: str = ""

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
    # Reads the tool's output and returns why it skipped, or "" if it did
    # not. Without this, "no new file" is an ERROR, never "already there":
    # XHS-Downloader failed three different ways -- wrong link, missing
    # note, no network -- ended with exit code 0 and no file, and the app
    # said "This file was already there" (found by step 5b, 2026-09-23).
    skipped: Callable[[list[str]], str] | None = None
    # How the tool writes its text. "" = UTF-8. "oem" = the code page Windows
    # gives console programs -- 936 (Chinese) on the developer's PC, while
    # Windows itself speaks French. N_m3u8DL-RE (.NET) writes that way, so a
    # French error arrived as "n��a pu ��tre" (seen 2026-09-23; decoding with
    # the OEM code page gave the clean text).
    encoding: str = ""
    # Files the tool SAYS it wrote, read from its output. Needed because
    # watching the folder cannot see an identical overwrite: gallery-dl's
    # "Download again" rewrote the same file with the same size and the
    # server's date, the folder looked unchanged, and the app reported an
    # error made of a hidden path (2026-09-23).
    reported: Callable[[list[str], Path], list[Path]] | None = None


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
    # "Download again" on a skipped job. Without this the button asked
    # gallery-dl to skip the same file a second time -- a dead button
    # (found by step 5b, 2026-09-23). `--no-skip` read from its own --help.
    if r.force:
        command += ["--no-skip"]
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


def _encoding(kind: str) -> str:
    """The Python codec for a recipe's `encoding` field."""
    if kind == "oem" and sys.platform == "win32":
        import ctypes
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    return "utf-8"


def _gallery_dl_reported(tail: list[str], out_dir: Path) -> list[Path]:
    """gallery-dl prints the path of every file it downloads, one per line,
    and `# <path>` for one it skipped (both seen 2026-09-23). A printed path
    that exists inside the download folder is a file it wrote.

    Only the last 40 lines are kept, so on a very large gallery re-downloaded
    in place this counts the last 40 -- enough to report a success, not an
    exact total.
    """
    base = out_dir.resolve()
    found: list[Path] = []
    for line in tail:
        text = line.strip()
        if not text or text.startswith(("#", "[")):
            continue
        path = Path(text)
        try:
            if path.is_file() and path.resolve().is_relative_to(base):
                found.append(path)
        except (OSError, ValueError):
            continue
    return found


def _gallery_dl_skipped(tail: list[str]) -> str:
    """gallery-dl prints `# <path>` for a file it did not download because it
    is already there -- and the file IS there (seen 2026-09-23: second run on
    the same image, same folder, 1 file, exit code 0)."""
    if any(line.startswith("# ") for line in tail):
        return "The file is already in this folder, so gallery-dl did not download it again."
    return ""


def _xhs_skipped(tail: list[str]) -> str:
    """XHS-Downloader's summary line says how many it skipped and why.

    Seen 2026-09-23: "作品 <id> 存在下载记录，跳过处理" ("this note has a
    download record, skipped") then "共处理 1 个作品，成功 0 个，失败 0 个，
    跳过 1 个". ⚠️ Its skip does NOT mean the file is in this folder: it
    skipped into a brand-new empty folder, because it keeps its own history
    of every note it ever downloaded. Saying "already there" would be false.
    """
    if any("存在下载记录" in line for line in tail):
        return ("XHS-Downloader skipped this note: it keeps a history of every "
                "note it has downloaded, and this one is in it. The file may be "
                "in another folder. Press \"Download again\" to get it here.")
    return ""


RECIPES: dict[str, Recipe] = {
    "gallery-dl": Recipe("gallery-dl", _gallery_dl, module="gallery_dl",
                         skipped=_gallery_dl_skipped, reported=_gallery_dl_reported),
    "streamlink": Recipe("streamlink", _streamlink, after=_repackage_to_mp4),
    "xhs-downloader": Recipe("xhs-downloader", _xhs, ignore=("*.db",),
                             skipped=_xhs_skipped),
    "n-m3u8dl-re": Recipe("n-m3u8dl-re", _n_m3u8dl_re, encoding="oem"),
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

    # The cheap check first: a folder that cannot be created used to be
    # found only after the server had started and answered (57 s, 2026-09-23).
    make_folder(request.out_dir)

    # One site's cookies only, and only when this job may use cookies at all.
    cookie = cookies.header_for(site, True) if request.cookie_header else ""

    toolservers.TIKTOK.start()
    try:
        data = toolservers.detail(request.url, douyin, cookie)
    finally:
        toolservers.TIKTOK.release()

    # MP3 is the sound of THIS video, as with yt-dlp and Kuaishou. It used to
    # be `music_url` -- the post's background music, another recording --
    # and, when a post had none, the video itself saved as .mp4: asked for an
    # MP3, the user got a 27 MB video (seen 2026-09-24).
    address = data.get("downloads") or ""
    if not isinstance(address, str) or not address.startswith("http"):
        raise RunnerError(
            "TikTokDownloader found the work but gave no file to download. "
            "It may be a photo post, or a live stream that has ended.")

    name = request.out_name or _clean_name(data)
    if not douyin:
        cookie = _with_page_cookies(request.url, cookie)
    if request.mode == "mp3":
        # The video is only a step: its own name, so the user's MP4 of the
        # same post is never overwritten, then deleted (the Kuaishou bug).
        video = request.out_dir / (name + ".teleloadzai-audio.mp4")
        _fetch(address, video, site, on_progress, cookie)
        target = _to_mp3(video, request.out_dir / (name + ".mp3"))
    else:
        target = request.out_dir / (name + ".mp4")
        _fetch(address, target, site, on_progress, cookie)
    return RunResult([target], [f"TikTokDownloader: {data.get('desc', '')[:80]}"])


def _kuaishou(request: Request, on_progress: Callable[[int], None] | None) -> RunResult:
    """KS-Downloader: the same road as TikTokDownloader, on port 5557.

    Proven 2026-09-23 on a real video: 2.43 MB, 960x720, 10.0 s, decoded
    clean by ffmpeg, with no cookie. yt-dlp ("Unsupported URL"), lux and
    you-get (both broken on today's page) all failed on the same link --
    which is why this is the only Kuaishou tool (decision 39).
    """
    make_folder(request.out_dir)

    # Kuaishou's cookies only, and only when this job may use cookies at all.
    cookie = cookies.header_for("kuaishou.com", True) if request.cookie_header else ""

    toolservers.KS.start()
    try:
        data = toolservers.ks_detail(request.url, cookie)
    finally:
        toolservers.KS.release()

    address = data.get("download")
    if not isinstance(address, str) or not address.startswith("http"):
        # Its own label for the post, not our guess about why (decision 38).
        kind = data.get("photoType") or "unknown"
        raise RunnerError(
            f"KS-Downloader found the post (type: {kind}) but gave no single "
            "video file to download.")

    name = request.out_name or _clean_name(
        {"nickname": data.get("name", ""), "desc": data.get("caption", "")})
    if request.mode == "mp3":
        # The video is only a step, so it gets a name of its own. Fetched as
        # `<name>.mp4` it overwrote -- then deleted -- the user's own MP4 of
        # the same post (seen 2026-09-23: MP4, then MP3, left only the MP3).
        video = request.out_dir / (name + ".teleloadzai-audio.mp4")
        _fetch(address, video, "kuaishou.com", on_progress)
        target = _to_mp3(video, request.out_dir / (name + ".mp3"))
    else:
        target = request.out_dir / (name + ".mp4")
        _fetch(address, target, "kuaishou.com", on_progress)
    return RunResult([target], [f"KS-Downloader: {str(data.get('caption', ''))[:80]}"])


def _to_mp3(video: Path, target: Path) -> Path:
    """Keep only the sound of a downloaded video, as an MP3.

    Kuaishou has no separate music link to ask for, so MP3 means "the sound
    of this video". ``video`` is a temporary file of ours and is removed once
    the MP3 exists; if FFmpeg is missing or fails, the user is told and keeps
    the video.
    """
    ffmpeg = tools.installed_path("ffmpeg")
    if ffmpeg is None:
        raise RunnerError(
            f"The video was downloaded ({video.name}), but FFmpeg is not "
            "installed, so it could not be turned into an MP3.")
    done = subprocess.run(
        [str(ffmpeg), "-y", "-i", str(video), "-vn", "-c:a", "libmp3lame",
         "-q:a", "0", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=1800, creationflags=_NO_WINDOW,
    )
    if done.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise RunnerError(
            f"The video was downloaded ({video.name}), but turning it into an "
            "MP3 failed. The video is kept.")
    video.unlink(missing_ok=True)
    return target


def _with_page_cookies(page: str, cookie: str) -> str:
    """Add the cookies TikTok hands out with the video's own page.

    Its file server wants `tt_chain_token`, measured 2026-09-24 with a 1 KB
    request: the video-page cookies -> 206; the same minus `tt_chain_token`
    -> 403. A log-in window closed on tiktok.com/login never gets that cookie,
    and a plain request for the video page does (seen twice the same day).
    So we do what a browser does: open the page, then fetch the file.

    ⚠️ The page must be asked WITH the cookies we hold. The token belongs to
    the visit that made it: measured the same day, held cookies + a token
    from an unrelated visit -> 403; held cookies + a token from a visit that
    carried them -> 206. The page goes to tiktok.com itself -- the same site
    those cookies came from.

    Only names we do not already hold are added -- a logged-in cookie is
    never replaced by a visitor's. Nothing here is written to disk; it lives
    for this one download (hard rule 1). If the page cannot be read, the held
    cookies go out unchanged and the fetch says what went wrong.
    """
    import http.cookiejar
    host = (urllib.parse.urlsplit(page).hostname or "").lower()
    if not (host == "tiktok.com" or host.endswith(".tiktok.com")):
        return cookie           # never send TikTok's cookies anywhere else
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {"User-Agent": _BROWSER}
    if cookie:
        headers["Cookie"] = cookie
    try:
        with opener.open(urllib.request.Request(page, headers=headers), timeout=30) as answer:
            answer.read(1)
    except Exception:
        return cookie
    held = {part.split("=", 1)[0].strip() for part in cookie.split(";") if "=" in part}
    extra = [f"{c.name}={c.value}" for c in jar
             if c.name not in held and (c.domain.lstrip(".") == "tiktok.com"
                                        or c.domain.endswith(".tiktok.com"))]
    return "; ".join(p for p in [cookie.strip("; ")] + extra if p)


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
        "User-Agent": _BROWSER,
        "Referer": f"https://www.{site}/",
    }
    host = (urllib.parse.urlsplit(address).hostname or "").lower()
    if cookie and (host == site or host.endswith("." + site)):
        headers["Cookie"] = cookie
    request = urllib.request.Request(address, headers=headers)
    make_folder(target.parent)
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


# What each tool REALLY does with the window's choices -- the window shows
# these and nothing else (the user, 2026-09-26: "don't fabricate something
# that does not exist"). Until then the Quality list was shown for every
# tool and only yt-dlp and streamlink ever received it.
#   "mp3" / "mp4": the button exists. Its value is the quality list the tool
#   takes ("kbps", "height"), or "" for none -- then "best" is sent.
#   "label": the MP4 button's words, where the tool hands back the post's own
#   files (pictures, videos) as they are, not an MP4 we chose.
# Read in each recipe on 2026-09-26; measured where a choice is passed on.
CHOICES: dict[str, dict] = {
    # Measured 2026-09-25/26 on real files: 2160/1080/720/480/360p and
    # 320/192/128 kbps each came out as asked.
    "yt-dlp": {"mp3": "kbps", "mp4": "height"},
    # Heights passed as its own stream names (_STREAMLINK_QUALITY); not
    # measured on a live stream. Its "MP3" gave an audio .mp4: no MP3 button.
    "streamlink": {"mp4": "height"},
    # MP3 really made, by our ffmpeg at its best setting; no quality passed.
    "tiktokdownloader": {"mp3": "", "mp4": ""},
    "ks-downloader": {"mp3": "", "mp4": ""},
    # Neither the mode nor the quality reaches these three.
    "gallery-dl": {"mp4": "", "label": "Original files"},
    "xhs-downloader": {"mp4": "", "label": "Original files"},
    "n-m3u8dl-re": {"mp4": "", "label": "Original file"},
    "f2": {"mp4": "", "label": "Original files"},
}


def can_run(tool_id: str) -> bool:
    """True when we know how to drive this tool at all."""
    return tool_id in RECIPES or tool_id in ("yt-dlp", "tiktokdownloader", "ks-downloader")


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
    if tool_id == "ks-downloader":
        return _kuaishou(request, on_progress)

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

    make_folder(request.out_dir)
    before = _snapshot(request.out_dir)

    command = head + recipe.build(exe, request)
    tail: list[str] = []

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,        # never wait for a human
        text=True,
        encoding=_encoding(recipe.encoding),
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
        # A crash report is never the reason, and it is long: N_m3u8DL-RE
        # printed 64 lines when the network failed, the last 40 were all
        # stack frames, and the one line that said what happened (line 14)
        # was dropped before anyone read it (2026-09-23).
        if not line.strip().startswith(("at ", "--- End of")):
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

    if recipe.reported:
        said_written = recipe.reported(tail, request.out_dir)
        written = sorted(set(written) | set(said_written))

    if not written:
        reason = recipe.skipped(tail) if recipe.skipped else ""
        if reason:
            return RunResult([], tail, skip_reason=reason)
        said = _short_error(tail)
        if said:
            raise explain.from_tool(RunnerError(said))      # its words (decision 38)
        raise RunnerError(f"{tool_id} finished without downloading anything, "
                          "and said nothing about why.")

    if recipe.after:
        written = recipe.after(written)
    return RunResult(written, tail)


def _short_error(tail: list[str]) -> str:
    """The line worth showing, washed of anything that could be a cookie.

    This returns raw output from somebody else's program straight onto the
    screen. Decision 34 wants those words; hard rule 1 forbids one kind of
    word inside them. `redact` is what lets both be true (added 2026-09-22).
    """
    # Lines that are never the reason, seen in step 5b (2026-09-23):
    #   "at ...InvokeAsync>d__0.MoveNext() + 0x1aa"  -- N_m3u8DL-RE's crash
    #       report; its real reason ("... 404 (Not Found)") comes before.
    #   "共处理 1 个作品，成功 0 个，失败 1 个..."    -- XHS-Downloader's summary;
    #       it contains 失败 (failed) but the reason is the line above it.
    useful = [l.strip() for l in tail
              if l.strip() and not l.strip().startswith(("at ", "--- End of", "共处理"))]
    for clean in reversed(useful):
        if any(word in clean.lower()
               for word in ("error", "exception", "失败", "错误", "traceback")):
            return cookies.redact(clean.lstrip("-> ")[:200])
    return cookies.redact(useful[-1][:200]) if useful else ""
