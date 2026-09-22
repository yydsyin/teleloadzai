"""Log in inside Teleloadzai, instead of exporting a file by hand.

**Why this exists.** The other road -- export `cookies.txt` from the browser --
works, and it is what the leading open-source downloader does. But it has two
faults that no amount of good wording fixes:

* A browser export holds **every site you are logged into**. yt-dlp's own FAQ
  warns not to let such a file fall into the wrong hands. `cookies.py` now
  filters it, but the whole file still had to be read to do that.
* The cookies go stale. Sites rotate them on any open tab, so the documented
  recipe is "open a private window, log in, export, close the window".

Logging in here fixes both at the source. We only ever receive the cookies of
the one site the user logged into, and they are taken the moment they are
created. This is what the commercial downloaders do, and it is what users
recognise.

**How it works.** Decision 25 already gave us a real Chromium window
(pywebview + WebView2). A second window is opened on the site; the user logs
in exactly as in a browser; WebView2's own CookieManager hands the cookies
back -- including the `httpOnly` ones, which are the session cookies and which
JavaScript can never read. Proven 2026-09-22: 7 cookies, 6 of them httpOnly.

**What it is NOT.** No password is read, typed, stored or seen by us. The
login page is the site's own page, in the site's own window. We ask for the
cookies afterwards, the same thing the browser would keep anyway.
"""

from __future__ import annotations

import shutil
import threading
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from . import cookies
from .platforms import PLATFORMS

# The profile of the login window: its own folder, inside ours, so nothing
# touches the user's real browser and everything can be deleted in one go.
from .paths import DATA_DIR

BROWSER_PROFILE = DATA_DIR / "login-profile"

# Sites whose front page does not lead to a login. Everything else is derived
# from `platforms.py`, so a new platform needs no line here.
_LOGIN_URL = {
    "youtube": "https://accounts.google.com/ServiceLogin?service=youtube",
    "instagram": "https://www.instagram.com/accounts/login/",
    "facebook": "https://www.facebook.com/login/",
    "twitter": "https://x.com/login",
    "reddit": "https://www.reddit.com/login/",
    "bilibili": "https://passport.bilibili.com/login",
    "weibo": "https://passport.weibo.com/sso/signin",
    "twitch": "https://www.twitch.tv/login",
}

_lock = threading.Lock()        # one login window at a time, never two

# How long we wait for a page WE asked for to finish loading. pywebview's own
# limit is 20 seconds and it is not enough for a heavy site, which is how a
# working window came back as "Main window failed to start".
LOAD_PATIENCE = 60


class LoginError(RuntimeError):
    """The login window cannot run, with a sentence saying why."""


def login_url(platform_id: str) -> str | None:
    """Where to send the user for this platform."""
    if platform_id in _LOGIN_URL:
        return _LOGIN_URL[platform_id]
    for platform in PLATFORMS:
        if platform.id == platform_id and platform.domains:
            return f"https://www.{platform.domains[0]}/"
    return None


def choices() -> list[dict]:
    """The platforms worth offering a login for, for the page to draw."""
    offered = []
    for platform in PLATFORMS:
        if not platform.is_supported:
            continue
        url = login_url(platform.id)
        if url:
            offered.append({"id": platform.id, "name": platform.name, "url": url})
    return offered


def unavailable_reason() -> str | None:
    """Why logging in here is impossible right now, or None when it works.

    Two real cases, and both must be said rather than shown as a dead button
    (decisions 15 and 34): the window engine is missing, or Teleloadzai was
    started with ``--browser`` and has no window of its own to attach to.
    """
    try:
        import webview
    except ImportError:
        return ("the window engine is not installed, so Teleloadzai cannot open "
                "a login window. Import a cookies.txt instead")
    if not webview.windows:
        return ("Teleloadzai is running in a browser tab, not in its own window, "
                "so it has no window to open the log-in in. Start it normally, "
                "or import a cookies.txt instead")
    return None


# --------------------------------------------------------------------------
# turning WebView2 cookies into the file the tools read
# --------------------------------------------------------------------------

