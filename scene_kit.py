"""
Shared house style for the scene library.

Every scene draws 1080x1920 frames with Pillow and hands them to ffmpeg.
The parts that must not drift between scenes -- palette, easing, fonts,
safe area, encoder settings -- live here, so a new scene is only the
drawing code.

    from scene_kit import *

    def draw(t):
        im, d = frame()
        d.text((W // 2, 900), "HELLO", font=load_font(120),
               fill=fade(INK, ease(t / 0.5)), anchor="mm")
        return im

    render(draw, 2.0, "clips/hello.mp4")

House rules, from the README:

  BG  (11, 13, 18)     near-black
  INK (238, 236, 230)  off-white
  DIM (120, 124, 132)  grey, for labels
  HOT (255, 214, 122)  amber, for the one thing that matters

Amber is a budget, not a colour. One idea per scene gets it.
Ease-out cubic on all motion. Nothing arrives linearly.
"""

import os
import shutil
import subprocess
from contextlib import contextmanager
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30

BG = (11, 13, 18)
INK = (238, 236, 230)
DIM = (120, 124, 132)
HOT = (255, 214, 122)

# Captions are burned in along the bottom. captions.py sets MarginV to
# 22% of the height (config.yaml, captions.safe_area_bottom_pct), but
# that is the gap *below* the text -- the line itself then occupies
# roughly a font size plus its outline above that. Reserve both, or a
# scene drawn to 78% of the frame lands inside the captions.
MARGIN = 90
SAFE_TOP = 180
CAPTION_MARGIN_V = int(H * 0.22)       # captions.py SAFE_BOTTOM_PCT
CAPTION_BAND = 110                     # one 76px line plus its 6px outline
SAFE_BOTTOM = H - CAPTION_MARGIN_V - CAPTION_BAND

_BOLD = ["C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_REGULAR = ["C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


@lru_cache(maxsize=None)
def load_font(size, bold=True):
    """Cached: a scene that resizes text per frame asks for the same
    handful of sizes thousands of times."""
    for p in (_BOLD if bold else _REGULAR):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# --- motion ------------------------------------------------------

def ease(x):
    """Ease-out cubic. Movement should decelerate, never arrive linearly."""
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    """Cubic in-out. For camera moves, which start from rest as well as
    stopping at rest -- a map zoom eased only on the way out lurches."""
    x = max(0.0, min(1.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def lerp(a, b, t):
    return a + (b - a) * t


def blend(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def fade(c, a):
    """Fade a colour toward the background. Everything sits on flat BG,
    so this is opacity without an alpha channel."""
    return blend(BG, c, max(0.0, min(1.0, a)))


def stagger(t, i, start=0.0, step=0.12, dur=0.45):
    """Eased 0..1 for item i of a list that arrives one after another."""
    return ease((t - start - i * step) / dur)


# --- frames ------------------------------------------------------

def frame(bg=BG):
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


_SCRATCH = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def measure(text, fnt):
    """Width of a string, without needing a frame to measure it on.
    Layout gets computed once before the render loop starts."""
    return _SCRATCH.textlength(text, font=fnt)


def wrap(text, fnt, max_w):
    """Greedy word wrap. Returns a list of lines."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and measure(trial, fnt) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit(text, max_w, sizes, max_lines=1, bold=True):
    """Largest size from sizes (pass them descending) whose wrap fits in
    max_lines. Keeps a scene readable when video 12 hands it a longer
    string than video 2 did."""
    for size in sizes:
        fnt = load_font(size, bold)
        lines = wrap(text, fnt, max_w)
        if len(lines) <= max_lines:
            return fnt, lines
    fnt = load_font(sizes[-1], bold)
    return fnt, wrap(text, fnt, max_w)


def tracked_width(text, fnt, track=8):
    return (sum(measure(ch, fnt) for ch in text)
            + track * max(0, len(text) - 1))


def fit_tracked(text, max_w, sizes, track=8, bold=True):
    """As fit(), for tracked one-liners -- returns (font, track).

    Tracking adds real width, so a label that fits unspaced can still run
    off the frame, and it scales with the size it is set at: tracking is
    an em measure, not a pixel one.
    """
    for size in sizes:
        fnt = load_font(size, bold)
        tr = track * size / sizes[0]
        if tracked_width(text, fnt, tr) <= max_w:
            return fnt, tr
    return load_font(sizes[-1], bold), track * sizes[-1] / sizes[0]


def tracked(d, xy, text, fnt, fill, track=8, anchor="mm"):
    """Letter-spaced text. Pillow has no tracking, and small uppercase
    labels need it. anchor: mm (centred) or lm (left)."""
    widths = [measure(ch, fnt) for ch in text]
    total = sum(widths) + track * max(0, len(text) - 1)
    x, y = xy
    if anchor.startswith("m"):
        x -= total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=fnt, fill=fill, anchor="lm")
        x += w + track
    return total


# --- output ------------------------------------------------------

_MEASURING = False


@contextmanager
def measuring():
    """Inside this block, render() returns what a scene's duration would
    be without drawing or encoding anything.

    A storyboard has to know how long a scene comes out before it can
    decide how long to make it. Without this, fitting a scene to its
    narration beat means rendering it twice.
    """
    global _MEASURING
    was = _MEASURING
    _MEASURING = True
    try:
        yield
    finally:
        _MEASURING = was


def render(draw, duration, out, frames_dir=None, fps=FPS, crf=18):
    """draw(t) -> Image for time t in seconds. Writes an h264 mp4."""
    n = max(1, int(round(duration * fps)))
    if _MEASURING:
        return n / fps

    stem = os.path.splitext(os.path.basename(out))[0]
    frames_dir = frames_dir or f"tmp_{stem}"

    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for i in range(n):
        draw(i / fps).save(os.path.join(frames_dir, f"{i:04d}.png"))

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
         "-i", os.path.join(frames_dir, "%04d.png"),
         "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p", out],
        check=True)
    shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"wrote {out}  ({n} frames, {n / fps:.1f}s)")
    return n / fps
