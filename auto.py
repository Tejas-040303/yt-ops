"""
Pick a subject, research it, write it, storyboard it.

    python auto.py                      # -> shots/NNNN.yaml, ready to render
    python auto.py --lane curiosity     # force a lane; default is the one behind its share
    python auto.py --topic "how we weighed the Earth"
    python auto.py --swipe research/swipe.json   # steer the topic with what is working
    python auto.py --seq 7              # force the sequence number

Lanes
-----
config.yaml defines three: found_out (how somebody found something
out), curiosity (one everyday question answered properly) and trending
(the checkable story behind something in the news). Without --lane, the
run makes whichever lane is furthest behind its configured share of
everything made so far. Each lane brings its own gates, source rules
and search domains; the trending lane also searches the news first,
because a model's own knowledge of "this week" is months old.

--swipe takes a listing collected from comparable channels (see
youtube-agent-skill/skills/yt-viral) and hands the outliers to topic
selection as direction -- never as titles to copy.

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
word count, a named person, a year or a date, a checkable specific,
banned openers, quotation length, enough sources of the right kind, and
similarity against every previous script. The ones that cannot be
checked by a program -- whether a claim is actually true -- are handed
to the model as constraints and left in the audit trail for a human.
That distinction is deliberate and is not a gap to be closed by
pretending.
"""

import argparse
import datetime
import difflib
import inspect
import json
import os
import re
import sqlite3

import yaml

import brain
import ytskill

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
    # Databases built before lanes existed: every topic in them was the
    # history-of-discovery kind, which is found_out.
    cols = [r[1] for r in con.execute("PRAGMA table_info(topics)")]
    if "lane" not in cols:
        con.execute("ALTER TABLE topics ADD COLUMN lane TEXT NOT NULL "
                    "DEFAULT 'found_out'")
        con.commit()
    return con


def covered(con):
    return [f"{r[0]} -- {r[1]}" for r in
            con.execute("SELECT slug, title FROM topics").fetchall()]


def myths(con):
    return [r[0] for r in con.execute("SELECT myth FROM myth_blacklist")]


def next_seq(con):
    row = con.execute("SELECT MAX(id) FROM videos").fetchone()
    return (row[0] or 0) + 1


def choose_lane(con, lanes):
    """The lane furthest behind its share of everything made so far.

    Deficit, not a dice roll: the mix comes out right over any short run
    instead of only on average, and the choice is reproducible. Ties go
    to the lane listed first in config.yaml."""
    made = dict(con.execute("SELECT lane, COUNT(*) FROM topics "
                            "GROUP BY lane").fetchall())
    total = sum(made.get(n, 0) for n in lanes) + 1
    return max(lanes, key=lambda n: lanes[n]["share"] * total
               - made.get(n, 0))


# --- gates --------------------------------------------------------

MONTHS = ("january|february|march|april|may|june|july|august|september|"
          "october|november|december")
# "one" and "half" are left out: "one of the reasons" is not a figure.
NUMBER_WORDS = ("two|three|four|five|six|seven|eight|nine|ten|eleven|"
                "twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
                "ninety|hundred|thousand|million|billion|dozen")


def specifics(body):
    """Checkable specifics a program can see: figures, number words, and
    capitalised words that do not open a sentence (names, places).

    A floor, not a judge: it stops a script made only of generalities,
    and cannot tell a telling number from a decorative one."""
    found = re.findall(r"\b\d[\d,.]*\b", body)
    found += re.findall(rf"\b({NUMBER_WORDS})\b", body, re.I)
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        found += [w for w in re.findall(r"[A-Za-z][\w'-]*", sentence)[1:]
                  if w[0].isupper() and w != "I"]
    return found


def check(script, person, cfg, con, lane):
    """Returns a list of failures. Empty means it may proceed."""
    gates = {**cfg["gates"], **lane["gates"]}
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
    if gates.get("must_name_person") and not has_person:
        fails.append("names nobody"
                     if not named else f"never says {named} in the script")

    has_year = bool(re.search(r"\b(1\d{3}|20\d{2})\b", body))
    if gates.get("must_name_place_or_year") and not has_year:
        fails.append("no year anywhere -- a place may still satisfy the "
                     "rule, but a program cannot tell, so check by eye")

    has_date = has_year or bool(re.search(rf"\b({MONTHS})\b", body, re.I))
    if gates.get("must_name_date") and not has_date:
        fails.append("no year or month -- this lane has to say when")

    has_specific = bool(specifics(body))
    if gates.get("must_carry_specific") and not has_specific:
        fails.append("no number, year or name anywhere -- generalities "
                     "only, which is the generic-fact video this channel "
                     "exists not to make")

    cap = cfg.get("media", {}).get("max_quote_words")
    for l in script["lines"]:
        n = len(l["text"].split())
        if cap and l.get("voice") == "quote" and n > cap:
            fails.append(f"a {n}-word quotation -- the cap is {cap}")

    opener = script["lines"][0]["text"].lower()
    for banned in cfg["script"]["banned_openers"]:
        if opener.startswith(banned.lower()):
            fails.append(f"opens with a banned opener: {banned!r}")

    limit = gates["max_similarity_to_past"]
    for (past,) in con.execute("SELECT body FROM scripts WHERE rejected = 0"):
        r = difflib.SequenceMatcher(None, body, past).ratio()
        if r > limit:
            fails.append(f"{r:.0%} similar to an earlier script "
                         f"(limit {limit:.0%})")
            break

    return fails, dict(words=words, has_person=has_person,
                       has_year=has_year, has_date=has_date,
                       has_specific=has_specific)


