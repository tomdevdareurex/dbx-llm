"""Load editable prompt files.

By default prompts are read from a ``prompts/`` directory in the current
working directory. Override the location with the DBX_LLM_PROMPT_DIR env var.
"""

import os
from pathlib import Path


def _prompt_dir() -> Path:
    return Path(os.getenv("DBX_LLM_PROMPT_DIR", Path.cwd() / "prompts"))


def load_prompt(name: str = "default") -> str:
    """Return the contents of ``prompts/<name>.md``."""
    path = _prompt_dir() / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text(encoding="utf-8")


def list_prompts() -> list[str]:
    """Names (without extension) of all ``*.md`` files in the prompt directory."""
    directory = _prompt_dir()
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.md"))
