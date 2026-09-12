"""
Shot list for 0001-galileo-pisa-myth-bust, composed from the scene library.

This is what "storyboard" means in practice until make.py exists: one
file per video that calls the scenes with that video's arguments and
prints the SHOTS block render.py needs. Copy it to video_0002.py for the
next one and change the content.

    python video_0001.py        # renders every scene, prints SHOTS + SFX

The narration is the master clock. Every `until` below is a real cut
point read out of vo.json -- where that sentence ends on the voiceover.
Scenes are tuned to fill their beat; the report says how close each one
landed, so you retune the scene rather than stretching the shot.

Stretching a shot past its clip is the one thing render.py will not tell
you about: build_video loops a clip that is too short and truncates one
that is too long, silently. These numbers agree by construction.
"""

from falling_bodies import drop_test
from scene_map_zoom import map_zoom
from scene_number_reveal import number_reveal
from scene_quote_card import quote_card
from scene_text_beat import text_beat
from scene_timeline import timeline
from scene_versus import versus

NARRATION_END = 42.14      # last word in vo.json
TAIL = 0.8                 # must match render.py TAIL_SEC

SHOTS, SFX = [], []


def shot(name, until, make, sfx_offset=None):
    """Render one scene into the beat that ends at `until`.

    sfx_offset: seconds into this clip where a sound lands, if any. Used
    to print the absolute time for render.py's SFX list.
    """
    start = SHOTS[-1]["end"] if SHOTS else 0.0
    actual = make(f"clips/{name}.mp4")
    SHOTS.append({"name": name, "start": start, "end": until,
                  "target": until - start, "actual": actual})
    if sfx_offset is not None:
        SFX.append((name, start + sfx_offset))


# --- the shots, in narration order --------------------------------

shot("01-myth", 4.0, lambda out: text_beat(
    "The Leaning Tower of Pisa.",
    kicker="the story everyone knows", hold=2.7, out=out))

# The spine of the whole video: four dates, and the twelve-year gap
# between the last two is the argument.
shot("02-dates", 15.5, lambda out: timeline(
    [(1564, "Galileo born"), (1622, "Viviani born"),
     (1642, "Galileo dies"), (1654, "the story written")],
    gap=(1642, 1654), gap_label="12 years",
    pace=2.4, hold=2.9, out=out))

shot("03-norecord", 18.7, lambda out: text_beat(
    "No letter. No witness. No other record.",
    hot="record", hold=1.65, out=out))

shot("04-delft", 22.9, lambda out: map_zoom(
    (52.0116, 4.3571),
    [("EUROPE", 22), ("THE NETHERLANDS", 3.2), ("DELFT", 0.22)],
    pin_label="Delft, 1586", per_step=0.95, hold=0.8, out=out))

shot("05-tentimes", 27.6, lambda out: number_reveal(
    10, "times heavier", sub="two lead balls, dropped together",
    count_time=1.1, hold=3.16, out=out))

# The clap is the payoff of the video, so the impact frame is placed
# first and the scene is built backwards from it. The extra time goes
# into hold_before -- never into fall_time, which is real physics: 30 ft
# is a 1.4s fall and stretching it would make the diagram a lie.
shot("06-drop", 32.1, lambda out: drop_test(
    ratio=10, height_label="30 ft", payoff="ONE SOUND",
    hold_before=2.3, fall_time=1.4, hold_after=0.8, out=out),
    sfx_offset=2.3 + 1.4)

shot("07-quote", 35.8, lambda out: quote_card(
    "Their two sounds seem to be a single clap.",
    who="Simon Stevin", source="De Beghinselen der Weeghconst, 1586",
    per_line=0.5, hold=1.95, out=out))

shot("08-52years", 39.3, lambda out: number_reveal(
    52, "years earlier", sub="Stevin 1586, Galileo 1638",
    count_time=0.9, hold=2.16, out=out))

# No winner: the script explains why Galileo is the famous one, it does
# not call him wrong. versus() takes a verdict; this line does not make
# one, so it does not get one.
shot("09-dutch", round(NARRATION_END + TAIL, 2), lambda out: versus(
    ("STEVIN", ["wrote in Dutch"]),
    ("GALILEO", ["wrote to be read"]),
    hold=2.52, out=out))


# --- the report ---------------------------------------------------

print("\n  shot             target   actual    drift")
worst = 0.0
for s in SHOTS:
    drift = s["actual"] - s["target"]
    worst = max(worst, abs(drift))
    flag = "   <-- retune this scene" if abs(drift) > 0.35 else ""
    print(f"  {s['name']:15s} {s['target']:6.2f}s {s['actual']:7.2f}s "
          f"{drift:+7.2f}s{flag}")

total = SHOTS[-1]["end"]
print(f"\n  picture {total:.2f}s   narration {NARRATION_END:.2f}s "
      f"+ {TAIL}s tail = {NARRATION_END + TAIL:.2f}s")
print(f"  worst drift {worst:+.2f}s")

print("\n# ---------- paste into render.py ----------")
print('CODE = "0001-galileo-pisa-myth-bust"')
print("SHOTS = [")
for s in SHOTS:
    print(f'    {{"mode": "video", "src": "clips/{s["name"]}.mp4", '
          f'"start": {s["start"]:.2f}, "end": {s["end"]:.2f}}},')
print("]")
for name, at in SFX:
    print(f'SFX = [("assets/knock.wav", {at:.2f}, -3)]'
          f'    # impact frame of {name}')