def check_sources(data, lane):
    """A thin or weakly-sourced topic does not proceed to script."""
    g = lane["gates"]
    fails = []
    if len(data["sources"]) < g["min_sources"]:
        fails.append(f"only {len(data['sources'])} sources, this lane "
                     f"wants {g['min_sources']}")
    strong = [s for s in data["sources"] if s["kind"] in g["strong_kinds"]]
    if len(strong) < g["min_strong_sources"]:
        fails.append(f"{len(strong)} {' or '.join(g['strong_kinds'])} "
                     f"source(s), this lane wants "
                     f"{g['min_strong_sources']}")
    if not data["claims"]:
        fails.append("no claim survived with a quote attached")
    return fails


def check_quote_cards(shots, cap):
    """On-screen quotations obey the same cap as spoken ones."""
    fails = []
    for s in shots["shots"]:
        if s["scene"] != "quote_card" or not cap:
            continue
        text = json.loads(s["args_json"]).get("text", "")
        if len(text.split()) > cap:
            fails.append(f"line {s['line']}: a {len(text.split())}-word "
                         f"quote_card -- the cap is {cap}")
    return fails


def rank_titles(titles, names):
    """Titles best-first by the fork's linter. Advisory: a missing fork
    or a failed run leaves the order as written."""
    rows, note = ytskill.lint_titles(titles, names)
    if rows is None:
        print(f"  title lint skipped: {note}")
        return titles
    for r in rows:
        issues = ", ".join(k for k, _ in r["issues"]) or "clean"
        print(f"  {r['score']:3d}  {r['title']}   [{issues}]")
    return [r["title"] for r in rows]


def leads_from_swipe(path, per_channel=4):
    """The best outliers from EACH channel, not the best overall.

    Channels differ in how hit-driven they are, not just in size: on the
    first real collection Veritasium's Shorts ran to 14.7x their median
    and Kurzgesagt's topped out at 3.4x, so a plain top-8 was six
    Veritasium. The multiple already corrects for size; this corrects
    for spread."""
    if not os.path.exists(path):
        raise SystemExit(f"  --swipe {path}: no such file")
    rows, note = ytskill.swipe(path)
    if rows is None:
        print(f"  swipe skipped: {note}")
        return ""
    by = {}
    for r in rows["outliers"]:                     # already best-first
        by.setdefault(r["channel"], []).append(r)
    top = sorted((r for rs in by.values() for r in rs[:per_channel]),
                 key=lambda r: -r["multiple"])
    print(f"  {len(top)} outliers from {path}: " + ", ".join(
        f"{min(len(rs), per_channel)} {ch}" for ch, rs in by.items()))
    try:
        when = json.load(open(path, encoding="utf-8")).get("collected_at")
        age = (datetime.date.today()
               - datetime.date.fromisoformat(when)).days
        if age > 14:
            print(f"  NOTE  collected {age} days ago -- re-run "
                  f"collect_swipe.py for what is working now")
    except (AttributeError, TypeError, ValueError):
        pass   # a hand-made list with no collected_at
    return "\n".join(f"- {r['multiple']}x its channel's median "
                     f"({r['channel']}): {r['title']}" for r in top)


# --- persistence --------------------------------------------------

def unique_slug(con, slug):
    """topics.slug is UNIQUE. A repeated slug -- the same --topic twice, or
    a model reusing one -- must not crash the run after the API calls
    have been paid for."""
    taken = {r[0] for r in con.execute("SELECT slug FROM topics")}
    n, out = 2, slug
    while out in taken:
        out, n = f"{slug}-{n}", n + 1
    return out


def save(con, topic, data, script, seq, lane_name, stats):
    topic = {**topic, "slug": unique_slug(con, topic["slug"])}
    cur = con.cursor()
    cur.execute("INSERT INTO topics (slug, title, status, researched_at, "
                "lane) VALUES (?, ?, 'ready', datetime('now'), ?)",
                (topic["slug"], topic["title"], lane_name))
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
                (angle_id, body, len(body.split()),
                 int(stats["has_person"]), int(stats["has_year"])))
    script_id = cur.lastrowid

    code = f"{seq:04d}-{topic['slug']}-{script['angle']}"
    cur.execute("INSERT INTO videos (script_id, code) VALUES (?, ?)",
                (script_id, code))
    con.commit()
    return code


# --- the storyboard file -----------------------------------------

