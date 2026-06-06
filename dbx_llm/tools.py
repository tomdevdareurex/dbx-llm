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
    max_turns: int = 5,
) -> str:
    """Run a tool-calling loop using local Python functions.

    Args:
        model: Serving endpoint name.
        messages: OpenAI-style chat messages (mutated in place as the loop runs).
        functions: Map of tool name -> callable(**kwargs).
        tool_schemas: OpenAI tool definitions describing those functions.
        max_turns: Safety cap on tool-calling iterations.

    Returns:
        The model's final text answer, or a notice if the turn cap is reached.
    """
    from dbx_llm.client import chat

    for _ in range(max_turns):
        message = chat(model, messages, tools=tool_schemas)

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content

        messages.append(message.model_dump(exclude_none=True))
        for call in tool_calls:
            func = functions[call.function.name]
            arguments = json.loads(call.function.arguments or "{}")
            result = func(**arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return "Stopped: reached max tool-calling turns."
