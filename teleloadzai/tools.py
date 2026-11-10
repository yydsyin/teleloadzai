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
import threading
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
_cache_lock = threading.RLock()
# Decision 18, changed by the user 2026-10-21: every 6 hours, not 24. A site
# that breaks gets its fix in yt-dlp within hours, and the app knew of it a
# day later. 8 tools x 4 checks = 32 requests a day; GitHub allows 60 an hour.
CACHE_HOURS = 6
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
    # The oldest Python it installs on (its own "Requires-Python"), said on
    # the Programs row and checked before pip runs: () = any.
    python_min: tuple[int, ...] = ()
    version_args: tuple[str, ...] = ("--version",)
    # Shown to the user BEFORE he installs, never discovered afterwards.
    requires: tuple[str, ...] = ()
    # A second release channel the user may choose (Settings -> Tools):
    # yt-dlp's preview builds get fixes for broken sites days earlier.
    preview_repo: str = ""


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("yt-dlp", "yt-dlp", "yt-dlp/yt-dlp", "exe",
             what_for="Downloads from almost every site.", essential=True,
             exe_name="yt-dlp.exe", asset_keywords=("yt-dlp.exe",),
             requires=("FFmpeg",),       # for MP3, and to join video with sound
             # Read 2026-10-21: its latest release holds a plain yt-dlp.exe.
             preview_repo="yt-dlp/yt-dlp-nightly-builds"),

    ToolSpec("ffmpeg", "FFmpeg", "GyanD/codexffmpeg", "zip",
             what_for="Makes MP3s, and joins picture and sound.", essential=True,
             exe_name="ffmpeg.exe", asset_keywords=("essentials_build.zip",),
             asset_exclude=("shared",), extract_only=("ffmpeg.exe", "ffprobe.exe")),

    ToolSpec("n-m3u8dl-re", "N_m3u8DL-RE", "nilaoda/N_m3u8DL-RE", "zip",
             what_for="For stream links (.m3u8, .mpd), when yt-dlp is not enough.",
             exe_name="N_m3u8DL-RE.exe", asset_keywords=("win-x64",),
             extract_only=("N_m3u8DL-RE.exe",)),

    # No command line at all: `--help` opens a language menu (checked 2026-09-21).
    # version_args empty = never start it just to read a version.
    ToolSpec("tiktokdownloader", "TikTokDownloader", "JoeanAmier/TikTokDownloader", "zip",
             # "without the watermark" until 2026-09-25: on the same TikTok
             # video neither this tool nor yt-dlp had one (decision 38).
             what_for="TikTok and Douyin.",
             # "X64": the release has an ARM64 twin, listed first -- with
             # "Windows" alone, Update fetched the ARM64 build (found by the
             # silent-failure hunt, 2026-10-18; both names read from the 5.8
             # release the same day).
             exe_name="DouK-Downloader.exe", asset_keywords=("Windows", "X64"),
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
             # "X64" for the same reason as TikTokDownloader (2.8 release).
             exe_name="XHS-Downloader.exe", asset_keywords=("Windows", "X64")),

    ToolSpec("streamlink", "Streamlink", "streamlink/windows-builds", "zip",
             what_for="Records a live stream while it happens.",
             exe_name="streamlink.exe", asset_keywords=(".zip",)),

    ToolSpec("gallery-dl", "gallery-dl", "mikf/gallery-dl", "pip",
             what_for="Instagram and Pinterest: photos, carousels, stories.",
             pip_name="gallery-dl", module="gallery_dl", needs_python=True,
             requires=("Python",)),

    # The second Bilibili tool, the user's choice 2026-11-09: with a log-in
    # it saved the whole 1080p video where yt-dlp's "Best" got a file
    # Bilibili's main server cuts. Needs Python 3.11 or newer (its own
    # "Requires-Python", read from 2.3.1).
    ToolSpec("yutto", "yutto", "yutto-dev/yutto", "pip",
             what_for="Bilibili: 1080p with your log-in, 480p without.",
             pip_name="yutto", module="yutto", needs_python=True,
             python_min=(3, 11), requires=("Python",)),

)

