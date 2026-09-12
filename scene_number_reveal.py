"""
Scene library: number reveal.

One figure, arriving with weight. The value rolls up, settles slightly
larger than it ends, a rule lands under it and the label follows.

A channel about how things were found out is a channel about
measurements, so this scene runs constantly: 30 feet, 10 times, 12 years,
299,792,458 metres per second.

Usage as a script (renders the Galileo example):
    python scene_number_reveal.py

Usage from a storyboard:
    from scene_number_reveal import number_reveal
    number_reveal(30, "FEET", sub="Nieuwe Kerk, Delft",
                  out="clips/04-number.mp4")

Pass a year as a string -- number_reveal("1586", ...) -- because you do
not count up to a year and 1586 must not gain a comma.
"""

from scene_kit import (DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, W, ease,
                       fade, fit, frame, lerp, load_font, measure, render,
                       tracked)

SIZES = [260, 230, 200, 176, 152, 132, 116]
OVERSHOOT = 1.22       # size it arrives at, before settling to 1.0
RULE_TIME = 0.32
LABEL_LAG = 0.12


def _text(value, t_frac, prefix, suffix, decimals):
    """The string on screen at count progress t_frac (0..1)."""
    if isinstance(value, str):
        body = value
    else:
        cur = value * t_frac
        body = f"{cur:,.{decimals}f}" if decimals else f"{round(cur):,}"
    return f"{prefix}{body}{suffix}"


def number_reveal(value, label, sub=None, prefix="", suffix="",
                  count=True, count_time=0.75, hold=1.5, decimals=0,
                  out="clips/number.mp4"):
    """value: number (counts up) or string (lands whole). label: the unit
    or the thing being counted. sub: an optional source-ish second line."""
    final = _text(value, 1.0, prefix, suffix, decimals)
    fnt, _ = fit(final, W - 2 * MARGIN, SIZES)
    base = fnt.size if hasattr(fnt, "size") else SIZES[-1]
    f_label = load_font(46)
    f_sub = load_font(38, bold=False)

    counting = count and not isinstance(value, str)
    mid_y = (SAFE_TOP + SAFE_BOTTOM) / 2 - 60
    rule_y = mid_y + base * 0.62
    half = measure(final, fnt) / 2

    total = count_time + RULE_TIME + LABEL_LAG + hold

    def draw(t):
        im, d = frame()

        a = ease(t / count_time)
        size = max(8, int(round(base * lerp(OVERSHOOT, 1.0, a))))
        d.text((W // 2, mid_y), _text(value, a if counting else 1.0,
                                      prefix, suffix, decimals),
               font=load_font(size), fill=fade(INK, min(1.0, a * 1.6)),
               anchor="mm")

        # The rule lands when the number does, and carries the amber: it
        # is the thing that makes the figure feel set down rather than
        # merely displayed.
        r = ease((t - count_time) / RULE_TIME)
        if r > 0:
            d.line([(W / 2 - half * r, rule_y), (W / 2 + half * r, rule_y)],
                   fill=HOT, width=8)

        la = ease((t - count_time - LABEL_LAG) / 0.4)
        if la > 0:
            tracked(d, (W // 2, rule_y + 86), label.upper(), f_label,
                    fade(HOT, la), track=12)
            if sub:
                sa = ease((t - count_time - LABEL_LAG - 0.18) / 0.4)
                d.text((W // 2, rule_y + 160), sub, font=f_sub,
                       fill=fade(DIM, sa), anchor="mm")

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    number_reveal(30, "feet", sub="Nieuwe Kerk, Delft, 1586",
                  out="clips/04-number.mp4")
