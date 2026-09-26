"""The download queue.

A job waits, then runs, then finishes. Only a few run at the same time, so
ten pasted links do not fight for the same internet connection.

The queue owns the running process of each job, which is what makes
``cancel`` possible: it stops yt-dlp instead of waiting for it to end.
"""

from __future__ import annotations

import glob
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cookies, explain, runners, ytdlp

WAITING, RUNNING, DONE, ERROR, CANCELLED = "waiting", "running", "done", "error", "cancelled"
ACTIVE_STATES = (WAITING, RUNNING)


def stop_tree(process: subprocess.Popen) -> None:
    """Stop a tool AND every process it started.

    `yt-dlp.exe` is a launcher that starts the real yt-dlp as a second
    process. `terminate()` stopped the launcher only: seen 2026-09-26, a job
    stopped after 10 s kept downloading in the background and delivered the
    whole 164,088,517-byte file. `taskkill /T` follows the family while the
    launcher is still alive to name it -- so it runs first.
    """
    try:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass                    # the check below still stops what we hold
    if process.poll() is None:
        process.kill()


_INTERMEDIATE = re.compile(r"\.f\d+(-\d+)?\.[A-Za-z0-9]+$")    # name.f137.mp4, name.f251-1.webm


def _leftovers(destinations: list[Path], since: float) -> list[Path]:
    """What a STOPPED yt-dlp job leaves half-written, and nothing more.

    Asked by the user 2026-09-26: a stopped download left `cops.mp4.part`
    (4.1 MB) in his folder, which Teleloadzai never resumes. Deleting is
    dangerous, so the list is narrow on purpose:
      * only names yt-dlp itself announced for THIS job ("Destination:") --
        never a glob of the folder, where another job may be running;
      * their unfinished pieces: `.part`, `.ytdl`, `.part-FragN`;
      * a picture-only / sound-only piece (`name.f137.mp4`) ONLY if it was
        written after the job started -- never a file that was already there.
    The finished file of the user's own name is never on the list.
    """
    found: list[Path] = []
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
    error: str = ""
    error_from_tool: bool = False   # is `error` the tool's own words? (decision 38)
    # When the job started running. Until a tool prints a percentage there is
    # nothing else true to show, and a silent 0% bar looks frozen (decision
    # 33). Seen 2026-09-25: 12 to 18 s of nothing at the start of every
    # yt-dlp download.
    started: float = 0.0
    part: str = ""              # "picture" / "sound" while yt-dlp fetches that part
    step: str = ""              # "joining picture and sound", "making the MP3"
    # The files yt-dlp said it was writing, for this job only. After a Stop,
    # their unfinished pieces are removed -- and nothing else (`_leftovers`).
    destinations: list[Path] = field(default_factory=list, repr=False)
    process: subprocess.Popen | None = field(default=None, repr=False)

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
        }


