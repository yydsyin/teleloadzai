"""The download queue.

A job waits, then runs, then finishes. Only a few run at the same time, so
ten pasted links do not fight for the same internet connection.

The queue owns the running process of each job, which is what makes
``cancel`` possible: it stops yt-dlp instead of waiting for it to end.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import children, console, cookies, explain, login, needs, notify, runners, ytdlp

WAITING, RUNNING, DONE, ERROR, CANCELLED = "waiting", "running", "done", "error", "cancelled"
ACTIVE_STATES = (WAITING, RUNNING)


def _same_path(path: str) -> str:
    """One spelling per file: Windows names are not case-sensitive."""
    return os.path.normcase(os.path.abspath(path))


class TargetInUse(Exception):
    """A "Save as" file another download in the list will write."""


def target_clashes(target: str, taken: set[str]) -> bool:
    """Is `target` one of `taken`, or a numbered item of one ("name 2.mp4"
    of a post saved as "name.mp4", decision 24)?"""
    path = Path(target)
    numbered = re.fullmatch(r"(.+) \d+", path.stem)
    return _same_path(target) in taken or bool(
        numbered and _same_path(str(path.with_name(numbered.group(1) + path.suffix))) in taken)

# The list survives closing (Phase 2 item 2, 2026-10-24): these fields of
# each row are kept in data/jobs.json. Never a cookie: not the cookie file's
# path, not its note -- the error words are already washed (decision 37).
_KEPT = ("id", "url", "mode", "quality", "title", "folder", "target", "tool",
         "platform", "skipped", "skip_reason", "state", "files", "error",
         "error_from_tool", "limit_minutes", "live", "interrupted", "note", "pieces",
         "subs", "sub_lang", "items", "group", "group_title", "group_index", "post_part")
# Rows kept; the oldest finished ones go first. Measured 2026-11-01 with the
# page's own refresh(): each update while downloading took 14-19 ms at 200
# rows, 40 ms at 500, 84-91 ms at 1,000 (felt as stutter), 177-217 ms at
# 2,000; a save of jobs.json 4 ms at 500. 500 holds a 182-video playlist,
# one row per video, beside 300 older rows.
HISTORY_LIMIT = 500

# Each video or file of a row that holds several (the user, 2026-10-31: "see
# the process of all videos in the list, not only for yt-dlp"). Read from the
# lines each program prints, all seen 2026-10-31 (docs/BELIEFS.md):
#   yt-dlp 2026.10.29, a playlist: "[download] Downloading item 2 of 4", then
#     that item's progress; an item that fails says "ERROR: [youtube] <id>: …"
#     and yt-dlp goes on to the next one.
#   XHS-Downloader, a note of 2 pictures: "文件 <name> 下载成功" per file, all
#     at the end -- no count before, no progress.
#   gallery-dl, a Pinterest pin: the path of each finished file, one per
#     line; "# <path>" for a file already there.
# TikTokDownloader and KS-Downloader fetch one video per link: nothing to list.
ITEM_RUNNING, ITEM_DONE, ITEM_FAILED, ITEM_STOPPED, ITEM_THERE, ITEM_MISSED = (
    "running", "done", "failed", "stopped", "there", "missed")
ITEMS_KEPT = 2000           # a 5,000-video channel must not fill jobs.json
# Programs that fetch a whole post in one run: their files become one row
# each once it ends (`Queue._split_post`, 2026-11-01).
POST_TOOLS = ("xhs-downloader", "gallery-dl")
_ITEM_START = re.compile(r"^\[download\] Downloading item (\d+) of (\d+)")
_ITEM_ERROR = re.compile(r"^ERROR: \[[^\]]+\] [^:\s]+: (.+)")
_PLAYLIST_END = "[download] Finished downloading playlist"
_XHS_FILE = re.compile(r"^文件 (.+) 下载成功\s*$")
_WINDOWS_PATH = re.compile(r"^(# )?[A-Za-z]:\\")


def _item(title: str = "", state: str = WAITING) -> dict:
    return {"title": title, "state": state, "error": ""}


def _read_item_line(job: "Job", text: str) -> None:
    """Move the row's items on, from one line its program printed. Call with
    the queue's lock held."""
    line = text.strip()
    if job.tool == "yt-dlp":
        start = _ITEM_START.match(line)
        if start:
            number, count = int(start.group(1)), int(start.group(2))
            # The card's titles fill the list beforehand; a post read with
            # none (several links at once) gets its places as they come.
            while len(job.items) < min(count, ITEMS_KEPT):
                job.items.append(_item())
            for item in job.items:
                if item["state"] == ITEM_RUNNING:
                    item["state"] = ITEM_DONE
            if number <= len(job.items):
                job.items[number - 1]["state"] = ITEM_RUNNING
            return
        if line.startswith(_PLAYLIST_END):
            # The last item came through. Without this, a playlist whose 1st
            # video failed ended "failed" as a whole, and its 2nd video --
            # downloaded -- was marked failed with it (test of 2026-10-31).
            for item in job.items:
                if item["state"] == ITEM_RUNNING:
                    item["state"] = ITEM_DONE
            return
        # Any ERROR line fails the video it came during. Only the
        # "[site] id: reason" shape was read, and a video that failed with
        # "unable to download video data: HTTP Error 403" or "Postprocessing:"
        # was marked done when the next one began (hunt of 2026-11-08).
        if line.startswith("ERROR:"):
            failed = _ITEM_ERROR.match(line)
            reason = failed.group(1) if failed else line[len("ERROR:"):].strip()
            for item in job.items:
                if item["state"] == ITEM_RUNNING:
                    item["state"] = ITEM_FAILED
                    item["error"] = cookies.redact(reason)[:200]
        return
    if len(job.items) >= ITEMS_KEPT:
        return
    if job.tool == "xhs-downloader":
        done = _XHS_FILE.match(line)
        if done:
            job.items.append(_item(done.group(1), ITEM_DONE))
    elif job.tool == "gallery-dl" and _WINDOWS_PATH.match(line):
        there = line.startswith("# ")
        job.items.append(_item(Path(line[2:] if there else line).name,
                               ITEM_THERE if there else ITEM_DONE))


