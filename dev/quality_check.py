"""The quality check -- run on OUR side only, never on a user's computer.

For each site yt-dlp serves, it reads one public link's list of qualities
(the app's own title-read rule, downloads nothing), once without cookies and
once with the developer's own log-in, and writes:

  data/quality-check/table.json            the latest results (read by the next run)
  data/quality-check/report-<date>.md      what changed, what broke, the full table

Both are under data/, which git ignores: the report says which sites the
developer is logged in on, and the repository is public. Nothing here
changes the app; a change reaches the app's table only after a review.

Run from the project folder:
  python dev/quality_check.py                every site (the first table, or by hand)
  python dev/quality_check.py --site reddit  one site (can repeat)
  python dev/quality_check.py --due          the daily run: only the sites that are due

A site is due when (1) it was never read or was read more than FLOOR_DAYS ago,
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
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teleloadzai import cookies, login, needs, ytdlp  # noqa: E402
from teleloadzai.paths import DATA_DIR  # noqa: E402
from teleloadzai.platforms import PLATFORMS  # noqa: E402

LINKS_FILE = Path(__file__).with_name("quality_links.json")
OUT_DIR = DATA_DIR / "quality-check"
TABLE_FILE = OUT_DIR / "table.json"
RUN_COPIES = OUT_DIR / "run"
SETTINGS_FILE = DATA_DIR / "settings.json"
RUNS_LOG = OUT_DIR / "runs.log"
TIMEOUT = 90.0
FLOOR_DAYS = 90         # no line older than 3 months (the user's plan, 2026-11-15)

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


def _cookies_on() -> bool:
    """The app's "Use my log-ins" switch, read from its settings file."""
    for _ in range(5):          # the app may be replacing the file this instant
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("cookies_enabled") is True
        except FileNotFoundError:
            return False
        except (OSError, ValueError):
            time.sleep(0.2)
    return False


