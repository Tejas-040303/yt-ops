"""
The Claude API calls that research and write a video.

Everything here produces *drafts*. The audit trail is the point: each
step writes what it found to disk, so the research call's raw output --
quotes, URLs, what it could not find -- is readable before a word of it
reaches a script.

Needs ANTHROPIC_API_KEY in the environment (or a .env next to this file).

    from brain import scout, pick_topic, research, extract, write_script, storyboard

Every prompt takes its lane from config.yaml (found_out, curiosity,
trending): what the lane is for, which gates its script must pass, and
the domains its research may reach. The lane changes the brief, never
the discipline -- every lane is domain-locked and quote-backed.

Why the search is domain-locked
-------------------------------
Every lane is myth-dense. Asked to research Galileo and the Tower of
Pisa, a model returns the myth, confidently, citing blogs that repeat
it -- and general knowledge is worse than history for this. Each lane
in config.yaml lists the domains it may cite, and that list is handed
to the server-side web_search tool as allowed_domains -- so a blog is
not "discouraged", it is unreachable.
Every claim must then carry a verbatim quote from one of those pages,
and a claim that cannot produce one does not survive extract().
"""

import inspect
import json
import os
import sys

MODEL = "claude-opus-5-5"

# Listed Opus 5.5 rates, for the cost line only. Not billing -- and a
# turn a fallback model answered was billed at that model's rates.
USD_IN, USD_OUT = 4.00 / 1e6, 20.00 / 1e6

# A request the safety classifiers decline is re-run server-side on the
# model Anthropic recommends for that refusal category, instead of
# stopping the run. Biology and toxicology are among the categories, and
# medicine's history is in range for this channel.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_CONTINUATIONS = 5     # pause_turn restarts before giving up
_spend = {"in": 0, "out": 0, "calls": 0}


PLACEHOLDER = "sk-ant-REPLACE-ME"   # the value .env.example ships with


def _env_key(path, name="ANTHROPIC_API_KEY"):
    """A key from a .env file (ANTHROPIC_API_KEY unless named), whatever
    wrote the file.

    Windows PowerShell's `echo ... > .env` writes UTF-16 and Notepad may
    add a UTF-8 BOM, so the bytes are decoded by their BOM rather than
    assumed to be UTF-8 -- which used to crash here with
    UnicodeDecodeError before the key was ever read."""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    for line in text.splitlines():
        key, eq, value = line.partition("=")
        if eq and key.strip().removeprefix("export ").strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def _client():
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "pip install anthropic  -- needed for the research and script "
            "steps. Everything downstream of the storyboard runs without it.")
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.path.join(here, ".env")
    if not (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        if os.path.exists(env):
            key = _env_key(env)
            if key:
                os.environ["ANTHROPIC_API_KEY"] = key
    if os.environ.get("ANTHROPIC_API_KEY") == PLACEHOLDER:
        raise SystemExit(f"{env} still has the placeholder from .env.example "
                         f"-- put your real key in it.")
    if not (os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        hint = ""
        if os.path.exists(env + ".txt"):
            hint = (" There is a .env.txt -- Notepad added .txt; rename it "
                    "to .env.")
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Copy .env.example to .env next to "
            "brain.py and put your key in it, or set it in the "
            "environment." + hint)
    return anthropic.Anthropic(timeout=900.0)


def _charge(usage):
    _spend["in"] += usage.input_tokens
    _spend["out"] += usage.output_tokens
    _spend["calls"] += 1


# --- which backend answers ----------------------------------------
#
# config.yaml llm.provider (or $YT_LLM_PROVIDER for one run):
#   claude_api   the Anthropic API, below -- needs API credits
#   claude_code  the `claude -p` CLI on your Claude plan (brain_claude_code.py)
#   gemini       Google's Gemini API (brain_gemini.py)
# Every step's prompt and schema is the same whichever answers.

PROVIDERS = ("claude_api", "claude_code", "gemini")


def _provider():
    """(provider, its settings) from config.yaml, read once."""
    if "provider" not in _spend:
        llm = {}
        try:
            import yaml
            cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "config.yaml")
            llm = (yaml.safe_load(open(cfg, encoding="utf-8")) or {}).get(
                "llm") or {}
        except (OSError, ImportError):
            pass
        name = os.environ.get("YT_LLM_PROVIDER") or llm.get("provider") \
            or "claude_api"
        if name not in PROVIDERS:
            raise SystemExit(f"llm.provider {name!r} -- choose one of "
                             f"{', '.join(PROVIDERS)}")
        _spend["provider"], _spend["settings"] = name, llm.get(name) or {}
    return _spend["provider"], _spend["settings"]


