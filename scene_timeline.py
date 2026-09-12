"""
Scene library: animated timeline.

Dates arrive one at a time on a vertical line, then an optional gap
between two of them highlights and labels itself. This is the backbone
scene for a channel about when things were discovered.

Usage as a script (renders the Galileo example):
    python scene_timeline.py

Usage from a storyboard:
    from scene_timeline import timeline
    timeline([(1564, "Galileo born"), (1622, "Viviani born"),
              (1642, "Galileo dies"), (1654, "the story written")],
             gap=(1642, 1654), gap_label="12 years",
             out="clips/02-timeline.mp4")
"""

import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30

BG = (11, 13, 18)
INK = (238, 236, 230)
DIM = (120, 124, 132)
HOT = (255, 214, 122)

TOP = 380
BOTTOM = 1560
LINE_X = 470          # right enough to fit the gap label on the left

ENTRY = 0.45          # seconds for each date to arrive
HOLD = 0.35           # pause between arrivals
GAP_DRAW = 0.9        # seconds to draw the gap bracket
GAP_HOLD = 1.2        # hold after the gap is labelled


def load_font(size, bold=True):
    names = ["arialbd.ttf" if bold else "arial.ttf"]
    for p in ([f"C:/Windows/Fonts/{n}" for n in names] +
              ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def ease(x):
    """Ease-out cubic. Movement should decelerate, never arrive linearly."""
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def blend(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def timeline(events, gap=None, gap_label="", out="clips/timeline.mp4",
             frames_dir="tmp_timeline"):
    """events: list of (year, label). gap: (year_from, year_to) to highlight."""
    if len(events) < 2:
        raise ValueError("need at least two events")

    events = sorted(events, key=lambda e: e[0])
    years = [e[0] for e in events]
    span = max(years) - min(years)
    if span == 0:
        raise ValueError("all events share one year")

    # y position is proportional to the actual year, so visual distance
    # equals elapsed time. That is the whole point of the scene.
    ypos = {y: TOP + (y - min(years)) / span * (BOTTOM - TOP) for y in years}

    # Proportional spacing is the point, but labels still have to be
    # readable. Push any pair closer than MIN_SPACING apart, in order.
    MIN_SPACING = 190
    ordered = sorted(years)
    for a, b in zip(ordered, ordered[1:]):
        if ypos[b] - ypos[a] < MIN_SPACING:
            ypos[b] = ypos[a] + MIN_SPACING
    # rescale back into frame if the pushes overflowed
    lo, hi = ypos[ordered[0]], ypos[ordered[-1]]
    if hi > BOTTOM:
        k = (BOTTOM - TOP) / (hi - lo)
        for y in ordered:
            ypos[y] = TOP + (ypos[y] - lo) * k
        # re-apply the floor after rescaling
        for a, b in zip(ordered, ordered[1:]):
            if ypos[b] - ypos[a] < MIN_SPACING:
                ypos[b] = ypos[a] + MIN_SPACING

    f_year = load_font(84)
    f_label = load_font(42)
    f_gap = load_font(58)

    per_event = ENTRY + HOLD
    t_events = len(events) * per_event
    t_gap = (GAP_DRAW + GAP_HOLD) if gap else 0.6
    total = t_events + t_gap
    n = int(total * FPS)

    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    for i in range(n):
        t = i / FPS
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)

        # the spine grows downward as events arrive
        grown = min(1.0, ease(t / max(0.001, t_events)))
        d.line([(LINE_X, TOP), (LINE_X, TOP + grown * (BOTTOM - TOP))],
               fill=DIM, width=4)

        for idx, (year, label) in enumerate(events):
            start = idx * per_event
            if t < start:
                continue
            a = ease((t - start) / ENTRY)
            y = ypos[year]

            # slide in from the left while fading up
            x_off = lerp(-70, 0, a)
            col_year = blend(BG, INK, a)
            col_lbl = blend(BG, DIM, a)

            r = int(lerp(4, 14, a))
            d.ellipse([LINE_X - r, y - r, LINE_X + r, y + r], fill=col_year)
            d.text((LINE_X + 70 + x_off, y - 6), str(year),
                   font=f_year, fill=col_year, anchor="lm")
            d.text((LINE_X + 70 + x_off, y + 52), label.upper(),
                   font=f_label, fill=col_lbl, anchor="lm")

        # the gap bracket: the argument of the scene
        if gap and t >= t_events:
            a = ease((t - t_events) / GAP_DRAW)
            y1, y2 = ypos[gap[0]], ypos[gap[1]]
            bx = LINE_X - 110
            cur = lerp(y1, y2, a)
            d.line([(bx, y1), (bx, cur)], fill=HOT, width=7)
            d.line([(bx, y1), (bx + 36, y1)], fill=HOT, width=7)
            if a > 0.98:
                d.line([(bx, y2), (bx + 36, y2)], fill=HOT, width=7)
            if a > 0.6 and gap_label:
                la = ease((a - 0.6) / 0.4)
                col = blend(BG, HOT, la)
                mid = (y1 + y2) / 2
                d.text((bx - 40, mid), gap_label.upper(),
                       font=f_gap, fill=col, anchor="rm")

        im.save(os.path.join(frames_dir, f"{i:04d}.png"))

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(frames_dir, "%04d.png"),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out],
        check=True)
    shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"wrote {out}  ({n} frames, {total:.1f}s)")
    return total


if __name__ == "__main__":
    timeline(
        [(1564, "Galileo born"),
         (1622, "Viviani born"),
         (1642, "Galileo dies"),
         (1654, "the story written")],
        gap=(1642, 1654),
        gap_label="12 years",
        out="clips/02-timeline.mp4",
    )