# CLAUDE.md — Teleloadzai

> Version 0.2 — started 2026-09-20.
> This file grows with the project. Only decisions the user has approved go in here.
> Lightened 2026-10-31: the stories, evidence and round-by-round history moved word for word to `docs/HISTORY.md`; the beliefs about other programs to `docs/BELIEFS.md`.

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
| `runners.py` | runs every other tool: one engine, one recipe each. Also says which tools are **not usable yet**, so the window never offers one it cannot drive, and which choices each tool **really** makes (`CHOICES`, decision 40). |
| `toolservers.py` | drives the tools that have no command line, only a local server: **TikTokDownloader** (port 5555, answers its menu by reading it) and **KS-Downloader** (port 5557, `main.exe api`). One machine for both: starts a server only while a job needs it, stops it after, asks where the file is. *(Was `tiktokserver.py` until 2026-09-23.)* |
| `cookies.py` | the cookie file: import it (filtered to our sites), describe it without ever showing a value, give it to the tools that can take it safely, wash secrets out of error text (`redact`) |
| `login.py` | the in-app log-in window (decision 36): opens the site on its log-in page, **watches the window** (closes it by itself once the user is in, keeps the cookies if he closes it himself), takes that one site's cookies, forgets them for real |
| `explain.py` | what an error MEANS, only for errors really met, each with its evidence (decision 38). Also marks which error texts are the tool's own words |
| `tools.py` | the Tool Manager: install, update, versions |
| `jobs.py` | the download queue |
| `console.py` | the Console page's lines: downloads, title reads, installs and updates, and the page's own messages (since 2026-10-26; until then downloads only), washed by `cookies.redact`, the last 2,000 in memory only — never written to disk by us |
| `needs.py` | what each site needs per program — a visit, nothing, an account — for the Sites page: the proofs of §4 as a start (`SEEN_BEFORE`, with their dates), then kept true by the real results of downloads on this PC (`data/needs.json`: site, program, result, date — never a cookie) |
| `notify.py` | the Windows message when downloads end (Phase 2 item 6): a tray message through Windows' own functions, named "Teleloadzai" by the process's app id, only when the window is not in front, several ends in one message; its icon lives only with its box |
| `children.py` | every tool process we start is put in a Windows **job object** with "kill on close", so it dies with Teleloadzai even after a crash or a closed console (TikTokDownloader's and KS-Downloader's servers on 0.0.0.0 included); also `stop_tree` (added 2026-10-18) |
| `dialogs.py` | the Windows "Save as" and folder windows |
| `server.py` | the local server |
| `__main__.py` | opens the real app window (pywebview) |
| `web/index.html` | the whole interface, one file. **Screens are `data-view`, and `showView()` is the only thing that changes one.** A card is drawn when the screen matches **and** the card has something to say (`.hidden`) — two separate questions that used to be answered by one mechanism. *(2026-09-22: Settings was a card wedged under the link box. Hiding it with CSS would have hidden the status line with it, and every message the app says would have gone somewhere invisible. Adding a screen is now one `data-view`.)* |

## 2. How to work with the user

- The user is a French speaker writing in English. **Use simple, short sentences.** Avoid rare words and idioms.
- Tables and short lists are better than long paragraphs.
- **Always answer in English.** If he writes in French, keep answering in English and say so in one short line ("You wrote in French — I'm staying in English"): he may have switched without meaning to. Switch to French only if he asks. *(Changed 2026-09-25 at his request; this line used to say "if the user switches to French, follow in French".)*
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
- 🔎 **Before starting a new big thing, say if a skill could help — and ask to go and look.** Not only the skills already on this PC: **the internet too**. A roadmap step, a new tool to drive, a part of the trade we have never touched — that is the moment. I say *what* I would look for and *why*; the user decides. ⚠️ Three limits: a skill is **read before being installed**, never installed blind. A skill is **not a menu** (§2.1) — I come back with **one**, not with twelve. And I say plainly when the search found nothing, instead of bringing back something almost useful. *(Asked by the user 2026-09-22, after a search found `verifying-external-behavior`, which describes the `--record_data false` bug better than we had.)*
- 🚨 **NEVER modify this file on my own initiative** (SDH rule, adopted 2026-09-21 — it **replaces** the earlier "bookkeeping needs no second yes" rule). When something should go in: (1) tell him, (2) explain **what** and **why**, (3) ask, (4) write **only** on a yes. I detect the moment; he decides.
- **Targeted edits only.** Never rewrite a whole file without need. Change the smallest possible fragment.
- **Say which files are touched**, every time.
- 🚨 **NEVER a script that can erase a file.** Use the edit tool, which replaces a precise fragment and fails cleanly. If a script is truly unavoidable (mass replacement), it writes a **temporary file** and replaces the original only after full success — never open the target for writing first.
- 🚨 **A CHANGE REACHES MORE THAN THE LINE CHANGED.** Before saying "done", list everything the change touches, check each one, and **adapt what no longer fits the new code** — where adapting is not simple, propose the fix. Three lists, every time:
  - **every program it drives** — all of them, not only yt-dlp, in one table: works / does not / fix proposed;
  - **every screen, at the user's two sizes** (small window, full screen), when the layout can move — never a third size unasked;
  - **every name, id, route, data format or rule** that depended on what changed.
  *(The user's rule, 2026-10-24, joining three: this line's old "a change of form makes everything that depended on it suspect" — renaming the app in one place left the token header, `launch.json` and six docstrings behind; the two sizes, until then only in my memory; and "every function that calls the tools is checked for all of them" — "Choose for each" sent a "Save as" name that gallery-dl and XHS-Downloader throw away.)*
