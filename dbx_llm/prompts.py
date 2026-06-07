"""Load editable prompt files.

Prompts are read from a ``prompts/`` directory in the current working directory
(override with the DBX_LLM_PROMPT_DIR env var). If a prompt isn't found there,
we fall back to the prompts bundled inside the installed package, so plain chat
works out of the box from any repo or machine without copying files around.
"""

import os
from pathlib import Path

# Prompts shipped inside the package as a portable fallback.
_BUNDLED_DIR = Path(__file__).resolve().parent / "_bundled_prompts"


def _prompt_dir() -> Path:
    return Path(os.getenv("DBX_LLM_PROMPT_DIR", Path.cwd() / "prompts"))


def _search_dirs() -> list[Path]:
    """Where to look for prompts, in priority order (local first, bundled last)."""
    return [_prompt_dir(), _BUNDLED_DIR]


def load_prompt(name: str = "default") -> str:
    """Return the contents of ``<name>.md`` from the local or bundled prompts."""
    searched = []
    for directory in _search_dirs():
        path = directory / f"{name}.md"
        searched.append(str(path))
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"Prompt '{name}' not found. Looked in: {', '.join(searched)}"
    )


def list_prompts() -> list[str]:
    """Names (without extension) of all ``*.md`` prompts, local and bundled."""
    names: set[str] = set()
    for directory in _search_dirs():
        if directory.exists():
            names.update(p.stem for p in directory.glob("*.md"))
    return sorted(names)
