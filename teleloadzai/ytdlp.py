"""Run yt-dlp: read what is behind a link, or download it.

This is the only place that knows the yt-dlp command line. The MP3 and MP4
options are chosen for quality first: best audio for MP3, best video plus
best audio merged for MP4.

Nothing here assumes a tool is installed (CLAUDE.md, hard rule 3): the
functions raise ``ToolMissing`` and the caller decides what to tell the user.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import children, cookies, explain
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
# The numbers are yt-dlp's RAW ones (bytes, bytes per second, seconds), so
# every tool's row speaks one unit: its own strings said "MiB". Seen
# 2026-09-26: a plain download gives the exact total (Bilibili's picture,
# 15,317,730 bytes); a stream cut in pieces gives only an estimate, "NA" for
# the total -- 16.6 MB after its first piece, 22.4 MB at the end.
_PROGRESS_TEMPLATE = (
    f"download:{_PROGRESS_TAG}\t%(progress._percent_str)s"
    "\t%(progress.speed)s\t%(progress.eta)s"
    "\t%(info.vcodec)s\t%(info.acodec)s"
    "\t%(progress.downloaded_bytes)s\t%(progress.total_bytes)s"
    "\t%(progress.total_bytes_estimate)s"
)

# The steps after the download, as yt-dlp announces them (both seen
# 2026-09-25): joining picture and sound for an MP4, converting for an MP3.
_STEPS = (
    ("[Merger]", "joining picture and sound"),
    ("[ExtractAudio]", "making the MP3"),
)
_FILE_TEMPLATE = f"after_move:{_FILE_TAG}\t%(filepath)s"
# Said before the download starts: is this a live stream? Stop is how a live
# recording ENDS, and Stop's clean-up deleted it as a leftover -- 40 s of a
# YouTube live, 2,097,152 bytes, gone, the row "stopped" (round 6 of the
# hunt, 2026-10-18, with the real yt-dlp on @LofiGirl/live).
_LIVE_TAG = "TLZ_L"
_LIVE_TEMPLATE = f"before_dl:{_LIVE_TAG}\t%(is_live)s"
# The video's title, said as the download starts: several links pasted at
# once are added with no title read first (a read takes 3-10 s a link), and
# their rows showed nothing to recognise (several links, 2026-10-24).
_TITLE_TAG = "TLZ_T"
_TITLE_TEMPLATE = f"before_dl:{_TITLE_TAG}\t%(title)s"
_DESTINATION = "[download] Destination: "
# The files yt-dlp writes AFTER the download, under their final names. A Stop
# during these steps left a half MP3 that the next try called "already
# there" (silent-failure hunt, 2026-10-18). The two lines, as yt-dlp prints
# them: `[ExtractAudio] Destination: <path>`, and `[Merger] Merging formats
# into "<path>"`, which writes `<name>.temp.<ext>` first.
_CONVERTING = "[ExtractAudio] Destination: "
_MERGING = re.compile(r'^\[Merger\] Merging formats into "(.+)"$')
# yt-dlp's repairs after a download ("[FixupM3u8] Fixing MPEG-TS in MP4
# container of "<path>"") write `<name>.temp.<ext>` the same way.
_FIXING = re.compile(r'^\[Fixup\w*\] .* of "(.+)"$')


class ToolMissing(RuntimeError):
    """A needed program is not installed yet."""


class DownloadFailed(RuntimeError):
    """yt-dlp ran but did not succeed."""


@dataclass(frozen=True)
class Progress:
    percent: str            # "  42.1%"
    speed: float = 0.0      # bytes per second, 0 when unknown
    eta: int | None = None  # seconds left, None when unknown
    part: str = ""          # "picture", "sound", or "" when it cannot be told
    done: int = 0           # bytes of this part so far
    total: int = 0          # its size, 0 when unknown
    estimated: bool = False  # the size is yt-dlp's estimate, not the file's


def _number(text: str) -> float | None:
    """yt-dlp's raw value, or None for its "NA"."""
    try:
        return float(text)
    except ValueError:
        return None


