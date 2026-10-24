# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(One HTML page, `teleloadzai/web/index.html`, shown in a pywebview window with WebView2 on Windows 10/11. Not a browser tab for the user. Minimum window 520×560, opens at 860×900 when it fits, else at the free space above the taskbar (860×846 on the user's PC, 175 % scaling), can go full screen.)

## Users

Everyday Windows users who are **not technical** (confirmed by the user, 2026-10-21). They paste a link from a site they use — YouTube, TikTok, Douyin, Bilibili, Instagram, Xiaohongshu, Kuaishou, Weibo… — and want the video or the sound as a file. They may never have heard the word "cookie" and must still be able to decide (CLAUDE.md decision 35). The developer reads English as a second language: every word on screen is simple English, short sentences.

## Product Purpose

One window that groups the best download programs behind a single box. The user pastes a link; Teleloadzai finds the site, picks the right tool, and says plainly what will happen before Download. Success: the file the user wanted is in the folder, and the app never claims a success that did not happen.

## Positioning

- It **chooses the tool for each site by itself** (yt-dlp, gallery-dl, streamlink, N_m3u8DL-RE, TikTokDownloader, KS-Downloader, XHS-Downloader), where other apps drive one engine or make the user write rules.
- It **logs in inside the app** (one site's cookies only), where free apps ask for an exported file or a password.
- It **manages its own tools**: install, update, "Update and retry".
- It speaks in plain sentences: what happened, and what to do — and says "unknown" when it does not know (decisions 33, 34, 38).

## Operating Context

The main moment (confirmed 2026-10-21): **paste one link, get it.** The downloads list comes second. A session: paste a link → a card shows the title, the picture, MP4 / MP3, the quality the video really has, the tool (a switch with program names, decided — decision 13) → Download → a row with real progress (size, speed, time left), Stop, then Open / Show in folder. Settings: download folder, "Save as" window on/off, downloads at once, live recording limit, tool per site, Installed programs (update mode, yt-dlp version), Accounts (log in per site, import a cookie file, forget).

## Capabilities and Constraints

- Standard library only, one HTML file, no framework, no build step (decision 20). Fonts and assets must be local or system (no network at run time for the UI).
- Every button, list and switch has a real action seen working (decision 40); only real choices are shown.
- A task never looks frozen (decision 33); a problem is always said (decision 34).
- **Built 2026-10-24:** several links at once — one paste, one card, one folder window; status filters with counts, "Retry all failed", a total ("5 of 8 finished").
- **Built 2026-10-24:** a list that survives closing — the last 200 rows come back; downloads cut off by closing come back interrupted and wait for "Continue"; closing during a download asks first.
- **Chosen to come after the redesign (2026-10-21), still to build:** the link from the clipboard + a Paste button; keyboard shortcuts written on buttons; MP3 tags + cover art; a Windows notification; subtitles. The design must give them their place from the start.
- No DRM sites, ever. No browser extension (the stores refuse YouTube downloaders).

## Brand Commitments

- Name: **Teleloadzai** (lives in one config constant; injected as `__APP_NAME__`).
- Voice: direct, plain, honest; never a guessed cause; never "done" for nothing.
- No logo or palette is binding: the user asked for a **total change of the look, "more comfortable"** (2026-10-21).

## Evidence on Hand

- The study `reports/Similar downloader apps study.md` (22 apps, popularity, design lessons: cobalt's single box, 4K's remembered choices, Parabolic's filters with counts; no second "found links" list).
- No users' testimonials, no download numbers of Teleloadzai itself: none may be invented.

## Product Principles

1. Paste and know: before Download, the user already knows what he will get and what is missing.
2. The truth on screen: real numbers, real states, the tool's own words folded under plain ones.
3. One way in: one box; choices are remembered, not asked again and again.
4. Calm under failure: every failure ends on one clear way out.

## Accessibility & Inclusion

Keyboard focus visible on every control; text contrast at least 4.5:1 (checked in past reviews); dark mode follows Windows; screen-reader announcements for finished / failed downloads (already in place).
