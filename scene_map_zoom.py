"""
Scene library: map zoom.

Continent to country to city, then a pin drops. Answers "where" without
a stock map, a tile server or a licence.

What is on screen is a graticule -- real lines of latitude and longitude
round the real coordinates, with a real scale bar -- rather than a
drawing of land. Same rule as falling_bodies.py: it is a diagram, not a
depiction, so it cannot be wrong about a coastline it never claims to
show. Pass `outline` if you have public-domain geometry to add.

Usage as a script (renders the Delft example):
    python scene_map_zoom.py

Usage from a storyboard:
    from scene_map_zoom import map_zoom
    map_zoom((52.0116, 4.3571),
             [("EUROPE", 22), ("THE NETHERLANDS", 3.2), ("DELFT", 0.22)],
             pin_label="Nieuwe Kerk", out="clips/07-map.mp4")
"""

import math

from scene_kit import (BG, DIM, HOT, INK, MARGIN, SAFE_BOTTOM, SAFE_TOP, H, W,
                       blend, ease, ease_in_out, fade, frame, lerp, load_font,
                       render, tracked)

GRID = [30, 20, 10, 5, 2, 1, 0.5, 0.25, 0.1, 0.05, 0.02, 0.01]
BARS_KM = [5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]
KM_PER_DEG = 111.32
GRID_COL = None        # set on first use: fade() needs no frame
ESTABLISH = 1.45       # the first step starts this much wider and pushes in
PIN_RISE = 430         # how far above the target the pin starts
PIN_H = 86


def _deg(v, pos, neg):
    return f"{round(abs(v), 4):g}°{pos if v >= 0 else neg}"


def _nice(value, ladder, want):
    for step in ladder:
        if value / step >= want:
            return step
    return ladder[-1]


