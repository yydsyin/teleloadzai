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

import re
import shutil
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Callable
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
    # Added 2026-09-23 so the window opens ON the log-in, not on a front page
    # where the user has to hunt for the button. Each one probed that day
    # (plain request, where it lands, its title) and kept only with evidence
    # that it IS a log-in page:
    #   tiktok       title "Log in | TikTok"
    #   xiaohongshu  its own /explore redirected there
    #   vimeo        title "Log in to Vimeo"
    #   rumble       lands on auth.rumble.com, "Rumble Auth", and its address
    #                carries redirect_uri=https://rumble.com/ -- it sends the
    #                user back to the site once logged in
    #   soundcloud   title "... sign-in ..."
    #   bandcamp     title "Log in | Bandcamp"
    #   mixcloud     title "Login | Mixcloud"
    #   archive      /account/login redirected there by the site itself
    # A plain request was NOT enough for the next six: Pinterest, Dailymotion
    # and Odysee answer 200 even for a page that does not exist (control run
    # the same day). So they were opened in WebView2 itself, our window's
    # engine, and kept on what was drawn:
    #   pinterest    title "Pinterest Login", a password box on screen
    #   dailymotion  title "Connexion - Dailymotion"
    #   odysee       the "Se connecter" form (email first, no password yet)
    #   ted          the address TED's own "SIGN IN" button points to
    #   niconico     lands on /spa/login/, title "ログイン", a password box
    # Douyin keeps its front page on purpose: the log-in QR code is already
    # drawn there, and sso.douyin.com just sends the window back to it.
    # TED and Niconico live on another sub-domain; `_needs_moving` takes the
    # window back to the main site before reading, so nothing is missed.
    # ⚠️ Kuaishou is NOT here any more. Its passport page was, for an hour:
    # the user scanned the QR code, logged in, and the page never went back
    # to the site, so the window waited for nothing (2026-09-23). The site's
    # own log-in is a pop-up on www.kuaishou.com -- see _PRESS_LOGIN.
    "tiktok": "https://www.tiktok.com/login",
    "pinterest": "https://www.pinterest.com/login/",
    "dailymotion": "https://www.dailymotion.com/signin",
    "odysee": "https://odysee.com/$/signin",
    "ted": "https://auth.ted.com/users/new?context=ted.www%2Fnav",
    "niconico": "https://account.nicovideo.jp/login",
    "xiaohongshu": "https://www.xiaohongshu.com/login",
    "vimeo": "https://vimeo.com/log_in",
    "rumble": "https://rumble.com/login.php",
    "soundcloud": "https://soundcloud.com/signin",
    "bandcamp": "https://bandcamp.com/login",
    "mixcloud": "https://www.mixcloud.com/login/",
    "archive": "https://archive.org/account/login",
}

# Sites whose log-in is a pop-up on the front page: we press the site's own
# button, so the user sees the log-in straight away. If the site renames it,
# nothing breaks -- the user sees the front page and its log-in panel.
_PRESS_LOGIN = {
    # (the button, the pop-up it opens). Seen 2026-09-23 in WebView2: the
    # side panel "登录即可享受" holds a "立即登录" button (class
    # `sidebar-login-b...`); clicking it draws `login-modal ... modal-dialog`
    # with the QR code, address unchanged.
    # ⚠️ A click the moment the page says "loaded" can do nothing -- the page
    # is not drawn yet. Seen the same day: pressed once, pop-up not there. So
    # the pop-up is CHECKED, and the button pressed again until it shows.
    "kuaishou": ("document.querySelector('[class*=sidebar-login]')",
                 "document.querySelector('[class*=login-modal]')"),
}
_PRESS_TRIES = 8

