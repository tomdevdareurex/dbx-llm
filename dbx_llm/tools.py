"""Optional helper for OpenAI-style tool/function calling.

This module is NOT required for plain chat. Import it only when you want the
model to call your own Python functions. The core (`dbx_llm.client`) has no
dependency on this file, keeping simple chat free of tool machinery.
"""

import json
from typing import Callable


def run_with_tools(
    model: str,
    messages: list[dict],
    functions: dict[str, Callable],
    tool_schemas: list[dict],
    *,
    max_turns: int = 12,
    stats: dict | None = None,
) -> str:
    """Run a tool-calling loop using local Python functions.

    Args:
        model: Serving endpoint name.
        messages: OpenAI-style chat messages (mutated in place as the loop runs).
        functions: Map of tool name -> callable(**kwargs).
        tool_schemas: OpenAI tool definitions describing those functions.
        max_turns: Safety cap on tool-calling iterations.
        stats: Optional dict accumulated across the loop with usage metrics:
            ``turns`` (model calls), ``prompt_tokens`` / ``completion_tokens`` /
            ``total_tokens`` (summed), ``last_prompt_tokens`` (current context
            fill), and ``tool_calls`` (a name -> count map).

    Returns:
        The model's final text answer, or a notice if the turn cap is reached.
    """
    from dbx_llm.client import chat

    if stats is not None:
        stats.setdefault("turns", 0)
        stats.setdefault("prompt_tokens", 0)
        stats.setdefault("completion_tokens", 0)
        stats.setdefault("total_tokens", 0)
        stats.setdefault("last_prompt_tokens", 0)
        stats.setdefault("tool_calls", {})

    for _ in range(max_turns):
        usage: dict = {}
        message = chat(model, messages, tools=tool_schemas, usage=usage)

        if stats is not None and usage:
            stats["turns"] += 1
            stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
            stats["completion_tokens"] += usage.get("completion_tokens", 0)
            stats["total_tokens"] += usage.get("total_tokens", 0)
            stats["last_prompt_tokens"] = usage.get("prompt_tokens", 0)

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content

        messages.append(message.model_dump(exclude_none=True))
        for call in tool_calls:
            name = call.function.name
            if stats is not None:
                stats["tool_calls"][name] = stats["tool_calls"].get(name, 0) + 1
            try:
                func = functions[name]
            except KeyError:
                result = f"Error: unknown tool '{name}'."
            else:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    result = func(**arguments)
                except Exception as exc:  # keep the loop alive on tool failure
                    result = f"Tool '{name}' failed: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return "Stopped: reached max tool-calling turns."