BY_ID: dict[str, ToolSpec] = {s.id: s for s in SPECS}

# The tools whose PREVIEW channel the user chose. Set by the server from the
# settings at start and when the setting changes.
PREVIEW: set[str] = set()


def set_preview(tool_id: str, on: bool) -> None:
    (PREVIEW.add if on else PREVIEW.discard)(tool_id)


def channel(tool_id: str) -> str:
    """"preview" or "stable" -- the channel this tool is fetched from."""
    tool = BY_ID.get(tool_id)
    return "preview" if tool and tool.preview_repo and tool_id in PREVIEW else "stable"


def _release_key(tool: ToolSpec) -> str:
    """Where a channel's release is remembered in the cache: the preview has
    an entry of its own, so switching back finds the stable answer intact."""
    return tool.id + "@preview" if channel(tool.id) == "preview" else tool.id


def spec(tool_id: str) -> ToolSpec | None:
    return BY_ID.get(tool_id)


# --------------------------------------------------------------------------
# is it here, and which version
# --------------------------------------------------------------------------

def libs_dir() -> Path:
    return BIN_DIR / PYTHON_LIBS


def find_python() -> str | None:
    """The user's Python, needed only by the pip tools (decision 26).

    A PC without Python still has a `python.exe` on its PATH: Windows' Store
    alias (`WindowsApps\\python.exe`), which only prints "Python was not
    found" and exits with 9009 (seen on this PC, 2026-10-18). Found by name,
    it hid the "Python is missing" screen behind a raw pip error. A Python
    from the Store lives in the same folder and DOES run, so that folder is
    asked, not skipped.
    """
    for candidate in ("python", "py"):
        found = shutil.which(candidate)
        if found and ("windowsapps" not in found.lower() or _runs(found)):
            return found
    return None


