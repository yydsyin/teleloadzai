"""The signs every user's app shows about a site and a program.

Four kinds, each from the quality check (dev/quality_check.py) and each line
reviewed before it is published (the user's plan, 2026-11-18):

  before_download -- what a program needs before Download, said on the card
                     ("login", "visit", "asked"; login.need)
  sites_page      -- what a site needs per program, with its date, on the
                     Sites page ("visit", "none", "account"; needs.all_needs)
  quality         -- what a log-in does not unlock, beside Quality
  download_fails  -- a program that fails on a site (a warning sign, never a
                     block), or a yt-dlp file to avoid at one height

The list ships with the app (teleloadzai/signs.json) and every user's app
reads the newer one from GitHub with the update check, every CACHE_HOURS:
a sign reaches users without a new release. The file is DATA, checked line
by line before use: a known site, a known program, known fields, short text,
a codec from a short list (it becomes a yt-dlp argument). A line that fails
is left out and said in the Console; a file that fails is not used, and the
last good one stays. Nothing about the user is sent: a plain GET of a public
file, with no cookie and no token.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .paths import DATA_DIR

FORMAT = 1                                  # the file's shape; a newer one needs a newer app
BUNDLED = Path(__file__).resolve().parent / "signs.json"
CACHE = DATA_DIR / "signs.json"
# raw.githubusercontent.com is a plain file, not the API: no X-RateLimit
# headers, where api.github.com answers "X-RateLimit-Limit: 60" (both seen
# 2026-11-18), so it does not spend decision 18's requests.
URL = "https://raw.githubusercontent.com/yydsyin/teleloadzai/main/teleloadzai/signs.json"
CACHE_HOURS = 6                             # as the update check (tools.CACHE_HOURS)
RETRY_AFTER = 3600                          # a failed fetch waits an hour
MAX_BYTES = 256 * 1024
MAX_TEXT = 300

# A codec yt-dlp sorts by (`-S vcodec:<name>`): the value goes on its
# command line, so only these names, never the file's own text.
CODECS = ("h264", "h265", "vp9", "av01")
NEEDS_BEFORE = ("login", "visit", "asked")
NEEDS_SITES = ("visit", "none", "account")
SECTIONS = ("before_download", "sites_page", "quality", "download_fails")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

_lock = threading.Lock()                    # the cache file's reads and its replace
_state = {"signs": None, "said": set(), "tried": 0.0, "running": False, "generation": 0,
          "problem": ""}         # why the last fetch from GitHub failed, "" when it worked
_NOT_UPDATED = "the sign list was not updated"


def _say(text: str) -> None:
    """A problem with the list, said once per text in the Console (decision 34)."""
    if text in _state["said"]:
        return
    _state["said"].add(text)
    from . import console
    console.add("app", f"Teleloadzai: {text}", "err")


def _text(value, limit: int = MAX_TEXT) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit


def _line(section: str, entry) -> str:
    """"" when the line is good, else why not."""
    if not isinstance(entry, dict):
        return "not a set of fields"
    why = entry.get("why")
    if why is not None and not _text(why, 2000):
        return "its evidence is not a short text"
    if section == "before_download":
        return "" if entry.get("need") in NEEDS_BEFORE else "an unknown need"
    if not (isinstance(entry.get("seen"), str) and _DATE.fullmatch(entry["seen"])):
        return "no date"
    if section == "sites_page":
        return "" if entry.get("need") in NEEDS_SITES else "an unknown need"
    if section == "quality":
        return "" if _text(entry.get("text")) else "no short text"
    # download_fails: a warning, or a codec to avoid at one height
    for field, limit in (("next", MAX_TEXT), ("who", 60), ("version", 80)):
        if field in entry and not _text(entry[field], limit):
            return f"a bad '{field}'"
    if entry.get("fails") is True:
        return ""
    if entry.get("prefer") in CODECS and entry.get("avoid") in CODECS and entry["avoid"] != entry["prefer"]:
        height = entry.get("height")
        if isinstance(height, int) and not isinstance(height, bool) and 144 <= height <= 4320:
            return ""
        return "a bad height"
    return "neither a warning nor a codec from the list"


def clean(data) -> tuple[dict | None, list[str]]:
    """The file's good lines, and why the others were left out. None when the
    file itself cannot be used (its shape, its format, its date)."""
    if not isinstance(data, dict):
        return None, ["not a list of signs"]
    if data.get("format") != FORMAT:
        newer = isinstance(data.get("format"), int) and data["format"] > FORMAT
        return None, ["it needs a newer Teleloadzai" if newer else "an unknown format"]
    if not (isinstance(data.get("updated"), str) and _STAMP.fullmatch(data["updated"])):
        return None, ["no date of update"]
    from .platforms import PLATFORMS
    from .tools import SPECS
    sites, programs = {p.id for p in PLATFORMS}, {s.id for s in SPECS}
    out, problems = {"updated": data["updated"]}, []
    # A part missing is a broken file, not "no lines": a list that lost its
    # "download_fails" would take every warning from every user (hunt 2026-11-18).
    missing = [s for s in SECTIONS if s not in data]
    if missing:
        return None, [f"the part '{missing[0]}' is missing"]
    for section in SECTIONS:
        lines = data[section]
        if not isinstance(lines, dict):
            problems.append(f"{section}: not a list")
            lines = {}
        kept = {}
        for key, entry in lines.items():
            site, bar, program = str(key).partition("|")
            why = ("not 'site|program'" if not bar else
                   "an unknown site" if site not in sites else
                   "an unknown program" if program not in programs else _line(section, entry))
            if why:
                problems.append(f"{section} · {str(key)[:60]}: {why}")
            else:
                kept[key] = {k: v for k, v in entry.items() if k != "why"}
        out[section] = kept
    return out, problems


def _load(path: Path, where: str) -> dict | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        # No fetched copy yet is normal; no shipped one is a broken install,
        # and every sign would vanish without a word (hunt round 2).
        if path == BUNDLED:
            _say(f"the sign list {where} is missing: no sign about sites or programs is shown.")
        return None
    except OSError as problem:
        _say(f"the sign list {where} could not be read ({problem.strerror or problem}).")
        return None
    if len(raw) > MAX_BYTES:
        _say(f"the sign list {where} is too big to be one ({len(raw)} bytes): not used.")
        return None
    signs, problems = read_text(raw)
    if signs is None:
        _say(f"the sign list {where} is not used — {problems[0]}.")
        return None
    for problem in problems:
        _say(f"a line of the sign list {where} was left out — {problem}.")
    return signs


def read_text(raw: bytes) -> tuple[dict | None, list[str]]:
    """clean() on a file's bytes; a file that is not JSON, or too deep to
    read (RecursionError, under MAX_BYTES), is "damaged". "utf-8-sig": a file
    saved by PowerShell 5.1 starts with a BOM, which json refuses (round 2)."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, ["it is damaged"]
    return clean(data)


