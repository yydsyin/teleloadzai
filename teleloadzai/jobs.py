"""The download queue.

A job waits, then runs, then finishes. Only a few run at the same time, so
ten pasted links do not fight for the same internet connection.

The queue owns the running process of each job, which is what makes
``cancel`` possible: it stops yt-dlp instead of waiting for it to end.
"""

from __future__ import annotations

import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cookies, runners, ytdlp

WAITING, RUNNING, DONE, ERROR, CANCELLED = "waiting", "running", "done", "error", "cancelled"
ACTIVE_STATES = (WAITING, RUNNING)


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
    skipped: bool = False       # the file was already there and nothing was written
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
    speed: str = ""
    eta: str = ""
    files: list[str] = field(default_factory=list)
    error: str = ""
    process: subprocess.Popen | None = field(default=None, repr=False)

    def as_dict(self) -> dict:
        """What the UI sees. The process handle never leaves this module."""
        return {
            "id": self.id, "url": self.url, "mode": self.mode, "quality": self.quality,
            "title": self.title, "folder": self.folder, "target": self.target,
            "tool": self.tool, "force": self.force, "skipped": self.skipped,
            "state": self.state, "percent": self.percent, "speed": self.speed,
            "eta": self.eta, "files": self.files, "error": self.error,
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
            platform: str = "", cookie_header: bool = False) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12], url=url, mode=mode, quality=quality,
            title=title or url, folder=str(target.parent if target else folder),
            target=str(target) if target else "", force=force, tool=tool,
            limit_minutes=limit_minutes,
            cookie_file=str(cookie_file) if cookie_file else "",
            cookie_note=cookie_note, platform=platform,
            cookie_header=cookie_header,
        )
        with self._lock:
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
            process.terminate()     # the worker sees CANCELLED and stays quiet
        self._pump()
        return True

    def retry(self, job_id: str, force: bool = False) -> Job | None:
        """Queue the same download again, with the same name and quality.

        ``force`` is what "Download again" uses: the file is already there,
        the user has now said in so many words that it must be rewritten.
        """
        with self._lock:
            old = self._jobs.get(job_id)
            if old is None or old.state in ACTIVE_STATES:
                return None
            url, mode, quality = old.url, old.mode, old.quality
            title, folder, target = old.title, old.folder, old.target
            tool, limit_minutes = old.tool, old.limit_minutes
            # A retry keeps the cookies. Losing them here would make "Retry"
            # fail again for a reason the first attempt had already solved.
            cookie_file = Path(old.cookie_file) if old.cookie_file else None
            cookie_note, platform = old.cookie_note, old.platform
            cookie_header = old.cookie_header
        return self.add(url, mode, quality, title, Path(folder),
                        Path(target) if target else None, force=force, tool=tool,
                        limit_minutes=limit_minutes,
                        cookie_file=cookie_file, cookie_note=cookie_note,
                        platform=platform, cookie_header=cookie_header)

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
                    starting.append(job)
                    free -= 1

        for job in starting:
            threading.Thread(target=self._work, args=(job,), daemon=True).start()

    def _work(self, job: Job) -> None:
        def on_progress(progress: ytdlp.Progress) -> None:
            with self._lock:
                job.percent, job.speed, job.eta = progress.percent, progress.speed, progress.eta

        def on_start(process: subprocess.Popen) -> None:
            with self._lock:
                job.process = process
                # Cancelled while it was still starting up.
                if job.state == CANCELLED:
                    process.terminate()

        def on_percent(percent: int) -> None:
            """The specialist tools give a bare number, not yt-dlp's three fields."""
            with self._lock:
                job.percent = f"{percent}%"

        cookie_file = Path(job.cookie_file) if job.cookie_file else None

        try:
            if job.tool == "yt-dlp":
                result = ytdlp.download(
                    job.url, job.mode, Path(job.folder),
                    on_progress=on_progress, quality=job.quality, on_start=on_start,
                    out_path=Path(job.target) if job.target else None,
                    force=job.force, cookie_file=cookie_file,
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
                        mode=job.mode, quality=job.quality,
                        limit_minutes=job.limit_minutes, force=job.force,
                        cookie_file=cookie_file,
                        # TikTokDownloader wants a cookie STRING, not a file,
                        # so it cannot read `cookie_file`. This says it may
                        # ask for one.
                        cookie_header=job.cookie_header,
                    ),
                    on_progress=on_percent, on_start=on_start,
                )

            with self._lock:
                if job.state != CANCELLED:
                    job.files = [str(p) for p in result.files]
                    # Say the truth: the file was already there and nothing
                    # was written. "Done" would be a lie the user cannot see.
                    job.skipped = result.nothing_downloaded
                    job.state = DONE
                    job.percent = "100%"
        except Exception as exc:
            with self._lock:
                if job.state != CANCELLED:      # a cancel is not a failure
                    job.state = ERROR
                    job.error = str(exc)
        finally:
            with self._lock:
                job.process = None
            self._pump()
