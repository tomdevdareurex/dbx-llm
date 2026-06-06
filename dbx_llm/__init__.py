"""dbx-llm: a portable client + CLI to chat with Databricks-hosted models."""

from dbx_llm.client import chat, get_client, list_models
from dbx_llm.prompts import list_prompts, load_prompt

__all__ = ["chat", "get_client", "list_models", "list_prompts", "load_prompt"]
__version__ = "0.1.0"