def _expiry(raw: str) -> int:
    """RFC-1123 date -> seconds since 1970. 0 means "dies with the session".

    WebView2 hands back e.g. 'Sun, 21 Mar 2027 17:07:07 GMT' (read from a real
    cookie, 2026-09-22). A session cookie has no usable date; 0 is what the
    Netscape format uses for that, and every tool understands it.

    ⚠️ A date **in the past** is not an expiry, it is that sentinel. WebView2
    does not hand back dead cookies -- it never returns a cookie the browser
    has already dropped -- so a past date can only mean "no expiry set". Seen
    2026-09-22: YouTube's `YSC`, a session cookie, came back as 2001-01-01,
    which is .NET's default date. Writing that literally made the file say it
    held an expired cookie, and would have made yt-dlp throw it away.
    """
    if not raw:
        return 0
    try:
        when = int(parsedate_to_datetime(raw).timestamp())
    except (TypeError, ValueError):
        return 0
    return when if when > time.time() else 0


def _netscape_lines(jar) -> list[str]:
    """Every cookie as one Netscape line, the format all three tools read.

    ``#HttpOnly_`` is a real prefix, not a comment: it is how the format marks
    a cookie JavaScript cannot see, and those are exactly the session cookies
    that make a log-in work. Dropping them would give a file that looks full
    and proves nothing.
    """
    lines: list[str] = []
    for simple in jar:
        for name, morsel in simple.items():
            domain = morsel["domain"] or ""
            if not domain:
                continue
            subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if morsel["secure"] else "FALSE"
            row = "\t".join([
                domain, subdomains, morsel["path"] or "/", secure,
                str(_expiry(morsel["expires"])), name, morsel.value,
            ])
            lines.append(("#HttpOnly_" + row) if morsel["httponly"] else row)
    return lines


def home_url(platform_id: str) -> str:
    """The platform's own page, where its cookies live."""
    for platform in PLATFORMS:
        if platform.id == platform_id and platform.domains:
            return f"https://www.{platform.domains[0]}/"
    return ""


# --------------------------------------------------------------------------
# the flow: open, let the user log in, then take the cookies
# --------------------------------------------------------------------------

_window = None                  # the login window, while one is open
_open_for = ""                  # which platform it belongs to


def open_for(platform_id: str) -> dict:
    """Open the log-in window for one platform.

    It does not wait. The user logs in at his own pace -- a password, a code
    by SMS, a CAPTCHA -- and tells the main window when he is done. Blocking
    here would freeze the app behind a window nobody has finished with, which
    is the mistake decision 23 already records about the "Save as" dialog.
    """
    global _window, _open_for

    problem = unavailable_reason()
    if problem:
        raise LoginError(problem)

    url = login_url(platform_id)
    if not url:
        raise LoginError(f"Teleloadzai does not know where to log in for {platform_id}")

    import webview

    with _lock:
        if _window is not None:
            raise LoginError("a log-in window is already open — finish that one first")
        name = next((p.name for p in PLATFORMS if p.id == platform_id), platform_id)
        # A non-main thread after start(): pywebview then creates the window
        # at once. The HTTP handler that calls this IS such a thread.
        _window = webview.create_window(
            f"Log in to {name}", url, width=980, height=760,
        )
        _open_for = platform_id

    return {"platform": platform_id, "url": url}


