"""The data of the brain: which site a link belongs to, and which tools can download it.

Two tables live here:

* ``TOOLS``     -- every download tool Teleloadzai knows about.
* ``PLATFORMS`` -- every site, its domains, and the tools that support it.

For a platform, the FIRST tool is the Teleloadzai default. The user may pick
another one (CLAUDE.md, decision 13), so every option carries a short ``why``
text that the UI shows in the dropdown.
"""

from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Tool:
    """One download program."""

    id: str
    name: str
    repo: str   # GitHub "owner/name" -- the Tool Manager (step 4) uses it to check versions
    kind: str   # "exe" = single binary, "python" = pip package. PROVISIONAL: confirm in step 4.


_TOOL_LIST = (
    Tool("yt-dlp", "yt-dlp", "yt-dlp/yt-dlp", "exe"),
    Tool("ffmpeg", "FFmpeg", "BtbN/FFmpeg-Builds", "exe"),
    Tool("gallery-dl", "gallery-dl", "mikf/gallery-dl", "exe"),
    Tool("streamlink", "Streamlink", "streamlink/streamlink", "python"),
    Tool("tiktokdownloader", "TikTokDownloader", "JoeanAmier/TikTokDownloader", "python"),
    Tool("xhs-downloader", "XHS-Downloader", "JoeanAmier/XHS-Downloader", "python"),
    Tool("ks-downloader", "KS-Downloader", "JoeanAmier/KS-Downloader", "exe"),
    Tool("n-m3u8dl-re", "N_m3u8DL-RE", "nilaoda/N_m3u8DL-RE", "exe"),
)

TOOLS: dict[str, Tool] = {t.id: t for t in _TOOL_LIST}


# --------------------------------------------------------------------------
# Platforms
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolOption:
    """One tool proposed for a platform, with the reason shown to the user."""

    tool_id: str
    why: str


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    domains: tuple[str, ...]
    tools: tuple[ToolOption, ...]   # first one = Teleloadzai default
    note: str = ""

    @property
    def default_tool(self) -> str | None:
        return self.tools[0].tool_id if self.tools else None

    @property
    def alternatives(self) -> tuple[ToolOption, ...]:
        return self.tools[1:]

    @property
    def is_supported(self) -> bool:
        return bool(self.tools)


_DRM = ("This site protects its videos and music against copying (DRM). "
        "Teleloadzai does not download protected content.")


def _only_ytdlp(why: str = "the only serious option for this site") -> tuple[ToolOption, ...]:
    return (ToolOption("yt-dlp", why),)


PLATFORMS: tuple[Platform, ...] = (
    Platform("youtube", "YouTube",
             ("youtube.com", "youtu.be", "youtube-nocookie.com"),
             _only_ytdlp()),
    Platform("bilibili", "Bilibili",
             ("bilibili.com", "bilibili.tv", "b23.tv"),
             _only_ytdlp("works well; BBDown is archived since 2026-05")),
    Platform("instagram", "Instagram",
             ("instagram.com", "instagr.am"),
             (ToolOption("gallery-dl", "photos, carousels, stories"),
              ToolOption("yt-dlp", "video only"))),
    Platform("tiktok", "TikTok",
             ("tiktok.com",),
             # Measured 2026-09-25 on the same video: TikTokDownloader
             # 1280x720 (27.0 MB), yt-dlp 1024x576 (18.3 MB) -- and NEITHER
             # had a watermark. These lines said "no watermark" / "may keep
             # the watermark" until then, never checked (decision 38).
             (ToolOption("tiktokdownloader", "higher quality"),
              ToolOption("yt-dlp", "smaller file"))),
    Platform("douyin", "Douyin",
             ("douyin.com", "iesdouyin.com"),
             (ToolOption("tiktokdownloader", "no watermark"),)),
    # One tool, and the only one that works (decision 39). Tested 2026-09-23
    # on the same video: KS-Downloader downloaded it; yt-dlp ("Unsupported
    # URL"), lux and you-get failed. f2, listed here until 2026-09-22, has no
    # Kuaishou at all ("the ks app was not found").
    Platform("kuaishou", "Kuaishou",
             ("kuaishou.com", "gifshow.com"),
             (ToolOption("ks-downloader", "the only program that works on Kuaishou today"),)),
    Platform("xiaohongshu", "Xiaohongshu",
             ("xiaohongshu.com", "xhslink.com"),
             (ToolOption("xhs-downloader", "video and photos, no watermark"),)),
    # f2 was listed first here until 2026-09-26, and never ran once: with
    # the user's Weibo cookies, through its own config file, it saved only
    # the post's text (329 B, 77 B) on two posts where gallery-dl and yt-dlp
    # both gave the same video (118,485,736 B at 1920x1080; 1,810,094 B).
    # Removed from Teleloadzai (decision 39).
    Platform("weibo", "Weibo",
             ("weibo.com", "weibo.cn"),
             (ToolOption("gallery-dl", "the post's own files, video and photos"),
              ToolOption("yt-dlp", "video, or MP3"))),
    Platform("twitter", "X (Twitter)",
             ("twitter.com", "x.com"),
             (ToolOption("yt-dlp", "video"),
              ToolOption("gallery-dl", "images and whole threads"))),
    Platform("facebook", "Facebook",
             ("facebook.com", "fb.watch", "fb.com"),
             _only_ytdlp("public video works; private needs cookies")),
    Platform("reddit", "Reddit",
             ("reddit.com", "redd.it"),
             (ToolOption("yt-dlp", "video and audio merged"),
              ToolOption("gallery-dl", "images and galleries"))),
    Platform("twitch", "Twitch",
             ("twitch.tv",),
             (ToolOption("streamlink", "a LIVE stream, recorded in real time"),
              ToolOption("yt-dlp", "past videos and clips"))),
    Platform("pinterest", "Pinterest",
             ("pinterest.com", "pin.it"),
             (ToolOption("gallery-dl", "boards and pins"),
              ToolOption("yt-dlp", "video pins"))),
    Platform("vimeo", "Vimeo", ("vimeo.com",), _only_ytdlp()),
    Platform("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly"), _only_ytdlp()),
    Platform("rumble", "Rumble", ("rumble.com",), _only_ytdlp()),
    Platform("odysee", "Odysee", ("odysee.com",), _only_ytdlp()),
    Platform("soundcloud", "SoundCloud", ("soundcloud.com",), _only_ytdlp()),
    Platform("bandcamp", "Bandcamp", ("bandcamp.com",), _only_ytdlp()),
    Platform("mixcloud", "Mixcloud", ("mixcloud.com",), _only_ytdlp()),
    Platform("niconico", "Niconico", ("nicovideo.jp",), _only_ytdlp()),
    Platform("archive", "Archive.org", ("archive.org",), _only_ytdlp()),
    Platform("ted", "TED", ("ted.com",), _only_ytdlp()),
    Platform("wechat_channels", "WeChat Channels",
             ("channels.weixin.qq.com", "finder.video.qq.com"),
             (),  # a tool exists, but it does not fit the "paste a link" model
             # Said to the user, so in the user's words and with a next step
             # (§6: "v1 shows a clear message + link"). It used to speak of
             # "the user" and a "root certificate", and stopped there.
             note="WeChat videos cannot be downloaded from a link. A separate "
                  "program does it from inside the WeChat PC app: "
                  "github.com/ltaoo/wx_channels_download. It needs "
                  "administrator rights, so Teleloadzai does not run it for you."),
    # Decision 10: protected against copying (DRM), out of scope for good.
    # Named here so a link is REFUSED on sight. Before 2026-09-25 a Netflix
    # link fell through to "Unknown site" and was offered for download with
    # a bright button; Spotify's got yt-dlp's own "[DRM]" error AND the button.
    # No tools, so `is_supported` is False and no log-in is offered.
    Platform("netflix", "Netflix", ("netflix.com",), (), note=_DRM),
    Platform("disneyplus", "Disney+", ("disneyplus.com",), (), note=_DRM),
    Platform("primevideo", "Prime Video", ("primevideo.com",), (), note=_DRM),
    Platform("spotify", "Spotify", ("spotify.com",), (), note=_DRM),
)