def _end_items(job: "Job") -> None:
    """The run is over: the item it was on ends with it. Lock held."""
    for item in job.items:
        if item["state"] == ITEM_RUNNING:
            item["state"] = {DONE: ITEM_DONE, ERROR: ITEM_FAILED}.get(job.state, ITEM_STOPPED)
        elif item["state"] == WAITING and job.state not in ACTIVE_STATES:
            # The run is over and never reached it: stopped or failed before,
            # or the playlist changed since the card read it. "Waiting" on a
            # row that has ended would be false (seen 2026-10-31).
            item["state"] = ITEM_MISSED


# Stop a tool AND every process it started (moved to children.py, 2026-10-18).
stop_tree = children.stop_tree


_INTERMEDIATE = re.compile(r"\.f\d+(-\d+)?\.[A-Za-z0-9]+$")    # name.f137.mp4, name.f251-1.webm


def _leftovers(destinations: list[Path], since: float,
               writing: list[Path] = ()) -> list[Path]:
    """What a STOPPED yt-dlp job leaves half-written, and nothing more.

    Asked by the user 2026-09-26: a stopped download left `cops.mp4.part`
    (4.1 MB) in his folder, which Teleloadzai never resumes. Deleting is
    dangerous, so the list is narrow on purpose:
      * only names yt-dlp itself announced for THIS job ("Destination:") --
        never a glob of the folder, where another job may be running;
      * their unfinished pieces: `.part`, `.ytdl`, `.part-FragN`;
      * a picture-only / sound-only piece (`name.f137.mp4`) ONLY if it was
        written after the job started -- never a file that was already there.
    The finished file of the user's own name is never on the list -- except
    in ``writing``: a file yt-dlp announced it was writing AFTER the download
    (the MP3 of "[ExtractAudio]", the `.temp` file of "[Merger]"), under this
    job's name and after its start. Stopped there, it is half a file, and the
    next try called it "already there" (2026-10-18).
    """
    found: list[Path] = []
    for piece in writing:
        try:
            if piece.is_file() and piece.stat().st_mtime >= since and piece not in found:
                found.append(piece)
        except OSError:
            pass
    for dest in destinations:
        pieces = [dest.with_name(dest.name + ".part"), dest.with_name(dest.name + ".ytdl")]
        pieces += list(dest.parent.glob(glob.escape(dest.name) + ".part-Frag*"))
        if _INTERMEDIATE.search(dest.name):
            pieces.append(dest)
        for piece in pieces:
            try:
                if piece.is_file() and piece.stat().st_mtime >= since and piece not in found:
                    found.append(piece)
            except OSError:
                pass
    return found


def _as_mp3(kept: list[Path], quality: str) -> list[Path]:
    """A kept live recording, when the user asked for an MP3: its sound at
    the kbps chosen. Until 2026-10-18 the row said "128 kbps" beside a .ts
    video (round 8). If FFmpeg fails, the recording stays as it is."""
    from .dialogs import free_name
    final: list[Path] = []
    for path in kept:
        target = path.with_name(free_name(path.parent, path.stem, "mp3") + ".mp3")
        try:
            final.append(runners._to_mp3(path, target, quality, on_start=children.bind))
        except Exception:
            final.append(path)
    return final


def _keep_recording(destinations: list[Path]) -> list[Path]:
    """The `.part` of a stopped yt-dlp live recording, renamed `<name>.ts`
    beside it -- never over a file of the user's (a free name)."""
    from .dialogs import free_name
    kept: list[Path] = []
    for dest in destinations:
        part = dest.with_name(dest.name + ".part")
        try:
            if not part.is_file() or part.stat().st_size == 0:
                continue
            stem = ytdlp.untagged(dest.stem)        # an MP3 run's tag goes
            target = dest.with_name(free_name(dest.parent, stem, "ts") + ".ts")
            os.rename(part, target)
            kept.append(target)
        except OSError:
            pass                # still held: it stays as .part, never deleted below
    return kept


