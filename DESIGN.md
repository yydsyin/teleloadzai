---
name: Teleloadzai
description: Paste a link, get the file — every download a parcel you can track.
colors:
  paper: "#ebe5d8"
  card: "#fffdf9"
  ink: "#24221e"
  soft-ink: "#625b4f"
  line: "#e2d8c4"
  line-strong: "#cfc3ab"
  ochre: "#7d5d00"
  ink-fill: "#2e2b26"
  on-fill: "#fffdf8"
  go-yellow: "#f5c400"
  go-yellow-hover: "#e6b700"
  go-ink: "#1d1b17"
  ok-green: "#2f7a4f"
  bad-red: "#b03a2e"
  paper-dark: "#161513"
  card-dark: "#25231f"
  ink-dark: "#ede8dd"
  soft-ink-dark: "#aaa293"
  line-dark: "#3a3630"
  line-strong-dark: "#4e483f"
  ochre-dark: "#e3bb4f"
  ok-green-dark: "#5cc28a"
  bad-red-dark: "#f07a6a"
  ink-fill-dark: "#ede8dd"
  on-fill-dark: "#1b1a17"
  visit-blue: "#2f5f9e"
  visit-blue-dark: "#8fb3e8"
  console-box: "#1d1f24"
  console-text: "#d8d4cb"
  console-time: "#868c96"
  console-link: "#84b6ff"
  console-error: "#ff8f80"
  console-end: "#a3a9b3"
typography:
  pane-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  screen-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  section-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  list-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
  control-small:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
  help:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  thumb: "6px"
  segment: "7px"
  control: "8px"
  band: "10px"
  card: "12px"
  pill: "99px"
spacing:
  gutter: "16px"
  card-padding: "16px"
  card-gap: "14px"
  row-gap: "12px"
components:
  button-download:
    backgroundColor: "{colors.go-yellow}"
    textColor: "{colors.go-ink}"
    rounded: "{rounded.control}"
    padding: "8px 24px"
    height: "40px"
  button-download-hover:
    backgroundColor: "{colors.go-yellow-hover}"
  button-filled:
    backgroundColor: "{colors.ink-fill}"
    textColor: "{colors.on-fill}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
    height: "40px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.soft-ink}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
    height: "40px"
  button-tiny:
    rounded: "{rounded.control}"
    padding: "4px 12px"
    height: "30px"
  link-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "48px"
  text-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "{spacing.card-padding}"
  switch-track:
    rounded: "{rounded.band}"
    padding: "3px"
  switch-option:
    textColor: "{colors.soft-ink}"
    rounded: "{rounded.segment}"
    padding: "0 14px"
    height: "34px"
  switch-option-selected:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
  settings-row:
    padding: "10px 16px"
    height: "60px"
  status-message:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
    rounded: "{rounded.band}"
    padding: "10px 16px"
---

# Design System: Teleloadzai

The page is `teleloadzai/web/index.html`. Its `:root` block is the source of the colours. This file records the look **the user chose from drawn models** (2026-10-22 → 23), so new screens (Phase 2: several links, history, Paste, notifications, subtitles) use the same look and don't invent a new one. The product facts live in `PRODUCT.md`, and the decisions live in `CLAUDE.md`.

## Overview

