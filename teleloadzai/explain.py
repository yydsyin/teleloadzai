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
    # False when the link or the post itself is the problem: a Retry, or an
    # updated tool, gets the same answer. The failed row then offers neither
    # -- it showed a filled Retry under "check the link" (loop round 2,
    # 2026-09-26).
    retry: bool = True
    # The button the words point to, filled on the failed row: "update",
    # "login", or "" (then Retry). "read": on the card, reading the link
    # again is the only step (no download offered); a row keeps Retry. A 403 said "Update it first" above a
    # filled Retry (review of 2026-09-27). "reread": the failed row's button
    # is "Read the link again", Retry waits in its menu -- a Retry cannot
    # bring back a deleted video (the user's choice, 2026-11-08).
    action: str = ""


KNOWN: tuple[Known, ...] = (
    Known(
        words=("your ip address is blocked from accessing this post",),
        tools=("yt-dlp",),
        title="TikTok does not show this video on your internet connection.",
        retry=False,
        next_step=("Other videos can still work. This one may be limited "
                   "to some countries."),
        seen=("2026-09-22/23, Telecom Malagasy (Madagascar): two videos gave "
              "TikTok code 10204, which yt-dlp prints as this sentence. A "
              "normal browser on the same PC got the same code. Another "
              "video downloaded fine on the same connection, the same day."),
    ),
    Known(
        words=("only works when logged-in",),
        tools=("yt-dlp",),
        title="Vimeo shows this video only to a logged-in account.",
        next_step="Log in to Vimeo, then try again.",
        action="login",
        seen=("2026-09-26: vimeo.com/56015672 and vimeo.com/68375962, no "
              "cookies -- yt-dlp: 'The web client only works when "
              "logged-in'. It then listed its own command-line options "
              "(--cookies, --username…), which the card used to show as "
              "they were. Never tried with a Vimeo log-in (§4)."),
    ),
    Known(
        words=("this video is unavailable",),
        tools=("yt-dlp",),
        title="YouTube says this video is unavailable.",
        next_step=("It may be deleted or private. If it is private, logging "
                   "in to YouTube may help."),
        action="reread",
        seen=("2026-09-22: a private video and a video id that does not "
              "exist both answered 'This video is unavailable', word for "
              "word."),
    ),
    Known(
        # yt-dlp's cookie hint, "…for the authentication", ends the errors of
        # EVERY site that wants a log-in; alone it named Instagram for
        # YouTube's bot check and Reddit (the grids, 2026-11-21). The site
        # is part of the words now.
        words=("sign in to confirm you", "not a bot"),
        tools=("yt-dlp",),
        title="YouTube asks this computer to prove it is not a robot.",
        action="login",
        next_step=("Log in to YouTube here, then try again. YouTube sometimes asks "
                   "this of one internet connection and not another."),
        seen=("2026-11-19, the quality check, no cookies: a9LDPn-MO4I -- 'Sign in "
              "to confirm you're not a bot. ... Use --cookies-from-browser or "
              "--cookies for the authentication'; read the same day with the "
              "developer's YouTube log-in: it worked. Again 2026-11-21 in the test "
              "copy, no cookies, jNQXAC9IVRw."),
    ),
    Known(
        words=("account authentication is required",),
        tools=("yt-dlp",),
        title="Reddit shows this video only to a logged-in account.",
        action="login",
        next_step="Logging in to Reddit may let you download it.",
        seen=("2026-11-15, the quality check, yt-dlp 2026.11.04: 'Account "
              "authentication is required. Use --cookies-from-browser or --cookies "
              "for the authentication', 4 public links of 4, with no cookies and "
              "with a visit's. Never tried with a Reddit log-in: 'may'."),
    ),
    Known(
        words=("[instagram]", "for the authentication"),
        tools=("yt-dlp",),
        title="Instagram gave nothing for this post without a log-in.",
        action="login",
        next_step=("It may be private, or not exist. If you can see it while "
                   "logged in, log in to Instagram here, then press Retry."),
        seen=("2026-09-22: post C1234567890 -- an id I INVENTED, so a post "
              "that does not exist. Until 2026-09-23 this entry called it 'a "
              "private post' and claimed a log-in was needed; that was never "
              "seen. The advice to log in is yt-dlp's own. A real private "
              "post has not been tested."),
    ),
    Known(
        words=("there is no video in this post",),
        tools=("yt-dlp",),
        # True whichever program the card is on: "yt-dlp downloads videos
        # only" stayed red above gallery-dl (the beginner's walk, 2026-11-06).
        title="yt-dlp found no video in this post.",
        # Updating does not change it: yt-dlp builds nothing for a photo.
        retry=False,
        next_step="For photos, try gallery-dl (it needs your Instagram log-in).",
        seen=("2026-09-27, no cookies: instagram.com/p/DDhF_64RGd9 and "
              "/p/DGDRzmvALJW (named in gallery-dl issue 6688 and yt-dlp "
              "issue 12439) -- 'There is no video in this post'. The card offered "
              "a filled 'Update yt-dlp' under it. What the posts hold was "
              "not seen; gallery-dl was not tried (it needs a log-in)."),
    ),
    # The PC could not find the site's address. Not "your internet is down":
    # a domain typed wrong says exactly the same.
    Known(
        words=("could not resolve host",),
        tools=("yt-dlp",),
        title="This PC could not find the site's address.",
        # On the CARD, reading again is the step: it offered MP3 / MP4 and
        # "Try anyway", which led to a "Save as" window and the same failure
        # (loop round 5, 2026-10-18). A failed ROW keeps Retry: after an
        # internet hiccup it is the way out (decision 15; grids, same day).
        action="read",
        next_step="Check your internet connection and the link, then read it again.",
        seen=("2026-10-05, the review agent, in the app: Instagram "
              "BQ0eAlwhDrw failed once with 'Could not resolve host: "
              "www.instagram.com'; curl reached the site seconds later. The "
              "card said 'yt-dlp could not read this link', nothing about "
              "the connection."),
    ),
    Known(
        words=("failed to resolve", "getaddrinfo failed"),
        tools=("yt-dlp",),
        title="This PC could not find the site's address.",
        # On the CARD, reading again is the step: it offered MP3 / MP4 and
        # "Try anyway", which led to a "Save as" window and the same failure
        # (loop round 5, 2026-10-18). A failed ROW keeps Retry: after an
        # internet hiccup it is the way out (decision 15; grids, same day).
        action="read",
        next_step="Check your internet connection and the link, then read it again.",
        seen=("2026-10-05: three made-up addresses (…tlz-4821.invalid, "
              "…tlz-4821.com, instagram.invalid) -- 'Failed to resolve '…' "
              "([Errno 11001] getaddrinfo failed)'. The other wording of the "
              "same failure."),
    ),
    Known(
        words=("http error 403",),
        tools=("yt-dlp",),
        title="The site refused the download.",
        next_step="Update yt-dlp, then try again.",
        action="update",
        seen=("2026-09-20: HTTP 403 with a six-week-old yt-dlp; after "
              "updating to 2026.08.19 the same link downloaded."),
    ),
    Known(
        words=("failed to retrieve data",),
        tools=("tiktokdownloader",),
        title="TikTokDownloader could not read this video.",
        next_step=("Check the link, log in to the site on the Sites page, "
                   "or try another video."),
        seen=("2026-09-22: /douyin/detail without a cookie failed this way, "
              "and worked with one. 2026-09-23, WITH cookies: a NASA video "
              "that gives code 10204 in a normal browser, and an id that "
              "does not exist -- same words for both."),
    ),

    # ---- found by step 5b, 2026-09-23: inputs broken ON PURPOSE, so the
    # ---- cause of each message is known because we made it.
    Known(
        words=("unsupported url",),
        tools=("yt-dlp", "gallery-dl"),
        title="This program found nothing it can download on this page.",
        retry=False,
        next_step="Paste the link of the video itself, not a home page or a profile.",
        seen=("https://example.com/ -- a page that exists and has no video. "
              "yt-dlp: 'ERROR: Unsupported URL'; gallery-dl: 'Unsupported URL'."),
    ),
    Known(
        words=("unable to download webpage", "http error 404"),
        tools=("yt-dlp",),
        title="The site says this page does not exist (error 404).",
        retry=False,
        next_step="Check the link: it may be mistyped, or the site removed the page.",
        seen="https://example.com/some-page -- a page that does not exist.",
    ),
    Known(
        words=("unable to connect to proxy",),
        tools=("yt-dlp", "streamlink"),
        title="Your PC sends programs through a proxy, and that proxy does not answer.",
        next_step="If you use a VPN or a proxy program, check that it is running.",
        seen=("Proxy set to a closed port (127.0.0.1:9): yt-dlp and "
              "streamlink both said 'Unable to connect to proxy'. ⚠️ This "
              "is a BROKEN PROXY, not a missing internet connection -- true "
              "'no internet' was not reproduced, so nothing here claims it."),
    ),
    Known(
        words=("notfounderror",),
        tools=("gallery-dl",),
        title="The site says it cannot find this item.",
        retry=False,
        next_step="The link may be wrong, or the item was deleted.",
        seen=("Pinterest pin 999999999999999999, which does not exist: "
              "'NotFoundError: Requested pin could not be found'."),
    ),
    Known(
        words=("http redirect to login page",),
        tools=("gallery-dl",),
        title="Instagram sent gallery-dl to its log-in page.",
        action="login",
        next_step=("It may be private, or not exist. If you can see it while "
                   "logged in, log in to Instagram here, then press Retry."),
        seen="Instagram post C1234567890, an invented id that does not exist.",
    ),
    Known(
        words=("no plugin can handle url",),
        tools=("streamlink",),
        title="Streamlink cannot read this page.",
        retry=False,
        next_step="Streamlink records live streams: paste a live channel's link.",
        seen="https://example.com/: 'error: No plugin can handle URL'.",
    ),
    Known(
        words=("no playable streams found",),
        tools=("streamlink",),
        title="There is no live stream at this link right now.",
        next_step="The channel may be offline, or its name wrong.",
        seen=("Same words for twitch.tv/twitch, /nasa, /riotgames (exist, "
              "offline at the time) and for a channel name that does not "
              "exist. So the message cannot tell the two apart."),
    ),
    Known(
        words=("提取小红书作品链接失败",),
        tools=("xhs-downloader",),
        title="XHS-Downloader found no Xiaohongshu note in this link.",
        retry=False,
        next_step="Check that the link opens a note on xiaohongshu.com.",
        seen=("https://example.com/: '提取小红书作品链接失败' (could not "
              "extract a Xiaohongshu link), exit code 0."),
    ),
    Known(
        words=("获取数据失败",),
        tools=("xhs-downloader",),
        title="XHS-Downloader could not get this note.",
        next_step="Check the link and your internet connection.",
        seen=("'<id> 获取数据失败' (could not get the data) for a note id "
              "that does not exist, AND for a real note with the proxy "
              "pointed at a closed port. Same words, two causes."),
    ),
    Known(
        words=("does not indicate success: 404",),
        tools=("n-m3u8dl-re",),
        title="The server says this stream does not exist (error 404).",
        retry=False,
        next_step="Check the link: it may be mistyped, or no longer there.",
        seen=("https://example.com/nothing-here.m3u8: 'Response status code "
              "does not indicate success: 404 (Not Found)', after 10 tries."),
    ),
    Known(
        words=("input not supported",),
        tools=("n-m3u8dl-re",),
        title="N_m3u8DL-RE cannot read this link.",
        retry=False,
        next_step="It reads links ending in .m3u8 or .mpd.",
        seen="https://example.com/, a web page: 'Unhandled exception: ...: Input not supported'.",
    ),
    Known(
        words=("(10061)",),
        tools=("n-m3u8dl-re",),
        title="The connection was refused (Windows code 10061).",
        next_step="If you use a VPN or a proxy program, check that it is running.",
        seen=("Proxy pointed at a closed port: 'SocketException (10061)', in "
              "the language of Windows. Matched on the code, not the words, "
              "because the words change with the language of Windows."),
    ),
    # Our own sentences (dialogs.TOO_LONG, and the "Save as" one), not a
    # tool's: listed so the failed row offers no Retry -- a Retry goes back
    # to the same folder and the same name, and gets the same answer.
    Known(
        words=("folder's path is too long for windows",),
        tools=("yt-dlp", "gallery-dl", "streamlink", "n-m3u8dl-re", "xhs-downloader",
               "tiktokdownloader", "ks-downloader", "yutto"),
        title="This folder's path is too long for Windows.",
        retry=False,
        next_step=("Choose a folder with a shorter path in Settings → Download folder, "
                   "then paste the link again."),
        seen=("2026-10-24, real runs (yt-dlp, N_m3u8DL-RE, TikTokDownloader) in "
              "a 205-character folder: refused in words, nothing created. "
              "Before, a 278-character path gave '[Errno 2] No such file or "
              "directory'."),
    ),
    Known(
        words=("chosen in \"save as\" is too long for windows",),
        tools=("yt-dlp", "streamlink", "n-m3u8dl-re", "tiktokdownloader", "ks-downloader",
               "yutto"),
        title="The name chosen in \"Save as\" is too long for Windows.",
        retry=False,
        next_step=("Paste the link again and choose a shorter name, or a folder "
                   "with a shorter path."),
        seen=("2026-10-24, a real yt-dlp run: an 80-character name in a "
              "150-character folder was refused in words before starting."),
    ),
    Known(
        words=("did not start", "over proxy"),
        tools=("tiktokdownloader",),
        title="TikTokDownloader could not reach the internet through this PC's proxy.",
        next_step="If you use a VPN or a proxy program, check that it is running.",
        seen=("Proxy pointed at a closed port: at startup it printed 'curl: "
              "(7) Failed to connect to 127.0.0.1:9 over proxy' and never "
              "reached its menu."),
    ),

    # ---- yutto 2.3.1, 2026-11-09 (its words are Chinese).
    Known(
        # "url 不正确，也许该 url 仅支持批量下载" -- "the url is not correct,
        # maybe it only supports batch download".
        words=("url 不正确",),
        tools=("yutto",),
        title="yutto cannot read this Bilibili link.",
        retry=False,
        next_step=("Remove the language part (…/zh-Hans/…) so the link reads "
                   "bilibili.com/video/BV…, then paste it again."),
        seen=("2026-11-09, exit 14 on bilibili.com/zh-Hans/video/BV1DLnJ6xEKC/ "
              "and bilibili.com/en/video/BV1Gsnj6XE9M; the same video's "
              "bilibili.com/video/ link downloaded whole. Also on a bilibili.tv "
              "link, where yutto is no longer offered."),
    ),
    Known(
        # "媒体下载失败：range … failed after 3 attempts: Timeout: error
        # sending request" (or "Transport: error sending request") --
        # "media download failed".
        words=("媒体下载失败", "error sending request"),
        tools=("yutto",),
        title="yutto lost its connection to Bilibili's server, and gave up.",
        next_step="Press Retry: it usually works the next time.",
        seen=("2026-11-09, 3 times in 15 yutto runs of one video, with and "
              "without a log-in: 'Timeout: error sending request' twice, "
              "'Transport: error sending request' once, exit 16; each time "
              "the next run of the same video came whole."),
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
                    "next_step": entry.next_step, "retry": entry.retry,
                    "action": entry.action}
    return {"known": False}
