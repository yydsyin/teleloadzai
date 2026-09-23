"""What an error means, in plain words -- but only when we KNOW (decision 38).

Every entry below is an error met **in this project**, with its cause
checked. The `seen` line says what was observed, where and when, so the next
person can re-check it instead of trusting it.

Anything not in this list is shown exactly as the tool said it (washed of
secrets by `cookies.redact`, decision 37), with one honest line: Teleloadzai
does not recognise this error. **Never add an entry from a guess.** A wrong
explanation sends the user to fix the wrong thing, and he believes it because
the app said it.

The scar that produced this file: on 2026-09-22 I told the user "this network
is blocked by TikTok" after two videos. yt-dlp's own words for TikTok's code
10204 say "Your IP address is blocked", and I repeated them as a fact. It was
a video limited to some countries; the user found it by noticing he could
still scroll TikTok.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Known:
    words: tuple[str, ...]      # lower-case pieces that must ALL be in the error
    tools: tuple[str, ...]      # the tool that printed it
    title: str                  # what happened, in plain words
    next_step: str              # what the user can do -- advice, not a cause
    seen: str                   # the evidence. No evidence, no entry.


KNOWN: tuple[Known, ...] = (
    Known(
        words=("your ip address is blocked from accessing this post",),
        tools=("yt-dlp",),
        title="TikTok does not show this video on your internet connection.",
        next_step=("Other TikTok videos can still work — try another one. "
                   "TikTok does not say why; it may be a video limited to "
                   "some countries."),
        seen=("2026-09-22/23, Telecom Malagasy (Madagascar): two videos gave "
              "TikTok code 10204, which yt-dlp prints as this sentence. A "
              "normal browser on the same PC got the same code. Another "
              "video downloaded fine on the same connection, the same day."),
    ),
    Known(
        words=("this video is unavailable",),
        tools=("yt-dlp",),
        title="YouTube says this video is unavailable.",
        next_step=("YouTube gives this same message for a deleted video and "
                   "for a private one, so Teleloadzai cannot tell which. If "
                   "it is private, logging in to YouTube may help."),
        seen=("2026-09-22: a private video and a video id that does not "
              "exist both answered 'This video is unavailable', word for "
              "word."),
    ),
    Known(
        words=("for the authentication",),
        tools=("yt-dlp",),
        title="This post can only be seen when logged in.",
        next_step="Log in to the site, then press Retry.",
        seen=("2026-09-22, a private Instagram post: yt-dlp answered "
              "'...use --cookies-from-browser or --cookies for the "
              "authentication'. The advice to log in is yt-dlp's own. "
              "NOT yet seen: the retry succeeding with a real account."),
    ),
    Known(
        words=("http error 403",),
        tools=("yt-dlp",),
        title="The site refused the download.",
        next_step=("The one time this happened here, yt-dlp was six weeks "
                   "old and updating it fixed it. Update it first."),
        seen=("2026-09-20: HTTP 403 with a six-week-old yt-dlp; after "
              "updating to 2026.08.19 the same link downloaded."),
    ),
    Known(
        words=("failed to retrieve data",),
        tools=("tiktokdownloader",),
        title="TikTokDownloader could not read this video.",
        next_step=("We have seen this in two cases: no cookies for the "
                   "site — log in to it in Settings — or a video the site "
                   "does not show on your connection — try another video."),
        seen=("2026-09-22: /douyin/detail without a cookie failed this "
              "way, and worked with one. /tiktok/detail on a NASA video "
              "failed this way WITH a cookie; that video gave code 10204 in "
              "a normal browser."),
    ),
)


def from_tool(error: Exception) -> Exception:
    """Mark an error whose text is the TOOL's own words, not ours.

    Only then may the page say "this is exactly what <tool> said". Most errors
    are sentences Teleloadzai writes itself ("Port 5555 ... is taken by ...",
    "yt-dlp is not installed"), and labelling one of those as the tool's words
    is the very invention decision 38 forbids -- found 2026-09-23, the same
    hour the rule was written, on our own port message.
    """
    error.from_tool = True
    return error


def said_by_tool(error: Exception) -> bool:
    return bool(getattr(error, "from_tool", False))


def explain(error: str, tool: str) -> dict:
    """What to tell the user about this error.

    Returns {"known": True, "title", "next_step"} for an error we have met,
    or {"known": False} -- and then the page shows the tool's own words and
    says plainly that it does not recognise them.
    """
    low = (error or "").lower()
    if not low:
        return {"known": False}
    for entry in KNOWN:
        if tool in entry.tools and all(w in low for w in entry.words):
            return {"known": True, "title": entry.title,
                    "next_step": entry.next_step}
    return {"known": False}
