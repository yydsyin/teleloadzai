"""Start Teleloadzai:  python -m teleloadzai

By default the app opens its own window, with its own title and icon, and no
browser is involved. The page inside is HTML, but the user never sees a
browser -- same idea as VS Code or Discord.

``--browser`` falls back to a normal browser tab, which is useful while
developing and on a machine where the window engine is missing.
"""

from __future__ import annotations

import argparse
import sys

from . import commands, console, cookies, login, notify, runners, toolservers
from .config import APP_NAME, APP_VERSION
from .paths import ensure_dirs
from .server import QUEUE, claim, forget_if_once, holder_is_us, serve, start_background

WINDOW_SIZE = (860, 900)
WINDOW_MINIMUM = (520, 560)


def opening_place() -> tuple[int, int, int | None, int | None]:
    """Width, height, x, y of the window at start: WINDOW_SIZE when it fits
    the free screen above the taskbar, else that space minus a margin --
    never below WINDOW_MINIMUM -- and centred in it. Seen 2026-10-22 on the
    user's PC (175 % scaling): 866 free in height, the window opened 900 tall
    and its bottom edge went under the taskbar; at 846 tall, Windows still
    put its top at 125 (bottom 971), so the place is given too. Windows'
    work area is in the same unit as pywebview's sizes (both read 1463 wide
    that day). x and y are None when the free area cannot be read."""
    try:
        import ctypes
        from ctypes import wintypes
        area = wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0):
            return (*WINDOW_SIZE, None, None)   # SPI_GETWORKAREA refused: the old way
    except (AttributeError, OSError):
        return (*WINDOW_SIZE, None, None)       # not Windows
    free_width, free_height = area.right - area.left, area.bottom - area.top
    margin = 20
    width = max(WINDOW_MINIMUM[0], min(WINDOW_SIZE[0], free_width - margin))
    height = max(WINDOW_MINIMUM[1], min(WINDOW_SIZE[1], free_height - margin))
    return (width, height, area.left + max(0, (free_width - width) // 2),
            area.top + max(0, (free_height - height) // 2))


def say_port_taken(port: int, show_box: bool, folders: OSError | None = None) -> None:
    """The second copy says why it opens nothing -- never a silent exit
    (decision 34). In a Windows box, because the app has no other screen.
    `folders`: not the port at all -- its data folders could not be made (a
    read-only stick): "port 8777 is in use" sent the user to Task Manager for
    nothing (round 37 of the hunt)."""
    if folders is not None:
        text = (f"{APP_NAME} cannot start: it could not make its folders next to it "
                f"({folders.strerror or folders}). Put {APP_NAME} in a folder you can write in, "
                f"such as Documents, then start it again.")
        print(text)
        if show_box and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x40)
        return
    # A frozen copy answers nothing and looked like "another program"; the
    # advice "--port and another number" then started a second copy on the
    # SAME data folder, whose start-up sweep takes the first one's running
    # downloads (round 18 of the hunt). Both cases now point at Task Manager.
    if holder_is_us(port):
        text = (f"{APP_NAME} is already open. Look for its window in the taskbar. "
                f"If that window does not answer, end {APP_NAME} in Task Manager, then start it again.")
    else:
        text = (f"{APP_NAME} cannot start: port {port} is in use. It may be {APP_NAME} itself, "
                f"open but not answering, or another program. End it in Task Manager, then start "
                f"{APP_NAME} again.")
    print(text)
    if show_box and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x40)   # "i" icon


def ask_before_closing() -> bool:
    """Closing during a download asks first (Phase 2 item 2, 2026-10-24).
    pywebview cancels the close when a `closing` handler returns False (read
    in its winforms code, 6.2.1). Windows writes the buttons in its own
    language: Yes closes, No (the default) keeps the window open."""
    left = QUEUE.unfinished()
    if not left or sys.platform != "win32":
        return True
    import ctypes
    # A stopped recording still being made into its MP4 or MP3 does not come
    # back "ready to continue": closing ends that step (round 34 of the hunt).
    making = QUEUE.making()
    left -= making
    one = left == 1
    saving = ("A stopped recording is still being made into its MP4 or MP3. "
              "Closing ends that: the recording is kept as .ts." if making == 1 else
              f"{making} stopped recordings are still being made into their MP4 or MP3. "
              "Closing ends that: the recordings are kept as .ts.") if making else ""
    text = (f"{'1 download is' if one else f'{left} downloads are'} not finished.\n\n"
            f"Close {APP_NAME} anyway? {'It stops' if one else 'They stop'} now, and "
            f"{'comes' if one else 'come'} back the next time you open {APP_NAME}, ready to continue."
            + (f"\n\n{saving}" if saving else "")) if left else (
            f"{saving}\n\nClose {APP_NAME} anyway?")
    # MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2 | MB_SETFOREGROUND | MB_TOPMOST
    answer = ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x4 | 0x20 | 0x100 | 0x10000 | 0x40000)
    return answer == 6          # IDYES