def _progress(parts: list[str]) -> Progress:
    """One progress line, split on tabs, as numbers."""
    parts = parts + [""] * (9 - len(parts))
    speed, eta = _number(parts[2]), _number(parts[3])
    done, total, guess = _number(parts[6]), _number(parts[7]), _number(parts[8])
    return Progress(
        percent=parts[1].strip(), speed=speed or 0.0,
        eta=int(eta) if eta is not None else None, part=_part(parts[4], parts[5]),
        done=int(done or 0), total=int(total or guess or 0),
        estimated=not total and bool(guess),
    )


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
    # The tallest picture the site offers, or None. The Quality list shows
    # nothing above it: "Me at the zoo" (240p at most) was offered 1080p
    # (the user's decision, 2026-09-26: a list from each video's real sizes).
    max_height: int | None = None
    # Every picture height the site really has, up to max_height. A smaller
    # choice is offered only if it exists: TikTok's "480p" gave 576p.
    heights: tuple[int, ...] = ()


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
    """Run yt-dlp for a title read: tied to the app, and ended whole.

    Started loose, a read still running when the app closed outlived it and
    wrote its cookie jar back AFTER "Forget when I close" had wiped them; a
    read that timed out ended only the yt-dlp.exe launcher, and the real
    yt-dlp went on (round 5 of the hunt, 2026-10-18). The timeout also
    reached the card as Python's own words, the whole command line with it.
    """
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    children.bind(process)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        children.stop_tree(process)
        process.communicate()
        raise DownloadFailed(f"yt-dlp did not answer within {int(timeout)} seconds.")
    return subprocess.CompletedProcess(command, process.returncode, out, err)


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
        # The same as the download, so "N items" means what the download
        # gets: a YouTube video opened from a list is one video, while an
        # Instagram post with 3 videos stays 3 -- yt-dlp ignores this there
        # and downloads all 3 (seen 2026-09-27, "Downloading 3 items of 3").
        "--no-playlist",
        # yt-dlp writes in the code page Windows gives old programs. On this
        # PC that is GBK (Chinese) while Windows itself speaks French, so a
        # French error came through as "n¡¯a pu ¨ºtre"
        # and we showed "n??a pu ??tre". Proven 2026-09-23: PYTHONUTF8 and
        # PYTHONIOENCODING change nothing; yt-dlp's own option does.
        "--encoding", "utf-8",
        "--no-warnings",
        "--no-colors",
        # The download's own MP4 rule: the answer's "height" is then what
        # "Best" will really give (see _MP4_BEST).
        "-f", _MP4_BEST,
        *_cookie_arguments(cookie_file),
        url,
    ]
    finished = _run(command, timeout)
    if finished.returncode != 0:
        raise _tool_said(finished.stderr)

    data = json.loads(finished.stdout)
    entries = data.get("entries")
    is_playlist = isinstance(entries, list)
    # Heights of the formats that carry a picture (seen 2026-09-26: YouTube
    # "Me at the zoo" 144/240, TikTok 576/720, Bilibili up to 1080).
    heights = sorted({f.get("height") for f in data.get("formats") or []
                      if isinstance(f.get("height"), int) and f.get("vcodec") != "none"})
    # What "Best" delivers: the height of the format the rule picked. Not the
    # tallest listed -- TikTok lists 720p, the rule gives 576p.
    picked = data.get("height") if isinstance(data.get("height"), int) else None

    return MediaInfo(
        title=data.get("title") or "(no title)",
        uploader=data.get("uploader") or data.get("channel") or "",
        duration=data.get("duration"),
        thumbnail=data.get("thumbnail"),
        extractor=data.get("extractor_key") or data.get("extractor") or "",
        webpage_url=data.get("webpage_url") or url,
        is_playlist=is_playlist,
        entries=len(entries) if is_playlist else 1,
        max_height=picked,
        heights=tuple(h for h in heights if picked is None or h <= picked),
    )


# What the quality dropdown offers. "best" is always first and is the default.
AUDIO_QUALITIES = ("best", "320", "192", "128")     # kbps
VIDEO_QUALITIES = ("best", "1080", "720", "480", "360")   # max height


