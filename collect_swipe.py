"""
Collect the comparable channels' listings for the swipe file.

    python collect_swipe.py                 # -> research/swipe.json
    python collect_swipe.py --tabs shorts videos
    python make.py --auto --swipe research/swipe.json

The channels, tabs and file live in config.yaml under `swipe`. This
reads public listings only (yt-dlp, flat: one request per tab, no
video pages, no login) and writes what youtube-agent-skill's swipe.py
takes: one row per video, ranked later by how far each beat its own
channel's median.

Three things the numbers are, and are not
------------------------------------------
Each tab is its own "channel" in the file -- "Veritasium (shorts)" and
"Veritasium (videos)" -- because a channel's Shorts and its long videos
have medians an order of magnitude apart, and one median over both
would make every long video an outlier.

The counts are YouTube's rounded labels ("1.2M views"), so a multiple
is good to a few percent, which is plenty for 2x and up.

The newest uploads are skipped (`skip_newest`): they are still
gathering views, and a flat listing carries no upload date to adjust
for, so a week-old Short would read as a flop against a median of
year-old ones.
"""

import argparse
import datetime
import json
import os
import sys

import yaml


def collect(url, tab, limit, skip):
    """[(title, views, url)] for the newest `limit` uploads on one tab,
    minus the `skip` newest. Rows without a view count are dropped."""
    try:
        import yt_dlp
    except ImportError:
        raise SystemExit("pip install yt-dlp  -- needed to read the "
                         "channel listings")
    opts = {"extract_flat": "in_playlist", "playlistend": limit + skip,
            "quiet": True, "skip_download": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{url.rstrip('/')}/{tab}", download=False)
    rows = []
    for e in list((info or {}).get("entries") or [])[skip:]:
        if not e or e.get("view_count") is None or not e.get("title"):
            continue
        link = e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"
        rows.append((e["title"], int(e["view_count"]), link,
                     e.get("duration")))
    return rows


def main(argv=None):
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["swipe"]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--tabs", nargs="+", choices=["shorts", "videos"],
                    default=cfg.get("tabs", ["shorts"]))
    ap.add_argument("--per-channel", type=int,
                    default=cfg.get("per_channel", 60))
    ap.add_argument("--out", default=cfg.get("file", "research/swipe.json"))
    a = ap.parse_args(argv)
    skip = cfg.get("skip_newest", 0)

    videos, short = [], []
    for ch in cfg["channels"]:
        for tab in a.tabs:
            name = f"{ch['name']} ({tab})"
            rows = collect(ch["url"], tab, a.per_channel, skip)
            print(f"  {name:<28} {len(rows):3d} with view counts")
            if len(rows) < 4:
                short.append(name)
            videos += [{"channel": name, "title": t, "views": v, "url": u,
                        "duration": d} for t, v, u, d in rows]

    if not videos:
        raise SystemExit("nothing collected -- check the channel URLs in "
                         "config.yaml, and that youtube.com is reachable")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"collected_at": datetime.date.today().isoformat(),
               "videos": videos},
              open(a.out, "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(f"wrote {a.out}  ({len(videos)} videos)")
    for name in short:
        print(f"  NOTE  {name}: under 4 videos, so swipe.py will skip it "
              f"-- a median of one or two is not a median")
    print(f"next: python make.py --auto --swipe {a.out}")


if __name__ == "__main__":
    sys.exit(main())