# The cookies that exist only once logged in. Where the address never
# changes after a log-in (a pop-up, a QR code), their arrival is the only
# sign the user is in. ONLY names seen on a real log-in (decision 38).
_SESSION_COOKIES = {
    # 2026-09-23, the user's own QR log-in: `userId` and
    # `kuaishou.web.api_st` on .kuaishou.com. Neither was among the 9
    # cookies of a visit without an account, recorded the same afternoon.
    "kuaishou": ("userId", "kuaishou.web.api_st"),
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
        window = _window

    # Closing the window by hand used to take NOTHING and say nothing, and
    # left a dead handle that refused the next log-in ("already open"). Seen
    # 2026-09-23: the user logged in to Kuaishou, closed the window, and no
    # cookie file existed afterwards. The watcher below is the answer.
    closed = threading.Event()
    window.events.closed += closed.set
    threading.Thread(target=_watch, args=(window, platform_id, url, closed),
                     daemon=True).start()
    return {"platform": platform_id, "url": url}


# --------------------------------------------------------------------------
# the watcher: finish by itself, and never lose a log-in to a closed window
# --------------------------------------------------------------------------

WATCH_EVERY = 1.5               # seconds between two looks at the window

# What the last log-in ended with, for the main window to say it. Only
# counts and words -- never a cookie.
_result: dict = {}
_result_number = 0

# Set by the server: what to do once cookies are saved (turn the switch on).
# A plain hook, because the server imports this module and not the reverse.
on_saved: Callable[[int], None] | None = None


def _report(platform_id: str, kept: int, how: str, error: str = "") -> None:
    global _result_number
    _result_number += 1
    _result.clear()
    _result.update(number=_result_number, platform=platform_id, kept=kept,
                   how=how, error=error)
    if kept and on_saved is not None:
        try:
            on_saved(kept)
        except Exception:
            pass                # the cookies ARE saved; the switch is second


def state() -> dict:
    """Is a log-in window open, and how did the last one end."""
    with _lock:
        is_open, platform_id = _window is not None, _open_for
    return {"open": is_open, "platform": platform_id, "result": dict(_result)}


def _left_login_page(here: str, start: str) -> bool:
    """True once the window has moved past the page it was opened on.

    `/login/phone-or-email` still counts as the log-in page of `/login`: a
    site that walks the user through several steps must not be closed on
    the second one.
    """
    now, then = urlsplit(here), urlsplit(start)
    # A page that still calls itself a log-in is not past it. Sites move
    # their own log-in page on arrival: x.com/login -> x.com/i/flow/login,
    # archive.org/account/login -> archive.org/login. Both windows closed
    # by themselves before anyone logged in (all-sites test, 2026-09-24).
    # The query counts too: X's third stop, 7 s after opening, was
    # x.com/i/jf/onboarding/web?mode=login -- the word only after the "?".
    if _LOGIN_WORDS.search(now.path) or _LOGIN_WORDS.search(now.query):
        return False
    if (now.hostname or "") != (then.hostname or ""):
        return True
    path, start_path = now.path.rstrip("/"), then.path.rstrip("/")
    return not (path == start_path or path.startswith(start_path + "/"))


# In the path of every log-in address we open on a site's main host (/login,
# /signin, /log_in, /$/signin, /accounts/login/ ...), checked 2026-09-24.
_LOGIN_WORDS = re.compile(r"log[-_]?in|sign[-_]?in", re.IGNORECASE)


def _watch(window, platform_id: str, start: str, closed: threading.Event) -> None:
    """Look at the log-in window every moment it is open.

    Two jobs:

    * **Finish by itself**, on one of two signs. Either the window has left
      the log-in page and landed on the platform's own address; or, for a
      site whose log-in is a pop-up that never changes the address, a cookie
      that only exists once logged in has appeared (`_SESSION_COOKIES`,
      names seen on a real log-in). Then: take the cookies, close the window.
      ⚠️ "Left the page" is not used when the log-in page IS the front page
      (Douyin's QR code): it would fire the moment the user clicks a video,
      before logging in. Closing the window finishes those.
    * **Keep what it has.** While the window is on ANY address of the site,
      its cookies are copied in memory -- never on another site such as
      accounts.google.com (decision 36). If the user closes the window, that
      copy is saved: closing is how most people say "done".
    * **Press the site's own log-in button** where the log-in is a pop-up
      (`_PRESS_LOGIN`), once, so the user lands on it instead of hunting.
    """
    global _window, _open_for
    latest: list[str] = []
    automatic = login_url(platform_id) != home_url(platform_id)
    press = _PRESS_LOGIN.get(platform_id)
    tries = 0
    session = _SESSION_COOKIES.get(platform_id, ())
    domains = next((p.domains for p in PLATFORMS if p.id == platform_id), ())

    while True:
        with _lock:
            if _window is not window:
                return          # finished, or cancelled, by someone else

        if closed.is_set():
            with _lock:
                mine = _window is window
                if mine:
                    _window, _open_for = None, ""
            if mine:
                kept = cookies.merge_lines(latest) if latest else 0
                _report(platform_id, kept, "closed")
            return

        try:
            here = window.get_current_url() or ""
        except Exception:
            here = ""
        host = urlsplit(here).hostname or ""
        # ANY address of the site, passport.* included: the copy is what a
        # closed window leaves us, and a log-in that ends on a sub-domain
        # must not be lost. Another site (accounts.google.com) never counts.
        on_site = any(host == d or host.endswith("." + d) for d in domains)
        if on_site and press:
            button, popup = press
            try:
                shown = window.evaluate_js(
                    f"(() => {{ const p = {popup}; if (p) {{ const r = p.getBoundingClientRect(); "
                    "if (r.width > 0 && r.height > 0) return true; } "
                    f"const b = {button}; if (b) b.click(); return false; }})()")
                tries += 1      # only a look that really ran counts
            except Exception:
                shown = False   # a page still loading; the next look will do
            if shown or tries >= _PRESS_TRIES:
                press = None    # open -- or the site changed; the user sees its page
        if on_site:
            try:
                latest = _netscape_lines(window.get_cookies() or [])
            except Exception:
                pass            # a page still loading; the next look will do
            logged_in = any(f"\t{name}\t" in line for name in session for line in latest)
            if (logged_in or (automatic and not _needs_moving(window, platform_id)
                              and _left_login_page(here, start))) and not closed.is_set():
                try:
                    kept = finish()
                except Exception as problem:
                    _report(platform_id, 0, "auto", cookies.redact(str(problem)))
                    return
                _report(platform_id, kept, "auto")
                return

        closed.wait(WATCH_EVERY)


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
    """True when the window is not on the platform's MAIN address yet.

    Not "somewhere on the site": WebView2 gives the cookies of the page the
    window is on (`GetCookiesAsync(self.url)`, read in pywebview's own code
    2026-09-23), so a log-in finished on passport.kuaishou.com would miss the
    cookies that live only on www.kuaishou.com. `www.` is ignored, so a site
    that drops it (vimeo.com) is not moved for nothing -- a needless move
    costs a page load, and TikTok's did not load within 20 s (2026-09-22).
    """
    home = home_url(platform_id)
    if not home:
        return False
    try:
        here = (window.get_current_url() or "").lower()
    except Exception:
        return True                  # cannot tell -> the safe move is to go
    if not here:
        return True

    host = urlsplit(here).hostname or ""
    host = host[4:] if host.startswith("www.") else host
    # Any of the platform's own addresses, exactly: X finishes its log-in on
    # x.com while our table lists twitter.com first (caught by the check of
    # 2026-09-23). A sub-domain such as passport.* is still moved.
    sites = next((p.domains for p in PLATFORMS if p.id == platform_id), ())
    return host not in sites


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