def _runs(python: str) -> bool:
    try:
        return subprocess.run([python, "-c", "import sys"], capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=15,
                              creationflags=_NO_WINDOW).returncode == 0
    except Exception:
        return False


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
        "error": tail[-1][:200] if tail else "Python still not found. Restart Teleloadzai.",
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
    # An empty answer kept by an older version of this code is asked again.
    nothing_to_ask = tool.kind != "pip" and not tool.version_args
    if stamp and remembered.get("stamp") == stamp and (remembered.get("version") or nothing_to_ask):
        return remembered.get("version", "")

    version = _pip_version(tool) if tool.kind == "pip" else _ask_program(tool, path)

    # Only a real answer is kept. A version read that timed out was kept as
    # "no version" until the file changed: streamlink 8.6.2 answered in 3.6 s
    # when asked by hand, and the Tools page showed no version, so Update was
    # never offered (data/tools.json, 2026-10-18). A tool that has no version
    # to read (`version_args=()`) is never asked anyway.
    if version or nothing_to_ask:
        _change_cache(lambda cache: cache.setdefault(tool_id, {}).__setitem__(
            "installed", {"stamp": stamp, "version": version}))
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
        text = finished.stdout or finished.stderr or ""
    except subprocess.TimeoutExpired as late:
        # XHS-Downloader prints "XHS-Downloader V2.8 Stable" at once and then
        # never exits (seen 2026-10-18): what it said before the time limit
        # is its answer. Until then it was kept as "no version".
        text = late.stdout or late.stderr or ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
    except Exception:
        return ""

    text = text.strip()
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
    # Under the save's lock: on Windows a read and a replace of the same file
    # refuse each other -- 16 of 3,000 saves refused while another thread
    # read, 0 with one lock (2026-11-01); a refused save left
    # `tools.json.<n>.tmp`, and a refused read gave {}.
    with _cache_lock:
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_cache(cache: dict) -> None:
    """To a temporary file first, then put in place: a reader never meets
    half a file (it read {} and the next save wrote over every record --
    `installed_from` is the only version TikTokDownloader and KS-Downloader
    have; hunt of 2026-10-31)."""
    ensure_dirs()
    temp = CACHE_FILE.with_name(f"{CACHE_FILE.name}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    os.replace(temp, CACHE_FILE)


def _change_cache(change: Callable[[dict], None]) -> None:
    """Read, change and write the cache as one step: "Update all" installs
    in parallel, and two of them could each write over the other's record."""
    with _cache_lock:
        cache = _load_cache()
        change(cache)
        _save_cache(cache)


def _is_fresh(entry: dict, hours: float = CACHE_HOURS) -> bool:
    try:
        checked = datetime.fromisoformat(entry["checked_at"])
    except Exception:
        return False
    return datetime.now(timezone.utc) - checked < timedelta(hours=hours)


def latest_release(tool_id: str, force: bool = False,
                   max_age_hours: float | None = None) -> dict:
    """Latest version + the file to download, from the tool's chosen channel.
    Asks GitHub at most every CACHE_HOURS -- or every ``max_age_hours``: after
    a failed download the page asks with 1, so a fix released this morning is
    found at once, and never more than once an hour per tool.

    Returns ``{"version": str, "url": str, "size": int, "error": str}``.
    """
    tool = spec(tool_id)
    if tool is None:
        return {"error": "unknown tool"}
    key = _release_key(tool)
    repo = tool.preview_repo if key != tool.id else tool.repo

    cache = _load_cache()
    entry = cache.get(key, {})
    # A file remembered from before the asset rules changed is not trusted:
    # the ARM64 links of TikTokDownloader and XHS-Downloader sat in this cache
    # after "X64" was added to their rules (2026-10-18).
    usable = tool.kind == "pip" or _pick_asset(
        tool, [{"name": str(entry.get("url", "")).rsplit("/", 1)[-1]}]) is not None
    remembered = entry.get("version") and usable
    fresh = _is_fresh(entry, CACHE_HOURS if max_age_hours is None else max_age_hours)
    if not force and remembered and (fresh or _failed_lately(entry)):
        return {k: entry.get(k, "") for k in ("version", "url", "size")} | {"error": ""}
    if not force and _failed_lately(entry):
        return {"error": "cannot reach GitHub (tried less than an hour ago)"}

    try:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # The failure is remembered for an hour: without that, every pasted
        # link asked GitHub again for each tool it offered -- up to 20 s each
        # when GitHub hangs, and more requests spent when it refuses
        # (decision 18). Install and Update pass `force` and still ask.
        _change_cache(lambda cache: cache.setdefault(key, {}).__setitem__(
            "failed_at", datetime.now(timezone.utc).isoformat()))
        # Keep an old answer rather than nothing.
        if remembered:
            return {k: entry.get(k, "") for k in ("version", "url", "size")} | {"error": ""}
        return {"error": f"cannot reach GitHub ({type(exc).__name__})"}

    found = {"version": (data.get("tag_name") or "").lstrip("v"), "url": "", "size": 0}
    if tool.kind != "pip":
        asset = _pick_asset(tool, data.get("assets") or [])
        if asset is None:
            return {"error": f"no Windows file in the {tool.name} release"}
        found["url"], found["size"] = asset["browser_download_url"], asset.get("size", 0)

    # The entry is merged, not replaced: replacing it dropped the cached
    # installed version, so every check made the Tools page start each
    # program again to read it.
    def merge(cache: dict) -> None:
        kept = {k: v for k, v in cache.get(key, {}).items() if k != "failed_at"}
        cache[key] = kept | found | {"checked_at": datetime.now(timezone.utc).isoformat()}
    _change_cache(merge)
    return found | {"error": ""}


def _failed_lately(entry: dict) -> bool:
    try:
        failed = datetime.fromisoformat(entry["failed_at"])
    except Exception:
        return False
    return datetime.now(timezone.utc) - failed < timedelta(hours=1)


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
                    on_progress(f"{label} · connection lost, trying again "
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

    release: dict = {}
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

    # Which release and channel is now here. TikTokDownloader and
    # KS-Downloader print no version, so this is the only way to know an
    # update worked -- and whether yt-dlp is the stable or the preview build.
    _change_cache(lambda cache: cache.setdefault(tool_id, {}).__setitem__(
        "installed_from", {"channel": channel(tool_id), "release": release.get("version", "")}))

    if on_progress:
        on_progress("done", 100)
    return installed_version(tool_id)


# What a Windows program says it runs on (its PE header's "machine" field).
# x64 runs here; 32-bit x86 too. ARM64 does not -- and it is what Update
# fetched for TikTokDownloader and XHS-Downloader (2026-10-18).
_RUNS_HERE = {0x8664, 0x014C}


def _check_program(path: Path, tool: ToolSpec) -> None:
    """Refuse a program that cannot run on this PC, BEFORE it replaces the
    working one. Read from the file, never from its name."""
    import struct
    try:
        with path.open("rb") as program:
            head = program.read(4096)
        start = struct.unpack_from("<I", head, 0x3C)[0]
        machine = struct.unpack_from("<H", head, start + 4)[0]
        is_program = head[:2] == b"MZ" and head[start:start + 4] == b"PE\0\0"
    except (OSError, struct.error):
        is_program, machine = False, 0
    if not is_program:
        raise InstallError(f"the downloaded {tool.name} is not a Windows program; "
                           "the installed one was kept")
    if machine not in _RUNS_HERE:
        raise InstallError(f"the downloaded {tool.name} is built for another kind of "
                           f"processor (code {machine:#06x}); the installed one was kept")


def _install_exe(tool: ToolSpec, url: str, on_progress: ProgressFn | None) -> None:
    target = BIN_DIR / tool.exe_name
    temporary = target.with_suffix(target.suffix + ".part")
    _download(url, temporary, on_progress, f"downloading {tool.name}")
    try:
        _check_program(temporary, tool)
    except InstallError:
        temporary.unlink(missing_ok=True)
        raise
    # A title read can hold yt-dlp.exe for a few seconds: wait for it rather
    # than fail on a raw "PermissionError".
    for attempt in range(10):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            time.sleep(1)
    temporary.unlink(missing_ok=True)
    raise InstallError(f"{tool.name} is in use by another program, so it could not be "
                       "replaced. The installed one was kept: try again in a moment.")


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
                for temporary, target in taken:
                    if target.suffix.lower() == ".exe":
                        _check_program(temporary, tool)
                for temporary, target in taken:     # only now, all of them complete
                    temporary.replace(target)
            else:
                folder = BIN_DIR / tool.id
                fresh = BIN_DIR / f"{tool.id}.new"
                old = BIN_DIR / f"{tool.id}.old"
                shutil.rmtree(fresh, ignore_errors=True)
                shutil.rmtree(old, ignore_errors=True)
                zipped.extractall(fresh)            # complete, beside the working one
                # The program we will run must be in it, and run here --
                # checked before the working folder is moved away.
                if tool.exe_name:
                    program = next(fresh.rglob(tool.exe_name), None)
                    if program is None:
                        raise InstallError(f"{tool.exe_name} is not in the downloaded "
                                           f"archive; the installed {tool.name} was kept")
                    _check_program(program, tool)
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


_PYTHON_VERSIONS: dict[str, tuple[float, tuple[int, ...]]] = {}


def python_version(python: str) -> tuple[int, ...]:
    """(3, 13) for that Python, () when it cannot say. Asked once per file
    (its date): a new Python installed over it is asked again."""
    try:
        stamp = os.stat(python).st_mtime
    except OSError:
        return ()
    known = _PYTHON_VERSIONS.get(python)
    if known and known[0] == stamp:
        return known[1]
    try:
        said = subprocess.run([python, "-c", "import sys; print(*sys.version_info[:2])"],
                              capture_output=True, text=True, timeout=20,
                              creationflags=_NO_WINDOW).stdout.split()
        version = tuple(int(part) for part in said[:2])
    except (OSError, subprocess.SubprocessError, ValueError):
        version = ()
    _PYTHON_VERSIONS[python] = (stamp, version)
    return version


def _install_pip(tool: ToolSpec, on_progress: ProgressFn | None) -> None:
    python = find_python()
    if not python:
        raise InstallError("python_missing")      # the UI shows the help screen
    # Too old: said in words before pip runs -- pip's own answer was "No
    # matching distribution found" (yutto needs 3.11; decision 28).
    have = python_version(python)
    if tool.python_min and have and have < tool.python_min:
        need = ".".join(map(str, tool.python_min))
        # No button named: the "Install Python" block shows only when Python
        # is missing. A newly installed Python is seen after a restart (the
        # PATH Teleloadzai started with).
        raise InstallError(
            f"{tool.name} needs Python {need} or newer, and this PC has Python "
            f"{'.'.join(map(str, have))}. Install a newer one from {PYTHON_DOWNLOAD_PAGE}, "
            "then close and reopen Teleloadzai.")
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
    _drop_old_records()


def _drop_old_records() -> None:
    """Keep only the newest version record of EACH package in our folder.

    `pip install --target --upgrade` replaces a package but ADDS its new
    record (`gallery_dl-1.32.14.dist-info`) beside the old one
    (`gallery_dl-1.32.13.dist-info`), and Python then reads the old one: the
    code was 1.32.14, the Tools page said 1.32.13 with "update", and pressing
    Update seemed to do nothing (seen 2026-09-28). The packages a tool brings
    along do the same: charset_normalizer had 3.5.1 and 3.5.2 side by side
    (grids of 2026-10-18), when only the tool's own records were cleaned.
    Only `<package>-<version>.dist-info` folders inside `libs_dir()` are
    touched, and only when a newer record of the same package is there.
    """
    by_package: dict[str, list] = {}
    for folder in libs_dir().glob("*.dist-info"):
        name, _, version = folder.name[: -len(".dist-info")].rpartition("-")
        if name and _numbers(version):
            key = re.sub(r"[-_.]+", "_", name).lower()
            by_package.setdefault(key, []).append((_numbers(version), folder))
    for records in by_package.values():
        for _, folder in sorted(records)[:-1]:
            try:
                shutil.rmtree(folder)
            except OSError:
                pass    # the version shown stays old; the package itself is new


# The app's own packages in bin/pylibs (requirements.txt, decision 20): kept
# whatever the tools need.
APP_PACKAGES = ("pywebview",)

_MARKER_TOKEN = re.compile(
    r"""\(|\)|"[^"]*"|'[^']*'|===|==|!=|<=|>=|~=|<|>|not\s+in\b|in\b|and\b|or\b"""
    r"""|[A-Za-z_][A-Za-z0-9_.]*""")


def _marker_env() -> dict[str, str]:
    """This PC, as a package's requirement conditions name it."""
    import platform
    return {"sys_platform": sys.platform, "os_name": os.name,
            "platform_system": platform.system(), "platform_machine": platform.machine(),
            "python_version": "%d.%d" % sys.version_info[:2],
            "python_full_version": platform.python_version(),
            "implementation_name": sys.implementation.name,
            "platform_python_implementation": platform.python_implementation(),
            "extra": ""}


def _marker_true(marker: str, env: dict[str, str]) -> bool:
    """A requirement's condition (`sys_platform == "win32"`, `extra == "dev"`,
    `python_version < "3.9"`), for this PC. Raises ValueError on anything it
    does not understand -- the caller then KEEPS the package: a wrong answer
    here may only keep files, never delete one that is needed."""
    tokens, pos, text = [], 0, marker.strip()
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        found = _MARKER_TOKEN.match(text, pos)
        if not found:
            raise ValueError(marker)
        tokens.append(found.group())
        pos = found.end()
    at = 0

    def value(token: str) -> str:
        if token[:1] in "\"'":
            return token[1:-1]
        if token in env:
            return env[token]
        raise ValueError(token)

    def compare() -> bool:
        nonlocal at
        if tokens[at] == "(":
            at += 1
            result = either()
            if tokens[at] != ")":
                raise ValueError(marker)
            at += 1
            return result
        left, op, right = value(tokens[at]), " ".join(tokens[at + 1].split()), value(tokens[at + 2])
        at += 3
        if op in ("in", "not in"):
            return (left in right) == (op == "in")
        if op in ("==", "!=") and not (left[:1].isdigit() and right[:1].isdigit()):
            return (left == right) == (op == "==")
        a, b = _numbers(left), _numbers(right)
        if not a or not b or op not in ("==", "!=", "<", "<=", ">", ">="):
            raise ValueError(marker)
        size = max(len(a), len(b))
        a, b = a + (0,) * (size - len(a)), b + (0,) * (size - len(b))
        return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b,
                ">": a > b, ">=": a >= b}[op]

    def both() -> bool:
        nonlocal at
        result = compare()
        while at < len(tokens) and tokens[at] == "and":
            at += 1
            result = compare() and result
        return result

    def either() -> bool:
        nonlocal at
        result = both()
        while at < len(tokens) and tokens[at] == "or":
            at += 1
            result = both() or result
        return result

    try:
        result = either()
    except IndexError:
        raise ValueError(marker) from None
    if at != len(tokens):
        raise ValueError(marker)
    return result


def _package_key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pip_packages() -> dict:
    """The packages in bin/pylibs, by normalised name."""
    from importlib.metadata import distributions
    return {_package_key(d.metadata["Name"]): d
            for d in distributions(path=[str(libs_dir())]) if d.metadata["Name"]}


def unneeded_packages() -> list[str]:
    """The packages in bin/pylibs that neither Teleloadzai nor any installed
    pip tool needs, following each package's own requirements. Removing a
    pip tool used to remove its own package only: f2's 43 stayed for weeks,
    94 MB (found 2026-11-10)."""
    packages = _pip_packages()
    roots = [*APP_PACKAGES] + [t.pip_name for t in SPECS
                               if t.kind == "pip" and installed_path(t.id)]
    env = _marker_env()
    needed: set[str] = set()
    waiting = [_package_key(r) for r in roots]
    while waiting:
        key = waiting.pop()
        if key in needed or key not in packages:
            continue
        needed.add(key)
        for line in packages[key].requires or []:
            requirement, _, marker = line.partition(";")
            name = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
            if not name:
                continue
            try:
                if marker.strip() and not _marker_true(marker, env):
                    continue            # another system, an old Python, an extra
            except ValueError:
                pass                    # not understood: kept
            waiting.append(_package_key(name.group(1)))
    return sorted(packages[k].metadata["Name"] for k in set(packages) - needed)


def _record_entries(package) -> list[str]:
    """Every path in the package's RECORD, as written. Not `package.files`:
    Python 3.13 drops the entries whose file is not at the recorded place, and
    `../../bin/biliass.exe` read from bin/pylibs is not there -- 19 lines, 18
    entries, the launcher never deleted (seen 2026-11-10)."""
    import csv
    import io
    text = package.read_text("RECORD") or ""
    return [row[0] for row in csv.reader(io.StringIO(text)) if row and row[0]]


def _package_files(package) -> list[Path]:
    """The files of one installed package, from its own file list -- each one
    where our `pip install --target` really put it, and ONLY inside
    bin/pylibs. Its list names the launchers and manual pages
    `../../bin/x.exe` and `../../share/…`, from pip's temporary folder; read
    from bin/pylibs that is Teleloadzai's own bin/ -- where yt-dlp.exe lives.
    `pip uninstall` deleted a file there (a dummy, on a copy, 2026-11-10) and
    left the real launchers in bin/pylibs/bin. Anything else outside is kept."""
    libs = libs_dir().resolve()
    found: list[Path] = []
    for entry in _record_entries(package):
        text = entry.replace("\\", "/")
        for outside in ("../../bin/", "../../share/"):
            if text.startswith(outside):
                text = text[len("../../"):]
        path = (libs / text).resolve()
        if path != libs and path.is_relative_to(libs):
            found.append(path)
            if path.suffix == ".py":        # its compiled copies, made later
                found.extend(path.parent.glob(f"__pycache__/{path.stem}.*.pyc"))
    return found


def _record_folder(package) -> Path | None:
    """The package's `<name>-<version>.dist-info`, directly in bin/pylibs."""
    libs = libs_dir().resolve()
    for entry in _record_entries(package):
        parts = entry.replace("\\", "/").split("/")
        if len(parts) == 2 and parts[0].endswith(".dist-info"):
            folder = (libs / parts[0]).resolve()
            if folder.parent == libs:
                return folder
    return None


def _delete_package(package) -> bool:
    """Delete one package's files and its record, inside bin/pylibs only.
    True when its record is gone (it no longer counts as installed)."""
    record = _record_folder(package)
    for path in _package_files(package):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass                        # held by Windows: the record decides
    if record is None:
        return False
    shutil.rmtree(record, ignore_errors=True)
    return not record.exists()


def _drop_empty_folders() -> None:
    """The empty folders pip leaves behind (protobuf left `google/`, empty,
    2026-11-10). `os.rmdir` refuses a folder with anything in it."""
    for entry in libs_dir().iterdir():
        if entry.is_dir() and not entry.is_symlink():
            for root, _dirs, _files in os.walk(entry, topdown=False):
                try:
                    os.rmdir(root)
                except OSError:
                    pass                # not empty: kept


def remove_unneeded() -> list[str]:
    """Delete what `unneeded_packages` names, each from its own file list and
    only inside bin/pylibs (`_delete_package` -- never `pip uninstall`, which
    follows `../../bin/` out of it). Returns the names really gone, judged by
    what is left."""
    names = unneeded_packages()
    if not names:
        return []
    packages = _pip_packages()
    for name in names:
        package = packages.get(_package_key(name))
        if package is not None:
            _delete_package(package)
    left = _pip_packages()
    gone = [n for n in names if _package_key(n) not in left]
    _drop_empty_folders()
    from . import console
    if gone:
        console.add("app", f"Teleloadzai: removed {len(gone)} package(s) no program needs any more: "
                           + ", ".join(gone), "end")
    if len(gone) < len(names):
        console.add("app", "Teleloadzai: these packages no program needs could not be removed: "
                           + ", ".join(n for n in names if n not in gone), "err")
    return gone


def remove(tool_id: str) -> bool:
    """Delete a tool from our folder. Never touches anything outside it."""
    tool = spec(tool_id)
    if tool is None:
        return False

    if tool.kind == "pip":
        # Its own files from its own list, inside bin/pylibs only -- not
        # `pip uninstall`, which follows `../../bin/` into Teleloadzai's bin/
        # (`_package_files`, 2026-11-10).
        package = _pip_packages().get(_package_key(tool.pip_name))
        if package is not None:
            _delete_package(package)
        for leftover in libs_dir().glob(f"{tool.module}*"):
            shutil.rmtree(leftover, ignore_errors=True) if leftover.is_dir() else leftover.unlink(missing_ok=True)
        # And what it brought with it, if nothing else needs it now.
        if installed_path(tool_id) is None:
            remove_unneeded()
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
    installed_from = _load_cache().get(tool_id, {}).get("installed_from", {}) if path else {}

    # A tool with no readable version is compared by the release we installed.
    update = _is_newer(latest, here or installed_from.get("release", ""))
    # yt-dlp installed from the other channel: "Update" switches it over --
    # a preview build is newer than stable, so numbers alone would never
    # take the user back to stable.
    # Only when the channel it came from is KNOWN: a tools.json lost or reset
    # read as "stable", and a user on Preview was offered a false Update
    # (seen in a fresh test copy, 2026-11-10) -- decision 30: no proof, say
    # nothing.
    came_from = installed_from.get("channel", "")
    switch = bool(path) and bool(tool.preview_repo) and bool(came_from) \
        and came_from != channel(tool_id)

    return {
        "id": tool.id,
        "name": tool.name,
        "what_for": tool.what_for,
        "essential": tool.essential,
        "kind": tool.kind,
        "needs_python": tool.needs_python,
        "python_min": ".".join(map(str, tool.python_min)),
        # What this tool cannot work without, shown BEFORE the user installs.
        "requires": list(tool.requires),
        "blocked": tool.needs_python and not find_python(),
        "installed": bool(path),
        "path": str(path) if path else "",
        "outside": bool(path) and BIN_DIR not in path.parents,
        "version": here,
        "release_installed": installed_from.get("release", ""),
        "latest": latest,
        "update_available": update or switch,
        "channel_change": switch,
        "channel": channel(tool_id) if tool.preview_repo else "",
        "size": release.get("size", 0),
        "error": release.get("error", ""),
    }


def status_all(check_online: bool = True) -> list[dict]:
    return [status(s.id, check_online) for s in SPECS]
