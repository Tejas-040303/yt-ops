"""
Pick a subject, research it, write it, storyboard it.

    python auto.py                      # -> shots/NNNN.yaml, ready to render
    python auto.py --topic "how we weighed the Earth"
    python auto.py --seq 7              # force the sequence number

Then `python make.py shots/NNNN.yaml` turns that into a video, or run
`python make.py --auto` to do both in one command.

Everything this writes is a draft with its working shown. The research
call's raw output goes to research/NNNN-notes.md and the structured
claims to research/NNNN-claims.json, so what the machine found -- and
what it could not establish -- is readable before anything ships.

The gates
---------
config.yaml declares gates that nothing enforced until now. The ones
that can be checked mechanically are checked here and will stop the run:
word count, a named person, a year on screen, banned openers, and
similarity against every previous script. The ones that cannot be
checked by a program -- whether a claim is actually true -- are handed
to the model as constraints and left in the audit trail for a human.
That distinction is deliberate and is not a gap to be closed by
pretending.
"""

import argparse
import difflib
import inspect
import json
import os
import re
import sqlite3

import yaml

import brain

DB = "db.sqlite"
RESEARCH_DIR = "research"
SHOTS_DIR = "shots"

# Arguments every scene takes that the storyboard must NOT set: make.py
# solves all of them from the narration.
TIMING = {"hold", "hold_before", "hold_after", "lead", "per_word", "per_line",
          "per_step", "pace", "count_time", "roll", "drop", "out",
          "frames_dir", "fall_time"}


def load_config():
    return yaml.safe_load(open("config.yaml", encoding="utf-8"))


def catalogue():
    """The scene library, generated from the code so it cannot go stale."""
    from falling_bodies import drop_test
    from scene_map_zoom import map_zoom
    from scene_number_reveal import number_reveal
    from scene_quote_card import quote_card
    from scene_ramp import ramp
    from scene_text_beat import text_beat
    from scene_timeline import timeline
    from scene_versus import versus

    lines = []
    for name, fn in (("text_beat", text_beat), ("timeline", timeline),
                     ("drop_test", drop_test),
                     ("number_reveal", number_reveal),
                     ("quote_card", quote_card), ("versus", versus),
                     ("map_zoom", map_zoom), ("ramp", ramp)):
        args = [p for p in inspect.signature(fn).parameters if p not in TIMING]
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        lines.append(f"{name}({', '.join(args)})\n    {doc}")
    return "\n\n".join(lines)


def db():
    if not os.path.exists(DB):
        raise SystemExit(f"{DB} not found -- run: python init_db.py")
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def covered(con):
    return [f"{r[0]} -- {r[1]}" for r in
            con.execute("SELECT slug, title FROM topics").fetchall()]


def myths(con):
    return [r[0] for r in con.execute("SELECT myth FROM myth_blacklist")]


def next_seq(con):
    row = con.execute("SELECT MAX(id) FROM videos").fetchone()
    return (row[0] or 0) + 1


# --- gates --------------------------------------------------------

def check(script, person, cfg, con):
    """Returns a list of failures. Empty means it may proceed."""
    body = " ".join(l["text"] for l in script["lines"])
    words = len(body.split())
    lo, hi = cfg["script"]["target_words"]
    fails = []

    if not lo <= words <= hi:
        fails.append(f"{words} words, outside the {lo}-{hi} range")

    # The script declares who it names, so this gate works whether the
    # subject came from pick_topic or from --topic, which carries no
    # person at all.
    named = (script.get("person") or person or "").strip()
    surname = named.split()[-1] if named else ""
    has_person = bool(surname) and surname.lower() in body.lower()
    if cfg["gates"]["must_name_person"] and not has_person:
        fails.append("names nobody"
                     if not named else f"never says {named} in the script")

    has_year = bool(re.search(r"\b(1\d{3}|20\d{2})\b", body))
    if cfg["gates"]["must_name_place_or_year"] and not has_year:
        fails.append("no year anywhere -- a place may still satisfy the "
                     "rule, but a program cannot tell, so check by eye")

    opener = script["lines"][0]["text"].lower()
    for banned in cfg["script"]["banned_openers"]:
        if opener.startswith(banned.lower()):
            fails.append(f"opens with a banned opener: {banned!r}")

    limit = cfg["gates"]["max_similarity_to_past"]
    for (past,) in con.execute("SELECT body FROM scripts WHERE rejected = 0"):
        r = difflib.SequenceMatcher(None, body, past).ratio()
        if r > limit:
            fails.append(f"{r:.0%} similar to an earlier script "
                         f"(limit {limit:.0%})")
            break

    return fails, dict(words=words, has_person=has_person,
                       has_year=has_year)