def open_window(port: int, httpd=None) -> int:
    """Open the native window. Falls back to the browser if it cannot.
    Returns the exit code: 1 when closing could not forget the log-ins."""
    try:
        import webview
    except ImportError:
        print("The window engine (pywebview) is missing -- using the browser.")
        serve(port=port, open_browser=True, httpd=httpd)
        return 0

    httpd, url = start_background(port, httpd)
    failed = False
    # Before any window exists: Windows names our messages after this id --
    # "Teleloadzai", where it said "Python" (seen by the user, 2026-10-24).
    notify.set_app_id()
    print(f"{APP_NAME} {APP_VERSION}  -  close the window to stop.")
    try:
        width, height, x, y = opening_place()
        window = webview.create_window(
            APP_NAME, url,
            width=width, height=height, x=x, y=y,
            min_size=WINDOW_MINIMUM,
            # Opens maximized (the user, 2026-10-25, with the left menu of
            # model S1); the place above is where "Restore down" goes.
            maximized=True,
        )
        window.events.closing += ask_before_closing

        def to_front() -> None:
            """A click on the end-of-download message brings the window back
            (Phase 2 item 6) at the size it had: out of the taskbar if
            minimised, then in front. pywebview's restore() always sets the
            small size (winforms: WindowState Normal), so a maximized window
            came back 860 wide (the user, 2026-10-26). Windows' own
            SW_RESTORE brings a minimised window back as it was, maximized
            included; a window not minimised keeps its size."""
            try:
                import ctypes
                handle = ctypes.c_void_p(int(window.native.Handle.ToInt64()))
                if ctypes.windll.user32.IsIconic(handle):
                    ctypes.windll.user32.ShowWindow(handle, 9)        # SW_RESTORE
            except Exception:
                window.restore()    # no handle: the old way, it still comes back
            window.show()

        notify.on_click = to_front
        # A "Forget them" that Windows refused last time happens now, before
        # WebView2 takes hold of the folder again.
        login.forget_pending()
        login.BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
        # Every site the log-in window visits keeps its data HERE, inside our
        # own folder -- never in the user's real browser profile. Removing
        # Teleloadzai removes it, and "Forget them" can wipe it in one go.
        webview.start(storage_path=str(login.BROWSER_PROFILE))
    finally:
        # "Forget when I close Teleloadzai" happens HERE, after the window
        # engine has stopped -- the one moment Windows releases the profile.
        # TikTokDownloader's and KS-Downloader's servers must not outlive us.
        # Both bind 0.0.0.0 and ask for no token, so one left running is a
        # door open on the network -- exactly what decision 21 forbids for
        # our own.
        # Every download first: one left running went on unseen, and yt-dlp
        # wrote its cookie jar back AFTER the forget below (2026-10-18).
        stopped = QUEUE.stop_all()
        if stopped:
            print(f"{stopped} download(s) stopped.")
        # The Console's command too: only Windows' job object ended it, and
        # one Windows refused to bind went on after the app (round 17).
        try:
            if commands.stop():
                print("The Console's command was stopped.")
        except Exception as problem:            # never block the shutdown
            print(f"Could not stop the Console's command: {problem}")
        notify.close()          # no icon may stay in the notification area
        for server in toolservers.ALL:
            if server.stop_now():
                print(f"{server.name}'s server stopped.")
        # The per-run cookie copies of reads and downloads still running:
        # their own clean-up never runs once the app is closing. A title read
        # left a whole jar there on 2026-11-05, kept 4 days until the next
        # start (found 2026-11-10). Downloads are stopped above, first.
        cookies.clear_run_copies()
        try:
            forget_if_once()
        except Exception as problem:            # never block the shutdown
            print(f"Could not forget the log-ins: {problem}")
            # The console closes at once on a clean exit, so this line could
            # never be read: a non-zero code makes Teleloadzai.bat pause.
            failed = True
        httpd.shutdown()
        httpd.server_close()
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="teleloadzai")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--browser", action="store_true",
                        help="open a browser tab instead of the app window")
    parser.add_argument("--no-browser", action="store_true",
                        help="only run the server, open nothing")
    args = parser.parse_args()

    # The port FIRST: one Teleloadzai at a time. A second copy stops here,
    # before the lines below touch the first copy's log-ins.
    try:
        ensure_dirs()
    except OSError as problem:
        say_port_taken(args.port, show_box=not args.no_browser, folders=problem)
        return 1
    try:
        httpd = claim(args.port)
    except OSError:
        say_port_taken(args.port, show_box=not args.no_browser)
        return 1

    # "Forget when I close" also has to survive NOT being closed properly.
    # A crash, Task Manager, or a PC switched off at the wall all skip the
    # shutdown path, and the cookies would then outlive the session they were
    # promised to. Wiping here as well means the promise costs one extra
    # start, never a leak. (Found 2026-09-22 by killing the app and finding
    # data/cookies.txt still there.)
    try:
        forget_if_once()
    except Exception as problem:
        # Said on the Console page too: a print reaches no one in the app's
        # window (silent-failure hunt, 2026-11-22).
        text = (f"Your log-ins from the last run could not be forgotten ({problem}). "
                "They are still saved: forget them on the Sites page.")
        print(text)
        console.add("app", f"Teleloadzai: {text}", "err")
    # The per-run cookie copies a crash left behind (cookies.for_one_run).
    # One that cannot be deleted is a copy of a log-in left on the disk:
    # said, not passed over (round 17 of the hunt).
    held = cookies.clear_run_copies()
    if held < 0:
        console.add("app", "Teleloadzai: the folder data/cookie-runs could not be read, so copies "
                    "of your log-ins may be left in it; tried again at the next start.", "err")
    elif held:
        console.add("app", f"Teleloadzai: {held} cop{'ies' if held > 1 else 'y'} of your log-ins "
                    f"in data/cookie-runs could not be deleted (held by another program); "
                    "tried again at the next start.", "err")
    # And the hidden work folders of downloads a crash cut off: what they
    # finished goes to the user's folder, the rest is deleted.
    try:
        rescued = runners.sweep_work_folders()
        files = [path.name for owner, path in rescued if path.is_file()]
        stuck = [str(path) for owner, path in rescued if path.is_dir()]
        # Said in the Console too: the console window is hidden from the user.
        if files:
            text = f"Kept from downloads cut off last time: {', '.join(files)}"
            print(text)
            console.add("app", f"Teleloadzai: {text}", "note")
        if stuck:
            text = ("Some files of downloads cut off last time could not be moved "
                    f"(still in use?). They stay in {', '.join(stuck)}; Teleloadzai tries "
                    "again at the next start.")
            print(text)
            console.add("app", f"Teleloadzai: {text}", "err")
    except Exception as problem:
        rescued = []
        text = (f"The unfinished downloads of last time could not be cleaned up ({problem}). "
                "Teleloadzai tries again at the next start.")
        print(text)
        console.add("app", f"Teleloadzai: {text}", "err")   # round 2 of the hunt, 2026-11-22
    # A site refused since (Netflix) must not keep the cookies it had.
    try:
        dropped = cookies.drop_unsupported()
        if dropped:
            print(f"{dropped} cookies of sites no longer supported were removed.")
    except Exception as problem:
        text = (f"The cookies of sites no longer supported could not be removed ({problem}). "
                "Teleloadzai tries again at the next start.")
        print(text)
        console.add("app", f"Teleloadzai: {text}", "err")
    # The list of the last run, after the sweep above has moved what cut-off
    # downloads finished: only now is the port ours (decision 21).
    QUEUE.load()
    # The rows whose work folder still holds a file that could not be moved:
    # never called done (round 19 -- a post went green with a file stuck).
    stuck = set()
    for owner, path in rescued:
        if not owner:
            try:
                stuck.add((path / runners._JOB_MARK).read_text(encoding="utf-8").strip())
            except OSError:
                pass
    QUEUE.rescued([(owner, path) for owner, path in rescued if owner], stuck)

    if args.no_browser:
        serve(port=args.port, open_browser=False, httpd=httpd)
    elif args.browser:
        serve(port=args.port, open_browser=True, httpd=httpd)
    else:
        return open_window(args.port, httpd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
