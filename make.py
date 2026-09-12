"""
One command from storyboard to uploadable video.

    python make.py shots/0001.yaml               # the whole pipeline
    python make.py shots/0001.yaml --skip-vo     # reuse vo.wav + vo.json
    python make.py shots/0001.yaml --plan        # print the plan, render nothing

    python make.py --auto                        # pick a subject and make it
    python make.py --auto --topic "how we weighed the Earth"

The storyboard is the entire input. Nothing gets edited per video any
more: what used to live in make_vo.py's SEGMENTS, render.py's SHOTS and
metadata.py's constants now comes out of one yaml file.

Why the cut points are exact
----------------------------
Each line of the script is synthesised as its own segment, so the
voiceover itself reports where every line starts and ends. No transcript
matching, no alignment guessing. A shot says which lines it covers and
gets that beat, to the frame.

Each scene is then measured before it is drawn (scene_kit.measuring)
and its slack parameter solved so the clip comes out exactly as long as
its beat. This matters because render.py loops a clip that is too short
and truncates one that is too long, and says nothing either way.

Writing a storyboard
--------------------
See shots/0001.yaml. Copy it, change the content, run it.
"""

import argparse
import inspect
import json
import os
import sys

import yaml

import metadata as metadata_mod
import render as render_mod
from falling_bodies import drop_test
from scene_kit import measuring
from scene_map_zoom import map_zoom
from scene_number_reveal import number_reveal
from scene_quote_card import quote_card
from scene_ramp import ramp
from scene_text_beat import text_beat
from scene_timeline import timeline
from scene_versus import versus

# name in yaml -> (function, slack parameter, squeeze parameter or None)
#
# Every scene ends on a held frame, and that hold is what gets stretched
# to fill a beat. drop_test is the exception: its slack normally goes
# after the impact, but a shot can say `slack: hold_before` to push the
# impact later instead, which is how you land a sound on a specific word.
#
# The squeeze parameter is the opposite case -- a scene whose content
# makes it longer than its line even with no hold at all (a three-step
# map zoom under a three-second sentence). Compressing that parameter
# fits it. drop_test deliberately has none: the only thing left to
# compress there is fall_time, and that is real physics.
SCENES = {
    "text_beat":     (text_beat, "hold", "per_word"),
    "timeline":      (timeline, "hold", "pace"),
    "drop_test":     (drop_test, "hold_after", None),
    "number_reveal": (number_reveal, "hold", "count_time"),
    "quote_card":    (quote_card, "hold", "per_line"),
    "versus":        (versus, "hold", None),
    "map_zoom":      (map_zoom, "hold", "per_step"),
    "ramp":          (ramp, "hold", "roll"),
}

SQUEEZE_FLOOR = 0.3        # never compress a pacing value below this

# Scenes with a moment a sound has to hit, as an offset into the clip.
IMPACT = {
    "drop_test": lambda a: a["hold_before"] + a["fall_time"],
}

TAIL = 0.8          # picture holds this long after the last word


def die(msg):
    raise SystemExit(f"storyboard error: {msg}")


def resolved(fn, args):
    """args with the function's own defaults filled in, so an impact time
    is computed from what the scene will really do."""
    out = {k: p.default for k, p in inspect.signature(fn).parameters.items()
           if p.default is not inspect.Parameter.empty}
    out.update(args)
    return out


def load(path):
    if not os.path.exists(path):
        die(f"{path} not found")
    board = yaml.safe_load(open(path, encoding="utf-8"))

    for key in ("code", "script", "shots"):
        if not board.get(key):
            die(f"{path} has no `{key}`")

    n = len(board["script"])
    covered = []
    for i, shot in enumerate(board["shots"]):
        if shot.get("scene") not in SCENES:
            die(f"shot {i}: unknown scene {shot.get('scene')!r}. "
                f"Known: {', '.join(sorted(SCENES))}")
        lines = shot.get("lines")
        if not lines:
            die(f"shot {i} ({shot['scene']}) covers no script lines")
        covered += list(lines)

    # Every line must be spoken over exactly one shot, in order. A gap
    # here means a stretch of narration with no picture; an overlap
    # means two clips claim the same seconds.
    if covered != list(range(n)):
        missing = sorted(set(range(n)) - set(covered))
        dupes = sorted({x for x in covered if covered.count(x) > 1})
        why = []
        if missing:
            why.append(f"lines never shown: {missing}")
        if dupes:
            why.append(f"lines claimed twice: {dupes}")
        if not why:
            why.append(f"shots cover {covered}, script has 0..{n - 1} in order")
        die("; ".join(why))

    return board


