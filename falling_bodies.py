"""
Falling-bodies animation for the Delft 1586 beat.

Two lead balls, one ten times the mass of the other, released together
from 30 feet. They fall under real physics (s = 1/2 g t^2), which means
they stay level the whole way down and land as one sound.

Nothing here is invented: it is a diagram, not a depiction. No claim is
made about what anyone or anywhere looked like.

Usage:  python falling_bodies.py
Writes: clips/falling.mp4  (1080x1920, 30fps)

Requires: pillow, numpy, ffmpeg
"""

import math
import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30

HOLD_BEFORE = 0.5      # beat before release
FALL_TIME = 1.4        # seconds of fall
HOLD_AFTER = 0.9       # impact ring + settle
TOTAL = HOLD_BEFORE + FALL_TIME + HOLD_AFTER

DROP_TOP = 380         # y of release point
BOARD_Y = 1500         # y of the board

BG = (11, 13, 18)
INK = (238, 236, 230)
DIM = (120, 124, 132)
HOT = (255, 214, 122)

R_SMALL = 26
R_BIG = 56             # 10x mass -> ~2.15x radius

FRAMES_DIR = "tmp_falling"
OUT = "clips/falling.mp4"


def load_font(size):
    for p in ("C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_frame(i, n, font_lbl, font_big):
    t = i / FPS
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # release line and board
    d.line([(140, DROP_TOP), (W - 140, DROP_TOP)], fill=DIM, width=3)
    d.line([(140, BOARD_Y), (W - 140, BOARD_Y)], fill=INK, width=8)

    # fall physics: normalise so the balls arrive exactly at BOARD_Y
    span = BOARD_Y - DROP_TOP
    if t < HOLD_BEFORE:
        frac = 0.0
    elif t < HOLD_BEFORE + FALL_TIME:
        tt = (t - HOLD_BEFORE) / FALL_TIME
        frac = tt * tt                      # s proportional to t^2
    else:
        frac = 1.0

    x_small, x_big = 380, 700
    y_small = DROP_TOP + frac * (span - R_SMALL)
    y_big = DROP_TOP + frac * (span - R_BIG)

    # motion blur trail once moving
    if 0 < frac < 1:
        for k in range(1, 5):
            back = max(0.0, frac - k * 0.035)
            fade = int(70 - k * 14)
            c = (fade, fade, fade + 6)
            ys = DROP_TOP + back * (span - R_SMALL)
            yb = DROP_TOP + back * (span - R_BIG)
            d.ellipse([x_small - R_SMALL, ys - R_SMALL,
                       x_small + R_SMALL, ys + R_SMALL], fill=c)
            d.ellipse([x_big - R_BIG, yb - R_BIG,
                       x_big + R_BIG, yb + R_BIG], fill=c)

    d.ellipse([x_small - R_SMALL, y_small - R_SMALL,
               x_small + R_SMALL, y_small + R_SMALL], fill=INK)
    d.ellipse([x_big - R_BIG, y_big - R_BIG,
               x_big + R_BIG, y_big + R_BIG], fill=INK)

    # mass labels stay pinned at the release line so they never
    # collide with the motion trails
    d.text((x_small, DROP_TOP - 52), "1x",
           font=font_lbl, fill=DIM, anchor="mm")
    d.text((x_big, DROP_TOP - 52), "10x",
           font=font_lbl, fill=DIM, anchor="mm")

    # impact: one expanding ring from between them, because one sound
    impact_t = HOLD_BEFORE + FALL_TIME
    if t >= impact_t:
        age = t - impact_t
        if age < 0.55:
            rr = int(40 + age * 1400)
            fade = max(0, 1 - age / 0.55)
            col = tuple(int(BG[j] + (HOT[j] - BG[j]) * fade) for j in range(3))
            cx = (x_small + x_big) // 2
            d.ellipse([cx - rr, BOARD_Y - rr // 3,
                       cx + rr, BOARD_Y + rr // 3],
                      outline=col, width=max(2, int(9 * fade)))
        if 0.06 < age:
            a = min(1.0, (age - 0.06) / 0.3)
            col = tuple(int(BG[j] + (HOT[j] - BG[j]) * a) for j in range(3))
            d.text((W // 2, BOARD_Y + 190), "ONE SOUND",
                   font=font_big, fill=col, anchor="mm")

    # height marker
    d.text((W - 150, (DROP_TOP + BOARD_Y) // 2), "30 ft",
           font=font_lbl, fill=DIM, anchor="lm")

    return im


def main():
    os.makedirs(FRAMES_DIR, exist_ok=True)
    os.makedirs("clips", exist_ok=True)

    font_lbl = load_font(44)
    font_big = load_font(96)

    n = int(TOTAL * FPS)
    for i in range(n):
        draw_frame(i, n, font_lbl, font_big).save(
            os.path.join(FRAMES_DIR, f"{i:04d}.png"))

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES_DIR, "%04d.png"),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", OUT],
        check=True)

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print(f"wrote {OUT}  ({n} frames, {TOTAL:.1f}s, impact at "
          f"{HOLD_BEFORE + FALL_TIME:.1f}s)")


if __name__ == "__main__":
    main()