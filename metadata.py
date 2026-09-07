"""
Build the upload metadata for a video.

Pulls asset attributions from db.sqlite so CC licence conditions are
satisfied automatically, and folds in the sources for the claims.

Usage:  python metadata.py
Writes: out/<CODE>-metadata.txt   (paste straight into YouTube Studio)
"""

import os
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


def attributions():
    """Required credit lines, straight from the asset manifest."""
    if not os.path.exists(DB):
        return [], ["db.sqlite not found -- attributions NOT included"]

    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            "SELECT local_path, license, attribution_required, "
            "attribution_text, source_url, commercial_ok "
            "FROM assets WHERE video_id = ?", (VIDEO_ID,)
        ).fetchall()
    except sqlite3.OperationalError as e:
        return [], [f"could not read assets table: {e}"]
    finally:
        con.close()

    if not rows:
        return [], [f"no assets logged for video_id={VIDEO_ID} "
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    credits, warnings = attributions()

    parts = [HOOK_LINE, ""]

    parts.append("Sources:")
    for name, url in SOURCES:
        parts.append(f"- {name}")
        parts.append(f"  {url}")
    parts.append("")

    if credits:
        parts.append("Image credits:")
        parts += [f"- {c}" for c in credits]
        parts.append("")

    parts.append(" ".join(HASHTAGS))

    description = "\n".join(parts)

    out = os.path.join(OUT_DIR, f"{CODE}-metadata.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("=== TITLE OPTIONS (pick one) ===\n")
        for i, t in enumerate(TITLES, 1):
            f.write(f"{i}. [{len(t):>2} chars] {t}\n")
        f.write("\n=== DESCRIPTION ===\n")
        f.write(description)
        f.write("\n\n=== UPLOAD CHECKLIST ===\n")
        f.write("[ ] Tick 'Altered or synthetic content' in Studio\n")
        f.write("[ ] Set to Not made for kids\n")
        f.write("[ ] Category: Education\n")
        f.write("[ ] Schedule, do not publish immediately\n")

    print(f"wrote {out}")
    print(f"  {len(TITLES)} titles, {len(SOURCES)} sources, "
          f"{len(credits)} attributions")

    over = [t for t in TITLES if len(t) > 60]
    for t in over:
        print(f"  NOTE: title over 60 chars, will truncate on mobile: {t!r}")

    for w in warnings:
        print(f"  WARNING: {w}")


if __name__ == "__main__":
    main()