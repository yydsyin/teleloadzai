"""The Console's command box (decision 42, model A, 2026-11-15).

The user picks one of Teleloadzai's own tools and types ANY of its arguments
-- not only the guide's. What keeps it safe is what it is NOT:

- **no shell**: the arguments are split here and the tool is started
  directly (a list, never a string), so `|`, `&&` or `>` can start nothing
  else -- they are refused in words, since the tool would only misread them;
- **only an installed tool of ours**, from the list below;
- one command at a time, **bound to the app** (`children`): it dies with it;
- its words go to the Console through `console.add`, **washed** (37);
- cookies are **never added** for the user: a command uses them only if the
  user types the option and a file himself.

It runs in the download folder, where a file it writes is easy to find.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from . import children, console, tools
from .runners import _NO_WINDOW, _child_environment, _encoding

# tool id -> (shown name, how it prints). TikTokDownloader and KS-Downloader
# are left out: they are servers with a menu, not commands (`toolservers`).
# "oem": yt-dlp.exe writes in the old Windows code page whatever
# PYTHONIOENCODING says (proven 2026-09-23, `ytdlp.probe`); N_m3u8DL-RE the
# same (`runners.RECIPES`). Python modules are told UTF-8.
RUNNABLE: dict[str, tuple[str, str]] = {
    "yt-dlp": ("yt-dlp", "oem"),
    "ffmpeg": ("FFmpeg", "utf-8"),
    "ffprobe": ("FFprobe", "utf-8"),
    "gallery-dl": ("gallery-dl", "utf-8"),
    "streamlink": ("Streamlink", "utf-8"),
    "n-m3u8dl-re": ("N_m3u8DL-RE", "oem"),
    "yutto": ("yutto", "utf-8"),
    "xhs-downloader": ("XHS-Downloader", "utf-8"),
}

# The guide: examples only (decision 42), each one run and seen working
# through `run` before it was listed (decision 40) -- see docs/HISTORY.md,
# 2026-11-15. <link> and <file> are for the user to replace; the page selects
# the first one when an example is put in the box.
GUIDE: dict[str, list[tuple[str, str]]] = {
    "yt-dlp": [
        ("-F <link>", "List every quality the video has"),
        ('-f "bv*[height<=720]+ba" <link>', "The best video up to 720p, with its sound"),
        ("-x --audio-format mp3 <link>", "The sound only, as an MP3"),
        ("--list-subs <link>", "List the subtitles"),
        ("--write-subs --sub-langs en --skip-download <link>", "Only the English subtitles, no video"),
        ("--version", "Which version is installed"),
    ],
    "ffmpeg": [
        ('-i "<file>" -vn -b:a 192k "sound.mp3"', "Take the sound out of a video, as an MP3"),
        ('-i "<file>" -ss 00:00:10 -to 00:00:20 -c copy "part.mp4"', "Cut a part (seconds 10 to 20), no re-encoding"),
        ("-version", "Which version is installed"),
    ],
    "ffprobe": [
        ('-hide_banner "<file>"', "What a file holds: length, picture, sound"),
        ('-v error -show_entries format=duration -of csv=p=0 "<file>"', "Its length in seconds"),
    ],
    "gallery-dl": [
        ("-g <link>", "List the post's files, download nothing"),
        ("<link>", "Download the post's files"),
        ("--version", "Which version is installed"),
    ],
    "streamlink": [
        ("<link>", "List a live stream's qualities"),
        ('<link> best -o "live.ts" --hls-duration 00:00:30', "Record 30 seconds of it in the best quality"),
        ("--version", "Which version is installed"),
    ],
    "n-m3u8dl-re": [
        # Without --auto-select it asks which stream, and with nobody to
        # answer it crashes ("Cannot see if a key has been pressed", seen).
        ("<link> --auto-select --save-name video", "Download a stream link (.m3u8), best quality"),
        ("--version", "Which version is installed"),
    ],
    "yutto": [
        ("<link>", "Download a Bilibili video (480p without a log-in)"),
        ("<link> --audio-only", "The sound only"),
    ],
}

# Shell words a command line would give a meaning to; here they would reach
# the tool as plain text. Said instead of passed on.
_SHELL_WORDS = {"|", "||", "&", "&&", ">", ">>", "<", "2>", "2>&1", ";"}

LINE = "console"        # the job id of these lines in the Console

_lock = threading.Lock()
_process: subprocess.Popen | None = None
_tool = ""


class CommandError(Exception):
    """Said to the user as it is: why the command did not start."""


def split(text: str) -> list[str]:
    """Windows-style: spaces separate, double quotes group, a backslash is
    just a character (paths like C:\\Users stay whole)."""
    words: list[str] = []
    current: list[str] = []
    quoted = started = False
    for char in text:
        if char == '"':
            quoted, started = not quoted, True
        elif char.isspace() and not quoted:
            if started:
                words.append("".join(current))
                current, started = [], False
        else:
            current.append(char)
            started = True
    if quoted:
        raise CommandError("A quote (\") is not closed.")
    if started:
        words.append("".join(current))
    return words


def _program(tool_id: str) -> list[str]:
    """The start of the command: the tool's own program, or `python -m`."""
    if tool_id == "ffprobe":
        ffmpeg = tools.installed_path("ffmpeg")
        probe = ffmpeg.with_name("ffprobe.exe") if ffmpeg else None
        if probe is None or not probe.is_file():
            raise CommandError("FFprobe is not installed. It comes with FFmpeg: install FFmpeg on Programs.")
        return [str(probe)]
    spec = tools.spec(tool_id)
    found = tools.installed_path(tool_id)
    if spec is None or found is None:
        raise CommandError(f"{RUNNABLE[tool_id][0]} is not installed. Install it on Programs first.")
    if spec.module:
        return [sys.executable, "-m", spec.module]
    return [str(found)]