def current() -> dict:
    """The list in use: the newer of the one shipped with the app and the one
    last fetched (an app update can ship a newer list than an old fetch)."""
    signs = _state["signs"]
    if signs is None:
        # A fetch that lands during this read must not be undone by it: the
        # list read here is kept only if no fetch landed meanwhile (hunt).
        generation = _state["generation"]
        with _lock:
            fetched = _load(CACHE, "fetched from GitHub")
        shipped = _load(BUNDLED, "shipped with the app")
        # A fetched list of the same date wins: it is the same, or newer.
        if fetched and (not shipped or fetched["updated"] >= shipped["updated"]):
            signs = fetched
        else:
            signs = shipped or {}
        if _state["generation"] == generation:
            _state["signs"] = signs
    return signs


def shipped() -> tuple[dict, list[str]]:
    """The list in this folder -- the one a review changes -- and its
    problems. The quality check compares its results with it, never with a
    fetched copy, and says the problems in its report (the Console of its
    own process is seen by nobody)."""
    return _file(BUNDLED)


def fetched_problems() -> list[str]:
    """What is wrong with the copy fetched from GitHub ([] when none is kept):
    the quality check's own tests read it through current(), and says these
    in its report (round 2)."""
    return _file(CACHE)[1] if CACHE.exists() else []


