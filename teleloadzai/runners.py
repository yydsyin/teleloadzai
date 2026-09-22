"""Run the specialist tools: one engine, one recipe per tool.

`ytdlp.py` stays on its own, because yt-dlp lets us choose the shape of its
progress and tell us the exact file it wrote. None of the others do. So this
module works the other way round:

**Watch the folder.** We note what is in the output folder before the tool
runs, and look again afterwards. What appeared or changed is what the tool
downloaded. That works for every tool, whatever it prints, and it answers
the question of decision 24 for free: if nothing changed, nothing was
downloaded, and we must not claim a success.

Two things every tool gets, and both were learned the hard way:

* **UTF-8 forced in its environment.** f2 printed a rocket and crashed,
  because this machine's console speaks GBK (checked 2026-09-21).
* **stdin closed.** A tool that decides to ask a question must fail, not
  wait forever for a human who is not watching.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import tools
from .paths import BIN_DIR

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Most tools print a percentage somewhere. Those that do not simply show
# "working" -- we do not invent a number we cannot measure.
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Request:
    url: str
    out_dir: Path               # the folder the file must land in
    out_name: str = ""          # wanted base name; some tools ignore it
    mode: str = "mp4"
    quality: str = "best"


@dataclass
class RunResult:
    files: list[Path] = field(default_factory=list)
    log_tail: list[str] = field(default_factory=list)

    @property
    def nothing_downloaded(self) -> bool:
        return not self.files


@dataclass(frozen=True)
class Recipe:
    """How to drive one tool."""

    tool_id: str
    build: Callable[[Path, Request], list[str]]
    module: str = ""            # run as `python -m <module>` instead of an exe
    note: str = ""              # shown to the user when it matters


# --------------------------------------------------------------------------
# the recipes -- every command line below was read from the tool itself
# --------------------------------------------------------------------------

def _gallery_dl(_exe: Path, r: Request) -> list[str]:
    # -D is the exact folder, no category sub-folders.
    return [r.url, "-D", str(r.out_dir), "--windows-filenames"]


def _streamlink(exe: Path, r: Request) -> list[str]:
    name = (r.out_name or "stream") + (".mp3" if r.mode == "mp3" else ".ts")
    return [str(exe), r.url, "best", "-o", str(r.out_dir / name),
            "--progress", "force"]


def _xhs(exe: Path, r: Request) -> list[str]:
    # It builds its own folder under --work_path, so we give it ours.
    return [str(exe), "--url", r.url,
            "--work_path", str(r.out_dir.parent),
            "--folder_name", r.out_dir.name]


def _n_m3u8dl_re(exe: Path, r: Request) -> list[str]:
    # --auto-select is not optional: a stream with several qualities makes it
    # stop and ask which one, and with stdin closed it crashes (2026-09-21).
    # --tmp-dir is not optional either: without it the pieces of the video
    # pile up beside the program (28 MB found in bin/ the same day).
    return [str(exe), r.url,
            "--auto-select",
            "--tmp-dir", str(r.out_dir),
            "--save-dir", str(r.out_dir),
            "--save-name", r.out_name or "stream"]


def _f2(_exe: Path, r: Request) -> list[str]:
    # f2 has one sub-command per site, and it needs a config file with a
    # cookie for almost everything. Until step 5 this will mostly refuse.
    site = "ks" if "kuaishou" in r.url or "gifshow" in r.url else "wb"
    return [site, "-u", r.url, "-p", str(r.out_dir)]


RECIPES: dict[str, Recipe] = {
    "gallery-dl": Recipe("gallery-dl", _gallery_dl, module="gallery_dl"),
    "streamlink": Recipe("streamlink", _streamlink),
    "xhs-downloader": Recipe("xhs-downloader", _xhs),
    "n-m3u8dl-re": Recipe("n-m3u8dl-re", _n_m3u8dl_re),
    "f2": Recipe("f2", _f2, module="f2",
                 note="f2 needs a cookie in its own config file for most sites."),
}


def can_run(tool_id: str) -> bool:
    """True when we know how to drive this tool at all."""
    return tool_id in RECIPES or tool_id == "yt-dlp"


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

def _snapshot(folder: Path) -> dict[Path, tuple[int, float]]:
    """Every file under a folder, with its size and date."""
    if not folder.is_dir():
        return {}
    found = {}
    for path in folder.rglob("*"):
        if path.is_file():
            try:
                info = path.stat()
                found[path] = (info.st_size, info.st_mtime)
            except OSError:
                pass
    return found


def _child_environment(module: str) -> dict:
    """UTF-8 forced, and our own package folder when we run a module."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if module:
        libs = str(tools.libs_dir())
        env["PYTHONPATH"] = libs + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run(
    tool_id: str,
    request: Request,
    on_progress: Callable[[int], None] | None = None,
    on_start: Callable[[subprocess.Popen], None] | None = None,
) -> RunResult:
    """Run one specialist tool and report what it actually wrote."""
    recipe = RECIPES.get(tool_id)
    if recipe is None:
        raise RunnerError(f"no recipe for {tool_id}")

    if recipe.module:
        exe = Path(sys.executable)
        head = [str(exe), "-m", recipe.module]
        if tools.installed_path(tool_id) is None:
            raise RunnerError(f"{tool_id} is not installed")
    else:
        found = tools.installed_path(tool_id)
        if found is None:
            raise RunnerError(f"{tool_id} is not installed")
        exe, head = found, []

    request.out_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(request.out_dir)

    command = head + recipe.build(exe, request)
    tail: list[str] = []

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,        # never wait for a human
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_child_environment(recipe.module),
        # A program run from our own folder drops its logs there: f2 wrote a
        # `logs/` folder straight into the project (2026-09-21). A module has
        # no folder of its own, so it works from the download folder instead.
        # A real program keeps its own folder, where its settings live.
        cwd=str(exe.parent) if not recipe.module else str(request.out_dir),
        creationflags=_NO_WINDOW,
    )
    if on_start:
        on_start(process)

    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        if on_progress:
            found_percent = _PERCENT.search(line)
            if found_percent:
                try:
                    on_progress(min(100, int(float(found_percent.group(1).replace(",", ".")))))
                except ValueError:
                    pass
        tail.append(line)
        del tail[:-40]

    code = process.wait()

    # What is new or changed since before the tool ran.
    #
    # ⚠️ Do NOT also test the file's date. gallery-dl keeps the date the web
    # server sent, so a picture from 2005 lands with a 2005 date, and a
    # "newer than the start" filter threw away the only file it downloaded
    # (found 2026-09-21). Comparing before and after needs no clock.
    after = _snapshot(request.out_dir)
    written = sorted(
        path for path, stamp in after.items()
        if path not in before or before[path] != stamp
    )

    # A tool can end badly and still have written something useful, and it
    # can end well having written nothing. Both are reported honestly.
    if code != 0 and not written:
        raise RunnerError(_short_error(tail) or f"{tool_id} stopped with code {code}")
    return RunResult(written, tail)


def _short_error(tail: list[str]) -> str:
    for line in reversed(tail):
        clean = line.strip()
        if any(word in clean.lower() for word in ("error", "失败", "错误", "traceback")):
            return clean[:200]
    return tail[-1][:200] if tail else ""