# The MP4 rule for "Best" -- shared by the download AND the title read, so
# the Quality list names what the download will really pick. They differed:
# TikTok lists a 720p version, this rule (a real .mp4 first) picks 576p, and
# the list said "Best (720p)" over a 1024x576 file; "480p" gave the same
# 576p file (both measured 2026-09-27, ffprobe, 18,277,961 bytes).
_REAL = "[ext!=jpg][ext!=png][ext!=webp][ext!=mhtml]"
_MP4_BEST = (f"bestvideo[ext=mp4]{_REAL}+bestaudio[ext=m4a]/bestvideo{_REAL}+bestaudio/"
             f"best[ext=mp4]{_REAL}/best{_REAL}")


# In MP3 mode, yt-dlp first fetches a step file named like the final one,
# "Title.mp4", then makes "Title.mp3" from it and deletes it. When the user
# already had "Title.mp4" -- the MP4 of the same video -- yt-dlp took HIS file
# as the step, and deleted it; the row said "already there" (round 9 of the
# hunt, real yt-dlp: clip.mp4 47,317 B, gone after the MP3 run). So the run's
# names carry a tag of their own, ".tlz<6 hex>", removed once the MP3 exists.
_TAG = re.compile(r"\.tlz[0-9a-f]{6}")


def untagged(name: str, tag: str = "") -> str:
    """A file name without this run's MP3 tag -- the LAST one, which is the
    run's: a title of its own containing ".tlz" + 6 hex keeps it (round 10)."""
    if tag:
        head, found, rest = name.rpartition(tag)
        return head + rest if found else name
    found = list(_TAG.finditer(name))
    return name[:found[-1].start()] + name[found[-1].end():] if found else name


def _output_arguments(
    mode: str, out_dir: Path, quality: str = "best", out_path: Path | None = None,
    tag: str = "",
) -> list[str]:
    """Build the yt-dlp options for the chosen format and quality.

    ``out_path`` is an exact file the user picked in the "Save as" window.
    Its extension is dropped and left to yt-dlp, so extracting audio cannot
    produce ``name.mp3.mp3``.
    """
    # A post of several items (an Instagram post of 3 videos) is downloaded
    # whole, even with --no-playlist: each item gets its number, " 1", " 2"…,
    # and a single video none. Without it the 3 videos shared ONE name: with
    # "Save as" each overwrote the last (the user got video 3), without it
    # videos 2 and 3 were skipped as already there (he got video 1) -- and
    # the row said "done" (seen 2026-09-27).
    number = "%(playlist_index& {}|)s"
    if out_path is not None:
        # The user's name is text, not a template: a "%" in it is doubled.
        target = str(out_path.with_suffix("")).replace("%", "%%") + number + tag + ".%(ext)s"
        tidy: list[str] = []
    else:
        folder = str(out_dir).replace("%", "%%")
        target = str(Path(folder) / f"%(title)s{number}{tag}.%(ext)s")
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
            selector = _MP4_BEST
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