def synth_vo(board, out_wav="vo.wav", out_json="vo.json"):
    """One TTS segment per script line, so the line boundaries are exact
    rather than inferred. Word timings for the captions come from
    Whisper afterwards, as before."""
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    from kokoro_onnx import Kokoro

    v = board.get("voice", {})
    narrator = v.get("narrator", "bf_emma")
    quote = v.get("quote", "bm_george")
    speed = float(v.get("speed", 1.05))

    k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    audio, sr, timeline_rows, cursor = [], None, [], 0.0

    for i, line in enumerate(board["script"]):
        voice = quote if line.get("voice") == "quote" else narrator
        samples, sr = k.create(line["text"], voice=voice, speed=speed,
                               lang="en-us")
        dur = len(samples) / sr
        timeline_rows.append({"seg": i, "voice": voice,
                              "start": round(cursor, 2),
                              "end": round(cursor + dur, 2),
                              "text": line["text"]})
        audio.append(samples)
        cursor += dur
        gap = float(line.get("gap", 0.0))
        if gap:
            audio.append(np.zeros(int(gap * sr), dtype=samples.dtype))
            cursor += gap

    full = np.concatenate(audio)
    sf.write(out_wav, full, sr)
    print(f"  {out_wav}  {len(full) / sr:.1f}s, {len(timeline_rows)} lines")

    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segments, _ = m.transcribe(out_wav, word_timestamps=True)
    words = [{"w": w.word.strip(), "start": round(w.start, 2),
              "end": round(w.end, 2)}
             for s in segments for w in s.words]
    json.dump({"timeline": timeline_rows, "words": words},
              open(out_json, "w", encoding="utf-8"), indent=2)
    print(f"  {out_json}  {len(words)} words")


def beats(board, vo):
    """(start, end) on the voiceover clock for each shot.

    A shot runs until the next line starts speaking, so it holds through
    the silence after its own line rather than cutting on the last
    syllable. The final shot runs past the narration by TAIL.
    """
    rows = vo["timeline"]
    if len(rows) != len(board["script"]):
        die(f"vo.json has {len(rows)} lines but the storyboard has "
            f"{len(board['script'])} -- re-run without --skip-vo")

    out, prev_end = [], 0.0
    for shot in board["shots"]:
        last = max(shot["lines"])
        if last + 1 < len(rows):
            end = rows[last + 1]["start"]
        else:
            end = rows[last]["end"] + TAIL
        out.append((prev_end, round(end, 2)))
        prev_end = round(end, 2)
    return out


