"""
Build captions.ass from vo.json word timings.

Usage:  python captions.py

Handles the long-token problem: Whisper collapses spoken numbers
("sixteen thirty-eight") into one token ("1638") spanning 2+ seconds.
Left alone that freezes on screen and looks broken, so any token longer
than MAX_TOKEN_SEC is split into evenly-timed chunks.
"""

import json
import os

VO_JSON = "vo.json"
OUT = "captions.ass"

W, H = 1080, 1920
MAX_WORDS = 3           # words visible at once
MAX_CHARS = 18          # break earlier if the line would be too wide
MAX_TOKEN_SEC = 0.8     # split anything held longer than this
MIN_CUE_SEC = 0.25      # never flash a cue faster than this
SAFE_BOTTOM_PCT = 22    # keep clear of the YouTube UI overlay

FONT = "Arial"          # swap to Inter once installed system-wide
FONT_SIZE = 76

MARGIN_V = int(H * SAFE_BOTTOM_PCT / 100)

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(seconds):
    """Seconds -> ASS timestamp h:mm:ss.cc"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def mark_long_tokens(words):
    """Flag tokens held longer than MAX_TOKEN_SEC.

    Whisper collapses a spoken year ("sixteen fifty-four") into one token
    ("1654") spanning the whole utterance. We cannot recover the sub-words,
    so instead of grouping it with neighbours -- which would freeze four
    words on screen -- we give it a cue of its own. A date held alone reads
    as deliberate emphasis.
    """
    for w in words:
        w["solo"] = (w["end"] - w["start"]) > MAX_TOKEN_SEC
    return words


MAX_CHARS = 20          # break early if a cue would overflow the line


def group(words, max_words=MAX_WORDS):
    """Chunk words into cues.

    Break early on sentence-ending punctuation, and always isolate a
    long-held token into a cue of its own.
    """
    cues, buf = [], []
    for w in words:
        if w.get("solo"):
            if buf:
                cues.append(buf)
                buf = []
            cues.append([w])
            continue
        buf.append(w)
        ends_sentence = w["w"].rstrip().endswith((".", "!", "?"))
        too_long = len(" ".join(x["w"] for x in buf)) >= MAX_CHARS
        if len(buf) >= max_words or ends_sentence or too_long:
            cues.append(buf)
            buf = []
    if buf:
        cues.append(buf)
    return cues


def main():
    if not os.path.exists(VO_JSON):
        raise SystemExit(f"{VO_JSON} not found -- run make_vo.py first")

    data = json.load(open(VO_JSON, encoding="utf-8"))
    words = data["words"]

    words = mark_long_tokens(words)
    cues = group(words)

    lines = []
    for cue in cues:
        start = cue[0]["start"]
        end = cue[-1]["end"]
        if end - start < MIN_CUE_SEC:
            end = start + MIN_CUE_SEC
        text = " ".join(w["w"] for w in cue).strip().upper()
        text = text.replace("\n", " ")
        lines.append(
            f"Dialogue: 0,{ts(start)},{ts(end)},Main,,0,0,0,,{text}"
        )

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write("\n".join(lines) + "\n")

    dur = words[-1]["end"] if words else 0
    print(f"{OUT}: {len(cues)} cues over {dur:.1f}s")
    solo = sum(1 for w in words if w.get("solo"))
    if solo:
        print(f"  {solo} long tokens isolated into their own cues "
              f"(spoken numbers/dates)")


if __name__ == "__main__":
    main()