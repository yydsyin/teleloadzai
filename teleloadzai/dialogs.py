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

_FILTERS = {
    "mp3": "MP3 audio (*.mp3)|*.mp3|All files (*.*)|*.*",
    "mp4": "MP4 video (*.mp4)|*.mp4|All files (*.*)|*.*",
}


def safe_filename(name: str, fallback: str = "download") -> str:
    """Turn a video title into something Windows accepts as a file name."""
    clean = _ILLEGAL.sub("_", name or "").strip().rstrip(".")
    clean = re.sub(r"\s+", " ", clean)
    return clean[:150] or fallback


# PowerShell prints in the old Windows code page unless it is told otherwise,
# which destroys every non-Latin character of a path (Chinese, Japanese...).
_FORCE_UTF8 = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"


def _run_dialog(script: str) -> str | None:
    if sys.platform != "win32":
        return None
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
    except Exception:
        return None
    chosen = (finished.stdout or "").strip()
    return chosen or None


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
    name = f"{safe_filename(suggested_name)}.{extension}"
    script = _SAVE_FILE.format(
        start=_quote(start),
        name=_quote(name),
        filter=_quote(_FILTERS.get(mode, _FILTERS["mp4"])),
    )
    chosen = _run_dialog(script)
    return Path(chosen) if chosen else None