# A link that points straight at a stream manifest, whatever the site is.
STREAM = Platform(
    "stream", "Direct stream link", (),
    (ToolOption("yt-dlp", "simple, works most of the time"),
     ToolOption("n-m3u8dl-re", "faster, and opens streams locked with a key")),
)

# Nothing matched. yt-dlp still knows 1752 sites (checked 2026-09-20), so we try it.
UNKNOWN = Platform(
    "unknown", "Unknown site", (),
    _only_ytdlp("unknown site, but yt-dlp knows 1752 of them - worth trying"),
)

STREAM_EXTENSIONS = (".m3u8", ".mpd")

# Link shorteners that hide the real site. They must be resolved before we can
# detect anything (CLAUDE.md, decision 14). Shorteners that belong to ONE site
# (b23.tv, xhslink.com, redd.it...) are NOT here: they are in the domain table.
GENERIC_SHORTENERS = frozenset({
    "bit.ly", "t.co", "tinyurl.com", "is.gd", "ow.ly", "buff.ly",
    "rb.gy", "cutt.ly", "shorturl.at", "goo.gl", "t.cn", "url.cn",
})

_BY_DOMAIN: dict[str, Platform] = {
    domain: platform for platform in PLATFORMS for domain in platform.domains
}

_BY_ID: dict[str, Platform] = {platform.id: platform for platform in PLATFORMS}

# Some hosts carry several products, so the domain alone is not enough.
# ``weixin.qq.com`` serves many things; only ``/sph/`` is a Channels video.
# (host, path prefix, platform id) -- checked before the domain table.
PATH_RULES: tuple[tuple[str, str, str], ...] = (
    ("weixin.qq.com", "/sph/", "wechat_channels"),
)


def _clean_host(host: str) -> str:
    host = host.lower().strip().strip(".")
    return host[4:] if host.startswith("www.") else host


def platform_for_host(host: str, path: str = "") -> Platform | None:
    """Find the platform of a hostname, or None.

    Matches the exact domain and any subdomain of it, so ``m.youtube.com``
    and ``vt.tiktok.com`` are found without listing them one by one.
    ``path`` is only needed for the few hosts listed in ``PATH_RULES``.
    """
    host = _clean_host(host)

    for rule_host, prefix, platform_id in PATH_RULES:
        if (host == rule_host or host.endswith("." + rule_host)) and path.startswith(prefix):
            return _BY_ID[platform_id]

    if host in _BY_DOMAIN:
        return _BY_DOMAIN[host]
    for domain, platform in _BY_DOMAIN.items():
        if host.endswith("." + domain):
            return platform
    return None


def is_generic_shortener(host: str) -> bool:
    return _clean_host(host) in GENERIC_SHORTENERS


def tool_name(tool_id: str) -> str:
    tool = TOOLS.get(tool_id)
    return tool.name if tool else tool_id
