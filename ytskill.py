"""
The bridge to the youtube-agent-skill fork.

Three of its tools earn a place here, each run as its own process with
--json, so the fork stays a plain checkout and nothing is copied in:

    lint_titles(titles, names)   skills/yt-package/title.py
    swipe(collected_json)        skills/yt-viral/swipe.py
    retention(csv, ...)          skills/yt-retention/retention.py

Where the fork lives: $YT_AGENT_SKILL, else config.yaml's
tools.youtube_agent_skill (relative to this file), else
../youtube-agent-skill. Clone it next to yt-ops:

    git clone https://github.com/Tejas-040303/youtube-agent-skill ../youtube-agent-skill

The title linter is advisory everywhere it is used: when the fork is
missing it says so and the pipeline carries on. retention_report.py,
whose whole job is the fork's retention reader, stops instead.

Not used: hookscore.py. Its formulas and word lists were built on
creator-economy hooks, and on video 1's real openers it rated every one
WEAK and misfiled "the only witness" as a superlative. A gate built on
it would push scripts toward "you" and "lose", not toward this channel.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def root():
    """The fork's checkout, or None if it is not there."""
    path = os.environ.get("YT_AGENT_SKILL")
    if not path:
        try:
            import yaml
            cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml"),
                                      encoding="utf-8"))
            path = (cfg.get("tools") or {}).get("youtube_agent_skill")
        except (OSError, ImportError):
            path = None
    path = os.path.join(HERE, path or "../youtube-agent-skill")
    path = os.path.normpath(path)
    return path if os.path.isdir(os.path.join(path, "skills")) else None


def _run(tool, args):
    base = root()
    if not base:
        return None, ("youtube-agent-skill not found -- clone it next to "
                      "yt-ops or set YT_AGENT_SKILL")
    script = os.path.join(base, "skills", tool)
    if not os.path.exists(script):
        return None, f"{script} missing -- is the fork checkout current?"
    p = subprocess.run([sys.executable, script, *args, "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None, (p.stdout + p.stderr).strip()[:400] or f"{tool} failed"
    try:
        return json.loads(p.stdout), None
    except json.JSONDecodeError:
        return None, f"{tool} printed something that is not JSON"


def lint_titles(titles, names=()):
    """Every title scored, best first. Returns (rows, note): rows is None
    when the linter could not run, and note says why."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(t.replace("\n", " ") for t in titles))
        path = f.name
    try:
        args = [path]
        names = [n for n in names if n]
        if names:
            args += ["--names", ",".join(names)]
        return _run(os.path.join("yt-package", "title.py"), args)
    finally:
        os.remove(path)


def swipe(collected, min_multiple=2.0):
    """Outliers from a collected listing, ranked by multiple over their own
    channel's median. Returns (result, note)."""
    return _run(os.path.join("yt-viral", "swipe.py"),
                [collected, "--min", str(min_multiple)])


def retention(csv_path, duration=None, hook_seconds=None, axis=None):
    """The fork's retention reading, as a dict. Returns (result, note)."""
    args = [csv_path]
    if duration:
        args += ["--duration", f"{duration:.2f}"]
    if hook_seconds:
        args += ["--hook-seconds", f"{hook_seconds:.2f}"]
    if axis:
        args += ["--axis", axis]
    return _run(os.path.join("yt-retention", "retention.py"), args)
