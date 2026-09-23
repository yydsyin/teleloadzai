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


class FolderError(RuntimeError):
    """A folder we need could not be created, said in plain words."""


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
        raise FolderError(
            f"Teleloadzai could not create the download folder {folder}. "
            "Choose another folder in Settings. "
            f"(Windows says: {problem.strerror or problem})") from problem
