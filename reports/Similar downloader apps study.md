# Popular downloaders point to eight missing basics

Popular downloader apps agree on a short list of things Teleloadzai does not have yet. They take **several links at once**, they **keep the list after the app closes** (history, and unfinished jobs brought back), they **take the link from the clipboard**, they **put tags and a cover in the MP3**, and they **say "done" with a Windows notification**. Most also offer **subtitles**. The big features are where popular apps get hurt: a **browser extension** (Google removed Downie's from the Chrome store, and XDM's is out of it today), **subscriptions** (4K Video Downloader had to check YouTube less often so users' IPs stopped being blocked), and **Bilibili extras** (DownKyi, 2.5 million downloads, closed after a lawyer's letter from Bilibili). Teleloadzai is already ahead on two points. It has an **in-app log-in**, and it **picks the tool for each site by itself**. No free app studied has the first: only the paid 4K Video Downloader logs in inside the app, as a paid feature. Only Media Downloader has several tools, with rules the user writes by hand. Popularity is local. **IDM** (21 million Chrome extension users) and **4K Video Downloader Plus** (13,216 Trustpilot reviews) own the Windows mass market. **Open Video Downloader** and **Parabolic** lead the free yt-dlp windows. **MeTube** is big only with self-hosters (people who run apps on their own server). **cat-catch** leads the browser and Chinese world. Nothing was built. The list at the end is for you to choose from.

Source notes: `research_notes/Similar downloader apps study/` (5 files, all read on 2026-10-21). Every number below was read by the researchers that day. No app was installed or run.

---

## 1. Who is popular, and where: 22 apps, measured in their own community

"Own community" means the place where that app's users really are. For Parabolic that is Flathub (the Linux app store). For IDM it is the Chrome extension store. For Downie it is Setapp (a Mac app subscription). AlternativeTo is a site where users "like" software. Its likes lean toward technical users.