def write_yaml(path, code, cfg, script, shots, data, lane_name):
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
            "hashtags": cfg["lanes"][lane_name]["hashtags"],
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Drafted by auto.py, {lane_name} lane. Every claim "
                f"traces to "
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
    ap.add_argument("--lane", help="found_out, curiosity or trending; "
                                   "default: the one furthest behind its share")
    ap.add_argument("--swipe", help="a collected listing for yt-viral's "
                                    "swipe.py, used to steer the topic")
    ap.add_argument("--seq", type=int, help="sequence number for the code")
    a = ap.parse_args(argv)

    cfg = load_config()
    lanes = cfg["lanes"]
    if a.lane and a.lane not in lanes:
        raise SystemExit(f"no lane {a.lane!r} -- config.yaml has "
                         f"{', '.join(lanes)}")
    con = db()
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)
    seq = a.seq or next_seq(con)
    today = datetime.date.today().isoformat()

    lane_name = a.lane or choose_lane(con, lanes)
    lane = lanes[lane_name]
    banned = cfg["gates"]["banned_topic_areas"] + lane.get("extra_banned", [])
    print(f"\nlane  {lane_name}" + ("" if a.lane else "  (furthest behind "
                                     "its share)"))

    if a.topic:
        topic = {"slug": re.sub(r"[^a-z0-9]+", "-", a.topic.lower()).strip("-")[:40],
                 "title": a.topic, "person": "", "why": "asked for",
                 "gap": ""}
        print(f"\ntopic (given)  {topic['title']}")
    else:
        print("\ntopic")
        leads = (leads_from_swipe(
            a.swipe, cfg.get("swipe", {}).get("leads_per_channel", 4))
            if a.swipe else "")
        if lane_name == "trending":
            news = brain.scout(lane, lane["domains"], banned, today)
            open(os.path.join(RESEARCH_DIR, f"{seq:04d}-scout.md"), "w",
                 encoding="utf-8").write(news)
            leads = (leads + "\n\nIn the news (pick from these):\n"
                     + news).strip()
        topic = brain.pick_topic(covered(con), cfg["channel"]["rule"],
                                 lane_name, lane, banned, today, leads)
        print(f"  {topic['title']}" + (f"  [{topic['person']}]"
                                       if topic["person"] else ""))
        print(f"  gap: {topic['gap']}")

    print(f"\nresearch  (domain-locked to the {lane_name} lane's domains)")
    notes = brain.research(topic["title"], topic["person"], lane["domains"],
                           today, lane)
    notes_path = os.path.join(RESEARCH_DIR, f"{seq:04d}-notes.md")
    open(notes_path, "w", encoding="utf-8").write(notes)
    print(f"  {notes_path}  ({len(notes.split())} words)")

    data = brain.extract(notes)
    claims_path = os.path.join(RESEARCH_DIR, f"{seq:04d}-claims.json")
    json.dump(data, open(claims_path, "w", encoding="utf-8"), indent=2)
    print(f"  {len(data['sources'])} sources, {len(data['claims'])} claims, "
          f"{len(data['unestablished'])} things it could not establish")

    thin = check_sources(data, lane)
    for f in thin:
        print(f"  GATE FAILED: {f}")
    if thin:
        raise SystemExit("  stopping: a thin topic does not proceed to "
                         "script.")

    print("\nscript")
    script = brain.write_script(topic["title"], data["claims"], myths(con),
                                cfg["script"]["target_words"], lane_name,
                                lane, cfg.get("media", {}), banned)
    fails, stats = check(script, topic["person"], cfg, con, lane)
    print(f"  {stats['words']} words, {len(script['lines'])} lines, "
          f"angle {script['angle']}")
    for f in fails:
        print(f"  GATE FAILED: {f}")
    if fails:
        raise SystemExit("  rejected by the gates in config.yaml. Nothing "
                         "written to the database.")

    print("\ntitles  (youtube-agent-skill title.py, best first)")
    script["titles"] = rank_titles(
        script["titles"], [script.get("person") or topic["person"]])

    print("\nstoryboard")
    cap = cfg.get("media", {}).get("max_quote_words")
    shots = brain.storyboard(script["lines"], data["claims"], catalogue(),
                             cap)
    lines_covered = sorted(s["line"] for s in shots["shots"])
    if lines_covered != list(range(len(script["lines"]))):
        raise SystemExit(f"  shots cover lines {lines_covered}, script has "
                         f"0..{len(script['lines']) - 1}")
    long_quotes = check_quote_cards(shots, cap)
    for f in long_quotes:
        print(f"  GATE FAILED: {f}")
    if long_quotes:
        raise SystemExit("  rejected: on-screen quotation over the cap. "
                         "Nothing written to the database.")
    for s in sorted(shots["shots"], key=lambda s: s["line"]):
        print(f"  {s['line']:02d}  {s['scene']}")

    code = save(con, topic, data, script, seq, lane_name, stats)
    path = os.path.join(SHOTS_DIR, f"{seq:04d}.yaml")
    write_yaml(path, code, cfg, script, shots, data, lane_name)

    print(f"\nwrote {path}")
    print(f"  {brain.spend_line()}")
    print(f"\nRead {notes_path} before this ships -- the section on what "
          f"could not be established is the one that matters.")
    print(f"Then: python make.py {path}")
    return path


if __name__ == "__main__":
    main()