def provider():
    """The backend this run uses: claude_api, claude_code or gemini."""
    return _provider()[0]


def _ask_elsewhere(provider, settings, **call):
    if provider == "claude_code":
        import brain_claude_code as backend
    else:
        import brain_gemini as backend
    result, meter = backend.ask(**call, settings=settings)
    _spend["in"] += meter["in"]
    _spend["out"] += meter["out"]
    _spend["calls"] += 1
    if meter.get("usd") is not None:
        _spend["usd"] = _spend.get("usd", 0.0) + meter["usd"]
    return result


def spend_line():
    provider = _spend.get("provider", "claude_api")
    tokens = (f"{_spend['calls']} calls, {_spend['in']:,} in / "
              f"{_spend['out']:,} out tokens")
    if provider == "claude_code":
        usd = _spend.get("usd")
        return (f"{tokens} via Claude Code -- counted against your Claude "
                f"plan, not API credits"
                + (f" (Claude Code's list-price estimate: ${usd:.2f})"
                   if usd is not None else ""))
    if provider == "gemini":
        return (f"{tokens} via Gemini -- $0 within the free tier's limits")
    d = _spend["in"] * USD_IN + _spend["out"] * USD_OUT
    return (f"{tokens} via the Anthropic API, about ${d:.2f} at listed "
            f"{MODEL} rates")


def _text(blocks):
    return "\n".join(b.text for b in blocks if b.type == "text")


def _supports_fallbacks(client):
    """Older anthropic SDKs have no `fallbacks` parameter. Run without it
    there rather than fail on an unexpected keyword."""
    try:
        return "fallbacks" in inspect.signature(
            client.beta.messages.create).parameters
    except (AttributeError, TypeError, ValueError):
        return False


def _extend(turn, new):
    """The assistant turn so far, plus what a resumed request returned.

    A resumed pause_turn returns the blocks that came after the pause, so
    they are appended: dropping the earlier ones loses that part of the
    research, and on Opus 5.5 changes the history its thinking blocks
    are bound to. If a response ever repeats the turn from the start
    instead, it replaces it, so nothing is doubled either way."""
    new = list(new)
    if turn and new and new[0].model_dump() == turn[0].model_dump():
        return new
    return turn + new


def _echoable(turn):
    """The turn as it may be sent back to resume. After a server-side
    fallback, the declined model's thinking and tool calls from before the
    switch are left out, as the fallback docs require; text, completed
    server-tool pairs and everything after the switch go back as-is."""
    switch = max((i for i, b in enumerate(turn) if b.type == "fallback"),
                 default=-1)
    if switch < 0:
        return turn
    answered = {getattr(b, "tool_use_id", None) for b in turn}
    return [b for i, b in enumerate(turn)
            if i > switch
            or b.type not in ("thinking", "redacted_thinking", "tool_use",
                              "server_tool_use")
            or (b.type == "server_tool_use" and b.id in answered)]


