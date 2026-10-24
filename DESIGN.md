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

Each link is a parcel. Before Download it gets a **label**: the card with its title, picture, format, quality and program. After Download it gets **tracking steps** until it is in your folder. The world is warm paper and ink with soft corners, like a shipping slip on a desk, not a dark "pro" dashboard. Everything is calm and quiet, so the one thing that moves (the download in progress) and the one thing to press (Download) stand out.

The layout is **A**. There is one column. The link box sits under its title "Paste a link", and Settings sits alone in the top corner. The card comes under the link box, and the list fills the rest of the window and scrolls inside its own card. No name band: the window title already says "Teleloadzai". Settings copies the **Windows 11 Settings app** (model S2): a side menu, and every setting a row.

**Key Characteristics:**
- Warm paper page, a lighter card on top, dark ink text.
- **One yellow on screen: Download.** Everything else is ink, grey or ochre.
- Rows, not boxes: the card's choices and the settings are lines with a name on the left and a control on the right.
- Windows 11's own controls: the on/off switch and the two-way switch with a raised white button.
- The tracking line: a step is drawn only once the app has really seen it (decision 33).

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
- **OK Green / Bad Red** (ok-green, bad-red): only for states: a step passed, "done", a log-in sign / a failure, a warning. A warning is a card tinted 7 % red, never a thick coloured bar on its side.

### Named Rules
**The One Yellow Rule.** Only Download is filled yellow. A doubtful card turns Download into an outline ("Try anyway"), and then it is grey.
**The One Filled Button Rule.** Only one filled button is visible at a time. Once a card shows, Read becomes an outline: Download is the next step.
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
**The Few Sizes Rule.** Eight sizes: 12, 13, 14, 15, 16, 17, 18, 22. No new ones. A new screen picks one of these roles.

## Layout

- **One column**, centred, 860 px wide at most (1040 px from 1200 px wide), with a 16 px gutter on each side of the window.
- **The main screen never scrolls.** It is one column `100vh` tall: bar, link box, card, then the list, which takes the room left (at least 170 px) and scrolls inside its card.
- **Settings** is a grid: a 190 px side menu (it stays in place while you scroll) and the page beside it. Below 700 px wide, the menu keeps only its icons.
- **The compact step:** a window ≤ 640 px wide or ≤ 720 px tall has smaller margins, a 40 px link field, a smaller picture and lower rows. The real window (860×814 inside) and full screen (1463×834) are above it.
- **Test at the user's two real sizes:** the small window (860×814 inside) and full screen (1463×834). Invented sizes missed what the user saw at once.
- **Rhythm:** 16 px inside cards, 14 px between cards, 12 px between a title and its box, rows at least 54 px (card) or 60 px (Settings).
- **Messages** appear at the bottom of the window, centred, never at the top of the page.

## Elevation & Depth

The design is flat and depth comes from tone: paper, then a lighter card, then a thin line. Shadows only mark **the raised thing you chose**, plus one floating message:
- **Raised choice** (`0 1px 3px rgba(40,30,10,.2)` plus a 1 px ink ring at 7 %): the chosen option in a two-way switch.
- **Selected menu item** (`0 1px 3px rgba(40,30,10,.14)`): the open Settings page in the side menu.
- **Switch knob** (`0 1px 2px rgba(0,0,0,.25)`).
- **Floating message** (`0 6px 20px rgba(0,0,0,.18)`): the message at the bottom of the window.

**The Flat Card Rule.** Cards and groups never cast a shadow. Only something you can press and have chosen is lifted.

## Shapes

Soft corners, never sharp and never bubbly. Corner sizes (rounded tokens):
- 12px: cards and settings groups;
- 10px: bands, switch tracks and the bottom message;
- 8px: buttons, fields and icon tiles;
- 7px: the options inside a switch;
- 6px: pictures;
- pills for badges, the "or" between the two log-in ways, and the on/off switch.

Lines are 1 px, and a field's border is one step stronger than a card's border.

Icons are simple line drawings (24-unit grid, 2 px stroke, round ends). They are drawn as a CSS mask filled with `currentColor` and set through `--icon`. Because of that, the code can rewrite a button's text without erasing its icon.

## Components

### Buttons
- **Download:** yellow, ink text, a download icon, 40 px high, padding 8px 24px. It is the only one of its kind.
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
A picture (132×76, 200×112 in full screen, 96×54 in the compact step), the title, and a grey meta line ("YouTube · yt-dlp"). The × closes it. Under it come **choice rows**: a 32 px icon tile tinted yellow, the name (Format, Quality, Program) and the control on the right. **A row with nothing to choose is not drawn** (decision 40). What the chosen program gives ("TikTokDownloader: higher quality.") is a help line **under its switch**, lined up with the row's name. The foot holds Download on the right.

**One word:** the thing that downloads is a **program** everywhere on screen (the card, Settings → Programs, the messages), never a "tool".

