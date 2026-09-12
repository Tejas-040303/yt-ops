"""
Assemble the final vertical video.

Usage:  python render.py

Reads:   vo.wav, captions.ass, assets/, clips/
Writes:  out/<code>.mp4

Shot modes
----------
portrait : crop to 9:16 and slowly pan/zoom across the face. Full frame,
           no wasted space. Use for portraits and title pages.
wide     : blurred copy fills the frame, real image sits centred. Use for
           cityscapes and anything whose width is the point.
video    : an existing clip (e.g. Wan 2.2 I2V output), fitted to frame.
black    : solid black, optional centred text. Free, and the strongest
           pattern break available on a feed full of motion.
"""

import json
import os
import subprocess
import sys

W, H, FPS = 1080, 1920, 30

# Windows FFmpeg has no fontconfig, so drawtext and libass must be handed
# an explicit font file / directory. Point FONT_FILE at a real .ttf.
if os.name == "nt":
    FONT_FILE = "C:/Windows/Fonts/arialbd.ttf"
    FONTS_DIR = "C:/Windows/Fonts"
else:
    FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONTS_DIR = "/usr/share/fonts"


def ff_path(p):
    """Escape a Windows path for use inside an ffmpeg filter argument."""
    return p.replace("\\", "/").replace(":", "\\:")

AUDIO = "vo.wav"
SUBS = "captions.ass"
TMP = "tmp_shots"
OUT_DIR = "out"
CODE = "0001-galileo-pisa-myth-bust"
TAIL_SEC = 0.8          # picture holds this long after the last word

# --- Audio bed ---------------------------------------------------
# MUSIC: optional. Grab a track from YouTube Studio -> Audio Library
# and drop it in assets/. Leave as None for narration only.
MUSIC = None                    # e.g. "assets/bed.mp3"
MUSIC_DB = -22                  # relative to the voice

# SFX: (file, seconds into the video, gain in dB)
# Sync the knock to the impact frame of clips/falling.mp4:
#   impact = shot start + HOLD_BEFORE + FALL_TIME  (from falling_bodies.py)
SFX = [
    ("assets/knock.wav", 29.9, -3),
]

# ---------------------------------------------------------------
# Shot list. start/end are seconds on the voiceover timeline.
# Adjust these against vo.json once you hear the narration.
# ---------------------------------------------------------------
SHOTS = [
    {"mode": "black",    "text": "GALILEO",              "start": 0.0,  "end": 2.5},
    {"mode": "portrait", "src": "assets/03-galileo-portrait.jpg",   "start": 2.5,  "end": 6.0},
    {"mode": "portrait", "src": "assets/02-viviani-portrait.jpg",   "start": 6.0,  "end": 11.0},
    {"mode": "black",    "text": "NO OTHER RECORD",      "start": 11.0, "end": 13.5},
    {"mode": "video",    "src": "clips/delft_vertical.mp4",         "start": 13.5, "end": 18.5},
    {"mode": "wide",     "src": "assets/05-nieuwe-kerk-delft.jpg",  "start": 18.5, "end": 22.0},
    {"mode": "portrait", "src": "assets/06-stevin-portrait.jpg",    "start": 22.0, "end": 26.0},
    {"mode": "black",    "text": "",                     "start": 26.0, "end": 28.0},
    {"mode": "portrait", "src": "assets/07-weeghconst-titlepage.jpg", "start": 28.0, "end": 34.0},
    {"mode": "wide",     "src": "assets/09-inclined-plane.jpg",     "start": 34.0, "end": 40.0},
]


def run(args, label):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"\nFFMPEG FAILED: {label}", file=sys.stderr)
        print(" ".join(args), file=sys.stderr)
        print(r.stderr[-2500:], file=sys.stderr)
        sys.exit(1)


def vf_portrait(frames):
    """Scale to cover the frame, then drift across it. Ends ~8% tighter."""
    return (
        f"scale={W*4}:-2,"
        f"zoompan=z='min(1+0.0009*on,1.12)'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)-(ih*0.04*on/{frames})'"
        f":d={frames}:s={W}x{H}:fps={FPS},"
        f"setsar=1,format=yuv420p"
    )


def vf_wide(frames, dur):
    """Blurred copy fills the frame; the real image sits centred and pans.

    Uses crop with a time expression rather than a second zoompan --
    stacking zoompan after a split needs a fixed output size, which means
    guessing the source aspect ratio. Panning avoids the guess entirely.
    """
    pan_w = int(W * 1.25)          # widen so there is room to travel
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=40[bgb];"
        f"[fg]scale={pan_w}:-2,"
        f"crop={W}:ih:x='(iw-{W})*(t/{dur:.3f})':y=0[fgc];"
        f"[bgb][fgc]overlay=(W-w)/2:(H-h)/2,"
        f"setsar=1,format=yuv420p"
    )


def build_still(shot, path, dur):
    frames = max(2, int(round(dur * FPS)))
    src = shot["src"]
    if not os.path.exists(src):
        print(f"MISSING ASSET: {src}", file=sys.stderr)
        sys.exit(1)

    if shot["mode"] == "portrait":
        args = ["ffmpeg", "-y", "-loop", "1", "-i", src,
                "-vf", vf_portrait(frames)]
    else:  # wide
        args = ["ffmpeg", "-y", "-loop", "1", "-i", src,
                "-filter_complex", vf_wide(frames, dur)]

    args += ["-t", f"{dur:.3f}", "-r", str(FPS),
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
             "-an", path]
    run(args, f"still {src}")


def build_video(shot, path, dur):
    src = shot["src"]
    if not os.path.exists(src):
        print(f"MISSING CLIP: {src}", file=sys.stderr)
        sys.exit(1)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
          f"fps={FPS},setsar=1,format=yuv420p")
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src,
         "-t", f"{dur:.3f}", "-vf", vf, "-r", str(FPS),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-an", path], f"clip {src}")


