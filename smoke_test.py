import soundfile as sf
from kokoro_onnx import Kokoro
from faster_whisper import WhisperModel

TEXT = """Everyone knows Galileo dropped two balls off the Leaning Tower of Pisa.

One person wrote that down. Vincenzo Viviani, his assistant, around 1654. Viviani was born in 1622. He wasn't there — Galileo had been dead twelve years.

But somebody did do it.

Delft, 1586. Simon Stevin climbs a church tower with two lead balls. One is ten times heavier. He drops them thirty feet onto a board below.

He doesn't watch them. He listens.

The experience against Aristotle is the following: Let us take (as the very learned Mr. Jan Cornets de Groot, most industrious investigator of the secrets of Nature, and myself have done) two spheres of lead, the one ten times larger and heavier than the other, and drop them together from a height of 30 feet on to a board or something on which they give a perceptible sound....It will show that the lightest ball is not ten times longer under way than the heaviest, but they fall together at the same time on the ground, so that their two sounds seem to be a single clap.

One sound. Twenty years before Galileo was famous.

Galileo's real experiment was slower. Bronze balls, a wooden ramp, a water clock. Less dramatic. Far better science."""

k = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
samples, sr = k.create(TEXT, voice="bf_emma", speed=1.05, lang="en-us")
sf.write("test5.wav", samples, sr)
print(f"wrote test5.wav ({len(samples)/sr:.1f}s)")

m = WhisperModel("base.en", device="cpu", compute_type="int8")
segments, _ = m.transcribe("test5.wav", word_timestamps=True)
for seg in segments:
    for w in seg.words:
        print(f"{w.start:6.2f} - {w.end:6.2f}  {w.word}")