def build_shots(board, spans, plan_only=False):
    """Render each scene fitted to its beat. Returns render.py's SHOTS
    and SFX lists."""
    os.makedirs("clips", exist_ok=True)
    shots, sfx, report = [], [], []

    for i, (shot, (start, end)) in enumerate(zip(board["shots"], spans)):
        name = shot["scene"]
        fn, default_slack, squeeze_kw = SCENES[name]
        slack_kw = shot.get("slack", default_slack)
        if slack_kw not in inspect.signature(fn).parameters:
            die(f"shot {i}: {name}() has no parameter {slack_kw!r}")

        args = dict(shot.get("args", {}))
        beat = round(end - start, 3)
        clip = f"clips/{i + 1:02d}-{name}.mp4"

        # Measure at zero slack, then solve. Every scene's duration is
        # linear in its slack parameter, so one probe is enough.
        def measure(a):
            with measuring():
                return fn(**{**a, slack_kw: 0.0}, out=clip)

        floor = measure(args)

        # Too long for its line even with no hold: compress the pacing
        # parameter instead of cropping. Duration is linear in it, so two
        # probes give the exact value -- no search.
        if floor > beat + 0.02 and squeeze_kw and squeeze_kw not in args:
            p0 = resolved(fn, args)[squeeze_kw]
            p1 = p0 * 0.5
            d1 = measure({**args, squeeze_kw: p1})
            slope = (floor - d1) / (p0 - p1) if p0 != p1 else 0
            if slope > 0:
                want = max(SQUEEZE_FLOOR, p1 + (beat - d1) / slope)
                args[squeeze_kw] = round(want, 3)
                floor = measure(args)
                if floor <= beat + 0.02:
                    report.append(
                        f"     {name}: {squeeze_kw} {p0:.2f} -> {want:.2f} "
                        f"to fit a {beat:.2f}s line")

        args[slack_kw] = max(0.0, round(beat - floor, 3))

        if floor > beat + 0.05:
            report.append(
                f"  shot {i + 1} ({name}) is {floor:.2f}s at its shortest "
                f"but its beat is only {beat:.2f}s -- shorten the line, "
                f"or give this scene fewer arguments")

        if plan_only:
            with measuring():
                actual = fn(**args, out=clip)
        else:
            actual = fn(**args, out=clip)

        shots.append({"mode": "video", "src": clip,
                      "start": round(start, 2), "end": round(end, 2)})

        if shot.get("sfx"):
            spec = shot["sfx"]
            if name not in IMPACT:
                die(f"shot {i}: {name} has no impact moment to sync a "
                    f"sound to")
            at = start + IMPACT[name](resolved(fn, args))
            sfx.append((spec["file"], round(at, 2), spec.get("gain", -3)))

        report.append(f"  {i + 1:02d} {name:14s} {start:6.2f} -> {end:6.2f}"
                      f"  beat {beat:5.2f}s  clip {actual:5.2f}s"
                      f"  {'drift ' + format(actual - beat, '+.2f') + 's' if abs(actual - beat) > 0.05 else 'exact'}")

    return shots, sfx, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("storyboard", nargs="?",
                    help="path to a storyboard yaml; omit with --auto")
    ap.add_argument("--auto", action="store_true",
                    help="research and write a new storyboard first "
                         "(needs ANTHROPIC_API_KEY)")
    ap.add_argument("--topic", help="with --auto: the subject to research, "
                                    "instead of letting it choose")
    ap.add_argument("--skip-vo", action="store_true",
                    help="reuse the existing vo.wav and vo.json")
    ap.add_argument("--plan", action="store_true",
                    help="print the shot plan and stop, rendering nothing")
    a = ap.parse_args(argv)

    if a.auto:
        if a.storyboard:
            die("pass a storyboard or --auto, not both")
        import auto
        a.storyboard = auto.main(["--topic", a.topic] if a.topic else [])
        print("\n" + "=" * 60)
    elif not a.storyboard:
        die("give me a storyboard (shots/NNNN.yaml) or --auto")
    elif a.topic:
        die("--topic only means something with --auto")

    board = load(a.storyboard)
    code = board["code"]
    print(f"\n{code}  ({len(board['script'])} lines, "
          f"{len(board['shots'])} shots)\n")

    if not a.skip_vo and not a.plan:
        print("voice")
        synth_vo(board)
        print()
    elif not os.path.exists("vo.json"):
        die("no vo.json to reuse -- run without --skip-vo")

    vo = json.load(open("vo.json", encoding="utf-8"))
    spans = beats(board, vo)

    print("shots")
    shots, sfx, report = build_shots(board, spans, plan_only=a.plan)
    print("\n".join(report))
    total = shots[-1]["end"]
    print(f"\n  picture {total:.2f}s   narration "
          f"{vo['timeline'][-1]['end']:.2f}s + {TAIL}s tail")
    for f, at, gain in sfx:
        print(f"  sfx {f} at {at:.2f}s ({gain}dB)")

    if a.plan:
        print("\n--plan: nothing rendered")
        return 0

    print("\ncaptions")
    import captions
    captions.main()

    print("\nrender")
    render_mod.main(shots=shots, code=code, sfx=sfx,
                    music=board.get("music"), tail=TAIL)

    meta = board.get("metadata")
    if meta:
        print("\nmetadata")
        metadata_mod.main(
            code=code,
            titles=meta.get("titles"),
            hook=meta.get("hook"),
            sources=[tuple(s) for s in meta.get("sources", [])] or None,
            hashtags=meta.get("hashtags"),
            video_id=meta.get("video_id"))

    print(f"\ndone. Upload out/{code}.mp4 and tick "
          f"'Altered or synthetic content'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
