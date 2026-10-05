"""
Where viewers left, named by script line and scene.

    python retention_report.py shots/0002.yaml retention.csv
    python retention_report.py shots/0002.yaml retention.csv --axis seconds
    python retention_report.py shots/0001.yaml retention.csv --vo vo.json

Export the CSV from Studio: the video -> Analytics -> Engagement -> the
audience-retention chart -> download.

The reading itself -- hook leak, cliffs, slide -- is youtube-agent-skill's
retention.py (see ytskill.py). What this adds is the part a transcript
cannot do as well: make.py synthesises every script line as its own
segment and records exactly when each one starts, so a drop at 19s is
not "something around 15-23s" but line 4, under the timeline scene.

Two things it sets for a Short, because the defaults are long-form:
  --duration      the video's real length, from out/<code>-timing.json,
                  which is what lets a seconds axis be told from a
                  percent one
  --hook-seconds  the end of the first line, not 30s, which would be
                  two thirds of the video

Timings come from out/<code>-timing.json, which make.py writes on every
render. A video rendered before that existed has none: pass --vo with
the vo.json it was made from, and check the line count it reports.
"""

import argparse
import json
import os
import sys

import yaml

import ytskill

TAIL = 0.8   # make.py's hold after the last word, for --vo fallbacks only


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_timing(board, vo_path=None):
    code = board["code"]
    path = os.path.join("out", f"{code}-timing.json")
    if os.path.exists(path) and not vo_path:
        return json.load(open(path, encoding="utf-8"))
    if not vo_path:
        die(f"no {path} -- render with the current make.py, or pass --vo "
            f"with the vo.json this video was made from")
    vo = json.load(open(vo_path, encoding="utf-8"))
    lines = vo["timeline"]
    if len(lines) != len(board["script"]):
        print(f"  NOTE  {vo_path} has {len(lines)} lines, the storyboard "
              f"{len(board['script'])} -- lines are named from {vo_path}, "
              f"scenes are left out")
        return {"code": code, "duration": lines[-1]["end"] + TAIL,
                "lines": lines, "shots": []}
    shots, prev = [], 0.0
    for shot in board["shots"]:
        last = max(shot["lines"])
        end = (lines[last + 1]["start"] if last + 1 < len(lines)
               else lines[last]["end"] + TAIL)
        shots.append({"scene": shot["scene"], "lines": shot["lines"],
                      "start": prev, "end": end})
        prev = end
    return {"code": code, "duration": lines[-1]["end"] + TAIL,
            "lines": lines, "shots": shots}


def line_at(t, lines):
    """The line on screen at t: from its start until the next one starts,
    so the silence after a line still belongs to it."""
    hit = None
    for i, l in enumerate(lines):
        if l["start"] <= t:
            hit = i
    return hit


def shot_at(t, shots):
    for s in shots:
        if s["start"] <= t < s["end"]:
            return s
    return shots[-1] if shots and t >= shots[-1]["start"] else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("storyboard")
    ap.add_argument("csv")
    ap.add_argument("--axis", choices=["percent", "seconds"],
                    help="override the position column's unit")
    ap.add_argument("--vo", help="a vo.json, for videos rendered before "
                                 "timing files existed")
    a = ap.parse_args(argv)

    board = yaml.safe_load(open(a.storyboard, encoding="utf-8"))
    timing = load_timing(board, a.vo)
    lines = timing["lines"]
    hook = lines[0]["end"]

    r, note = ytskill.retention(a.csv, duration=timing["duration"],
                                hook_seconds=hook, axis=a.axis)
    if r is None:
        die(note)

    print(f"\n{timing['code']}   {timing['duration']:.1f}s   "
          f"{r['start']:.0f}% -> {r['end']:.0f}%")
    print(f"  axis: {r['axis']} ({r['axis_reason']})")
    for w in r["warnings"]:
        print(f"  NOTE  {w}")

    print(f"\nHOOK   {r['hook_leak']:.1f}% gone by the end of line 0 "
          f"({hook:.1f}s)")
    print(f"       \"{lines[0]['text'].strip()}\"")

    print("\nCLIFFS")
    if not r["cliffs"]:
        print("  none -- the loss is all slide")
    for c in r["cliffs"]:
        t = c["at_seconds"]
        if t is None:
            print(f"  -{c['lost']:.1f}% at {c['from']}% of the video "
                  f"(no time -- check --axis)")
            continue
        i = line_at(t, lines)
        s = shot_at(t, timing["shots"])
        where = f"line {i}" if i is not None else "before the first line"
        scene = f", {s['scene']}" if s else ""
        print(f"  -{c['lost']:.1f}% at {t:.1f}s   {where}{scene}")
        if i is not None:
            print(f"        \"{lines[i]['text'].strip()[:110]}\"")

    print(f"\nSLIDE  {r['slide_per_unit']:.3f} {r['slide_unit']}")
    print("\nOne video is an anecdote. Read these across twenty before "
          "changing a scene\nor a line pattern because of them.")


if __name__ == "__main__":
    main()
