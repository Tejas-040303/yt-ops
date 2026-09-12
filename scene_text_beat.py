"""
Scene library: text beat.

A full-frame statement, one line of the script held still while the words
land one at a time. This is the pattern break -- on a feed of constant
motion the strongest thing available is a frame that stops moving.

Usage as a script (renders the Galileo example):
    python scene_text_beat.py

Usage from a storyboard:
    from scene_text_beat import text_beat
    text_beat("He wasn't there.", hot="wasn't",
              out="clips/03-text-beat.mp4")
"""

from scene_kit import (DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, W,
                       ease, fade, fit, frame, lerp, load_font, measure,
                       render, tracked)

SIZES = [140, 124, 110, 96, 84, 74, 64]
RISE = 26              # px each word travels up as it arrives
RAISE_TIME = 0.42      # seconds for one word to land


def _key(word):
    return word.strip(".,;:!?\"'()[]—’").lower()


def text_beat(text, hot=(), kicker="", lead=0.35, per_word=0.13, hold=1.3,
              max_lines=3, out="clips/text_beat.mp4"):
    """text: the statement. hot: word or words to set in amber.

    lead is silence before the first word -- the break only reads as a
    break if the frame is empty for a moment first.
    """
    if isinstance(hot, str):
        hot = hot.split()
    hot = {_key(w) for w in hot}

    fnt, lines = fit(text, W - 2 * MARGIN, SIZES, max_lines)
    size = fnt.size if hasattr(fnt, "size") else SIZES[-1]
    f_kicker = load_font(38)
    space = measure(" ", fnt)
    line_h = size * 1.24

    # Lay the words out once, up front: position is static, only the
    # arrival animates.
    block_h = line_h * len(lines)
    top = (SAFE_TOP + SAFE_BOTTOM) / 2 - block_h / 2 + line_h / 2
    placed, idx = [], 0
    for li, line in enumerate(lines):
        words = line.split()
        widths = [measure(w, fnt) for w in words]
        x = (W - (sum(widths) + space * (len(words) - 1))) / 2
        for word, wid in zip(words, widths):
            placed.append((word, x, top + li * line_h, idx))
            x += wid + space
            idx += 1

    n_words = len(placed)
    total = lead + (n_words - 1) * per_word + RAISE_TIME + hold

    def draw(t):
        im, d = frame()

        if kicker:
            a = ease((t - 0.1) / 0.5)
            tracked(d, (W // 2, SAFE_TOP + 40), kicker.upper(), f_kicker,
                    fade(DIM, a), track=10)

        for word, x, y, i in placed:
            a = ease((t - lead - i * per_word) / RAISE_TIME)
            if a <= 0:
                continue
            colour = HOT if _key(word) in hot else INK
            d.text((x, y + lerp(RISE, 0, a)), word,
                   font=fnt, fill=fade(colour, a), anchor="ls")

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    text_beat("He wasn't there.", hot="wasn't",
              kicker="Vincenzo Viviani, 1654",
              out="clips/03-text-beat.mp4")
