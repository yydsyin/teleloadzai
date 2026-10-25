"""Native Windows dialogs.

A web page cannot ask for a real folder path -- the browser only gives file
names, never a full path. So the backend opens the standard Windows dialogs
itself and keeps the path they return.

Windows only, which matches v1 (CLAUDE.md, decision 2).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Characters Windows refuses in a file name. A video title often has some.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# A hidden top-most form is used as the parent, otherwise the dialog can
# open behind the browser window and look like nothing happened.
_PICK_FOLDER = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose the download folder'
$dialog.SelectedPath = '{start}'
$parent = New-Object System.Windows.Forms.Form
$parent.TopMost = $true
if ($dialog.ShowDialog($parent) -eq 'OK') {{ Write-Output $dialog.SelectedPath }}
$parent.Dispose()
"""

# OverwritePrompt is what makes Windows ask "this file exists, replace it?".
_SAVE_FILE = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.InitialDirectory = '{start}'
$dialog.FileName = '{name}'
$dialog.Filter = '{filter}'
$dialog.OverwritePrompt = $true
$dialog.AddExtension = $true
$parent = New-Object System.Windows.Forms.Form
$parent.TopMost = $true
if ($dialog.ShowDialog($parent) -eq 'OK') {{ Write-Output $dialog.FileName }}
$parent.Dispose()
"""

# Same idea as _SAVE_FILE, the other way round: the user points at a file that
# already exists. CheckFileExists stops him returning a name he typed himself.
_OPEN_FILE = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.InitialDirectory = '{start}'
$dialog.Filter = '{filter}'
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
$dialog.Title = '{title}'
$parent = New-Object System.Windows.Forms.Form
$parent.TopMost = $true
if ($dialog.ShowDialog($parent) -eq 'OK') {{ Write-Output $dialog.FileName }}
$parent.Dispose()
"""

_FILTERS = {
    "mp3": "MP3 audio (*.mp3)|*.mp3|All files (*.*)|*.*",
    "mp4": "MP4 video (*.mp4)|*.mp4|All files (*.*)|*.*",
    # A cookie export is almost always literally named cookies.txt.
    "cookies": "Cookie file (*.txt)|*.txt|All files (*.*)|*.*",
    # The Console page's "Save as file" (2026-10-25).
    "txt": "Text file (*.txt)|*.txt|All files (*.*)|*.*",
}


# A title that already ends like a file: "UHDTV TEST 8K VIDEO.mp4" is a real
# YouTube title, and the file came out "….mp4.mp4" -- ".mp3.mp3" too, and
# the mixed ".mp4.mp3" (seen 2026-09-26, through the app's own download and
# "Save as" code). That ending goes before the real one is added. The same
# pattern is handed to yt-dlp (`--replace-in-metadata`), which names the
# file itself when there is no "Save as".
MEDIA_ENDING = r"(?i)\.(?:mp4|m4v|mkv|webm|mov|avi|flv|ts|mp3|m4a|aac|wav|flac|ogg|opus)\s*$"


def without_media_ending(title: str) -> str:
    """'song.mp3' -> 'song'. A title with no such ending is left alone."""
    return re.sub(MEDIA_ENDING, "", title or "")


def safe_filename(name: str, fallback: str = "download") -> str:
    """Turn a video title into something Windows accepts as a file name."""
    clean = _ILLEGAL.sub("_", name or "").strip().rstrip(".")
    clean = re.sub(r"\s+", " ", clean)
    return clean[:150] or fallback


# The name of a file whose title nobody could read (asked by the user
# 2026-09-26). Before, the same case gave "download", "video", "stream" or a
# post number, depending on the road, and the job row showed the raw link.
UNKNOWN = "unknown"


# Windows refuses a path over 260 characters (259 and the closing zero)
# unless long paths are switched on -- off on the user's PC (LongPathsEnabled
# = 0, read 2026-10-24). A TikTok caption of 120 characters in a deep folder
# gave a 278-character path, and the row showed a raw "[Errno 2] No such file
# or directory". Counted in UTF-16 units, Windows' own unit: an emoji is two.
PATH_LIMIT = 259
# Kept free after a name for what the programs add to it. The longest seen
# (2026-10-24): our ".teleloadzai-audio.mp4.cover" (28), N_m3u8DL-RE's
# "<name>\meta_selected.json" (19), yt-dlp's ".tlz<hex>" tag (10) and
# ".part" pieces, a "name (12)" number (5).
NAME_ENDING = 40
# A folder that leaves less than this for a name is refused, in words.
MIN_NAME = 20
TOO_LONG = ("This folder's path is too long for Windows to save a file in it. "
            "Choose a folder with a shorter path in Settings.")


class PathTooLong(ValueError):
    """The folder (or the name chosen in "Save as") leaves no room."""


def units(text: str) -> int:
    """Length as Windows counts it (UTF-16 units)."""
    return len(text.encode("utf-16-le")) // 2