| App | What it is | Alive? (last release) | Key number, in its own community | Verdict |
|---|---|---|---|---|
| **IDM** | paid download manager, Windows | ✅ 6.43 b15, 2026-10-08 | **21,000,000** Chrome extension users ([Chrome store](https://chromewebstore.google.com/detail/idm-integration-module/ngpampappnmepgilojfohadhhmbhlaek)) | **Mass market**, Windows worldwide. Every other app is compared with it. |
| **4K Video Downloader Plus** | paid video app (free: 10 videos a day) | ✅ 26.2, 2026-08-02 | **13,216** Trustpilot reviews, 4.6. The company invites them ([Trustpilot](https://www.trustpilot.com/review/4kdownload.com)) | **Popular with the general public**, Windows + Mac |
| **JDownloader 2** | free download manager (file hosts) | ✅ page updated 2026-09-04 | **1,316** AlternativeTo likes ([AlternativeTo](https://alternativeto.net/software/jdownloader/about/)) | **Popular** with heavy downloaders |
| **cat-catch** (猫抓) | browser extension that catches the video a page loads | ✅ 2.7.2, 2026-07-29 | **800,000** Chrome users, 4.6 ([Chrome store](https://chromewebstore.google.com/detail/cat-catch/jfedfbgedapdagkghmgibemcoggfppbb)) | **Popular**, worldwide and in China |
| **Open Video Downloader** | free yt-dlp window | ✅ 3.2.1, 2026-07-05 (rewritten 2025-12, after 4 silent years) | **124,265** real downloads of 3.2.1: Windows 54 %, Mac 28 % ([releases](https://github.com/jely2002/youtube-dl-gui/releases/tag/app-v3.2.1)) | **Popular**, Windows + Mac |
| **Parabolic** | free yt-dlp window | ✅ 2026.5.0, 2026-05-24 (quiet since June) | Flathub **466,510** installs, 15,765 last month ([Flathub](https://flathub.org/api/v2/stats/org.nickvision.tubeconverter)). GitHub: 140,355 for 2026.5.0, 88 % Windows | **Popular**: Linux first, Windows too |
| **MeTube** | self-hosted web page for yt-dlp | ✅ 2026.10.20 (almost weekly) | **52.2 M** Docker Hub pulls ([Docker Hub](https://hub.docker.com/v2/repositories/alexta69/metube/)). Only **5** AlternativeTo likes | **Popular with self-hosters only** |
| **cobalt** | website, "paste and get the file" | ⚠️ no commit since 2026-04-06; YouTube disabled on its main site | **45,322** stars, **104** AlternativeTo likes ([AlternativeTo](https://alternativeto.net/software/cobalt-co-wukko-me-/about/)) | **Popular with ordinary web users** |
| **Motrix** | free HTTP / torrent manager | 🟡 v2 betas daily; last stable 2023-05-03 | **57,180** stars; Flathub 159,286 ([Flathub](https://flathub.org/api/v2/stats/net.agalwood.Motrix)) | **Popular** with Chinese developers and on Linux. **Not a video tool.** |
| **Downie** | paid video app, Mac only | ✅ 4.13.3, Oct 2026 | **98 %** from 5,583 Setapp ratings ([Setapp](https://setapp.com/apps/downie)) | **Popular only on Mac** |
| **res-downloader** | proxy sniffer (catches media from all traffic) | 🟡 stable 2025-12-30, beta 2026-10-21 | **483,365** release downloads ([GitHub](https://github.com/putyy/res-downloader)) | **Popular in China** (WeChat Channels) |
| **wx_channels_download** | proxy for WeChat Channels | ✅ v260907, 2026-09-07 | **284,269** release downloads ([GitHub](https://github.com/ltaoo/wx_channels_download)) | **Popular in China**, WeChat only |
| **TikTokDownloader** | terminal + local server (we drive it) | ✅ 5.8, 2026-09-13 | **17,030** stars, 128,277 downloads ([GitHub](https://github.com/JoeanAmier/TikTokDownloader)) | **Popular on GitHub**, power users |
| **XHS-Downloader** | terminal (we drive it) | ✅ 2.8, 2026-09-12 | **13,083** stars, 92,821 downloads ([GitHub](https://github.com/JoeanAmier/XHS-Downloader)) | **Popular on GitHub**, power users |
| **Douyin_TikTok_Download_API** | self-hosted API + web console | ✅ v5.1.7, 2026-10-21 | **20,821** stars ([GitHub](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)) | **Popular with developers** |
| **DownKyi** (+ DownKyiCore) | Bilibili window | ⛔ **closed 2026-07-06** after Bilibili's lawyer letter | **2,495,929** downloads, all time ([GitHub](https://github.com/leiurayer/downkyi)) | **Was** the most popular Bilibili app |
| **XDM** | free download manager + video popup | 🟡 v9 pre-release 2026-10-19; last stable **2020** | 4.0 M downloads of the 2020 build; no Chrome extension in the store today ([GitHub](https://github.com/subhra74/xdm)) | **Popular in the past** (free IDM, India first). Unproven today. |
| **BilibiliDown** | Bilibili window | 🟡 V6.41, 2026-04-24; code branch renamed "deleted" | 195,219 downloads ([GitHub](https://github.com/nICEnnnnnnnLee/BilibiliDown)) | **Mid**, Bilibili users. Its future is unclear. |
| **Tartube** | yt-dlp window for following channels | 🟡 v2.5.231, 2026-05-24 | **53,939** SourceForge downloads in 12 months, 81 % Windows ([SourceForge](https://sourceforge.net/projects/tartube/files/stats/json?start_date=2025-10-21&end_date=2026-10-20)) | **Niche**: Windows channel followers |
| **Media Downloader** | window with 8+ engines | ✅ 5.6.6, 2026-09-09 | **26,133** downloads of 5.6.6: 95 % Windows, 32 % on Windows 7 / 32-bit ([release](https://github.com/mhogomchungu/media-downloader/releases/tag/5.6.6)) | **Niche**: Windows power users |
| **Persepolis** | download manager + yt-dlp "Video Finder" | 🟡 5.2.0, 2025-07-14 | 88,504 downloads of 5.2.0 ([GitHub](https://github.com/persepolisdm/persepolis/releases)) | **Niche**: Persian community + Linux |
| **KS-Downloader** | terminal (we drive it) | ✅ 1.6, 2026-07-05 | 881 stars, 9,790 downloads ([GitHub](https://github.com/JoeanAmier/KS-Downloader)) | **Niche** |

Dropped after a check: **BBDown** (archived), **lux** (no release since 2024-05), **bilix** (2024-09), **N_m3u8DL-CLI-SimpleG** (dead since 2022).

**How the weight works below.** For Teleloadzai (a Windows desktop app), the apps that count most are IDM, 4K, Open Video Downloader, Parabolic and JDownloader. The Chinese tools count most for Douyin, Kuaishou and Xiaohongshu. Motrix's fame is about torrents, not video, so it counts little on video functions. Tartube's numbers are the closest to what Teleloadzai can hope for at first.

---

## 2. The functions: 38 rows, and one decision each

**Short names.** IDM · **4K** · **JD** JDownloader · **OVD** Open Video Downloader · **PB** Parabolic · **MT** MeTube · **CB** cobalt · **DW** Downie · **CC** cat-catch · **RD** res-downloader · **WX** wx_channels_download · **TTD** TikTokDownloader · **XHS** · **DTA** Douyin_TikTok_Download_API · **DK** DownKyi · **MX** Motrix (popular, not for video) — niche: **MD** Media Downloader · **TT** Tartube · **PS** Persepolis · **XDM** · **BD** BilibiliDown · **KS**.

**Cost.** "cheap (notes)" or "big (notes)" = the researchers' own estimate. "est." = my estimate, not measured.

### 2a. Getting links in

| Function | Popular apps that have it | Niche apps that have it | Decision | Why (one line) | Cost |
|---|---|---|---|---|---|
| Several links at once (paste many, or import a .txt) | PB, OVD, MT, IDM, JD, MX, TTD | MD, TT, PS, XDM | **TAKE** | Every popular yt-dlp window has it. It is the base the playlist and "retry all" features need. | cheap (notes) |
| Link from the clipboard: fill the box when the window comes to the front, plus a **Paste** button | OVD (on by default), 4K "Paste Link", CB paste button | PS, XDM, MD | **TAKE** | One click less on every download. Read only when the window is in front, never stored or logged (a clipboard can hold a password). | cheap (notes) |
| Background clipboard watching (adds downloads by itself) | JD (on by default), OVD (3.2.1), TTD, XHS | MD, TT, PS (opt-in, off by default) | **LATER** | Useful with many links. It reads the clipboard all the time, so it needs its own switch, off by default. | cheap (notes) |
| Keyboard path: Enter downloads, a key for MP3 / MP4, shortcuts written on the buttons | CB (Shift+D paste, Shift+J/K/L modes), PB, 4K (26.2 shows shortcuts in menus) | — | **TAKE** | Your own reviews list "a Download shortcut" as missing. In-app keys only. | est. cheap |
| Global hotkey (works when the app is hidden) | OVD (Alt+Shift+V / D) | — | **LATER** | Only one app, and it got a bug report: "Auto-Download Hotkey Causes D/L Failures" ([#870](https://github.com/jely2002/youtube-dl-gui/issues/870)). | est. medium |
| "Smart Mode": remember my choices, paste = download starts | 4K, CB (a link in the address starts at once), DW (Cmd+V starts) | — | **LATER, discuss first** | The most praised idea in 4K. But it skips the card that says what a link needs **before** Download (decision 40). | cheap (notes) |
| Browser extension that sends the page to the app | IDM, JD, PB, MX, DW, MT (by others), XHS (user script) | XDM, PS | **NO** | The most fragile part of the field. Google removed Downie's Chrome extension, "as it did with any YouTube downloading extension" ([Downie blog](https://blog.charliemonroe.net/downie-and-chrome)). XDM's extension is out of the store. Our server also refuses outside callers on purpose (decision 21). | **big (notes)** |
| Built-in browser: open an unknown site, press Play, catch the video | DW (User-Guided Extraction), 4K (in-app browser), CC, IDM panel | XDM | **LATER** | Our log-in window is already a small browser, so it is a natural next step. cat-catch's most-commented request asks for exactly this ([#635](https://github.com/xifangczy/cat-catch/issues/635)). It must refuse encrypted streams (hard rule 2). | est. big |
| Proxy + root certificate sniffer (WeChat Channels, mini-programs) | RD, WX | — | **NO** | A root certificate (it lets a program read all your encrypted web traffic), Administrator rights, and a system proxy that cuts the internet if the app closes badly ([RD #18](https://github.com/putyy/res-downloader/issues/18), 27 comments). Keep "explain, do not run". | big |

### 2b. What gets downloaded

| Function | Popular apps that have it | Niche apps that have it | Decision | Why (one line) | Cost |
|---|---|---|---|---|---|
| Playlists / channels / a whole account | PB, OVD, MT, 4K, JD, TTD, DTA, DK | MD, TT, BD | **LATER (right after several links)** | Wanted everywhere: cobalt's 2nd most-asked feature ([#193](https://github.com/imputnet/cobalt/issues/193), 26 reactions). It reuses "several links", so it comes after it. | est. big |
| Subscriptions (new uploads download by themselves) | MT, 4K (paid), DTA | MD, TT | **LATER** | Needs the app open all day. Checking too often gets the user's IP blocked: 4K had to slow its checks ([TidBITS](https://tidbits.com/watchlist/4k-video-downloader-plus-26-2/)). | **big (notes)** |
| Subtitles (one language setting) | PB, OVD, MT, CB, 4K, JD | MD, TT, BD, DK | **TAKE** | All popular yt-dlp windows have it, and cobalt added it after 18 reactions. Shown only for the tools that really do it (decision 40). Not for Bilibili. | est. cheap for yt-dlp |
| SponsorBlock (cuts the sponsor parts of YouTube videos, from a shared list) | PB, OVD, MT | TT, MD (typed) | **LATER** | Cheap, but YouTube only. Our users' sites are wider. | est. cheap |
| Cut a section (2:00 → 5:00) | PB, OVD, MT | MD, TT | **LATER** | Asked a lot (cobalt [#128](https://github.com/imputnet/cobalt/issues/128), 29 reactions), but fragile: Parabolic's cut broke and is still open ([#1906](https://github.com/NickvisionApps/Parabolic/issues/1906)). | est. medium |
| Choose the audio track / dub language | 4K (dubs as separate files) | — | **LATER** | Asked in 2026 in two apps (MD [#750](https://github.com/mhogomchungu/media-downloader/issues/750), 27 comments; OVD [#885](https://github.com/jely2002/youtube-dl-gui/issues/885)). | est. medium |
| "Phone-friendly" MP4 / repair a file's container | CB (Remux tab), OVD (WhatsApp mode after 49 comments, [#710](https://github.com/jely2002/youtube-dl-gui/issues/710)) | — | **LATER** | Teleloadzai already gives a real .mp4. Wait until a user meets the problem. | est. medium |
| Bilibili extras: 8K, HDR, Dolby, paid streams, danmaku (on-screen comments) | DK (closed) | BD | **NO** | This is word for word the list in Bilibili's lawyer letter that closed DownKyi on 2026-07-06 ([DownKyi README](https://github.com/leiurayer/downkyi)). | — |
| Video "mute" mode (picture without sound) | CB | — | **NO** | Nobody asks for it in the notes. | — |

### 2c. Files and naming

| Function | Popular apps that have it | Niche apps that have it | Decision | Why (one line) | Cost |
|---|---|---|---|---|---|
| MP3 tags + cover art, on by default | PB, OVD, MT, CB | TT (partly) | **TAKE** | Both "paste and get" leaders (cobalt, MeTube) do it by default. MeTube's tip: turn the cover into a JPG first, or embedding fails on WebP ([MeTube wiki](https://github.com/alexta69/metube/wiki/YTDL_OPTIONS-Cookbook)). | est. cheap for yt-dlp |
| File-name styles or templates | OVD, MT, CB (4 styles with a preview), XHS | MD, TT, KS | **LATER** | Our "Save as" already lets the user type the name. That answers the request MeTube users have made since 2021 ([#56](https://github.com/alexta69/metube/issues/56)). If wanted later, use cobalt's simple form: a few styles with a preview. | cheap (notes) |
| "Already downloaded" record (an archive: a list of what was taken) | TTD, XHS, DTA, MT (option), DW (history) | MD, TT, KS | **LATER** | Needed only for playlists and channels. "Already there" covers one link. Don't repeat the message: BilibiliDown users asked how to stop that popup ([#6](https://github.com/nICEnnnnnnnLee/BilibiliDown/issues/6)). | cheap (notes) |
| Categories / sub-folders by type, several queues | IDM | XDM, PS | **NO** | Only general download managers have it. No yt-dlp window does. | — |

### 2d. The queue

| Function | Popular apps that have it | Niche apps that have it | Decision | Why (one line) | Cost |
|---|---|---|---|---|---|
| History of finished downloads (kept after closing; search later) | PB (+ search), MT, DW, 4K (sort, filter, export) | MD (since 2026-09), TT | **TAKE** | Today our list is forgotten when the app closes. | cheap (notes) |
| Unfinished jobs brought back at start, with a count | PB ("Recover Downloads?"), MX ("N recovered"), IDM | XDM | **TAKE** | Asked again in Oct 2026 (PB [#1982](https://github.com/NickvisionApps/Parabolic/issues/1982)). Matches decision 34: nothing lost in silence. | cheap (notes) |
| "Are you sure?" when closing during a download | — | MD request ([#804](https://github.com/mhogomchungu/media-downloader/issues/804)) | **TAKE** | Only a niche app's users asked, but it costs one dialog and protects running jobs. | est. cheap |
| Status filters with counts + "Retry all failed" + total progress | PB, OVD, MT, MX | MD (asked, [#462](https://github.com/mhogomchungu/media-downloader/issues/462)) | **TAKE (with several links)** | Needed the day several links exist. PB's filters with counts keep a long list readable. | est. cheap |
| Windows notification when done (+ progress on the taskbar icon) | OVD (+ icon badge), MX | MD, XDM, PS | **TAKE** | You can leave the window. Motrix users ask for taskbar progress too ([#2309](https://github.com/agalwood/Motrix/issues/2309)). | cheap (notes) |
| Pause / resume | PB, OVD, JD, IDM, MX | XDM | **LATER** | Stop exists. Resume works differently in each tool, so each tool must be seen resuming first (decision 40). | est. medium |
| Speed limit | PB, IDM, JD, MX | TT, XDM, PS | **LATER** | Open Video Downloader dropped it in v3. A limit left on by mistake looks like a broken app (an IDM user stuck at 25 KB/s, [forum](https://forums.tomsguide.com/faq/download-speed-doesn%E2%80%99t-exceed-25kbps-in-internet-download-manager.337985)). | est. cheap for yt-dlp |
| Keep the PC awake / shut down when done | PB (prevent sleep), IDM, JD (add-on) | XDM, PS | **LATER** | Cheap, but mainly a download-manager habit. | cheap (notes) |
| Scheduler (start at a set time) | IDM, JD (add-on) | TT, XDM | **NO** | None of the yt-dlp windows has one. It is the least proven idea on our Phase 2 list. | — |
| Several connections per file (faster) | IDM, PB (aria2 option) | XDM, PS | **NO** | Speed is not what users complain about. Their complaints are sites breaking. | — |

### 2e. Settings and tools

| Function | Popular apps that have it | Niche apps that have it | Decision | Why (one line) | Cost |
|---|---|---|---|---|---|
| yt-dlp "preview" (nightly) channel, opt-in | PB ("Allow preview updates"), MT (nightly at a set hour) | MD (extension) | **TAKE, as a switch off by default** | This answers our open question in §6. Nightly gets fixes for broken sites days earlier, and "the site broke" is the top complaint everywhere. | est. cheap |
| Proxy setting inside the app | PB, OVD, 4K, IDM, MX, TTD | XDM, PS | **LATER** | Our tools already follow the PC's proxy (our own error texts name it). A second proxy setting is a second place to break. | est. cheap |
| Saved username / password per site (a "keyring") | PB, OVD | — | **NO** | Decision 9: the user never types a password into Teleloadzai. | — |
| Remote control from a phone | JD (my.jdownloader.org), MT, DTA | — | **NO** | Decision 21: the server answers this PC only. | — |
| Per-site status ("TikTok is broken for everyone right now") | DTA (live health), MT (pinned known issue) | — | **LATER** | Asked for in cobalt ([#1389](https://github.com/imputnet/cobalt/issues/1389), 16 reactions), but it needs an online source we don't have. | est. big |
| Data export, comments, speech-to-text, AI vocal removal | TTD, DTA, 4K (paid AI) | MD (comments) | **NO** | Not downloading. Out of scope. | — |

**What Teleloadzai already does better** (no change needed):
- **In-app log-in.** Parabolic **removed** browser cookies on Windows in 2026.4.0 ("manual txt files should be used instead", [release](https://github.com/NickvisionApps/Parabolic/releases/tag/2026.4.0)). Tartube cannot read Chrome or Edge cookies. MeTube needs an exported file. cobalt has no user log-in at all. The four download managers borrow the browser's cookies or ask for a password. Only the paid 4K Video Downloader has an in-app browser with a log-in, and "private content download is a premium feature" ([4K](https://www.4kdownload.com/products/videodownloader-42)).
- **The tool is chosen for each site automatically.** Media Downloader has 8+ engines, but the user writes the URL rules by hand ([FAQ](https://github.com/mhogomchungu/media-downloader/wiki/Frequently-Asked-Questions)).
- **"Already there — nothing was downloaded", in plain words.** No studied app was seen doing that. Users of other apps ask for both sides: skip it, or download it again (MD [#366](https://github.com/mhogomchungu/media-downloader/issues/366)).

---

## 3. Design: cobalt's one box wins, Media Downloader's raw log loses

⚠️ **Screenshots:** only the Parabolic, Open Video Downloader and Media Downloader screenshots were looked at by the researchers. The other links come from the notes and were **not opened**. Those design lines come from text: READMEs, manuals, reviews.

| App | Main screen in one line | Works | Does not work | Screenshot |
|---|---|---|---|---|
| **cobalt** | One box, one Paste button, three modes under it (auto / audio / mute). Everything else is in Settings. | Errors as one sentence: cause + next step. An unknown error is said as unknown ([error texts](https://github.com/imputnet/cobalt/blob/main/web/i18n/en/error/api.json)). This is our decision 38 already. | A site that is down is **hidden** from the list, so users do not notice it is missing ([#1389](https://github.com/imputnet/cobalt/issues/1389)). | none in the repo; live page [cobalt.tools](https://cobalt.tools/) |
| **4K Video Downloader Plus** | Toolbar (Paste Link, Smart Mode bulb, browser) over one list of downloads. | "Simple copy-and-paste workflow". Shortcuts shown in every menu. | Free limit of 10 a day; paid walls. | [product page](https://www.4kdownload.com/products/videodownloader-42) |
| **Downie** | One list, a "+" button; Cmd+V or drag a link onto it. | "Simple for novices, useful to power users". | "Somewhat technical at first". Mac only. | [official page](https://software.charliemonroe.net/downie/) |
| **Open Video Downloader** | Link box on top, one card per video with its own format and quality, a fixed Download bar at the bottom. | Closest to our shape. Fits several links. | Many icons without labels. Only 1 download at a time by default. | [screenshot.png](https://raw.githubusercontent.com/jely2002/youtube-dl-gui/main/docs/img/screenshot.png) (Mac) |
| **Parabolic** | Filters on the left (All / Running / Queued / Completed / Failed, with counts), download rows on the right. | The filters with counts; "Retry All Failed" in one click. | Every link goes through a dialog full of dropdowns: more clicks than our card. | [Downloading.png](https://raw.githubusercontent.com/NickvisionApps/Parabolic/main/Nickvision.Parabolic.WinUI/Screenshots/Downloading.png), [AddDownloadDialog.png](https://raw.githubusercontent.com/NickvisionApps/Parabolic/main/Nickvision.Parabolic.WinUI/Screenshots/AddDownloadDialog.png) |
| **MeTube** | One long page: link box + Download / **Subscribe** split button, folding Advanced Options, then the lists. | A help bubble on each advanced field. "Copy error details" on a failed row. The form only offers what the server knows (our decision 40). | Users ask for control over files: rename, folder, do not delete. | [screenshot.gif](https://github.com/alexta69/metube/raw/master/screenshot.gif) |
| **JDownloader 2** | Two tabs full of tables: LinkGrabber (found links), then Downloads. | Strong with hundreds of links. | Feels technical; heavy memory use; adware in old installers. | [jdownloader.org](https://jdownloader.org/) (Screenshots page not opened) |
| **IDM** | A table of downloads + categories; a "Download this video" panel drawn on web players. | Defines the genre. | The panel often does not appear: its own most common support topic ([FAQ](https://internetdownloadmanager.com/register/new_faq/video1.html)). | [main](https://www.internetdownloadmanager.com/images/idm_screenshot_6_35.png), [panel](https://www.internetdownloadmanager.com/images/idm_download_video_animation-4.gif) |
| **Motrix 2** | A Dashboard of tiles + a Downloads list with a detail panel. | A failure shows "a plain-language reason and a suggested fix". Delete keeps the file by default. | Speed and time left freeze for seconds ([#2315](https://github.com/agalwood/Motrix/issues/2315)): our decision 33's defect. | [downloads](https://raw.githubusercontent.com/agalwood/Motrix/main/screenshots/motrix-downloads-en-light.webp) |
| **XDM** | Downloads list, a "New download" dialog, one progress window per download. | The quality popup on a playing video. | "The interface should be redesigned" (open since 2019). | [img1.png](https://raw.githubusercontent.com/subhra74/xdm/master/screenshots/img1.png) |
| **Persepolis** | Menu + toolbar, side panel of queues, a table, one progress window per download. | Video Finder picks the best quality by default (like our "Best"). | Users report corrupted files and crashes on 5.2.0 ([#1133](https://github.com/persepolisdm/persepolis/issues/1133)). | [windows.png](https://persepolisdm.github.io/img/screen/windows.png) |
| **Tartube** | Tree of channels, a video grid, five tabs. | Powerful for channels. | It needed a separate "Classic Mode" because the main mode is too much. On Windows, button text shows only on hover. | [screenshot.png](https://github.com/axcore/tartube/raw/master/screenshots/screenshot.png) |
| **Media Downloader** | Tabs; the main tab is a big raw log + a free-text "options" box. | Everything is reachable. | A raw log and typed yt-dlp options: the opposite of our plain words. | [media-downloader-1.png](https://raw.githubusercontent.com/mhogomchungu/media-downloader/main/images/media-downloader-1.png) |
| **cat-catch** | A popup listing the page's files. | Works on any site the browser opens. | Merge failures; fake copies with ads in the stores. | [popup.png](https://raw.githubusercontent.com/xifangczy/cat-catch/master/README/popup.png) |
| **res-downloader** | "Start proxy" button + a type picker + the captured list. | One button. | The PC stays offline if the proxy is left on. | [show.webp](https://raw.githubusercontent.com/putyy/res-downloader/master/docs/images/show.webp) |
| **wx_channels_download** | A terminal + a Download button injected into WeChat itself. | The button is where the user already is. | Certificate problems: its top issue, 36 comments. | [screenshot1.png](https://raw.githubusercontent.com/ltaoo/wx_channels_download/master/docs/assets/screenshot1.png) |
| **TikTokDownloader / XHS / KS** | Numbered terminal menus. | — | No window at all (TikTokDownloader plans one for 6.0). | [TTD](https://raw.githubusercontent.com/JoeanAmier/TikTokDownloader/master/docs/screenshot/终端交互模式截图CN1.png) |
| **Douyin_TikTok_Download_API v5** | Web console: overview, accounts, scheduler, library. | Live health for each account and endpoint. Its own words: v4's API "would die quietly and nobody would know" ([README](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)). | Not for end users. | [console-en.gif](https://raw.githubusercontent.com/Evil0ctal/Douyin_TikTok_Download_API/main/screenshots/console-en.gif) |

**Five quick design lessons for Teleloadzai:**
1. **One way in, choices remembered.** Reviewers praise 4K and Downie for this. Our card asks each time.
2. **Several links must not create a second list.** JDownloader's "found links → downloads" is what makes it feel technical.
3. **A long list needs filters with counts** (Parabolic), and a total progress (Media Downloader's users asked for it).
4. **Never hide a broken site** (cobalt #1389). Say it, as MeTube's pinned issue does: "It is not a MeTube bug and it is not your cookies" ([#1066](https://github.com/alexta69/metube/issues/1066)).
5. **Say each setting's cost in its label.** cobalt does it: the MP3 setting says "there will be some quality loss".

---

## 4. Warnings for later steps

| Warning | Seen where | What it means for us |
|---|---|---|
| **Fake download sites** | A fake **tartube.org** put a malicious PowerShell command in the clipboard ([#797](https://github.com/axcore/tartube/issues/797)). Attackers changed JDownloader's download links in May 2026 ([Gridinsoft](https://blog.gridinsoft.com/jdownloader-site-malware-installer-links/)). Fake cat-catch copies with ads are in the stores. | Step 6: name **one** official place in the README from day one, publish SHA-256 hashes (JDownloader does), sign the installer. |
| **Antivirus at first run** | Media Downloader is flagged by Windows Defender (false positive). Open Video Downloader's top error: "disable antivirus" (16 reactions) and "Binaries missing" ([#362](https://github.com/jely2002/youtube-dl-gui/issues/362)). "Fails to download yt-dlp on first run" (MD, 20 comments). Motrix is unsigned, so SmartScreen warns. | Our installer will download tools too (decision 17). Plan the message for a blocked tool before it happens. |
| **Sites breaking** | YouTube 403s in every app (MeTube [#1066](https://github.com/alexta69/metube/issues/1066), 31 reactions). cobalt's main site cannot download YouTube at all ([#1356](https://github.com/imputnet/cobalt/issues/1356), 144 reactions). 4 of IDM's last 5 builds fix 403s or broken video/audio joining. | "Update first" advice (decision 8) matches the real pain. The preview channel helps. |
| 🚨 **Our own engine for Douyin may stop being fixed** | TikTokDownloader: "to keep the project legal, the encryption-parameter algorithm is no longer maintained" ([README](https://github.com/JoeanAmier/TikTokDownloader)). | If Douyin changes its signing, our Douyin download can break with no fix coming from upstream. |
| **Bilibili is legally hostile** | DownKyi and DownKyiCore closed (2026-07-06). bilibili-API-collect closed (2026-01-28). BBDown archived. BilibiliDown's branch is renamed "deleted". | Bilibili stays on yt-dlp only. No Bilibili-specific features. |
| **Stores refuse YouTube downloaders** | Chrome removed Downie's extension. Apple's Mac App Store refuses YouTube downloaders. Open Video Downloader's README advises **against** its own Microsoft Store build (slower updates, no automatic yt-dlp update). | Ship on GitHub (decision 11). Do not plan on a store. |
| **Too many downloads at once** | Media Downloader warns that too many "may cause the host to ban you". | Keep our 1-5 limit. |
| **Portable vs installer updates** | Parabolic: "Portable version is trying to install Installer version" ([#1983](https://github.com/NickvisionApps/Parabolic/issues/1983)). Media Downloader users prefer portable 3 to 1. | Decision 16 ships both: each one must update itself as itself. |
| **Rewrites and silences** | Open Video Downloader was silent for 4 years ("This repo is dead", 41 reactions), and its v3 says "some older features may be missing". XDM and Motrix had the same gap. | Say the project's status plainly in the README. |

---

## 5. What was NOT measured

- **Reddit.** Not measured at all. Reddit refused automatic reads (HTTP 403), and searches returned no Reddit page. The only "Reddit" lines come from SEO blogs that sum up Reddit. They say yt-dlp is first, and 4K is "Reddit's go-to desktop application" ([joinotto](https://joinotto.com/blog/youtube-video-downloader-reddit/)). Not checked.
- **Real user counts.** None can be worked out from the numbers above:
  - Download counts include automatic updates. Open Video Downloader's `latest.json` was fetched 488,137 times, and it was removed from the count.
  - Docker pulls are not installs.
  - 4K's "11 million" counts all of its apps together.
  - IDM's "30 million" is the company's own claim.
- **Chinese forums.** V2EX, 52pojie, Zhihu answer counts and Bilibili video views were not measured. The search tool is US-based, so few hits is a tool limit, not proof.
- **Not confirmed:**
  - the MyJDownloader Chrome count (400,000 or 800,000: two snapshots disagree);
  - IDM's Edge count and its price in dollars;
  - Trustpilot for JDownloader and Downie;
  - cobalt.tools traffic (not published);
  - winget and Microsoft Store counts (not public).
- **Functions are claims, not seen.** No app was run. Every "has it" comes from code, docs or release notes. XDM 9 is two weeks old and unproven. Some absences are "not found", not proven: Parabolic's clipboard, IDM's clipboard, 4K's notifications. Some JDownloader and Downie features were remembered but not sourced, so they were left out.
- **Screenshots.** Only three apps' screenshots were looked at (section 3).
- **Teleloadzai's side.** Not checked:
  - whether pywebview can show a Windows notification, set taskbar progress, or read the clipboard;
  - the "queue forgotten at close" line in `jobs.py` (it comes from the brief).

  Checked: the page has no clipboard code, no notification code and no keyboard shortcut code. It already follows the Windows dark mode (one `prefers-color-scheme` rule in `teleloadzai/web/index.html`, searched 2026-10-21).

---

## Conclusion

Popular apps win on boring things. Users keep them for the queue around the download: several links, a list that survives closing, a sound when it's done. Their engines are mostly the same yt-dlp. The features that hurt popular apps are the ones that depend on **somebody else's gate**: a browser store (Downie, XDM), YouTube's patience (4K's subscriptions, cobalt's main site), or a platform's lawyers (DownKyi). Teleloadzai's in-app log-in and automatic tool choice are rare, and worth keeping in front. The real new risk this study found is upstream: one of our own engines, TikTokDownloader, has stopped maintaining the part that keeps Douyin working.

## The TAKE short-list (for you to choose; nothing is built)

In the order I would do them. Each one makes the next one easier.

1. **Several links at once** (paste many lines, or a .txt), with status filters + counts, "Retry all failed" and a total progress.
2. **A list that survives closing**: history of finished downloads, unfinished jobs brought back at start ("2 downloads recovered"), and "Are you sure?" when closing during a download.
3. **Link from the clipboard**: fill the box when the window comes to the front, plus a Paste button.
4. **Keyboard path**: Enter downloads, a key for MP3 / MP4, shortcuts written on the buttons.
5. **MP3 tags + cover art**, on by default.
6. **Windows notification when a download ends** (and progress on the taskbar icon, if pywebview allows it).
7. **Subtitles**: one language setting, shown only for the tools that really do it.
8. **yt-dlp preview channel**: a switch, off by default. It closes the open question of §6.

Next after these: **playlists and channels** (LATER, the first big one). Discuss first: **Smart Mode**, because it collides with decision 40.
