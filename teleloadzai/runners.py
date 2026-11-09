"""Run the specialist tools: one engine, one recipe per tool.

`ytdlp.py` stays on its own, because yt-dlp lets us choose the shape of its
progress and tell us the exact file it wrote. None of the others do. So this
module works the other way round:

**Watch the folder.** Each run gets a folder of its own (`_work_folder`), and
what the tool finished there is what it downloaded. That works for every
tool, whatever it prints, and it answers the question of decision 24 for
free: if nothing arrived, nothing was downloaded, and we must not claim a
success. *(Until 2026-10-18 the user's own folder was watched, before and
after -- and a download running beside it was taken for this tool's.)*

Two things every tool gets, and both were learned the hard way:

* **UTF-8 forced in its environment.** f2 printed a rocket and crashed,
  because this machine's console speaks GBK (checked 2026-09-21).
* **stdin closed.** A tool that decides to ask a question must fail, not
  wait forever for a human who is not watching.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import children, cookies, explain, toolservers, tools, ytdlp
from .dialogs import (NAME_ENDING, UNKNOWN, PathTooLong, fit_name, free_name, name_room,
                      units, without_media_ending)
from .paths import BIN_DIR, DATA_DIR, make_folder

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Most tools print a percentage somewhere. Those that do not simply show
# "working" -- we do not invent a number we cannot measure.
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")
# What the Console leaves out: a progress line -- a percentage standing on
# its own ("45.20% 3.1MB/s"), never one inside a name ("file1%20copy.mp4"),
# and never an error line ("ERROR: HTTP 403 at 50%"): the plain _PERCENT
# swallowed both (grids of 2026-10-25).
_PROGRESS_LINE = re.compile(r"^(?!.*\b(?:ERROR|WARN)\b)(?=.*(?<![\w%])\d{1,3}(?:[.,]\d+)?\s?%(?![\w%]))")

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
    # The FULL name chosen in "Save as" ("Foo.mp4"). Windows asked about that
    # name only: a "Foo.ts" handed back by the tool is another file, and an
    # older "Foo.ts" of the user's was replaced by the base-name test
    # (round 3 of the hunt, 2026-10-18).
    out_file: str = ""
    # The title the card read, or "" when nobody could. Used to name the file
    # when the tool leaves the name to us and the user was not asked.
    title: str = ""
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
    # Subtitles (Phase 2 item 7): "" off, "embed", "file"; the track's code.
    subs: str = ""
    sub_lang: str = ""
    # The row this run belongs to: written in its work folder, so the start-
    # up sweep can tell which row a file it saves from a crash finishes.
    job_id: str = ""
    # Set by Stop. A tool driven by its server holds no process for Stop to
    # end while it reads the post or while we fetch its file: Stop said
    # "stopped" and the whole video still arrived (silent-failure hunt,
    # 2026-10-18). Every step checks this.
    stop: threading.Event | None = field(default=None, compare=False)


def _stopped(request: Request) -> bool:
    return request.stop is not None and request.stop.is_set()


def _check_stop(request: Request) -> None:
    if _stopped(request):
        raise RunnerError("Stopped.")       # the job is already "stopped": never shown


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
    # Clutter the tool leaves beside its download: never moved out of the
    # work folder, so it goes with it. Exact names, never a pattern. XHS-Downloader writes an empty `ExploreData.db` beside every
    # video, whatever its own `record_data` setting says (False, and the file
    # still came, with 0 rows -- seen 2026-09-26).
    litter: tuple[str, ...] = ()
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
    # The line a tool prints when the link is a LIVE stream. Only then is
    # what it wrote kept on Stop: a normal N_m3u8DL-RE download merges its
    # picture BEFORE fetching the sound, and Stop kept a silent video called
    # "Recorded until Stop" (round 8 of the hunt, with the real tool).
    live_sign: str = ""


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
    name = _file_name(r) + ".ts"
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
    # A LIVE stream (all four flags read from its own --help, and seen on a
    # real YouTube live 2026-10-21): without them it recorded with no end and
    # kept only pieces until the stream ended, and Stop lost everything.
    # `--live-real-time-merge` builds one `<name>.ts` as it records;
    # `--live-keep-segments false` drops the pieces (with them, every piece
    # would have been moved into the user's folder); `--live-record-limit`
    # is the "Stop a live recording after" setting (110 s asked, 110.0 s
    # recorded). It counts the stream's time from its first fetch, which
    # already holds the last minute or so. And no update check against
    # GitHub on every run.
    command = [str(exe), r.url,
               "--auto-select",
               "--tmp-dir", str(r.out_dir),
               "--save-dir", str(r.out_dir),
               "--save-name", _file_name(r),
               "--live-real-time-merge",
               "--live-keep-segments", "false",
               "--disable-update-check",
               # Its own words in English: "Live stream found" is how a live
               # run is told from a normal one (`Recipe.live_sign`). In the
               # PC's language it printed Chinese, unreadable here.
               "--ui-language", "en-US"]
    if r.limit_minutes > 0:
        # HH:mm:ss has no 24th hour: the setting's top (24 h) becomes 23:59.
        minutes = min(r.limit_minutes, 23 * 60 + 59)
        command += ["--live-record-limit", f"{minutes // 60:02d}:{minutes % 60:02d}:00"]
    # Picture and sound joined into ONE .mp4 (its own "-M", read in
    # `--morehelp mux-after-done`). Without it, a stream that keeps its sound
    # apart left a SILENT video and the sound beside it, and the row said
    # done: Apple's test stream gave bip.mp4 (no sound) + bip.en.m4a +
    # bip.en.srt; a Sky News live gave live.copy.ts (picture) + live.ts
    # (sound); with -M, one .mp4 with both (ffprobe, 2026-10-25). An MP3 is
    # taken from that video's sound, so it needed this too. FFmpeg is found
    # beside the program by itself (`bin_path` auto, seen).
    # Subtitles (Phase 2 item 7), all three seen on the disk the same day:
    # off -> none downloaded, none kept; "embed" -> a mov_text track and no
    # file left; "file" -> `<name>.<lang>.srt` beside the .mp4.
    wanted = r.mode == "mp4" and r.subs in ("embed", "file") and bool(
        ytdlp.SUB_LANG.fullmatch(r.sub_lang or ""))
    command += ["-M", "format=mp4" + ("" if wanted and r.subs == "embed" else ":skip_sub=true")]
    if wanted:
        command += ["--select-subtitle", f'lang="{r.sub_lang}":for=best']
    else:
        command += ["--drop-subtitle", "lang=.*"]
    return command


# Our heights as yutto's quality codes (its own `-q` list, 2.3.1: 16 360p,
# 32 480p, 64 720p, 80 1080p, 112 1080p+, 116 1080p60, 120 4K, 127 8K). It
# takes the best it has at or below the code: asked 1080p without a log-in,
# it gave 480p (seen 2026-11-09) -- hence `TOP_WITHOUT_LOGIN`.
_YUTTO_QUALITY = {"best": "127", "1080": "116", "720": "64", "480": "32", "360": "16"}


def _yutto(_exe: Path, r: Request) -> list[str]:
    # Every flag read from its own --help (2.3.1) and seen 2026-11-09.
    # `--no-progress`: through a pipe it prints no percentage anyway; the row
    # measures the bytes in the folder. No comments overlay (danmaku), no
    # subtitles, no cover picture, no chapters: one video file, as asked.
    command = [r.url, "-d", str(r.out_dir), "--tmp-dir", str(r.out_dir),
               "-q", _YUTTO_QUALITY.get(r.quality, "127"),
               "--no-color", "--no-progress", "--no-danmaku", "--no-subtitle",
               "--no-cover", "--no-chapter-info"]
    # Our name ("Save as", else the card's title). yutto fills `-tp` with
    # Python's str.format, so a brace in a title is doubled to stay a brace.
    # With no title, yutto's own (it reads the video's) beats "unknown".
    if r.out_name or r.title:
        command += ["-tp", _file_name(r).replace("{", "{{").replace("}", "}}")]
    # The log-in, from yutto's own file made for this run (cookies.yutto_auth,
    # handed in as `cookie_file` by `run`). Never on the command line.
    if r.cookie_file:
        command += ["--auth-file", str(r.cookie_file), "--auth-profile", "default"]
    return command


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
        # Written as `.tmp` and renamed once whole: a crash half-way left an
        # unplayable `name.mp4` that the next start took for a download.
        partial = target.with_name(target.name + ".tmp")
        try:
            # Tied to the app: started loose, it outlived a closed app.
            done = subprocess.Popen(
                [str(ffmpeg), "-y", "-i", str(path), "-c", "copy",
                 "-movflags", "+faststart", "-f", "mp4", str(partial)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
            )
            children.bind(done)
            done.wait(timeout=1800)
        except Exception:
            partial.unlink(missing_ok=True)
            final.append(path)
            continue

        if done.returncode == 0 and partial.is_file() and partial.stat().st_size > 0:
            partial.replace(target)
            path.unlink(missing_ok=True)
            final.append(target)
        else:
            partial.unlink(missing_ok=True)     # never leave a broken mp4
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
                             litter=("ExploreData.db",), skipped=_xhs_skipped),
    # "Live stream found": read on a real YouTube live, 2026-10-21.
    "n-m3u8dl-re": Recipe("n-m3u8dl-re", _n_m3u8dl_re, encoding="oem",
                          live_sign="Live stream found"),
    "yutto": Recipe("yutto", _yutto, module="yutto"),
}

# Tools that read only some of their platform's links. yutto read none of
# bilibili.tv (an international video: "url 不正确", exit 14, 2026-11-09), so
# it is not offered there (decision 40). A short link is resolved first.
READS_ONLY: dict[str, tuple[str, ...]] = {
    "yutto": ("bilibili.com",),
}


def reads_link(tool_id: str, url: str) -> bool:
    """False when this tool is known NOT to read this link's site."""
    hosts = READS_ONLY.get(tool_id)
    if not hosts:
        return True
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