@dataclass
class Job:
    id: str
    url: str
    mode: str
    quality: str
    title: str
    folder: str
    target: str = ""            # exact file chosen in the "Save as" window
    tool: str = "yt-dlp"        # the program that really runs, for the error buttons
    force: bool = False         # rewrite a file that is already there
    skipped: bool = False       # nothing was written, and the tool said why
    # The tool's own reason for skipping, when it gave one. yt-dlp's skip is
    # checked by the file's date and needs none; XHS-Downloader's is NOT
    # "already there" -- it skips anything in its own history (decision 38).
    skip_reason: str = ""
    limit_minutes: int = 60     # how long a live recording may last
    cookie_file: str = ""       # our copy of the cookie file, when it applies
    # Why this job runs WITHOUT the cookies although they are switched on.
    # Shown, never swallowed: otherwise the user turns cookies on, the download
    # still fails for not being logged in, and nothing ever says the tool was
    # never given them (decision 34).
    cookie_note: str = ""
    cookie_header: bool = False   # may this job use cookies as a header?
    platform: str = ""          # which site, so a failure can offer its log-in
    # Subtitles (Phase 2 item 7): "" off, "embed" inside the MP4, "file" a
    # .srt beside it; `sub_lang` the track's code ("en", "fr", "en-orig").
    subs: str = ""
    sub_lang: str = ""
    state: str = WAITING
    percent: str = ""
    speed: float = 0.0          # bytes per second, 0 when unknown
    eta: int | None = None      # seconds left, None when unknown
    # Bytes so far and the size, so the row can say "12.3 MB / 45.6 MB"
    # (asked by the user 2026-09-26). `total` 0 = not known -- a live stream,
    # or a tool that never says: then "12.3 MB so far", never a guessed size.
    done_bytes: int = 0
    total_bytes: int = 0
    estimated: bool = False     # the size is yt-dlp's estimate ("~")
    # (time, bytes) of the last few seconds, for the specialist tools' speed.
    samples: list[tuple[float, int]] = field(default_factory=list, repr=False)
    files: list[str] = field(default_factory=list)
    # Each video or file of a row that holds several: {"title", "state",
    # "error"}; state is WAITING or one of the ITEM_ states above.
    items: list[dict] = field(default_factory=list)
    # A playlist is one row per video (the user, 2026-11-01): its rows share
    # a `group` (an id made when it was added), its name, and their place
    # in it, so the list keeps them together, in order, under one label.
    group: str = ""
    group_title: str = ""
    group_index: int = 0
    # A picture of a post split one row per file (`_split_post`), not its
    # first: it cannot be downloaded again alone -- the program fetches the
    # whole post -- so only the first row offers it.
    post_part: bool = False
    error: str = ""
    error_from_tool: bool = False   # is `error` the tool's own words? (decision 38)
    # A finished job's one plain sentence about what it did not get: "Saved
    # without a cover picture." (Phase 2 item 5, decision 34).
    note: str = ""
    # A failed yt-dlp job's unfinished pieces, left in the folder for a Retry
    # to pick up: the row says they are there (a Bilibili video, 2026-10-24:
    # its whole sound and 1.4 MB of picture, and the row said nothing).
    pieces: list[str] = field(default_factory=list)
    # When the job started running. Until a tool prints a percentage there is
    # nothing else true to show, and a silent 0% bar looks frozen (decision
    # 33). Seen 2026-09-25: 12 to 18 s of nothing at the start of every
    # yt-dlp download.
    started: float = 0.0
    part: str = ""              # "picture" / "sound" while yt-dlp fetches that part
    step: str = ""              # "joining picture and sound", "making the MP3"
    # When that step began: "Making the MP3… 30 s" counted from the start of
    # the whole row, while the MP3 itself had taken 2 s (seen 2026-10-31).
    step_started: float = 0.0
    # The files yt-dlp said it was writing, for this job only. After a Stop,
    # their unfinished pieces are removed -- and nothing else (`_leftovers`).
    destinations: list[Path] = field(default_factory=list, repr=False)
    writing: list[Path] = field(default_factory=list, repr=False)
    live: bool = False          # yt-dlp said it is recording a live stream
    limit_reached: bool = False # ...and its time limit ended it (on_live)
    # Stopped because Teleloadzai closed, not by the user: its half-written
    # file is KEPT, and the row offers Continue at the next start.
    interrupted: bool = False
    process: subprocess.Popen | None = field(default=None, repr=False)
    # Set by Stop, for the steps that hold no process: a server tool reading
    # the post, our own fetch of its file (runners.Request.stop).
    stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def _on_disk(self) -> dict:
        """For a row that has ended with files (a finished one, a live
        recording stopped): {"on_disk": files still there, "disk_bytes": their
        size}. A file moved or deleted since is said."""
        if self.state not in (DONE, CANCELLED) or not self.files:
            return {}
        present, size = 0, 0
        for name in self.files:
            try:
                size += os.stat(name).st_size
                present += 1
            except OSError:
                pass
        return {"on_disk": present, "disk_bytes": size}

    def as_dict(self) -> dict:
        """What the UI sees. The process handle never leaves this module."""
        return {
            "id": self.id, "url": self.url, "mode": self.mode, "quality": self.quality,
            "title": self.title, "folder": self.folder, "target": self.target,
            "tool": self.tool, "force": self.force, "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "state": self.state, "percent": self.percent, "speed": self.speed,
            "eta": self.eta, "done_bytes": self.done_bytes, "total_bytes": self.total_bytes,
            "estimated": self.estimated, "files": self.files, "error": self.error,
            "items": self.items,
            "group": self.group, "group_title": self.group_title, "group_index": self.group_index,
            "post_part": self.post_part,
            # The first row of a split post: its "Download again" fetches
            # the whole post, and says so.
            "post_head": bool(self.group) and self.group == self.id,
            "note": self.note,
            # Asked to the disk at each refresh, like the finished files: a
            # piece the user deleted is no longer said.
            "pieces_on_disk": sum(1 for p in self.pieces if os.path.isfile(p))
                              if self.state == ERROR else 0,
            # A finished row's files as they are NOW on the disk: how many are
            # still there, and their size -- asked to the files themselves,
            # never remembered (the compact finished row, 2026-10-24).
            **self._on_disk(),
            # The PATH never leaves this module -- only whether cookies were
            # used, and the reason when they were not.
            # Either road counts. Saying "no cookies" after a job that used
            # them as a header would be a small lie the user cannot check.
            "with_cookies": bool(self.cookie_file) or self.cookie_header,
            "cookie_note": self.cookie_note,
            "platform": self.platform,
            # Did the tool itself blame a missing log-in? Only then may the
            # page say an account is needed rather than merely offer one.
            "needs_login": bool(self.error) and cookies.needs_login(self.error),
            # What the error means -- only for errors we have really met
            # (decision 38). {"known": False} makes the page say so honestly.
            "explain": explain.explain(self.error, self.tool),
            "error_from_tool": self.error_from_tool,
            # Seconds since it started, measured here: the page and this
            # server share a clock, but the server is the one that knows.
            "elapsed": int(time.time() - self.started)
                       if self.state == RUNNING and self.started else 0,
            "part": self.part,
            "step": self.step,
            "step_elapsed": int(time.time() - self.step_started)
                            if self.state == RUNNING and self.step and self.step_started else 0,
            # A live recording and its limit: the row said "Downloading" over
            # an empty bar, never "live" nor "of 60 min" (loop round 2,
            # 2026-10-23). streamlink only ever records live streams.
            "live": self.live or self.tool == "streamlink",
            "limit_minutes": self.limit_minutes,
            "interrupted": self.interrupted,
            "subs": self.subs, "sub_lang": self.sub_lang,
        }


