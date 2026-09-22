# CLAUDE.md — Teleloadzai

> Version 0.2 — started 2026-09-20.
> This file grows with the project. Only decisions the user has approved go in here.

---

## 1. What Teleloadzai is

One desktop interface that groups the best video/audio download tools behind a single UI.

- **yt-dlp is the engine** for most platforms.
- **Specialist tools are used only where yt-dlp is weak** (no watermark, 4K, login-heavy sites, live streams).
- The user pastes a link; Teleloadzai decides which tool to use.

**Code map** — `python -m teleloadzai` starts it (or double-click `Teleloadzai.bat`).

| File | Job |
|---|---|
| `config.py` | the name, and nothing else |
| `paths.py` | where `bin/` and `data/` live |
| `platforms.py` + `detect.py` | the brain: link -> platform -> tool |
| `ytdlp.py` | runs yt-dlp |
| `runners.py` | runs every other tool: one engine, one recipe each. Also says which tools are **not usable yet**, so the window never offers one it cannot drive. |
| `tools.py` | the Tool Manager: install, update, versions |
| `jobs.py` | the download queue |
| `dialogs.py` | the Windows "Save as" and folder windows |
| `server.py` | the local server |
| `__main__.py` | opens the real app window (pywebview) |
| `web/index.html` | the whole interface, one file |

## 2. How to work with the user

- The user is a French speaker writing in English. **Use simple, short sentences.** Avoid rare words and idioms.
- Tables and short lists are better than long paragraphs.
- If the user switches to French, follow in French.
- This file is built **gradually**. Do not add rules the user has not approved.

### 2.1 Speaking

- 🚨 **ONE PATH, NOT A MENU.** When he asks "what is the best solution", he wants an answer, not a comparison table. Decide, announce **one** way to go, stick to it. Other possibilities get one line, or nothing. *(This is the mistake that lost him most often; the same scar exists in the SDH project.)*
- **Explain a word the FIRST time it is used**, in half a sentence. Without that, the next sentence is lost too.
- **Examples taken from THIS project**, never generic ones. Not "imagine an app", but "your Xiaohongshu link, and XHS-Downloader which is not installed".
- **Length: aim for about 30 lines**, 100 for a real report. Longer almost always means options were listed instead of a decision being made. A style rule must be **checkable**: "be clear" means nothing, "30 lines" and "one way to go" can be controlled.
- 🎬 **DESCRIBE A DEFECT BY WHAT IS SEEN, BEFORE NAMING ANY CODE.** The order is: **the scene**, then the cause, then the code.
  - ⚠️ The control, and it is checkable: the first sentence describing a defect contains **no function name, no variable name, no line number**. If it does, it is the wrong first sentence.
  - A number beats an adjective: not "the file was skipped", but "size before 533931, size after 533931, and we displayed *done*".
  - The lines and file names still matter — they go **at the end**, under "where to look", not inside the explanation.
- **When he says he does not understand: do not re-explain louder.** Start again from zero: what we are trying to get (one sentence), why (one sentence), the single next action. Never "as I said".
- ⚠️ **Simple language never means hiding the problem.** Warnings, risks and disagreements stay — said with simple words.
- **Direct and technical tone. No flattery.** Go to the problem.
- **Challenge an incoherent request.** Do not follow blindly if it contradicts something already decided or would break existing logic. Say it, explain why, **discuss before coding**. An argued disagreement is worth more than obeying a bad idea.

### 2.2 Writing and changing things

- **Ask before writing code or making a real change** (new files, new features, deleting something, anything hard to undo). Propose, then WAIT for a clear yes. Asking a question and starting anyway is not allowed.
- 🚨 **NEVER modify this file on my own initiative** (SDH rule, adopted 2026-09-21 — it **replaces** the earlier "bookkeeping needs no second yes" rule). When something should go in: (1) tell him, (2) explain **what** and **why**, (3) ask, (4) write **only** on a yes. I detect the moment; he decides.
- **Targeted edits only.** Never rewrite a whole file without need. Change the smallest possible fragment.
- **Say which files are touched**, every time.
- 🚨 **NEVER a script that can erase a file.** Use the edit tool, which replaces a precise fragment and fails cleanly. If a script is truly unavoidable (mass replacement), it writes a **temporary file** and replaces the original only after full success — never open the target for writing first.
- ⚠️ **A CHANGE OF FORM MAKES EVERYTHING THAT DEPENDED ON IT SUSPECT.** An id, a class, a data format, a route, a rule: list what depended on it and check each one. *(Renaming the app in one place left the token header, `launch.json` and six docstrings behind.)*
- **Bugs: describe first, fix only after a yes.** Report any bug found along the way, even outside the current task.

