# Bilibili AV1 cut — facts for the yt-dlp report

Collected 2026-11-09. **This is not the report.** yt-dlp forbids AI-written issues and comments (its NO AI / NO LLM policy, which the issue form makes you tick). Read these facts, check what is marked "your check", and write the report in your own words.

## What the problem is, in one line

When Bilibili's main server sends a broken file, yt-dlp fails, because it never tries the backup servers Bilibili lists for the same file. yutto tries them and gets the whole file.

## Where to report

- Repository: <https://github.com/yt-dlp/yt-dlp/issues/new/choose>
- Type: the form for **a broken supported site** ("I'm reporting that yt-dlp is broken on a supported site").
- Before posting, search again. Close cousins exist, but none asks for the backup servers:
  - **#17847**, HTTP 567 from the backup server `upos-sz-mirrorcosov.bilivideo.com` (the opposite side of the same list).
  - **#17894** / **#17879** / PR **#17898**, links with a language.

## The facts (all from this PC, Windows 11, region: your choice to say)

| What | Value |
|---|---|
| yt-dlp | nightly@2026.11.04.232659, win_exe; `-U` says "up to date" |
| Video | `https://www.bilibili.com/video/BV1Gsnj6XE9M` |
| Format that fails | **100026**: AV1 (`av01.0.08M.08`), 1920×1080, announced 23,632,722 bytes |
| Error | `Got error: 1432959 bytes read, 22199763 more expected` … `Giving up after 10 retries` |
| With or without cookies | fails both ways |
| Other formats of the same video | all 11 whole: H.264 / HEVC / AV1 at 360p, 480p and 720p, plus H.264 and HEVC at 1080p (checked with ffprobe) |
| Other videos | AV1 1080p whole on 3 other videos, so it is one file, not every video |
| How long | the same cut at 1,432,959 bytes was seen on **2026-10-25** and again on **2026-11-09** |

## Why it is the server, and why yt-dlp could still get the file

1. **The main server cuts the file without yt-dlp.** A plain HTTP GET of format 100026's URL, sent with yt-dlp's own headers (User-Agent, Referer), announced 23,632,722 bytes and ended after 1,432,959. A second try ended after 1,048,576.
2. **The backup server has the whole file.** The playurl answer (`data.dash.video[].backupUrl`) lists `upos-sz-mirrorcosov.bilivideo.com` for the same file:
   - without a `Range` header, it answers 567;
   - with `Range: bytes=0-`, it sends all 23,632,722 bytes.
3. **yt-dlp reads only `baseUrl`.** In `yt_dlp/extractor/bilibili.py` on master, `extract_formats` takes `'url': traverse_obj(video, 'baseUrl', 'base_url', 'url')`. `backupUrl` / `backup_url` is never read. PR #17898 does not change that.
4. **yutto 2.3.1 gets the file.** `yutto <url> -q 80 --vcodec av1:copy --video-only` with a log-in saved 23,634,898 bytes, and ffprobe reads 1920×1080, 257 s. Its code passes `backup_url` on as `mirrors`.

## How to reproduce (one line each)

```bash
yt-dlp -vU --no-cookies -f 100026 "https://www.bilibili.com/video/BV1Gsnj6XE9M"
```

```bash
yt-dlp --no-cookies -f 30077 "https://www.bilibili.com/video/BV1Gsnj6XE9M"
```

The first fails. The second (HEVC 1080p, same video) comes whole.

## The log the form asks for

`reports/Bilibili AV1 cut - yt-dlp verbose.log`: the full `-vU` output, made without cookies (no cookie in it, checked). Git ignores it (`*.log`), so it stays on this PC only. Paste it whole into the form's log box. It contains the signed download URL, which has no account in it because no cookies were used.

## Your checks before posting

- [ ] The video plays in your browser at 1080p, on the same internet connection (the form asks this).
- [ ] Run the first command again on the day you post: the cut may be gone by then.
- [ ] Search the issues once more for "backup" / "backupUrl".
- [ ] Write it in your own words: what fails, what you expected, and the facts above.
