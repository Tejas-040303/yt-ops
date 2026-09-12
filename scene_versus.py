"""
Scene library: versus.

Two things side by side, with an optional verdict that dims one of them.

This is the myth_bust angle rendered as a picture: config.yaml labels
accounts by stance, and where `popular` and `consensus` disagree that gap
is the video. versus() is where the gap goes on screen.

Usage as a script (renders the Galileo example):
    python scene_versus.py

Usage from a storyboard:
    from scene_versus import versus
    versus(("THE STORY", ["Pisa, 1589", "one account"]),
           ("THE RECORD", ["Delft, 1586", "published at the time"]),
           winner="right", verdict="only one was written down",
           out="clips/06-versus.mp4")
"""

from scene_kit import (DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, W, blend,
                       ease, fade, fit, fit_tracked, frame, lerp, load_font,
                       render, tracked, wrap)

GAP = 110
COL_W = (W - 2 * MARGIN - GAP) // 2
TITLE_SIZES = [76, 66, 58, 50, 44]
TITLE_H = 76
LINE_SIZE = 38
LINE_H = 62
PAD = 80               # divider overhang above and below the columns
DIVIDER_TIME = 0.55
SIDE_LAG = 0.22        # the right side arrives after the left one
LOSER = 0.34           # how far the dismissed side fades back toward BG


def _side(spec):
    if isinstance(spec, str):
        return spec, []
    title, lines = spec
    return title, list(lines)


def versus(left, right, winner=None, verdict="", lead=0.2, hold=1.6,
           out="clips/versus.mp4"):
    """left/right: a title, or (title, [supporting lines]).
    winner: "left", "right" or None. verdict: one line under the columns."""
    if winner not in (None, "left", "right"):
        raise ValueError('winner must be "left", "right" or None')

    l_title, l_lines = _side(left)
    r_title, r_lines = _side(right)

    f_title, _ = fit(f"{l_title} {r_title}", COL_W, TITLE_SIZES, max_lines=2)
    f_line = load_font(LINE_SIZE, bold=False)
    f_vs = load_font(40)
    f_verdict, v_track = fit_tracked(verdict.upper(), W - 2 * MARGIN,
                                     [46, 42, 38, 34, 30, 26], track=9)

    cols = {}
    for name, title, body in (("left", l_title, l_lines),
                              ("right", r_title, r_lines)):
        flat = []
        for item in body:
            flat += wrap(item, f_line, COL_W)
        cols[name] = (wrap(title, f_title, COL_W), flat)

    # The divider hugs the columns instead of spanning the safe area: a
    # rule running a long way past the last line reads as an empty frame
    # with some text in it.
    n_title = max(len(t) for t, _ in cols.values())
    n_body = max(len(b) for _, b in cols.values())
    block_h = n_title * TITLE_H + (60 + n_body * LINE_H if n_body else 0)
    block_top = (SAFE_TOP + SAFE_BOTTOM) / 2 - 40 - block_h / 2
    title_y = block_top + TITLE_H / 2
    lines_y = block_top + n_title * TITLE_H + 60 + LINE_H / 2

    top, bottom = block_top - PAD, block_top + block_h + PAD
    mid = (top + bottom) / 2
    verdict_y = min(SAFE_BOTTOM - 50, bottom + 95)
    cx = {"left": MARGIN + COL_W // 2, "right": W - MARGIN - COL_W // 2}

    rows = n_title + n_body
    settled = lead + SIDE_LAG + rows * 0.1 + 0.5
    total = settled + (0.9 if winner else 0.0) + hold

    def draw(t):
        im, d = frame()

        # Divider first: the frame is a comparison before it is anything
        # else. It parts around a VS badge at the midpoint.
        grown = ease((t - lead) / DIVIDER_TIME)
        cur = top + grown * (bottom - top)
        d.line([(W / 2, top), (W / 2, min(cur, mid - 48))], fill=DIM, width=3)
        if cur > mid + 48:
            d.line([(W / 2, mid + 48), (W / 2, cur)], fill=DIM, width=3)
        if grown > 0.55:
            tracked(d, (W // 2, mid), "VS", f_vs,
                    fade(DIM, ease((grown - 0.55) / 0.45)), track=6)

        vd = ease((t - settled) / 0.5) if winner else 0.0

        for name, (title_lines, body_lines) in cols.items():
            start = lead + (SIDE_LAG if name == "right" else 0.0)
            drift = -60 if name == "left" else 60
            lost = winner and name != winner
            level = lerp(1.0, LOSER, vd) if lost else 1.0
            won = winner and name == winner
            colour = blend(INK, HOT, vd) if won else INK

            for i, line in enumerate(title_lines):
                a = ease((t - start - i * 0.1) / 0.5)
                if a <= 0:
                    continue
                d.text((cx[name] + lerp(drift, 0, a), title_y + i * TITLE_H),
                       line, font=f_title, fill=fade(colour, a * level),
                       anchor="mm")

            for i, line in enumerate(body_lines):
                a = ease((t - start - (len(title_lines) + i) * 0.1) / 0.5)
                if a <= 0:
                    continue
                d.text((cx[name] + lerp(drift, 0, a), lines_y + i * LINE_H),
                       line, font=f_line, fill=fade(DIM, a * level),
                       anchor="mm")

        if verdict and vd > 0:
            tracked(d, (W // 2, verdict_y), verdict.upper(), f_verdict,
                    fade(HOT, ease((t - settled - 0.25) / 0.5)), track=v_track)

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    versus(("THE STORY", ["Pisa, 1589",
                          "one account",
                          "written 65 years later"]),
           ("THE RECORD", ["Delft, 1586",
                           "published by the man who did it",
                           "and his witness"]),
           winner="right",
           verdict="only one was written down",
           out="clips/06-versus.mp4")