### 2.3 After every finished step

- 🚨 **Run what I just wrote, before saying "it's done".** Static reading cannot see a screen that no longer builds, or a probe that measures nothing.
- 🚨 **Make a check FAIL before believing it.** A green test proves nothing until it has been seen turning red. *(Verified here on 2026-09-20: the winget search was only trusted after a fake package returned the same error.)*
- **Never state that something works.** Check it, then say **what** was checked and **when**.
- **Checking a registry is not proof.** A name can be free on PyPI, npm and GitHub and still belong to a real company. **Always do a real web search too** before saying something is free, available, or does not exist. *(Lesson of 2026-09-20: "Grabbity" passed every registry and was a Latvian software company.)*
- Before recommending any tool: check its repo is **not archived**, and its **last commit date**.

**Three tools, and they do different jobs:**

- 🧰 **`mes-erreurs-recurrentes`** says **WHAT** to check — the mistakes I repeat, each with the control that catches it. Load it before announcing "done", "fixed", "verified", "0 error", and before claiming something is absent, clean or impossible. It is global: it applies to every project of this user.
- 🧰 **`doubt-driven-development`** says **HOW** — have the work re-read by a fresh context whose job is to **demolish**, not to approve. I re-read with the idea that produced the mistake, so I cannot see it.
- 🧰 **`silent-failure-hunter`** hunts **one precise family of bug**: code that fails quietly while the app reports success. *(Added 2026-09-21 at the user's request. It is exactly the bug of 2026-09-20: yt-dlp skipped the download, the file never changed, and the window said **done**.)*
- **A confirmed mistake of MINE gets written into `mes-erreurs-recurrentes` the same day** — the habit, not the project's bug.

### 2.3bis After a big section is finished

A roadmap step marked ✅ is a **big section**. Do not wait for a compaction to audit: **run the two grids of §2.4 at that moment too**, on what the step touched.

- Pass 0 still applies first: did this step add a **new type** of thing that no pass looks at? Then write the missing line before running anything.
- The step is not ✅ until the grids have run. Announcing "done" before that is how a defect reaches the next step and becomes expensive.
- ⚠️ The same rule as everywhere: **separate real defects from broken probes**, and say plainly what was NOT checked.

### 2.4 Before compacting — the two grids

**Pass 0 first: revise the grid before running it.** List what the project gained since last time; for each new **type** of thing, ask which pass looks at it; if the answer is "none", write the missing line **before** starting. A new type triggers a revision, not a new file. The five natures never change — their **content** widens. Never add a sixth pass.

**Five passes on the code** — five different angles, never five times the same one:

1. **RUN IT** — start the app, open the page: 0 console error, then really do a detect, a download, and the Tools page. The most profitable pass, and the one that gets skipped.
2. **WHAT WE JUST CHANGED** — against what I announced, and against the older rules.
   ➕ **Added 2026-09-22 by a pass 0** — a **recipe** is a new kind of thing: flags we pass to somebody else's program. **A flag is not a fix until its effect has been SEEN.** No pass asked this, and that is exactly how `--record_data false` survived: it was passed to XHS-Downloader, the problem was announced fixed, and the database kept appearing. The control: change the flag, run the tool, and look at what is on the disk. If nothing differs, the flag does nothing.
3. **THE FROZEN DECISIONS** — the decisions table of §3 and the hard rules of §5 (never log a cookie, no DRM, never assume a tool is installed, `.gitignore`).
4. **NUMBERS AND IDENTIFIERS, COUNTED IN THE CODE** — never copied from another file nor from my own prose. "1752 extractors", "8 tools", "24 platforms": recount them.
5. **NAMES THAT ANSWER EACH OTHER** — HTML ids ↔ `getElementById`, API routes ↔ `fetch` calls, tool ids ↔ `platforms.py` ↔ `tools.py`, placeholders (`__APP_NAME__`, `__APP_TOKEN__`) ↔ what the server injects.
   ➕ **Added 2026-09-21 by a pass 0** — three types no pass named: the **JSON files** (`data/settings.json`, `data/tools.json` keys ↔ the code that reads them; `.claude/launch.json` ↔ the module name), the **`.bat` launcher** (the module it calls must exist), and **`requirements.txt`** (it must list exactly the imports that are not in the standard library — check with `ast`, not with a shell pipeline: the shell one printed nothing and looked fine).

**Five passes on this file** (it is our only memory): *(1)* subjects written in several sections, where a divergence hides · *(2)* every file path and identifier cited, checked against the disk and the real code · *(3)* internal contradictions · *(4)* "open" questions already decided, and "to do" already done · *(5)* roadmap states that match reality.

- ⚠️ **Separate real defects from broken probes** in the report. Announcing "22 anomalies" when there is one causes panic for nothing. A massively negative result is first suspect on the tool side.
- ⚠️ **If he asks for a check again, really redo it.** Never answer "already verified". A second pass has found what the first missed.

### 2.5 Two authorities

- **This file is the authority on DECISIONS**: why a choice was made, what is frozen, what must not be reopened. Code can show an `if`, never the reason it was written.
- **The CODE is the authority on FACTS**: a count, an identifier, what a function really does, what still exists. My prose about the code goes stale silently.
- ⚠️ When this file states a **fact** (a number, a list, a name), it is a candidate for checking, not a judge.

## 3. Locked decisions (v1)

| # | Decision |
|---|---|
| 1 | Project name: **Teleloadzai**. The name lives in **one config constant** so renaming stays cheap. |
| 2 | **Windows only for v1.** macOS / Linux come later. |
| 3 | Base engine: **yt-dlp + ffmpeg**. Both are managed by us — never assume they exist on the machine. |
| 4 | Specialist tools **only** where yt-dlp is weak. Do not add a tool "just in case". |
| 5 | First launch = **platform picker**. Install only the tools the chosen platforms need. |
| 6 | Safety net = **install on demand**. Never answer "not supported" if a tool exists — offer to install it and continue. |
| 7 | A **Tools page** in settings: installed / not installed / update available. The user can add or remove any tool, any time. |
| 8 | **Auto-update check on start**, in the background, never blocking. "Update all" button always visible. When a download fails, suggest updating **first** — that is the cause ~80% of the time. |
| 9 | **Cookies supported but OFF by default**, read from the browser (`--cookies-from-browser`). The user never types a password. |
| 10 | **No DRM platforms.** Netflix, Disney+, Prime Video, Spotify, paid course sites: out of scope, permanently. |
| 11 | Stack: **Python backend + local web UI**, shipped as a **.zip on GitHub Releases**. The user must not need to install Python. |
| 12 | **Open source on GitHub.** |
| 13 | **The user can change the tool.** Every platform has a Teleloadzai default, but the user may override it. Two levels: **per platform** (settings, permanent) and **per download** (one time, from the main window). Only tools that actually support that platform are offered. |
| 14 | **Link -> platform detection** is done with a domain table. **Short links must be resolved first** (`vt.tiktok.com`, `b23.tv`, `xhslink.com`, `t.co`...): follow the redirect, then detect. Unknown domain -> fall back to yt-dlp, which supports 1000+ sites. |
| 15 | **A failed download always offers a way out**: 1) update the tool, 2) retry with another tool, 3) retry with cookies. Never a dead end. |
| 16 | **Two downloads published**: `Teleloadzai-setup.exe` (installer: Start menu + uninstaller) and `Teleloadzai.zip` (portable, USB key). Same app inside both. |
| 17 | **The installer installs only Teleloadzai** — fast, works with no internet. The **tool picker runs at first launch, inside the app**, with progress bars and a **Retry** button. The **same screen** is reachable later from Settings -> Tools. One screen, never two. |
| 18 | **Update check before every use, but cached.** Store per tool: last check time + last known version. Before running a tool: note fresher than 24 h -> start at once; note older -> ask GitHub (1 request), then act. Never more than ~8 GitHub requests per day (the limit is 60 per hour). |
| 19 | **Default update mode = "Ask me first"** — a bar with `[Update now] [Later]`. The user can switch to *Automatic* or *Manual* in settings. **Never update while a download is running**: update before starting, or when the queue is empty. |
| 20 | **Standard library only, with ONE exception.** The server is `http.server`, the UI is one HTML file. The only pip package allowed is `pywebview` (decision 25). Every new dependency must be asked for. |
| 21 | **The local server is locked down**: it listens on `127.0.0.1` only, refuses any `Host` that is not localhost, and every `/api/` call must carry a secret token created at startup. Without this, any web page open in the browser could drive Teleloadzai. |
| 22 | **"Save as" window, ON by default.** When a link is added, the Windows "Save as" dialog opens: the user picks the folder AND the file name, and Windows itself asks before replacing. A setting turns it off (save straight to the folder). |
| 23 | **The dialog runs when the job is ADDED, never when it starts.** Otherwise a queue left alone would stop and wait for a window nobody is watching. |
| 24 | **Never a success that did not happen, and never a silent overwrite.** Two roads: *(a)* the user picked a path in the "Save as" window — Windows already asked about replacing, so yt-dlp gets `--force-overwrites`; *(b)* the user is **not** asked (`ask_where` off) — then nothing may be destroyed behind his back. After the run we compare each file's date with the start time; if it was not rewritten, the job says **"already there — nothing was downloaded"** (grey, not green) with a `Download again` button that forces it. ⚠️ Found on road (a) the 2026-09-20 and announced as fixed; the §2.4 audit found it **still alive on road (b)** the 2026-09-21. A fix on one path is not a fix. |
| 25 | **A real app window, not a browser tab.** `pywebview` (approved by the user 2026-09-20) opens a window with its own title and icon, using the WebView2 engine already inside Windows. The page is HTML, but the user never sees a browser -- same idea as VS Code or Discord. `--browser` still opens a normal tab, for development. |
| 26 | **gallery-dl and f2 need Python, and we ask the user for it.** Checked 2026-09-20: neither publishes a Windows program (gallery-dl has had no release file for 5 versions, f2 is pip only). If the user picks one of them, Teleloadzai checks for Python; if it is missing it shows a clear screen with the download link, the steps, and a **Check again** button. Never a dead end. *(The user chose this over bundling a hidden Python.)* |
| 27 | **Python packages are installed inside Teleloadzai's folder**, with `pip install --target`, never into the user's own Python. Removing Teleloadzai removes them. We never break another program on the machine. |
| 28 | **A tool always shows what it needs BEFORE the user clicks install**, never after. `gallery-dl` and `f2` show "needs Python". MP3 and MP4 need FFmpeg, which is why FFmpeg is a base tool installed for everyone. Nothing is discovered halfway through an install. |
| 29 | **Python is offered through `winget`** (`winget install Python.Python.3.13`), with the python.org page as the fallback for PCs without winget. Verified 2026-09-20: winget is on the user's PC, and it has FFmpeg, Python, yt-dlp, Streamlink, gallery-dl and N_m3u8DL-RE -- but **not** TikTokDownloader, XHS-Downloader or f2 (checked against a control package). So winget cannot replace our own downloader; it is used for Python only. |
| 30 | **"Update available" is decided on numbers only**, never on the text. Every project writes versions differently (`0.6.0-beta`, `0.6.0+df70f0b3`, `ffmpeg version 8.0.1-essentials_build`). Comparing text claimed an update when nothing had changed, and would also read `1.32.9` as newer than `1.32.13`. When either side has no number, we say nothing rather than nag. |
| 31 | **The installed version of a tool is cached** until the file itself changes (size + date). Starting yt-dlp only to read `--version` costs over a second, and the Tools page asks for all 8 at once: 3974 ms -> 127 ms. |
| 32 | **The first-launch screen and Settings -> Tools are the same list, rendered by one function.** Decision 17 in practice: the tool rows already say which platform each one serves, so no second "platform picker" screen was needed. |
| 33 | 🚨 **A task must never look frozen.** At every moment a job shows either a real measure or the reason there is none. With a percentage: show it with the speed and the time left. Without one: show what we DO know — seconds elapsed, bytes written so far, or the step being done ("joining video and sound"). **A bar stuck at 0% with nothing beside it is a defect, not a display choice.** ⚠️ **Never invent an estimate we cannot measure** — a wrong time left is worse than none. *(Found 2026-09-22: XHS-Downloader prints no percentage, so a Xiaohongshu download showed an empty bar from beginning to end, exactly like a crashed app. A live recording has a real measure we were not using: "14 of 60 minutes". A silent tool has one too: elapsed time and the bytes appearing in the folder we already watch.)* |
| 34 | 🚨 **A problem is always said, never swallowed.** Every failure reaches the user in plain words: which step, what happened, what he can do. Silence is the worst answer — it cannot be told apart from a frozen app. *(Counted 2026-09-22: 16 places catch an error and return silence. Three are user-visible: a short link that cannot be followed is never shown — `redirect_error` exists in the code and appears **0 times** in the page; a failed repackaging keeps the `.ts` and says nothing; a Windows dialog that errors looks exactly like the user pressing Cancel.)* ⚠️ Catching an error to keep the app alive is right. Catching it to keep the user ignorant is not. |

