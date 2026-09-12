# yt-ops

Pipeline for **Had To Find Out** (`@hadtofindout`) — short-form videos about
how discoveries were actually made.

> **Channel rule:** Every video tells the story of how somebody found
> something out. Not what is true, but how we came to know it.

A script that names no person, no place and no year is rejected. That one
constraint keeps the channel out of generic-fact territory, which is what
YouTube's inauthentic-content policy targets.

---

## Status

**1 video published** (`0001-galileo-pisa-myth-bust`, Sep 7 2026).

The back half of the pipeline is automated. The front half is not.

| Stage | State | Script |
|---|---|---|
| Topic selection | manual | — |
| Research → sources → accounts → claims | manual | — |
| Script writing | manual | — |
| Storyboard (line → scene) | manual | — |
| Scene generation | **1 of ~8 scenes built** | `scene_timeline.py`, `falling_bodies.py` |
| Voice | automated | `make_vo.py` |
| Captions | automated | `captions.py` |
| SFX | automated | `make_sfx.py` |
| Render | automated | `render.py` |
| Metadata | automated | `metadata.py` |
| Upload | manual, deliberately | — |

Upload stays manual. It removes the Google API compliance audit entirely,
removes upload quota, removes duplicate-upload bugs, and puts a human
between the machine and the channel — which is the line YouTube's policy
draws between "AI-assisted" and "mass-produced".

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python init_db.py
```

System dependencies:

- **ffmpeg** — must be built with `--enable-libass` (burns captions)
- **espeak-ng** — phonemiser for the TTS

Model files, not in git (~340 MB), from
[thewh1teagle/kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases):

- `kokoro-v1.0.onnx`
- `voices-v1.0.bin`

---

## Making a video

```bash
python make_vo.py            # script  -> vo.wav + vo.json (word timings)
python captions.py           # vo.json -> captions.ass
python scene_timeline.py     # -> clips/NN-timeline.mp4
python falling_bodies.py     # -> clips/falling.mp4
python make_sfx.py           # -> assets/knock.wav
python render.py             # -> out/<code>.mp4
python metadata.py           # -> out/<code>-metadata.txt
```

Then upload manually and record the ID:

```bash
python -c "import sqlite3;c=sqlite3.connect('db.sqlite');c.execute(\"UPDATE videos SET youtube_id='XXX', published_at=datetime('now') WHERE id=1\");c.commit()"
```

---

## Data model

```
TOPIC ──┬── SOURCES          documents found during research
        ├── ACCOUNTS         competing versions of the story
        │     └── CLAIMS ──── CLAIM_SOURCES  (which source backs what)
        └── ANGLES           standalone video ideas from one topic
              └── SCRIPT ──── VIDEO ──── ANALYTICS_DAILY
