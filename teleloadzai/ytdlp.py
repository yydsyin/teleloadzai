"""Run yt-dlp: read what is behind a link, or download it.

This is the only place that knows the yt-dlp command line. The MP3 and MP4
options are chosen for quality first: best audio for MP3, best video plus
best audio merged for MP4.

Nothing here assumes a tool is installed (CLAUDE.md, hard rule 3): the
functions raise ``ToolMissing`` and the caller decides what to tell the user.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cookies, explain
from .dialogs import MEDIA_ENDING
from .paths import BIN_DIR, make_folder

# Keeps the black console window from flashing when the GUI runs a tool.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# yt-dlp prints one line per progress update, in our own format so that
# parsing never depends on the human-readable output.
_PROGRESS_TAG = "TLZ_P"
_FILE_TAG = "TLZ_F"
# The two codecs say WHICH part is coming down. An MP4 is fetched as two
# files, picture then sound, each counting from 0 to 100% -- the bar went
# from 86% back to 41% with nothing to say why (seen 2026-09-25). Probed the
# same day: the picture part reports `vcodec=av01 acodec=none`, the sound
# part `vcodec=none acodec=opus`.
_PROGRESS_TEMPLATE = (
    f"download:{_PROGRESS_TAG}\t%(progress._percent_str)s"
    "\t%(progress._speed_str)s\t%(progress._eta_str)s"
    "\t%(info.vcodec)s\t%(info.acodec)s"
)

# The steps after the download, as yt-dlp announces them (both seen
# 2026-09-25): joining picture and sound for an MP4, converting for an MP3.
_STEPS = (
    ("[Merger]", "joining picture and sound"),
    ("[ExtractAudio]", "making the MP3"),
)
_FILE_TEMPLATE = f"after_move:{_FILE_TAG}\t%(filepath)s"
_DESTINATION = "[download] Destination: "


class ToolMissing(RuntimeError):
    """A needed program is not installed yet."""


class DownloadFailed(RuntimeError):
    """yt-dlp ran but did not succeed."""


@dataclass(frozen=True)
class Progress:
    percent: str      # "  42.1%"
    speed: str        # "3.20MiB/s"
    eta: str          # "00:12"
    part: str = ""    # "picture", "sound", or "" when it cannot be told


def _part(vcodec: str, acodec: str) -> str:
    """Which part a download is, from its two codecs -- or "" if unsure.

    Named only when exactly one side is "none". A file carrying both, or a
    codec yt-dlp does not know ("NA"), gets no name: never a guess.
    """
    v, a = vcodec.strip().lower(), acodec.strip().lower()
    unknown = ("", "na", "n/a")
    if v in unknown or a in unknown:
        return ""
    if a == "none" and v != "none":
        return "picture"
    if v == "none" and a != "none":
        return "sound"
    return ""


@dataclass(frozen=True)
class MediaInfo:
    title: str
    uploader: str
    duration: int | None       # seconds
    thumbnail: str | None
    extractor: str
    webpage_url: str
    is_playlist: bool
    entries: int               # 1 for a single video


@dataclass(frozen=True)
class DownloadResult:
    files: list[Path]
    log_tail: list[str]
    # Files that were already there and that yt-dlp did NOT rewrite. Without
    # this we would report a success that never happened (bug of 2026-09-20,
    # found again on 2026-09-21 on the path where the user is not asked).
    skipped: list[Path] = field(default_factory=list)

    @property
    def nothing_downloaded(self) -> bool:
        return bool(self.skipped) and not (set(self.files) - set(self.skipped))


def find_tool(name: str) -> Path | None:
    """Look in our own `bin/` first, then in the system PATH."""
    for candidate in (BIN_DIR / f"{name}.exe", BIN_DIR / name):
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None


def require_ytdlp() -> Path:
    tool = find_tool("yt-dlp")
    if tool is None:
        raise ToolMissing("yt-dlp is not installed")
    return tool


def _ffmpeg_arguments() -> list[str]:
    """Tell yt-dlp where ffmpeg is, when it is not beside it."""
    ffmpeg = find_tool("ffmpeg")
    if ffmpeg is None:
        raise ToolMissing("ffmpeg is not installed")
    return ["--ffmpeg-location", str(ffmpeg.parent)]


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def _cookie_arguments(cookie_file: Path | None) -> list[str]:
    """``--cookies FILE``, or nothing at all.

    The path is always the copy Teleloadzai keeps, never the file the user
    picked: yt-dlp writes the cookie jar back into whatever file it is given
    (measured 2026-09-22 -- a 2-line probe file came back with 12 lines), and
    growing somebody's own export behind his back is not ours to do.
    """
    if cookie_file is None:
        return []
    return ["--cookies", str(cookie_file)]


def probe(url: str, timeout: float = 60.0, cookie_file: Path | None = None) -> MediaInfo:
    """Read the title, duration and thumbnail of a link. Downloads nothing.

    The cookies matter here too: without them a private post has no title to
    read, and the user would see "(no title)" with no idea why.
    """
    tool = require_ytdlp()
    command = [
        str(tool),
        "--dump-single-json",
        "--flat-playlist",       # do not open every video of a playlist
        # yt-dlp writes in the code page Windows gives old programs. On this
        # PC that is GBK (Chinese) while Windows itself speaks French, so a
        # French error came through as "n¡¯a pu ¨ºtre"
        # and we showed "n??a pu ??tre". Proven 2026-09-23: PYTHONUTF8 and
        # PYTHONIOENCODING change nothing; yt-dlp's own option does.
        "--encoding", "utf-8",
        "--no-warnings",
        "--no-colors",
        *_cookie_arguments(cookie_file),
        url,
    ]
    finished = _run(command, timeout)
    if finished.returncode != 0:
        raise _tool_said(finished.stderr)

    data = json.loads(finished.stdout)
    entries = data.get("entries")
    is_playlist = isinstance(entries, list)

    return MediaInfo(
        title=data.get("title") or "(no title)",
        uploader=data.get("uploader") or data.get("channel") or "",
        duration=data.get("duration"),
        thumbnail=data.get("thumbnail"),
        extractor=data.get("extractor_key") or data.get("extractor") or "",
        webpage_url=data.get("webpage_url") or url,
        is_playlist=is_playlist,
        entries=len(entries) if is_playlist else 1,
    )


# What the quality dropdown offers. "best" is always first and is the default.
AUDIO_QUALITIES = ("best", "320", "192", "128")     # kbps
VIDEO_QUALITIES = ("best", "1080", "720", "480", "360")   # max height


def _output_arguments(
    mode: str, out_dir: Path, quality: str = "best", out_path: Path | None = None
) -> list[str]:
    """Build the yt-dlp options for the chosen format and quality.

    ``out_path`` is an exact file the user picked in the "Save as" window.
    Its extension is dropped and left to yt-dlp, so extracting audio cannot
    produce ``name.mp3.mp3``.
    """
    if out_path is not None:
        target = str(out_path.with_suffix("")) + ".%(ext)s"
        tidy: list[str] = []
    else:
        target = str(out_dir / "%(title)s.%(ext)s")
        # yt-dlp names the file from the title: "… VIDEO.mp4" came out
        # "… VIDEO.mp4.mp4". Its own option drops that ending first.
        tidy = ["--replace-in-metadata", "title", MEDIA_ENDING, ""]

    if mode == "mp3":
        # yt-dlp: 0 = best variable bitrate, or a fixed rate like "192K".
        audio_quality = "0" if quality == "best" else f"{quality}K"
        return [
            *tidy,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", audio_quality,
            "-o", target,
        ]

    if mode == "mp4":
        # Never a picture. Weibo lists a 320x180 preview strip (`scrubber_hd`,
        # ext jpg, no codec) among its videos; asked for 360p, the old rule
        # downloaded that .jpg and the job said "done" (seen 2026-09-26).
        # Filtered by extension, not by codec: Archive.org's real videos
        # have no known codec either.
        real = "[ext!=jpg][ext!=png][ext!=webp][ext!=mhtml]"
        # "MP4" means an .mp4 file. Picture + sound fetched apart are joined
        # into one (--merge-output-format); but a site that serves READY
        # files (Archive.org) was answered with whatever file fit the height:
        # MP4 at 360p gave Cops1922's 300p .ogv (seen 2026-09-26). A real
        # .mp4 now comes first, at the closest height; another format only
        # when the site has no .mp4 at all.
        if quality == "best":
            selector = (f"bestvideo[ext=mp4]{real}+bestaudio[ext=m4a]/bestvideo{real}+bestaudio/"
                        f"best[ext=mp4]{real}/best{real}")
            sort = []
        else:
            # The best not taller than the chosen height; when there is none,
            # `-S res:N` makes the last "best" the CLOSEST above -- Weibo at
            # 360 now gives its 720p video, not its 1080p. Measured the same
            # day: YouTube picks exactly the formats it picked before.
            selector = (
                f"bestvideo[height<={quality}][ext=mp4]{real}+bestaudio[ext=m4a]/"
                f"bestvideo[height<={quality}]{real}+bestaudio/"
                f"best[height<={quality}][ext=mp4]{real}/best[ext=mp4]{real}/"
                f"best[height<={quality}]{real}/best{real}"
            )
            sort = ["-S", f"res:{quality}"]
        return [
            *tidy,
            "-f", selector,
            *sort,
            "--merge-output-format", "mp4",
            "-o", target,
        ]

    raise ValueError(f"unknown mode: {mode!r}")


def download(
    url: str,
    mode: str,
    out_dir: Path,
    on_progress: Callable[[Progress], None] | None = None,
    playlist: bool = False,
    quality: str = "best",
    on_start: Callable[[subprocess.Popen], None] | None = None,
    out_path: Path | None = None,
    force: bool = False,
    cookie_file: Path | None = None,
    on_step: Callable[[str], None] | None = None,
    on_destination: Callable[[Path], None] | None = None,
) -> DownloadResult:
    """Download one link as MP3 or MP4, reporting progress line by line.

    ``on_start`` receives the running process, so the caller can stop it
    when the user cancels the job.

    ``out_path`` is the exact file chosen in the "Save as" window. Windows
    already asked the user about replacing it, so we force the overwrite --
    otherwise yt-dlp would silently skip and we would report a success that
    did not happen.
    """
    tool = require_ytdlp()
    make_folder(out_dir)

    command = [
        str(tool),
        "--newline",
        "--no-colors",
        # yt-dlp writes in the code page Windows gives old programs. On this
        # PC that is GBK (Chinese) while Windows itself speaks French, so a
        # French error came through as "n¡¯a pu ¨ºtre"
        # and we showed "n??a pu ??tre". Proven 2026-09-23: PYTHONUTF8 and
        # PYTHONIOENCODING change nothing; yt-dlp's own option does.
        "--encoding", "utf-8",
        "--no-warnings",
        "--progress", "--progress-template", _PROGRESS_TEMPLATE,
        "--print", _FILE_TEMPLATE,
        # `--print` turns quiet mode on, and quiet mode hides "[Merger]" and
        # "[ExtractAudio]" -- the only signs of the step after the download.
        # Probed on this exact command, 2026-09-25: steps seen [] without
        # this flag, ["joining picture and sound"] with it, and the final
        # file still reported either way.
        "--no-quiet",
        *(["--yes-playlist"] if playlist else ["--no-playlist"]),
        *(["--force-overwrites"] if (out_path is not None or force) else []),
        *_cookie_arguments(cookie_file),
        *_ffmpeg_arguments(),
        *_output_arguments(mode, out_dir, quality, out_path),
        url,
    ]

    files: list[Path] = []
    tail: list[str] = []
    # Anything whose date is older than this was NOT written by this run.
    started_at = time.time() - 2      # a little slack for clock rounding

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_NO_WINDOW,
    )
    if on_start:
        on_start(process)

    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip("\n")
        if line.startswith(_PROGRESS_TAG):
            if on_progress:
                parts = line.split("\t")
                while len(parts) < 6:
                    parts.append("")
                on_progress(Progress(parts[1].strip(), parts[2].strip(), parts[3].strip(),
                                     _part(parts[4], parts[5])))
        elif line.startswith(_FILE_TAG):
            files.append(Path(line.split("\t", 1)[1].strip()))
        elif line.strip():
            # "[download] Destination: C:\...\name.f137.mp4" -- the one place
            # yt-dlp names the files it is writing. A stopped job uses these,
            # and only these, to remove what it leaves half-written.
            if on_destination and line.startswith(_DESTINATION):
                on_destination(Path(line[len(_DESTINATION):].strip()))
            if on_step:
                for prefix, step in _STEPS:
                    if line.startswith(prefix):
                        on_step(step)
            tail.append(line)
            del tail[:-40]          # keep only the last 40 lines

    if process.wait() != 0:
        raise _tool_said("\n".join(tail))

    # yt-dlp leaves an existing file alone and says nothing useful about it.
    # The only reliable proof is the file's own date.
    skipped = [f for f in files if f.exists() and f.stat().st_mtime < started_at]
    return DownloadResult(files, tail, skipped)


def _tool_said(text: str) -> DownloadFailed:
    """yt-dlp's own words as an error, marked as such (decision 38).

    When it printed nothing, the text is our "unknown error" and is NOT
    marked: the page must not present our placeholder as yt-dlp's words.
    """
    said = _short_error(text)
    problem = DownloadFailed(said)
    return explain.from_tool(problem) if (text or "").strip() else problem


def _short_error(text: str) -> str:
    """Keep the useful line of a yt-dlp error, not the whole dump.

    Cleaned before it leaves: this line goes on the screen, and a failure that
    happens *because of* a cookie is exactly the one that may quote it. Hard
    rule 1 and decision 34 only hold together if the words are washed first.
    """
    for line in reversed((text or "").splitlines()):
        clean = line.strip()
        if clean.startswith("ERROR:"):
            return cookies.redact(clean)
    body = (text or "").strip()
    return cookies.redact(body.splitlines()[-1]) if body else "unknown error"