## 4. Tool matrix — verified 2026-09-20

| Platform | Tool | Status |
|---|---|---|
| YouTube, Vimeo, Dailymotion, Facebook, X, Reddit, Bilibili, SoundCloud, Bandcamp, Rumble, any `.m3u8` | **yt-dlp** | ✅ alive (189k ⭐, pushed 2026-08-30) |
| Instagram, Pinterest (galleries) | **gallery-dl** | ✅ alive (19k ⭐, 2026-09-04) |
| Twitch live | **streamlink** | ✅ alive (12k ⭐, 2026-09-06) |
| TikTok / Douyin, no watermark | **TikTokDownloader** | ✅ alive (16k ⭐, 2026-09-06) |
| Xiaohongshu | **XHS-Downloader** | ✅ alive (13k ⭐, 2026-09-06) |
| Encrypted HLS/DASH | **N_m3u8DL-RE** | ✅ alive (8.7k ⭐, 2026-07-03) |
| Kuaishou, Weibo | **f2** | 🟡 slow (2.6k ⭐, last push 2026-04-13) |
| Bilibili 4K/HDR | ~~BBDown~~ | ⛔ **ARCHIVED 2026-05-14** — use yt-dlp instead |
| WeChat Channels (视频号) | **wx_channels_download** (ltaoo) | ✅ **alive** (9.4k ⭐, 1.5k forks, pushed 2026-09-20, Go). **Corrected 2026-09-20 — my first check was wrong.** Works in a totally different way: MITM proxy + root certificate + Administrator rights; the user clicks a button **inside the WeChat PC app**, there is no link to paste. License = NOASSERTION -> do **not** bundle it. (`WeChatVideoDownloader` by lecepin is the archived one.) |