# The highest picture a tool gives without a log-in, when it is lower than
# what the video has. yutto: 480p asked for 720p or 1080p, no word, exit 0
# (seen 2026-11-09); 1080p with the user's log-in. The card offers no more.
TOP_WITHOUT_LOGIN: dict[str, int] = {"yutto": 480}


def top_height(tool_id: str, logged_in: bool) -> int:
    """The highest height this tool can give now, or 0 for no limit known."""
    return 0 if logged_in else TOP_WITHOUT_LOGIN.get(tool_id, 0)


def _read_unless_stopped(read: Callable[[], dict], request: Request) -> dict:
    """A server's read, given up the moment Stop is pressed. Its answer can
    take up to 90 s, and waiting for it kept the server open 9 s
    (TikTokDownloader) and 16 s (KS-Downloader) after Stop, the row already
    "stopped", holding the cookie (2026-11-01). Leaving now sends the job to
    its `release()`, which shuts the server when no one else uses it; the
    read left behind dies with it."""
    if request.stop is None:
        return read()
    answer: dict = {}

    def work() -> None:
        try:
            answer["data"] = read()
        except Exception as problem:
            answer["error"] = problem

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(0.2)
        if _stopped(request):
            raise RunnerError("Stopped.")   # the job is already "stopped": never shown
    if "error" in answer:
        raise answer["error"]
    return answer["data"]


def _tiktok(request: Request, on_progress: Callable[[int], None] | None,
            on_start: Callable[[subprocess.Popen], None] | None = None,
            on_step: Callable[[str], None] | None = None,
            on_bytes: Callable[[int, int], None] | None = None) -> RunResult:
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

    # Said on the row: starting its server can take seconds, and reading
    # the post more (decision 33 -- a step, not only a clock).
    _say(on_step, "starting TikTokDownloader")
    toolservers.TIKTOK.start()
    try:
        # Stopped while it started: the post is not read, the cookie not sent.
        _check_stop(request)
        _say(on_step, "reading the post")
        data = _read_unless_stopped(lambda: toolservers.detail(request.url, douyin, cookie),
                                    request)
    finally:
        toolservers.TIKTOK.release()
    _check_stop(request)                # Stop pressed while the post was read
    _say(on_step, "")                   # the download's own percentage next

    # MP3 is the sound of THIS video, as with yt-dlp and Kuaishou. It used to
    # be `music_url` -- the post's background music, another recording --
    # and, when a post had none, the video itself saved as .mp4: asked for an
    # MP3, the user got a 27 MB video (seen 2026-09-24).
    address = data.get("downloads") or ""
    if not isinstance(address, str) or not address.startswith("http"):
        raise RunnerError(
            "TikTokDownloader found the work but gave no file to download. "
            "It may be a photo post, or a live stream that has ended.")

    name = _file_name(request, _clean_name(data))
    name = _reserve(request, name)
    reason = _already_there(request.out_dir / (name + "." + request.mode), request)
    if reason:
        return RunResult([], [], skip_reason=reason)
    if not douyin:
        cookie = _with_page_cookies(request.url, cookie)
    if request.mode == "mp3":
        # The video is only a step: its own name, so the user's MP4 of the
        # same post is never overwritten, then deleted (the Kuaishou bug).
        video = request.out_dir / (name + ".teleloadzai-audio.mp4")
        _fetch(address, video, site, on_progress, cookie, on_bytes, request.stop)
        # Its own data names the post, its author and its still cover
        # (fields read 2026-10-24; `dynamic_cover` moves, so not that one).
        target = _to_mp3_or_clean(video, request.out_dir / (name + ".mp3"), request,
                                  on_start, on_step,
                                  _tags(data.get("desc") or request.title, data.get("nickname")),
                                  data.get("static_cover"), site)
    else:
        target = request.out_dir / (name + ".mp4")
        _fetch(address, target, site, on_progress, cookie, on_bytes, request.stop)
    return RunResult([target], [f"TikTokDownloader: {data.get('desc', '')[:80]}"])