def _file(path: Path) -> tuple[dict, list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as problem:
        return {}, [f"it could not be read ({problem.strerror or problem})"]
    signs, problems = read_text(raw) if len(raw) <= MAX_BYTES else (None, ["it is too big"])
    return signs or {}, problems


def get(section: str, site: str, program: str) -> dict | None:
    entry = current().get(section, {}).get(f"{site}|{program}")
    return dict(entry) if entry else None


def section(name: str) -> dict[str, dict]:
    return {k: dict(v) for k, v in current().get(name, {}).items()}


# ---------------------------------------------------------------- what changed

# The user's model A, 2026-11-20: a red "!" on Sites and a "What changed"
# box until OK. Only what the user sees counts -- a warning (a program that
# fails) or a need before Download, added or removed; a new date, a codec
# to avoid (the app just takes the other file) or new evidence says nothing.
SEEN = DATA_DIR / "signs-seen.json"
_seen_lock = threading.Lock()               # signs-seen.json's reads and its replace


def _visible(signs: dict, shown_only: bool = False) -> dict[str, dict[str, str]]:
    """`shown_only` (the "seen" snapshot): only the warnings this user's
    buttons really showed (`needs.applies`, the button's own rule). All of
    them were stored, so removing one tied to another version said "Works
    again" for a warning never shown here (round 31 of the hunt)."""
    fails = {k: v for k, v in signs.get("download_fails", {}).items() if v.get("fails")}
    if shown_only:
        from .needs import applies
        fails = {k: v for k, v in fails.items() if applies(v, k.partition("|")[2]) is not None}
    return {"warning": {k: v.get("next", "") for k, v in fails.items()},
            "need": {k: v["need"] for k, v in signs.get("before_download", {}).items()}}


def _save_seen(signs: dict) -> str:
    """"" when the snapshot of what the user saw was written, else why not."""
    temp = SEEN.with_suffix(".tmp")
    # Computed BEFORE the lock: `needs.applies` may run a program to read its
    # version (up to 15 s), and the Sites page's own reads waited behind it
    # (round 32; pass 2: never a lock around a program).
    shown = _visible(signs, shown_only=True)
    try:
        with _seen_lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps({"updated": signs.get("updated", ""), **shown},
                                       ensure_ascii=False), encoding="utf-8")
            os.replace(temp, SEEN)
        return ""
    except OSError as problem:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return problem.strerror or str(problem)


_NEED_SAID = {"login": "Now needs your log-in.", "visit": "Now needs one visit of the site, no log-in.",
              "asked": "Now asks for an account."}


def _day(iso: str) -> str:
    """"2026-11-16" -> "Nov 16", as the Sites page writes its dates."""
    try:
        return f"{_MONTHS[int(iso[5:7]) - 1]} {int(iso[8:10])}"
    except (ValueError, IndexError):
        return iso


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def changes() -> dict:
    """{"changes": [{site, program, kind, added, text}], "date": the list's date}.
    The first time (no snapshot yet) the list in use is taken as seen: a new
    user must not get every existing sign as "new"."""
    signs = current()
    if not signs:
        return {"changes": [], "date": ""}
    try:
        with _seen_lock:
            seen = json.loads(SEEN.read_text(encoding="utf-8-sig"))
        if not (isinstance(seen, dict) and all(isinstance(seen.get(k), dict) for k in ("warning", "need"))):
            raise ValueError("not a snapshot")
    except FileNotFoundError:
        why = _save_seen(signs)
        if why:
            _say(f"what changed in the sign list cannot be followed: {SEEN.name} could not be written ({why}).")
        return {"changes": [], "date": signs["updated"]}
    except (OSError, ValueError, RecursionError) as problem:
        # Damaged: said, and started again from the list in use (nothing
        # here is the user's work -- it only marks what was seen).
        _say(f"{SEEN.name} could not be read ({getattr(problem, 'strerror', None) or problem}): "
             "the signs in use are taken as seen.")
        _save_seen(signs)
        return {"changes": [], "date": signs["updated"]}
    now, out = _visible(signs), []
    for key in sorted(set(now["warning"]) | set(seen["warning"])):
        if key in now["warning"] and key not in seen["warning"]:
            # The button's own first sentence, then its next step: "Its
            # authors fixed it…" alone did not say what failed (seen 2026-11-20).
            entry = signs["download_fails"][key]
            # Announced only when the button shows it: a warning tied to a
            # version ("XHS-Downloader V2.8 Stable") said "Now warned" to a
            # user with another version, or none, and no sign on the button
            # (silent-failure hunt, 2026-11-22). The button's own rule.
            from .needs import applies
            if applies(entry, key.partition("|")[2]) is None:
                continue
            out.append((key, "warning", True, " ".join(filter(None, [
                f"Now warned: it failed in our last check ({_day(entry['seen'])}).", entry.get("next", "")]))))
        elif key in seen["warning"] and key not in now["warning"]:
            out.append((key, "warning", False, "Works again: its warning is removed."))
    for key in sorted(set(now["need"]) | set(seen["need"])):
        if now["need"].get(key) != seen["need"].get(key):
            out.append((key, "need", key in now["need"],
                        _NEED_SAID.get(now["need"].get(key), "No longer asks for a log-in.")))
    from .platforms import PLATFORMS, tool_name
    names = {p.id: p.name for p in PLATFORMS}
    listed = []
    # A row's "new" tag shows on the first look only (the user, 2026-11-20);
    # the box and the "!" stay until Got it.
    tags_seen = set(x for x in seen.get("tags_seen", []) if isinstance(x, str))         if isinstance(seen.get("tags_seen"), list) else set()
    for key, kind, added, text in out:
        site, _, program = key.partition("|")
        change_id = f"{kind}|{key}"
        listed.append({"id": change_id, "site": site, "site_name": names.get(site, site), "program": program,
                       "program_name": tool_name(program), "kind": kind, "added": added, "text": text,
                       "tag": change_id not in tags_seen})
    return {"changes": listed, "date": signs["updated"]}