Re-verify this table before trusting it. Tools die fast in this field.

## 5. Hard rules

1. **Cookies are as dangerous as passwords.** Never log, print, copy, upload or commit a cookie value — not in logs, not in error messages, not in crash reports.
2. **Never write code that removes or bypasses DRM.**
3. **Never assume a tool is installed.** Always ask the Tool Manager.
4. `.gitignore` must exclude at minimum: `bin/`, `downloads/`, `*.log`, and any config file that can hold session data.
5. The UI must warn the user: heavy downloading with your own cookies can get the account suspended. Suggest a secondary account.

## 6. Still open

- WeChat Channels — a living tool exists (`ltaoo/wx_channels_download`) but it does not fit the "paste a link" model: it needs Administrator rights, installs a root certificate, and the user clicks inside WeChat. **Not decided:** v1 shows a clear message + link; v2 could launch the tool for the user. I will not write interception or decryption code myself.
- Publish on PyPI or not.
- yt-dlp has two channels, *stable* and *nightly*. Nightly gets fixes for broken sites several days earlier. Offer the choice to the user? **Not decided.**
- `_old/` holds an old `mp3.bat` + `yt-dlp.exe`. **It is NOT a design reference** — the user wrote it quickly, once, and said so on 2026-09-20. Never copy its choices or quote it as a reason. It is kept only as a fallback the user can still run.

