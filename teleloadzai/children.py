"""The programs we start die with Teleloadzai -- even when it is killed.

Closing the black console of `Teleloadzai.bat`, Task Manager, or a crash
skip every cleanup we write in Python. Until 2026-10-18 a download tool
then kept running unseen, and TikTokDownloader's or KS-Downloader's server
kept listening on 0.0.0.0 with the user's cookie, until the PC restarted
(found by the silent-failure hunt).

Windows has the answer itself: a **job object** with "kill on job close".
Every tool process is put in ours; Windows closes our handle when this
process ends, however it ends, and ends every process in the job with it.

Only the tools go in, never this process: a video the user opens from a row
("Open") is started by this process, and must not close when the app does.

⚠️ A tool is put in the job just after it starts. A program that starts a
second process within those few microseconds would leave that one outside
(yt-dlp.exe's launcher unpacks itself first, which takes far longer).
"""

from __future__ import annotations

import subprocess
import sys
import threading

_job = None
_lock = threading.Lock()


def _make_job():
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic),
                    ("IoInfo", Counters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                 wintypes.LPVOID, wintypes.DWORD)
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000     # KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info),    # 9 = extended
                                            ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    return kernel32, job


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


def bind(process: subprocess.Popen) -> bool:
    """Put one tool process in the job. False when Windows refused: the tool
    still runs, and the usual cleanup on close still stops it."""
    global _job
    if sys.platform != "win32":
        return False
    try:
        with _lock:
            if _job is None:
                _job = _make_job()
            kernel32, job = _job
        return bool(kernel32.AssignProcessToJobObject(job, int(process._handle)))
    except Exception:
        return False