# --- persistence --------------------------------------------------

def save(con, topic, data, script, seq):
    cur = con.cursor()
    cur.execute("INSERT INTO topics (slug, title, status, researched_at) "
                "VALUES (?, ?, 'ready', datetime('now'))",
                (topic["slug"], topic["title"]))
    topic_id = cur.lastrowid

    url_to_id = {}
    for s in data["sources"]:
        cur.execute("INSERT INTO sources (topic_id, url, title, publisher, "
                    "kind) VALUES (?, ?, ?, ?, ?)",
                    (topic_id, s["url"], s["title"], s["publisher"],
                     s["kind"]))
        url_to_id[s["url"]] = cur.lastrowid

    accounts = {}
    for stance, summary in (("popular", data["popular_version"]),
                            ("consensus", data["consensus_version"])):
        cur.execute("INSERT INTO accounts (topic_id, stance, label, summary) "
                    "VALUES (?, ?, ?, ?)",
                    (topic_id, stance, f"{stance} account", summary))
        accounts[stance] = cur.lastrowid

    for c in data["claims"]:
        # 'probable' not 'verified': a quote was produced, nobody has
        # confirmed it says what the claim says it says.
        cur.execute("INSERT INTO claims (account_id, text, verdict) "
                    "VALUES (?, ?, 'probable')",
                    (accounts["consensus"], c["text"]))
        claim_id = cur.lastrowid
        sid = url_to_id.get(c["source_url"])
        if sid:
            cur.execute("INSERT INTO claim_sources (claim_id, source_id, "
                        "direction, quote) VALUES (?, ?, 1, ?)",
                        (claim_id, sid, c["quote"]))

    cur.execute("INSERT INTO angles (topic_id, account_id, kind, hook, "
                "status) VALUES (?, ?, ?, ?, 'scripted')",
                (topic_id, accounts["consensus"], script["angle"],
                 script["hook"]))
    angle_id = cur.lastrowid

    body = " ".join(l["text"] for l in script["lines"])
    cur.execute("INSERT INTO scripts (angle_id, body, word_count, "
                "has_person, has_year) VALUES (?, ?, ?, ?, ?)",
                (angle_id, body, len(body.split()), 1, 1))
    script_id = cur.lastrowid

    code = f"{seq:04d}-{topic['slug']}-{script['angle']}"
    cur.execute("INSERT INTO videos (script_id, code) VALUES (?, ?)",
                (script_id, code))
    con.commit()
    return code


# --- the storyboard file -----------------------------------------

