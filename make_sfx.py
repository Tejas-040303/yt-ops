"""
Synthesise the impact sound for the Delft beat.

Two lead balls hitting a wooden board produce one sharp, short, woody
knock. This builds it from a noise transient plus damped resonances,
so it is original audio: no library, no licence, no attribution.

Usage:  python make_sfx.py
Writes: assets/knock.wav  (48kHz mono)
"""

import os

import numpy as np
import soundfile as sf

SR = 48000
DUR = 0.45
OUT = "assets/knock.wav"

# Damped resonances of a struck wooden board: (Hz, amplitude, decay 1/s)
PARTIALS = [
    (168.0, 1.00, 26.0),
    (392.0, 0.62, 34.0),
    (735.0, 0.34, 46.0),
    (1240.0, 0.20, 62.0),
    (2100.0, 0.11, 85.0),
]


def main():
    os.makedirs("assets", exist_ok=True)
    rng = np.random.default_rng(7)          # fixed seed = reproducible
    n = int(SR * DUR)
    t = np.arange(n) / SR

    # 1. Attack: a very short filtered noise burst -- the "crack".
    noise = rng.normal(0, 1, n)
    burst = noise * np.exp(-t * 300.0)
    # crude one-pole low-pass to take the fizz off
    lp = np.zeros(n)
    a = 0.11          # heavier low-pass: wood, not click
    for i in range(1, n):
        lp[i] = a * burst[i] + (1 - a) * lp[i - 1]
    body = lp * 1.1      # noise sits under the wood, not over it

    # 2. Body: damped sine partials -- the "wood".
    for f, amp, decay in PARTIALS:
        body += 2.2 * amp * np.sin(2 * np.pi * f * t) * np.exp(-t * decay)

    # 3. Sharp attack envelope, quick natural release.
    attack = np.minimum(1.0, t / 0.0016)
    body *= attack

    # 4. Soft clip so the transient has weight without digital clipping.
    body = np.tanh(body * 1.35)
    body /= np.max(np.abs(body))
    body *= 0.92

    # 5. Fade the last 30ms to zero so there is no click at the tail.
    fade = int(SR * 0.03)
    body[-fade:] *= np.linspace(1, 0, fade)

    sf.write(OUT, body.astype(np.float32), SR)

    peak = np.max(np.abs(body))
    rms = np.sqrt(np.mean(body ** 2))
    # time to fall 60dB below peak
    env = np.abs(body)
    thresh = peak * 10 ** (-60 / 20)
    idx = np.where(env > thresh)[0]
    t60 = idx[-1] / SR if len(idx) else DUR

    print(f"wrote {OUT}")
    print(f"  {DUR:.2f}s @ {SR}Hz   peak {peak:.2f}   rms {rms:.3f}")
    print(f"  decays to -60dB at {t60*1000:.0f}ms")


if __name__ == "__main__":
    main()