def map_zoom(target, steps, pin_label=None, per_step=1.1, drop=0.55,
             hold=1.5, outline=None, out="clips/map.mp4"):
    """target: (lat, lon). steps: [(label, half-height in degrees), ...],
    widest first. pin_label: what lands at the coordinates."""
    if not steps:
        raise ValueError("need at least one step")

    lat0, lon0 = target
    coslat = math.cos(math.radians(lat0))
    spans = [s for _, s in steps]
    f_step = load_font(44)
    f_grid = load_font(28)
    f_scale = load_font(30)
    f_pin = load_font(52)

    zoom_time = len(steps) * per_step
    pin_at = zoom_time
    total = zoom_time + drop + hold

    def span_at(t):
        """Log interpolation: zoom is multiplicative, so halving the span
        must take as long at 20 degrees as at 0.2."""
        i = min(int(t / per_step), len(steps) - 1)
        a = ease_in_out(min(1.0, (t - i * per_step) / (per_step * 0.72)))
        prev = spans[i - 1] if i else spans[0] * ESTABLISH
        return prev * (spans[i] / prev) ** a

    def draw(t):
        global GRID_COL
        if GRID_COL is None:
            GRID_COL = fade(DIM, 0.3)

        im, d = frame()
        span = span_at(min(t, zoom_time))
        k = (H / 2) / span                      # pixels per degree of latitude
        lon_span = span * (W / H) / coslat

        def px(lat, lon):
            return (W / 2 + (lon - lon0) * coslat * k,
                    H / 2 - (lat - lat0) * k)

        # Graticule. The interval steps down as you zoom so the frame
        # always carries four or more lines -- which is what makes the
        # movement read as a zoom rather than a fade.
        gs = _nice(2 * span, GRID, 4)
        lat_lo = math.floor((lat0 - span) / gs) * gs
        for i in range(int(2 * span / gs) + 3):
            lat = round(lat_lo + i * gs, 6)
            _, y = px(lat, lon0)
            if -50 < y < H + 50:
                d.line([(0, y), (W, y)], fill=GRID_COL, width=2)
                if SAFE_TOP < y < SAFE_BOTTOM:
                    d.text((MARGIN - 30, y - 20), _deg(lat, "N", "S"),
                           font=f_grid, fill=fade(DIM, 0.55), anchor="lb")
        lon_lo = math.floor((lon0 - lon_span) / gs) * gs
        for i in range(int(2 * lon_span / gs) + 3):
            lon = round(lon_lo + i * gs, 6)
            x, _ = px(lat0, lon)
            if -50 < x < W + 50:
                d.line([(x, 0), (x, H)], fill=GRID_COL, width=2)
                if MARGIN < x < W - MARGIN:
                    d.text((x + 12, SAFE_BOTTOM - 8), _deg(lon, "E", "W"),
                           font=f_grid, fill=fade(DIM, 0.55), anchor="lb")

        for poly in (outline or []):
            pts = [px(la, lo) for la, lo in poly]
            if len(pts) > 1 and any(-W < x < 2 * W for x, _ in pts):
                d.line(pts, fill=DIM, width=3, joint="curve")

        # Scale bar: the one element that says this is a map of somewhere
        # and not a grid.
        km = _nice(span * KM_PER_DEG, BARS_KM, 0.9)
        bar = km / KM_PER_DEG * k
        if 60 < bar < W - 2 * MARGIN:
            by, bx = SAFE_BOTTOM - 70, W - MARGIN - bar
            d.line([(bx, by), (bx + bar, by)], fill=DIM, width=4)
            for x in (bx, bx + bar):
                d.line([(x, by - 12), (x, by)], fill=DIM, width=4)
            d.text((bx + bar, by - 22), f"{km:g} km", font=f_scale,
                   fill=DIM, anchor="rb")

        # Step labels crossfade as the camera passes through them.
        for i, (label, _) in enumerate(steps):
            local = t - i * per_step
            if local < 0:
                continue
            a = ease(local / 0.35)
            if i < len(steps) - 1:
                a *= 1 - ease((local - per_step + 0.3) / 0.3)
            if a > 0.01:
                tracked(d, (W // 2, SAFE_TOP + 30), label.upper(), f_step,
                        fade(INK, a), track=12)

        cx, cy = W / 2, H / 2
        if t < pin_at:
            a = 1 - ease((t - pin_at + 0.3) / 0.3)
            col = fade(DIM, a)
            d.line([(cx - 34, cy), (cx - 12, cy)], fill=col, width=3)
            d.line([(cx + 12, cy), (cx + 34, cy)], fill=col, width=3)
            d.line([(cx, cy - 34), (cx, cy - 12)], fill=col, width=3)
            d.line([(cx, cy + 12), (cx, cy + 34)], fill=col, width=3)
        else:
            a = ease((t - pin_at) / drop)
            tip_y = cy - lerp(PIN_RISE, 0, a)
            head = tip_y - PIN_H
            r = 30
            d.polygon([(cx, tip_y), (cx - 20, head + 6), (cx + 20, head + 6)],
                      fill=HOT)
            d.ellipse([cx - r, head - r, cx + r, head + r], fill=HOT)
            d.ellipse([cx - 11, head - 11, cx + 11, head + 11], fill=BG)

            age = t - pin_at - drop
            if age >= 0:                      # landing ripple
                for k_ring in (0, 1):
                    ra = (age - k_ring * 0.16) / 0.5
                    if 0 < ra < 1:
                        rr = 24 + ra * 190
                        d.ellipse([cx - rr, tip_y - rr / 3,
                                   cx + rr, tip_y + rr / 3],
                                  outline=fade(HOT, 1 - ra),
                                  width=max(2, int(7 * (1 - ra))))
                if pin_label:
                    la = ease((age - 0.12) / 0.4)
                    tracked(d, (W // 2, tip_y + 96), pin_label.upper(),
                            f_pin, fade(blend(INK, HOT, 0.3), la), track=10)

        return im

    return render(draw, total, out)


if __name__ == "__main__":
    map_zoom((52.0116, 4.3571),
             [("EUROPE", 22), ("THE NETHERLANDS", 3.2), ("DELFT", 0.22)],
             pin_label="Nieuwe Kerk",
             out="clips/07-map.mp4")