def _kuaishou(request: Request, on_progress: Callable[[int], None] | None,
              on_start: Callable[[subprocess.Popen], None] | None = None,
              on_step: Callable[[str], None] | None = None,
              on_bytes: Callable[[int, int], None] | None = None) -> RunResult:
    """KS-Downloader: the same road as TikTokDownloader, on port 5557.

    Proven 2026-09-23 on a real video: 2.43 MB, 960x720, 10.0 s, decoded
    clean by ffmpeg, with no cookie. yt-dlp ("Unsupported URL"), lux and
    you-get (both broken on today's page) all failed on the same link --
    which is why this is the only Kuaishou tool (decision 39).
    """
    make_folder(request.out_dir)

    # Kuaishou's cookies only, and only when this job may use cookies at all.
    cookie = cookies.header_for("kuaishou.com", True) if request.cookie_header else ""

    _say(on_step, "starting KS-Downloader")
    toolservers.KS.start()
    try:
        _check_stop(request)
        _say(on_step, "reading the post")
        data = _read_unless_stopped(lambda: toolservers.ks_detail(request.url, cookie), request)
    finally:
        toolservers.KS.release()
    _check_stop(request)
    _say(on_step, "")

    address = data.get("download")
    if not isinstance(address, str) or not address.startswith("http"):
        # Its own label for the post, not our guess about why (decision 38).
        kind = data.get("photoType") or "unknown"
        raise RunnerError(
            f"KS-Downloader found the post (type: {kind}) but gave no single "
            "video file to download.")

    name = _file_name(request, _clean_name(
        {"nickname": data.get("name", ""), "desc": data.get("caption", "")}))
    name = _reserve(request, name)
    reason = _already_there(request.out_dir / (name + "." + request.mode), request)
    if reason:
        return RunResult([], [], skip_reason=reason)
    if request.mode == "mp3":
        # The video is only a step, so it gets a name of its own. Fetched as
        # `<name>.mp4` it overwrote -- then deleted -- the user's own MP4 of
        # the same post (seen 2026-09-23: MP4, then MP3, left only the MP3).
        video = request.out_dir / (name + ".teleloadzai-audio.mp4")
        _fetch(address, video, "kuaishou.com", on_progress, on_bytes=on_bytes,
               stop=request.stop)
        target = _to_mp3_or_clean(video, request.out_dir / (name + ".mp3"), request,
                                  on_start, on_step,
                                  _tags(data.get("caption") or request.title, data.get("name")),
                                  data.get("coverUrl"), "kuaishou.com")
    else:
        target = request.out_dir / (name + ".mp4")
        _fetch(address, target, "kuaishou.com", on_progress, on_bytes=on_bytes,
               stop=request.stop)
    return RunResult([target], [f"KS-Downloader: {str(data.get('caption', ''))[:80]}"])


def _to_mp3_or_clean(video: Path, target: Path, request: Request,
                     on_start: Callable[[subprocess.Popen], None] | None,
                     on_step: Callable[[str], None] | None,
                     tags: dict[str, str] | None = None,
                     cover_address: object = None, site: str = "") -> Path:
    """`_to_mp3` for the server tools' step video, which is ours: after a
    Stop it goes, instead of staying as `name.teleloadzai-audio.mp4`.
    The cover is fetched here, beside that step video, so it goes with it."""
    try:
        # Said before the cover is fetched (up to 20 s on a slow site): a
        # row at 100% with nothing beside it looks frozen (decision 33).
        _say(on_step, "making the MP3")
        cover = _cover(cover_address, video, site)
        if _stopped(request) and cover:
            cover.unlink(missing_ok=True)
        _check_stop(request)
        return _to_mp3(video, target, request.quality, on_start=on_start, on_step=on_step,
                       tags=tags, cover=cover)
    except Exception:
        # The target is NOT deleted: FFmpeg writes `.tmp` (removed in
        # `_to_mp3`), so the name may still be the user's own older MP3 --
        # deleting it on a Stop lost it (round 4 of the hunt, 2026-10-18).
        if _stopped(request):
            video.unlink(missing_ok=True)
        raise


def _say(on_step: Callable[[str], None] | None, step: str) -> None:
    if on_step:
        on_step(step)


# Names the server tools (TikTokDownloader, KS-Downloader) are writing now.
# They fetch straight into the user's folder, and two different posts of the
# same name (same author, no caption) both passed the "already there" check
# before either file existed, then wrote the same "name.mp4.part" -- one
# video lost, both rows done (hunt of 2026-10-31).
_writing: dict[str, int] = {}
_writing_lock = threading.Lock()


def _reserve(request: Request, name: str) -> str:
    """`name`, or "name (2)"... -- the first one no other running job of
    these tools is writing in this folder. Held until `_release(request)`.
    A name chosen in "Save as" is kept: the list already refuses a second
    download to it (server.queue_download)."""
    def key(stem: str) -> str:
        return os.path.normcase(os.path.abspath(request.out_dir / f"{stem}.{request.mode}"))

    with _writing_lock:
        base, number = name, 2
        if not request.out_name:
            while _writing.get(key(name), id(request)) != id(request):
                name, number = f"{base} ({number})", number + 1
        _writing[key(name)] = id(request)
    return name


def _release(request: Request) -> None:
    with _writing_lock:
        for held in [k for k, owner in _writing.items() if owner == id(request)]:
            del _writing[held]


