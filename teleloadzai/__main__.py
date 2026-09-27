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

from . import cookies, login, toolservers
from .config import APP_NAME, APP_VERSION
from .server import claim, forget_if_once, holder_is_us, serve, start_background

WINDOW_SIZE = (860, 900)
WINDOW_MINIMUM = (520, 560)


def say_port_taken(port: int, show_box: bool) -> None:
    """The second copy says why it opens nothing -- never a silent exit
    (decision 34). In a Windows box, because the app has no other screen."""
    if holder_is_us(port):
        text = f"{APP_NAME} is already open. Look for its window in the taskbar."
    else:
        text = (f"{APP_NAME} cannot start: another program is using port {port}. "
                f"Close it, or start {APP_NAME} with --port and another number.")
    print(text)
    if show_box and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x40)   # "i" icon


def open_window(port: int, httpd=None) -> None:
    """Open the native window. Falls back to the browser if it cannot."""
    try:
        import webview
    except ImportError:
        print("The window engine (pywebview) is missing -- using the browser.")
        serve(port=port, open_browser=True, httpd=httpd)
        return

    httpd, url = start_background(port, httpd)
    print(f"{APP_NAME} {APP_VERSION}  -  close the window to stop.")
    try:
        webview.create_window(
            APP_NAME, url,
            width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
            min_size=WINDOW_MINIMUM,
        )
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
        for server in toolservers.ALL:
            if server.stop_now():
                print(f"{server.name}'s server stopped.")
        try:
            forget_if_once()
        except Exception as problem:            # never block the shutdown
            print(f"Could not forget the log-ins: {problem}")
        httpd.shutdown()
        httpd.server_close()


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
        print(f"Could not forget the log-ins from the last run: {problem}")
    # A site refused since (Netflix) must not keep the cookies it had.
    try:
        dropped = cookies.drop_unsupported()
        if dropped:
            print(f"{dropped} cookies of sites no longer supported were removed.")
    except Exception as problem:
        print(f"Could not tidy the cookie file: {problem}")

    if args.no_browser:
        serve(port=args.port, open_browser=False, httpd=httpd)
    elif args.browser:
        serve(port=args.port, open_browser=True, httpd=httpd)
    else:
        open_window(args.port, httpd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