def mark_tags_seen(ids: list) -> str:
    """The Sites page was looked at: these changes' "new" tags are not shown
    again. "" or why not. A Got it later rewrites the file without them."""
    ids = [x for x in ids if isinstance(x, str) and len(x) <= 120][:200]
    temp = SEEN.with_suffix(".tmp")
    try:
        with _seen_lock:
            seen = json.loads(SEEN.read_text(encoding="utf-8-sig"))
            if not isinstance(seen, dict):
                return "the record is not readable"
            old = seen.get("tags_seen") if isinstance(seen.get("tags_seen"), list) else []
            seen["tags_seen"] = sorted(set(old) | set(ids))
            temp.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, SEEN)
        return ""
    except (OSError, ValueError, RecursionError) as problem:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return getattr(problem, "strerror", None) or str(problem)


def mark_seen(shown: str | None = None) -> str:
    """OK pressed: the list in use is now what the user saw. "" or why not.
    `shown`: the date of the list the box showed. A newer list taken since
    is not marked seen -- "Got it" hid a warning nobody had seen (round 17);
    "changed" then, and the page shows the new list."""
    signs = current()
    if not signs:       # an empty snapshot would show every sign as "new" later
        return "the sign list is not loaded"
    if shown is not None and shown != signs.get("updated", ""):
        return "changed"
    return _save_seen(signs)


# ---------------------------------------------------------------- the fetch

def _due() -> bool:
    if time.time() - _state["tried"] < RETRY_AFTER:
        return False
    try:
        age = time.time() - CACHE.stat().st_mtime
        # A file dated in the future (the clock was ahead) is due, not fresh (round 23).
        return age > CACHE_HOURS * 3600 or age < 0
    except OSError:
        return True


def refresh() -> str:
    """Fetch the list from GitHub now; "" when it was taken, else why not."""
    from .tools import _USER_AGENT
    _state["tried"] = time.time()
    try:
        request = urllib.request.Request(URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            # Only from GitHub's file host, whatever a redirect says.
            if not response.geturl().startswith("https://raw.githubusercontent.com/"):
                return "the answer came from another address"
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as problem:
        # 404: the file is not on GitHub (not pushed yet, or the repository moved).
        return f"GitHub answered {problem.code}"
    except Exception as problem:
        return f"GitHub could not be reached ({type(problem).__name__})"
    if len(raw) > MAX_BYTES:
        return "the answer is too big to be a sign list"
    signs, problems = read_text(raw)
    if signs is None:
        return f"the list was not used — {problems[0]}"
    with _lock:
        kept = _load(CACHE, "fetched from GitHub")
    if kept and kept["updated"] > signs["updated"]:
        # An old copy from GitHub's cache (max-age=300) must not bring a
        # removed sign back over a newer one already kept.
        return "GitHub gave an older list than the one kept"
    temp = CACHE.with_suffix(".tmp")
    try:
        with _lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(raw)
            os.replace(temp, CACHE)
    except OSError as problem:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return f"the list could not be saved ({problem.strerror or problem})"
    for problem in problems:
        _say(f"a line of the sign list fetched from GitHub was left out — {problem}.")
    _state["generation"] += 1
    _state["signs"] = None                  # read again, the newer of the two
    # A failure after this success is said again (it was said once already).
    _state["said"] = {t for t in _state["said"] if _NOT_UPDATED not in t}
    return ""


def refresh_soon() -> None:
    """Fetch in the background when due (never blocking, decision 8); a failure
    is said in the Console, and the list in use stays."""
    with _lock:
        if _state["running"] or not _due():
            return
        _state["running"] = True

    def work():
        try:
            why = refresh()
        except Exception as problem:        # never a thread dying in silence
            why = f"an error in Teleloadzai ({type(problem).__name__})"
        finally:
            _state["running"] = False
        # Kept for the Sites page too: only the Console said it, and the page
        # showed a week-old list with no word (round 17 of the hunt).
        _state["problem"] = why
        if why:
            _say(f"{_NOT_UPDATED}: {why}. The last one stays.")

    threading.Thread(target=work, daemon=True).start()