```

Two design decisions worth keeping:

**Accounts are labelled by stance, not version number.** `popular`,
`consensus`, `disputed`, `superseded`, `fringe`. Where `popular` and
`consensus` disagree, *that gap is the video*. A topic with only `popular`
sources and no scholarly backing does not proceed to script.

**Angles replace "part 1 / part 2".** One research effort yields several
standalone videos shot from different angles (`myth_bust`, `origin`,
`mechanism`, `person`, `consequence`), published days apart. Each works
alone. The Shorts feed serves videos individually to strangers — it has no
concept of a series, so Part 2 to a cold audience is a retention cliff.

Hierarchy lives in foreign keys. Files get a flat readable code:
`0042-earth-age-myth-bust.mp4`.

---

## Files

| File | Does |
|---|---|
| `config.yaml` | Channel rule, gates, voice, render settings. Single source of truth |
| `schema.sql` | 12-table SQLite schema |
| `init_db.py` | Builds `db.sqlite`, seeds the myth blacklist |
| `make_vo.py` | Multi-segment TTS (Emma narrates, George quotes sources) → `vo.wav` + word timings |
| `captions.py` | Word timings → styled `.ass`. Isolates long tokens so dates hold alone |
| `scene_timeline.py` | **Scene library:** animated dates with gap highlighting |
| `falling_bodies.py` | **Scene library:** physics animation, two masses falling |
| `make_sfx.py` | Synthesises the impact sound. Original audio, no licence |
| `render.py` | Shots → 1080×1920 30fps, burns captions, mixes voice + music + SFX |
| `metadata.py` | Title options + structured description + attributions from DB |
| `log_assets.py` | *(legacy)* Fetches Commons licences, logs to DB. Obsolete once fully animated |

---

## Visual direction

Video 1 used public-domain stills with Ken Burns motion. Verdict after
watching it: **it looks like a slideshow with narration.**

Direction from video 2: **everything animated.** Original motion graphics,
no stock images, no licence chasing. This also removes an entire category
of work — `log_assets.py`, the Commons licence checks, the `assets` table,
and image credits in the description all become unnecessary.

### Scene library — the thing that makes 2/day possible

You cannot hand-animate 60 videos a month. What makes it possible is a set
of **parameterised** scenes any video composes from. Video 1 is expensive
because you are building the library. Video 12 is a config file.

| Scene | Status | Signature |
|---|---|---|
| `timeline()` | built | `timeline(events, gap, gap_label)` |
| `drop_test()` | built | `falling_bodies.py` |
| `text_beat()` | **todo** | full-frame statement, the pattern break |
| `number_reveal()` | **todo** | a figure arriving with weight |
| `quote_card()` | **todo** | primary source on screen, attributed |
| `versus()` | **todo** | two things compared side by side |
| `map_zoom()` | **todo** | continent → country → city, pin drops |
| `ramp()` | **todo** | inclined plane, ticks as it accelerates |

Built with Pillow, not Manim. Reasons: no heavy dependency chain, runs on
CPU, deterministic output, and a hand-built look is more distinctive than
default Manim styling.

**House style** (keep consistent across every scene):

```
BG   (11, 13, 18)      near-black
INK  (238, 236, 230)   off-white
DIM  (120, 124, 132)   grey, for labels
HOT  (255, 214, 122)   amber, for the one thing that matters
```

Ease-out cubic on all motion. Nothing arrives linearly.

---

## Road to full automation

Each step needs the videos before it to exist — the later stages are built
from patterns that only appear once you have made things. The rule:
**automate a step after doing it by hand five times.** Five runs is roughly
when you know what actually varies between videos rather than what you
assumed would vary.

### Now → video 5: finish the scene library

Each video needs a scene that does not exist yet. Build it, add it to the
library, move on. By video 5 there should be 8–10 scenes.

### Video 5: automate the back half — `make.py`

```bash
python make.py --script script.txt --storyboard shots.yaml
```

You write the script and choose scenes. Everything after is one command.
**Biggest single win, arrives soonest** — per-video time drops from about
an hour to fifteen minutes.

Needs: scene registry, `shots.yaml` schema, `render.py` reading a
storyboard instead of a hardcoded `SHOTS` list.

### Video 15: auto-storyboard

Rules, not AI. A date becomes `timeline`. A quote becomes `quote_card`. A
comparison becomes `versus`. Derived from patterns across ~10 videos.

### Video 25+: research assistance — *not* research automation

**This stage stays human-in-the-loop, possibly permanently.**

The niche is myth-dense. An LLM asked to research Galileo and the Tower of
Pisa produces the myth, confidently, citing blogs that repeat it. During
this project's own development a wrong figure ("twenty years before
Galileo" — wrong by every measure) was written by an assistant and pasted
into a script unchecked. Two humans and it still got through.

Automating that step means shipping fabrications at 60/month on a channel
whose entire premise is that it checks things.

The realistic version: the machine finds candidate sources and drafts; a
human verifies claims against them and approves. ~20 minutes per video,
and it is the 20 minutes that makes the channel worth watching.

### Then: analytics loop

```
analytics.py   pull retention into analytics_daily
report.py      Telegram digest
```

Log everything. **Do not compute p-values.** At 60 videos/month against
heavy-tailed Shorts view distributions, any A/B test will confidently
report a winner from n=8 and optimise toward noise. Look at directional
patterns over 100+ videos.

---

## Known issues

- **~5s of dead air** at the end of video 1 (`TAIL_SEC` was 2.8). Set to
  0.4. Shorts loop — dead air at the end breaks the loop instead of
  sending viewers round again.
- **No real silence anywhere.** Audio never drops below RMS 0.06, so the
  clap payoff has nothing to land against. Widen the gap in `make_vo.py`
  from 1.2s to 2.0s.
- `08-two-new-sciences-titlepage` was never found. The 1586-vs-1638 beat
  has no visual. Moot once fully animated.
- `render.py` has a hardcoded `SHOTS` list. Moves to `shots.yaml` at the
  `make.py` step.

---

## Constraints to remember

**YPP thresholds rise 1 Feb 2027** — 1,000 subs + 8,000 watch hours/365d,
or 20M Shorts views/90d. Shorts ad revenue needs 10M qualified views over
the trailing 90 days. Treat ad revenue as a lottery ticket, not a plan.

**Free-first.** No GPU on this machine, so local video generation is out.
Wan 2.2 image-to-video via HuggingFace ZeroGPU Spaces is free but
quota-limited — good for one hero shot, not sixteen a day.

**Always tick "Altered or synthetic content"** in Studio on upload.

**Every number gets checked against a source**, including numbers
suggested by an assistant.