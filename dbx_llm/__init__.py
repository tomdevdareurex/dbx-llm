"""dbx-llm: a portable client + CLI to chat with Databricks-hosted models."""

from dbx_llm.client import chat, get_client, list_models
from dbx_llm.prompts import list_prompts, load_prompt
from dbx_llm.repo_tools import (
    DEFAULT_REPO_PROMPT,
    MEMORY_FILENAME,
    SCAN_TASK,
    build_repo_map,
    build_repo_system_prompt,
    build_repo_tools,
    read_memory,
)
from dbx_llm.tools import run_with_tools

__all__ = [
    "chat",
    "get_client",
    "list_models",
    "list_prompts",
    "load_prompt",
    "build_repo_tools",
    "build_repo_map",
    "build_repo_system_prompt",
    "read_memory",
    "run_with_tools",
    "DEFAULT_REPO_PROMPT",
    "MEMORY_FILENAME",
    "SCAN_TASK",
]
__version__ = "0.1.0"