def available() -> list[dict]:
    """The tools the box can run now, for its list."""
    answer = []
    for tool_id, (name, _) in RUNNABLE.items():
        try:
            _program(tool_id)
            answer.append({"id": tool_id, "name": name,
                           "guide": [{"args": a, "what": w} for a, w in GUIDE.get(tool_id, [])]})
        except CommandError:
            continue
    return answer


def busy(tool_id: str) -> bool:
    """A command of this tool runs now: its update waits (decision 19)."""
    with _lock:
        running = _process is not None and _process.poll() is None
        return running and (_tool == tool_id or (_tool == "ffprobe" and tool_id == "ffmpeg"))


def state() -> dict:
    with _lock:
        running = _process is not None and _process.poll() is None
        return {"running": running, "tool": _tool if running else ""}


def run(tool_id: str, text: str, folder: Path) -> None:
    """Start one command; its lines reach the Console as they come."""
    global _process, _tool
    if tool_id not in RUNNABLE:
        raise CommandError("The Console runs only Teleloadzai's own programs.")
    words = split(text)
    head = _program(tool_id)
    # "yt-dlp -F <link>" pasted from a web page: the program's name is not
    # one of its arguments.
    if words and words[0].lower().removesuffix(".exe") in {tool_id, RUNNABLE[tool_id][0].lower()}:
        words = words[1:]
    shell = [w for w in words if w in _SHELL_WORDS]
    if shell:
        raise CommandError(f"The Console runs one program, with no shell: “{shell[0]}” is not supported.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as problem:
        raise CommandError(f"The download folder cannot be used: {problem.strerror}.") from problem

    shown = RUNNABLE[tool_id][0]
    with _lock:
        if _process is not None and _process.poll() is None:
            raise CommandError("A command is already running. Stop it first.")
        console.add(LINE, f"> {shown} {subprocess.list2cmdline(words)}".rstrip(), "head")
        module = (tools.spec(tool_id).module if tools.spec(tool_id) else "") or ""
        try:
            _process = subprocess.Popen(
                head + words,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,        # nothing can wait for a typed answer
                text=True, encoding=_encoding(RUNNABLE[tool_id][1]), errors="replace", bufsize=1,
                env=_child_environment(module), cwd=str(folder), creationflags=_NO_WINDOW)
        except OSError as problem:
            _process = None
            console.add(LINE, f"{shown} could not start: {problem.strerror or problem}", "err")
            raise CommandError(f"{shown} could not start: {problem.strerror or problem}.") from problem
        _tool = tool_id
        process = _process
    children.bind(process)
    threading.Thread(target=_read, args=(process, shown), daemon=True).start()


def _read(process: subprocess.Popen, shown: str) -> None:
    global _process
    try:
        for line in process.stdout:
            console.add(LINE, line, "out")
    except (OSError, ValueError):
        pass                            # the pipe closed: stopped
    code = process.wait()
    if code >= 2 ** 31:
        code -= 2 ** 32             # Windows gives FFmpeg's -2 as 4294967294
    with _lock:
        stopped = getattr(process, "_stopped_by_user", False)
        if _process is process:
            _process = None
    if stopped:
        console.add(LINE, f"{shown}: stopped.", "end")
    elif code == 0:
        console.add(LINE, f"{shown}: done.", "end")
    else:
        console.add(LINE, f"{shown} ended with code {code}.", "err")


def stop() -> bool:
    """Stop the running command and everything it started."""
    with _lock:
        process = _process
    if process is None or process.poll() is not None:
        return False
    process._stopped_by_user = True
    children.stop_tree(process)
    return True
