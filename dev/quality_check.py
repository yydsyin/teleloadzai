"""The quality check -- run on OUR side only, never on a user's computer.

For each site yt-dlp serves, it reads one public link's list of qualities
(the app's own title-read rule, downloads nothing), once without cookies and
once with the developer's own log-in, and writes:

  data/quality-check/table.json            the latest results (read by the next run)
  data/quality-check/report-<date>.md      what changed, what broke, the full table

Then it DOWNLOADS the file "Best" picked (the download test, the user's plan,
2026-11-16): a read cannot see a file the site's server cuts -- Bilibili's
BV1Gsnj6XE9M listed its AV1 1080p, and the download stopped at 1.3 MB of
23.6 MB (2026-11-09). The file is checked with ffprobe (whole length), then
deleted. When it fails, the other files of the same height are tried (other
codecs), then the app's own rule one height down: the report says what
works instead, so the app can be told, after a review, not to pick the one
that fails. A file over MAX_MB is not downloaded, and that is said.

The OTHER programs (yutto, gallery-dl, TikTokDownloader, XHS-Downloader,
KS-Downloader) are tested the same way, through the app's own code
(runners.run): a real download, each file checked with ffprobe, deleted.
They take the post's file as it is, so when one fails the way out is
another program, not another quality. Streamlink and N_m3u8DL-RE are not
tested (NOT_TESTED says why).

HOW OFTEN (the user's choice, 2026-11-17): every yt-dlp site is READ every
day (no download, seconds). The full download test runs once a week, and at
once when something changed: a yt-dlp release that touched the site, a
program update, a read different from the last one, a failed download on
this PC (data/jobs.json, failed rows by id), a failed test. What is in the
reviewed table (needs.DOWNLOAD_FAILS) is tested every day, so a fixed site
or program loses its warning. On a day with no test, the last result is
kept with its date and gives no new message.

Both are under data/, which git ignores: the report says which sites the
developer is logged in on, and the repository is public. Nothing here
changes the app; a change reaches the app's table only after a review.

Run from the project folder:
  python dev/quality_check.py                every site (the first table, or by hand)
  python dev/quality_check.py --site reddit  one site (can repeat)
  python dev/quality_check.py --due          the daily run: only the sites that are due
  python dev/quality_check.py --no-download  reads only, no download test

A site is due when (1) it was never read or was last read on an earlier day,
(2) a yt-dlp release since the last run changed that site's code (its release
notes, "Extractor changes"), or (3) a download on this PC learned a need
(data/needs.json) that disagrees with the table. Every run adds a line to
data/quality-check/runs.log; a run that finds a change or a broken check, or
that crashes, says so in a Windows message -- a click opens the report.

Cookies: a copy of data/cookies.txt in data/quality-check/run/, deleted after
each read and NEVER written back (cookies.for_one_run writes back, which from
a second program could undo a "Forget them" pressed in the app meanwhile).
No cookie value is ever printed or written: errors go through cookies.redact.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teleloadzai import children, cookies, login, needs, runners, tools, ytdlp  # noqa: E402
from teleloadzai.paths import DATA_DIR  # noqa: E402
from teleloadzai.platforms import PLATFORMS, tool_name  # noqa: E402

LINKS_FILE = Path(__file__).with_name("quality_links.json")
OUT_DIR = DATA_DIR / "quality-check"
TABLE_FILE = OUT_DIR / "table.json"
RUN_COPIES = OUT_DIR / "run"
SETTINGS_FILE = DATA_DIR / "settings.json"
RUNS_LOG = OUT_DIR / "runs.log"
TIMEOUT = 90.0
DOWNLOADS = OUT_DIR / "download"    # one folder per download test, deleted after it
MAX_MB = 300            # YouTube's test link "Best" is 709 MB (2026-11-16): not downloaded
DOWNLOAD_TIMEOUT = 15 * 60.0
# A codec's family from yt-dlp's vcodec ("av01.0.08M…" -> "av01"), and its
# usual name for the report.
_FAMILY = {"vp9": "vp09", "h264": "avc1", "avc3": "avc1", "hev1": "hvc1", "h265": "hvc1"}
_CODEC_NAME = {"avc1": "H.264", "hvc1": "HEVC", "av01": "AV1", "vp09": "VP9"}
_LEFT_BEHIND: list[str] = []        # test folders Windows refused to delete: said in the report

# The preview channel's notes, the same format as stable's ("#### Extractor
# changes", then "- **name**: ..."), seen 2026-11-15 on 2026.11.14.232655.
NOTES_URL = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases?per_page=30"
# Extractor names in those notes -> our site ids (yt-dlp's file names,
# checked against 12 months of notes 2026-11-15).
EXTRACTORS = {
    "youtube": r"^youtube", "bilibili": r"^bili", "instagram": r"instagram",
    "tiktok": r"^tiktok", "weibo": r"weibo", "twitter": r"^twitter|^x$",
    "facebook": r"^facebook", "reddit": r"^reddit", "twitch": r"^twitch",
    "pinterest": r"pinterest", "vimeo": r"^vimeo", "dailymotion": r"dailymotion",
    "rumble": r"rumble", "odysee": r"lbry|odysee", "soundcloud": r"soundcloud",
    "bandcamp": r"bandcamp", "mixcloud": r"mixcloud", "niconico": r"^nico|niconico",
    "archive": r"archive", "ted": r"^ted",
}

# yt-dlp 2026.11.04.232659, Bilibili, seen 2026-11-10 with --no-quiet:
# "[BiliBili] Format(s) 1080P 高码率 are missing; you have to become a premium
# member to download them. Use --cookies-from-browser or --cookies ..."
_MISSING = re.compile(r"Format\(s\) (.+?) are missing; (.+?)\.")


def _cookies_on() -> bool | None:
    """The app's "Use my log-ins" switch, read from its settings file. None
    when the file cannot be read: said as such, never taken for "off"
    (hunt, 2026-11-15)."""
    for _ in range(5):          # the app may be replacing the file this instant
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("cookies_enabled") is True
        except FileNotFoundError:
            return False
        except (OSError, ValueError):
            time.sleep(0.2)
    return None


def _error_of(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # An "ERROR:" with nothing after it is skipped: Bilibili's cut AV1 file
    # gave "ERROR: " then "[download] Got error: 383 bytes read, 22199763
    # more expected. Giving up after 10 retries" (2026-11-16).
    errors = [line for line in lines if line.startswith("ERROR:") and line[6:].strip()]
    chosen = errors[-1] if errors else (lines[-1] if lines else "no message")
    return cookies.redact(chosen)[:240]


def read(url: str, cookie_file: Path | None, prefer: str = "") -> dict:
    """One title read, as the app does it, plus yt-dlp's own "missing" line.
    `prefer`: the codec the app prefers on this site (needs.ytdlp_prefer) --
    the check must test the file the app really picks (hunt, 2026-11-17: it
    tested Bilibili's AV1, which the app no longer takes)."""
    sort = f"res,vcodec:{prefer},{ytdlp.MP4_SORT}" if prefer else f"res,{ytdlp.MP4_SORT}"
    command = [
        str(ytdlp.require_ytdlp()),
        "--dump-single-json", "--no-playlist",
        "--encoding", "utf-8", "--no-colors",
        "--no-quiet",           # the app's read is quiet; the "missing" line needs this
        "-f", ytdlp._MP4_BEST, "-S", sort,
        *(["--cookies", str(cookie_file)] if cookie_file else []),
        url,
    ]
    try:
        finished = ytdlp._run(command, TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"no answer in {int(TIMEOUT)} s"}
    except Exception as problem:            # the check must say it, not stop
        return {"ok": False, "error": cookies.redact(f"{type(problem).__name__}: {problem}")[:240]}

    said = "\n".join([finished.stderr or ""] + [line for line in (finished.stdout or "").splitlines()
                                                 if not line.startswith("{")])
    missing = [{"names": m.group(1), "why": m.group(2)} for m in _MISSING.finditer(said)]
    if finished.returncode != 0:
        error = _error_of(finished.stderr or finished.stdout or "")
        # "Asks for a log-in" is a result, not a broken check: Reddit and
        # Vimeo answered that on every link, 2026-11-15. The app's own narrow
        # rule decides it (cookies.needs_login, only words seen).
        return {"ok": False, "error": error, "needs_login": cookies.needs_login(error)}
    try:
        data = json.loads(next(line for line in finished.stdout.splitlines() if line.startswith("{")))
    except (StopIteration, ValueError):
        return {"ok": False, "error": "yt-dlp gave no readable answer"}

    formats = data.get("formats") or []
    heights = sorted({f["height"] for f in formats
                      if isinstance(f.get("height"), int) and f.get("vcodec") != "none"})
    kbps = sorted({round(f["abr"]) for f in formats
                   if isinstance(f.get("abr"), (int, float)) and f.get("vcodec") in (None, "none")})
    best = data.get("height") if isinstance(data.get("height"), int) else None
    # What the download test needs: the exact file "Best" picked, its length,
    # its size, and the other files of the same height (seen 2026-11-16:
    # Bilibili 1080p = AV1 100026, H.264 30080, HEVC 30077).
    parts = data.get("requested_formats") or [data]
    sizes = [p.get("filesize") or p.get("filesize_approx") for p in parts]
    picked_codec = _family(data.get("vcodec"))
    alternatives = sorted(
        ({"id": f["format_id"], "codec": _family(f.get("vcodec")), "ext": f.get("ext"),
          "audio": f.get("acodec") not in (None, "none"), "tbr": f.get("tbr") or 0}
         for f in formats
         if best and f.get("height") == best and f.get("vcodec") not in (None, "none")
         and f.get("format_id") and f.get("ext") not in ("jpg", "png", "webp", "mhtml")
         and _family(f.get("vcodec")) != picked_codec),
        key=lambda f: (f["ext"] != "mp4", -f["tbr"]))
    one_per_codec: dict[str, dict] = {}
    for alt in alternatives:
        one_per_codec.setdefault(alt["codec"], alt)
    return {"ok": True, "best": best, "heights": heights,
            "kbps": kbps[-1:] if not heights else [], "missing": missing,
            "format_id": data.get("format_id"), "codec": picked_codec,
            "seconds": data.get("duration") if isinstance(data.get("duration"), (int, float)) else None,
            "mb": round(sum(sizes) / 1048576) if sizes and all(sizes) else None,
            "alternatives": list(one_per_codec.values())}


def _family(vcodec: str | None) -> str:
    name = (vcodec or "").split(".")[0].lower()
    return _FAMILY.get(name, name)


def _quality_name(codec: str | None, height: int | None) -> str:
    name = _CODEC_NAME.get(codec or "", codec or "")
    return f"{name} {height or '?'}p" if name else f"{height or '?'}p"


# ---------------------------------------------------------------- the download test

@contextlib.contextmanager
def _cookie_copy():
    """A throwaway copy of our cookie file, deleted when the block ends."""
    RUN_COPIES.mkdir(parents=True, exist_ok=True)
    copy = RUN_COPIES / f"{uuid.uuid4().hex}.txt"
    try:
        shutil.copyfile(cookies.COOKIE_FILE, copy)
        yield copy
    finally:
        copy.unlink(missing_ok=True)


def _remove_test_folder(folder: Path) -> None:
    """Delete one test folder -- only a direct child of DOWNLOADS, never anything else."""
    if folder.resolve().parent != DOWNLOADS.resolve():
        _LEFT_BEHIND.append(f"{folder} (not inside {DOWNLOADS}: not deleted)")
        return
    try:
        shutil.rmtree(folder)
    except OSError as problem:
        _LEFT_BEHIND.append(f"{folder.name}: {problem.strerror}")


def _ffprobe(path: Path) -> tuple[float, int, str] | None:
    """The file's length in seconds, its picture height, and "" -- or why it
    is cut; None when ffprobe cannot read it.

    The length alone does not see a cut MP4: cut at 60 %, a 19 s file still
    said "19.0" (probed 2026-11-16, with and without +faststart). What does:
    the packets really read against the count the file's index promises --
    165 of 284 there, 284 of 284 whole. A file whose index gives no count
    (.webm, .ts) is judged on its length only.
    """
    ffmpeg = ytdlp.find_tool("ffmpeg")
    probe = ffmpeg.with_name("ffprobe.exe") if ffmpeg else None
    if probe is None or not probe.is_file():
        return None
    try:
        asked = subprocess.run(
            [str(probe), "-v", "error", "-count_packets", "-show_entries",
             "format=duration:stream=codec_type,height,nb_frames,nb_read_packets",
             "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(asked.stdout or "{}")
        seconds = float(data["format"]["duration"])
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None
    streams = data.get("streams") or []
    heights = [s.get("height") for s in streams
               if s.get("codec_type") == "video" and isinstance(s.get("height"), int)]
    cut = ""
    for s in streams:
        try:
            promised, read_ = int(s["nb_frames"]), int(s["nb_read_packets"])
        except (KeyError, TypeError, ValueError):
            continue
        if promised > 0 and read_ < promised:
            cut = f"the file is cut: {s.get('codec_type', 'a')} stream {read_} of {promised} packets"
            break
    return seconds, max(heights) if heights else 0, cut


def fetch(url: str, rule: list[str], cookie_file: Path | None, seconds: float | None) -> dict:
    """Download once with `rule` (yt-dlp's -f …) into a folder of its own,
    look at the file with ffprobe, delete it. {"ok": True} only for one whole file."""
    folder = DOWNLOADS / uuid.uuid4().hex
    try:
        folder.mkdir(parents=True)
    except OSError as problem:
        return {"ok": False, "error": f"the test folder could not be made: {problem.strerror}"}
    try:
        try:
            command = [
                str(ytdlp.require_ytdlp()),
                "--no-playlist", "--encoding", "utf-8", "--no-colors", "--no-warnings", "--no-progress",
                *rule,
                "--merge-output-format", "mp4",
                *ytdlp._ffmpeg_arguments(),
                *(["--cookies", str(cookie_file)] if cookie_file else []),
                "-o", str(folder).replace("%", "%%") + "\\test.%(ext)s",
                url,
            ]
            finished = ytdlp._run(command, DOWNLOAD_TIMEOUT)
        except Exception as problem:            # a timeout, FFmpeg missing: said, not a stop
            return {"ok": False, "error": cookies.redact(f"{type(problem).__name__}: {problem}")[:240]}
        try:
            files = [f for f in folder.iterdir() if f.is_file()]
            got = sum(f.stat().st_size for f in files)
        except OSError as problem:
            return {"ok": False, "error": f"the test folder could not be read: {problem.strerror}"}
        if finished.returncode != 0:
            return {"ok": False, "bytes": got,
                    "error": _error_of(finished.stderr or finished.stdout or "")}
        if len(files) != 1:
            return {"ok": False, "bytes": got,
                    "error": f"yt-dlp said done, but left {len(files)} files: "
                             + ", ".join(f.name for f in files)[:160]}
        looked = _ffprobe(files[0])
        if looked is None:
            return {"ok": False, "bytes": got, "error": "ffprobe could not read the file"}
        length, height, cut = looked
        if cut:
            return {"ok": False, "bytes": got, "height": height, "error": cut}
        if seconds and length < seconds * 0.98 - 1:
            return {"ok": False, "bytes": got, "height": height,
                    "error": f"the file is cut: {length:.0f} s of {seconds:.0f} s"}
        return {"ok": True, "bytes": got, "height": height, "seconds": round(length)}
    finally:
        _remove_test_folder(folder)


def _app_rule(height: int) -> list[str]:
    """The app's own -f / -S for a chosen height (ytdlp._output_arguments), nothing else."""
    words = ytdlp._output_arguments("mp4", DOWNLOADS, str(height), None, "")
    rule = []
    for flag in ("-f", "-S"):
        if flag in words:
            rule += [flag, words[words.index(flag) + 1]]
    return rule


def test_download(url: str, state: dict, cookie_file: Path | None) -> dict | None:
    """Download what "Best" picked; when it fails, what works instead."""
    if not state.get("ok") or not state.get("format_id"):
        return None
    if state.get("mb") and state["mb"] > MAX_MB:
        return {"skipped": f"about {state['mb']} MB, over the {MAX_MB} MB limit"}
    best, seconds = state.get("best"), state.get("seconds")
    first = fetch(url, ["-f", state["format_id"]], cookie_file, seconds)
    result = {"format": state["format_id"], "codec": state.get("codec"), "height": best, **first}
    if first["ok"] or not best:
        return result
    tries = []
    for alt in state.get("alternatives") or []:
        rule = ["-f", alt["id"] if alt["audio"] else f"{alt['id']}+bestaudio[ext=m4a]/{alt['id']}+bestaudio"]
        got = fetch(url, rule, cookie_file, seconds)
        tries.append({"format": alt["id"], "codec": alt["codec"], "height": best, **got})
        if got["ok"]:
            break
    else:
        lower = [h for h in state.get("heights") or [] if h < best]
        if lower:
            got = fetch(url, _app_rule(lower[-1]), cookie_file, seconds)
            tries.append({"format": f"the app's {lower[-1]}p rule", "codec": None,
                          "height": lower[-1], **got})
    result["instead"] = tries
    return result


def test_avoided(url: str, picked: dict) -> dict:
    """The file the reviewed table makes the app AVOID (Bilibili's AV1 1080p):
    still failing, or whole again -- then the table's line can be removed.
    Read with the plain rule, downloaded once, without cookies."""
    plain_pick = read(url, None)
    if not plain_pick.get("ok"):
        return {"ok": False, "error": plain_pick.get("error", "the read failed")}
    if plain_pick.get("format_id") == picked.get("format_id"):
        return {"same": True}       # nothing avoided on this video
    got = fetch(url, ["-f", plain_pick["format_id"]], None, plain_pick.get("seconds"))
    return {"format": plain_pick["format_id"], "codec": plain_pick.get("codec"),
            "height": plain_pick.get("best"), **got}


def with_my_cookies(url: str, download: bool, plain_format: str | None, prefer: str = "") -> dict:
    """The same read with a throwaway copy of our cookie file -- and the
    download test, unless it picked the same file as without cookies."""
    try:
        with _cookie_copy() as copy:
            state = read(url, copy, prefer)
            if download and state.get("ok"):
                if state.get("format_id") == plain_format:
                    state["download"] = {"same": True}
                else:
                    state["download"] = test_download(url, state, copy)
            return state
    except OSError as problem:
        return {"ok": False, "error": f"the cookie copy failed: {problem.strerror}"}


# ---------------------------------------------------------------- the other programs

# Every program a site offers besides yt-dlp is tested by a real download
# through the app's own code (runners.run), the user's plan of 2026-11-16.
# Most take the post's file as it is: when one fails, the way out is another
# PROGRAM, not another quality. Two cannot be tested:
NOT_TESTED = {
    "streamlink": "its qualities exist only during a live stream",
    "n-m3u8dl-re": "no site of its own, and no stable public link",
}
PROGRAM_LINKS = 2               # links tried per program before "fails on every link"
_PICTURES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")


def program_pairs(links: dict) -> list[tuple[str, str]]:
    """(site, program) for every program a site with a test link offers, yt-dlp aside."""
    return [(p.id, o.tool_id) for p in PLATFORMS for o in p.tools
            if p.id in links and o.tool_id != "yt-dlp" and o.tool_id not in NOT_TESTED]


def program_version(tool: str) -> str:
    """The installed version, else the file's stamp (TikTokDownloader and
    KS-Downloader have no readable version, decision 31): it changes when
    the program is updated, which makes the pair due."""
    try:
        version = tools.installed_version(tool)
        path = tools.installed_path(tool)
        return version or (tools._file_stamp(path) if path else "")
    except Exception:
        return ""


def run_program(tool: str, url: str, cookie_file: Path | None, header: bool) -> dict:
    """One download through the app's own runner, into a folder of its own;
    every file looked at with ffprobe, then deleted."""
    folder = DOWNLOADS / uuid.uuid4().hex
    try:
        folder.mkdir(parents=True)
    except OSError as problem:
        return {"ok": False, "error": f"the test folder could not be made: {problem.strerror}"}
    stop = threading.Event()
    started: list[subprocess.Popen] = []

    def give_up() -> None:      # no end in DOWNLOAD_TIMEOUT: Stop, as the app's button
        stop.set()
        for process in started:
            children.stop_tree(process)

    timer = threading.Timer(DOWNLOAD_TIMEOUT, give_up)
    timer.start()
    try:
        request = runners.Request(url=url, out_dir=folder, mode="mp4", quality="best",
                                  limit_minutes=5, cookie_file=cookie_file,
                                  cookie_header=header, stop=stop)
        try:
            result = runners.run(tool, request, on_start=started.append)
        except Exception as problem:
            if stop.is_set():
                return {"ok": False, "error": f"no end in {int(DOWNLOAD_TIMEOUT / 60)} minutes"}
            text = cookies.redact(f"{problem}")[:240]
            # Port 5555 / 5557 held -- by the app's own server during a
            # download, or another program: the check is broken, not the program.
            return {"ok": False, "error": text, "port_taken": text.startswith("Port ")}
        if result.nothing_downloaded:
            return {"ok": False, "error": result.skip_reason or "the program wrote no file"}
        videos, pictures, total, top = 0, 0, 0, 0
        for path in result.files:
            try:
                total += path.stat().st_size
            except OSError:
                return {"ok": False, "error": f"a file it reported is not there: {path.name}"}
            if path.suffix.lower() in _PICTURES:
                pictures += 1
                continue
            looked = _ffprobe(path)
            if looked is None:
                return {"ok": False, "bytes": total, "error": f"ffprobe could not read {path.suffix} file"}
            length, height, cut = looked
            if cut or length <= 0:
                return {"ok": False, "bytes": total, "error": cut or "a file of 0 seconds"}
            videos += 1
            top = max(top, height)
        return {"ok": True, "bytes": total, "videos": videos, "pictures": pictures, "height": top}
    finally:
        timer.cancel()
        _remove_test_folder(folder)


def check_program(site: str, tool: str, links: list[str], cookies_on: bool | None) -> dict:
    """Without cookies first; with the developer's cookies only when that failed
    (a program that works without needs none). The first link that works in
    either state is kept; PROGRAM_LINKS links, then "fails on every link"."""
    result: dict = {"checked": time.strftime("%Y-%m-%d %H:%M"), "version": program_version(tool),
                    "failed_links": []}
    if tools.installed_path(tool) is None:
        result["not_installed"] = True
        return result
    takes_file, takes_site = tool in cookies.FILE_CAPABLE, cookies.takes_site_cookies(tool)
    if cookies_on is None:
        mine_skip = "the app's settings file could not be read"
    elif not cookies_on:
        mine_skip = "“Use my log-ins” is off in the app"
    elif not cookies.COOKIE_FILE.is_file():
        mine_skip = "no cookie file"
    elif login.site_state(site) == "none":
        mine_skip = "no cookies for this site"
    elif not (takes_file or takes_site):
        mine_skip = "this program takes no cookies from Teleloadzai"
    else:
        mine_skip = ""
    for number, url in enumerate(links[:PROGRAM_LINKS], 1):
        plain = run_program(tool, url, None, False)
        if plain.get("port_taken"):
            result.update(broken=True, port_taken=plain["error"])
            return result
        # yutto works without a log-in, but at 480p (runners.TOP_WITHOUT_LOGIN):
        # its log-in is what gives the 1080p, so that run is not "not needed".
        if plain["ok"] and not runners.top_height(tool, False):
            mine = {"skipped": "not needed: it worked without"}
        elif mine_skip:
            mine = {"skipped": mine_skip}
        else:
            try:
                with _cookie_copy() as copy:
                    mine = run_program(tool, url, copy if takes_file else None, takes_site)
            except OSError as problem:
                mine = {"ok": False, "error": f"the cookie copy failed: {problem.strerror}"}
        if plain["ok"] or mine.get("ok"):
            result.update(link=url, link_number=number, no_cookies=plain, your_cookies=mine)
            return result
        result["failed_links"].append({"number": number, "url": url, "no_cookies": plain, "your_cookies": mine})
    result["fails"] = True
    return result


def _program_said(state: dict | None) -> str:
    if not state:
        return "—"
    if state.get("skipped"):
        return f"not run ({state['skipped']})"
    if not state.get("ok"):
        got = f", {state['bytes'] / 1048576:.1f} MB received" if state.get("bytes") else ""
        return f"FAILED{got} — {state.get('error', '')}"
    what = []
    if state.get("videos"):
        what.append(f"{state['videos']} video{'s' if state['videos'] != 1 else ''}"
                    + (f" up to {state['height']}p" if state.get("height") else ""))
    if state.get("pictures"):
        what.append(f"{state['pictures']} picture{'s' if state['pictures'] != 1 else ''}")
    return f"whole: {', '.join(what) or 'files'}, {state['bytes'] / 1048576:.1f} MB"


def due_programs(pairs: list[tuple[str, str]], table: dict,
                 failed_pairs: set[str] | None = None) -> dict[str, str]:
    """{"site|program": why it is due} -- each test is a real download: weekly,
    daily for what is in the reviewed table or failing, at once after an
    update or a failed download on this PC (the user's plan, 2026-11-17)."""
    failed_pairs = failed_pairs or set()
    due: dict[str, str] = {}
    old = table.get("programs", {})
    for site, tool in pairs:
        key, entry = f"{site}|{tool}", old.get(f"{site}|{tool}") or {}
        if not entry.get("checked"):
            due[key] = "never tested"
        elif entry.get("broken") or entry.get("fails"):
            due[key] = "its last test failed"
        # Not installed: due again only when its version changes (installed),
        # not every day -- that would be a daily message for nothing.
        elif entry.get("version") != program_version(tool):
            due[key] = "the program was updated"
        elif entry.get("not_installed"):
            pass
        elif entry["checked"][:10] >= time.strftime("%Y-%m-%d"):
            pass                # already tested today
        elif needs.download_fail(site, tool):
            due[key] = "it is in the reviewed table (tested daily, so a fixed program loses its warning)"
        elif key in failed_pairs:
            due[key] = "a download on this PC failed"
        elif entry["checked"][:10] <= _days_ago(WEEK_DAYS):
            due[key] = f"last tested on {entry['checked'][:10]}"
    return due


def _read_changed(before: dict | None, now: dict) -> bool:
    """The read differs from the last one on the same link: another file picked,
    or other sizes offered -- worth a full test the same day."""
    if not before or not before.get("ok") or not now.get("ok"):
        return False
    return (before.get("format_id") != now.get("format_id")
            or before.get("heights") != now.get("heights"))


def _carried(before_state: dict | None, on: str | None) -> dict | None:
    """The last full test's result, kept on a day with none -- marked with its date."""
    old = (before_state or {}).get("download")
    if not old or not on:
        return None
    return {**old, "from": old.get("from") or on}


def check_site(site: str, links: list[str], cookies_on: bool | None, download: bool = True,
               before: dict | None = None, full_test: str = "") -> dict:
    """The day's read; the full download test only for a reason -- `full_test`
    (decided before), or the read changed since the last time (the user's
    plan, 2026-11-17: read every day, download weekly or on a change)."""
    before = before or {}
    prefer = needs.ytdlp_prefer(site, "mp4", "best")    # the app's own pick
    result: dict = {"checked": time.strftime("%Y-%m-%d %H:%M"), "failed_links": []}
    sign = login.site_state(site)
    result["sign"] = sign
    for number, url in enumerate(links, 1):
        plain = read(url, None, prefer)
        if plain["ok"] or plain.get("needs_login"):
            result.update(link=url, link_number=number, no_cookies=plain)
            break
        result["failed_links"].append({"number": number, "error": plain["error"]})
    else:
        result["broken"] = True
        return result
    same_link = before.get("link") == result["link"]
    if not full_test and same_link and _read_changed(before.get("no_cookies"), plain):
        full_test = "the read changed since the last time"
    download = download and bool(full_test)
    if download:
        result["downloaded"], result["full_test_why"] = time.strftime("%Y-%m-%d"), full_test
    else:
        result["downloaded"] = before.get("downloaded") if same_link else None
    if download and plain["ok"]:
        plain["download"] = test_download(result["link"], plain, None)
        if prefer and plain["download"] and not plain["download"].get("skipped"):
            plain["download"]["avoided"] = test_avoided(result["link"], plain)
    # Carried only on a day WITHOUT a test: on a test day whose read failed,
    # the old result was stamped with today's date (hunt, 2026-11-17).
    elif not download and same_link and _carried(before.get("no_cookies"), result["downloaded"]):
        plain["download"] = _carried(before.get("no_cookies"), result["downloaded"])

    if cookies_on is None:
        result["your_cookies"] = {"skipped": "the app's settings file could not be read"}
    elif not cookies_on:
        result["your_cookies"] = {"skipped": "“Use my log-ins” is off in the app"}
    elif not cookies.COOKIE_FILE.is_file():
        result["your_cookies"] = {"skipped": "no cookie file"}
    elif sign == "none":
        result["your_cookies"] = {"skipped": "no cookies for this site"}
    else:
        result["your_cookies"] = with_my_cookies(result["link"], download, plain.get("format_id"), prefer)
        if not download and same_link and _carried(before.get("your_cookies"), result["downloaded"]):
            result["your_cookies"]["download"] = _carried(before.get("your_cookies"), result["downloaded"])
    return result


WEEK_DAYS = 7               # the full download test of everything, once a week


def _days_ago(days: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))


def failed_rows() -> tuple[dict[str, str] | None, str]:
    """{row id: "site|program"} of the failed downloads in data/jobs.json, and
    a problem to say -- None when the file could not be read (then nothing is
    marked seen: hunt, 2026-11-17, an unreadable file forgot every failure).
    The file has no dates: rows already seen are remembered by their id."""
    jobs_file = DATA_DIR / "jobs.json"
    problem = ""
    for _ in range(5):          # the app may be replacing the file this instant
        try:
            data = json.loads(jobs_file.read_text(encoding="utf-8"))
            rows = data.get("jobs", []) if isinstance(data, dict) else data
            return ({r["id"]: f"{r.get('platform')}|{r.get('tool')}" for r in rows
                     if isinstance(r, dict) and r.get("state") == "error" and r.get("id")}, "")
        except FileNotFoundError:
            return {}, ""
        except (OSError, ValueError) as error:
            problem = f"data/jobs.json could not be read ({type(error).__name__}), so failed downloads on this PC were not looked at"
            time.sleep(0.2)
    return None, problem


def new_failures(table: dict, rows: dict[str, str] | None) -> set[str]:
    """{"site|program"} of the failed rows not yet tested."""
    seen = set(table.get("failed_jobs_seen") or [])
    return {pair for row, pair in (rows or {}).items() if row not in seen}


def seen_after(table: dict, rows: dict[str, str] | None, tested: set[str], testable: set[str]) -> list[str]:
    """The failed rows to remember as seen: those seen before, those whose
    pair was really tested in this run, and those no test can cover (no link,
    a program not tested). A failure not tested stays new for the next run
    (hunt, 2026-11-17: --site, --no-download, a pair tested earlier the same
    day marked it seen without a test). Rows gone from the list are dropped."""
    if rows is None:
        return list(table.get("failed_jobs_seen") or [])
    seen = set(table.get("failed_jobs_seen") or [])
    keep = [row for row, pair in rows.items() if row in seen or pair in tested or pair not in testable]
    return keep[-500:]


def full_test_reasons(sites: list[str], table: dict, read_reasons: dict[str, str],
                      failed_pairs: set[str]) -> dict[str, str]:
    """{site: why yt-dlp's download test runs today} -- weekly, or at once on a
    change; the read itself runs every day."""
    old = table.get("sites", {})
    reasons: dict[str, str] = {}
    for site in sites:
        entry, why = old.get(site) or {}, read_reasons.get(site, "")
        last = [(entry.get(s) or {}).get("download") or {} for s in ("no_cookies", "your_cookies")]
        if not entry.get("downloaded"):
            reasons[site] = "never tested by a download"
        elif any("ok" in d and not d["ok"] for d in last):
            # Retested at once, as the programs are: a site fixed the next day
            # was noticed up to a week late (hunt, 2026-11-17).
            reasons[site] = "its last download test failed"
        elif needs.download_fail(site, "yt-dlp"):
            reasons[site] = "it is in the reviewed table (tested daily, so a fixed site loses its warning)"
        elif why.startswith(("yt-dlp ", "a download on this PC", "more than 30", "its last read failed")):
            reasons[site] = why
        elif f"{site}|yt-dlp" in failed_pairs:
            reasons[site] = "a download on this PC failed"
        elif entry["downloaded"] <= _days_ago(WEEK_DAYS):
            reasons[site] = f"last full test on {entry['downloaded']}"
    return reasons


# ---------------------------------------------------------------- what is due

def _tag(text: str) -> tuple[int, ...]:
    """"2026.11.14.232655" -> numbers, so tags compare as dates."""
    return tuple(int(part) for part in re.findall(r"\d+", text or ""))


def releases_since(seen: str) -> tuple[list[tuple[str, set[str]]], bool]:
    """yt-dlp releases newer than `seen`, each with the sites its notes name,
    and whether the list reaches back to `seen` -- False when more releases
    came out than the page holds (30): the older ones' notes were not read."""
    request = urllib.request.Request(NOTES_URL, headers={
        "User-Agent": "quality-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        rows = json.load(answer)
    tags = [_tag(row.get("tag_name") or "") for row in rows]
    complete = not tags or not _tag(seen) or min(tags) <= _tag(seen)
    found = []
    for row in rows:
        tag, body = row.get("tag_name") or "", row.get("body") or ""
        if _tag(tag) <= _tag(seen):
            continue
        start = body.find("Extractor changes")
        names = []
        if start >= 0:
            end = body.find("\n#### ", start)
            names = re.findall(r"^\s*- \*\*([^*]+)\*\*", body[start:end if end > 0 else None], re.M)
        sites = {site for site, pattern in EXTRACTORS.items()
                 if any(re.search(pattern, name.strip().lower()) for name in names)}
        found.append((tag, sites))
    return sorted(found, key=lambda pair: _tag(pair[0])), complete


def due_sites(sites: list[str], table: dict, notes_seen: str) -> tuple[dict[str, str], str, list[str]]:
    """{site: why it is due}, the newest release read, and problems to say."""
    due: dict[str, str] = {}
    problems: list[str] = []
    old = table.get("sites", {})
    for site in sites:
        entry = old.get(site) or {}
        checked = entry.get("checked")
        if not checked:
            due[site] = "never read"
            continue
        if entry.get("retry") or entry.get("broken"):
            # Its last read failed (no network, links gone): the reason it was
            # due is not spent by a failure (hunt, 2026-11-15).
            due[site] = "its last read failed"
            continue
        # Every day (the user, 2026-11-17; was 90 days since 2026-11-15): a
        # calendar day, not 24 hours -- the first log-on moves.
        if checked[:10] < time.strftime("%Y-%m-%d"):
            due[site] = f"last read on {checked[:10]}"

    newest = notes_seen
    try:
        releases, complete = releases_since(notes_seen)
        if not complete:
            # More releases than one page of notes: the older ones were not
            # read, so any site may have changed -- all of them are read.
            for site in sites:
                due.setdefault(site, "more than 30 yt-dlp releases since the last run")
        for tag, named in releases:
            newest = tag
            for site in sorted(named & set(sites)):
                due.setdefault(site, f"yt-dlp {tag} changed its code for this site")
    except Exception as problem:            # said in the report, never silent
        problems.append(f"yt-dlp's release notes could not be read: {type(problem).__name__}: {problem}")

    try:
        learned = needs.all_needs()
    except Exception as problem:
        learned = {}
        problems.append(f"data/needs.json could not be read: {type(problem).__name__}")
    for key, seen in learned.items():
        site, _, program = key.partition("|")
        before = old.get(site) or {}
        if program != "yt-dlp" or site not in sites or not before.get("checked"):
            continue
        if seen.get("seen", "") <= before["checked"][:10]:
            continue
        expected = "account" if (before.get("no_cookies") or {}).get("needs_login") else "none"
        if seen.get("need") != expected:
            due.setdefault(site, f"a download on this PC learned “{seen.get('need')}” "
                                 f"on {seen.get('seen')}; the table says “{expected}”")
    return due, newest, problems


def tell(title: str, text: str, report_file: Path | None) -> None:
    """A Windows message, through the app's own (notify.py); a click opens the report."""
    try:
        from teleloadzai import notify
        notify.set_app_id()
        if report_file is not None:
            notify.on_click = lambda: os.startfile(report_file)
        notify._start()
        notify._shows.put((title, text))
        notify._wake()
        time.sleep(12)          # the icon lives only with its box: closing ends it
        notify.close()
    except Exception as problem:
        # Under pythonw.exe a print goes nowhere: the log keeps it (hunt,
        # 2026-11-15). Not a "PROBLEM" line -- a lost message is no reason
        # to read the sites again.
        print(f"The Windows message could not be shown: {problem}")
        log_run(f"MESSAGE NOT SHOWN ({title}): {type(problem).__name__}: {problem}")


def _ran_today() -> bool:
    """A finished run is already in today's log. The task starts at each log-on
    (the PC is off at any fixed hour, 2026-11-15): once a day is enough. A crash
    does not count, nor a run that met a problem (release notes unreadable,
    no network) -- the next log-on tries again (hunt, 2026-11-15)."""
    try:
        lines = RUNS_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    today = time.strftime("%Y-%m-%d")
    return any(line.startswith(today) and "CRASHED" not in line and "PROBLEM:" not in line
               and "MESSAGE NOT SHOWN" not in line for line in lines)


def log_run(line: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with RUNS_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M')}  {line}\n")


# ---------------------------------------------------------------- the report

def _said(state: dict | None) -> str:
    if not state:
        return "—"
    if state.get("skipped"):
        return f"not read ({state['skipped']})"
    if state.get("needs_login"):
        return "yt-dlp asks for a log-in"
    if not state.get("ok"):
        return f"failed: {state.get('error', '')}"
    if state.get("heights"):
        text = f"{state['best'] or '?'}p (offers {', '.join(map(str, state['heights']))})"
    elif state.get("kbps"):
        text = f"sound only, {state['kbps'][0]} kbps"
    else:
        text = "no quality listed"
    for gap in state.get("missing") or []:
        text += f" · missing: {gap['names']} ({gap['why']})"
    return text


def _one_try(t: dict) -> str:
    name = t["format"] if t.get("codec") is None else f"{_quality_name(t['codec'], t['height'])} ({t['format']})"
    if t.get("ok"):
        return f"{name}: whole, {t['bytes'] / 1048576:.1f} MB, {t['height']}p, {t['seconds']} s"
    got = f", {t['bytes'] / 1048576:.1f} MB received" if t.get("bytes") else ""
    return f"{name}: FAILED{got} — {t.get('error', '')}"


def _download_said(d: dict | None) -> str:
    """The download test in one cell; "—" when there was none."""
    if not d:
        return "—"
    if d.get("same"):
        return "same file as without cookies"
    if d.get("skipped"):
        return f"not downloaded ({d['skipped']})"
    text = (f"(full test of {d['from']}) " if d.get("from") else "") + _one_try(d)
    for t in d.get("instead") or []:
        text += f" → {_one_try(t)}"
    if not d.get("ok") and not d.get("instead"):
        text += " → nothing else to try"
    return text


def _download_key(d: dict | None) -> tuple | None:
    """What a change of the download test is; None when there is nothing to compare."""
    if not d or d.get("same") or d.get("skipped"):
        return None
    return (d.get("format"), bool(d.get("ok")),
            tuple((t.get("format"), bool(t.get("ok"))) for t in d.get("instead") or []))


def _key(state: dict | None) -> tuple:
    if state and state.get("needs_login"):
        return ("asks for a log-in",)
    if not state or not state.get("ok"):
        return ("not ok", (state or {}).get("skipped", ""))
    return (state.get("best"), tuple(state.get("heights") or ()), tuple(state.get("kbps") or ()),
            tuple(g["names"] for g in state.get("missing") or ()))


def report(new: dict, old: dict, header: list[str],
           new_programs: dict | None = None, old_programs: dict | None = None
           ) -> tuple[str, int, int, int, int]:
    """The report's text, and how many changes, broken checks, files that do
    not download, and NEW failures (failing now, not at the last test) it
    holds -- the Windows message counts only the new ones: a failure retested
    every day must not send the same message every day."""
    names = {p.id: p.name for p in PLATFORMS}
    changed, broken, fails, table_lines = [], [], [], []
    new_fails = 0
    new_programs, old_programs = new_programs or {}, old_programs or {}
    for key, now in new_programs.items():
        site, _, tool = key.partition("|")
        label = f"**{names.get(site, site)}** · {tool_name(tool)}"
        if now.get("port_taken"):
            broken.append(f"- {label}: not tested — {now['port_taken']}")
        elif now.get("fails"):
            tries = "; ".join(f"link {f['number']}: no cookies {_program_said(f['no_cookies'])}, "
                              f"your cookies {_program_said(f['your_cookies'])}" for f in now["failed_links"])
            fails.append(f"- {label}: failed on every link tried — the program, the site or "
                         f"the links. {tries}")
            new_fails += not (old_programs.get(key) or {}).get("fails")
        before = old_programs.get(key) or {}
        if before.get("link") and before.get("link") == now.get("link"):
            for state, words in (("no_cookies", "no cookies"), ("your_cookies", "your cookies")):
                was, is_ = before.get(state) or {}, now.get(state) or {}
                if "ok" in was and "ok" in is_ and was["ok"] != is_["ok"]:
                    changed.append(f"- {label} · {words}: {_program_said(was)} → {_program_said(is_)}")
        elif before.get("link") and now.get("fails"):
            changed.append(f"- {label}: worked on {before['checked'][:10]} → fails now")
        elif before.get("fails") and now.get("link"):
            changed.append(f"- {label}: failed on {before['checked'][:10]} → works now")
    for site, now in new.items():
        before = old.get(site)
        name = names.get(site, site)
        for state, label in (("no_cookies", "no cookies"), ("your_cookies", "your cookies")):
            d = (now.get(state) or {}).get("download")
            # Today's tests only: a failure carried from an earlier day was
            # already said (no daily message for one old result).
            if d and not d.get("same") and not d.get("skipped") and not d.get("ok") and not d.get("from"):
                fails.append(f"- **{name}** · {label} · {now.get('link')}: {_download_said(d)}")
                was = ((before or {}).get(state) or {}).get("download") or {}
                new_fails += not ("ok" in was and not was["ok"])
            # The file the reviewed table makes the app avoid: still failing,
            # or whole again (then its line can go).
            avoided = (d or {}).get("avoided") if d and not d.get("from") else None
            if avoided and not avoided.get("same"):
                entry = needs.download_fail(site, "yt-dlp") or {}
                what = _one_try(avoided)
                if avoided.get("ok"):
                    table_lines.append(f"- **{name}** · {label}: the avoided file came WHOLE — {what}. "
                                       f"The table's line (avoid {entry.get('avoid', '?')}) can be removed.")
                    changed.append(f"- **{name}**: the file the table avoids came whole — its line can be removed")
                else:
                    table_lines.append(f"- **{name}** · {label}: the avoided file still fails — {what}")
        if now.get("broken"):
            errors = "; ".join(f"link {f['number']}: {f['error']}" for f in now["failed_links"])
            # yt-dlp failing on every link of ONE site is a result to review,
            # like another program's (the user, 2026-11-16: "verify the
            # availability of every tool"); every site failing is the network.
            if all(n.get("broken") for n in new.values()) and len(new) > 1:
                broken.append(f"- **{name}**: no link could be read — the site, the links or the network. {errors}")
            else:
                fails.append(f"- **{name}** · yt-dlp: failed on every link tried — the program, the site "
                             f"or the links. {errors}")
                new_fails += not ((before or {}).get("broken") or (before or {}).get("retry"))
            continue
        if now.get("link_number", 1) > 1:
            broken.append(f"- **{name}**: link 1 failed, link {now['link_number']} used. "
                          + "; ".join(f"link {f['number']}: {f['error']}" for f in now["failed_links"]))
        if not before or before.get("broken"):
            continue
        if before.get("link") != now.get("link"):
            continue                    # another video: not comparable
        for state, label in (("no_cookies", "no cookies"), ("your_cookies", "your cookies")):
            if _key(before.get(state)) != _key(now.get(state)):
                changed.append(f"- **{name}** · {label}: {_said(before.get(state))} → {_said(now.get(state))}")
            # The download test: compared only when both runs made one (the
            # first run with it must not mark every site "changed").
            was, is_ = ((before.get(state) or {}).get("download"), (now.get(state) or {}).get("download"))
            if _download_key(was) and _download_key(is_) and _download_key(was) != _download_key(is_):
                changed.append(f"- **{name}** · {label} · download: {_download_said(was)} → {_download_said(is_)}")

    lines = [f"# Quality check — {time.strftime('%Y-%m-%d %H:%M')}", "", *header, ""]
    if new and all(now.get("broken") for now in new.values()):
        lines += ["🚨 **Every site failed.** Suspect the network or this script first, not the sites.", ""]
    lines += ["## Does not download", "",
              "yt-dlp: the file \"Best\" picks failed or came cut — what works instead is after "
              "the arrow. Other programs: the post failed on every link tried — the app can then "
              "start on another program. Nothing here reaches the app before your review.", ""]
    tested = new_programs or any((now.get(s) or {}).get("download")
                                 for now in new.values() for s in ("no_cookies", "your_cookies"))
    lines += fails or ["Nothing failed." if tested else "No download test in this run."]
    # Sizes a site gives yt-dlp only with the developer's cookies: candidates
    # for the card's locked sizes (needs.py, after review).
    login_only = []
    for site, now in new.items():
        plain, mine = now.get("no_cookies") or {}, now.get("your_cookies") or {}
        if plain.get("ok") and mine.get("ok"):
            extra = sorted(set(mine.get("heights") or []) - set(plain.get("heights") or []))
            if extra:
                login_only.append(f"- **{names.get(site, site)}** · yt-dlp: "
                                  f"{', '.join(f'{h}p' for h in extra)} only with your cookies")
    if table_lines:
        lines += ["", "## The reviewed table (needs.DOWNLOAD_FAILS)", ""] + table_lines
    lines += ["", "## Sizes only with your log-in", "",
              "Candidates for the card's locked sizes (grey, with the log-in that unlocks them).", ""]
    lines += login_only or ["None found."]
    lines += ["", "## Changed since the last check", ""]
    lines += changed or ["Nothing changed." if old else "First run: nothing to compare with."]
    lines += ["", "## Check broken (links, tools, network — not a site change)", ""]
    lines += broken or ["Nothing."]
    lines += ["", "## Full table", "",
              "| Site | Link | No cookies | Download test | Sign | Your cookies | Download test |",
              "|---|---|---|---|---|---|---|"]
    for site, now in new.items():
        if now.get("broken"):
            lines.append(f"| {names.get(site, site)} | none read | — | — | — | — | — |")
            continue
        plain, mine = now.get("no_cookies") or {}, now.get("your_cookies") or {}
        lines.append(f"| {names.get(site, site)} | {now['link_number']} | {_said(plain)} "
                     f"| {_download_said(plain.get('download'))} | {now.get('sign', '')} "
                     f"| {_said(mine)} | {_download_said(mine.get('download'))} |")
    if new_programs:
        lines += ["", "## Other programs (a real download through the app's own code)", "",
                  "| Site | Program | Version | Link | No cookies | Your cookies |",
                  "|---|---|---|---|---|---|"]
        for key, now in new_programs.items():
            site, _, tool = key.partition("|")
            first = f"| {names.get(site, site)} | {tool_name(tool)} | {now.get('version') or '?'} "
            if now.get("not_installed"):
                lines.append(first + "| — | not installed: not tested | — |")
            elif now.get("port_taken"):
                lines.append(first + "| — | not tested (port taken) | — |")
            elif now.get("fails"):
                lines.append(first + f"| none worked ({len(now['failed_links'])} tried) | FAILED | FAILED |")
            else:
                lines.append(first + f"| {now['link_number']} | {_program_said(now.get('no_cookies'))} "
                             f"| {_program_said(now.get('your_cookies'))} |")
    lines += ["", "Not tested: " + "; ".join(f"**{tool_name(t)}** — {why}" for t, why in NOT_TESTED.items())
              + ".", ""]
    return "\n".join(lines), len(changed), len(broken), len(fails), new_fails


def _write(path: Path, text: str) -> None:
    """Whole or not at all: a temporary file, then put in place."""
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    if sys.stdout is not None:      # None under pythonw.exe (the daily task: no black window)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Read each site's qualities, with and without cookies.")
    parser.add_argument("--site", action="append", help="only this site id (can repeat)")
    parser.add_argument("--due", action="store_true", help="the daily run: only the sites that are due")
    parser.add_argument("--no-download", action="store_true", help="read the qualities only, no download test")
    args = parser.parse_args()

    links = {k: v for k, v in json.loads(LINKS_FILE.read_text(encoding="utf-8")).items()
             if not k.startswith("_")}
    served = {p.id for p in PLATFORMS if any(o.tool_id == "yt-dlp" for o in p.tools)}
    testable = served | {site for site, _ in program_pairs({p.id: [] for p in PLATFORMS})}
    unknown = sorted(set(links) - testable)
    if unknown:
        print(f"Links for sites no tested program serves, skipped: {', '.join(unknown)}")
    sites = [s for s in links if s in served and (not args.site or s in args.site)]
    missing_links = sorted(testable - set(links))
    # The other programs are tested by downloading: none with --no-download.
    pairs = [] if args.no_download else [
        (site, tool) for site, tool in program_pairs(links) if not args.site or site in args.site]
    # runners.run notes its work folders in the APP's list, read by the app's
    # start-up sweep; a second program writing that file could lose the app's
    # lines. Ours are inside DOWNLOADS, swept below: a list of our own.
    runners.WORK_LIST = OUT_DIR / "work-folders.txt"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    # A copy of the whole cookie file left by a run cut off mid-read (log-off,
    # shut-down): deleted before anything else (hunt, 2026-11-15).
    if RUN_COPIES.is_dir():
        for leftover in RUN_COPIES.iterdir():
            try:
                leftover.unlink()
            except OSError as problem:
                problems.append(f"a cookie copy from an earlier run could not be deleted: {problem.strerror}")
    # The same for a download test cut off mid-file.
    if DOWNLOADS.is_dir():
        for leftover in DOWNLOADS.iterdir():
            if leftover.is_dir():
                _remove_test_folder(leftover)
    table: dict = {}
    if TABLE_FILE.is_file():
        table = json.loads(TABLE_FILE.read_text(encoding="utf-8"))
    old: dict = table.get("sites", {})
    old_programs: dict = table.get("programs", {})

    asked = subprocess.run([str(ytdlp.require_ytdlp()), "--version"], capture_output=True,
                           text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    version = (asked.stdout or "").strip()
    if asked.returncode != 0 or not _tag(version):
        # Never go on with an empty version: every release would look new
        # (hunt, 2026-11-15). The crash path says it in the log and a message.
        raise RuntimeError(f"yt-dlp --version answered code {asked.returncode}: "
                           f"{cookies.redact((asked.stderr or asked.stdout or '').strip())[:160]}")
    # The release notes already taken into account: at first, the yt-dlp the
    # table was made with.
    notes_seen = table.get("notes_seen") or table.get("ytdlp") or version
    reasons: dict[str, str] = {}
    if args.due and _ran_today():
        print("Already ran today.")
        return 0
    rows, rows_problem = failed_rows()
    if rows_problem:
        problems.append(rows_problem)
    failed_pairs = new_failures(table, rows)
    # Every pair a test can cover: a failed row of another pair is "seen" at
    # once (nothing would ever test it).
    testable = {f"{s}|yt-dlp" for s in sites} | {f"{s}|{t}" for s, t in program_pairs(links)}
    # ffprobe missing: every download test would say "could not read the
    # file" -- one problem said instead of twenty false failures (hunt).
    probe_tool = ytdlp.find_tool("ffmpeg")
    if not args.no_download and not (probe_tool and probe_tool.with_name("ffprobe.exe").is_file()):
        problems.append("ffprobe is missing (it comes with FFmpeg), so no download test ran")
        args.no_download = True
        pairs = []
    # By hand (no --due): every site read gets its full test, as before.
    full_tests: dict[str, str] = {s: "run by hand" for s in sites}
    if args.due:
        reasons, newest, found = due_sites(sites, table, notes_seen)
        problems += found
        # With --site, the other sites a release named were not read: their
        # release stays unspent for the next full run (hunt round 2).
        if not args.site:
            notes_seen = newest
        sites = [s for s in sites if s in reasons]
        full_tests = full_test_reasons(sites, table, reasons, failed_pairs)
        program_reasons = due_programs(pairs, table, failed_pairs)
        pairs = [(s, t) for s, t in pairs if f"{s}|{t}" in program_reasons]
        reasons.update(program_reasons)
        if not sites and not pairs:
            # A test folder Windows refused to delete at the start is said
            # on a quiet day too (hunt, 2026-11-17).
            problems += [f"a download test folder was left: {left}" for left in _LEFT_BEHIND]
            log_run("nothing due" + "".join(f" · PROBLEM: {p}" for p in problems))
            table["notes_seen"] = notes_seen
            table["failed_jobs_seen"] = seen_after(table, rows, set(), testable)
            _write(TABLE_FILE, json.dumps({**table, "sites": old}, ensure_ascii=False, indent=1))
            if problems:
                tell("Quality check: a problem", problems[0][:200], None)
            print("Nothing due." + "".join(f"\n{p}" for p in problems))
            return 0
    cookies_on = _cookies_on()
    if cookies_on is None:
        problems.append("the app's settings file could not be read, so no read used your cookies")
    new: dict = {}
    for site in sites:
        started = time.monotonic()
        new[site] = check_site(site, links[site], cookies_on, not args.no_download,
                               old.get(site), full_tests.get(site, ""))
        now = new[site]
        print(f"{site:12} {time.monotonic() - started:5.1f}s  "
              f"{'BROKEN' if now.get('broken') else _said(now.get('no_cookies'))}"
              f"{'' if now.get('broken') else '  |  ' + _said(now.get('your_cookies'))}", flush=True)
        for state in ("no_cookies", "your_cookies"):
            if (now.get(state) or {}).get("download"):
                print(f"{'':12}   download ({state}): {_download_said(now[state]['download'])}", flush=True)
    new_programs: dict = {}
    for site, tool in pairs:
        started = time.monotonic()
        key = f"{site}|{tool}"
        # Checked just before each run: our list, never the app's (a module
        # reload once put a test's paths back to the real ones, 2026-11-15).
        if runners.WORK_LIST.parent != OUT_DIR:
            raise RuntimeError(f"runners.WORK_LIST points at {runners.WORK_LIST}, not inside {OUT_DIR}")
        new_programs[key] = now = check_program(site, tool, links[site], cookies_on)
        said = ("not installed" if now.get("not_installed") else "BROKEN (port taken)" if now.get("port_taken")
                else "FAILED on every link" if now.get("fails")
                else f"{_program_said(now.get('no_cookies'))}  |  {_program_said(now.get('your_cookies'))}")
        print(f"{key:30} {time.monotonic() - started:5.1f}s  {said}", flush=True)

    problems += [f"a download test folder was left: {left}" for left in _LEFT_BEHIND]
    switch = "unknown (settings unreadable)" if cookies_on is None else ("on" if cookies_on else "off")
    header = [f"- yt-dlp {version} · “Use my log-ins” {switch} · {len(sites)} sites read"
              f" · {len(pairs)} other program tests",
              "- Download test: off (--no-download)" if args.no_download else
              f"- Download test: on — the file \"Best\" picks, checked with ffprobe, then deleted; "
              f"not over {MAX_MB} MB"]
    if missing_links:
        header.append(f"- No test link yet for: {', '.join(missing_links)}")
    if reasons:
        header.append("- Why these: " + "; ".join(f"{s}: {r}" for s, r in reasons.items()))
    tested = {s: n.get("full_test_why") for s, n in new.items() if n.get("full_test_why")}
    if not args.no_download:
        header.append("- yt-dlp full download test today: " + ("; ".join(f"{s}: {w}" for s, w in tested.items())
                      or "none (read only — the last test's result is shown with its date)"))
    header += [f"- ⚠️ {p}" for p in problems]
    text, changed, broken, fails, new_fails = report(new, {s: old[s] for s in new if s in old}, header,
                                          new_programs, old_programs)
    report_file = OUT_DIR / f"report-{time.strftime('%Y-%m-%d-%H%M%S')}.md"
    _write(report_file, text)
    # The pairs really tested by a download in this run: their failed rows
    # are now seen; the others stay new for the next run.
    tested_now = ({f"{s}|yt-dlp" for s, n in new.items() if n.get("full_test_why")}
                  | {k for k, n in new_programs.items() if not n.get("not_installed") and not n.get("port_taken")})
    merged = dict(old)
    for site, now in new.items():
        before = old.get(site)
        if now.get("broken") and before and not before.get("broken"):
            # A failed read never replaces the last good one: that baseline
            # is what the next read is compared with, and the site stays due
            # until a read works (hunt, 2026-11-15).
            merged[site] = {**before, "retry": True,
                            "last_failure": {"checked": now["checked"], "failed_links": now["failed_links"]}}
        else:
            merged[site] = now
    _write(TABLE_FILE, json.dumps({"ytdlp": version, "notes_seen": notes_seen, "sites": merged,
                                   "programs": {**old_programs, **new_programs},
                                   "failed_jobs_seen": seen_after(table, rows, tested_now, testable)},
                                  ensure_ascii=False, indent=1))
    log_run(f"{len(sites)} read ({', '.join(sites)}) · {len(pairs)} program tests"
            + (f" ({', '.join(f'{s}|{t}' for s, t in pairs)})" if pairs else "")
            + f" · {changed} changed · {broken} broken"
            + f" · {fails} not downloading"
            + "".join(f" · PROBLEM: {p}" for p in problems) + f" · {report_file.name}")
    print(f"\nReport: {report_file}")
    if changed or broken or problems or new_fails:
        parts = [f"{new_fails} new download failure{'s' if new_fails != 1 else ''}"] if new_fails else []
        parts += [f"{changed} change{'s' if changed != 1 else ''} to review"] if changed else []
        parts += [f"{broken} broken check{'s' if broken != 1 else ''}"] if broken else []
        parts += ["a problem"] if problems else []
        tell("Quality check", ", ".join(parts) + ". Click to open the report.", report_file)
    return 0


def _crashed() -> int:
    """The check itself broke: said in the log and in a Windows message, never silent."""
    details = cookies.redact(traceback.format_exc())
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        crash_file = OUT_DIR / f"crash-{time.strftime('%Y-%m-%d-%H%M%S')}.txt"
        crash_file.write_text(details, encoding="utf-8")
        log_run(f"CRASHED: {details.strip().splitlines()[-1][:200]} · {crash_file.name}")
    except OSError:
        crash_file = None
    print(details)
    tell("Quality check crashed", details.strip().splitlines()[-1][:200], crash_file)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.exit(_crashed())
