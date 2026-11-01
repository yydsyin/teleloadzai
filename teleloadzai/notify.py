"""A Windows message in the corner of the screen when downloads end.

Phase 2 item 6 (2026-10-24). Of three ways, probed on the user's PC, this is
the one that works: a tray message through Windows' own functions (ctypes,
decision 20 -- nothing to install).
  * The page's own notification: pywebview denies it ("denied", then an error).
  * A PowerShell toast: shown as "PowerShell", and a click cannot reach us.
  * A tray message: shown, and the user's click reached us (3 of 3, 2.7-3.9 s).
It was shown as "Python" until the process took its own app id (`set_app_id`):
then "Teleloadzai", seen by the user. Nothing is written to the registry.

The message is shown only when the Teleloadzai window is not in front (the row
already says it there), and downloads that end within a few seconds share one
message -- and nothing is said while another download still waits or runs:
the last one's end says them all. Its tray icon lives only while the
message is up. A click on the box
brings the window back; a click from Windows' notification list does not --
Windows never sends it back for this kind of message (tried 2026-10-24).
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
from typing import Callable

from .config import APP_NAME

GROUP_SECONDS = 3.0         # ends this close together share one message

# Set by the app: is the setting on? is anything still waiting or running?
# (server) and what a click does (__main__).
enabled: Callable[[], bool] = lambda: True
busy: Callable[[], bool] = lambda: False
on_click: Callable[[], None] | None = None

# (name, "done" | "already" | "failed", files in that row)
_pending: list[tuple[str, str, int]] = []
_lock = threading.Lock()
_timer: threading.Timer | None = None
_shows: "queue.Queue[tuple[str, str]]" = queue.Queue()
_started = False


def set_app_id() -> None:
    """The name Windows writes on our messages: "Teleloadzai", not "Python"."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
        except (AttributeError, OSError):
            pass            # only the name on the message is lost


def window_in_front() -> bool:
    """Is the window the user is looking at one of ours?"""
    if sys.platform != "win32":
        return True
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    owner = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()),
                                    ctypes.byref(owner))
    return owner.value == os.getpid()


def ended(name: str, how: str, files: int = 1) -> None:
    """A download ended: "done", "already" (nothing downloaded) or "failed";
    ``files`` > 1 for a row that brought several (a playlist in one row).
    Said once nothing is left waiting or running, with every end since."""
    global _timer
    if sys.platform != "win32":
        return
    with _lock:
        _pending.append((name or "A download", how, files))
        if _timer is None:
            _timer = threading.Timer(GROUP_SECONDS, _flush)
            _timer.daemon = True
            _timer.start()


def check() -> None:
    """A download left without an end to say (stopped by hand): the ends
    still waiting are said if it was the last one running."""
    global _timer
    with _lock:
        if _pending and _timer is None and sys.platform == "win32":
            _timer = threading.Timer(GROUP_SECONDS, _flush)
            _timer.daemon = True
            _timer.start()


def words(ends: list[tuple[str, str, int]]) -> tuple[str, str]:
    """(title, text) for these ends -- plain sentences, the file name only."""
    failed = sum(1 for _, how, _n in ends if how == "failed")
    if len(ends) == 1:
        name, how, files = ends[0]
        name = name if len(name) <= 120 else name[:119] + "…"
        if how == "failed":
            return "Download failed", f"{name} failed. Open {APP_NAME} to see why."
        if how == "already":
            return "Nothing downloaded", f"{name} was already in your folder."
        if files > 1:
            # A playlist in one row: its first file's name said "one video
            # arrived" when 29 did (found 2026-10-24).
            return "Download finished", f"{name}: {files} files are in your folder."
        return "Download finished", f"{name} is in your folder."
    done = len(ends) - failed
    title = "Downloads finished" if not failed else "Downloads ended"
    text = (f"{done} download{'s' if done != 1 else ''} finished"
            + (f" · {failed} failed" if failed else "") + f". Open {APP_NAME} to see them.")
    return title, text


def _flush() -> None:
    global _timer
    # Nothing is said while another download still waits or runs: a playlist
    # chosen video by video gave close to one message per video (found
    # 2026-10-24). The ends wait; the last download's end says them all.
    try:
        still = busy()
    except Exception:
        still = False
    with _lock:
        _timer = None
        if still:
            return
        ends, _pending[:] = list(_pending), []
    try:
        wanted = enabled()
    except Exception:
        wanted = True
    if ends and wanted and not window_in_front():
        _start()
        _shows.put(words(ends))
        _wake()


