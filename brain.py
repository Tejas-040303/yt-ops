"""
The Claude API calls that research and write a video.

Everything here produces *drafts*. The audit trail is the point: each
step writes what it found to disk, so the research call's raw output --
quotes, URLs, what it could not find -- is readable before a word of it
reaches a script.

Needs ANTHROPIC_API_KEY in the environment (or a .env next to this file).

    from brain import pick_topic, research, extract, write_script, storyboard

Why the search is domain-locked
-------------------------------
The niche is myth-dense. Asked to research Galileo and the Tower of
Pisa, a model returns the myth, confidently, citing blogs that repeat
it. config.yaml lists the domains that are allowed to be cited, and
that list is handed to the server-side web_search tool as
allowed_domains -- so a blog is not "discouraged", it is unreachable.
Every claim must then carry a verbatim quote from one of those pages,
and a claim that cannot produce one does not survive extract().
"""

import json
import os
import sys

MODEL = "claude-opus-5"

# Listed Opus 5 rates, for the cost line only. Not billing.
USD_IN, USD_OUT = 5.00 / 1e6, 25.00 / 1e6

MAX_CONTINUATIONS = 5     # pause_turn restarts before giving up
_spend = {"in": 0, "out": 0, "calls": 0}


def _client():
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "pip install anthropic  -- needed for the research and script "
            "steps. Everything downstream of the storyboard runs without it.")
    if not (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("ANTHROPIC_API_KEY"):
                    os.environ["ANTHROPIC_API_KEY"] = \
                        line.split("=", 1)[1].strip().strip('"').strip("'")
    if not (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Put it in the environment or in a .env "
            "file next to brain.py as ANTHROPIC_API_KEY=sk-ant-...")
    return anthropic.Anthropic(timeout=900.0)


def _charge(usage):
    _spend["in"] += usage.input_tokens
    _spend["out"] += usage.output_tokens
    _spend["calls"] += 1


def spend_line():
    d = _spend["in"] * USD_IN + _spend["out"] * USD_OUT
    return (f"{_spend['calls']} API calls, {_spend['in']:,} in / "
            f"{_spend['out']:,} out tokens, about ${d:.2f} at listed "
            f"{MODEL} rates")


def _text(message):
    return "\n".join(b.text for b in message.content if b.type == "text")


def _ask(system, prompt, schema=None, tools=None, effort="high",
         max_tokens=16000, label=""):
    """One turn, with the server-tool pause_turn loop handled.

    A long server-tool turn stops with stop_reason 'pause_turn' after the
    server's own sampling limit. Resuming means re-sending the assistant
    turn with no extra user message -- the API sees the trailing
    server_tool_use block and picks up where it left off.
    """
    import anthropic

    client = _client()
    output_config = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}

    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  thinking={"type": "adaptive"},
                  output_config=output_config)
    if tools:
        kwargs["tools"] = tools

    messages = [{"role": "user", "content": prompt}]
    try:
        response = client.messages.create(messages=messages, **kwargs)
        for _ in range(MAX_CONTINUATIONS):
            if response.stop_reason != "pause_turn":
                break
            messages = messages[:1] + [
                {"role": "assistant", "content": response.content}]
            response = client.messages.create(messages=messages, **kwargs)
        else:
            raise SystemExit(f"{label}: still paused after "
                             f"{MAX_CONTINUATIONS} continuations")
    except anthropic.AuthenticationError:
        raise SystemExit("ANTHROPIC_API_KEY was rejected.")
    except anthropic.RateLimitError as e:
        raise SystemExit(f"Rate limited. Retry after "
                         f"{e.response.headers.get('retry-after', '60')}s.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"{label}: API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit(f"{label}: could not reach the API. Check the network.")

    _charge(response.usage)
    if response.stop_reason == "refusal":
        why = getattr(response.stop_details, "explanation", "") or ""
        raise SystemExit(f"{label}: the model declined. {why}")
    if response.stop_reason == "max_tokens":
        print(f"  NOTE: {label} hit max_tokens -- output may be cut short",
              file=sys.stderr)

    body = _text(response)
    if schema:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise SystemExit(f"{label}: expected JSON, got:\n{body[:800]}")
    return body


# --- the four steps ----------------------------------------------

TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "slug": {"type": "string"},
        "title": {"type": "string"},
        "person": {"type": "string"},
        "why": {"type": "string"},
        "gap": {"type": "string"},
    },
    "required": ["slug", "title", "person", "why", "gap"],
    "additionalProperties": False,
}