- **Bugs: describe first, fix only after a yes.** Report any bug found along the way, even outside the current task.

### 2.3 After every finished step

- 🚨 **Run what I just wrote, before saying "it's done".** Static reading cannot see a screen that no longer builds, or a probe that measures nothing.
- 🚨 **Make a check FAIL before believing it.** A green test proves nothing until it has been seen turning red. *(Verified here on 2026-09-20: the winget search was only trusted after a fake package returned the same error.)*
- **Never state that something works.** Check it, then say **what** was checked and **when**.
- **Checking a registry is not proof.** A name can be free on PyPI, npm and GitHub and still belong to a real company. **Always do a real web search too** before saying something is free, available, or does not exist. *(Lesson of 2026-09-20: "Grabbity" passed every registry and was a Latvian software company.)*
- Before recommending any tool: check its repo is **not archived**, and its **last commit date**.

**Six tools, and they do different jobs. Five are skills (🧰), one is an agent (🤖) — a different thing, called a different way.**

- 🧰 **`mes-erreurs-recurrentes`** says **WHAT** to check — the mistakes I repeat, each with the control that catches it. Load it before announcing "done", "fixed", "verified", "0 error", and before claiming something is absent, clean or impossible. It is global: it applies to every project of this user.
- 🧰 **`doubt-driven-development`** says **HOW** — have the work re-read by a fresh context whose job is to **demolish**, not to approve. I re-read with the idea that produced the mistake, so I cannot see it.
- 🧰 **`verifying-external-behavior`** — before writing code around **somebody else's program**. Every tool we drive is somebody else's program. Its sentence is our own bug: *"permissive clients don't reject wrong arguments — they ignore them"* — that is `--record_data false`, passed to XHS-Downloader, ignored by it, announced by me as fixed. Load it before adding a flag, a sub-command or a config file to a recipe. *(Installed 2026-09-22 from `wdm0006/python-skills`, MIT.)*
- 🧰 **`security-and-hardening`** — before any code that touches a **cookie**, a token or a saved credential, which means all of step 5. ⚠️ It is written for Node web apps; most of it does not apply. Take "Secrets Management", "Never log sensitive data", "Destructive Operations on Derived Paths", and leave the rest.
- 🧰 **`ux-copy`** — when writing **what the user is told**: an error, an empty state, a loading line, a confirm box. It is how decisions 33 and 34 get their sentences. We wrote the rules; this writes the words.
- 🤖 **`silent-failure-hunter`** hunts **one precise family of bug**: code that fails quietly while the app reports success. *(Added 2026-09-21 at the user's request. It is exactly the bug of 2026-09-20: yt-dlp skipped the download, the file never changed, and the window said **done**.)* ⚠️ It lives in `agents/`, not `skills/` — an **agent**, not a skill. Corrected 2026-09-22; this file called it a skill for a day.
- **A confirmed mistake of MINE gets written into `mes-erreurs-recurrentes` the same day** — the habit, not the project's bug.

### 2.3bis After a big section is finished

A roadmap step marked ✅ is a **big section**. Do not wait for a compaction to audit: **run the two grids of §2.4 at that moment too**, on what the step touched.

- Pass 0 still applies first: did this step add a **new type** of thing that no pass looks at? Then write the missing line before running anything.
- The step is not ✅ until the grids have run. Announcing "done" before that is how a defect reaches the next step and becomes expensive.
- ⚠️ The same rule as everywhere: **separate real defects from broken probes**, and say plainly what was NOT checked.

### 2.4 Before compacting — the two grids

**Pass 0 first: revise the grid before running it.** List what the project gained since last time; for each new **type** of thing, ask which pass looks at it; if the answer is "none", write the missing line **before** starting. A new type triggers a revision, not a new file. The five natures never change — their **content** widens. Never add a sixth pass.

**Five passes on the code** — five different angles, never five times the same one:

1. **RUN IT** — start the app, open the page: 0 console error, then really do a detect, a download, and the Programs page. The most profitable pass, and the one that gets skipped.
   ➕ **Added 2026-09-26 by a pass 0** — **press the buttons, not only the main path** (decision 40): every button, list and switch, its effect observed — a file, a process gone, a setting saved. The one-pass-for-all audit of that day found four defects the usual detect / download / Tools page never touches (a false "updated", an unsafe tool update, two false sentences).
   ➕ **Added 2026-09-22 by a pass 0** — running it is not only what appears on screen. **Ask what the step left BEHIND: what is still running, and what is now on the disk.** Step 5 added two things no pass named — a **second window** we open and must close, and a **browser profile** we write and must be able to delete. Both hid a defect: Windows keeps that folder locked while the app lives, so "Forget them" quietly did nothing, and a forced stop skipped the cleanup entirely. Neither shows in the page, in a name, or in a count. The control: after the step, **list the windows still open and the folders newly written**, and for each one ask who closes it and who deletes it.
   ➕ **Added 2026-10-24 by a pass 0** — a **tray icon** is a new thing left behind (item 6's message lives on one). The control: show a message, close the app (`notify.close`), and ask Windows to modify our icon — it must fail; without `close()` it succeeds (seen both ways that day).
   ➕ **Added 2026-10-24 by a pass 0** — a **key that acts on the whole window** (Ctrl+Enter, Phase 2 item 4) is a new kind of control, and pass 1 named only buttons, lists and switches. The control: **press every key in each state where it must do nothing** (no card, a grey button, Settings, a held key, a new link typed), not only where it acts — and once in the real window, where pywebview decides which keys reach the page.
   ➕ **Added 2026-10-25 by a pass 0** — a **pop-up menu** (the ⋯ of model D) is a new kind of control. The control: open it, then check it closes with Esc (the keyboard back on its button), with a click elsewhere, and when another opens — and press each of its items.
2. **WHAT WE JUST CHANGED** — against what I announced, and against the older rules.
   ➕ **Added 2026-09-22 by a pass 0** — a **recipe** is a new kind of thing: flags we pass to somebody else's program. **A flag is not a fix until its effect has been SEEN.** No pass asked this, and that is exactly how `--record_data false` survived: it was passed to XHS-Downloader, the problem was announced fixed, and the database kept appearing. The control: change the flag, run the tool, and look at what is on the disk. If nothing differs, the flag does nothing.
   ➕ **Since 2026-09-25, by passes 0** — every **belief about somebody else's program** we keep (an error explanation, a skip detector, a text encoding, a replaced library method, the tables `runners.CHOICES`, `login._NEEDS`, `login._BADGES`…, flags seen once, Windows and pywebview behaviours) is listed with its evidence in **`docs/BELIEFS.md`**. Each is true for one version. The control, line by line: after an update of that program or library, **run it once and look**. Pass 2 reads that file; a new belief goes there, not here.
3. **THE FROZEN DECISIONS** — the decisions table of §3 and the hard rules of §5 (never log a cookie, no DRM, never assume a tool is installed, `.gitignore`).
   ➕ **Added 2026-10-25 by a pass 0** — the **Console** shows programs' raw words and can write them to a file (Save as file). *(Widened 2026-10-26 by a pass 0: its lines are programs' words, title reads, installs and updates, and the page's own messages through `/api/console/note` — token required, refused without it, seen.)* The control: plant a cookie-shaped line, check it comes out washed in the page and in the saved text — and once with the washing switched off, where it must show (seen both ways that day).
   ➕ **Added 2026-10-24 by a pass 0** — the **clipboard** is a new kind of thing we read: the user's private text (a password, a message) can be in it. Only links may leave `server.clipboard_links`; nothing of it is stored or printed. The control: put a fake password beside a link in the clipboard, and check the password does not come back (and that it **does** when the link pattern is made to match everything — seen both ways that day).
4. **NUMBERS AND IDENTIFIERS, COUNTED IN THE CODE** — never copied from another file nor from my own prose. "1752 extractors", "8 tools", "24 platforms": recount them.
   ➕ **Added 2026-10-18 by a pass 0** — a **CSS size computed from a measured size** is a number too. *(Until 2026-10-23 the Downloads list was `100vh − 264px`; the redesign removed that: the main screen is one column `100vh` tall and the list takes the room left, so no size is computed by hand any more.)* What still breaks silently: the page scrolling when the link box, the card or the list's minimum height grows. The control: after such a change, **re-measure** with 9 rows in the user's **small window (860×814 inside)** and **full screen (1463×834)** — the page not scrolling, the list scrolling in its card.
5. **NAMES THAT ANSWER EACH OTHER** — HTML ids ↔ `getElementById`, API routes ↔ `fetch` calls, tool ids ↔ `platforms.py` ↔ `tools.py`, placeholders (`__APP_NAME__`, `__APP_TOKEN__`) ↔ what the server injects.
   ➕ **Added 2026-09-21 by a pass 0** — three types no pass named: the **JSON files** (`data/settings.json`, `data/tools.json`, since 2026-10-24 `data/jobs.json` — its fields are `jobs._KEPT` — and since 2026-10-25 `data/needs.json` — "site|program" → need, seen — keys ↔ the code that reads them; `.claude/launch.json` ↔ the module name), the **`.bat` launcher** (the module it calls must exist), and **`requirements.txt`** (it must list exactly the imports that are not in the standard library — check with `ast`, not with a shell pipeline: the shell one printed nothing and looked fine).

➕ **Added 2026-10-21 by a pass 0:** `PRODUCT.md` (the design skill's product record: users, purpose, constraints, no look) is a **second memory file**. The five file passes below run on it too, and on any later DESIGN.md: its facts (window sizes, sites, chosen functions) go stale like ours. ➕ *2026-10-31:* and on `docs/BELIEFS.md`, moved out of pass 2. `docs/HISTORY.md` is a frozen record: not checked.

**Five passes on this file** (it is our main memory): *(1)* subjects written in several sections, where a divergence hides · *(2)* every file path and identifier cited, checked against the disk and the real code · *(3)* internal contradictions · *(4)* "open" questions already decided, and "to do" already done · *(5)* roadmap states that match reality.

- ⚠️ **Separate real defects from broken probes** in the report. Announcing "22 anomalies" when there is one causes panic for nothing. A massively negative result is first suspect on the tool side.
- ⚠️ **If he asks for a check again, really redo it.** Never answer "already verified". A second pass has found what the first missed.

### 2.5 Two authorities

- **This file is the authority on DECISIONS**: why a choice was made, what is frozen, what must not be reopened. Code can show an `if`, never the reason it was written.
- **The CODE is the authority on FACTS**: a count, an identifier, what a function really does, what still exists. My prose about the code goes stale silently.
- ⚠️ When this file states a **fact** (a number, a list, a name), it is a candidate for checking, not a judge.

## 3. Locked decisions (v1)

Each line is the decision and its reason. **The stories, evidence and dates behind them are in `docs/HISTORY.md` §3** (word for word, as of 2026-10-31) — read it before reopening a decision.

| # | Decision |
|---|---|
| 1 | Project name: **Teleloadzai**. The name lives in **one config constant** so renaming stays cheap. |
| 2 | **Windows only for v1.** macOS / Linux come later. |
| 3 | Base engine: **yt-dlp + ffmpeg**, both managed by us — never assume they exist on the machine. |
| 4 | Specialist tools **only** where yt-dlp is weak. Never a tool "just in case". |
| 5 | **The installer asks which sites you use**, and installs only the tools they need (step 6). *(Changed 2026-09-26; was a first-launch picker — see 17.)* |
| 6 | Safety net = **install on demand**. Never answer "not supported" if a tool exists: offer to install it and continue. |
| 7 | A **Programs page** (left menu): installed / not installed / update available. The user can add or remove any tool, any time. |
| 8 | **Update check on start**, in the background, never blocking. **"Update all"** in the bar and on Programs. Update is offered only when a newer version exists; "updated" is said only when the version read from the tool really changed. A failed download suggests updating first — **as advice, not as a cause** (38); its row offers "Update <tool> and retry". |
| 9 | **Cookies supported but OFF by default. The user never types a password into Teleloadzai.** `--cookies-from-browser` is **not** used: it fails on this PC (Chromium's app-bound encryption, yt-dlp issue 10927). The two roads are decision 36's. |
| 10 | **No DRM platforms** (Netflix, Disney+, Prime Video, Spotify, paid course sites): out of scope, permanently. |
| 11 | Stack: **Python backend + local web UI**, shipped on **GitHub Releases**. The user must not need to install Python. |
| 12 | **Open source on GitHub.** |
| 13 | **The user can change the tool**: per site (Sites page, permanent) and per download (the card). Only usable tools are offered; a saved choice no longer usable is ignored. When the default's proven **log-in** is missing, the card starts on an installed tool that needs none and says so — the default itself never changes, a "visit" need never moves it, and a tool the user presses always stands. **The switch keeps the program names** (decided, not to be reopened); the result is said in words under it. **The format can choose the tool**: MP3 or subtitles on a tool that makes none move the card to one that does, said; MP4 gives it back. **The Quality list = the video's real heights only**, read with the download's own rule (`ytdlp._MP4_BEST`); "Best" carries **no number** (TikTok answers 720p or 576p from one request to the next). |
| 14 | **Link → platform** by a domain table. **Short links are resolved first.** Unknown domain → yt-dlp. |
| 15 | **A failed download always offers a way out**: update the tool, another tool, cookies. Never a dead end. |
| 16 | **Two downloads published**: `Teleloadzai-setup.exe` (Start menu + uninstaller) and `Teleloadzai.zip` (portable). Same app inside both. |
| 17 | 🔄 **Tools are chosen in the installer** ("Which sites do you use?", progress, Retry, never blocks on one). Every other way in is install on demand (6). gallery-dl stays on demand (Python, 26). **FFmpeg comes with the first tool installed.** First launch = one line + **Manage programs**. ⚠️ Cost accepted: the installer needs the internet. |
| 18 | **Update check cached**: every **6 hours** (`tools.CACHE_HOURS`), plus right after a failed download, at most once an hour per tool — about 30 GitHub requests a day (limit 60 per hour). |
| 19 | **Update modes** (a setting): **Ask me first** (default: the bar, "Update and retry") · **Automatic** (updates at start; a failed download is updated and retried **once**) · **Manual** (badges only). **A tool is never updated while it is downloading** — it waits; FFmpeg waits for all downloads. **yt-dlp channel**: Stable by default; Preview offered on a failed yt-dlp row when stable is already the newest. |
| 20 | **Standard library only, with ONE exception: `pywebview`** (25). Every new dependency must be asked for. |
| 21 | **The local server is locked down**: `127.0.0.1` only, a localhost `Host` only, a secret token on every `/api/` call. **The port is ours alone** (`SO_EXCLUSIVEADDRUSE`, `server.claim`, taken before anything else runs): a second copy says *"Teleloadzai is already open"* and exits. |
| 22 | **"Save as" window, ON by default**: the user picks folder and name, Windows asks before replacing. A setting turns it off. Several links: **"Same for all"** = one folder window; **"Choose for each"** = one window per video. A program that names its files itself (`runners.NAMES_ITSELF`) is asked a **folder**, never a name. |
| 23 | **The dialog runs when the job is ADDED, never when it starts** — a queue left alone must not wait for a window nobody watches. |
| 24 | **Never a success that did not happen, and never a silent overwrite.** Name chosen in "Save as" → Windows already asked, so `--force-overwrites`. Not asked → nothing destroyed: a file not rewritten says **"already there — nothing was downloaded"** (grey) with **Download again** — on every tool (`runners._already_there`). A post of several items is numbered "name 1", "name 2"…, and forcing is allowed only when no numbered file is there (`ytdlp._only_chosen_name`). A fix on one path is not a fix. |
| 25 | **A real app window, not a browser tab**: `pywebview` (WebView2, already in Windows). `--browser` opens a tab, for development. |
| 26 | **gallery-dl needs Python, and we ask the user for it**: a clear screen, the link, the steps, **Check again**. Never a dead end. *(f2 was removed, 39.)* |
| 27 | **Python packages go inside Teleloadzai's folder** (`pip install --target`), never into the user's own Python. |
| 28 | **A tool shows what it needs BEFORE install** ("needs Python"). MP3 and MP4 need FFmpeg, a base tool. |
| 29 | **Python is offered through `winget`**, python.org as the fallback. winget is used for Python only. |
| 30 | **"Update available" is decided on numbers only**, never on text. No number on either side → say nothing. |
| 31 | **A tool's installed version is cached** until its file changes (size + date). TikTokDownloader and KS-Downloader have no readable version: the release the app installed is recorded (`installed_from`); an install made before 2026-10-21 stays "unknown". |
| 32 | **The Programs page is the only tool list**, drawn by one function (`renderTools`). |
| 33 | 🚨 **A task must never look frozen.** Always a real measure or the reason there is none: %, speed, time left; else elapsed time, bytes so far, or the step being done. **Never invent an estimate.** Sizes: `12.3 MB / 45.6 MB`, `~` before yt-dlp's estimate, `so far` where no total exists; MB = 1024 × 1024. A file still being written must be asked itself (Windows' folder listing gives its old size). |
| 34 | 🚨 **A problem is always said, never swallowed**: which step, what happened, what the user can do. Catching an error to keep the app alive is right; to keep the user ignorant is not. **Stop ends the whole process family** (`stop_tree`) and removes **only its own** unfinished pieces. A title nobody could read is said, and the file is named `unknown`, `unknown (2)`… (one naming rule: the "Save as" choice, else the post's text, else the card's title, else `unknown`). |
| 35 | 🚨 **A screen that asks for something sensitive explains itself first**: what it is, why it is needed, what we do **not** do with it, and the risk. |
| 36 | 🚨 **Logging in happens INSIDE Teleloadzai; importing a `cookies.txt` is the second road.** Reason: a browser export hands us every site, a log-in hands us one. Kept in `login.py`, each seen: read the cookies on the platform's own page · a log-in keeps **only the chosen site's** cookies · Facebook / Google log-ins use WebView2's own pop-up · the window **closes by itself** on the site's proven log-in cookie (`login._BADGES`), else on leaving the log-in page; closed by hand it keeps what it had · the window is private: log-ins live only in `data/cookies.txt` · cookies of a refused site are removed at start. **A sign per site**: green (log-in cookie), red (past its date), blue **Visited** (the site's cookies, no account), nothing — **never a grey "maybe"**; one rule, `login._sign`, for Sites and the card. An import **merges**, never replaces; "Keep every site" was removed. **"Use my log-ins" off pauses both roads.** What each site needs (a visit / nothing / an account) is shown with its date, learned from real downloads (`needs.py`); a download while logged in proves nothing. |
| 37 | 🚨 **A tool's own words are WASHED before they reach the screen, never hidden** (`cookies.redact`). It hides more than it must, on purpose: a token in a screenshot cannot be taken back. |
| 38 | 🚨 **Every error is explained — but ONLY with what we KNOW.** Known: an error really seen, cause checked, in `explain.py` with its evidence. Unknown: the tool's words (washed) + *"Teleloadzai does not recognise this error."* **Never a guessed cause.** Advice stays allowed, said as advice. |
| 39 | 🚨 **A second tool for a platform only if it passes three points**: (1) alive, (2) works on this PC — a real file, checked with ffprobe, (3) gives something the first does not. Never to reach a number. Failed so far: BBDown, yutto, lux, you-get (Bilibili), bandcamp-dl, internetarchive, nndownload; **f2 removed** 2026-09-26. |
| 40 | 🚨 **Every button, list and switch has a real action behind it, SEEN working** in the running app, its effect observed. One that cannot be proven is hidden. **The window shows only what each tool really does** (`runners.CHOICES`) **and what it needs before Download** (`login._NEEDS`). Each is a claim about another program: seen, not assumed, re-checked after an update. |
| 41 | 🚨 **Teleloadzai never adds code to work around a program's bug.** It is reported to that program, and we wait for its new version. Choosing among what a program offers stays ours. yt-dlp forbids AI-written contributions: I give the user the facts and the steps; **the report is written by the user**. |

## 4. Tool matrix — verified 2026-09-20, kept up to date since

The proofs (sizes, ffprobe results, links, dates) are in `docs/HISTORY.md` §4.

| Platform | Tool | Status |
|---|---|---|
| YouTube, Vimeo, Dailymotion, Facebook, X, Reddit, Bilibili, SoundCloud, Bandcamp, Rumble, any `.m3u8` | **yt-dlp** | ✅ alive |
| Instagram, Pinterest (galleries) | **gallery-dl** | ✅ alive. Instagram without a log-in: the card starts on yt-dlp (decision 13). |
| Twitch live | **streamlink** | ✅ alive |
| **Douyin** | **TikTokDownloader** (renamed DouK-Downloader) | ✅ proven 2026-09-22, through its Web API. **A visit is enough.** |
| TikTok | **TikTokDownloader** or **yt-dlp** | ✅ proven 2026-09-23 through both. TikTokDownloader 1280×720, yt-dlp 1024×576 ("higher quality" / "smaller file"). **"No watermark" stays unwritten** until a video with one has been seen. Its file server checks `tt_chain_token` (cookies + Referer together). Port 5555 is fixed in its code (Tencent Androws can hold it). |
| ⚠️ *their servers* | | 🚨 TikTokDownloader and KS-Downloader bind **`0.0.0.0`** with **no token**, and hold the user's cookie while they run. **So we never leave them open**: started when a job needs one, stopped when the last job ends, stopped when Teleloadzai closes. |
| Xiaohongshu | **XHS-Downloader** | ✅ alive. Its empty `ExploreData.db` is removed after the run (`Recipe.litter`). |
| Encrypted HLS/DASH | **N_m3u8DL-RE** | ✅ alive |
| Weibo | **gallery-dl** (default) or **yt-dlp** | ✅ the same video from both, 2026-09-26. |
| **Kuaishou** | **KS-Downloader** | ✅ proven 2026-09-23 — the only tool that works (decision 39). Server `main.exe api`, port **5557**. ⚠️ Kuaishou sometimes refuses every program for a while. |
| Bilibili 4K/HDR | ~~BBDown~~ | ⛔ archived 2026-05-14 — yt-dlp instead |
| ⚠️ *Bilibili, 2026-10-24* | | ⚠️ **Fails in every program**: links now carry a language (`/en/video/…`), yt-dlp fix #17898 not merged; the 1080p **AV1** picture stops at 1,432,959 bytes (H.264 comes whole). **Nothing added on our side** (decision 41). Pretending to be another browser was tried once and stopped: Teleloadzai does not trick a site's protection. |
| WeChat Channels (视频号) | **wx_channels_download** (ltaoo) | ✅ alive, but not driven: MITM proxy, root certificate, Administrator rights, no link to paste (§6). Licence NOASSERTION → never bundled. |

**No-log-in audit, 2026-09-26** (one public link per site, no cookies):
- **Works:** YouTube, Bilibili (then), Facebook, Dailymotion, Odysee, SoundCloud, Bandcamp, Niconico, Archive.org, Pinterest, Weibo (gallery-dl), Reddit / Instagram / TikTok (yt-dlp), Twitch (streamlink), X, Xiaohongshu.
- **Needs something:** Instagram / gallery-dl (a log-in) · TikTok / TikTokDownloader and Douyin (a **visit**) · Kuaishou (a log-in) · Vimeo (an account, never tried with one).
- **Not proven:** Rumble, TED, Mixcloud, Twitch with yt-dlp, Reddit / gallery-dl.

Re-verify this table before trusting it. Tools die fast in this field.

## 5. Hard rules

1. **Cookies are as dangerous as passwords.** Never log, print, copy, upload or commit a cookie value — not in logs, not in error messages, not in crash reports.
2. **Never write code that removes or bypasses DRM.**
3. **Never assume a tool is installed.** Always ask the Tool Manager.
4. `.gitignore` must exclude at minimum: `bin/`, `downloads/`, `*.log`, and any config file that can hold session data.
5. The UI must warn the user: heavy downloading with your own cookies can get the account suspended. Suggest a secondary account.

## 6. Still open

- WeChat Channels — a living tool exists (`ltaoo/wx_channels_download`) but it does not fit the "paste a link" model: it needs Administrator rights, installs a root certificate, and the user clicks inside WeChat. **v1 is done (2026-09-25):** a WeChat link gets a clear card — what cannot be done, where that program lives, and why Teleloadzai does not run it. **Still not decided:** v2, launching the tool for the user. I will not write interception or decryption code myself.
- Publish on PyPI or not.
- ~~yt-dlp has two channels, *stable* and *nightly*. Offer the choice to the user?~~ **Decided and built 2026-10-21** (decision 19): a setting, Stable by default, "Preview" offered on a failed yt-dlp row when stable is already the newest.
- `_old/` holds an old `mp3.bat` + `yt-dlp.exe`. **It is NOT a design reference** — the user wrote it quickly, once, and said so on 2026-09-20. Never copy its choices or quote it as a reason. It is kept only as a fallback the user can still run.

## 7. Roadmap

What each step did, found and checked, round by round: `docs/HISTORY.md` §7 (word for word, as of 2026-10-31). New results go in a dated section of that file; this table keeps the **state** and **what is still open**.

### Phase 1 — the basics (v1)

| Step | What | State |
|---|---|---|
| 0 | Name, rules, this file | ✅ 2026-09-20 |
| 1 | **The brain**: link → platform → tool (`platforms.py`, `detect.py`) | ✅ 2026-09-20 |
| 2 | **First window**: paste a link → MP3 / MP4 with yt-dlp | ✅ 2026-09-20 |
| 3 | Queue, progress, quality choice, output folder | ✅ 2026-09-20 |
| 4a | **Tool Manager engine** (`tools.py`): registry of **8 tools**, versions, install / update / remove | ✅ 2026-09-20 |
| 4b | **Programs page** + the Python screen (winget) | ✅ 2026-09-20 |
| 4c | Install on demand + Update / Retry on a failed download | ✅ 2026-09-20 |
| 4d | **Run the other tools** (`runners.py`): one engine, one recipe each | ✅ 2026-09-22 |
| 4e | **TikTokDownloader by its local server** (it has no command line; data, not files — we fetch the file ourselves) | ✅ 2026-09-22/23, Douyin and TikTok |
| 5 | **Cookies (OFF by default)**: log in inside the app, or import a `cookies.txt` (decision 36) | ✅ 2026-09-22 |
| 5b | **Error messages, every tool**: 30 cases, 6 tools, `explain.py` with evidence | ✅ 2026-09-23. ⚠️ Open: true "no internet" not covered; a TikTokDownloader start failure other than curl's still waits 120 s (the step is shown). |
| 5c | **Kuaishou** (KS-Downloader) and the log-in window that finishes by itself, on all 23 sites | ✅ 2026-09-24. ⚠️ The automatic close with a real account seen only on Kuaishou. |
| 5d | 🚨 **Make the app usable and fluid** | ⏳ **in progress.** Last: 2026-10-31, impeccable 4.8.0 review loop **26 → 28 → 29/40**, then a silent-failure hunt **2 → 1 → 0 big** and its 18 small findings fixed. *(Console title aligned, Console palette in DESIGN.md and nested `.way` cards removed, 2026-10-31; every list row has one grammar — mark · format · name · status · one button · ⋯ — and under a card of several links the list shows all its rows, one scrollbar, 2026-11-01.)* **Not seen:** a real crash then restart · Douyin's automatic close on a real log-in · Stop during "Making the MP3" or the subtitle step · a real Stop on a TikTok / Kuaishou fetch. **What caps the review scores:** program names on the switch, "Best" without a number (both decided). |
| 6 | Build `Teleloadzai-setup.exe` + `Teleloadzai.zip`, publish on GitHub. The installer asks which sites and downloads their tools (decisions 5, 17), with a Retry; gallery-dl stays on demand. | ⏸ **not before 5d is finished**, and after Phase 2's functions (every function added after it means rebuilding and re-testing the installer). ⚠️ Known for it: DouK-Downloader asks Windows' firewall at first run — Block is fine and safer (Teleloadzai reaches it inside the PC); KS-Downloader will likely ask too. A click from Windows' notification list needs a registered app id, which the installer can give (item 6). |

### Phase 2 — inspiration, then advanced features

**The order** (the user's decision, 2026-10-21): explore similar apps → redesign once → add the chosen functions → the installer (step 6). **Nothing is built before the user's choice.**

- **The study** ✅ 2026-10-21 — `reports/Similar downloader apps study.md` (22 apps, 38 functions marked TAKE / LATER / NO). The user took the whole TAKE list.
- **Item 0, the update system** (decisions 8, 18, 19) ✅ 2026-10-21, with yt-dlp's preview channel (item 8).
- **The redesign** ✅ 2026-10-23, every choice made by the user from drawn models — recorded in `DESIGN.md`. Then ✅ 2026-10-25: **a menu on the left** (Download · Console · Programs · Sites, Settings at the bottom; the window opens maximized) and the **Console** page (programs' own words, washed, last 2,000 lines, memory only).
- **Item 1, several links at once** ✅ 2026-10-24 — one card, "Not added" with reasons, Download N, filters, Retry all failed. **"Same for all" / "Choose for each"** and YouTube playlists ✅ the same day. ⚠️ Not pressed: the Windows folder window itself; more than 50 links.
- **Item 2, a list that survives closing** ✅ 2026-10-24 — `data/jobs.json`, "Are you sure?" on close, interrupted rows and **Continue**. ⚠️ A download saved through "Save as" starts again from zero when continued (so "Continue", never "resume"). Not seen: an interrupted live recording.
- **Item 3, the copied link + a Paste button** ✅ 2026-10-24 — only links leave the clipboard (`server.clipboard_links`). ⚠️ Not seen in the real window: WebView2 telling the page "focus" when the window comes back.
- **Item 4, keyboard shortcut** ✅ 2026-10-24 — **Ctrl+Enter = Download, and nothing else** (the user's rule: *"no useless shortcuts"*).
- **Item 5, MP3 tags + cover art** ✅ 2026-10-24 — always on; a missing cover is said. ⚠️ Not run: Douyin, XHS-Downloader, streamlink, a live saved as MP3.
- **Item 6, a Windows message when downloads end** ✅ 2026-10-24 — a tray message named "Teleloadzai". ⚠️ A click from Windows' notification list does nothing (see step 6). Not seen: a real failed download's message.
- **Item 7, subtitles** ✅ 2026-10-25 — one link and "Choose for each". ⚠️ Not seen: a real Stop during the subtitle step; "Chosen for the subtitles" on a real card.
- **The Downloads list**: a finished row is one line (2026-10-24); failed rows grouped, one button each, the rest behind ⋯ (model D, 2026-10-25).
- **One row per video** ✅ 2026-11-01, from a drawn mock (the user: "always one video by one video") — a playlist, "Same for all" or "Choose for each", is one row per video under one label, every video; a post fetched whole by XHS-Downloader or gallery-dl becomes one row per file, only the first offering "Download the whole post again". The list keeps **500** rows (`jobs.HISTORY_LIMIT`, measured: 40 ms per update at 500). The folder window is Windows' modern one (`dialogs._PICK_FOLDER`). ⚠️ Not seen: a folder chosen by hand in the real window; a Retry of a post.

**Safety rule for this phase:** the "video downloader" category is full of adware.
- **Open source** → safe to install and to read the code.
- **Commercial / closed source** → screenshots, videos and documentation **only**. Never install.

Apps to study (open source): Parabolic (Nickvision), Open Video Downloader (jely2002), Tartube, MeTube, cobalt, Media Downloader, XDM / Motrix / Persepolis. Look only (do not install): JDownloader 2, 4K Video Downloader, IDM, Downie.

**Feature ideas still parked** (not approved): whole channels, subscriptions with auto-download, scheduler, speed limit, proxy, subtitle translation, SponsorBlock, cut a section (2:00 → 5:00), filename templates, "already downloaded" archive, batch import from a .txt file, history search.