def _ask(system, prompt, schema=None, tools=None, effort="medium",
         max_tokens=16000, label=""):
    """One turn, with the server-tool pause_turn loop handled.

    A long server-tool turn stops with stop_reason 'pause_turn' after the
    server's own sampling limit. Resuming means re-sending the assistant
    turn so far with no extra user message -- the API sees the trailing
    server_tool_use block and picks up where it left off.

    Effort defaults to medium: on Opus 5.5 it is the documented starting
    point, which out-thinks Opus 5 at high and thinks more per level, so
    carrying "high" over would cost more than before for little gain.

    With llm.provider set to claude_code or gemini, the same call goes to
    that backend instead and nothing below runs.
    """
    provider, settings = _provider()
    if provider != "claude_api":
        return _ask_elsewhere(provider, settings, system=system,
                              prompt=prompt, schema=schema, tools=tools,
                              effort=effort, max_tokens=max_tokens,
                              label=label)

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
    if _supports_fallbacks(client):
        kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
    elif not _spend.get("warned"):
        _spend["warned"] = True
        print("  NOTE: this anthropic SDK has no server-side fallback; a "
              "refusal will stop the run. pip install -r requirements.txt",
              file=sys.stderr)
    create = client.beta.messages.create

    prompt_turn = {"role": "user", "content": prompt}
    try:
        response = create(messages=[prompt_turn], **kwargs)
        _charge(response.usage)
        turn = list(response.content)
        for _ in range(MAX_CONTINUATIONS):
            if response.stop_reason != "pause_turn":
                break
            response = create(messages=[prompt_turn, {
                "role": "assistant", "content": _echoable(turn)}], **kwargs)
            _charge(response.usage)
            turn = _extend(turn, response.content)
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

    # The documented served-by signal: a fallback_message iteration. (The
    # fallback content block is absent on turns routed straight to the
    # fallback model.)
    if any(getattr(it, "type", "") == "fallback_message"
           for it in (getattr(response.usage, "iterations", None) or [])):
        print(f"  NOTE: {label}: {MODEL} declined it; {response.model} "
              f"answered (server-side fallback)", file=sys.stderr)
    if response.stop_reason == "refusal":
        why = getattr(response.stop_details, "explanation", "") or ""
        raise SystemExit(f"{label}: the model declined. {why}")
    if response.stop_reason == "max_tokens":
        print(f"  NOTE: {label} hit max_tokens -- output may be cut short",
              file=sys.stderr)

    body = _text(turn)
    if schema:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise SystemExit(f"{label}: expected JSON, got:\n{body[:800]}")
    return body


# --- the steps ---------------------------------------------------

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


def _never(banned):
    return ", ".join(b.replace("_", " ") for b in banned)


def scout(lane, domains, banned, today):
    """What is being talked about right now, for the trending lane.

    Prose, not JSON: web search answers carry citations, and structured
    output refuses citations. pick_topic turns this into a choice."""
    tool = {"type": "web_search_20260209", "name": "web_search",
            "max_uses": 6, "allowed_domains": list(domains)}
    return _ask(
        system=(
            "You scout subjects for a short-form explainer channel. You "
            "may only use what the search tool can reach.\n\n"
            f"The lane: {lane['about']}\n\n"
            f"Never: {_never(banned)}."),
        prompt=(
            f"Today is {today}. Find up to six things in the news in the "
            "last two weeks that have a checkable, explainable story "
            "behind them. For each: what happened, the date, the URL you "
            "read it at, and the one question behind it that a 45-second "
            "explainer could answer and that will still be true next "
            "month. Leave out anything still unfolding."),
        tools=[tool], effort="medium", label="scout")


