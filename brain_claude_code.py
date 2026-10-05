"""
brain.py's model calls, run through the Claude Code CLI (`claude -p`)
instead of the Anthropic API.

    config.yaml:  llm: {provider: claude_code}

Why: `claude -p` signs in the way Claude Code does, so with a Claude
plan (Pro, Max...) the calls count against that plan's usage instead of
API credits. Same prompts, same schemas -- brain.py builds them, this
only carries them.

How a call runs
---------------
- The task goes in on stdin and the system prompt in a temp file, never
  on the command line: an npm-installed `claude` on Windows is a .cmd,
  and cmd.exe breaks arguments that contain newlines. The one JSON
  argument, the schema, has no newlines and its shell characters
  escaped.
- ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are removed from the
  child's environment. With either set, Claude Code bills that key
  instead of the plan -- which is the empty balance this backend exists
  to avoid.
- It runs in an empty temp directory with --permission-mode dontAsk:
  web search and fetch are allowed when the step searches, Bash and file
  edits never are, so a research call cannot touch the repo.
- Search cannot be locked to the lane's sites the way the API's
  allowed_domains locks it; the prompt asks for it, and auto.py drops
  any claim whose source is off the list afterwards.

Each call also carries Claude Code's own system prompt (about 15k
tokens in a test), which counts toward the plan's usage.
"""

import json
import os
import shutil
import subprocess
import tempfile

SEARCH_TOOLS = "WebSearch,WebFetch"
NEVER = "Bash,Edit,Write,NotebookEdit"

# Characters cmd.exe acts on even inside an argument, when `claude` is
# npm's claude.cmd. In JSON they can only occur inside strings, where a
# \u escape means the same thing, so the schema argument carries none.
CMD_SAFE = {ord(c): f"\\u{ord(c):04x}" for c in '&|<>^%!'}


def search_rules(tools):
    """The prompt text that stands in for allowed_domains, or ""."""
    search = next((t for t in tools or [] if t.get("name") == "web_search"),
                  None)
    if not search:
        return "", False
    domains = search.get("allowed_domains") or []
    return ("\n\nSearch rules for this task: search and fetch only these "
            f"sites -- {', '.join(domains)} -- and pass them as the "
            "search tool's allowed_domains. A source on any other site is "
            "discarded by the pipeline, so it is wasted. Use at most "
            f"{search.get('max_uses', 10)} searches."), True


def ask(system, prompt, schema=None, tools=None, effort="medium",
        max_tokens=None, label="", settings=None):
    """Same contract as brain._ask: the text, or the parsed JSON when a
    schema is given. Returns (result, meter); exits on failure."""
    settings = settings or {}
    exe = shutil.which(settings.get("command") or "claude")
    if not exe:
        raise SystemExit(
            "claude_code: the `claude` command is not on PATH. Install "
            "Claude Code and run `claude` once to sign in, or change "
            "llm.provider in config.yaml.")

    rules, searching = search_rules(tools)
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}

    with tempfile.TemporaryDirectory() as cwd:
        system_file = os.path.join(cwd, "system.txt")
        with open(system_file, "w", encoding="utf-8") as f:
            f.write(system)
        cmd = [exe, "-p", "Do the task given on standard input.",
               "--output-format", "json",
               "--append-system-prompt-file", system_file,
               "--permission-mode", "dontAsk",
               "--disallowedTools", NEVER if searching
               else f"{NEVER},{SEARCH_TOOLS}"]
        if searching:
            cmd += ["--allowedTools", SEARCH_TOOLS]
        if effort:
            cmd += ["--effort", effort]
        if settings.get("model"):
            cmd += ["--model", settings["model"]]
        if schema:
            cmd += ["--json-schema", json.dumps(schema).translate(CMD_SAFE)]
        try:
            p = subprocess.run(cmd, input=prompt + rules, capture_output=True,
                               text=True, encoding="utf-8", env=env, cwd=cwd,
                               timeout=settings.get("timeout", 1800))
        except subprocess.TimeoutExpired:
            raise SystemExit(f"{label}: claude -p did not finish in "
                             f"{settings.get('timeout', 1800)}s")

    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"{label}: claude -p returned no JSON (exit "
                         f"{p.returncode}): "
                         f"{(p.stderr or p.stdout).strip()[:600]}")
    if p.returncode != 0 or out.get("is_error"):
        raise SystemExit(f"{label}: Claude Code failed: "
                         f"{str(out.get('result') or p.stderr).strip()[:600]}")

    u = out.get("usage") or {}
    meter = {"in": (u.get("input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)),
             "out": u.get("output_tokens", 0),
             "usd": out.get("total_cost_usd")}
    denied = out.get("permission_denials") or []
    if denied:
        print(f"  NOTE: {label}: Claude Code was refused {len(denied)} "
              f"tool call(s) outside what this step allows")
    if schema:
        if out.get("structured_output") is None:
            raise SystemExit(f"{label}: Claude Code returned no structured "
                             f"output: {str(out.get('result'))[:600]}")
        return out["structured_output"], meter
    return out.get("result") or "", meter
