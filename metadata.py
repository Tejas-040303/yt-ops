"""
Build the upload metadata for a video.

Pulls asset attributions from db.sqlite so CC licence conditions are
satisfied automatically, and folds in the sources for the claims.

Given the storyboard (make.py passes it), it also writes the fact check
you do before uploading: every figure the video shows or says, each
marked with whether research/NNNN-claims.json contains it, and every
quotation, marked with whether it is word for word in the claims. A
figure that is not in the claims came from nowhere -- the one error the
rest of the pipeline cannot catch once it is on screen.

Usage:  python metadata.py
Writes: out/<CODE>-metadata.txt   (paste straight into YouTube Studio)
"""

import json
import os
import re
import sqlite3

CODE = "0001-galileo-pisa-myth-bust"
VIDEO_ID = 1
DB = "db.sqlite"
OUT_DIR = "out"

# ---------------------------------------------------------------
# Titles. Write several, pick one at upload time.
# Keep under ~60 chars: Shorts truncates hard on mobile.
# ---------------------------------------------------------------
TITLES = [
    "Galileo never did his most famous experiment",
    "The Pisa experiment has one source. He wasn't born yet.",
    "Someone beat Galileo to it by 52 years",
    "The man who tested gravity before Galileo",
    "Why you've never heard of Simon Stevin",
]

HOOK_LINE = (
    "The Leaning Tower story comes from one man, writing in 1654, "
    "twelve years after Galileo died. But the experiment did happen "
    "-- in Delft, in 1586."
)

# Sources for the claims made in the video.
SOURCES = [
    ("Stanford Encyclopedia of Philosophy: Galileo Galilei",
     "https://plato.stanford.edu/entries/galileo/"),
    ("MacTutor: Simon Stevin",
     "https://mathshistory.st-andrews.ac.uk/Biographies/Stevin/"),
    ("Linda Hall Library: Simon Stevin",
     "https://www.lindahall.org/about/news/scientist-of-the-day/simon-stevin/"),
    ("Simon Stevin, De Beghinselen der Weeghconst (1586)",
     "https://www.canonvanvlaanderen.be/en/events/simon-stevin/"),
]

HASHTAGS = ["#history", "#science", "#galileo", "#physics", "#didyouknow"]


def attributions(video_id=None):
    """Required credit lines, straight from the asset manifest."""
    video_id = VIDEO_ID if video_id is None else video_id
    if not os.path.exists(DB):
        return [], ["db.sqlite not found -- attributions NOT included"]

    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            "SELECT local_path, license, attribution_required, "
            "attribution_text, source_url, commercial_ok "
            "FROM assets WHERE video_id = ?", (video_id,)
        ).fetchall()
    except sqlite3.OperationalError as e:
        return [], [f"could not read assets table: {e}"]
    finally:
        con.close()

    if not rows:
        return [], [f"no assets logged for video_id={video_id} "
                    f"-- run log_assets.py"]

    lines, warnings = [], []
    for path, lic, req, text, url, ok in rows:
        if not ok:
            warnings.append(f"ASSET NOT CLEARED FOR COMMERCIAL USE: {path}")
        if req:
            if text:
                lines.append(f"{text} - {url}")
            else:
                warnings.append(
                    f"{path} requires attribution but attribution_text "
                    f"is empty -- LEGAL CONDITION UNMET")
    return lines, warnings


# --- the fact check ------------------------------------------------

UNITS = ("one|two|three|four|five|six|seven|eight|nine")
TEENS = ("ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
         "eighteen|nineteen")
TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
# "one" alone is left out: "one person" is not a figure, "fifty-one" is.
FIGURE = re.compile(
    rf"\d+(?:[.,]\d+)*%?|\b(?:(?:{TENS})(?:-(?:{UNITS}))?|"
    rf"(?:{UNITS.replace('one|', '')})|{TEENS}|hundred|thousand|million|"
    rf"billion|dozen)\b", re.I)
WORD_VALUE = {w: i for i, w in enumerate(UNITS.split("|"), 1)}
WORD_VALUE.update({w: i for i, w in enumerate(TEENS.split("|"), 10)})
WORD_VALUE.update({w: i * 10 for i, w in enumerate(TENS.split("|"), 2)})

# Scene arguments drawn on screen as numbers. Every other number in a
# shot's args is layout or timing (a map span, a pace) and never shown.
SHOWN_NUMBERS = {"value", "ratio", "events", "gap"}


def _digits(tok):
    """'fifty-two' -> '52', '1,586' -> '1586'; None for 'hundred'."""
    t = tok.lower().replace(",", "").rstrip("%")
    if t[:1].isdigit():
        return t
    total = sum(WORD_VALUE.get(part, 0) for part in t.split("-"))
    return str(total) if total else None


