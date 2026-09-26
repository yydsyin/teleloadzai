"""The Tool Manager: know, install, update and remove the download tools.

Nothing else in the app may guess whether a tool is present (CLAUDE.md,
hard rule 3) -- everything asks this module.

Version questions to GitHub are cached for 24 hours (decision 18), because
GitHub only answers 60 questions per hour from one computer.

Three kinds of tool:

* ``exe`` -- one program file, taken straight from a GitHub release.
* ``zip`` -- a release archive; either a few files we pull out, or a whole
  folder with its helper files kept together.
* ``pip`` -- a Python package. It needs Python on the machine (decision 26)
  and is installed inside our own folder, never in the user's Python
  (decision 27).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .paths import BIN_DIR, DATA_DIR, ensure_dirs

CACHE_FILE = DATA_DIR / "tools.json"
CACHE_HOURS = 24                      # decision 18
PYTHON_LIBS = "pylibs"                # where pip packages land, inside bin/
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_USER_AGENT = "Teleloadzai tool manager"

ProgressFn = Callable[[str, int], None]      # (what is happening, 0-100)


# --------------------------------------------------------------------------
# what we know about each tool
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    repo: str                       # GitHub "owner/name", for versions
    kind: str                       # "exe" | "zip" | "pip"
    what_for: str = ""              # shown in the Tools page
    essential: bool = False         # base tools, always installed
    # exe / zip
    exe_name: str = ""              # the program we run afterwards
    asset_keywords: tuple[str, ...] = ()     # all must appear in the file name
    asset_exclude: tuple[str, ...] = ()      # none may appear
    extract_only: tuple[str, ...] = ()       # pull out just these, flattened
    # pip
    pip_name: str = ""
    module: str = ""                # run with: python -m <module>
    needs_python: bool = False
    version_args: tuple[str, ...] = ("--version",)
    # Shown to the user BEFORE he installs, never discovered afterwards.
    requires: tuple[str, ...] = ()


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("yt-dlp", "yt-dlp", "yt-dlp/yt-dlp", "exe",
             what_for="The engine. Almost every site.", essential=True,
             exe_name="yt-dlp.exe", asset_keywords=("yt-dlp.exe",),
             requires=("FFmpeg",)),      # for MP3, and to join video with sound

    ToolSpec("ffmpeg", "FFmpeg", "GyanD/codexffmpeg", "zip",
             what_for="Makes MP3, and joins video with sound.", essential=True,
             exe_name="ffmpeg.exe", asset_keywords=("essentials_build.zip",),
             asset_exclude=("shared",), extract_only=("ffmpeg.exe", "ffprobe.exe")),

    ToolSpec("n-m3u8dl-re", "N_m3u8DL-RE", "nilaoda/N_m3u8DL-RE", "zip",
             what_for="Encrypted HLS / DASH streams.",
             exe_name="N_m3u8DL-RE.exe", asset_keywords=("win-x64",),
             extract_only=("N_m3u8DL-RE.exe",)),

    # No command line at all: `--help` opens a language menu (checked 2026-09-21).
    # version_args empty = never start it just to read a version.
    ToolSpec("tiktokdownloader", "TikTokDownloader", "JoeanAmier/TikTokDownloader", "zip",
             # "without the watermark" until 2026-09-25: on the same TikTok
             # video neither this tool nor yt-dlp had one (decision 38).
             what_for="TikTok and Douyin.",
             exe_name="DouK-Downloader.exe", asset_keywords=("Windows",),
             version_args=()),

    # The same author's Kuaishou tool, driven the same way (by its server).
    # Its program is called `main.exe`; the release has an ARM64 twin, hence
    # "x64" (file names read from the 1.6 release, 2026-09-23). Never started
    # for a version: without `api` it opens its own menu.
    ToolSpec("ks-downloader", "KS-Downloader", "JoeanAmier/KS-Downloader", "zip",
             what_for="Kuaishou.",
             exe_name="main.exe", asset_keywords=("Windows", "X64"),
             version_args=()),

    # Ships two programs; the plain one is the command-line one. Without
    # exe_name we picked XHS-Downloader-GUI.exe, the graphical one.
    ToolSpec("xhs-downloader", "XHS-Downloader", "JoeanAmier/XHS-Downloader", "zip",
             what_for="Xiaohongshu, video and photos.",
             exe_name="XHS-Downloader.exe", asset_keywords=("Windows",)),

    ToolSpec("streamlink", "Streamlink", "streamlink/windows-builds", "zip",
             what_for="Records a live stream while it happens.",
             exe_name="streamlink.exe", asset_keywords=(".zip",)),

    ToolSpec("gallery-dl", "gallery-dl", "mikf/gallery-dl", "pip",
             what_for="Instagram and Pinterest: photos, carousels, stories.",
             pip_name="gallery-dl", module="gallery_dl", needs_python=True,
             requires=("Python",)),

)

BY_ID: dict[str, ToolSpec] = {s.id: s for s in SPECS}


def spec(tool_id: str) -> ToolSpec | None:
    return BY_ID.get(tool_id)


# --------------------------------------------------------------------------
# is it here, and which version
# --------------------------------------------------------------------------

def libs_dir() -> Path:
    return BIN_DIR / PYTHON_LIBS


def find_python() -> str | None:
    """The user's Python, needed only by the pip tools (decision 26)."""
    for candidate in ("python", "py"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


WINGET_PYTHON_ID = "Python.Python.3.13"
PYTHON_DOWNLOAD_PAGE = "https://www.python.org/downloads/windows/"


def has_winget() -> bool:
    """Windows' own installer command. Present on most Windows 10 and 11."""
    return shutil.which("winget") is not None


def python_state() -> dict:
    """Everything the "Python is missing" screen needs to decide what to show."""
    path = find_python()
    return {
        "found": bool(path),
        "path": path or "",
        "winget": has_winget(),
        "winget_id": WINGET_PYTHON_ID,
        "download_page": PYTHON_DOWNLOAD_PAGE,
    }


def install_python_with_winget(timeout: float = 1800) -> dict:
    """Ask Windows to install Python. Shows its own window, needs the user's OK.

    We never install silently: this is a real program going onto the machine,
    so Windows asks, not us.
    """
    if not has_winget():
        return {"ok": False, "error": "winget is not on this PC"}
    try:
        finished = subprocess.run(
            ["winget", "install", "--id", WINGET_PYTHON_ID, "--exact",
             "--source", "winget", "--accept-package-agreements",
             "--accept-source-agreements"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}"}

    if find_python():
        return {"ok": True, "error": ""}
    tail = (finished.stdout or finished.stderr or "").strip().splitlines()
    return {
        "ok": False,
        # A new PATH only reaches programs started afterwards.
        "error": tail[-1][:200] if tail else "Python still not found -- restart Teleloadzai",
    }


def installed_path(tool_id: str) -> Path | None:
    """Where the tool is, or None. Our own folder first, then the PATH."""
    tool = spec(tool_id)
    if tool is None:
        return None

    if tool.kind == "pip":
        marker = libs_dir() / tool.module
        if marker.is_dir() or (libs_dir() / f"{tool.module}.py").is_file():
            return libs_dir()
        return None

    if tool.exe_name:
        direct = BIN_DIR / tool.exe_name
        if direct.is_file():
            return direct
        inside = BIN_DIR / tool.id
        if inside.is_dir():
            for found in inside.rglob(tool.exe_name):
                return found

    # A whole-folder tool and no name given: guess, but never blindly.
    # "Biggest .exe" alone chose XHS-Downloader-GUI.exe over the command-line
    # one (2026-09-21), so the graphical and helper programs are pushed last.
    inside = BIN_DIR / tool.id
    if inside.is_dir():
        exes = [p for p in inside.rglob("*.exe")
                if not any(word in p.stem.lower()
                           for word in ("gui", "setup", "install", "uninstall", "update"))]
        if exes:
            wanted = tool.id.replace("-", "").lower()
            exes.sort(key=lambda p: (p.stem.replace("-", "").lower() != wanted,
                                     -p.stat().st_size))
            return exes[0]

    system = shutil.which(tool.exe_name or tool.id)
    return Path(system) if system else None


def _file_stamp(path: Path) -> str:
    """Changes when the file changes, so a cached version can be trusted."""
    try:
        info = path.stat()
        return f"{info.st_size}-{int(info.st_mtime)}"
    except OSError:
        return ""


def installed_version(tool_id: str) -> str:
    """The version of the installed tool, asked once and remembered.

    Starting a program only to read its version is slow (yt-dlp alone needs
    more than a second), and the Tools page asks for all of them at once.
    So the answer is kept until the file itself changes.
    """
    tool = spec(tool_id)
    path = installed_path(tool_id)
    if tool is None or path is None:
        return ""

    stamp = _file_stamp(path if tool.kind != "pip" else libs_dir())
    cache = _load_cache()
    remembered = cache.get(tool_id, {}).get("installed", {})
    if stamp and remembered.get("stamp") == stamp:
        return remembered.get("version", "")

    version = _pip_version(tool) if tool.kind == "pip" else _ask_program(tool, path)

    cache.setdefault(tool_id, {})["installed"] = {"stamp": stamp, "version": version}
    _save_cache(cache)
    return version


def _ask_program(tool: ToolSpec, path: Path) -> str:
    """Ask a program its version, without ever letting it take over.

    Some tools have no command line: TikTokDownloader answers `--version` by
    opening its language menu, and we stored its banner ">>>>>>>>>>" as a
    version (2026-09-21). Two guards: `version_args=()` means never run it,
    and stdin is closed so a program waiting for a human cannot hold us.
    """
    if not tool.version_args:
        return ""
    try:
        finished = subprocess.run(
            [str(path), *tool.version_args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=15, creationflags=_NO_WINDOW,
        )
    except Exception:
        return ""

    text = (finished.stdout or finished.stderr or "").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip()[:60]
    # A version has a digit in it. A menu, a banner or a box drawing does not.
    return first if any(c.isdigit() for c in first) else ""


def _pip_version(tool: ToolSpec) -> str:
    python = find_python()
    if not python:
        return ""
    environment = dict(os.environ, PYTHONPATH=str(libs_dir()))
    try:
        finished = subprocess.run(
            [python, "-c",
             f"from importlib.metadata import version; print(version('{tool.pip_name}'))"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25, env=environment, creationflags=_NO_WINDOW,
        )
    except Exception:
        return ""
    return (finished.stdout or "").strip()[:40]


# --------------------------------------------------------------------------
# the 24 hour cache
# --------------------------------------------------------------------------

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    ensure_dirs()
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _is_fresh(entry: dict) -> bool:
    try:
        checked = datetime.fromisoformat(entry["checked_at"])
    except Exception:
        return False
    return datetime.now(timezone.utc) - checked < timedelta(hours=CACHE_HOURS)


def latest_release(tool_id: str, force: bool = False) -> dict:
    """Latest version + the file to download. Asks GitHub at most once a day.

    Returns ``{"version": str, "url": str, "size": int, "error": str}``.
    """
    tool = spec(tool_id)
    if tool is None:
        return {"error": "unknown tool"}

    cache = _load_cache()
    entry = cache.get(tool_id, {})
    if not force and _is_fresh(entry) and entry.get("version"):
        return {k: entry.get(k, "") for k in ("version", "url", "size")} | {"error": ""}

    try:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{tool.repo}/releases/latest",
            headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # Keep an old answer rather than nothing.
        if entry.get("version"):
            return {k: entry.get(k, "") for k in ("version", "url", "size")} | {"error": ""}
        return {"error": f"cannot reach GitHub ({type(exc).__name__})"}

    found = {"version": (data.get("tag_name") or "").lstrip("v"), "url": "", "size": 0}
    if tool.kind != "pip":
        asset = _pick_asset(tool, data.get("assets") or [])
        if asset is None:
            return {"error": f"no Windows file in the {tool.name} release"}
        found["url"], found["size"] = asset["browser_download_url"], asset.get("size", 0)

    cache[tool_id] = found | {"checked_at": datetime.now(timezone.utc).isoformat()}
    _save_cache(cache)
    return found | {"error": ""}


def _pick_asset(tool: ToolSpec, assets: list[dict]) -> dict | None:
    for asset in assets:
        name = asset.get("name", "").lower()
        if all(k.lower() in name for k in tool.asset_keywords) and \
           not any(x.lower() in name for x in tool.asset_exclude):
            return asset
    return None


# --------------------------------------------------------------------------
# install / remove
# --------------------------------------------------------------------------

class InstallError(RuntimeError):
    pass


DOWNLOAD_TRIES = 3


def _download(url: str, target: Path, on_progress: ProgressFn | None, label: str) -> None:
    """Fetch a file, retrying a broken connection.

    Streamlink died at 99% on a connection reset (2026-09-21) and the plain
    retry worked at once: the failure was a passing hiccup, but the user was
    told "install failed" with nowhere to go.

    A short read is also a failure. Without the size check a truncated file
    would land as a valid install and only break much later.
    """
    last_error: Exception | None = None

    for attempt in range(1, DOWNLOAD_TRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with target.open("wb") as out:
                    while True:
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        if on_progress and total:
                            on_progress(label, int(done * 100 / total))

            if total and done < total:
                raise InstallError(f"received {done} bytes out of {total}")

            if on_progress:
                on_progress(label, 100)
            return

        except Exception as exc:
            last_error = exc
            target.unlink(missing_ok=True)      # never keep half a file
            if attempt < DOWNLOAD_TRIES:
                if on_progress:
                    on_progress(f"{label} — connection lost, trying again "
                                f"({attempt + 1} of {DOWNLOAD_TRIES})", 0)
                time.sleep(2 * attempt)

    raise InstallError(f"download failed after {DOWNLOAD_TRIES} tries: {last_error}")


def install(tool_id: str, on_progress: ProgressFn | None = None) -> str:
    """Install or update one tool. Returns the version now installed."""
    tool = spec(tool_id)
    if tool is None:
        raise InstallError("unknown tool")
    ensure_dirs()
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # FFmpeg is the base every download uses (decision 28). Its only way in
    # was the first-launch list; that list went on 2026-09-26 (decision 17:
    # tools are chosen in the installer), so the first tool a link installs
    # brings FFmpeg with it. Without this, a fresh PC got yt-dlp from
    # "Install and continue", then "ffmpeg is not installed" on Download.
    if tool_id != "ffmpeg" and installed_path("ffmpeg") is None:
        try:
            install("ffmpeg", on_progress)
        except InstallError as problem:
            raise InstallError(f"FFmpeg, which every download needs, could not be "
                               f"installed: {problem}") from problem

    if tool.kind == "pip":
        _install_pip(tool, on_progress)
    else:
        release = latest_release(tool_id, force=True)
        if release.get("error"):
            raise InstallError(release["error"])
        if tool.kind == "exe":
            _install_exe(tool, release["url"], on_progress)
        else:
            _install_zip(tool, release["url"], on_progress)

    if on_progress:
        on_progress("done", 100)
    return installed_version(tool_id)


def _install_exe(tool: ToolSpec, url: str, on_progress: ProgressFn | None) -> None:
    target = BIN_DIR / tool.exe_name
    temporary = target.with_suffix(target.suffix + ".part")
    _download(url, temporary, on_progress, f"downloading {tool.name}")
    temporary.replace(target)


def _install_zip(tool: ToolSpec, url: str, on_progress: ProgressFn | None) -> None:
    archive = BIN_DIR / f"{tool.id}.zip.part"
    _download(url, archive, on_progress, f"downloading {tool.name}")
    if on_progress:
        on_progress(f"unpacking {tool.name}", 0)

    # The working tool is never touched until its replacement is COMPLETE on
    # the disk. Until 2026-09-26 the old folder was deleted first and the new
    # one unpacked after, and FFmpeg was copied straight over itself -- an
    # unpacking that failed half-way (a full disk, a file held open) left the
    # user with no tool at all.
    try:
        with zipfile.ZipFile(archive) as zipped:
            if tool.extract_only:
                wanted = {w.lower() for w in tool.extract_only}
                taken = []
                for member in zipped.infolist():
                    if Path(member.filename).name.lower() in wanted:
                        target = BIN_DIR / Path(member.filename).name
                        temporary = target.with_name(target.name + ".part")
                        with zipped.open(member) as source, temporary.open("wb") as out:
                            shutil.copyfileobj(source, out)
                        taken.append((temporary, target))
                if not taken:
                    raise InstallError(f"{', '.join(tool.extract_only)} not found in the archive")
                for temporary, target in taken:     # only now, all of them complete
                    temporary.replace(target)
            else:
                folder = BIN_DIR / tool.id
                fresh = BIN_DIR / f"{tool.id}.new"
                old = BIN_DIR / f"{tool.id}.old"
                shutil.rmtree(fresh, ignore_errors=True)
                shutil.rmtree(old, ignore_errors=True)
                zipped.extractall(fresh)            # complete, beside the working one
                if folder.exists():
                    folder.rename(old)              # fails cleanly if the tool is in use
                try:
                    fresh.rename(folder)
                except OSError:
                    if old.exists() and not folder.exists():
                        old.rename(folder)          # put the working one back
                    raise
                shutil.rmtree(old, ignore_errors=True)
    finally:
        archive.unlink(missing_ok=True)
        for leftover in BIN_DIR.glob(f"{tool.id}.new"):
            shutil.rmtree(leftover, ignore_errors=True)
        for name in tool.extract_only or ():       # a copy that stopped half-way
            (BIN_DIR / (Path(name).name + ".part")).unlink(missing_ok=True)

    if on_progress:
        on_progress(f"unpacking {tool.name}", 100)


def _install_pip(tool: ToolSpec, on_progress: ProgressFn | None) -> None:
    python = find_python()
    if not python:
        raise InstallError("python_missing")      # the UI shows the help screen
    if on_progress:
        on_progress(f"installing {tool.name} with pip", 10)

    finished = subprocess.run(
        [python, "-m", "pip", "install", "--upgrade", "--no-input",
         "--target", str(libs_dir()), tool.pip_name],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900, creationflags=_NO_WINDOW,
    )
    if finished.returncode != 0:
        last = (finished.stderr or finished.stdout or "").strip().splitlines()
        raise InstallError(last[-1] if last else "pip failed")


def remove(tool_id: str) -> bool:
    """Delete a tool from our folder. Never touches anything outside it."""
    tool = spec(tool_id)
    if tool is None:
        return False

    if tool.kind == "pip":
        python = find_python()
        if python:
            subprocess.run(
                [python, "-m", "pip", "uninstall", "-y", tool.pip_name],
                capture_output=True, text=True, timeout=300,
                env=dict(os.environ, PYTHONPATH=str(libs_dir())),
                creationflags=_NO_WINDOW,
            )
        for leftover in libs_dir().glob(f"{tool.module}*"):
            shutil.rmtree(leftover, ignore_errors=True) if leftover.is_dir() else leftover.unlink(missing_ok=True)
        # Judged by what is left, not by what this loop found: pip had
        # already deleted f2, the loop found nothing, and a real removal
        # answered False (seen 2026-09-26).
        return installed_path(tool_id) is None

    for name in (tool.exe_name, *tool.extract_only):
        try:
            if name:
                (BIN_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass                # still running: said below, never a crash
    folder = BIN_DIR / tool.id
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    # What is left in OUR folder decides -- `ignore_errors` hides a folder
    # Windows keeps locked. Not `installed_path`: it also looks at the PATH,
    # and a copy installed elsewhere on the PC is not ours to remove.
    ours = [BIN_DIR / name for name in (tool.exe_name, *tool.extract_only) if name] + [folder]
    return not any(path.exists() for path in ours)


# --------------------------------------------------------------------------
# what the Tools page shows
# --------------------------------------------------------------------------

_VERSION_NUMBER = re.compile(r"\d+(?:\.\d+)*")


def _numbers(text: str) -> tuple[int, ...]:
    """The first plain number of a version string, as numbers.

    Every project writes versions its own way -- ``0.6.0-beta``,
    ``0.6.0+df70f0b3``, ``ffmpeg version 8.0.1-essentials_build``. Comparing
    the raw text says "update available" when nothing changed, so only the
    numbers are compared.
    """
    found = _VERSION_NUMBER.search(text or "")
    return tuple(int(part) for part in found.group().split(".")) if found else ()


def _is_newer(latest: str, here: str) -> bool:
    """True only when we are sure the release is newer than what is installed."""
    new, old = _numbers(latest), _numbers(here)
    if not new or not old:
        return False            # cannot tell -- never nag the user for nothing
    size = max(len(new), len(old))
    return new + (0,) * (size - len(new)) > old + (0,) * (size - len(old))


def status(tool_id: str, check_online: bool = True) -> dict:
    tool = spec(tool_id)
    if tool is None:
        return {"error": "unknown tool"}

    path = installed_path(tool_id)
    here = installed_version(tool_id) if path else ""
    release = latest_release(tool_id) if check_online else {"version": "", "error": ""}
    latest = release.get("version", "")

    update = _is_newer(latest, here)

    return {
        "id": tool.id,
        "name": tool.name,
        "what_for": tool.what_for,
        "essential": tool.essential,
        "kind": tool.kind,
        "needs_python": tool.needs_python,
        # What this tool cannot work without, shown BEFORE the user installs.
        "requires": list(tool.requires),
        "blocked": tool.needs_python and not find_python(),
        "installed": bool(path),
        "path": str(path) if path else "",
        "outside": bool(path) and BIN_DIR not in path.parents,
        "version": here,
        "latest": latest,
        "update_available": update,
        "size": release.get("size", 0),
        "error": release.get("error", ""),
    }


def status_all(check_online: bool = True) -> list[dict]:
    return [status(s.id, check_online) for s in SPECS]