def write_yaml(path, code, cfg, script, shots, data):
    board = {
        "code": code,
        "voice": {"narrator": cfg["voice"]["narrator"],
                  "quote": cfg["voice"]["quote"],
                  "speed": cfg["voice"]["speed"]},
        "script": [{"text": l["text"], "gap": l["gap"],
                    **({"voice": "quote"} if l["voice"] == "quote" else {})}
                   for l in script["lines"]],
        "shots": [{"scene": s["scene"], "lines": [s["line"]],
                   "args": json.loads(s["args_json"])}
                  for s in sorted(shots["shots"], key=lambda s: s["line"])],
        "metadata": {
            "hook": script["description_hook"],
            "titles": script["titles"],
            "sources": [[s["title"], s["url"]] for s in data["sources"]],
            "hashtags": ["#history", "#science", "#space", "#didyouknow"],
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Drafted by auto.py. Every claim traces to "
                f"{RESEARCH_DIR}/{code[:4]}-claims.json;\n"
                f"# read {RESEARCH_DIR}/{code[:4]}-notes.md before this "
                f"ships, especially\n# the section on what could not be "
                f"established.\n\n")
        yaml.safe_dump(board, f, sort_keys=False, allow_unicode=True,
                       width=76, default_flow_style=False)
    return board


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--topic", help="skip topic selection, use this subject")
    ap.add_argument("--seq", type=int, help="sequence number for the code")
    a = ap.parse_args(argv)

    cfg = load_config()
    con = db()
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)
    seq = a.seq or next_seq(con)

    if a.topic:
        topic = {"slug": re.sub(r"[^a-z0-9]+", "-", a.topic.lower()).strip("-")[:40],
                 "title": a.topic, "person": "", "why": "asked for",
                 "gap": ""}
        print(f"\ntopic (given)  {topic['title']}")
    else:
        print("\ntopic")
        topic = brain.pick_topic(covered(con), cfg["channel"]["rule"])
        print(f"  {topic['title']}  [{topic['person']}]")
        print(f"  gap: {topic['gap']}")

    print("\nresearch  (domain-locked to config.yaml preferred_domains)")
    notes = brain.research(topic["title"], topic["person"],
                           cfg["sources"]["preferred_domains"])
    notes_path = os.path.join(RESEARCH_DIR, f"{seq:04d}-notes.md")
    open(notes_path, "w", encoding="utf-8").write(notes)
    print(f"  {notes_path}  ({len(notes.split())} words)")

    data = brain.extract(notes)
    claims_path = os.path.join(RESEARCH_DIR, f"{seq:04d}-claims.json")
    json.dump(data, open(claims_path, "w", encoding="utf-8"), indent=2)
    print(f"  {len(data['sources'])} sources, {len(data['claims'])} claims, "
          f"{len(data['unestablished'])} things it could not establish")

    if len(data["sources"]) < cfg["sources"]["min_sources_per_topic"]:
        raise SystemExit(
            f"  only {len(data['sources'])} sources, config wants "
            f"{cfg['sources']['min_sources_per_topic']}. Stopping: a thin "
            f"topic does not proceed to script.")
    if not data["claims"]:
        raise SystemExit("  no claim survived with a quote attached. "
                         "Stopping.")

    print("\nscript")
    script = brain.write_script(topic["title"], data["claims"], myths(con),
                                cfg["script"]["target_words"])
    fails, stats = check(script, topic["person"], cfg, con)
    print(f"  {stats['words']} words, {len(script['lines'])} lines, "
          f"angle {script['angle']}")
    for f in fails:
        print(f"  GATE FAILED: {f}")
    if fails:
        raise SystemExit("  rejected by the gates in config.yaml. Nothing "
                         "written to the database.")

    print("\nstoryboard")
    shots = brain.storyboard(script["lines"], data["claims"], catalogue())
    lines_covered = sorted(s["line"] for s in shots["shots"])
    if lines_covered != list(range(len(script["lines"]))):
        raise SystemExit(f"  shots cover lines {lines_covered}, script has "
                         f"0..{len(script['lines']) - 1}")
    for s in sorted(shots["shots"], key=lambda s: s["line"]):
        print(f"  {s['line']:02d}  {s['scene']}")

    code = save(con, topic, data, script, seq)
    path = os.path.join(SHOTS_DIR, f"{seq:04d}.yaml")
    write_yaml(path, code, cfg, script, shots, data)

    print(f"\nwrote {path}")
    print(f"  {brain.spend_line()}")
    print(f"\nRead {notes_path} before this ships -- the section on what "
          f"could not be established is the one that matters.")
    print(f"Then: python make.py {path}")
    return path


if __name__ == "__main__":
    main()