**Creative North Star: "Parcel tracking, softer"** (model 3A, the user's choice)

Each link is a parcel. Before Download it gets a **label**: the card with its title, picture, format, quality and program. After Download its row says where it is in words ("Downloading the picture", "Making the MP3") until it is in your folder. The world is warm paper and ink with soft corners, like a shipping slip on a desk, not a dark "pro" dashboard. Everything is calm and quiet, so the one thing that moves (the download in progress) and the one thing to press (Download) stand out.

The layout is **A**. There is one column. The link box sits under its title "Paste a link", and Settings sits alone in the top corner. The card comes under the link box, and the list under it shows all its rows; the page scrolls when they need more room. No name band: the window title already says "Teleloadzai". Settings copies the **Windows 11 Settings app** (model S2): a side menu, and every setting a row.

**Key Characteristics:**
- Warm paper page, a lighter card on top, dark ink text.
- **One yellow on screen: Download.** Everything else is ink, grey or ochre.
- Rows, not boxes: the card's choices and the settings are lines with a name on the left and a control on the right.
- Windows 11's own controls: the on/off switch and the two-way switch with a raised white button.
- A step is written only once the app has really seen it (decision 33).
- **One grammar for every list row:** mark · format · name · status · one button · ⋯ (2026-11-01).

## Colors

Warm, low-chroma paper and ink, with one saturated yellow kept for the single action that matters. Dark mode follows Windows (`prefers-color-scheme`) and uses the `-dark` tokens in the same roles.

### Primary
- **Download Yellow** (go-yellow, hover go-yellow-hover): the Download button **only**, with go-ink text on it (10.5:1, measured). It also tints three quiet things in its own family: the icon tiles of the card's rows (22 % mix), the updates band (16 %), and the text selection.

### Secondary
- **Dark Ochre** (ochre): the yellow's own family, dark enough to be text: 6.0:1 on a card, 4.9:1 on the paper page (measured). Small ochre text belongs on cards. It is used for links, focus rings, the icon inside each row's tile, and "show more" folds.

### Neutral
- **Paper** (paper): the page, one step darker than the cards. When they were closer (#f4f1ea), everything read as one washed-out sheet.
- **Card** (card): every box: the card, the list, the settings groups.
- **Ink** (ink): text. **Ink fill** (ink-fill) with **on-fill** text is used for filled buttons other than Download, and for an "on" switch.
- **Soft Ink** (soft-ink): help lines, program names, finished rows, inactive menu items, placeholders.
- **Line / Line strong** (line, line-strong): row dividers and card borders / field borders and the Settings button's border.
- **OK Green / Bad Red** (ok-green, bad-red): only for states: a step passed, "done", a log-in sign / a failure, a warning. A warning is a card tinted 7 % red, never a thick coloured bar on its side. *(The failed group's 3 px red line, model D, was the one side line; it went on 2026-11-01.)*
- **Visited Blue** (visit-blue): only the Sites page's **Visited** sign — the site's cookies, no account (6.36:1 on a card, 7.31:1 dark, measured 2026-10-25).

### Console (dark in both modes)
The Console's box is the one dark surface of the light theme, so its colours have no light / dark pair. Contrast on console-box, measured 2026-10-31:
- **console-text** — the programs' words, 11.15:1.
- **console-time** — each line's time, the empty line, 4.87:1 (the earlier #7d838e was 4.33:1, under 4.5).
- **go-yellow** — a download's title line, 10.03:1. Yellow text on a title line — it fills no button here.
- **console-link** — links, 7.94:1. **console-error** — errors and "Failed: …", 7.45:1. **console-end** — "Done.", "Stopped.", Teleloadzai's own messages, 6.97:1.

### Named Rules
**The One Yellow Rule.** Only Download is filled yellow. A doubtful card turns Download into an outline ("Try anyway"), and then it is grey.
**The One Filled Button Rule.** Only one filled button is visible at a time. Once a card shows, Read becomes an outline: Download is the next step. The update band's **Update all** and the list's **Retry failed** are outlines; on Programs, **Update all** is the filled one and each row's Update an outline (review of 2026-10-25: three or four filled buttons on the Download page). Both **Update all** buttons say how many programs they will update: "Update all (2)" (the user, 2026-10-26).
**The Words-Too Rule.** A colour never speaks alone. A green or red sign always has words beside it, or in its accessible name.

## Typography

**Font:** Segoe UI Variable Text (with Segoe UI, system-ui), the font of Windows itself. No web font, and nothing loaded from the network (decision 20). Buttons, lists and fields inherit it (`font-family: inherit`): before that rule, they were drawn in Arial.

**Character:** one plain family, weight does the hierarchy. It reads like a Windows app, not like a website.

### Hierarchy
- **Pane title** (600, 22px): the title of a Settings page (Downloads, Sites, Programs).
- **Screen title** (600, 18px): "Paste a link", and "Settings" in the bar.
- **Section title** (600, 17px): the empty list's sentence and section headings.
- **List title** (600, 16px): "Downloads (3)" over the list. The link field's text is 16px too.
- **Body** (400, 15px, 1.5): everything else, buttons and fields included. In full screen (≥ 1200 px wide) the body is 16px.
- **Small control** (500, 14px): the options inside a switch, the Quality list, the program column on Sites, the updates band, a warning card.
- **Help** (400, 13px, 14px in full screen): help lines and meta lines. Lines stay under 72 characters.
- **Label** (12px, tabular numbers): sizes, speeds, times, the step names.

### Named Rules
**The Few Sizes Rule.** Eight sizes: 12, 13, 14, 15, 16, 17, 18, 22. No new ones. A new screen picks one of these roles. Two exceptions, each for one part only: the **format tag** (11 px bold, a label inside a pill) and the **Console's** monospace lines (12.5 px, Cascadia Mono / Consolas).

## Layout

- **A menu on the left** (model S1, chosen by the user 2026-10-25 from a drawing, after a launcher they showed): an 88 px strip fixed to the window's left edge, a hair darker than the page, with **Download · Console · Programs · Sites** at the top and **Settings** alone at the bottom. Each item is a 72 px tile — icon (22 px) over its name (12 px) — and **each one is its own page**; the open one is tinted yellow. It replaced layout A's Settings button in the corner. **The window opens maximized** ("Restore down" gives the old 860-wide window).
- **One column** beside the menu, centred, 860 px wide at most (1040 px from 1200 px wide), with a 16 px gutter.
- **The Download page has one scrollbar, the page's.** It is one column, at least `100vh` tall: link box, card, then the list, which **shows all its rows, with no scroll of its own**. With few rows its card reaches the bottom of the window and nothing scrolls. *(The user, 2026-11-01, then 2026-11-05 with a model chosen: under the card of several links the list first had 0–25 px, then a 340 px box where a failed row hid above the four in sight; under a one-video card it kept 100–116 px of 547, and the page could not scroll at all.)*
- **Programs**, **Sites** and **Settings** are each a page with its title (22 px) and its groups of rows; Settings holds the download settings only — no tabs (Sites became its own page the same day, at the user's request).
- **The compact step:** a window ≤ 640 px wide or ≤ 720 px tall has smaller margins, a 40 px link field, a smaller picture and lower rows. The real window (860×814 inside) and full screen (1463×834) are above it.
- **Test at the user's two real sizes:** the small window (860×814 inside) and full screen (1463×834). Invented sizes missed what the user saw at once.
- **Rhythm:** 48 px above every page's title (the user, 2026-10-26, model A of three: at 16 px the title touched the window's top; 10 px in the compact step), 16 px inside cards, 14 px between cards, 12 px between a title and its box, rows at least 54 px (card) or 60 px (Settings).
- **Messages** appear at the bottom of the window, centred, never at the top of the page.

## Elevation & Depth

The design is flat and depth comes from tone: paper, then a lighter card, then a thin line. Shadows only mark **the raised thing you chose**, plus one floating message:
- **Raised choice** (`0 1px 3px rgba(40,30,10,.2)` plus a 1 px ink ring at 7 %): the chosen option in a two-way switch.
- **Selected menu item** (`0 1px 3px rgba(40,30,10,.14)`): the open Settings page in the side menu.
- **Switch knob:** none since 2026-10-31 (the off knob is soft ink, the on knob card-coloured).
- **Floating message** (`0 6px 20px rgba(0,0,0,.18)`): the message at the bottom of the window.
- **The ⋯ menu** (`0 6px 18px #0002`, about 13 % black): the small menu of a list row, the one shadow of the list.

**The Flat Card Rule.** Cards and groups never cast a shadow. Only something you can press and have chosen is lifted.

## Shapes

Soft corners, never sharp and never bubbly. Corner sizes (rounded tokens):
- 12px: cards and settings groups;
- 10px: bands, switch tracks and the bottom message;
- 8px: buttons, fields and icon tiles;
- 7px: the options inside a switch;
- 6px: pictures;
- pills for badges and the on/off switch.

Lines are 1 px, and a field's border is one step stronger than a card's border.

Icons are simple line drawings (24-unit grid, 2 px stroke, round ends). They are drawn as a CSS mask filled with `currentColor` and set through `--icon`. Because of that, the code can rewrite a button's text without erasing its icon.

## Components

### Buttons
- **Download:** yellow, ink text, a download icon, 40 px high, padding 8px 24px. It is the only one of its kind. Its key is written after its words, "Ctrl+Enter", 12px, ink mixed 72 % into the yellow (5.3:1, measured) — only while the key works: not on a grey "Try anyway", not while disabled. Ctrl+Enter is the app's only shortcut (the user's rule: no useless keys); Enter (Read) and Esc (close) are not written.
- **Filled:** ink fill with paper text, for main actions other than Download.
- **Outline ("ghost"):** transparent, soft-ink text, a 1 px line border. Read once a card shows, "Try anyway", and row actions.
- **Tiny:** 30 px high, 13px text, for actions inside a row.
- **Settings button:** card background, line-strong border, a gear icon + "Settings". On the Settings screen it becomes an arrow + "Back".
- **States:** colour changes in 0.15 s ease-out; pressed moves down 1 px; disabled at 50 % opacity; keyboard focus is a 2 px ochre outline 2 px outside.
- **A destructive button asks twice:** on the second step it turns red.

### Fields
- 40 px high (the link field 48 px), card background, a line-strong border, 8 px corners.
- **Focus:** the border turns ochre with a soft 3 px ochre halo (22 %), not a second outline.
- **Errors:** a red line of text under the field.

### The card (a parcel's label)
A picture (132×76, 200×112 in full screen, 96×54 in the compact step), the title, and a grey meta line ("YouTube"; the program is named only where the site has two, on the switch — critique of 2026-10-31). The × closes it. Under it come **choice rows**: a 32 px icon tile tinted yellow, the name (Format, Quality, Subtitles, Program) and the control on the right. **A row with nothing to choose is not drawn** (decision 40). **Subtitles** (chosen from a drawing, 2026-10-25): a switch Off · In the video · Separate file, and a language list beside it only when not Off — the video's real languages, an automatic one marked "(automatic)". The row exists only in MP4 and only when the video has subtitles: otherwise not a word. On the several-links card, only "Choose for each" has subtitles: **one Subtitles switch for the card** (Off · In the video · Separate file), shown when a video has subtitles; each video row then has only its **language** list ("Not this video", "English"…), or "no subtitles" in soft ink (critique of 2026-10-31: one mixed list had 13 options). What the chosen program gives ("TikTokDownloader: higher quality.") is a help line **under its switch**, lined up with the row's name. The foot holds Download on the right.

**One word:** the thing that downloads is a **program** everywhere on screen (the card, Settings → Programs, the messages), never a "tool".

### Switches
- **Two-way switch (Windows 11):** a soft track (ink 8 %). The chosen option is a raised card-coloured button in ink, and the others are soft-ink text. Used for MP3 | MP4 and the program names (decision 13). "Selected" is the raised button, never a fill.
- **On/off switch:** 42×22, pill shape. **Off:** an outline in soft ink and a 12 px soft-ink knob (Windows 11's own; the old pale fill with a card-coloured knob was 1.4:1, critique of 2026-10-31). **On:** ink fill, a card-coloured knob that slides 20 px.

### The downloads list (tracking)
**One grammar for every row** (the user, 2026-11-01: "it looks so messy", chosen from a drawn mock): every row, in every state, has the same places — **mark · format tag · name · status · one button · ⋯**. The marks start at one x, the buttons end at one x (measured: 265 / 1219 full screen, 121 / 760 in the small window). A row without ⋯ keeps its 30 px place empty. *(Until then a running row had no mark and sat 18 px left of the finished ones; a failed one was pushed right by a red line; a waiting one drew a whole empty track.)*
- **Marks:** waiting = an empty circle (1.5 px strong line); running = a ring that turns (still when the system asks for less motion); done ✓, failed ✕, stopped / gone / already there – (see Marks below).
- **Status place** (right, before the button): running = the percentage, 13 px ink semibold ("51.0%"), else the seconds (a step, or a program that gives no percentage); waiting = "Waiting"; failed = "Failed" in bad red; stopped = "Stopped" / "Interrupted"; done = the size.
- **A running row** has a second part under the name (from the name's x): a 4 px bar, then one 12 px soft line — "Downloading the picture · 70.2 MB / 138.1 MB · 8.1 MB/s · 8 s left", "Making the MP3…", "yt-dlp is working…". With a real percentage the bar fills, by its width in 0.25 s, so it never sits behind the number; an MP4 counts its picture and sound as **one** download when yt-dlp gives both sizes. Without a percentage a 30 % piece slides (a soft full bar was tried first: it read as finished). Never a bar frozen at 0 (decision 33).
- **A live recording** says "1 min 15 s of 60 min" in the status place and "Recording live · size" under the bar; its bar follows the time limit, the one real measure it has.
- **Order, at rest:** failed, then the rest. **While something moves, a row that ends stays where it is** (a finished row jumped from place 1 to 18 of 30, 2026-11-05): new rows come on top, and only a download that starts may pass those waiting (the waiting rows stood above the running ones). The list sorts itself once everything has ended. A video that fails stays under its playlist's label until then; at rest it stands with the failed rows and says "From: <playlist>".
- **One button and ⋯, every row.** "Already in your folder" keeps Download again; Open and Show in folder are in its ⋯. **A live recording you stopped is a success:** ✓, "Recorded", Open; Show in folder and Record again in its ⋯. *(Both had a second line of buttons; the recording said "Stopped" and offered "Download again". 2026-11-05.)*
- **The button's place is 121 px wide** ("Download again"), so the status words line up; only a longer button ("Update yt-dlp and retry") pushes its own word.
- **No title read yet:** the link is shown in soft grey, never in ink like a title.
- *(Replaced on 2026-11-01, the user's choice: the **tracking line** of model 3A — Started → Downloading → [Joining / Making the MP3] → In your folder, drawn as 9 px dots, only the current stop named. Three circles and two lines said one word; the step is now written in words under the bar.)*
- **The parcel arrives:** a finished row becomes **one line**. A format tag (11 px bold, soft ink on a 9 % ink tint, radius 6: "MP3", "MP3 · 128 kbps", "MP4 · 720p", "Files"), the name without its file ending (cut with "…", the full name on hover; a row of several files is named by its title), then on the right the size read from the disk (soft), **Open** (ghost button) and **⋯** (Show in folder · Download again · Remove from list — "from list": the file stays; "Download again" replaces the file, so it asks twice inside the menu: "Replace the file? Click again"). A file moved or deleted since: a grey "–" mark, "Gone · moved or deleted" (soft; a screen reader hears "Gone: the file was moved or deleted since it was saved." — it heard "Done, in your folder.", critique of 2026-10-31), **Download again** (its one button, one click: nothing to replace) and **⋯** (Remove from list). *(Download again on both: the user, 2026-10-26.)* *(Changed by the user 2026-10-24 from drawn pictures: four all-green lines read as a chart, and two rows of the same video differed by one letter. Until then: "a finished row keeps its line, all green". Model D, 2026-10-25: a green ✓ mark starts the row and replaces the words "In your folder"; one button and ⋯ replace the underlined links.)*
- **Marks** (model D; on every row since 2026-11-01, ended rows only until then): a 20 px circle starts the row — ✓ on ok green, ✕ on bad red, – grey on the line colour (stopped, gone, already there), an empty circle for waiting, a turning ring for running (still when less motion is asked). Aria-hidden: the state is said in words for screen readers.
- **One button and ⋯** (model D, chosen by the user 2026-10-25: the list was "so busy" — 16 buttons on screen for 6 rows): each ended row shows **one** ghost button (Open; for a failed row the way out its case calls for, else Retry), then **⋯**, a 30 px soft button opening a small menu (card colour, 1 px strong line, radius 10, soft shadow — the one shadow of the list) with the row's other actions. One menu open at a time; a click outside, a chosen item or Esc closes it. The header's green bar shows only while something waits or runs. An "already there" row drops the line and goes grey: nothing came down. Since the review of 2026-10-25 it is **one line** like a finished row: a grey **–** mark, its tag, the name, *"Already in your folder"*, **Download again**, and ⋯ with Remove from list. XHS-Downloader's skip comes from its own history, not the folder, so that row says *"Skipped"* and keeps the program's reason in a help line under it. **Every row carries the format tag**, waiting and running ones too (a running row said "· MP4 720p" in words).
- **One row per video** (the user, 2026-11-01: "always one video by one video", from a drawn mock): a playlist, "Same for all" or "Choose for each", adds **one normal row per video** — every video, past 50 too. Its rows share a **label** above them (12 px soft, a line on top): "Popular Music Videos · 182 videos · 7 done · 1 failed". They stay together in the playlist's order; while any is waiting or running, its finished ones stay up with it; a failed one goes with the other failed rows, without the label. A filter hides the label with its rows. A **post** fetched whole by XHS-Downloader or gallery-dl becomes one row per file once it ends, under its name ("· 2 files"); only its first row offers **Download the whole post again** (that is what it does), the others Open, Show in folder and Remove.
- **A row that still holds several items** — a single link yt-dlp downloads as several (a post), or a post while XHS-Downloader or gallery-dl fetch it (2026-10-31): under the row, a list with a 2 px line on its left (13 px, at most 220 px tall, scrolling inside and following the video under way). Each line: a mark (✓ ok green, ↓ ochre, ✕ bad red, · or – soft), the title (600 while under way), and its state on the right: the row's own progress while under way, else *Waiting · In your folder · Failed · Stopped · Already in your folder · Not downloaded*; a failed line holds the program's reason on hover. The row's right side says "1 of 4 done · 1 failed" (yt-dlp, which lists every video from the start) or "2 files so far" (gallery-dl, XHS-Downloader, which say each file only once it is there). A finished row that got everything stays one line.
- **The parcel is lost:** the failed rows are **together**, after the rows on their way and before the rest, in the same grammar as every row: ✕, the format tag, the name, **"Failed"** in the status place, one button, ⋯ — and **its reason on the line under the name**, each row its own (a playlist of 10 unavailable videos says it 10 times: the price of rows that line up, the user's choice 2026-11-01). **Retry failed**, an outline in the list's header (the screen's one filled button is Paste or Download, review of 2026-10-25), shows from two rows a retry can help, never counting a row whose words say "try again in a few days". *(Until 2026-11-01, model D: a 3 px red line on the left, a title "1 download failed", the reason said once above the rows, "Retry all" in the group. One failure took three blocks, its reason above it, and its ✕ out of line.)* A failed row's one ghost button (the log-in the program asked for, another program, an update, else Retry; none when the link itself is the problem; for an unknown error from a program already the newest — "try again in a few days" — yt-dlp's preview version when offered, else **Read the link again**, Retry waiting in ⋯; critique of 2026-10-31, the user's choice), **⋯** (Details, the other ways out, Read the link again when it is not the row's button, Remove). A card opened by *Read the link again* on the same program says the failure in a pink box ("This link failed last time with yt-dlp. …") and its Download is the grey **Try anyway**. *Read the link again* (the user, 2026-10-26) puts the link back in the box and reads it: the card shows the program and choices chosen now (a log-in since, another format), and its Download takes the failed row's place — Retry stays the same try, at once. **Details** opens a soft panel under the row (4 % ink tint, radius 8): the program's raw words folded under "Show <program>'s exact words, for a bug report" (red when open) and the unfinished pieces left in the folder with **Show in folder** (yt-dlp only — the other programs work in their own hidden folder). A site the user is logged in to never says "logging in may help"; its log-in is offered only when the program asked for one, as "Log in again to …". *(Chosen by the user 2026-10-25 from drawn pictures: a failed row was 173–198 px, and two filled the small window; then, the same day, model D — Retry had gone under Details, the same sentence was said three times, and ten underlined words read as a web page.)* The list's header no longer says "6 of 6 finished · 3 failed": the filters carry the counts.
- **What the parcel came without:** one help line under a finished row, in the help-line grey, above Open / Show in folder — today only "Saved without a cover picture." for an MP3 whose file holds no cover. A row that got everything says nothing; an "already there" row never shows it.
- **When the list is empty:** no box, just a parcel drawing and "Your downloads will appear here." — about 200 px down (`min(24vh, 200px)`), the drawing 96 px, the title 22 px, the line of sites 16 px (the user, 2026-10-26, model A: lower and bigger, still above the middle). While a card is open (one link or several), neither shows: the card is enough.

### Paste / Read
The button beside the link box says **Paste** while the box is empty and **Read** once it holds text: one place, never two buttons. It is ink-filled until a card shows, then an outline (the One Filled Button rule), beside both kinds of card. The box's placeholder says it beforehand: "https://…   One link, or several: one per line". **A pasted link waits in the box** for Read or Enter, so it can be changed first — Settings → "Read a link as soon as it is pasted", off by default (the user, 2026-10-26); on, it is read at once. The same for Paste and a link you copied.

### Several links (one card)
One paste of several links gives **one card**, never a second list of "found links". It shows:
- the title "3 links", and a meta line "YouTube 2 · TikTok 1";
- the links, each with its program in soft ink: a short list that scrolls past about 4 lines, so Download stays in sight;
- "**Not added:**" with one reason per line;
- the same rows as the single card: Format, Quality ("Best — each video at its own best size", or the kbps list for MP3), Folder: **the folder itself and a "Change…" button**, for this card only; Settings is not changed, and Download opens no window (the user, 2026-11-05: it said "You choose it when you press Download"). Not drawn when each video has its own window. A long path shows its drive and its end;
- the yellow **Download N**.

Under its title, a **Choices** row (the stack icon, a two-way switch): **Same for all · Choose for each**. The user's pick is kept.
- **Same for all**: as above.
- **Choose for each**: Format and Quality for all are not drawn; each video is a row instead — its title (soft ink while it is read), then a small MP3 / MP4 switch (28 px high, 13 px text), a Quality list only when the video has a real choice (else "Best" in soft ink), the language list, and a Program list only where the site has several. Since 2026-10-31 the title is on its own line and the controls sit under it in the same columns on every row (7.5rem · 6.5rem · up to 12rem · auto). Rows are separated by a line; the list scrolls in the card (up to 26vh since 2026-10-31 — 30vh made the page scroll with the card's Subtitles row; the Downloads card under it goes down to 72 px; 18vh in the compact step, where each row wraps onto two lines). While the videos are read, the title counts ("Reading the videos… 3 of 8") and the meta line says "Download now: videos not read yet come at their best size."
- **A playlist** uses the same card: the title "Team Fortress 2 [2010 Version] — 29 videos", its videos as the rows (their titles, not links), "…and N more videos" past 50 in Same for all.
- In the compact step the Choices row is tighter (34 px), so the screen does not scroll at 520×700.

Under this card, the list shows all its rows and the page scrolls, as everywhere on this page.

### List tools
Over the Downloads list:
- **from 2 downloads under way together:** a 4 px green bar of how many of **them** have ended; rows from before do not count (no total in words since model D: the filters carry the counts);
- **from 4 rows:** a two-way-switch style row of filters with counts (All · Running · Waiting · Done · Failed, in red when not chosen · Stopped). **The first five always show**; a filter at 0 is grey and cannot be pressed (they came and went as downloads moved, and the list jumped — 2026-11-01). **Stopped shows only when there are some** (2026-11-05: without it the counts gave 27 of 30);
- **from 2 retryable failed rows:** "Retry failed", an outline in the header, left of "Clear finished".

The title is always "Downloads (N)" (it switched to "Downloads · 2 running, 2 waiting" and back). "Clear finished" stays in the header (done, "already there" and stopped rows; never a failed one). **"Remove all"** is in the header's **⋯**, there whenever an ended row exists: it removes every ended row, failed ones too, in two clicks inside the menu ("Remove 3? Click again"); the files stay on the disk. *(Beside "Clear finished" from 2026-10-26, the user's placement, shown only with a failed row; moved into ⋯ on 2026-11-01: it appeared at the first failure and moved the header.)*

**Interrupted downloads** (cut off when Teleloadzai closed) get the updates band's tint: a yellow band over the list, "1 download did not finish when Teleloadzai closed.", with a ghost **Continue it / Continue them**. Each such row says "Interrupted" on its stop and has its own Continue and Remove. Nothing restarts by itself.

### Console (2026-10-25, like the yutto window the user showed)
- **Its title, "Console"**, at the top like Programs, Sites and Settings (review of 2026-10-25: it was the only page without one).
- **A state line:** a chip, *idle* (grey) or *running* (green), and what runs ("1 download: Me at the zoo (yt-dlp)").
- **Five tools** on the right, small ghost buttons: Clear · Copy all · Save as file · **Auto-scroll** (on) · **Wrap lines** (off); a tool that is on has an ochre border. **Clear** takes two clicks ("Clear all? Click again"), like every button that destroys.
- **The box** takes the page's height (the page never scrolls): near-black `#1d1f24`, 12 px radius, Cascadia Mono / Consolas 12.5 px, text `#d8d4cb`, each line led by its time in grey `#868c96` (4.87:1; `#7d838e` was 4.33, 2026-10-31). A download's title line is yellow (`--go`, "── Me at the zoo · yt-dlp ──"), links blue `#84b6ff`, errors red `#ff8f80`, our closing line light grey `#a3a9b3` ("Done.", "Stopped.") or red when it failed ("Failed: …", for a download, an install or a title read — one colour for every failure since 2026-10-26), the empty line grey `#868c96`. The box is dark in both modes, so these colours have no light / dark pair. Read only. Empty: "Nothing yet. Title reads, downloads and updates write here while they work." **Not only downloads** (the user, 2026-10-26): a title read ("Reading the title · yt-dlp · link", then "Title: …" or its error in red), a program install or update (each step once, then "Updated: 1.32.17 → 1.32.18." or "Failed: …" in red), and Teleloadzai's own messages from the bottom of the window ("Teleloadzai: …", light grey). The 6-hourly version checks are left out: eight lines of nothing each time.

### Settings (the Windows Settings model)
- **Groups:** cards of rows with a name (600), an optional help line (13 px soft), and the control on the right.
- **Sites, the log-in state** beside each site's button, a dot and a word: **Logged in** (ok green) · **Visited** (blue `--visit`, #2f5f9e / dark #8fb3e8 — the site's visitor cookies, no account; 2026-10-25) · **Expired** (bad red) · nothing.
- **Sites, what a site needs:** under the site's name, 12 px soft, one line — "A visit is enough · seen Oct 25" / "Works without a log-in · seen …" / "Needs your account · seen …" — for the program chosen on the row; nothing where nothing was seen. The name column is up to 230 px so it fits on one line.
- **Sites, its order** (critique of 2026-10-31, model 5 chosen by the user): the log-ins switch, then **the site table first** — its column names stay in sight while it scrolls; a site with one program shows no program name; sites with nothing to set (one program, no log-in, nothing seen) fold under "N more sites with nothing to set" — then the account warning (hard rule 5, always in sight), then **one folded card, "Your log-ins and cookie file"** — a Windows 11 expander (2026-10-31, the user: the bare line was "not noticeable" and "weird"): the key tile, the name, a help line with the state and what is inside ("153 cookies, 18 sites · add a log-in, import, forget"), and an arrow on the right; it opens downward **inside the same card**, holding what a cookie is, the two ways to add a log-in (no tiles of their own), the cookies.txt how-to and Forget them.
- **Paused:** while log-ins are paused, the whole Sites page except its switch is at 45 % opacity, greyscale, and out of reach (`inert`); one line under the switch says it: *"Paused: Teleloadzai does not use your log-ins now. Turn this on to change them."* (review of 2026-10-25: the grey page looked broken).
- **Downloads page, its switches in order:** Ask where to save each file · Use a link I copied · **Tell me when a download ends** (a bell icon; "A Windows message, only while you are in another window. Click it while it is on screen to come back.").

### The Windows message (outside the window)
Drawn by Windows, not by the page: "Teleloadzai" on top, a title ("Download finished", "Download failed", "Nothing downloaded", "Downloads finished", "Downloads ended") and one sentence with the file name only — never a link. Its icon is Windows' standard program icon until step 6 gives Teleloadzai its own.

### Bands and messages
- **Updates band:** a yellow-tinted band under the bar, not a card.
- **Message:** an ink box at the bottom of the window, with paper text and a 24×24 ×.
- **Badges:** pills with a 1 px border, 12 px text; green or red borders for states. An available **update** is ochre (`--accent`): good news, not a failure (review of 2026-10-25; it was red).

## Do's and Don'ts

### Do:
- **Do** keep Download the only yellow thing on screen.
- **Do** make a new choice a **row** (icon tile, name, control on the right), and a new setting a **row in a group**.
- **Do** use the two-way switch for an either/or choice, and the on/off switch for a yes/no setting.
- **Do** write a step under the bar only when the app has really seen it (decision 33).
- **Do** picture the main screen and the three Settings pages at 860×814 and 1463×834 after a change that can move the layout.
- **Do** keep text at 4.5:1 contrast or more, in light and dark mode.

### Don't:
- **Don't** add a second filled yellow button, or fill a selected option: selected is raised, not filled.
- **Don't** wrap every item in its own box. Use rows and lines; the screen became a grid of boxes before.
- **Don't** put a thick coloured bar on the side of a card for a warning; tint the card instead.
- **Don't** show the site and program as pills under the title: they read as buttons. They are plain grey words.
- **Don't** add a name band or a logo bar: the window title already says it.
- **Don't** give the Downloads list a scroll of its own: one scrollbar, the page's.
- **Don't** load fonts or icons from the network.