def pick_topic(avoid, rule):
    """A discovery story nobody on this channel has told yet."""
    return _ask(
        system=(
            "You choose subjects for a short-form channel about the history "
            "of scientific discovery.\n\n"
            f"The channel rule, which is absolute: {rule}\n\n"
            "A subject qualifies only if it is a story about how somebody "
            "found something out -- a named person, in a named place, in a "
            "known year. Not a fact, not a list, not a phenomenon. The "
            "strongest subjects are ones where the popular version and the "
            "scholarly version disagree, because that gap is the video.\n\n"
            "Space, physics, astronomy, geology, medicine and measurement "
            "are all in range. Avoid: medical or financial advice, "
            "religion, current conflicts, atrocity, and controversy about "
            "living people."),
        prompt=(
            "Propose one subject.\n\n"
            "Already covered, do not repeat or closely overlap:\n"
            + ("\n".join(f"- {a}" for a in avoid) or "- nothing yet")
            + "\n\nslug: lowercase-hyphenated, 2-4 words.\n"
              "person: the named human the story turns on.\n"
              "why: one sentence on why it is worth 45 seconds.\n"
              "gap: what most people believe, versus what the record says. "
              "If there is no such gap, say so plainly rather than "
              "inventing one."),
        schema=TOPIC_SCHEMA, effort="medium", label="pick_topic")


def research(topic, person, domains):
    """Search the allowed domains and report back with verbatim quotes."""
    tool = {"type": "web_search_20260209", "name": "web_search",
            "max_uses": 12, "allowed_domains": list(domains)}
    return _ask(
        system=(
            "You are a research assistant for a channel whose entire premise "
            "is that it checks things. You may only cite the domains the "
            "search tool allows you to reach. If something cannot be "
            "supported from those, say it cannot -- do not reach for what "
            "you remember.\n\n"
            "Quote exactly. A paraphrase is not a quote. If you cannot find "
            "the sentence that supports a claim, the claim does not exist."),
        prompt=(
            f"Subject: {topic}\nPerson: {person}\n\n"
            "Search, read, and report:\n\n"
            "1. SOURCES -- for each page you actually used: the URL, its "
            "title, its publisher, and whether it is primary, scholarly, "
            "encyclopedia or museum.\n\n"
            "2. THE POPULAR VERSION -- what the widely repeated story says, "
            "and where that version comes from if you can establish it.\n\n"
            "3. THE RECORD -- what the sources actually support. Names, "
            "places, years, quantities.\n\n"
            "4. CLAIMS -- every specific factual statement a script could "
            "make, each with the verbatim sentence from a source that backs "
            "it, and which URL it came from.\n\n"
            "5. WHAT YOU COULD NOT ESTABLISH -- be specific. This section "
            "matters more than the others."),
        tools=[tool], max_tokens=24000, label="research")


CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "publisher": {"type": "string"},
                    "kind": {"type": "string",
                             "enum": ["primary", "scholarly", "encyclopedia",
                                      "museum", "popular", "unknown"]},
                },
                "required": ["url", "title", "publisher", "kind"],
                "additionalProperties": False,
            },
        },
        "popular_version": {"type": "string"},
        "consensus_version": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "quote": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["text", "quote", "source_url"],
                "additionalProperties": False,
            },
        },
        "unestablished": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sources", "popular_version", "consensus_version",
                 "claims", "unestablished"],
    "additionalProperties": False,
}