def _only_chosen_name(out_path: Path | None) -> bool:
    """May this run replace files? Only the one Windows asked about.

    "Save as" asked about "name.mp4"; the items of a post are written as
    "name 1.mp4", "name 2.mp4"…, which nobody asked about. yt-dlp's
    --force-overwrites is all or nothing, so it is given only when no such
    numbered file is there: then it can only ever replace the chosen one.
    Otherwise nothing is replaced and the row says "already there", with
    "Download again" (decision 24).
    """
    if out_path is None:
        return False
    stem = out_path.with_suffix("").name
    numbered = re.compile(re.escape(stem) + r" \d+\.[^.]+", re.IGNORECASE)
    try:
        return not any(numbered.fullmatch(p.name) for p in out_path.parent.iterdir())
    except OSError:
        return True             # no folder yet: nothing there to replace


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
    on_writing: Callable[[Path], None] | None = None,
    on_live: Callable[[], None] | None = None,
    on_title: Callable[[str], None] | None = None,
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
    tag = f".tlz{uuid.uuid4().hex[:6]}" if mode == "mp3" else ""

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
        "--print", _LIVE_TEMPLATE,
        "--print", _TITLE_TEMPLATE,
        # `--print` turns quiet mode on, and quiet mode hides "[Merger]" and
        # "[ExtractAudio]" -- the only signs of the step after the download.
        # Probed on this exact command, 2026-09-25: steps seen [] without
        # this flag, ["joining picture and sound"] with it, and the final
        # file still reported either way.
        "--no-quiet",
        *(["--yes-playlist"] if playlist else ["--no-playlist"]),
        *(["--force-overwrites"] if (force or _only_chosen_name(out_path)) else []),
        *_cookie_arguments(cookie_file),
        *_ffmpeg_arguments(),
        *_output_arguments(mode, out_dir, quality, out_path, tag),
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
                on_progress(_progress(line.split("\t")))
        elif line.startswith(_LIVE_TAG):
            if on_live and line.split("\t", 1)[-1].strip() == "True":
                on_live()
        elif line.startswith(_TITLE_TAG):
            title = line.split("\t", 1)[-1].strip()
            if on_title and title and title != "NA":
                on_title(title)
        elif line.startswith(_FILE_TAG):
            files.append(Path(line.split("\t", 1)[1].strip()))
        elif line.strip():
            # "[download] Destination: C:\...\name.f137.mp4" -- the one place
            # yt-dlp names the files it is writing. A stopped job uses these,
            # and only these, to remove what it leaves half-written.
            if on_destination and line.startswith(_DESTINATION):
                on_destination(Path(line[len(_DESTINATION):].strip()))
                # An MP3 run's download is only its step file, tagged as
                # ours: after a Stop it goes too, finished or not.
                if tag and on_writing:
                    on_writing(Path(line[len(_DESTINATION):].strip()))
            if on_writing:
                merging = _MERGING.match(line.strip()) or _FIXING.match(line.strip())
                if merging:
                    whole = Path(merging.group(1))
                    on_writing(whole.with_name(f"{whole.stem}.temp{whole.suffix}"))
                elif line.startswith(_CONVERTING):
                    on_writing(Path(line[len(_CONVERTING):].strip()))
            if on_step:
                for prefix, step in _STEPS:
                    if line.startswith(prefix):
                        on_step(step)
            tail.append(line)
            del tail[:-40]          # keep only the last 40 lines

    if process.wait() != 0:
        problem = _tool_said("\n".join(tail))
        # An MP3 run that failed on its 2nd item had finished the others
        # under tagged names: never renamed, never said, one more set with
        # each Retry (round 10). They get their names, and the row says them.
        if tag and files:
            try:
                done = _untag(files, tail, out_path, force, tag)
                problem.saved = [f for f in done.files if f not in done.skipped]
            except DownloadFailed:
                pass
        raise problem
    # Ended well and named no file: a playlist with no video in it, an empty
    # channel tab. The row said "done" with nothing behind it (silent-failure
    # hunt, 2026-10-18). Our sentence, so it is not marked as yt-dlp's words.
    if not files:
        last = next((l.strip() for l in reversed(tail) if l.strip()), "")
        raise DownloadFailed("yt-dlp finished without downloading anything."
                             + (f" Its last line: {cookies.redact(last[:200])}" if last else ""))

    if tag:
        return _untag(files, tail, out_path, force, tag)

    # yt-dlp leaves an existing file alone and says nothing useful about it.
    # The only reliable proof is the file's own date.
    skipped = [f for f in files if f.exists() and f.stat().st_mtime < started_at]
    return DownloadResult(files, tail, skipped)


def _untag(files: list[Path], tail: list[str], out_path: Path | None,
           force: bool, tag: str) -> DownloadResult:
    """Give an MP3 run's files their real names (decision 24).

    Replaced only when the user asked: "Download again", or the very name
    Windows asked about in "Save as". Otherwise his file of that name stays,
    ours goes, and the row says "already there".
    """
    final: list[Path] = []
    already: list[Path] = []
    for path in files:
        if tag not in path.name or not path.is_file():
            final.append(path)
            continue
        target = path.with_name(untagged(path.name, tag))
        asked = out_path is not None and target.name == out_path.with_suffix(".mp3").name
        try:
            if force or asked:
                os.replace(path, target)
            else:
                os.rename(path, target)         # refuses a name that is taken
        except FileExistsError:
            try:
                path.unlink()
            except OSError:
                pass            # held a moment (an antivirus): his file is what counts
            already.append(target)
        except OSError as problem:
            raise DownloadFailed(
                f"\"{target.name}\" was made, but could not be given its name: "
                f"{problem.strerror or problem}. It is in the folder as \"{path.name}\".")
        final.append(target)
    return DownloadResult(final, tail, already)


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
