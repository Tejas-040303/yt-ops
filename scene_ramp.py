"""
Scene library: inclined plane.

A ball rolls down a ramp and ticks light up as it passes them. The ticks
are not evenly spaced -- they mark where the ball is after each equal
interval of time, so the distances come out 1 : 3 : 5 : 7. That odd-number
pattern is the actual result, and it is the whole reason the ramp beats
the tower: it slows gravity down until a water clock can measure it.

The geometry is computed from the physics (s proportional to t squared),
not drawn by eye, so the picture cannot disagree with the script.

Usage as a script (renders the Galileo example):
    python scene_ramp.py

Usage from a storyboard:
    from scene_ramp import ramp
    ramp(angle=25, intervals=4, out="clips/08-ramp.mp4")
"""

import math

from scene_kit import (DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, W,
                       ease, fade, fit_tracked, frame, load_font, render,
                       tracked)

RUN = W - 2 * MARGIN - 60      # horizontal length of the ramp
TOP_Y = 560                    # y of the high end
BALL_R = 22
BAR_DROP = 150                 # measure bar, below the ramp's low end
FLASH = 0.28                   # how long a tick burns amber as it is passed


def ramp(angle=25, intervals=4, roll=1.9, lead=0.45, hold=1.8,
         caption="distance in equal times", out="clips/ramp.mp4"):
    """angle: degrees below horizontal. intervals: equal time beats."""
    if not 2 <= intervals <= 8:
        raise ValueError("intervals outside 2..8 stops reading as a pattern")
    if not 5 <= angle <= 45:
        raise ValueError("angle outside 5..45 degrees does not fit the frame")

    th = math.radians(angle)
    ax, ay = MARGIN + 30, TOP_Y
    bx, by = ax + RUN, TOP_Y + RUN * math.tan(th)
    nx, ny = math.sin(th) * BALL_R, -math.cos(th) * BALL_R   # ramp normal

    f_beat = load_font(30)
    f_odd = load_font(40)
    f_ratio = load_font(52)
    f_angle = load_font(34)
    f_cap, cap_track = fit_tracked(caption.upper(), W - 2 * MARGIN,
                                   [40, 36, 32, 28, 24], track=10)

    # Distance goes as t squared, so after k of n equal beats the ball has
    # covered (k/n)^2 of the ramp. Every position on screen comes from
    # this one line.
    marks = [(k / intervals) ** 2 for k in range(intervals + 1)]
    odds = [2 * k - 1 for k in range(1, intervals + 1)]

    def on_ramp(frac):
        return ax + frac * RUN, ay + frac * (by - ay)

    bar_y = by + BAR_DROP
    cap_y = bar_y + 150
    ratio_y = min(SAFE_BOTTOM - 40, cap_y + 80)
    ratio = "  :  ".join(str(o) for o in odds)

    beats_done = lead + roll
    brackets_at = beats_done + 0.25
    total = brackets_at + intervals * 0.16 + 0.55 + hold

    def draw(t):
        im, d = frame()
        rolling = max(0.0, min(1.0, (t - lead) / roll))
        travelled = rolling ** 2

        # the plane, and the height it falls through
        d.line([(ax, by), (bx + 40, by)], fill=DIM, width=4)
        d.line([(ax, ay), (ax, by)], fill=fade(DIM, 0.45), width=3)
        d.line([(ax, ay), (bx, by)], fill=INK, width=6)
        # Pillow measures arcs clockwise from 3 o'clock, so the wedge
        # between the ground (due left) and the ramp is 180 -> 180+angle.
        d.arc([bx - 100, by - 100, bx + 100, by + 100],
              180, 180 + angle, fill=DIM, width=3)
        d.text((bx - 118, by - 26), f"{angle}°", font=f_angle,
               fill=DIM, anchor="rm")

        # beat dots: the water clock. One fills per equal interval.
        for k in range(intervals):
            done = rolling * intervals >= k + 1
            age = t - lead - roll * (k + 1) / intervals
            col = HOT if done and age < FLASH else (
                fade(HOT, 0.55) if done else fade(DIM, 0.5))
            d.ellipse([bx - 26 - (intervals - 1 - k) * 44, SAFE_TOP + 78,
                       bx - 6 - (intervals - 1 - k) * 44, SAFE_TOP + 98],
                      fill=col)
        tracked(d, (ax + 6, SAFE_TOP + 88), "WATER CLOCK", f_beat,
                fade(DIM, 0.9), track=8, anchor="lm")

        # ticks across the ramp, lit as the ball reaches them
        for k, frac in enumerate(marks[1:], start=1):
            px, py = on_ramp(frac)
            passed = travelled >= frac - 1e-9
            age = t - lead - roll * k / intervals
            col = HOT if passed and age < FLASH else (
                INK if passed else fade(DIM, 0.55))
            d.line([(px + nx * 0.9, py + ny * 0.9),
                    (px - nx * 0.9, py - ny * 0.9)], fill=col, width=5)

        # the ball, with the same trail language as falling_bodies.py
        if rolling > 0:
            for g in range(1, 4):
                gf = max(0.0, (rolling - g * 0.045)) ** 2
                gx, gy = on_ramp(gf)
                shade = int(70 - g * 16)
                d.ellipse([gx + nx - BALL_R, gy + ny - BALL_R,
                           gx + nx + BALL_R, gy + ny + BALL_R],
                          fill=(shade, shade, shade + 6))
        cxp, cyp = on_ramp(travelled)
        d.ellipse([cxp + nx - BALL_R, cyp + ny - BALL_R,
                   cxp + nx + BALL_R, cyp + ny + BALL_R], fill=INK)

        # the measurement: brackets under the ramp, one per beat
        for k in range(intervals):
            a = ease((t - brackets_at - k * 0.16) / 0.45)
            if a <= 0:
                continue
            x0 = ax + marks[k] * RUN
            x1 = ax + marks[k + 1] * RUN
            col = fade(HOT, a)
            d.line([(x0, bar_y), (x0 + (x1 - x0) * a, bar_y)],
                   fill=col, width=5)
            for x in (x0, x1):
                d.line([(x, bar_y - 16), (x, bar_y + 16)], fill=col, width=5)
            d.text(((x0 + x1) / 2, bar_y + 52), str(odds[k]),
                   font=f_odd, fill=col, anchor="mm")

        ca = ease((t - brackets_at - intervals * 0.16) / 0.5)
        if ca > 0:
            tracked(d, (W // 2, cap_y), caption.upper(), f_cap,
                    fade(DIM, ca), track=cap_track)
            tracked(d, (W // 2, ratio_y), ratio, f_ratio,
                    fade(HOT, ease((t - brackets_at - intervals * 0.16 - 0.2)
                                   / 0.5)), track=6)

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    ramp(angle=25, intervals=4, out="clips/08-ramp.mp4")
