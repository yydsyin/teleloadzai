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

from .config import APP_NAME, APP_VERSION
from .server import serve, start_background

WINDOW_SIZE = (860, 900)
WINDOW_MINIMUM = (520, 560)


def open_window(port: int) -> None:
    """Open the native window. Falls back to the browser if it cannot."""
    try:
        import webview
    except ImportError:
        print("The window engine (pywebview) is missing -- using the browser.")
        serve(port=port, open_browser=True)
        return

    httpd, url = start_background(port)
    print(f"{APP_NAME} {APP_VERSION}  -  close the window to stop.")
    try:
        webview.create_window(
            APP_NAME, url,
            width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
            min_size=WINDOW_MINIMUM,
        )
        webview.start()          # returns when the user closes the window
    finally:
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

    if args.no_browser:
        serve(port=args.port, open_browser=False)
    elif args.browser:
        serve(port=args.port, open_browser=True)
    else:
        open_window(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
