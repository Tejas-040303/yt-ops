"""
Scene library: quote card.

A primary source on screen, attributed, revealed a line at a time so the
eye tracks the second voice reading it.

The channel's whole claim is that it checks things. Showing the sentence
somebody actually wrote, with the book and the year under it, is the
cheapest way to make that visible -- and it is the scene that pairs with
the George segments in make_vo.py.

Usage as a script (renders the Stevin example):
    python scene_quote_card.py

Usage from a storyboard:
    from scene_quote_card import quote_card
    quote_card("their two sounds seem to be a single clap",
               who="Simon Stevin",
               source="De Beghinselen der Weeghconst, 1586",
               out="clips/05-quote.mp4")
"""

from scene_kit import (DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, W, ease,
                       fade, frame, lerp, load_font, render, tracked, wrap)

SIZES = [66, 60, 54, 48, 44, 40, 36]
LINE_RATIO = 1.42
SPINE_X = MARGIN + 6
TEXT_X = MARGIN + 52
MARK_TOP = SAFE_TOP + 30
TEXT_TOP = SAFE_TOP + 200
ATTRIB_GAP = 96


def quote_card(text, who, source=None, lead=0.25, per_line=0.5, hold=1.8,
               out="clips/quote.mp4"):
    """text: the quotation, verbatim. who: who wrote it. source: work and
    year, which is what turns a nice sentence into a citation."""
    wrap_w = W - TEXT_X - MARGIN
    avail = SAFE_BOTTOM - TEXT_TOP - ATTRIB_GAP - 120

    for size in SIZES:
        fnt = load_font(size, bold=False)
        lines = wrap(text, fnt, wrap_w)
        if len(lines) * size * LINE_RATIO <= avail:
            break

    line_h = size * LINE_RATIO
    block_h = line_h * len(lines)

    # Centre the whole composition -- mark, text, attribution -- in the
    # band above the captions, so a two-line quote is not stranded at the
    # top of the frame the way a six-line one is not.
    comp_bottom = TEXT_TOP + block_h + ATTRIB_GAP + 70
    centre = (SAFE_TOP + SAFE_BOTTOM) / 2
    shift = max(0.0, centre - (MARK_TOP + comp_bottom) / 2)
    mark_top, text_top = MARK_TOP + shift, TEXT_TOP + shift

    f_mark = load_font(230, bold=False)
    f_who = load_font(46)
    f_src = load_font(36, bold=False)

    attrib_at = lead + len(lines) * per_line
    total = attrib_at + 0.5 + hold

    def draw(t):
        im, d = frame()

        # Decoration, not content: a dim amber quote mark, well under the
        # brightness of anything you are meant to read.
        d.text((MARGIN - 8, mark_top), "“", font=f_mark,
               fill=fade(HOT, 0.3 * ease(t / 0.4)), anchor="la")

        # The spine grows with the reading, same device as the timeline.
        grown = ease((t - lead) / max(0.001, len(lines) * per_line))
        if grown > 0:
            d.line([(SPINE_X, text_top - 28),
                    (SPINE_X, text_top - 28 + grown * (block_h + 20))],
                   fill=HOT, width=5)

        for i, line in enumerate(lines):
            a = ease((t - lead - i * per_line) / 0.45)
            if a <= 0:
                continue
            d.text((TEXT_X + lerp(18, 0, a), text_top + i * line_h), line,
                   font=fnt, fill=fade(INK, a), anchor="la")

        aa = ease((t - attrib_at) / 0.45)
        if aa > 0:
            y = text_top + block_h + ATTRIB_GAP
            tracked(d, (TEXT_X, y), f"— {who.upper()}", f_who,
                    fade(INK, aa), track=6, anchor="lm")
            if source:
                sa = ease((t - attrib_at - 0.2) / 0.45)
                d.text((TEXT_X, y + 56), source, font=f_src,
                       fill=fade(DIM, sa), anchor="lm")

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    quote_card(
        "two spheres of lead, the one ten times larger and heavier than "
        "the other... their two sounds seem to be a single clap",
        who="Simon Stevin",
        source="De Beghinselen der Weeghconst, 1586",
        out="clips/05-quote.mp4")