class Queue:
    """Holds the jobs and decides when each one starts."""

    def __init__(self, max_parallel: Callable[[], int]) -> None:
        self._max_parallel = max_parallel
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []          # oldest first
        self._lock = threading.RLock()

    # -- public ------------------------------------------------------------

    def add(self, url: str, mode: str, quality: str, title: str, folder: Path,
            target: Path | None = None, force: bool = False,
            tool: str = "yt-dlp", limit_minutes: int = 60,
            cookie_file: Path | None = None, cookie_note: str = "",
            platform: str = "", cookie_header: bool = False,
            replace: str = "") -> Job | None:
        """Queue a download. With ``replace``, it takes the place of that
        finished job -- same id, same spot in the list -- instead of adding a
        row: a Retry used to leave the failed row behind, one more each time.
        Returns None when ``replace`` is unknown or still running."""
        job = Job(
            id=replace or uuid.uuid4().hex[:12], url=url, mode=mode, quality=quality,
            title=title, folder=str(target.parent if target else folder),
            target=str(target) if target else "", force=force, tool=tool,
            limit_minutes=limit_minutes,
            cookie_file=str(cookie_file) if cookie_file else "",
            cookie_note=cookie_note, platform=platform,
            cookie_header=cookie_header,
        )
        with self._lock:
            if replace:
                old = self._jobs.get(replace)
                if old is None or old.state in ACTIVE_STATES:
                    return None
                self._jobs[replace] = job           # its place in _order stays
            else:
                self._jobs[job.id] = job
                self._order.append(job.id)
        self._pump()
        return job

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
            process = job.process
        if process and process.poll() is None:
            stop_tree(process)      # the worker sees CANCELLED and stays quiet
        self._pump()
        return True

    # Retry lives in server.py now (`queue_download(..., replace=)`): it must
    # decide the cookies from the CURRENT settings, which this module does not
    # read. Copying the failed attempt's choice made a Retry after a log-in
    # run without the log-in (found 2026-09-23).

    def clear_finished(self) -> int:
        with self._lock:
            finished = [i for i in self._order if self._jobs[i].state not in ACTIVE_STATES]
            for job_id in finished:
                del self._jobs[job_id]
                self._order.remove(job_id)
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
                if job.state == WAITING:
                    job.state = RUNNING
                    job.started = time.time()
                    starting.append(job)
                    free -= 1

        for job in starting:
            threading.Thread(target=self._work, args=(job,), daemon=True).start()

    def _work(self, job: Job) -> None:
        def on_progress(progress: ytdlp.Progress) -> None:
            with self._lock:
                job.percent, job.speed, job.eta = progress.percent, progress.speed, progress.eta
                job.part = progress.part
                job.done_bytes, job.total_bytes = progress.done, progress.total
                job.estimated = progress.estimated

        def on_step(step: str) -> None:
            with self._lock:
                job.step = step

        def on_start(process: subprocess.Popen) -> None:
            with self._lock:
                job.process = process
                # Cancelled while it was still starting up.
                if job.state == CANCELLED:
                    stop_tree(process)

        def on_destination(path: Path) -> None:
            with self._lock:
                job.destinations.append(path)

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

        cookie_file = Path(job.cookie_file) if job.cookie_file else None

        try:
            if job.tool == "yt-dlp":
                result = ytdlp.download(
                    job.url, job.mode, Path(job.folder),
                    on_progress=on_progress, quality=job.quality, on_start=on_start,
                    out_path=Path(job.target) if job.target else None,
                    force=job.force, cookie_file=cookie_file, on_step=on_step,
                    on_destination=on_destination,
                )
            else:
                # A specialist tool cannot be told an exact file name, so it
                # gets the folder the user chose and names the file itself.
                target = Path(job.target) if job.target else None
                result = runners.run(
                    job.tool,
                    runners.Request(
                        url=job.url,
                        out_dir=target.parent if target else Path(job.folder),
                        out_name=target.stem if target else "",
                        title=job.title,
                        mode=job.mode, quality=job.quality,
                        limit_minutes=job.limit_minutes, force=job.force,
                        cookie_file=cookie_file,
                        # TikTokDownloader wants a cookie STRING, not a file,
                        # so it cannot read `cookie_file`. This says it may
                        # ask for one.
                        cookie_header=job.cookie_header,
                    ),
                    on_progress=on_percent, on_start=on_start, on_step=on_step,
                    on_bytes=on_bytes,
                )

            with self._lock:
                if job.state != CANCELLED:
                    job.files = [str(p) for p in result.files]
                    # Say the truth: the file was already there and nothing
                    # was written. "Done" would be a lie the user cannot see.
                    job.skipped = result.nothing_downloaded
                    job.skip_reason = getattr(result, "skip_reason", "")
                    job.state = DONE
                    job.percent = "100%"
        except Exception as exc:
            with self._lock:
                if job.state != CANCELLED:      # a cancel is not a failure
                    job.state = ERROR
                    job.error = str(exc)
                    job.error_from_tool = explain.said_by_tool(exc)
        finally:
            with self._lock:
                job.process = None
                stopped = job.state == CANCELLED
                destinations = list(job.destinations)
            # Here the tool has ended (download() returned), so Windows no
            # longer holds its files open and they can go.
            if stopped:
                for piece in _leftovers(destinations, job.started - 2):
                    try:
                        piece.unlink()
                    except OSError:
                        pass            # still held: a leftover, never a crash
            self._pump()