def pick_topic(avoid, rule, lane_name, lane, banned, today, leads=""):
    """One subject for this lane that the channel has not covered."""
    return _ask(
        system=(
            "You choose subjects for a short-form channel.\n\n"
            f"The channel rule, which is absolute: {rule}\n\n"
            f"This video is in the {lane_name} lane. {lane['about']}\n\n"
            f"In range: {' '.join(lane['range'].split())}.\n\n"
            f"Never: {_never(banned)}. A subject that brushes one of "
            "these is the wrong subject -- choose another."),
        prompt=(
            f"Today is {today}. Propose one subject.\n\n"
            "Already covered, do not repeat or closely overlap:\n"
            + ("\n".join(f"- {a}" for a in avoid) or "- nothing yet")
            + (f"\n\nLeads, for direction only. Never copy a title or a "
               f"framing from them:\n{leads}" if leads else "")
            + "\n\nslug: lowercase-hyphenated, 2-4 words.\n"
              "person: the named human the story turns on, or an empty "
              "string if this lane does not need one and the story has "
              "none.\n"
              "why: one sentence on why it is worth 45 seconds.\n"
              "gap: what most people believe, versus what the record says. "
              "If there is no such gap, say so plainly rather than "
              "inventing one."),
        schema=TOPIC_SCHEMA, effort="medium", label="pick_topic")


def research(topic, person, domains, today, lane):
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
            f"Today is {today}.\nSubject: {topic}\n"
            f"Person: {person or 'none named yet'}\n"
            f"The video it is for: {' '.join(lane['about'].split())}\n\n"
            "Search, read, and report:\n\n"
            "1. SOURCES -- for each page you actually used: the URL, its "
            "title, its publisher, its publication date if it shows one, "
            "and whether it is primary, scholarly, encyclopedia, museum "
            "or news.\n\n"
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
                                      "museum", "news", "popular",
                                      "unknown"]},
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
        "person": {"type": "string"},
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
    "required": ["angle", "person", "hook", "lines", "titles",
                 "description_hook"],
    "additionalProperties": False,
}


def write_script(topic, claims, myths, limits, lane_name, lane, media,
                 banned):
    lo, hi = limits
    g = lane["gates"]
    rules = [f"- {lo}-{hi} words total."]
    if g.get("must_name_person"):
        rules.append("- Name a person, and return that name in `person`, "
                     "spelled exactly as the script spells it.")
    else:
        rules.append("- If the script names a person, return that name in "
                     "`person`, spelled exactly as the script spells it; "
                     "otherwise return an empty string.")
    if g.get("must_name_place_or_year"):
        rules.append("- Name a place or a year.")
    if g.get("must_name_date"):
        rules.append("- Say when: a year, or a month and year.")
    if g.get("must_carry_specific"):
        rules.append("- Carry at least one checkable specific: a number, a "
                     "year, or a named place or thing. A script made only "
                     "of generalities is rejected.")
    cap = media.get("max_quote_words")
    return _ask(
        system=(
            "You write 45-second scripts for a channel that shows how we "
            "know things, not just what is true.\n\n"
            f"This one is in the {lane_name} lane. "
            f"{' '.join(lane['about'].split())}\n\n"
            "Hard rules:\n" + "\n".join(rules) + "\n"
            "- Every factual statement must come from the claims you are "
            "given. You may not add a number, a date or a name that is not "
            "in them. If a line needs a fact you do not have, cut the line.\n"
            "- The video stands alone. No 'as we saw last time', no part 2.\n"
            "- Do not open with 'Did you know', 'Hey guys', 'In this video' "
            "or 'Let's dive in'.\n"
            "- One line may be a verbatim source quotation, marked "
            "voice='quote'"
            + (f", of at most {cap} words" if cap else "")
            + ". Its text must match a quote in the claims exactly.\n"
            f"- Never: {'; '.join(media.get('never', []))}. Brands: "
            f"{media.get('brand_names', 'identify only')}.\n"
            f"- Do not stray into: {_never(banned)}.\n\n"
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


def storyboard(lines, claims, catalogue, max_quote_words=None):
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
            "not in the claims is the one unrecoverable error here.\n"
            + (f"- A quote_card holds at most {max_quote_words} words.\n"
               if max_quote_words else "") + "\n"
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