class Queue:
    """Holds the jobs and decides when each one starts."""

    def __init__(self, max_parallel: Callable[[], int], store: Path | None = None) -> None:
        self._max_parallel = max_parallel
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []          # oldest first
        self._lock = threading.RLock()
        self._workers: set[threading.Thread] = set()
        # Tools being updated: their waiting jobs do not start meanwhile.
        self._held: set[str] = set()
        # Where the list is kept between two runs (None: not kept, in tests).
        self._store = store
        self._save_lock = threading.Lock()
        # Said once on the page when the kept list could not be read.
        self.load_problem = ""
        self._store_blocked = False    # a bad list that could not be set aside

    # -- the list kept between two runs ---------------------------------------

    def load(self) -> None:
        """Bring back the list of the last run. A row that was waiting or
        running then (a crash, a closed console) comes back interrupted:
        nothing starts by itself (the user's choice, 2026-10-24)."""
        if self._store is None or not self._store.is_file():
            return
        try:
            rows = json.loads(self._store.read_text(encoding="utf-8"))["jobs"]
            loaded = []
            for row in rows:
                kept = {k: row[k] for k in _KEPT if k in row}
                job = Job(**kept)
                if job.state in ACTIVE_STATES:
                    job.state, job.interrupted = CANCELLED, True
                    _end_items(job)
                loaded.append(job)
        except (OSError, ValueError, KeyError, TypeError) as problem:
            # Never a silent empty list (decision 34): the file is kept aside
            # under another name, and the page says so once.
            # A name of its own each time: a second bad file never replaces
            # the first one kept (hunt of 2026-10-31).
            aside, number = self._store.with_name("jobs (unreadable).json"), 2
            while aside.exists():
                aside, number = self._store.with_name(f"jobs (unreadable {number}).json"), number + 1
            try:
                os.replace(self._store, aside)
            except OSError as moved:
                # Not set aside: then it must not be written over either.
                self._store_blocked = True
                self.load_problem = (f"The list of your last downloads could not be read "
                                     f"({type(problem).__name__}), nor set aside ({moved.strerror}). "
                                     f"It is left as it is in {self._store.parent}, and this "
                                     f"session's downloads are not kept in it.")
                return
            self.load_problem = (f"The list of your last downloads could not be read "
                                 f"({type(problem).__name__}). It was kept as {aside.name}.")
            return
        with self._lock:
            for job in loaded[-HISTORY_LIMIT:]:
                self._jobs[job.id] = job
                self._order.append(job.id)

    def save(self) -> None:
        """Write the list, newest HISTORY_LIMIT rows, to a temporary file
        first, then put it in place: a crash mid-write never leaves half a
        list (CLAUDE.md §2.2)."""
        if self._store is None or self._store_blocked:
            return
        # The list is taken INSIDE the save lock: taken outside, two downloads
        # ending together could write the older list last, and after a crash
        # a finished row came back "interrupted" (hunt of 2026-10-31).
        with self._save_lock:
            with self._lock:
                # The oldest finished rows go first; a row in progress never does.
                extra = len(self._order) - HISTORY_LIMIT
                for job_id in [i for i in self._order if self._jobs[i].state not in ACTIVE_STATES][:max(0, extra)]:
                    del self._jobs[job_id]
                    self._order.remove(job_id)
                rows = [{k: getattr(self._jobs[i], k) for k in _KEPT} for i in self._order]
            text = json.dumps({"version": 1, "jobs": rows}, ensure_ascii=False, indent=1)
            temp = self._store.with_name(self._store.name + ".tmp")
            try:
                self._store.parent.mkdir(parents=True, exist_ok=True)
                temp.write_text(text, encoding="utf-8")
                os.replace(temp, self._store)
            except OSError as problem:
                # The downloads go on; only the memory of them is not kept.
                print(f"Could not keep the list of downloads: {problem}")

    def rescued(self, saved: list[tuple[str, Path]]) -> None:
        """Rows whose file the start-up sweep saved from a crash: done, with
        that file -- "Continue" made a second copy, "name (2)" (hunt of
        2026-10-31)."""
        with self._lock:
            for job_id, path in saved:
                job = self._jobs.get(job_id) if job_id else None
                if job is None or not job.interrupted or not path.is_file():
                    continue
                if str(path) not in job.files:
                    job.files.append(str(path))
                job.state, job.interrupted = DONE, False
                job.note = "Saved from the download cut off last time."
        self.save()

    def unfinished(self) -> int:
        """Downloads waiting or running now: asked before the window closes."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.state in ACTIVE_STATES)

    def targets_in_use(self, besides: str = "") -> set[str]:
        """The files that waiting or running jobs will write. Windows only
        asks about a file already on the disk: two untitled videos of
        "Choose for each" both got "unknown.mp4", and the second replaced the
        first while both rows said done (hunt of 2026-10-31). A job with no
        "Save as" name counts by its title, the name its program will most
        likely give: a later "Save as" of the same title replaced it."""
        with self._lock:
            return self._taken(besides)

    def _taken(self, besides: str) -> set[str]:
        from .dialogs import safe_filename, without_media_ending
        taken = set()
        for job_id, job in self._jobs.items():
            if job.state not in ACTIVE_STATES or job_id == besides:
                continue
            if job.target:
                taken.add(_same_path(job.target))
            elif job.title:
                stem = safe_filename(without_media_ending(job.title), fallback="")
                if stem:
                    taken.add(_same_path(str(Path(job.folder) / f"{stem}.{job.mode}")))
        return taken

    # -- public ------------------------------------------------------------

    def add(self, url: str, mode: str, quality: str, title: str, folder: Path,
            target: Path | None = None, force: bool = False,
            tool: str = "yt-dlp", limit_minutes: int = 60,
            cookie_file: Path | None = None, cookie_note: str = "",
            platform: str = "", cookie_header: bool = False,
            replace: str = "", subs: str = "", sub_lang: str = "",
            items: list[str] | None = None,
            group: tuple[str, str, int] | None = None) -> Job | None:
        """Queue a download. With ``replace``, it takes the place of that
        finished job -- same id, same spot in the list -- instead of adding a
        row: a Retry used to leave the failed row behind, one more each time.
        Returns None when ``replace`` is unknown or still running.

        ``items``: the titles of a playlist, as the card read them, so every
        video is listed and waiting from the start. A Retry keeps the old
        row's titles, every item waiting again."""
        job = Job(
            id=replace or uuid.uuid4().hex[:12], url=url, mode=mode, quality=quality,
            title=title, folder=str(target.parent if target else folder),
            target=str(target) if target else "", force=force, tool=tool,
            limit_minutes=limit_minutes,
            cookie_file=str(cookie_file) if cookie_file else "",
            cookie_note=cookie_note, platform=platform,
            cookie_header=cookie_header, subs=subs, sub_lang=sub_lang,
        )
        if group:
            job.group, job.group_title, job.group_index = group
        with self._lock:
            # Checked and added in one step: two requests at once cannot both
            # pass with the same file.
            if target and target_clashes(str(target), self._taken(replace)):
                raise TargetInUse(Path(target).name)
            if replace:
                old = self._jobs.get(replace)
                if old is None or old.state in ACTIVE_STATES:
                    return None
                if items is None and job.tool == "yt-dlp":
                    items = [item.get("title", "") for item in old.items]
                if old.group and old.group == old.id:
                    # "Download again" on a split post fetches the whole post:
                    # its other picture rows go, the new run splits again.
                    for other in [i for i in self._order
                                  if i != replace and self._jobs[i].group == old.group]:
                        del self._jobs[other]
                        self._order.remove(other)
                    job.title = old.group_title     # the post's name, not its 1st file's
                elif not group:             # a Retry stays in its playlist
                    job.group, job.group_title, job.group_index = (
                        old.group, old.group_title, old.group_index)
                self._jobs[replace] = job           # its place in _order stays
            else:
                self._jobs[job.id] = job
                self._order.append(job.id)
            if items:
                job.items = [_item(str(title)[:300]) for title in items[:ITEMS_KEPT]]
        self._pump()
        self.save()
        return job

    def _split_post(self, job: Job) -> None:
        """A post of several files ends as one row per file (the user,
        2026-11-01: "always one video by one video", for every program).
        XHS-Downloader and gallery-dl fetch a whole post in one run and name
        each file only at the end (seen 2026-10-31), so the rows are made
        here, once it is over, under one label: the post's name. Lock held."""
        if job.tool not in POST_TOOLS or job.skipped or len(job.files) < 2:
            return
        files = list(job.files)
        job.group, job.group_title, job.group_index = job.id, job.title or "Post", 1
        job.files, job.title = files[:1], Path(files[0]).stem
        at = self._order.index(job.id)
        for k, path in enumerate(files[1:], start=2):
            part = Job(id=uuid.uuid4().hex[:12], url=job.url, mode=job.mode, quality=job.quality,
                       title=Path(path).stem, folder=job.folder, tool=job.tool,
                       platform=job.platform, state=DONE, percent="100%", files=[path],
                       group=job.group, group_title=job.group_title, group_index=k,
                       post_part=True)
            self._jobs[part.id] = part
            self._order.insert(at + k - 1, part.id)

    def all(self) -> list[dict]:
        """Newest first, which is the order the UI shows."""
        with self._lock:
            return [self._jobs[i].as_dict() for i in reversed(self._order)]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state not in ACTIVE_STATES:
                return False
            job.state = CANCELLED
            job.stop.set()
            process = job.process
        if process and process.poll() is None:
            stop_tree(process)      # the worker sees CANCELLED and stays quiet
        self._pump()
        self.save()
        return True

    # Retry lives in server.py now (`queue_download(..., replace=)`): it must
    # decide the cookies from the CURRENT settings, which this module does not
    # read. Copying the failed attempt's choice made a Retry after a log-in
    # run without the log-in (found 2026-09-23).

    def busy(self, tool_id: str) -> int:
        """How many running downloads use this tool now. FFmpeg serves them
        all (joining, MP3), so every running download counts for it.
        Decision 19, changed 2026-10-21: a tool is never updated while it
        downloads -- and only that tool waits, not the others."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.state == RUNNING
                       and (j.tool == tool_id or tool_id == "ffmpeg"))

    def hold(self, tool_id: str) -> None:
        """No new download of this tool starts until `release`."""
        with self._lock:
            self._held.add(tool_id)

    def release(self, tool_id: str) -> None:
        with self._lock:
            self._held.discard(tool_id)
        self._pump()

    def stop_all(self) -> int:
        """Stop every job, waiting or running. Used when the app closes:
        until 2026-10-18 a download went on unseen after the window closed,
        and yt-dlp wrote its cookie jar back after "Forget when I close".
        Since 2026-10-24 each one is marked INTERRUPTED: it keeps its
        half-written file and comes back at the next start, to continue."""
        with self._lock:
            active = [i for i in self._order if self._jobs[i].state in ACTIVE_STATES]
            for job_id in active:           # waiting ones first: none may start
                self._jobs[job_id].state = CANCELLED
                self._jobs[job_id].interrupted = True
                self._jobs[job_id].stop.set()
            processes = [self._jobs[i].process for i in active]
            workers = list(self._workers)
        for process in processes:
            if process and process.poll() is None:
                stop_tree(process)
        # A few seconds for each worker to clean its work folder: these are
        # daemon threads, and the app's exit used to cut them off half-way.
        # What is still left is dealt with at the next start.
        deadline = time.time() + 8
        for worker in workers:
            worker.join(max(0.0, deadline - time.time()))
        self.save()
        return len(active)

    def remove(self, job_id: str) -> bool:
        """Take ONE finished row off the list. A failed row whose link is the
        problem ("This video is private") had no button at all, and "Clear
        finished" took every other row with it (review of 2026-09-27)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state in ACTIVE_STATES:
                return False
            del self._jobs[job_id]
            self._order.remove(job_id)
        self.save()
        return True

    def clear_all(self) -> int:
        """Every ended row -- done, "already there", stopped AND failed: the
        list's "Remove all" (the user, 2026-10-26: three Bilibili failures took
        six clicks to clear). Never a running, waiting or interrupted one. The
        files stay on the disk: only the rows go."""
        with self._lock:
            ended = [i for i in self._order if self._jobs[i].state in (DONE, CANCELLED, ERROR)
                     and not self._jobs[i].interrupted]
            for job_id in ended:
                del self._jobs[job_id]
                self._order.remove(job_id)
        self.save()
        return len(ended)

    def clear_finished(self) -> int:
        """Done, "already there" and stopped rows -- never a failed one: its
        words and its Retry went with the rest in one click, and "finished"
        reads as "succeeded" (loop round 1, 2026-10-23). A failed row has
        its own Remove. Nor an interrupted one: it is not finished."""
        with self._lock:
            finished = [i for i in self._order if self._jobs[i].state in ("done", "cancelled")
                        and not self._jobs[i].interrupted]
            for job_id in finished:
                del self._jobs[job_id]
                self._order.remove(job_id)
        self.save()
        return len(finished)

    # -- inside ------------------------------------------------------------

    def _pump(self) -> None:
        """Start waiting jobs while there is a free slot."""
        with self._lock:
            running = sum(1 for j in self._jobs.values() if j.state == RUNNING)
            free = max(0, self._max_parallel() - running)
            starting = []
            for job_id in self._order:
                if free <= 0:
                    break
                job = self._jobs[job_id]
                if job.tool in self._held or "ffmpeg" in self._held:
                    continue            # its tool is being updated
                if job.state == WAITING:
                    job.state = RUNNING
                    job.started = time.time()
                    starting.append(job)
                    free -= 1

        for job in starting:
            worker = threading.Thread(target=self._work, args=(job,), daemon=True)
            with self._lock:
                self._workers.add(worker)
            worker.start()

    def _work(self, job: Job) -> None:
        # The Console page (2026-10-25): a title line, then what the program
        # says, then how it ended. The name, never a cookie path.
        from .platforms import tool_name
        console.add(job.id, f"{job.title or job.url} · {tool_name(job.tool)}", "head")

        def on_line(text: str) -> None:
            console.add(job.id, text)
            with self._lock:
                _read_item_line(job, text)

        def on_progress(progress: ytdlp.Progress) -> None:
            with self._lock:
                job.percent, job.speed, job.eta = progress.percent, progress.speed, progress.eta
                job.part = progress.part
                job.done_bytes, job.total_bytes = progress.done, progress.total
                job.estimated = progress.estimated

        def on_step(step: str) -> None:
            with self._lock:
                if step != job.step:
                    job.step_started = time.time()
                job.step = step
            # TikTokDownloader and KS-Downloader print nothing we read: their
            # steps are what the console can say of them.
            console.add(job.id, step[:1].upper() + step[1:] + "…")

        def on_start(process: subprocess.Popen) -> None:
            # It dies with Teleloadzai, even when the app is killed (children.py).
            children.bind(process)
            with self._lock:
                job.process = process
                # Cancelled while it was still starting up.
                if job.state == CANCELLED:
                    stop_tree(process)

        def on_destination(path: Path) -> None:
            with self._lock:
                job.destinations.append(path)

        def on_title(title: str) -> None:
            """yt-dlp's own title, for a row added with none read (several
            links at once). A title the card read is never replaced."""
            with self._lock:
                if not job.title:
                    job.title = title
            self.save()

        def on_live() -> None:
            """yt-dlp is recording a live stream. The "Stop a live recording
            after" setting reached streamlink only, while Settings promised
            it for every live (round 7, 2026-10-18: a 1-minute limit, still
            recording after 80 s). Here it ends the recording itself, and
            the row ends DONE on the kept file, not "stopped"."""
            with self._lock:
                job.live = True
            if job.limit_minutes > 0:
                timer = threading.Timer(job.limit_minutes * 60, end_live)
                timer.daemon = True
                timer.start()

        def end_live() -> None:
            with self._lock:
                if job.state != RUNNING:
                    return
                job.limit_reached = True
                process = job.process
            if process and process.poll() is None:
                stop_tree(process)

        def on_writing(path: Path) -> None:
            with self._lock:
                job.writing.append(path)

        def on_final(path: Path) -> None:
            """yt-dlp's last word on a file: it and its subtitle files are
            the user's now, never a leftover (a Stop during the next video
            of the same run deleted them, hunt of 2026-11-08)."""
            def finished(piece: Path) -> bool:
                return piece == path or (piece.parent == path.parent
                    and piece.name.startswith(path.stem + ".")
                    and piece.suffix.lower() in (".srt", ".vtt", ".ass"))
            with self._lock:
                job.writing = [p for p in job.writing if not finished(p)]

        def on_percent(percent: int) -> None:
            """The specialist tools give a bare number, not yt-dlp's three fields."""
            with self._lock:
                job.percent = f"{percent}%"

        def on_bytes(done: int, total: int) -> None:
            """Bytes from a specialist tool: our own fetch (with the size the
            site sent) or what grew in the folder (no size). The speed is
            measured over the last 5 s; the time left only with a size."""
            now = time.time()
            with self._lock:
                if done < job.done_bytes:
                    job.samples = []        # pieces joined into one file: restart
                job.samples = [s for s in job.samples if now - s[0] <= 5] + [(now, done)]
                first_time, first_done = job.samples[0]
                job.done_bytes, job.total_bytes = done, total
                if now - first_time >= 1:
                    job.speed = max(0.0, (done - first_done) / (now - first_time))
                if total and job.speed > 0:
                    job.eta = int((total - done) / job.speed)

        def run_tool(cookie_file: Path | None):
            if job.tool == "yt-dlp":
                return ytdlp.download(
                    job.url, job.mode, Path(job.folder),
                    on_progress=on_progress, quality=job.quality, on_start=on_start,
                    out_path=Path(job.target) if job.target else None,
                    force=job.force, cookie_file=cookie_file, on_step=on_step,
                    on_destination=on_destination, on_writing=on_writing, on_final=on_final,
                    on_live=on_live, on_title=on_title, job_id=job.id,
                    subs=job.subs, sub_lang=job.sub_lang, on_line=on_line,
                )
            else:
                # A specialist tool cannot be told an exact file name, so it
                # gets the folder the user chose and names the file itself.
                target = Path(job.target) if job.target else None
                return runners.run(
                    job.tool,
                    runners.Request(
                        url=job.url,
                        out_dir=target.parent if target else Path(job.folder),
                        out_name=target.stem if target else "",
                        out_file=target.name if target else "",
                        title=job.title,
                        mode=job.mode, quality=job.quality,
                        limit_minutes=job.limit_minutes, force=job.force,
                        cookie_file=cookie_file,
                        # TikTokDownloader wants a cookie STRING, not a file,
                        # so it cannot read `cookie_file`. This says it may
                        # ask for one.
                        cookie_header=job.cookie_header,
                        stop=job.stop,
                        subs=job.subs, sub_lang=job.sub_lang, job_id=job.id,
                    ),
                    on_progress=on_percent, on_start=on_start, on_step=on_step,
                    on_bytes=on_bytes, on_line=on_line,
                )

        try:
            # Each run gets its own copy of the cookie file: yt-dlp and
            # gallery-dl write their jar back when they exit (cookies.py).
            cookie_file = Path(job.cookie_file) if job.cookie_file else None
            with cookies.for_one_run(cookie_file) as run_cookies:
                result = run_tool(run_cookies)

            # Every program's MP3 is asked, in the file itself, whether it got
            # its cover (Phase 2 item 5) -- not the log. Outside the lock:
            # ffprobe takes a moment per file.
            note = ""
            if job.mode == "mp3":
                made = [f for f in result.files if f not in getattr(result, "skipped", [])]
                # The kbps only for yt-dlp: the other programs' MP3 is made
                # by our FFmpeg, always at the kbps asked (measured 2026-09-26
                # and again 2026-10-24).
                note = " ".join(filter(None, [
                    ytdlp.kbps_note(made, job.quality) if job.tool == "yt-dlp" else "",
                    ytdlp.cover_note(made)]))
            elif job.subs:
                # Subtitles asked: are they in the file / beside it (item 7)?
                made = [f for f in result.files if f not in getattr(result, "skipped", [])]
                note = ytdlp.subs_note(made, job.subs)

            with self._lock:
                # A stopped row keeps files only for a live recording, which
                # Stop ends without throwing away. A stopped yt-dlp job's
                # files are deleted below as leftovers: never shown.
                if job.state != CANCELLED or job.tool in runners.LIVE_RECORDERS:
                    job.files = [str(p) for p in result.files]
                if job.state != CANCELLED:
                    # Say the truth: the file was already there and nothing
                    # was written. "Done" would be a lie the user cannot see.
                    job.skipped = result.nothing_downloaded
                    job.skip_reason = getattr(result, "skip_reason", "")
                    job.note = note
                    job.state = DONE
                    job.percent = "100%"
                    self._split_post(job)
        except Exception as exc:
            with self._lock:
                limit = job.limit_reached and job.state == RUNNING
                destinations = list(job.destinations)
            if limit:
                # Ended by its time limit: a finished recording, not an error.
                kept = _keep_recording(destinations)
                if job.mode == "mp3":
                    kept = _as_mp3(kept, job.quality)
                with self._lock:
                    job.files = [str(p) for p in kept]
                    job.state = DONE
                    job.percent = "100%"
                    if not kept:
                        job.state = ERROR
                        job.error = ("The live recording reached its time limit, but its "
                                     "file could not be renamed. Look for a .part file "
                                     "in the folder.")
            with self._lock:
                if limit:
                    pass                        # said above: done, or why not
                elif job.state == CANCELLED and getattr(exc, "keep_work", False):
                    # A stopped recording that could not be moved out: it is
                    # kept aside, and the row says so instead of nothing.
                    job.error = str(exc)
                elif job.state != CANCELLED:    # a cancel is not a failure
                    job.state = ERROR
                    job.error = str(exc)
                    job.error_from_tool = explain.said_by_tool(exc)
                    # Files a tool finished before it failed (3 pictures of
                    # 8): shown on the row, never as the download itself.
                    job.files = [str(f) for f in getattr(exc, "saved", [])]
        finally:
            with self._lock:
                job.process = None
                _end_items(job)
                stopped = job.state == CANCELLED
                failed = job.state == ERROR
                destinations = list(job.destinations)
                writing = list(job.writing)
                live = job.live
                interrupted = job.interrupted
            # A live recording ended by Stop is KEPT, not cleaned up: yt-dlp
            # writes it as `<name>.part` in MPEG-TS (its default for a live
            # stream), so it becomes `<name>.ts` under a free name.
            if stopped and live:
                kept = _keep_recording(destinations)
                if job.mode == "mp3":
                    kept = _as_mp3(kept, job.quality)
                with self._lock:
                    job.files = [str(p) for p in kept]
            # Here the tool has ended (download() returned), so Windows no
            # longer holds its files open and they can go. Never after a live
            # recording: a `.part` that could not be renamed is still it.
            # Interrupted by the app closing: its `.part` stays, so Continue
            # can pick it up (yt-dlp resumes it, unless "Save as" chose the
            # name: then it starts again, --force-overwrites says no-continue).
            if stopped and not live and not interrupted:
                for piece in _leftovers(destinations, job.started - 2, writing):
                    try:
                        piece.unlink()
                    except OSError:
                        pass            # still held: a leftover, never a crash
            # A failure keeps its pieces -- yt-dlp picks them up on Retry --
            # and remembers them, so the row can say where they are. The same
            # narrow list as a Stop's: only names announced for THIS job. An
            # interrupted row too: removing it must still say they are there.
            if (failed or (stopped and interrupted)) and not live:
                pieces = [str(p) for p in _leftovers(destinations, job.started - 2, writing)]
                with self._lock:
                    job.pieces = pieces
            # A Windows message when the user is elsewhere (Phase 2 item 6).
            # Not for a Stop: the user did it, and is looking.
            with self._lock:
                state, skipped, count = job.state, job.skipped, len(job.files)
                error = job.error
            # What the site needs, kept true by real results (the user,
            # 2026-10-25: "the needs may change with the updates"). Worked
            # with no cookies -> "none"; with only a visit -> "visit"; the
            # program asked for a log-in -> "account". Logged in proves
            # nothing about the need, so nothing is written then.
            try:
                given = bool(job.cookie_file) or job.cookie_header
                if state == DONE and not skipped and job.platform:
                    seen = login.site_state(job.platform) if given else "none"
                    if seen in ("none", "visited"):
                        needs.record(job.platform, job.tool, "visit" if seen == "visited" else "none")
                elif state == ERROR and job.platform and cookies.needs_login(error):
                    needs.record(job.platform, job.tool, "account")
            except Exception:
                pass            # a line not updated is never a failed download
            # The console's last line for this download, in our words.
            # A failure is red, like a failed install or title read (grids of
            # 2026-10-26: downloads ended grey, installs red).
            console.add(job.id, "Done." if state == DONE and not skipped
                        else "Already there: nothing was downloaded." if state == DONE
                        else f"Failed: {error}" if state == ERROR else "Stopped.",
                        "err" if state == ERROR else "end")
            with self._lock:
                saved = Path(job.files[0]).name if job.files else ""
                # Never the link: a message on the screen says a name only
                # ("A download failed" when there is none).
                named = job.title or saved
            if state == DONE and count > 1 and not skipped:
                # A playlist in one row: its title and how many files.
                notify.ended(named, "done", count)
            elif state == DONE:
                # A playlist already there is "already", never "finished"
                # (hunt of 2026-10-31), and named by its title.
                notify.ended(named if count > 1 else saved or named,
                             "already" if skipped else "done")
            elif state == ERROR:
                notify.ended(named, "failed")
            else:
                notify.check()      # stopped: maybe the last one running
            with self._lock:
                self._workers.discard(threading.current_thread())
            self._pump()
            self.save()
