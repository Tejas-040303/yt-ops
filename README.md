# yt-ops

Pipeline for "Had To Find Out" — short-form videos on how discoveries
were actually made.

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python init_db.py

Download into project root (not in git, ~340 MB):
- kokoro-v1.0.onnx
- voices-v1.0.bin

from github.com/thewh1teagle/kokoro-onnx releases

## Requires
ffmpeg (with --enable-libass), espeak-ng