def _already_there(target: Path, request: Request) -> str:
    """Why this file must not be written, or "" -- decision 24, road (b).

    When the user picked the name in "Save as" (``out_name``), Windows has
    already asked about replacing it; "Download again" (``force``) is the
    user asking. Otherwise a file of the same name is his, and it stays:
    FFmpeg's ``-y`` and our own fetch used to replace it without a word
    (found 2026-09-26).
    """
    if request.force or request.out_name or not target.exists():
        return ""
    return (f"\"{target.name}\" is already in this folder, and Teleloadzai "
            "never replaces a file without asking.")


def _cover(address: object, beside: Path, site: str) -> Path | None:
    """Fetch a post's cover picture for its MP3, or None.

    The address comes from the tool's own data (TikTokDownloader's
    `static_cover`, KS-Downloader's `coverUrl`, read 2026-10-24). A cover is
    a bonus: when it cannot be had, the MP3 is made without it and the row
    says so (`ytdlp.cover_note`), never a failed download.
    """
    if not isinstance(address, str) or not address.startswith("http"):
        return None
    picture = beside.with_name(beside.name + ".cover")
    request = urllib.request.Request(address, headers={
        "User-Agent": _BROWSER, "Referer": f"https://www.{site}/"})
    try:
        with urllib.request.urlopen(request, timeout=20) as answer:
            data = answer.read(10 * 1024 * 1024 + 1)
        if not data or len(data) > 10 * 1024 * 1024:
            return None
        picture.write_bytes(data)
    except Exception:
        picture.unlink(missing_ok=True)
        return None
    # A page of text instead of a picture would make FFmpeg fail, and the
    # MP3 with it. Checked BEFORE, not retried after: a Stop also makes
    # FFmpeg fail, and a retry would start it again.
    if ytdlp.has_cover(picture) is not True:
        picture.unlink(missing_ok=True)
        return None
    return picture


def _tags(title: object = "", artist: object = "") -> dict[str, str]:
    """The MP3's title and artist, on one line each ("" left out)."""
    found = {"title": title, "artist": artist}
    return {k: " ".join(str(v).split()) for k, v in found.items() if v and str(v).strip()}