def build_black(shot, path, dur):
    text = shot.get("text", "")
    vf = f"fps={FPS},setsar=1,format=yuv420p"
    if text:
        safe = text.replace("'", "").replace(":", "")
        vf = (f"drawtext=fontfile='{ff_path(FONT_FILE)}':text='{safe}':"
              f"fontcolor=white:fontsize=110:"
              f"x=(w-text_w)/2:y=(h-text_h)/2," + vf)
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=black:s={W}x{H}:r={FPS}",
         "-t", f"{dur:.3f}", "-vf", vf,
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-an", path], "black frame")


_UNSET = object()


def main(shots=None, code=None, sfx=None, music=_UNSET, music_db=None,
         audio=None, subs=None, out_dir=None, tmp=None, tail=None):
    """Assemble one video. Called bare it renders the module's own
    SHOTS; make.py passes a storyboard's instead."""
    shots = [dict(x) for x in (SHOTS if shots is None else shots)]
    code = CODE if code is None else code
    sfx = SFX if sfx is None else sfx
    music = MUSIC if music is _UNSET else music
    music_db = MUSIC_DB if music_db is None else music_db
    audio = AUDIO if audio is None else audio
    subs = SUBS if subs is None else subs
    out_dir = OUT_DIR if out_dir is None else out_dir
    tmp = TMP if tmp is None else tmp
    tail = TAIL_SEC if tail is None else tail

    for d in (tmp, out_dir):
        os.makedirs(d, exist_ok=True)

    if not os.path.exists(audio):
        raise SystemExit(f"{audio} not found -- run make_vo.py first")

    # Stretch the final shot to cover the narration plus a tail, so the
    # audio is never truncated by -shortest and the video does not stop
    # on the last syllable.
    if os.path.exists("vo.json"):
        words = json.load(open("vo.json", encoding="utf-8"))["words"]
        vo_end = words[-1]["end"] if words else 0
        need = vo_end + tail
        if shots[-1]["end"] < need:
            print(f"  extending final shot {shots[-1]['end']:.1f}s "
                  f"-> {need:.1f}s to cover narration + {tail}s tail")
            shots[-1]["end"] = round(need, 2)
        elif shots[-1]["end"] > need + 1.5:
            print(f"  NOTE: shots run {shots[-1]['end'] - need:.1f}s past "
                  f"the narration -- trim SHOTS if that is not deliberate")
        print()

    parts = []
    for i, shot in enumerate(shots):
        dur = shot["end"] - shot["start"]
        if dur <= 0:
            raise SystemExit(f"shot {i}: end must be after start")
        path = os.path.join(tmp, f"{i:02d}.mp4")
        mode = shot["mode"]

        if mode in ("portrait", "wide"):
            build_still(shot, path, dur)
        elif mode == "video":
            build_video(shot, path, dur)
        elif mode == "black":
            build_black(shot, path, dur)
        else:
            raise SystemExit(f"shot {i}: unknown mode {mode!r}")

        label = shot.get("src") or shot.get("text") or "black"
        print(f"  [{i:02d}] {mode:8s} {dur:4.1f}s  {label}")
        parts.append(path)

    # Concat the shots.
    total = shots[-1]["end"]
    listfile = os.path.join(tmp, "concat.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{os.path.basename(p)}'\n")

    silent = os.path.join(tmp, "silent.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", silent], "concat")

    # Burn captions, mix audio, write the final file.
    final = os.path.join(out_dir, f"{code}.mp4")

    # ---- audio graph: voice + optional music bed + timed SFX ----
    # apad must be bounded. Left open it produces an infinite stream,
    # amix=duration=first then follows it forever, and -shortest does not
    # terminate a filtergraph: ffmpeg encodes the whole picture, writes
    # the frames, and then hangs before the moov atom -- leaving an mp4
    # every player rejects as invalid. whole_dur ends the pad exactly
    # where the picture ends.
    inputs = ["-i", silent, "-i", audio]
    chains = [f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,"
              f"apad=whole_dur={total:.3f}[voice]"]
    mix_labels = ["[voice]"]
    idx = 2

    if music and os.path.exists(music):
        inputs += ["-stream_loop", "-1", "-i", music]
        chains.append(
            f"[{idx}:a]volume={music_db}dB,afade=t=out:st={total-2.0:.2f}:d=2[bed]")
        mix_labels.append("[bed]")
        idx += 1
    elif music:
        print(f"  NOTE: music file {music} not found -- narration only")

    for path, at, gain in sfx:
        if not os.path.exists(path):
            print(f"  NOTE: sfx {path} not found -- skipped")
            continue
        inputs += ["-i", path]
        chains.append(
            f"[{idx}:a]volume={gain}dB,adelay={int(at*1000)}|{int(at*1000)}[s{idx}]")
        mix_labels.append(f"[s{idx}]")
        idx += 1

    if len(mix_labels) == 1:
        chains.append("[voice]anull[aout]")
    else:
        chains.append(
            "".join(mix_labels) +
            f"amix=inputs={len(mix_labels)}:duration=first:"
            f"dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95[aout]")

    vf = (f"subtitles={subs}:fontsdir='{ff_path(FONTS_DIR)}'"
          if os.path.exists(subs) else "null")
    if not os.path.exists(subs):
        print("  (no captions.ass -- run captions.py to add subtitles)")
    chains.insert(0, f"[0:v]{vf}[vout]")

    run(["ffmpeg", "-y"] + inputs +
        ["-filter_complex", ";".join(chains),
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-shortest", final], "final mux")

    print(f"\nwrote {final}")
    return final


if __name__ == "__main__":
    main()