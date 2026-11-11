# Teleloadzai

> 🚧 **Still in development.** It runs and downloads, but there is no installer yet,
> and it has only been tested on one Windows 11 PC. Not ready for everyday use.

One desktop window for many video and audio download tools.
You paste a link; Teleloadzai finds the site, picks the right tool, and downloads the video (MP4) or the sound (MP3).

## Why

The best download tools are command-line programs, and each one is good at different sites:
yt-dlp for most of the web, other tools for Douyin, Kuaishou, Xiaohongshu, Bilibili, live streams...
Using them means knowing which tool fits which site, installing each one, and typing commands.
Teleloadzai does that part for you.

## What it does

- **Link → site → tool.** 23 sites are recognised (YouTube, Bilibili, TikTok, Douyin, Kuaishou, Xiaohongshu, Instagram, X, Twitch, SoundCloud and more). Unknown sites go to yt-dlp.
- **Manages the tools itself.** It installs, updates and removes the 9 tools it drives (yt-dlp, FFmpeg, gallery-dl, Streamlink, TikTokDownloader, XHS-Downloader, KS-Downloader, N_m3u8DL-RE, yutto), only when a site needs them.
- **A queue with real progress.** Percent, speed and time left when the tool gives them; otherwise the step being done. A task never looks frozen.
- **Errors explained, never hidden.** A failed download says what happened and offers a way out: update the tool, try another tool, or log in.
- **Several links at once**, playlists, subtitles, MP3 tags and cover art, a list that survives closing the app.

## Safety rules

- **No DRM.** Netflix, Disney+, Prime Video and Spotify are refused, permanently.
- **Cookies are off by default.** When a site needs an account, you log in inside Teleloadzai's own window; you never type a password into Teleloadzai itself. A cookie value is never logged, printed or uploaded.
- **The local server listens only on your own PC** (127.0.0.1), with a secret token on every call.

Downloading with your own account can get it suspended if you download a lot. Respect each site's terms and the creators' rights.

## Run it (developers)

Needs Windows and Python 3 (tested with 3.13).

```bash
pip install -r requirements.txt
python -m teleloadzai
```

Or double-click `Teleloadzai.bat`. The tools themselves are downloaded by the app, into its own `bin/` folder.

## Project files

- `CLAUDE.md`: the decisions, the rules and the roadmap.
- `docs/HISTORY.md`: what was tried, found and checked, step by step.
- `docs/BELIEFS.md`: what we rely on in other people's programs, with the evidence.
- `reports/`: studies and bug facts.

## How it was built

Built with [Claude Code](https://claude.com/claude-code) as a coding assistant. My part: the product decisions and rules, choosing and checking the tools, and testing every feature on real sites.

## Licence

MIT. See [LICENSE](LICENSE). The tools Teleloadzai downloads keep their own licences.