## 7. Roadmap

### Phase 1 — the basics (v1)

| Step | What | State |
|---|---|---|
| 0 | Name, rules, this file | ✅ done 2026-09-20 |
| 1 | **The brain**: link -> platform -> tool. Domain table + short-link resolver. No UI. | ✅ done 2026-09-20 (`teleloadzai/platforms.py`, `teleloadzai/detect.py`) |
| 2 | **First window**: paste a link -> MP3 / MP4 with yt-dlp. | ✅ done 2026-09-20 |
| 3 | Queue, progress bars, quality choice, output folder | ✅ done 2026-09-20 (`jobs.py` queue + Stop, quality dropdown, native folder picker in `dialogs.py`, 1-5 downloads at a time) |
| 4a | **Tool Manager engine** (`tools.py`): registry of 8 tools, version check cached 24 h, install (exe / zip / pip), remove, status | ✅ done 2026-09-20 |
| 4b | **Tools page** in Settings + the Python screen (winget) | ✅ done 2026-09-20 |
| 4c | First-launch screen + install on demand + `[Update]` / `[Retry]` on a failed download | ✅ done 2026-09-20 |
| 4d | **Run the other tools** (`runners.py`): one engine, five recipes, folder-watching instead of parsing each tool's output. The window offers only tools we can actually drive. | ✅ done 2026-09-22. Proven against real links: **gallery-dl, N_m3u8DL-RE, XHS-Downloader, streamlink**. ⚠️ **f2 has never run once** — it needs cookies. |
| 5 | Cookies (OFF by default). Unlocks f2 (Kuaishou, Weibo), Instagram and Facebook private posts, YouTube age-restricted — and 4e after it. | ⬅ next |
| 4e | 🚨 **TikTokDownloader, by its local server.** It has **no command line**: verified 2026-09-21, `--help` opens a language menu (*"请选择语言 / Please Select Language"*). Its own door is a local server on `127.0.0.1:5555`, which is a different mechanism — start the program, keep it alive, talk HTTP, stop it. It also said `配置文件 cookie 参数未设置`, so it can do nothing without cookies. **Placed after step 5 on purpose. The user asked explicitly that this not be dropped.** | |
| 6 | Build `Teleloadzai-setup.exe` + `Teleloadzai.zip`, publish on GitHub | |

### Phase 2 — inspiration, then advanced features

Only **after** Phase 1 works. Goal: study other download GUIs, list the good ideas,
then choose a few. Do not start building advanced features before this study.

**Safety rule for this phase:** the "video downloader" category is full of adware.
- **Open source** -> safe to install and to read the code.
- **Commercial / closed source** -> screenshots, videos and documentation **only**. Never install.

Apps to study (open source): Parabolic (Nickvision), Open Video Downloader (jely2002),
Tartube, MeTube (local web UI, same architecture as us), cobalt (best minimal design),
Media Downloader (Qt, several tools behind one window), XDM / Motrix / Persepolis (real queue managers).

Look only (do not install): JDownloader 2, 4K Video Downloader, IDM, Downie.

**Feature ideas already on the table** (not approved, just parked): clipboard watching,
playlists and channels, subscriptions with auto-download, scheduler, speed limit, proxy,
subtitles (download / embed / translate), SponsorBlock, cut a section (2:00 -> 5:00),
filename templates, "already downloaded" archive, batch import from a .txt file,
MP3 tags + cover art, notifications, history and search, dark mode.