# --- The Windows side: one hidden window, owned by one thread -------------
# A tray message talks back to the window that made it, on that window's own
# thread: so one thread makes the window, shows the messages it is handed,
# and hears the click (probe 2, 2026-10-24).

_WM_APP = 0x8000
_CALLBACK = _WM_APP + 1     # the tray icon speaks
_SHOW = _WM_APP + 2         # a message is waiting in _shows
_STOP = _WM_APP + 3         # the app closes: the icon goes, then the loop
_NIN_BALLOONHIDE, _NIN_BALLOONTIMEOUT, _NIN_BALLOONUSERCLICK = 0x403, 0x404, 0x405
_hwnd = None
_thread: threading.Thread | None = None
_refusal_said = False


def _start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    global _thread
    ready = threading.Event()
    _thread = threading.Thread(target=_loop, args=(ready,), daemon=True, name="notify")
    _thread.start()
    ready.wait(5)
    if not _hwnd:
        # Windows refused the hidden window the messages need. Said once,
        # and tried again at the next end -- it used to stop every message
        # for the whole session without a word (hunt of 2026-10-31).
        with _lock:
            _started = False
        global _refusal_said
        if not _refusal_said:
            _refusal_said = True
            from . import console
            console.add("app", f"{APP_NAME}: Windows did not let {APP_NAME} show its "
                        "message when a download ends. The list still shows how each download ended.", "err")


def _wake() -> None:
    if _hwnd:
        ctypes.windll.user32.PostMessageW(ctypes.c_void_p(_hwnd), _SHOW, 0, 0)


def _loop(ready: threading.Event) -> None:
    global _hwnd
    from ctypes import wintypes as w
    user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                    ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                    ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                    ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                    ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON)]

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.restype = w.HWND
    user32.LoadIconW.restype = w.HICON
    icon = user32.LoadIconW(None, ctypes.c_void_p(32512))      # the standard program icon
    showing = {"on": False}
    nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), uID=1)

    def remove() -> None:
        if showing["on"]:
            shell32.Shell_NotifyIconW(2, ctypes.byref(nid))          # NIM_DELETE
            showing["on"] = False

    def show(title: str, text: str) -> None:
        remove()            # a new message replaces the one still up
        nid.hWnd = _hwnd
        nid.uFlags = 0x1 | 0x2 | 0x4 | 0x10                           # MESSAGE ICON TIP INFO
        nid.uCallbackMessage = _CALLBACK
        nid.hIcon = icon
        nid.szTip = APP_NAME
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = 0x1                                         # NIIF_INFO
        if shell32.Shell_NotifyIconW(0, ctypes.byref(nid)):           # NIM_ADD
            showing["on"] = True
            nid.uVersion = 4
            shell32.Shell_NotifyIconW(4, ctypes.byref(nid))           # NIM_SETVERSION

    def proc(hwnd, msg, wparam, lparam):
        if msg == _SHOW:
            while not _shows.empty():
                show(*_shows.get_nowait())
            return 0
        if msg == _STOP:
            remove()
            user32.PostQuitMessage(0)
            return 0
        if msg == _CALLBACK:
            event = lparam & 0xFFFF
            if event == _NIN_BALLOONUSERCLICK and on_click:
                try:
                    on_click()
                except Exception as problem:     # never kill the loop
                    print(f"Could not bring the window to the front: {problem}")
            if event in (_NIN_BALLOONUSERCLICK, _NIN_BALLOONTIMEOUT, _NIN_BALLOONHIDE):
                # The icon lives only as long as its box. A click from Windows'
                # notification list never comes back to us, even with the icon
                # kept 5 minutes (tried by the user, 2026-10-24); a click on
                # the box itself does (seen twice).
                remove()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wndproc = WNDPROC(proc)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                    ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                    ("lpszClassName", w.LPCWSTR)]

    hinst = kernel32.GetModuleHandleW(None)
    klass = WNDCLASSW(lpfnWndProc=wndproc, hInstance=hinst, lpszClassName="TeleloadzaiNotify")
    user32.RegisterClassW(ctypes.byref(klass))
    _hwnd = user32.CreateWindowExW(0, "TeleloadzaiNotify", APP_NAME, 0, 0, 0, 0, 0,
                                   None, None, hinst, None)
    ready.set()
    if not _hwnd:
        return          # said by _start
    message = w.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
    finally:
        remove()


def close() -> None:
    """When the app closes: no icon may stay in the notification area. The
    loop's own thread removes it; we wait for that, a little."""
    if _hwnd:
        ctypes.windll.user32.PostMessageW(ctypes.c_void_p(_hwnd), _STOP, 0, 0)
    if _thread is not None:
        _thread.join(2)