def _to_mp3(video: Path, target: Path, quality: str = "best", remove: bool = True,
            on_start: Callable[[subprocess.Popen], None] | None = None,
            on_step: Callable[[str], None] | None = None,
            tags: dict[str, str] | None = None, cover: Path | None = None) -> Path:
    """Keep only the sound of a downloaded video, as an MP3.

    Kuaishou has no separate music link to ask for, so MP3 means "the sound
    of this video". ``quality`` is the window's kbps ("320", "192", "128"), or
    "best" -- LAME's top variable setting, as yt-dlp's own "best" MP3.
    ``video`` is removed once the MP3 exists, only when ``remove`` says it is
    ours; if FFmpeg is missing or fails, the user is told and keeps the video.
    FFmpeg is handed to ``on_start`` so Stop reaches it too: a 60-minute
    recording takes a while to convert.
    ``tags`` (title, artist) and ``cover`` (a picture file, removed here) go
    into the MP3 as ID3v2.3, the version yt-dlp writes and Windows reads
    (Phase 2 item 5).
    """
    ffmpeg = tools.installed_path("ffmpeg")
    if ffmpeg is None:
        if cover:
            cover.unlink(missing_ok=True)
        raise RunnerError(
            f"The video was downloaded ({video.name}), but FFmpeg is not "
            "installed, so it could not be turned into an MP3.")
    if on_step:
        on_step("making the MP3")       # the row says it, never a frozen 100%
    rate = ["-q:a", "0"] if quality == "best" else ["-b:a", f"{int(quality)}k"]
    # The cover as a JPEG marked "front cover", whatever the site sent
    # (TikTok's may be WebP); without one, the sound only, as before.
    picture = (["-i", str(cover), "-map", "0:a:0", "-map", "1:v:0", "-c:v", "mjpeg",
                "-q:v", "2", "-disposition:v", "attached_pic"]
               if cover else ["-map", "0:a:0", "-vn"])
    labels = [arg for key, value in (tags or {}).items() for arg in ("-metadata", f"{key}={value}")]
    # Written as `.tmp`, renamed once whole (as `_repackage_to_mp4`).
    partial = target.with_name(target.name + ".tmp")
    process = subprocess.Popen(
        [str(ffmpeg), "-y", "-i", str(video), *picture, "-c:a", "libmp3lame",
         *rate, *labels, "-id3v2_version", "3", "-f", "mp3", str(partial)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    if on_start:
        on_start(process)
    try:
        code = process.wait()
    finally:
        if cover:
            cover.unlink(missing_ok=True)
    if code != 0 or not partial.is_file() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise RunnerError(
            f"The video was downloaded ({video.name}), but turning it into an "
            "MP3 failed. The video is kept.")
    partial.replace(target)
    if remove:
        video.unlink(missing_ok=True)
    return target


# What a tool can hand back that holds sound. Pictures are left alone.
_SOUND_SUFFIXES = {".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts",
                   ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}


def _has_sound(path: Path) -> bool:
    """Does this file hold a sound track? Asked to ffprobe; when it cannot
    answer, yes -- FFmpeg will then say what is wrong."""
    ffmpeg = tools.installed_path("ffmpeg")
    probe = ffmpeg.with_name("ffprobe.exe") if ffmpeg else None
    if probe is None or not probe.is_file():
        return True
    try:
        found = subprocess.run(
            [str(probe), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=60, creationflags=_NO_WINDOW)
    except Exception:
        return True
    return found.returncode != 0 or bool(found.stdout.strip())


def _sound_of(written: list[Path], request: Request,
              on_start: Callable[[subprocess.Popen], None] | None,
              on_step: Callable[[str], None] | None = None) -> list[tuple[Path, str]]:
    """MP3 for the tools that only hand back a video (streamlink, XHS-Downloader,
    N_m3u8DL-RE): our FFmpeg keeps the sound, at the kbps the user chose.

    Everything here is in the run's own work folder (`_work_folder`), so the
    videos are ours and go once their MP3 exists. Until 2026-10-18 this ran
    in the user's folder and took every new video there as the tool's -- a
    YouTube MP4 downloading at the same time was turned into an MP3 and
    deleted (silent-failure hunt, reproduced with a fake tool).
    Returns (MP3 in the work folder, the name it should have in the user's).
    """
    candidates = [p for p in written if p.suffix.lower() in _SOUND_SUFFIXES and p.is_file()]
    if not candidates:
        raise RunnerError(
            "The program downloaded no video or sound file, so there is no MP3 to "
            "make.")
    # A track with no sound is a step, not a source: N_m3u8DL-RE hands back
    # the picture and the sound as two files, and the picture failed first --
    # the row said "the MP3 failed" beside a real MP3 (round 8, real tool).
    sources = [p for p in candidates if _has_sound(p)]
    if not sources:
        raise RunnerError("The program downloaded a video with no sound, so there is "
                          "no MP3 to make.")
    # The "Save as" name fits one file; several keep the tool's own names.
    chosen = request.out_name if len(sources) == 1 else ""
    final = [(p, p.name) for p in written if p not in candidates]
    for source in sources:
        # These tools hand back a file and no data: the title only, the
        # card's, else the name -- no artist, no cover (none is known).
        made = _to_mp3(source, source.with_name(free_name(source.parent, source.stem, "mp3") + ".mp3"),
                       request.quality, on_start=on_start, on_step=on_step,
                       tags=_tags(request.title or chosen or source.stem))
        final.append((made, (chosen or source.stem) + ".mp3"))
    return final


# The tools that can record a live stream into one growing file at the top
# of their work folder. Stop is how such a recording ends, so what they
# recorded is kept -- streamlink always (it only records lives), N_m3u8DL-RE
# only when it said the stream is live (`Recipe.live_sign`). Round 7 kept
# N_m3u8DL-RE's work on every Stop, on the belief that a normal download
# writes nothing at the top until the end; round 8 proved it false.
LIVE_RECORDERS = ("streamlink", "n-m3u8dl-re")

# Pieces a tool leaves while it works -- never a finished file. `.mark` are
# our own notes in the work folder (which tool, and whether it is live).
# "*.m4s": yutto's picture and sound before it joins them. A failed run
# moved `<title>_video.m4s` and `<title>_audio.m4s` into the user's folder as
# "saved before it failed" (a Bilibili timeout, 2026-11-09, real run).
_PIECES = ("*.part", "*.tmp", "*.ytdl", "*.mark", "*.m4s")
_LIVE_MARK = "teleloadzai-live.mark"

# The work folders that exist right now, one path per line. A crash or a
# closed console skips our clean-up, and the folder is hidden: its download
# stayed there unseen, taking the disk (round 2 of the hunt, 2026-10-18).
# `sweep_work_folders` deals with them at the next start.
WORK_LIST = DATA_DIR / "work-folders.txt"
_work_lock = threading.Lock()


def _note_work(work: Path, present: bool) -> None:
    with _work_lock:
        try:
            known = set(WORK_LIST.read_text(encoding="utf-8").splitlines()) \
                if WORK_LIST.is_file() else set()
            known.discard("")
            (known.add if present else known.discard)(str(work))
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temporary = WORK_LIST.with_name(WORK_LIST.name + ".tmp")
            temporary.write_text("\n".join(sorted(known)), encoding="utf-8")
            temporary.replace(WORK_LIST)
        except OSError:
            # The folder is still cleaned after the run; only a crash would
            # leave it unswept. Said, never swallowed.
            print(f"Could not note the work folder {work} in {WORK_LIST.name}.")


def _work_folder(out_dir: Path, tool_id: str = "") -> Path:
    """A folder of this run's own, inside the user's folder.

    Watching the user's folder could not tell this tool's files from another
    download's running beside it: with 2 downloads at once, a tool that
    failed was shown "done" with the other job's video, and an MP3 job
    converted and deleted the other job's MP4 (2026-10-18). A tool writes
    here; what it finished is moved out (`_move_out`); the rest goes with
    the folder. Inside the user's folder, so the move is a rename on the
    same disk, never a copy.

    No dot or underscore in front: XHS-Downloader strips both from the
    folder name it is given (its own name cleaner, read in its code), and
    would have written beside our folder instead of inside it.
    """
    make_folder(out_dir)
    work = out_dir / f"teleloadzai-{uuid.uuid4().hex[:8]}"
    try:
        work.mkdir()            # a new name: never someone else's folder
    except OSError as problem:
        raise RunnerError(f"Teleloadzai could not write in {out_dir}. Choose another "
                          f"folder. (Windows says: {problem.strerror or problem})") from problem
    _note_work(work, True)
    try:
        # Which tool, for the start-up sweep after a crash.
        (work / f"{tool_id or 'tool'}.tool.mark").write_text(tool_id, encoding="utf-8")
    except OSError:
        pass
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(work), 0x2)   # hidden
    return work


def _drop_work(work: Path) -> None:
    """Delete a work folder. One that cannot go yet (a file still held) stays
    on the list, and the next start deals with it."""
    shutil.rmtree(work, ignore_errors=True)
    if not work.exists():
        _note_work(work, False)


_JOB_MARK = "job.mark"       # a "*.mark": never taken for a download


def sweep_work_folders() -> list[tuple[str, Path]]:
    """At start: the work folders a crash left. Their finished files are put
    in the user's folder, never over one of his (a free name); the rest goes.
    A file that cannot be moved keeps its folder, never deleted with it
    (hunt of 2026-10-31): the next start tries again.
    Returns (row id or "", file) for each file saved -- the row it finishes
    is then no longer offered "Continue" -- and ("", folder) for each folder
    kept back, so both can be said."""
    if not WORK_LIST.is_file():
        return []
    saved: list[tuple[str, Path]] = []
    for line in WORK_LIST.read_text(encoding="utf-8").splitlines():
        work = Path(line)
        if not line or not work.name.startswith("teleloadzai-") or not work.is_dir():
            _note_work(work, False)
            continue
        # A normal N_m3u8DL-RE download cut off by a crash holds a half
        # file (the picture without its sound): nothing is rescued from it.
        # A live recording, or another tool's finished files, are.
        half = (work / "n-m3u8dl-re.tool.mark").is_file() and not (work / _LIVE_MARK).is_file()
        try:
            owner = (work / _JOB_MARK).read_text(encoding="utf-8").strip()
        except OSError:
            owner = ""
        stuck = False
        for path in ([] if half else work.iterdir()):
            if path.is_file() and not any(path.match(x) for x in (*_PIECES, "*.db")):
                stem, ending = path.stem, path.suffix.lstrip(".")
                target = work.parent / (free_name(work.parent, stem, ending) + path.suffix)
                try:
                    os.rename(path, target)
                    saved.append((owner, target))
                except OSError:
                    stuck = True
        if stuck:
            saved.append(("", work))
        else:
            _drop_work(work)
    return saved


def _finished(work: Path, recipe: Recipe, top_only: bool = False) -> list[Path]:
    """The files a tool finished in its work folder. Its bookkeeping, its
    clutter and its unfinished pieces are not downloads."""
    found = work.iterdir() if top_only else work.rglob("*")
    return sorted(p for p in found if p.is_file()
                  and not any(p.match(x) for x in (*recipe.ignore, *recipe.litter, *_PIECES)))


def _move_out(pairs: list[tuple[Path, str]], request: Request,
              own_names: bool) -> tuple[list[Path], list[str]]:
    """Move finished files from the work folder into the user's folder.

    Decision 24 decides what happens when the name is taken. Replaced only
    when the user asked: "Download again", or the very name he chose in
    "Save as" (Windows asked about that one, and only that one -- a post's
    other files keep the tool's names). Otherwise his file stays, and:
    ``own_names`` (streamlink, N_m3u8DL-RE: a name WE gave, from the title)
    -> the new file gets "name (2)" -- a second recording of a channel is not
    the first one; the post's own names (gallery-dl, XHS-Downloader) -> the
    same file is already there, and ours is dropped.
    When nobody asked, the move is a rename that REFUSES a taken name, so two
    jobs ending at the same moment cannot replace each other's file.
    Returns (files now in the user's folder, names that were already there).
    """
    moved: list[Path] = []
    already: list[str] = []
    for source, name in pairs:
        target = request.out_dir / name
        replace = request.force or (bool(request.out_file) and target.name == request.out_file)
        for _attempt in range(20):
            try:
                if replace:
                    os.replace(source, target)
                else:
                    os.rename(source, target)       # fails if the name is taken
                moved.append(target)
                break
            except FileExistsError:
                if not own_names:
                    already.append(name)
                    break
                target = request.out_dir / (free_name(request.out_dir, Path(name).stem,
                                                      target.suffix.lstrip(".")) + target.suffix)
            except OSError as problem:
                # The chosen name is held -- the old file open in a player.
                # The new one takes a free name beside it: a stopped live
                # recording was deleted with the work folder, and the row
                # said only "stopped" (round 5 of the hunt, 2026-10-18).
                spare = request.out_dir / (free_name(request.out_dir, Path(name).stem,
                                                     target.suffix.lstrip(".")) + target.suffix)
                try:
                    os.rename(source, spare)
                    moved.append(spare)
                    break
                except OSError:
                    pass
                failure = RunnerError(
                    f"\"{name}\" was downloaded, but could not be put in the folder: "
                    f"{problem.strerror or problem}. It is kept aside, and Teleloadzai "
                    "puts it in the folder the next time it starts.")
                failure.saved = moved       # the files before it ARE there: said
                failure.keep_work = True    # never deleted with the work folder
                raise failure from problem
    return moved, already


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
    """A file name from what the site says, safe for Windows, or "".

    A caption ending in ".mp4" would give "….mp4.mp4" (dialogs.MEDIA_ENDING).
    """
    raw = without_media_ending(f"{data.get('nickname', '')} {data.get('desc', '')}".strip())
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)[:120].strip().rstrip(".")


def _file_name(request: Request, found: str = "") -> str:
    """The file's base name, for the tools that let us choose it.

    The "Save as" choice first; then what the tool found in the post; then
    the title the card read; else "unknown" -- or "unknown (2)" when that is
    taken, so two videos without a title never share one name (asked by the
    user 2026-09-26). Until then a stream was always "stream.mp4", even
    when its title was on the card.
    """
    if request.out_name:
        # The user's own name is never cut: Windows asked about that one.
        if units(request.out_name) > name_room(request.out_dir):
            raise PathTooLong("The name chosen in \"Save as\" is too long for Windows once "
                              "Teleloadzai adds its working endings. Choose a shorter name "
                              "or folder.")
        return request.out_name
    # Cut to what the folder leaves (a deep folder + a long caption went over
    # Windows' 260 characters, 2026-10-24).
    name = found or _clean_name({"desc": request.title})
    if name:
        return fit_name(request.out_dir, name)
    return free_name(request.out_dir, UNKNOWN, "mp3" if request.mode == "mp3" else "mp4")


def _fetch(address: str, target: Path, site: str,
           on_progress: Callable[[int], None] | None, cookie: str = "",
           on_bytes: Callable[[int, int], None] | None = None,
           stop: threading.Event | None = None) -> None:
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
                    if stop is not None and stop.is_set():
                        raise RunnerError("Stopped.")   # the half file goes below
                    block = answer.read(256 * 1024)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if on_progress and total:
                        on_progress(min(100, int(done * 100 / total)))
                    if on_bytes:
                        on_bytes(done, total)       # the size the site sent
        if partial.stat().st_size == 0:
            raise RunnerError("The download came back empty.")
        # A connection that ends early is not an error to Python: the read
        # just returns nothing, and the loop ends as if the file were whole.
        # A server announcing 1,000,000 bytes and sending 300,000 gave a
        # 300,000-byte video under its real name, shown "done" (silent-
        # failure hunt, 2026-10-18).
        if total and done < total:
            raise RunnerError(
                f"The download was cut off at {done / 1048576:.1f} MB of "
                f"{total / 1048576:.1f} MB. Nothing was kept: try again.")
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
#   "subs": the Subtitles row's choices reach it (Phase 2 item 7).
# Read in each recipe on 2026-09-26; measured where a choice is passed on.
CHOICES: dict[str, dict] = {
    # Measured 2026-09-25/26 on real files: 2160/1080/720/480/360p and
    # 320/192/128 kbps each came out as asked. Subtitles probed 2026-10-25:
    # "In the video" = a mov_text track, nothing left beside it.
    "yt-dlp": {"mp3": "kbps", "mp4": "height", "subs": True},
    # Heights passed as its own stream names (_STREAMLINK_QUALITY); not
    # measured on a live stream.
    # MP3, for the five below: the tool's video, then our FFmpeg keeps the
    # sound at the kbps asked (_to_mp3 / _sound_of). Measured 2026-09-26 with
    # ffprobe on real links, 128 and 320 each came out as asked.
    "streamlink": {"mp3": "kbps", "mp4": "height"},
    "tiktokdownloader": {"mp3": "kbps", "mp4": ""},
    "ks-downloader": {"mp3": "kbps", "mp4": ""},
    # Neither the MP4 choice nor the quality reaches these: the post's own
    # files, as they are. gallery-dl makes no MP3.
    "gallery-dl": {"mp4": "", "label": "Original files"},
    "xhs-downloader": {"mp3": "kbps", "mp4": "", "label": "Original files"},
    # Subtitles: its -M / --select-subtitle, the three choices seen on the
    # disk 2026-10-25 (_n_m3u8dl_re).
    "n-m3u8dl-re": {"mp3": "kbps", "mp4": "", "label": "Original file", "subs": True},
    # MP4 only (the plan of 2026-11-09): MP3 and subtitles move the card to
    # yt-dlp. Heights seen 2026-11-09: 360p and 480p without a log-in, 1080p
    # with one -- capped by `top_height`.
    "yutto": {"mp4": "height"},
}


# The formats in which a tool names its files itself, from the post: a name
# typed in "Save as" never reaches it (`_move_out` keeps the tool's names).
# XHS-Downloader's single MP3 is the exception -- ours, from its video
# (`_sound_of`). The window asks these for a FOLDER, not a name it would
# throw away (found 2026-10-24, checking "Choose for each" on every tool).
NAMES_ITSELF: dict[str, tuple[str, ...]] = {
    "gallery-dl": ("mp4", "mp3"),
    "xhs-downloader": ("mp4",),
}


def can_run(tool_id: str) -> bool:
    """True when we know how to drive this tool at all."""
    return tool_id in RECIPES or tool_id in ("yt-dlp", "tiktokdownloader", "ks-downloader")


# A tool can be installed and still be useless to us today. Offering it and
# failing on the button is a dead end, which decisions 6 and 15 forbid: a
# TikTok link proposed TikTokDownloader, looked ready, and answered "no
# runner" when pressed (found 2026-09-22 by the audit).
# Empty since f2 was removed (2026-09-26): kept for the next tool that is
# installed before we can drive it.
NOT_READY: dict[str, str] = {}


def unavailable_reason(tool_id: str) -> str | None:
    """Why this tool cannot be used right now, or None when it can."""
    if tool_id in NOT_READY:
        return NOT_READY[tool_id]
    if not can_run(tool_id):
        return "Teleloadzai does not know how to drive this program yet"
    return None


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

def _grown(folder: Path, before: dict[Path, tuple[int, float]],
           ignore: tuple[str, ...] = ()) -> int:
    """Bytes of the files that are new or changed since `before`.

    Only the folder itself and the folders that are new are opened: a user's
    Downloads folder can hold thousands of files, read once a second. A
    tool's own bookkeeping (`Recipe.ignore`) is not a download: without that,
    XHS-Downloader's 12 KB database read "12 KB so far" for 84 s while its
    video was being written elsewhere (seen 2026-09-26).
    """
    known = {path.parent for path in before}
    total = 0
    waiting = [folder]
    while waiting:
        current = waiting.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    if path not in known:
                        waiting.append(path)
                elif entry.is_file(follow_symlinks=False):
                    # The file itself, not the folder listing: Windows lists a
                    # file still being written at its old size -- gallery-dl's
                    # growing video read 0 bytes the whole way (2026-09-26).
                    info = path.stat()
                    if (before.get(path) != (info.st_size, info.st_mtime)
                            and not any(path.match(pattern) for pattern in ignore)):
                        total += info.st_size
            except OSError:
                continue            # a piece removed while we looked
    return total


def _child_environment(module: str, work: Path | None = None) -> dict:
    """UTF-8 forced, and our own package folder when we run a module."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if module:
        libs = str(tools.libs_dir())
        env["PYTHONPATH"] = libs + os.pathsep + env.get("PYTHONPATH", "")
    if module == "yutto" and work is not None:
        # yutto reads `yutto.toml` from where it runs, else from
        # XDG_CONFIG_HOME (or ~/.config) -- and its saved log-in from there
        # too (its 2.3.1 code). Pointed at our empty work folder, a yutto the
        # user set up outside Teleloadzai never changes our downloads, and
        # its log-in is never used without the user's "Use my log-ins".
        env["XDG_CONFIG_HOME"] = str(work)
    return env


def run(
    tool_id: str,
    request: Request,
    on_progress: Callable[[int], None] | None = None,
    on_start: Callable[[subprocess.Popen], None] | None = None,
    on_step: Callable[[str], None] | None = None,
    on_bytes: Callable[[int, int], None] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> RunResult:
    """Run one specialist tool and report what it actually wrote."""
    if tool_id in ("tiktokdownloader", "ks-downloader"):
        try:
            if tool_id == "tiktokdownloader":
                # No command line exists for this one; it is driven over HTTP.
                return _tiktok(request, on_progress, on_start, on_step, on_bytes)
            return _kuaishou(request, on_progress, on_start, on_step, on_bytes)
        finally:
            _release(request)

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

    # gallery-dl and XHS-Downloader name their files themselves, inside the
    # work folder ("teleloadzai-1a2b3c4d\", 21 more): a folder with no room
    # for a name is said in words BEFORE anything runs, not left to a raw
    # error. (Our own names are cut to fit: `_file_name`.)
    name_room(request.out_dir, NAME_ENDING + units("teleloadzai-00000000\\"))
    work = _work_folder(request.out_dir, tool_id)
    if request.job_id:
        try:
            (work / _JOB_MARK).write_text(request.job_id, encoding="utf-8")
        except OSError:
            pass            # only the crash sweep reads it
    keep = False
    try:
        if tool_id in cookies.AUTH_FILE_CAPABLE:
            # yutto: Bilibili's log-in in a file of its own, for this run
            # only, handed in as `cookie_file` (`_yutto`), gone afterwards.
            with cookies.yutto_auth(request.cookie_header) as auth:
                return _run_in(work, recipe, exe, head, tool_id,
                               dataclasses.replace(request, cookie_file=auth),
                               on_progress, on_start, on_step, on_bytes, on_line)
        return _run_in(work, recipe, exe, head, tool_id, request,
                       on_progress, on_start, on_step, on_bytes, on_line)
    except Exception as problem:
        # A finished file that could not be moved out stays in the work
        # folder, still listed: the next start puts it in the user's folder.
        keep = getattr(problem, "keep_work", False)
        raise
    finally:
        # What was finished has been moved out; what is left is the tool's
        # pieces and clutter, in a folder this run created.
        if not keep:
            _drop_work(work)


# N_m3u8DL-RE prints its messages one after another with no line break, each
# starting with its time: the whole run arrived as ONE line, cut at 200
# characters before the reason ("... 404") was reached (round 9 of the hunt).
_STAMP = re.compile(r"(?=\d\d:\d\d:\d\d\.\d{3} (?:INFO|WARN|ERROR|DEBUG) :)")


def _lines(stream) -> Iterator[str]:
    """The tool's lines -- and, inside one, each message that starts with its
    time is a line of its own."""
    for raw in stream:
        for piece in _STAMP.split(raw.rstrip("\n")):
            yield piece


def _run_in(work: Path, recipe: Recipe, exe: Path, head: list[str], tool_id: str,
            request: Request,
            on_progress: Callable[[int], None] | None,
            on_start: Callable[[subprocess.Popen], None] | None,
            on_step: Callable[[str], None] | None,
            on_bytes: Callable[[int, int], None] | None,
            on_line: Callable[[str], None] | None = None) -> RunResult:
    """One tool run inside its work folder; finished files end in the user's."""
    # The tool is told the work folder. Names are still decided against the
    # user's folder when the files move out ("unknown (2)", decision 24).
    command = head + recipe.build(exe, dataclasses.replace(request, out_dir=work))
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
        env=_child_environment(recipe.module, work),
        # A program run from our own folder drops its logs there: f2 wrote a
        # `logs/` folder straight into the project (2026-09-21). A module has
        # no folder of its own, so it works from the work folder instead.
        # A real program keeps its own folder, where its settings live.
        cwd=str(exe.parent) if not recipe.module else str(work),
        creationflags=_NO_WINDOW,
    )
    if on_start:
        on_start(process)

    # These tools never say a size, but what they write grows in the folder
    # (seen 2026-09-26: gallery-dl's file 6.5 -> 53.4 MB, streamlink's .ts,
    # N_m3u8DL-RE's pieces). Measured once a second, never guessed.
    # A live recording: what it wrote is kept on Stop (`LIVE_RECORDERS`).
    live = tool_id == "streamlink"
    stop_watching = threading.Event()
    if on_bytes:
        def watch() -> None:
            while not stop_watching.wait(1.0):
                grown = _grown(work, {}, (*recipe.ignore, "*.mark"))
                if grown:                   # nothing yet: "Working…" stays
                    on_bytes(grown, 0)
        threading.Thread(target=watch, daemon=True).start()

    assert process.stdout is not None
    for line in _lines(process.stdout):
        if not line.strip():
            continue
        # The Console page (2026-10-25): the tool's words, but not its
        # percentage lines -- N_m3u8DL-RE repaints them many times a second,
        # and the row already shows the progress.
        if on_line and not _PROGRESS_LINE.search(line):
            on_line(line)
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
        if recipe.live_sign and not live and recipe.live_sign in line:
            live = True
            try:
                (work / _LIVE_MARK).write_text("live", encoding="utf-8")
            except OSError:
                pass            # only the crash sweep reads it

    code = process.wait()
    stop_watching.set()
    # The tool's names, unless it is one whose name we chose from the title.
    own_names = tool_id in LIVE_RECORDERS

    if _stopped(request):
        # A live recording is the exception: Stop is how it ENDS ("no limit"
        # records until the disk is full). Round 1 of the hunt deleted it with
        # the work folder -- 2 hours of stream gone, the row said "stopped"
        # (round 2, 2026-10-18). What was recorded is kept, as before; FFmpeg
        # is not handed to Stop here, or the stopped job would end it at once.
        recorded = _finished(work, recipe, top_only=True)
        if not live or not recorded:
            raise RunnerError("Stopped.")   # the pieces go with the work folder
        if request.mode == "mp3":
            try:
                pairs = _sound_of(recorded, request, children.bind, on_step)
            except RunnerError:
                pairs = [(p, p.name) for p in _finished(work, recipe, top_only=True)]
        else:
            pairs = [(p, p.name) for p in (recipe.after(recorded) if recipe.after else recorded)]
        moved, _ = _move_out(pairs, request, own_names)
        return RunResult(moved, tail)

    if code != 0:
        # A tool that failed is a failure, even when some files arrived (3
        # pictures of 8). Until 2026-10-18 any new file in the folder made it
        # "done" -- even another download's. Only complete files at the top
        # of the work folder are kept: N_m3u8DL-RE's pieces sit in a sub-
        # folder. They are said on the row, never claimed as the download.
        said = _short_error(tail)
        problem = explain.from_tool(RunnerError(said)) if said else \
            RunnerError(f"{tool_id} stopped with code {code}")
        # The tool's own error comes first: a file that could not be moved
        # (open in a viewer) must not hide it. A normal N_m3u8DL-RE run keeps
        # nothing: what it merged before failing is the picture without its
        # sound -- "Saved before it failed" was a silent video (round 9).
        keepable = [] if recipe.live_sign and not live else _finished(work, recipe, top_only=True)
        try:
            moved, _ = _move_out([(p, p.name) for p in keepable], request, own_names)
        except RunnerError as failure:
            moved = getattr(failure, "saved", [])
            problem.keep_work = getattr(failure, "keep_work", False)
        problem.saved = moved
        raise problem

    written = _finished(work, recipe)
    if recipe.reported:
        written = sorted(set(written) | set(recipe.reported(tail, work)))

    if not written:
        reason = recipe.skipped(tail) if recipe.skipped else ""
        if reason:
            return RunResult([], tail, skip_reason=reason)
        said = _short_error(tail)
        if said:
            raise explain.from_tool(RunnerError(said))      # its words (decision 38)
        raise RunnerError(f"{tool_id} finished without downloading anything, "
                          "and said nothing about why.")

    if request.mode == "mp3":
        # The sound only, straight from what the tool wrote: a .ts recording
        # is not repackaged to .mp4 first.
        try:
            pairs = _sound_of(written, request, on_start, on_step)
        except RunnerError as problem:
            # "The video is kept" must be true: the video sat in the work
            # folder and went with it (round 3, 2026-10-18). Not after a
            # Stop -- except a recording, which Stop never throws away.
            if _stopped(request) and not live:
                raise
            try:
                kept, _ = _move_out([(p, p.name) for p in _finished(work, recipe)],
                                    request, own_names)
            except RunnerError as failure:
                kept = getattr(failure, "saved", [])
                problem.keep_work = getattr(failure, "keep_work", False)
            if _stopped(request):
                return RunResult(kept, tail)
            problem.saved = kept
            raise
    else:
        if recipe.after:
            written = recipe.after(written)
        # A recording's name is the one we built ("Save as" or the title).
        pairs = [(p, p.name) for p in written]
    # A recording that ended by itself and is being repackaged when Stop
    # comes is kept, like one ended by Stop (round 4, 2026-10-18).
    if not live:
        _check_stop(request)
    moved, already = _move_out(pairs, request, own_names)
    if not moved:
        return RunResult([], tail, skip_reason=(
            f"\"{already[0]}\" is already in this folder, and Teleloadzai never "
            "replaces a file without asking."))
    return RunResult(moved, tail)


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
