"""Core client: authenticate to Databricks and talk to serving endpoints.

Databricks model serving endpoints are OpenAI-compatible, so we obtain a
standard OpenAI client that is pre-wired with the workspace URL and auth.

Auth resolves automatically through the Databricks SDK in this order:
    1. environment variables (DATABRICKS_HOST / DATABRICKS_TOKEN)
    2. a profile in ~/.databrickscfg (DATABRICKS_CONFIG_PROFILE)
    3. OAuth (after running `databricks auth login`)
"""

from functools import lru_cache

from databricks.sdk import WorkspaceClient
from openai import OpenAI


@lru_cache(maxsize=1)
def _workspace() -> WorkspaceClient:
    """Cached Databricks workspace client (auth resolved by the SDK)."""
    return WorkspaceClient()


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """An OpenAI-compatible client pointed at this workspace's serving endpoints."""
    return _workspace().serving_endpoints.get_open_ai_client()


def list_models() -> list[str]:
    """Names of all serving endpoints available to select as a model."""
    return [endpoint.name for endpoint in _workspace().serving_endpoints.list()]


# Best-effort context-window sizes (in tokens) by model family. These are not
# reported by the serving API, so we keep a small lookup keyed by a substring
# that appears in the endpoint name. Values are approximate — edit freely as
# models change. Unknown models fall back to ``None`` (no limit shown).
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "claude": 1_000_000,
    "gpt": 128_000,
    "gemini": 1_000_000,
    "llama": 128_000,
}


def context_limit(model: str) -> int | None:
    """Best-effort context-window size for a model, or ``None`` if unknown.

    Matches on a family substring in the endpoint name (e.g. "meta-llama-3-3"
    matches "llama"), mirroring how the GUI groups models by family.
    """
    lower = model.lower()
    for family, limit in MODEL_CONTEXT_LIMITS.items():
        if family in lower:
            return limit
    return None


def new_stats() -> dict:
    """A fresh per-conversation stats accumulator shared by the CLI and GUI.

    Callers fold each turn's token usage and latency into this dict and pass it
    to :func:`format_stats` (CLI) or render it in the sidebar (GUI), so both
    surfaces report identical numbers. ``run_with_tools`` also accepts one and
    accumulates turns, tokens, and per-tool call counts into it.
    """
    return {
        "turns": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "last_prompt_tokens": 0,
        "last_completion_tokens": 0,
        "last_latency": 0.0,
        "total_latency": 0.0,
        "tool_calls": {},
    }


def format_stats(stats: dict, model: str | None = None) -> str:
    """One-line human summary of a :func:`new_stats` dict.

    Returns an empty string when nothing has happened yet (no turns), so callers
    can ``if line:`` before printing. Parts are joined by ``·``: last-turn
    latency, completion tokens, throughput, context-window fill, and total tool
    calls. ``model`` is used to look up the context-window limit.
    """
    if not stats or not stats.get("turns"):
        return ""
    parts: list[str] = []
    lat = stats.get("last_latency", 0.0)
    out = stats.get("last_completion_tokens", 0)
    if lat > 0:
        parts.append(f"{lat:.1f}s")
    if out:
        parts.append(f"{out:,} tok")
        if lat > 0:
            parts.append(f"{out / lat:.0f} tok/s")
    used = stats.get("last_prompt_tokens", 0)
    limit = context_limit(model) if model else None
    if used:
        if limit:
            parts.append(f"{used:,}/{limit:,} ctx ({used / limit:.0%})")
        else:
            parts.append(f"{used:,} ctx")
    calls = stats.get("tool_calls") or {}
    if calls:
        parts.append(f"{sum(calls.values())} tool call(s)")
    return "  \u00b7  ".join(parts)


def chat(
    model: str,
    messages: list[dict],
    *,
    tools: list | None = None,
    usage: dict | None = None,
    **kwargs,
):
    """Send a chat completion request to a Databricks-hosted model.

    Args:
        model: The serving endpoint name (e.g. "databricks-claude-opus-4-6").
        messages: OpenAI-style chat messages.
        tools: Optional OpenAI tool/function schemas. When omitted (the common
            case) this returns the assistant reply as a plain string.
        usage: Optional dict to populate with token counts from the response
            (``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``). The
            return value is unaffected; pass ``{}`` and read it after the call.
        **kwargs: Forwarded to ``chat.completions.create`` (temperature, etc.).

    Returns:
        The assistant message string for plain chat, or the full OpenAI message
        object (so the caller can inspect ``tool_calls``) when ``tools`` is set.
    """
    if tools is not None:
        kwargs["tools"] = tools
    response = get_client().chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    if usage is not None and getattr(response, "usage", None) is not None:
        usage["prompt_tokens"] = getattr(response.usage, "prompt_tokens", 0) or 0
        usage["completion_tokens"] = getattr(response.usage, "completion_tokens", 0) or 0
        usage["total_tokens"] = getattr(response.usage, "total_tokens", 0) or 0
    message = response.choices[0].message
    if tools:
        return message
    return message.content