def extract(research_text):
    """Turn the research prose into rows. No new facts may appear here."""
    return _ask(
        system=(
            "You restructure research notes into data. You add nothing. "
            "Every claim you emit must already appear in the notes, and its "
            "quote must be copied character for character from them. If a "
            "claim in the notes has no quote, drop the claim."),
        prompt=f"Restructure these notes.\n\n---\n{research_text}\n---",
        schema=CLAIMS_SCHEMA, effort="medium", label="extract")


SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "angle": {"type": "string",
                  "enum": ["myth_bust", "origin", "mechanism", "person",
                           "consequence", "unknown_still"]},
        "hook": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "gap": {"type": "number"},
                    "voice": {"type": "string",
                              "enum": ["narrator", "quote"]},
                },
                "required": ["text", "gap", "voice"],
                "additionalProperties": False,
            },
        },
        "titles": {"type": "array", "items": {"type": "string"}},
        "description_hook": {"type": "string"},
    },
    "required": ["angle", "hook", "lines", "titles", "description_hook"],
    "additionalProperties": False,
}


def write_script(topic, claims, myths, limits):
    lo, hi = limits
    return _ask(
        system=(
            "You write 45-second scripts for a channel about how discoveries "
            "were actually made. Not what is true -- how we came to know it.\n\n"
            "Hard rules:\n"
            f"- {lo}-{hi} words total.\n"
            "- Name a person. Name a place or a year.\n"
            "- Every factual statement must come from the claims you are "
            "given. You may not add a number, a date or a name that is not "
            "in them. If a line needs a fact you do not have, cut the line.\n"
            "- The video stands alone. No 'as we saw last time', no part 2.\n"
            "- Do not open with 'Did you know', 'Hey guys', 'In this video' "
            "or 'Let's dive in'.\n"
            "- One line may be a verbatim source quotation, marked "
            "voice='quote'. Its text must match a quote in the claims "
            "exactly.\n\n"
            "Write in short sentences. One line per sentence-group -- a "
            "line is what one shot will sit under, so break where the "
            "picture should change. gap is the silence after a line in "
            "seconds: 0 inside a thought, 0.6-1.2 before a payoff."),
        prompt=(
            f"Subject: {topic}\n\n"
            f"Claims you may use:\n{json.dumps(claims, indent=2)}\n\n"
            f"Known-false, never assert these as true:\n"
            + "\n".join(f"- {m}" for m in myths)
            + "\n\nWrite the script. Also give 5 title options under 60 "
              "characters, and one description hook of 2-3 sentences."),
        schema=SCRIPT_SCHEMA, label="write_script")


SHOTS_SCHEMA = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "scene": {"type": "string",
                              "enum": ["text_beat", "timeline", "drop_test",
                                       "number_reveal", "quote_card",
                                       "versus", "map_zoom", "ramp"]},
                    "args_json": {"type": "string"},
                },
                "required": ["line", "scene", "args_json"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["shots"],
    "additionalProperties": False,
}


def storyboard(lines, claims, catalogue):
    return _ask(
        system=(
            "You storyboard a narrated short by choosing, for each line of "
            "script, one scene from a fixed library. You may only use the "
            "scenes listed, with the arguments they take.\n\n"
            "Rules the renderer enforces:\n"
            "- Exactly one shot per script line, in order, covering every "
            "line. Shot i covers line i.\n"
            "- Do not set any timing or hold argument. The renderer solves "
            "every duration from the narration. Give content only.\n"
            "- Every date, number, name and quotation you put on screen "
            "must come from the claims. On-screen text that states a fact "
            "not in the claims is the one unrecoverable error here.\n\n"
            "Choose for meaning: a date becomes timeline, a quotation "
            "becomes quote_card, a figure becomes number_reveal, two "
            "competing versions become versus, a location becomes map_zoom, "
            "a bare statement becomes text_beat."),
        prompt=(
            f"The scene library:\n{catalogue}\n\n"
            f"Claims (the only facts allowed on screen):\n"
            f"{json.dumps(claims, indent=2)}\n\n"
            f"The script, one entry per line:\n{json.dumps(lines, indent=2)}\n\n"
            "Return one shot per line, in order."),
        schema=SHOTS_SCHEMA, label="storyboard")
