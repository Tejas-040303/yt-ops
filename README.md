# yt-ops

Pipeline for **Had To Find Out** (`@hadtofindout`) — short-form videos that
answer one real question and show how we know the answer.

> **Channel rule:** Every video answers one real question, and shows how
> we know the answer: a source behind every claim, and a person, a place,
> a year or a number to anchor it. Not trivia — how we know.

The subjects are general now — three [lanes](#lanes), from the history
of discovery to everyday questions to the story behind the news. The
rule above is what did not widen. A script with no checkable specific in
it is rejected, because that one constraint keeps the channel out of
generic-fact territory, which is what YouTube's inauthentic-content
policy targets.

---

## Status

**1 video published** (`0001-galileo-pisa-myth-bust`, Sep 7 2026).

One command makes a video from nothing. **The check that it is true is
still yours**, and that is the one stage the roadmap below argues should
stay that way.

| Stage | State | Script |
|---|---|---|
| Lane choice | automated, by share | `auto.py` → `config.yaml` `lanes` |
| Topic selection | automated | `make.py --auto` → `brain.py` (trending: searches the news first) |
| Research → sources → accounts → claims | automated, **unverified** | `auto.py` → `brain.py` |
| Script writing | automated | `auto.py` → `brain.py` |
| Storyboard (line → scene) | automated | `auto.py` → `shots/NNNN.yaml` |
| Voice | automated | `make.py` → kokoro |
| Captions | automated | `make.py` → `captions.py` |
| Scene generation | automated, 8 scenes | `make.py` → `scene_*.py` |
| SFX placement | automated | `make.py` |
| Render | automated | `make.py` → `render.py` |
| Title ranking | automated, advisory | `auto.py` → youtube-agent-skill `title.py` |
| Metadata | automated | `make.py` → `metadata.py` |
| **Checking the claims** | **manual, permanently** | `research/NNNN-notes.md` |
| Upload | manual, deliberately | — |
| Retention reading | automated, per video | `retention_report.py` → youtube-agent-skill `retention.py` |

Upload stays manual. It removes the Google API compliance audit entirely,
removes upload quota, removes duplicate-upload bugs, and puts a human
between the machine and the channel — which is the line YouTube's policy
draws between "AI-assisted" and "mass-produced".

---

## Lanes

Three kinds of video, one channel. `make.py --auto` makes whichever lane
is furthest behind its share of everything made so far; `--lane` forces
one.

| Lane | Share | What it is | Must have | Sources |
|---|---|---|---|---|
| `found_out` | 50% | How somebody found something out — the original channel | a named person, a year, a specific | 4+, at least 1 primary or scholarly |
| `curiosity` | 30% | One everyday question answered properly | a number, year or name | 3+, at least 1 primary, scholarly, museum or encyclopedia |
| `trending` | 20% | The checkable story behind something in the news | a year or month, a specific | 3+, at least 2 news or primary |

Every lane is domain-locked to its own list in `config.yaml` and every
claim still needs a verbatim quote. The lanes change the brief, never
the discipline.

**Why the shares lean on `found_out`.** YouTube's inauthentic-content
policy is about channels whose videos are hard to tell apart: one
template, little variation, easily made at scale. This channel already
has the template — one locked voice, one length band, one house style,
two a day. What has kept each video distinct is a specific, sourced
story, and `found_out` carries that most strongly. Keep it the largest
share. The "a number, year or name" gate exists for the same reason: a
script made only of generalities is the video this channel is built not
to make.

**Grey areas.** `gates.banned_topic_areas` (medical, financial or legal
advice, religion, politics, conflicts, recent disasters and deaths,
crime and trials, controversy about living people, children, and more)
goes to the model when it picks a subject and when it writes. `trending`
adds celebrity news, anything still unfolding, and reacting to another
creator's video. No program can check a topic area, so these are also
the first thing to read in review.

**Copyright.** Every frame comes from a `scene_*.py` and every sound
from kokoro or `make_sfx.py`, so there has been nothing to license.
`config.yaml` `media` keeps it that way as subjects widen: no clips,
screenshots, logos or likenesses, no lyrics or lines from films and
shows, brands named only to identify them, and any quotation — spoken
or on a `quote_card` — capped at 25 words. That cap is a conservative
house rule, not legal advice.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python init_db.py
```

`make.py --auto` also needs an Anthropic API key, in the environment or
in a `.env` next to `brain.py`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Nothing else in the pipeline needs it. A storyboard you wrote yourself
renders without touching the API.

The [youtube-agent-skill](https://github.com/Tejas-040303/youtube-agent-skill)
fork goes next to this checkout. Title ranking, the swipe file and
retention reports call its tools (`ytskill.py`); without it, title
ranking is skipped with a note and everything else runs.

```bash
git clone https://github.com/Tejas-040303/youtube-agent-skill ../youtube-agent-skill
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

From nothing:

```bash
python make.py --auto                              # it picks the lane and the subject
python make.py --auto --lane curiosity             # a given lane
python make.py --auto --topic "how we weighed the Earth"
python make.py --auto --swipe research/swipe.json  # steer it with what is working
```

It picks the lane furthest behind its share, chooses a subject it has
not covered, researches it against that lane's allowed domains, writes
the script, ranks the titles, storyboards it and renders it. Then
**read `research/NNNN-notes.md` before it ships** — particularly the
section on what it could not establish. That file is the whole point of
the design.

From a storyboard you wrote:

```bash
python make.py shots/0002.yaml
```

Voice, captions, every scene, SFX placement, render and metadata. Out
comes `out/<code>.mp4` and `out/<code>-metadata.txt`.

```bash
python make.py shots/0002.yaml --plan      # durations and cuts, renders nothing
python make.py shots/0002.yaml --skip-vo   # reuse vo.wav, re-cut the picture
```

`--plan` is the one to run first: it reports whether every scene fits
the line it sits under, before spending minutes on frames. `--skip-vo`
is for the second pass onwards, because the TTS is the slow part and the
narration rarely changes once it is right.

Copy `shots/0001.yaml` and change the content. The schema is three
blocks — `script`, `shots`, `metadata` — and the rules are enforced, not
documented: every script line must be covered by exactly one shot, in
order, or `make.py` refuses to run.

`--swipe` takes a listing of comparable channels' videos — collect it
with `yt-dlp --flat-playlist -J` per channel, shaped as
[yt-viral](https://github.com/Tejas-040303/youtube-agent-skill/tree/main/skills/yt-viral)
describes. The outliers, ranked by how far each beat its own channel's
median, go to topic selection as direction, never as titles to copy.

Then upload manually and record the ID:

```bash
python -c "import sqlite3;c=sqlite3.connect('db.sqlite');c.execute(\"UPDATE videos SET youtube_id='XXX', published_at=datetime('now') WHERE id=1\");c.commit()"
```

A few days later, export its audience-retention CSV from Studio and:

```bash
python retention_report.py shots/0002.yaml retention.csv
```

It names the script line and the scene on screen at every drop, from
the timings `make.py` saved to `out/<code>-timing.json`. Read the
patterns across twenty videos, not one.

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
| `make_vo.py` | *(superseded by `make.py`)* Video 1's TTS with its script hardcoded |
| `captions.py` | Word timings → styled `.ass`. Isolates long tokens so dates hold alone |
| `make.py` | **The pipeline.** Storyboard → voice, captions, scenes, SFX, render, metadata |
| `brain.py` | The Claude API calls: scout the news, pick a subject, research it, write it, storyboard it — each briefed by its lane |
| `auto.py` | Picks the lane, runs those steps, enforces the gates, ranks the titles, writes the DB rows and the storyboard |
| `ytskill.py` | The bridge to the youtube-agent-skill fork: title lint, swipe file, retention reading |
| `retention_report.py` | A Studio retention export → the line and scene behind every drop |
| `research/` | Per-video audit trail: the raw notes and the claims with their quotes. Not in git |
| `shots/NNNN.yaml` | One storyboard per video. The only file that changes between videos |
| `scene_kit.py` | **Scene library core:** palette, easing, fonts, safe area, encode. Every scene imports it |
| `scene_timeline.py` | `timeline()` — dates arriving on a line, with the gap that matters bracketed |
| `falling_bodies.py` | `drop_test()` — two masses falling level, landing as one sound |
| `scene_text_beat.py` | `text_beat()` — a statement landing word by word. The pattern break |
| `scene_number_reveal.py` | `number_reveal()` — a figure counting up, settling, labelled |
| `scene_quote_card.py` | `quote_card()` — a primary source on screen with its work and year |
| `scene_versus.py` | `versus()` — two accounts side by side, one dismissed |
| `scene_map_zoom.py` | `map_zoom()` — graticule zoom onto real coordinates, pin drop |
| `scene_ramp.py` | `ramp()` — inclined plane, ticks landing at 1 : 3 : 5 : 7 |
| `make_sfx.py` | Synthesises the impact sound. Original audio, no licence |
| `render.py` | Shots → 1080×1920 30fps, burns captions, mixes voice + music + SFX. Takes a storyboard's shots, or its own |
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
| `drop_test()` | built | `drop_test(ratio, height_label, payoff)` |
| `text_beat()` | built | `text_beat(text, hot, kicker)` |
| `number_reveal()` | built | `number_reveal(value, label, sub, prefix, suffix)` |
| `quote_card()` | built | `quote_card(text, who, source)` |
| `versus()` | built | `versus(left, right, winner, verdict)` |
| `map_zoom()` | built | `map_zoom(target, steps, pin_label, outline)` |
| `ramp()` | built | `ramp(angle, intervals, caption)` |

Every scene takes its arguments and an `out=` path, renders frames with
Pillow, hands them to ffmpeg and returns its duration in seconds — which
is what `render.py` needs to place the next shot. Each file also renders
its own example under `python <file>.py`, so a scene can be looked at
without a script to put it in.

`map_zoom()` draws a real graticule and a real scale bar rather than a
picture of land: same rule as the drop test, a diagram and not a
depiction, so it cannot be wrong about a coastline it never claims to
show. Pass `outline=` if you have public-domain geometry to add.

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

Ease-out cubic on all motion. Nothing arrives linearly. Amber is a
budget, not a colour: one idea per scene gets it.

All of that lives in `scene_kit.py` — palette, easing, cached font
loading, word wrap, letter-spaced labels, and the frames-to-mp4 step —
so a new scene is only its drawing code, and the house style cannot
drift one file at a time.

`scene_kit.SAFE_BOTTOM` is the floor: captions.py burns cues at
`MarginV` 22% of the height, and the line itself sits about 110px above
that, so a scene has until y=1388 and no further.

---

## Road to full automation

Each step needs the videos before it to exist — the later stages are built
from patterns that only appear once you have made things. The rule:
**automate a step after doing it by hand five times.** Five runs is roughly
when you know what actually varies between videos rather than what you
assumed would vary.

### Now → video 5: use the library, find what it is missing

The eight scenes are built. What is not known yet is what a storyboard
has to say to drive them — which arguments really vary between videos and
which never do. Videos 2–5 answer that by composing them by hand. Add a
scene when a script needs one that does not exist, not before.

### ~~Video 5~~ done: the back half is `make.py`

```bash
python make.py shots/0002.yaml
```

You write the script and choose the scenes. Everything after is one
command. Per-video time drops from about an hour to the time it takes to
write the storyboard.

This arrived at video 1 rather than video 5, against the five-times
rule, and that was the right call: the back half is ffmpeg orchestration
that video 1 already proved. Four more videos of running it by hand
would have taught nothing about how to run ffmpeg — only about which
scenes a script wants, which is the *next* stage and still waiting.

Two things make the cuts exact rather than eyeballed. Each script line
is synthesised as its own TTS segment, so the voiceover reports where
every line starts and ends — no transcript matching. And every scene can
be measured before it is drawn (`scene_kit.measuring`), so the slack
parameter is solved rather than tuned. Both exist because `render.py`
loops a clip that is too short and truncates one that is too long,
silently: nothing else would catch it.

### ~~Video 15~~ done: auto-storyboard

Not rules in the end — the model picks the scene per line, from a
catalogue generated out of the scene functions' own signatures, so it
cannot invent a scene or an argument that does not exist. `make.py`
then solves every duration, and compresses a scene's pacing when its
content runs longer than the line it sits under.

### Built early: research assistance — *not* verified research

**The verification stays human-in-the-loop, permanently.** What is
built is the drafting. What is not built, and should not be, is anything
that marks a claim true.

The niche is myth-dense. An LLM asked to research Galileo and the Tower of
Pisa produces the myth, confidently, citing blogs that repeat it. During
this project's own development a wrong figure ("twenty years before
Galileo" — wrong by every measure) was written by an assistant and pasted
into a script unchecked. Two humans and it still got through.

Automating that step means shipping fabrications at 60/month on a channel
whose entire premise is that it checks things.

The realistic version, and the one that is built: the machine finds
candidate sources and drafts; a human verifies claims against them and
approves. Two things make that check small rather than a research
session of its own.

The search is **domain-locked**. Each lane's `domains` list is handed
to the web search tool as `allowed_domains`, so a blog repeating the
myth is not discouraged, it is unreachable.

Every claim must carry a **verbatim quote** from one of those pages.
A claim that cannot produce one is dropped before the script sees it,
and the quotes land in `claim_sources.quote` — which is what that
column was always for.

So claims are written to the database as `probable`, never `verified`.
A quote was produced; nobody has yet confirmed it says what the claim
says it says. Moving a row to `verified` is a human action and there is
deliberately no code that does it.

### Then: analytics loop

```
retention_report.py   done: a retention export → line and scene per drop
analytics.py          pull daily stats into analytics_daily
report.py             Telegram digest
```

Log everything. **Do not compute p-values.** At 60 videos/month against
heavy-tailed Shorts view distributions, any A/B test will confidently
report a winner from n=8 and optimise toward noise. Look at directional
patterns over 100+ videos.

---

## Known issues

- **~5s of dead air** at the end of video 1 (`TAIL_SEC` was 2.8). Now
  0.8 in `render.py`. Shorts loop — dead air at the end breaks the loop
  instead of sending viewers round again.
- **No real silence anywhere.** Audio never drops below RMS 0.06, so the
  clap payoff has nothing to land against. Widen the gap in `make_vo.py`
  from 1.2s to 2.0s.
- `08-two-new-sciences-titlepage` was never found. The 1586-vs-1638 beat
  has no visual. Moot once fully animated.
- **The two oldest scenes draw below the safe area.** `scene_timeline.py`
  runs to y=1560 and `falling_bodies.py` puts its `ONE SOUND` payoff at
  y=1690. Captions occupy y=1388–1498 and YouTube's UI covers everything
  under 1498, so in video 1 that payoff line is behind the UI. The six
  newer scenes respect `scene_kit.SAFE_BOTTOM`; these two predate it.
  Raising them recomposes both scenes, so it is a look decision.

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