def _shown(v, key=None):
    """Every string in a shot's args, and the numbers it draws."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, bool):
        return
    elif isinstance(v, (int, float)):
        if key in SHOWN_NUMBERS:
            yield f"{v:g}"
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _shown(x, k)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _shown(x, key)


def _context(text, start, end, width=56):
    """About width characters around the match, cut between words."""
    a = max(0, start - width // 2)
    b = min(len(text), a + width)
    if a:
        a = text.find(" ", a, start) + 1 or a
    if b < len(text):
        b = text.rfind(" ", end, b) if text.rfind(" ", end, b) > 0 else b
    snip = " ".join(text[a:b].split())
    return ("..." if a else "") + snip + ("..." if b < len(text) else "")


def figures(board):
    """[(figure, where)] for every figure spoken or shown, first seen first."""
    out, seen = [], set()

    def add(text, where):
        for m in FIGURE.finditer(text):
            key = _digits(m.group()) or m.group().lower()
            if key not in seen:
                seen.add(key)
                out.append((m.group(), f'{where}: "{_context(text, *m.span())}"'))

    for i, line in enumerate(board.get("script", [])):
        add(line["text"], f"line {i}")
    for j, shot in enumerate(board.get("shots", []), 1):
        for text in _shown(shot.get("args", {})):
            add(text, f"shot {j} {shot['scene']}")
    return out


def quotations(board):
    """Every quotation, spoken (voice: quote) or on a quote_card."""
    qs = [l["text"] for l in board.get("script", [])
          if l.get("voice") == "quote"]
    qs += [s["args"]["text"] for s in board.get("shots", [])
           if s["scene"] == "quote_card" and s.get("args", {}).get("text")]
    return list(dict.fromkeys(" ".join(q.split()) for q in qs))


def _flat(t):
    return " ".join(t.replace("\u2019", "'").replace("\u201c", '"')
                    .replace("\u201d", '"').lower().split())


def fact_check(board, claims_path, notes_path):
    """The checklist lines, and how many figures are not in the claims."""
    lines = ["=== BEFORE YOU UPLOAD: THE FACT CHECK ===",
             "Nothing in the pipeline can tell whether a claim is true.",
             "This is where that happens.", ""]
    claims = None
    if claims_path and os.path.exists(claims_path):
        claims = json.load(open(claims_path, encoding="utf-8"))["claims"]
    if notes_path and os.path.exists(notes_path):
        lines.append(f"[ ] Read {notes_path}, the section on what could not "
                     f"be established")
    if board is None:
        lines.append("[ ] Check every figure and quotation in the video "
                     "against its source")
        return lines, 0
    if claims is None:
        lines.append("[ ] No claims file for this video -- check each of "
                     "these against its source by hand:")
    else:
        lines.append(f"[ ] Each figure is backed by a source that says it "
                     f"(see {claims_path}):")
    corpus = _flat(" ".join(f"{c['text']} {c['quote']}" for c in claims or []))
    missing = 0
    for fig, where in figures(board):
        mark = ""
        if claims is not None:
            forms = {fig.lower(), _digits(fig) or fig.lower()}
            found = any(re.search(rf"\b{re.escape(f)}\b", corpus)
                        for f in forms)
            mark = "in claims     " if found else "NOT IN CLAIMS "
            missing += not found
        lines.append(f"    [ ] {fig:<12} {mark}{where}")
    quotes = quotations(board)
    if quotes:
        lines.append("[ ] Each quotation is word for word from its source:")
        exact = {_flat(c["quote"]) for c in claims or []}
        for q in quotes:
            mark = ""
            if claims is not None:
                mark = ("  verbatim in claims" if _flat(q) in exact
                        else "  NOT VERBATIM IN CLAIMS")
            lines.append(f'    [ ] "{q}"{mark}')
    return lines, missing


def main(code=None, titles=None, hook=None, sources=None, hashtags=None,
         video_id=None, out_dir=None, board=None, research_dir="research"):
    """Called bare it writes video 1's metadata; make.py passes a
    storyboard's instead."""
    code = CODE if code is None else code
    titles = TITLES if titles is None else titles
    hook = HOOK_LINE if hook is None else hook
    sources = SOURCES if sources is None else sources
    hashtags = HASHTAGS if hashtags is None else hashtags
    out_dir = OUT_DIR if out_dir is None else out_dir

    os.makedirs(out_dir, exist_ok=True)
    credits, warnings = attributions(video_id)

    parts = [hook, ""]

    parts.append("Sources:")
    for name, url in sources:
        parts.append(f"- {name}")
        parts.append(f"  {url}")
    parts.append("")

    if credits:
        parts.append("Image credits:")
        parts += [f"- {c}" for c in credits]
        parts.append("")

    parts.append(" ".join(hashtags))

    description = "\n".join(parts)

    seq = code[:4]
    check, missing = fact_check(
        board, os.path.join(research_dir, f"{seq}-claims.json"),
        os.path.join(research_dir, f"{seq}-notes.md"))

    out = os.path.join(out_dir, f"{code}-metadata.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("=== TITLE OPTIONS (pick one) ===\n")
        for i, t in enumerate(titles, 1):
            f.write(f"{i}. [{len(t):>2} chars] {t}\n")
        f.write("\n=== DESCRIPTION ===\n")
        f.write(description)
        f.write("\n\n" + "\n".join(check) + "\n")
        f.write("\n=== UPLOAD CHECKLIST ===\n")
        f.write("[ ] Tick 'Altered or synthetic content' in Studio\n")
        f.write("[ ] Set to Not made for kids\n")
        f.write("[ ] Category: Education\n")
        f.write("[ ] Schedule, do not publish immediately\n")

    print(f"wrote {out}")
    print(f"  {len(titles)} titles, {len(sources)} sources, "
          f"{len(credits)} attributions")

    over = [t for t in titles if len(t) > 60]
    for t in over:
        print(f"  NOTE: title over 60 chars, will truncate on mobile: {t!r}")

    for w in warnings:
        print(f"  WARNING: {w}")

    if missing:
        print(f"  WARNING: {missing} figure(s) on screen are not in the "
              f"claims -- see the fact check in {out}")

    return out


if __name__ == "__main__":
    main()