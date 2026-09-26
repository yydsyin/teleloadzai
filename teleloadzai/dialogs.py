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


# PowerShell prints in the old Windows code page unless it is told otherwise,
# which destroys every non-Latin character of a path (Chinese, Japanese...).
_FORCE_UTF8 = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"


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
        detail = (finished.stderr or "").strip().splitlines()
        raise DialogError(
            "The Windows window could not open: "
            + (detail[-1][:160] if detail else f"PowerShell stopped with code {finished.returncode}")
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
    extension = "mp3" if mode == "mp3" else "mp4"
    name = f"{safe_filename(without_media_ending(suggested_name))}.{extension}"
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