def finish() -> int:
    """Take the cookies from the open log-in window, then close it.

    Before reading, the window is sent to the platform's **own** page. This is
    not cosmetic: YouTube is logged in through accounts.google.com, and
    reading there would hand us Google cookies -- the same `.google.com` that
    carries a Gmail session. Landing on youtube.com first means we receive the
    site's own cookies and nothing else.
    """
    global _window, _open_for

    with _lock:
        window, platform_id = _window, _open_for

    if window is None:
        raise LoginError("no log-in window is open")

    try:
        # Only move if we are NOT already on the site. YouTube finishes its
        # log-in on accounts.google.com and must be sent home; TikTok finishes
        # on tiktok.com and must be left alone.
        #
        # ⚠️ Re-navigating for nothing is not merely wasteful: `get_cookies`
        # waits 20 seconds for the new page to say it has loaded, and TikTok
        # does not make it. The window was fine and the app answered "Main
        # window failed to start" (2026-09-22). Not moving is the fix; the
        # message below is for the times we must move and the site is slow.
        if _needs_moving(window, platform_id):
            # Wait for OUR navigation to finish, with our own patience.
            # `get_cookies` waits 20 seconds and no more, and a heavy site
            # crosses that line: YouTube's home and TikTok's both did, on
            # different runs (2026-09-22). Clearing the flag first means we
            # wait for the page we asked for, not for one already loaded.
            window.events.loaded.clear()
            window.load_url(home_url(platform_id))
            if not window.events.loaded.wait(LOAD_PATIENCE):
                # Not fatal on its own -- the page may still answer. We only
                # stop pretending the 20-second wait below is enough.
                time.sleep(2.0)

        try:
            jar = window.get_cookies()
        except Exception as problem:
            raise LoginError(
                "The site took too long to answer, so the cookies could not be "
                "read. Leave the window open on the site itself, wait for the "
                "page to finish, and press the button again."
            ) from problem

        fresh = _netscape_lines(jar)
        kept = cookies.merge_lines(fresh) if fresh else 0
    finally:
        close()

    return kept


def _needs_moving(window, platform_id: str) -> bool:
    """True when the window is not on the platform's own site yet."""
    home = home_url(platform_id)
    if not home:
        return False
    try:
        here = (window.get_current_url() or "").lower()
    except Exception:
        return True                  # cannot tell -> the safe move is to go
    if not here:
        return True
    sites = next((p.domains for p in PLATFORMS if p.id == platform_id), ())
    host = urlsplit(here).hostname or ""
    return not any(host == d or host.endswith("." + d) for d in sites)


# Windows will not let a folder go while WebView2 still holds it, and WebView2
# holds this one for as long as the app lives -- measured 2026-09-22: closing
# the log-in window was not enough, `lockfile` and the cache stayed busy. So a
# deletion that cannot happen now is written down and done at the next start.
FORGET_MARKER = DATA_DIR / "login-profile.forget"


def forget_browser() -> str:
    """Delete the log-in window's browser profile.

    "Forget them" must really forget. Removing `cookies.txt` alone leaves the
    WebView2 profile behind, so the next log-in window would open **already
    logged in** -- the app would say it had forgotten and plainly have not.

    Returns "" when there was nothing, "now" when it is gone, or "later" when
    Windows refused and it will go at the next start. Never claims a deletion
    that did not happen.
    """
    close()                       # nothing of OURS may hold the files open
    if not BROWSER_PROFILE.exists():
        FORGET_MARKER.unlink(missing_ok=True)
        return ""
    try:
        shutil.rmtree(BROWSER_PROFILE)
    except OSError:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        FORGET_MARKER.write_text("delete the login profile at the next start\n",
                                 encoding="utf-8")
        return "later"
    FORGET_MARKER.unlink(missing_ok=True)
    return "now"


def forget_pending() -> bool:
    """Carry out a deletion Windows refused last time. Run at startup.

    Returns True when a profile was really removed.
    """
    if not FORGET_MARKER.exists():
        return False
    gone = False
    if BROWSER_PROFILE.exists():
        try:
            shutil.rmtree(BROWSER_PROFILE)
            gone = True
        except OSError:
            return False          # still locked: keep the marker, try again later
    FORGET_MARKER.unlink(missing_ok=True)
    return gone


def close() -> bool:
    """Shut the log-in window, taking nothing. Returns True if one was open."""
    global _window, _open_for
    with _lock:
        window, _window, _open_for = _window, None, ""
    if window is None:
        return False
    try:
        window.destroy()
    except Exception:
        # The user may have closed it himself. Either way it is gone, and the
        # app must not carry a dead handle that blocks the next log-in.
        pass
    return True
