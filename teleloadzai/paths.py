"""Where Teleloadzai keeps its files.

Everything stays next to the app, so the portable `.zip` works from a USB key
(CLAUDE.md, decision 16). Nothing is written into Windows system folders.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    """The folder that holds `bin/` and `data/`."""
    if getattr(sys, "frozen", False):        # packaged with PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _root()
BIN_DIR = ROOT / "bin"            # the download tools live here
DATA_DIR = ROOT / "data"          # settings + the "last update check" notes
WEB_DIR = Path(__file__).resolve().parent / "web"

# Every user keeps his own Downloads folder. A personal folder is a setting,
# not a default, so the app never writes outside a place the user expects.
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads"


def ensure_dirs() -> None:
    for folder in (BIN_DIR, DATA_DIR):
        folder.mkdir(parents=True, exist_ok=True)


THIS_IS_THE_CHECK = False      # set by dev/quality_check.py once it holds its lock


def quality_check_running() -> bool:
    """Teleloadzai's own daily check (`dev/quality_check.py`) is running now.

    It holds a lock on `data/quality-check/running.lock` while it lives
    (Windows frees it when the process ends, even after a crash). While it
    runs it uses the same programs and TikTokDownloader's / KS-Downloader's
    ports, and the app named only "TikTokDownloader.exe" as the holder
    (round 16 of the hunt). Asked only when something is already refused:
    the lock is taken for an instant and given back at once.
    """
    # Asked INSIDE the check (its own TikTokDownloader test finding 5555
    # taken): its second look at its own lock was refused, and it named
    # itself where the app's server held the port (round 35 of the hunt).
    if THIS_IS_THE_CHECK:
        return False
    lock = DATA_DIR / "quality-check" / "running.lock"
    if not lock.is_file():
        return False
    import msvcrt
    try:
        handle = open(lock, "a+")
    except OSError:
        return False
    try:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True                     # held: the check is running
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return False
    finally:
        handle.close()


class FolderError(RuntimeError):
    """A folder we need could not be created, said in plain words."""


def write_refused(folder: Path) -> OSError | None:
    """Windows' refusal to let us write in `folder`, or None. Asked with a
    tiny file of our own, deleted at once: C:\\Windows or a read-only stick
    said "Folder saved." and yt-dlp then failed in its own words (round 37 of
    the hunt). The other programs learn it from their work folder."""
    import os
    import uuid
    probe = folder / f"teleloadzai-write-test-{uuid.uuid4().hex[:8]}.tmp"
    # Deleted by Windows itself when closed (O_TEMPORARY): a delete refused
    # afterwards (a sync client holding the new file) left one probe per
    # download in the user's folder (round 38 of the hunt).
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_TEMPORARY", 0)
    try:
        handle = os.open(probe, flags)
    except OSError as problem:
        return problem
    os.close(handle)
    if not getattr(os, "O_TEMPORARY", 0):
        try:
            probe.unlink()
        except OSError:
            pass
    return None


def make_writable_folder(folder: Path) -> None:
    """`make_folder`, then the write test: one sentence for both."""
    make_folder(folder)
    refused = write_refused(folder)
    if refused is not None:
        raise FolderError(f"Teleloadzai could not write in {folder}. Choose another folder. "
                          f"(Windows says: {refused.strerror or refused})")


def make_folder(folder: Path) -> None:
    """Create a folder, or say plainly why it cannot be.

    Until 2026-09-23 a failure here reached the user as Windows' own text:
    "[WinError 183] Impossible de créer un fichier déjà existant" -- a code
    number, in the language of Windows, about a folder he never named. The
    cause is known exactly (creating it is our own step), so the sentence is
    ours; Windows' reason stays at the end, as its own words.
    """
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as problem:
        # "Choose another folder in Settings" was wrong for a folder picked
        # in "Save as" or on the card, and a removed drive got the same words
        # (round 13 of the hunt). Advice, not a cause: Windows' reason follows.
        raise FolderError(
            f"Teleloadzai could not create the download folder {folder}. "
            "If it was on a drive that was removed, plug it back in; "
            "otherwise choose another folder. "
            f"(Windows says: {problem.strerror or problem})") from problem