### Switches
- **Two-way switch (Windows 11):** a soft track (ink 8 %). The chosen option is a raised card-coloured button in ink, and the others are soft-ink text. Used for MP3 | MP4 and the program names (decision 13). "Selected" is the raised button, never a fill.
- **On/off switch:** 42×22, pill shape, ink fill when on, a white knob that slides 20 px.

### The downloads list (tracking)
Each row has the name, then numbers on the right joined with " · " (12.3 MB / 45.6 MB · 2.1 MB/s · 16 s left). Under that is the **tracking line**: Started → Downloading → [Joining / Making the MP3, only once announced] → In your folder.
- Stops are 9 px dots: green when passed; yellow with an ink ring for **now**; red for failed; grey for stopped.
- **Only the stop where the parcel is now keeps its name**, and it says what happened there: "Waiting", "Failed", "Stopped". The other stops are dots only. The state is also written for screen readers (the line itself is drawn only).
- **A live recording** says "Recording" on its stop and "Recording live · 1 min 15 s of 60 min" on the right; its bar follows the time limit, the one real measure it has.
- Started → Downloading is a short fixed step (24 px). The segment after Downloading **is** the progress bar and takes the rest of the row, so the green never shows more than was measured. It moves with `scaleX` over 0.7 s, the refresh rhythm.
- **The parcel arrives:** a finished row keeps its line, all green, ending on "In your folder"; its title stays in ink. An "already there" row drops the line and goes grey: nothing came down.
- **When the list is empty:** no box, just a parcel drawing and "Your downloads will appear here."

### Paste / Read
The button beside the link box says **Paste** while the box is empty and **Read** once it holds text: one place, never two buttons. It is ink-filled until a card shows, then an outline (the One Filled Button rule), beside both kinds of card. The box's placeholder says it beforehand: "https://…   One link, or several: one per line".

### Several links (one card)
One paste of several links gives **one card**, never a second list of "found links". It shows:
- the title "3 links", and a meta line "YouTube 2 · TikTok 1";
- the links, each with its program in soft ink: a short list that scrolls past about 4 lines, so Download stays in sight;
- "**Not added:**" with one reason per line;
- the same rows as the single card: Format, Quality ("Best — each video at its own best size", or the kbps list for MP3), Folder;
- the yellow **Download N**.

While this card is open, the list under it may shrink to 96 px, so the main screen never scrolls.

### List tools
Over the Downloads list:
- **from 2 rows:** a real total in the header ("5 of 8 finished · 2 failed"), with a 4 px green bar;
- **from 4 rows:** a two-way-switch style row of filters with counts (All · Running · Waiting · Done · Failed, in red when not chosen);
- **from 2 retryable failed rows:** a ghost "Retry all failed" on the right.

"Clear finished" stays in the header. Nothing shows before it is needed.

**Interrupted downloads** (cut off when Teleloadzai closed) get the updates band's tint: a yellow band over the list, "1 download did not finish when Teleloadzai closed.", with a ghost **Continue it / Continue them**. Each such row says "Interrupted" on its stop and has its own Continue and Remove. Nothing restarts by itself.

### Settings (the Windows Settings model)
- **Side menu:** icon + name, 40 px rows. The open page is raised on a card.
- **Groups:** cards of rows with a name (600), an optional help line (13 px soft), and the control on the right.
- **Paused:** while log-ins are paused, the whole Sites page except its switch is at 45 % opacity, greyscale, and out of reach (`inert`).

### Bands and messages
- **Updates band:** a yellow-tinted band under the bar, not a card.
- **Message:** an ink box at the bottom of the window, with paper text and a 24×24 ×.
- **Badges:** pills with a 1 px border, 12 px text; green or red borders for states.

## Do's and Don'ts

### Do:
- **Do** keep Download the only yellow thing on screen.
- **Do** make a new choice a **row** (icon tile, name, control on the right), and a new setting a **row in a group**.
- **Do** use the two-way switch for an either/or choice, and the on/off switch for a yes/no setting.
- **Do** draw a tracking stop only when the app has really seen that step (decision 33).
- **Do** picture the main screen and the three Settings pages at 860×814 and 1463×834 after a change that can move the layout.
- **Do** keep text at 4.5:1 contrast or more, in light and dark mode.

### Don't:
- **Don't** add a second filled yellow button, or fill a selected option: selected is raised, not filled.
- **Don't** wrap every item in its own box. Use rows and lines; the screen became a grid of boxes before.
- **Don't** put a thick coloured bar on the side of a card for a warning; tint the card instead.
- **Don't** show the site and program as pills under the title: they read as buttons. They are plain grey words.
- **Don't** add a name band or a logo bar: the window title already says it.
- **Don't** let the main screen scroll; the list scrolls in its card.
- **Don't** load fonts or icons from the network.
