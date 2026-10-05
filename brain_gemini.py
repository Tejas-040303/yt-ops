"""
brain.py's model calls, run on Google's Gemini API instead of Claude.

    config.yaml:  llm: {provider: gemini, gemini: {model: gemini-2.5-flash}}
    .env:         GEMINI_API_KEY=...      (a free key from Google AI Studio)

Same prompts and schemas as the Claude path -- brain.py builds them,
this only carries them. What differs, and what it costs you:

- Search is Google Search grounding, which takes no allow-list (the SDK
  offers exclude_domains only). The prompt names the lane's sites, every
  search result is listed under the notes with its real domain, and
  auto.py drops any claim whose source is off the lane's list. The lock
  still holds, one step later than on the Claude API.
- Grounding returns redirect links. They are resolved to the page they
  point at, so the notes and claims carry real URLs the domain check can
  read; a link that will not resolve keeps its redirect and is dropped.
- A weaker model than Opus for careful research. The fact check in the
  metadata file is the backstop either way.
- On the free tier, check Google's terms for how prompts may be used.

Schemas go over as JSON Schema (response_json_schema) without
"additionalProperties", which the Claude path needs and Gemini's subset
may not accept; the shape is otherwise the same.
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-2.5-flash"


def _key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    import brain
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env):
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            value = brain._env_key(env, name)
            if value:
                return value
    raise SystemExit("gemini: no GEMINI_API_KEY. Get a free key from Google "
                     "AI Studio and add GEMINI_API_KEY=... to .env next to "
                     "brain.py.")


def _plain_schema(schema):
    """The schema without additionalProperties, recursively."""
    if isinstance(schema, dict):
        return {k: _plain_schema(v) for k, v in schema.items()
                if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_plain_schema(v) for v in schema]
    return schema


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _resolve(uri, timeout=10):
    """Where a grounding redirect link points, without loading the page."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(uri, method="HEAD"),
                    timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            return e.headers["Location"]
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return uri


def _search_appendix(response):
    """Every search result the answer was grounded in, with its real
    domain and resolved URL -- and a map from redirect link to URL."""
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
    except (AttributeError, IndexError, TypeError):
        chunks = None
    lines, resolved = [], {}
    for c in chunks or []:
        web = getattr(c, "web", None)
        if not web or not web.uri:
            continue
        url = resolved.setdefault(web.uri, _resolve(web.uri))
        lines.append(f"- {web.title or ''} ({web.domain or '?'}): {url}")
    if not lines:
        return "", resolved
    return ("\n\nSEARCH RESULTS THE ANSWER WAS GROUNDED IN (listed by the "
            "search tool, not written by the model):\n"
            + "\n".join(dict.fromkeys(lines))), resolved


def ask(system, prompt, schema=None, tools=None, effort="medium",
        max_tokens=None, label="", settings=None):
    """Same contract as brain._ask: the text, or the parsed JSON when a
    schema is given. Returns (result, meter); exits on failure."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError:
        raise SystemExit("pip install google-genai  -- needed for "
                         "llm.provider: gemini")
    from brain_claude_code import search_rules

    settings = settings or {}
    model = settings.get("model") or DEFAULT_MODEL
    rules, searching = search_rules(tools)
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=([types.Tool(google_search=types.GoogleSearch())]
               if searching else None),
        response_mime_type="application/json" if schema else None,
        response_json_schema=_plain_schema(schema) if schema else None)

    try:
        response = genai.Client(api_key=_key()).models.generate_content(
            model=model, contents=prompt + rules, config=config)
    except errors.APIError as e:
        if e.code == 429:
            raise SystemExit(f"{label}: Gemini rate limit reached -- the "
                             f"free tier caps requests per minute and per "
                             f"day. Wait, then rerun. ({e.message})")
        if e.code in (401, 403):
            raise SystemExit(f"{label}: Gemini rejected the key. "
                             f"({e.message})")
        raise SystemExit(f"{label}: Gemini API error {e.code}: {e.message}")

    blocked = getattr(response.prompt_feedback, "block_reason", None)
    blocked = getattr(blocked, "name", blocked)
    cand = response.candidates[0] if response.candidates else None
    finish = getattr(cand, "finish_reason", None)
    finish = getattr(finish, "name", finish)
    if blocked or not cand or finish in ("SAFETY", "PROHIBITED_CONTENT",
                                         "BLOCKLIST", "SPII", "RECITATION"):
        raise SystemExit(f"{label}: Gemini declined "
                         f"({blocked or finish or 'no candidates'}).")
    if finish == "MAX_TOKENS":
        print(f"  NOTE: {label} hit the output limit -- output may be cut "
              f"short", file=sys.stderr)

    u = response.usage_metadata
    meter = {"in": getattr(u, "prompt_token_count", 0) or 0,
             "out": ((getattr(u, "candidates_token_count", 0) or 0)
                     + (getattr(u, "thoughts_token_count", 0) or 0)),
             "usd": None}
    body = response.text or ""
    if schema:
        try:
            return json.loads(body), meter
        except json.JSONDecodeError:
            raise SystemExit(f"{label}: expected JSON, got:\n{body[:800]}")
    appendix, resolved = _search_appendix(response) if searching else ("", {})
    for redirect, url in resolved.items():
        body = body.replace(redirect, url)
    return body + appendix, meter