def _error_of(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR:")]
    chosen = errors[-1] if errors else (lines[-1] if lines else "no message")
    return cookies.redact(chosen)[:240]


def read(url: str, cookie_file: Path | None) -> dict:
    """One title read, as the app does it, plus yt-dlp's own "missing" line."""
    command = [
        str(ytdlp.require_ytdlp()),
        "--dump-single-json", "--no-playlist",
        "--encoding", "utf-8", "--no-colors",
        "--no-quiet",           # the app's read is quiet; the "missing" line needs this
        "-f", ytdlp._MP4_BEST,
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
    return {"ok": True, "best": best, "heights": heights,
            "kbps": kbps[-1:] if not heights else [], "missing": missing}


def with_my_cookies(url: str) -> dict:
    """The same read with a throwaway copy of our cookie file."""
    RUN_COPIES.mkdir(parents=True, exist_ok=True)
    copy = RUN_COPIES / f"{uuid.uuid4().hex}.txt"
    try:
        shutil.copyfile(cookies.COOKIE_FILE, copy)
        return read(url, copy)
    except OSError as problem:
        return {"ok": False, "error": f"the cookie copy failed: {problem.strerror}"}
    finally:
        copy.unlink(missing_ok=True)


def check_site(site: str, links: list[str], cookies_on: bool) -> dict:
    result: dict = {"checked": time.strftime("%Y-%m-%d %H:%M"), "failed_links": []}
    sign = login.site_state(site)
    result["sign"] = sign
    for number, url in enumerate(links, 1):
        plain = read(url, None)
        if plain["ok"] or plain.get("needs_login"):
            result.update(link=url, link_number=number, no_cookies=plain)
            break
        result["failed_links"].append({"number": number, "error": plain["error"]})
    else:
        result["broken"] = True
        return result

    if not cookies_on:
        result["your_cookies"] = {"skipped": "“Use my log-ins” is off in the app"}
    elif not cookies.COOKIE_FILE.is_file():
        result["your_cookies"] = {"skipped": "no cookie file"}
    elif sign == "none":
        result["your_cookies"] = {"skipped": "no cookies for this site"}
    else:
        result["your_cookies"] = with_my_cookies(result["link"])
    return result


# ---------------------------------------------------------------- what is due

def _tag(text: str) -> tuple[int, ...]:
    """"2026.11.14.232655" -> numbers, so tags compare as dates."""
    return tuple(int(part) for part in re.findall(r"\d+", text or ""))


def releases_since(seen: str) -> list[tuple[str, set[str]]]:
    """yt-dlp releases newer than `seen`, each with the sites its notes name."""
    request = urllib.request.Request(NOTES_URL, headers={
        "User-Agent": "quality-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        rows = json.load(answer)
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
    return sorted(found, key=lambda pair: _tag(pair[0]))


def due_sites(sites: list[str], table: dict, notes_seen: str) -> tuple[dict[str, str], str, list[str]]:
    """{site: why it is due}, the newest release read, and problems to say."""
    due: dict[str, str] = {}
    problems: list[str] = []
    old = table.get("sites", {})
    for site in sites:
        checked = (old.get(site) or {}).get("checked")
        if not checked:
            due[site] = "never read"
            continue
        days = (time.time() - time.mktime(time.strptime(checked, "%Y-%m-%d %H:%M"))) / 86400
        if days > FLOOR_DAYS:
            due[site] = f"last read {int(days)} days ago"

    newest = notes_seen
    try:
        for tag, named in releases_since(notes_seen):
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
        print(f"The Windows message could not be shown: {problem}")


def _ran_today() -> bool:
    """A finished run is already in today's log. The task starts at each log-on
    (the PC is off at any fixed hour, 2026-11-15): once a day is enough. A crash
    does not count -- the next log-on tries again."""
    try:
        lines = RUNS_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    today = time.strftime("%Y-%m-%d")
    return any(line.startswith(today) and "CRASHED" not in line for line in lines)


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


def _key(state: dict | None) -> tuple:
    if state and state.get("needs_login"):
        return ("asks for a log-in",)
    if not state or not state.get("ok"):
        return ("not ok", (state or {}).get("skipped", ""))
    return (state.get("best"), tuple(state.get("heights") or ()), tuple(state.get("kbps") or ()),
            tuple(g["names"] for g in state.get("missing") or ()))


def report(new: dict, old: dict, header: list[str]) -> tuple[str, int, int]:
    """The report's text, and how many changes and broken checks it holds."""
    names = {p.id: p.name for p in PLATFORMS}
    changed, broken = [], []
    for site, now in new.items():
        before = old.get(site)
        name = names.get(site, site)
        if now.get("broken"):
            errors = "; ".join(f"link {f['number']}: {f['error']}" for f in now["failed_links"])
            broken.append(f"- **{name}**: no link could be read — the site, the links or the network. {errors}")
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

    lines = [f"# Quality check — {time.strftime('%Y-%m-%d %H:%M')}", "", *header, ""]
    if new and all(now.get("broken") for now in new.values()):
        lines += ["🚨 **Every site failed.** Suspect the network or this script first, not the sites.", ""]
    lines += ["## Changed since the last check", ""]
    lines += changed or ["Nothing changed." if old else "First run: nothing to compare with."]
    lines += ["", "## Check broken (links, tools, network — not a site change)", ""]
    lines += broken or ["Nothing."]
    lines += ["", "## Full table", "",
              "| Site | Link | No cookies | Sign | Your cookies |", "|---|---|---|---|---|"]
    for site, now in new.items():
        if now.get("broken"):
            lines.append(f"| {names.get(site, site)} | none read | — | — | — |")
            continue
        lines.append(f"| {names.get(site, site)} | {now['link_number']} | {_said(now.get('no_cookies'))} "
                     f"| {now.get('sign', '')} | {_said(now.get('your_cookies'))} |")
    lines += ["", "Not checked: **yutto** (Bilibili) — it has no way to list its qualities "
              "without downloading. Streamlink — its qualities exist only during a live stream.", ""]
    return "\n".join(lines), len(changed), len(broken)


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
    args = parser.parse_args()

    links = {k: v for k, v in json.loads(LINKS_FILE.read_text(encoding="utf-8")).items()
             if not k.startswith("_")}
    served = {p.id for p in PLATFORMS if any(o.tool_id == "yt-dlp" for o in p.tools)}
    unknown = sorted(set(links) - served)
    if unknown:
        print(f"Links for sites yt-dlp does not serve, skipped: {', '.join(unknown)}")
    sites = [s for s in links if s in served and (not args.site or s in args.site)]
    missing_links = sorted(served - set(links))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table: dict = {}
    if TABLE_FILE.is_file():
        table = json.loads(TABLE_FILE.read_text(encoding="utf-8"))
    old: dict = table.get("sites", {})

    version = subprocess.run([str(ytdlp.require_ytdlp()), "--version"], capture_output=True,
                             text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    # The release notes already taken into account: at first, the yt-dlp the
    # table was made with.
    notes_seen = table.get("notes_seen") or table.get("ytdlp") or version
    problems: list[str] = []
    reasons: dict[str, str] = {}
    if args.due and _ran_today():
        print("Already ran today.")
        return 0
    if args.due:
        reasons, notes_seen, problems = due_sites(sites, table, notes_seen)
        sites = [s for s in sites if s in reasons]
        if not sites:
            log_run("nothing due" + "".join(f" · {p}" for p in problems))
            table["notes_seen"] = notes_seen
            _write(TABLE_FILE, json.dumps({**table, "sites": old}, ensure_ascii=False, indent=1))
            if problems:
                tell("Quality check: a problem", problems[0][:200], None)
            print("Nothing due." + "".join(f"\n{p}" for p in problems))
            return 0
    cookies_on = _cookies_on()
    new: dict = {}
    for site in sites:
        started = time.monotonic()
        new[site] = check_site(site, links[site], cookies_on)
        now = new[site]
        print(f"{site:12} {time.monotonic() - started:5.1f}s  "
              f"{'BROKEN' if now.get('broken') else _said(now.get('no_cookies'))}"
              f"{'' if now.get('broken') else '  |  ' + _said(now.get('your_cookies'))}", flush=True)

    header = [f"- yt-dlp {version} · “Use my log-ins” {'on' if cookies_on else 'off'} · {len(sites)} sites read"]
    if missing_links:
        header.append(f"- No test link yet for: {', '.join(missing_links)}")
    if reasons:
        header.append("- Why these sites: " + "; ".join(f"{s}: {r}" for s, r in reasons.items()))
    header += [f"- ⚠️ {p}" for p in problems]
    text, changed, broken = report(new, {s: old[s] for s in new if s in old}, header)
    report_file = OUT_DIR / f"report-{time.strftime('%Y-%m-%d-%H%M%S')}.md"
    _write(report_file, text)
    merged = {**old, **new}
    _write(TABLE_FILE, json.dumps({"ytdlp": version, "notes_seen": notes_seen, "sites": merged},
                                  ensure_ascii=False, indent=1))
    log_run(f"{len(sites)} read ({', '.join(sites)}) · {changed} changed · {broken} broken"
            + "".join(f" · {p}" for p in problems) + f" · {report_file.name}")
    print(f"\nReport: {report_file}")
    if changed or broken or problems:
        parts = [f"{changed} change{'s' if changed != 1 else ''} to review"] if changed else []
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
