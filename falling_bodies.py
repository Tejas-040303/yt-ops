"""
Scene library: drop test.

Two lead balls, one many times the mass of the other, released together.
They fall under real physics (s = 1/2 g t^2), which means they stay level
the whole way down and land as one sound. The impact frame is what the
knock in make_sfx.py is synced to.

Nothing here is invented: it is a diagram, not a depiction. No claim is
made about what anyone or anywhere looked like.

Usage as a script (renders the Delft 1586 beat):
    python falling_bodies.py

Usage from a storyboard:
    from falling_bodies import drop_test
    drop_test(ratio=10, height_label="30 ft", payoff="ONE SOUND",
              out="clips/falling.mp4")

Impact lands at hold_before + fall_time seconds into the clip; add that
to the shot's start time to place the SFX in render.py.

Requires: pillow, ffmpeg
"""

from scene_kit import DIM, HOT, INK, W, fade, frame, load_font, render

DROP_TOP = 380         # y of release point
BOARD_Y = 1500         # y of the board
R_SMALL = 26


def drop_test(ratio=10, height_label="30 ft", payoff="ONE SOUND",
              hold_before=0.5, fall_time=1.4, hold_after=0.9,
              out="clips/falling.mp4"):
    """ratio: how many times heavier the big ball is. The radius follows
    the cube root of it, because mass goes as volume -- 10x mass is a
    ball about 2.15x across, not 10x."""
    r_big = round(R_SMALL * ratio ** (1 / 3))
    impact_t = hold_before + fall_time
    total = impact_t + hold_after

    font_lbl = load_font(44)
    font_big = load_font(96)
    x_small, x_big = 380, 700
    span = BOARD_Y - DROP_TOP

    def draw(t):
        im, d = frame()

        # release line and board
        d.line([(140, DROP_TOP), (W - 140, DROP_TOP)], fill=DIM, width=3)
        d.line([(140, BOARD_Y), (W - 140, BOARD_Y)], fill=INK, width=8)

        # fall physics: normalise so the balls arrive exactly at BOARD_Y
        if t < hold_before:
            frac = 0.0
        elif t < impact_t:
            tt = (t - hold_before) / fall_time
            frac = tt * tt                      # s proportional to t^2
        else:
            frac = 1.0

        y_small = DROP_TOP + frac * (span - R_SMALL)
        y_big = DROP_TOP + frac * (span - r_big)

        # motion blur trail once moving
        if 0 < frac < 1:
            for k in range(1, 5):
                back = max(0.0, frac - k * 0.035)
                shade = int(70 - k * 14)
                c = (shade, shade, shade + 6)
                ys = DROP_TOP + back * (span - R_SMALL)
                yb = DROP_TOP + back * (span - r_big)
                d.ellipse([x_small - R_SMALL, ys - R_SMALL,
                           x_small + R_SMALL, ys + R_SMALL], fill=c)
                d.ellipse([x_big - r_big, yb - r_big,
                           x_big + r_big, yb + r_big], fill=c)

        d.ellipse([x_small - R_SMALL, y_small - R_SMALL,
                   x_small + R_SMALL, y_small + R_SMALL], fill=INK)
        d.ellipse([x_big - r_big, y_big - r_big,
                   x_big + r_big, y_big + r_big], fill=INK)

        # mass labels stay pinned at the release line so they never
        # collide with the motion trails
        d.text((x_small, DROP_TOP - 52), "1x",
               font=font_lbl, fill=DIM, anchor="mm")
        d.text((x_big, DROP_TOP - 52), f"{ratio:g}x",
               font=font_lbl, fill=DIM, anchor="mm")

        # impact: one expanding ring from between them, because one sound
        if t >= impact_t:
            age = t - impact_t
            if age < 0.55:
                rr = int(40 + age * 1400)
                left = max(0.0, 1 - age / 0.55)
                cx = (x_small + x_big) // 2
                d.ellipse([cx - rr, BOARD_Y - rr // 3,
                           cx + rr, BOARD_Y + rr // 3],
                          outline=fade(HOT, left),
                          width=max(2, int(9 * left)))
            if 0.06 < age and payoff:
                a = min(1.0, (age - 0.06) / 0.3)
                d.text((W // 2, BOARD_Y + 190), payoff,
                       font=font_big, fill=fade(HOT, a), anchor="mm")

        # height marker
        d.text((W - 150, (DROP_TOP + BOARD_Y) // 2), height_label,
               font=font_lbl, fill=DIM, anchor="lm")

        return im

    return render(draw, total, out, "tmp_falling")


if __name__ == "__main__":
    drop_test(ratio=10, height_label="30 ft", payoff="ONE SOUND",
              out="clips/falling.mp4")
