"""The brain: turn a link into "which platform" and "which tool".

Nothing here downloads anything. It only reads a link and answers three
questions:

1. Which site is this?
2. Which tool should Teleloadzai use by default?
3. Which other tools could the user choose instead?

Short links hide the real site, so they are resolved first by following the
redirect (CLAUDE.md, decision 14). If the site is unknown we do NOT refuse:
we fall back to yt-dlp, which knows 1752 sites.

Test it by hand::

    python -m teleloadzai.detect https://b23.tv/AbCdEf
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from .platforms import (
    STREAM,
    STREAM_EXTENSIONS,
    UNKNOWN,
    Platform,
    ToolOption,
    is_generic_shortener,
    platform_for_host,
    tool_name,
)

# Some shorteners answer with an error page to an unknown client.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
_REDIRECT_TIMEOUT = 8.0


@dataclass(frozen=True)
class Detection:
    """The answer of the brain for one link."""

    given_url: str            # what the user typed, cleaned
    final_url: str            # after following a short link
    platform: Platform
    was_shortened: bool = False
    redirect_error: str | None = None   # set when we could not follow the short link

    @property
    def default_tool(self) -> str | None:
        return self.platform.default_tool

    @property
    def alternatives(self) -> tuple[ToolOption, ...]:
        return self.platform.alternatives

    @property
    def is_supported(self) -> bool:
        return self.platform.is_supported


def normalise_url(raw: str) -> str:
    """Clean what the user pasted: spaces, stray quotes, missing ``https://``."""
    url = raw.strip().strip("<>").strip("\"'")
    if url and "://" not in url:
        url = "https://" + url
    return url


def _looks_like_stream(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith(STREAM_EXTENSIONS)


def resolve_short_link(url: str, timeout: float = _REDIRECT_TIMEOUT) -> tuple[str, str | None]:
    """Follow the redirects of a short link.

    Returns ``(final_url, error)``. On failure the original url comes back
    with a short error message -- we never raise, because a dead shortener
    must not break the app.
    """
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": _USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.geturl(), None
        except urllib.error.HTTPError as exc:
            # The page may answer 404 and still have redirected us to the real site.
            if exc.url and exc.url != url:
                return exc.url, None
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # network down, DNS, timeout, bad TLS...
            last_error = type(exc).__name__
    return url, last_error


def detect(url: str, follow_short_links: bool = True) -> Detection:
    """Read a link and say which platform and which tool."""
    given = normalise_url(url)
    final = given
    was_shortened = False
    error: str | None = None

    host = urlsplit(given).hostname or ""

    if follow_short_links and is_generic_shortener(host):
        was_shortened = True
        final, error = resolve_short_link(given)
        host = urlsplit(final).hostname or host

    # A manifest link wins over the domain: it is a stream whatever the site is.
    if _looks_like_stream(final):
        return Detection(given, final, STREAM, was_shortened, error)

    platform = platform_for_host(host, urlsplit(final).path) or UNKNOWN
    return Detection(given, final, platform, was_shortened, error)


def describe(result: Detection) -> str:
    """One readable block, for the terminal test."""
    lines = [f"link      : {result.given_url}"]
    if result.was_shortened:
        if result.redirect_error:
            lines.append(f"short link: could NOT follow it ({result.redirect_error})")
        else:
            lines.append(f"real link : {result.final_url}")
    lines.append(f"platform  : {result.platform.name}")

    if not result.is_supported:
        lines.append("tool      : NONE")
        lines.append(f"note      : {result.platform.note}")
        return "\n".join(lines)

    default = result.platform.tools[0]
    lines.append(f"default   : {tool_name(default.tool_id)}  ({default.why})")
    for option in result.alternatives:
        lines.append(f"or        : {tool_name(option.tool_id)}  ({option.why})")
    if result.platform.note:
        lines.append(f"note      : {result.platform.note}")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    import sys

    # The Windows console is not UTF-8 by default and platform names can be Chinese.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    follow = "--no-follow" not in argv
    urls = [a for a in argv if not a.startswith("--")]
    if not urls:
        print(__doc__)
        return 1

    for index, url in enumerate(urls):
        if index:
            print("-" * 60)
        print(describe(detect(url, follow_short_links=follow)))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
