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


def chat(
    model: str,
    messages: list[dict],
    *,
    tools: list | None = None,
    **kwargs,
):
    """Send a chat completion request to a Databricks-hosted model.

    Args:
        model: The serving endpoint name (e.g. "databricks-claude-opus-4-6").
        messages: OpenAI-style chat messages.
        tools: Optional OpenAI tool/function schemas. When omitted (the common
            case) this returns the assistant reply as a plain string.
        **kwargs: Forwarded to ``chat.completions.create`` (temperature, etc.).

    Returns:
        The assistant message string for plain chat, or the full OpenAI message
        object (so the caller can inspect ``tool_calls``) when ``tools`` is set.
    """
    response = get_client().chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        **kwargs,
    )
    message = response.choices[0].message
    if tools:
        return message
    return message.content
