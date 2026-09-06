import numpy as np, soundfile as sf, json
from kokoro_onnx import Kokoro
from faster_whisper import WhisperModel

NARRATOR = "bf_emma"
QUOTE    = "bm_george"
SPEED    = 1.05

# (voice, text, seconds of silence AFTER this segment)
SEGMENTS = [
    (NARRATOR,
     "Everyone knows Galileo dropped two balls off the Leaning Tower of Pisa. "
     "One person wrote that down. Vincenzo Viviani, his assistant. He wrote it in 1654. "
     "Viviani was born in 1622. Galileo had been dead twelve years. "
     "No letter. No witness. No other record.",
     0.7),

    (NARRATOR,
     "But somebody did do it. "
     "Delft, 1586. Simon Stevin climbs a church tower with two lead balls. "
     "One is ten times heavier. He drops them thirty feet onto a board. "
     "He doesn't watch them. He listens.",
     1.2),                                   # <- the silence before the clap

    (QUOTE,
     "Their two sounds seem to be a single clap.",
     0.6),

    (NARRATOR,
     "Fifty-two years before Galileo published his own version. "
     "Stevin wrote in Dutch. Galileo wrote to be read.",
     0.0),
]

k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
audio, sr = [], None
timeline = []
cursor = 0.0

for i, (voice, text, gap) in enumerate(SEGMENTS):
    samples, sr = k.create(text, voice=voice, speed=SPEED, lang="en-us")
    dur = len(samples) / sr
    timeline.append({"seg": i, "voice": voice, "start": round(cursor, 2),
                     "end": round(cursor + dur, 2), "text": text})
    audio.append(samples)
    cursor += dur
    if gap:
        audio.append(np.zeros(int(gap * sr), dtype=samples.dtype))
        cursor += gap

full = np.concatenate(audio)
sf.write("vo.wav", full, sr)
print(f"vo.wav  {len(full)/sr:.1f}s")
for t in timeline:
    print(f"  {t['start']:5.1f} - {t['end']:5.1f}  {t['voice']}")

# word-level timings for captions
m = WhisperModel("base.en", device="cpu", compute_type="int8")
segments, _ = m.transcribe("vo.wav", word_timestamps=True)
words = [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
         for s in segments for w in s.words]
json.dump({"timeline": timeline, "words": words},
          open("vo.json", "w"), indent=2)
print(f"vo.json  {len(words)} words")