def name_room(folder: Path, ending: int = NAME_ENDING) -> int:
    """How long a name may be in `folder`, in UTF-16 units. Raises
    PathTooLong when it is less than MIN_NAME."""
    room = PATH_LIMIT - units(str(folder)) - 1 - ending
    if room < MIN_NAME:
        raise PathTooLong(TOO_LONG)
    return room


def fit_name(folder: Path, base: str, ending: int = NAME_ENDING) -> str:
    """`base`, cut so that the full path stays under Windows' limit."""
    room = name_room(folder, ending)
    while units(base) > room:
        base = base[:-1]
    return base.rstrip(" .") or UNKNOWN


def free_name(folder: Path, base: str, extension: str) -> str:
    """`base`, or `base (2)`, `base (3)`... -- the first one not in `folder`.

    Two different videos without a title must not share "unknown.mp4": the
    second would be refused as "already there" (decision 24), or replace the
    first. Windows names its copies the same way.
    """
    candidate, number = base, 2
    while (folder / f"{candidate}.{extension}").exists():
        candidate, number = f"{base} ({number})", number + 1
    return candidate


# PowerShell prints in the old Windows code page unless it is told otherwise,
# which destroys every non-Latin character of a path (Chinese, Japanese...).
# And any error stops the script: PowerShell otherwise goes on to the next
# line, ends with code 0 and prints nothing -- a window that failed to open
# was read as Cancel (silent-failure hunt, 2026-10-18: exit 0 without this
# line, exit 1 with it, on the same failing script).
_FORCE_UTF8 = ("$ErrorActionPreference = 'Stop'\n"
               "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n")


class DialogError(RuntimeError):
    """The window could not be opened at all.

    This exists to keep two very different things apart. The user pressing
    Cancel is an answer -- we return None and nothing is wrong. PowerShell
    missing, refusing to start, or timing out is a failure, and until
    2026-09-22 it returned None too: the app behaved exactly as if the user
    had cancelled, and never said a word. That is the case decision 34 names.
    """


def _run_dialog(script: str) -> str | None:
    """The chosen path, or None when the user cancelled.

    Raises ``DialogError`` when the window itself failed.
    """
    if sys.platform != "win32":
        raise DialogError("This window only exists on Windows.")
    try:
        finished = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", _FORCE_UTF8 + script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,            # the user may think for a while
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as problem:
        raise DialogError(
            "The Windows window stayed open for five minutes with no answer, "
            "so it was closed. Try again."
        ) from problem
    except FileNotFoundError as problem:
        raise DialogError(
            "Windows PowerShell could not be started, so the file window "
            "cannot open. Type the path by hand instead."
        ) from problem
    except Exception as problem:
        raise DialogError(f"The Windows window could not open: {problem}") from problem

    chosen = (finished.stdout or "").strip()
    if chosen:
        return chosen
    if finished.returncode != 0:
        # PowerShell ran and failed -- that is not a cancel.
        # The first line says what failed; the ones after it say where
        # ("At line:3 char:1", "+ FullyQualifiedErrorId : TypeNotFound").
        detail = [line.strip() for line in (finished.stderr or "").splitlines()
                  if line.strip() and not line.strip().startswith(("At line", "+"))]
        raise DialogError(
            "The Windows window could not open: "
            + (detail[0][:160] if detail else f"PowerShell stopped with code {finished.returncode}")
        )
    return None                      # the user pressed Cancel


def _quote(text: str) -> str:
    """Escape for a PowerShell single-quoted string."""
    return str(text).replace("'", "''")


def pick_folder(start: Path) -> Path | None:
    """Open the Windows folder dialog. Returns None if the user cancels."""
    chosen = _run_dialog(_PICK_FOLDER.format(start=_quote(start)))
    return Path(chosen) if chosen else None


def save_file(suggested_name: str, mode: str, start: Path) -> Path | None:
    """Open the Windows "Save as" dialog. Returns None if the user cancels.

    Windows asks about replacing an existing file by itself, so when a path
    comes back the user has already agreed to overwrite it.
    """
    extension = mode if mode in ("mp3", "txt") else "mp4"
    base = safe_filename(without_media_ending(suggested_name), fallback="")
    name = f"{base or free_name(start, UNKNOWN, extension)}.{extension}"
    script = _SAVE_FILE.format(
        start=_quote(start),
        name=_quote(name),
        filter=_quote(_FILTERS.get(mode, _FILTERS["mp4"])),
    )
    chosen = _run_dialog(script)
    return Path(chosen) if chosen else None


def open_file(title: str, start: Path, kind: str = "cookies") -> Path | None:
    """Open the Windows "Open file" dialog. None means the user cancelled.

    Raises ``DialogError`` if the window itself could not open.
    """
    script = _OPEN_FILE.format(
        start=_quote(start),
        filter=_quote(_FILTERS.get(kind, _FILTERS["cookies"])),
        title=_quote(title),
    )
    chosen = _run_dialog(script)
    return Path(chosen) if chosen else None
