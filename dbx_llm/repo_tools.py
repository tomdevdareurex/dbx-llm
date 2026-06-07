"""Read-only repository tools for the ``--repo`` codebase-expert agent.

These functions let a model explore the repository it is run inside: list files,
read a file, and search the code. Everything is sandboxed to a single root
directory and refuses to touch secrets (``.env``) or version-control internals.

``build_repo_tools(root)`` returns ``(functions, schemas)`` ready to hand to
``dbx_llm.tools.run_with_tools``. A ``save_note`` tool is included so the agent
can append durable knowledge to ``AGENTS.md`` (the living-memory file).
"""

from __future__ import annotations

import difflib
import fnmatch
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Directories never worth walking into.
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
}

# Filenames/patterns that must never be read (secrets).
_SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "id_rsa", "*.pfx")

# The living-memory file the agent reads at startup and may append to.
MEMORY_FILENAME = "AGENTS.md"


# Cap how much data a single tool call returns, to protect the context window.
_MAX_FILE_BYTES = 100_000
_MAX_SEARCH_HITS = 100
_MAX_LIST_ENTRIES = 2_000


def _is_secret(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pat) for pat in _SECRET_PATTERNS)


# Directories that must never be written to.
_PROTECTED_WRITE_DIRS = {".git"}

# dbx-llm's own source directory. Writes here are refused unless the caller
# explicitly opts in (protect_self=False), so the agent can't rewrite its own
# guardrails when run on the dbx-llm repository itself.
_PACKAGE_DIR = Path(__file__).resolve().parent


def _terminal_confirm(action: str, rel_path: str, diff: str) -> bool:
    """Show a diff and ask the user to approve a write. True if approved."""
    print(f"\n--- proposed {action}: {rel_path} ---")
    print(diff if diff.strip() else "(no textual changes)")
    try:
        answer = input("Apply this change? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _resolve_within(root: Path, rel: str) -> Path:
    """Resolve ``rel`` against ``root``, refusing any escape outside the root."""
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path '{rel}' is outside the repository root.")
    return candidate


def _iter_files(root: Path):
    """Yield all non-skipped files under ``root`` (depth-first)."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                yield entry


def build_repo_tools(
    root: str | Path,
    *,
    allow_write: bool = False,
    confirm: Callable[[str, str, str], bool] | None = None,
    protect_self: bool = True,
) -> tuple[dict[str, Callable], list[dict]]:
    """Build the sandboxed repo tools bound to ``root``.

    Args:
        root: Repository root; all access is confined here.
        allow_write: When True, also expose ``write_file`` and ``edit_file``.
        confirm: Callback ``(action, rel_path, diff) -> bool`` asked before every
            write. Defaults to a terminal y/N prompt that shows the diff.
        protect_self: When True (default), refuse writes that land inside
            dbx-llm's own source directory, even if it sits under ``root``.

    Returns:
        A ``(functions, schemas)`` pair for ``run_with_tools``.
    """
    root_path = Path(root).resolve()
    approve = confirm or _terminal_confirm

    def list_files(glob: str | None = None) -> str:
        """List repository files, optionally filtered by a glob pattern."""
        matches = []
        for file in _iter_files(root_path):
            rel = file.relative_to(root_path).as_posix()
            if glob is None or fnmatch.fnmatch(rel, glob):
                matches.append(rel)
            if len(matches) >= _MAX_LIST_ENTRIES:
                matches.append("... (truncated)")
                break
        if not matches:
            return "No files matched."
        return "\n".join(sorted(matches))

    def read_file(path: str) -> str:
        """Return the contents of a repository file."""
        target = _resolve_within(root_path, path)
        if _is_secret(target):
            return f"Refused: '{path}' looks like a secret file and cannot be read."
        if not target.is_file():
            return f"Not found: '{path}'."
        data = target.read_bytes()
        if len(data) > _MAX_FILE_BYTES:
            data = data[:_MAX_FILE_BYTES]
            suffix = "\n... (truncated)"
        else:
            suffix = ""
        return data.decode("utf-8", errors="replace") + suffix

    def search_code(query: str) -> str:
        """Search file contents for a substring; returns path:line matches."""
        hits = []
        needle = query.lower()
        for file in _iter_files(root_path):
            if _is_secret(file):
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    rel = file.relative_to(root_path).as_posix()
                    hits.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                    if len(hits) >= _MAX_SEARCH_HITS:
                        hits.append("... (truncated)")
                        return "\n".join(hits)
        return "\n".join(hits) if hits else f"No matches for '{query}'."

    def save_note(note: str) -> str:
        """Append a durable note to the repository's AGENTS.md memory file."""
        memory = root_path / MEMORY_FILENAME
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"- ({stamp}) {note.strip()}\n"
        if not memory.exists():
            memory.write_text(
                "# AGENTS.md\n\nLiving memory for this repository.\n\n## Notes\n\n",
                encoding="utf-8",
            )
        with memory.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return f"Saved note to {MEMORY_FILENAME}."

    def _writable_target(path: str) -> Path:
        target = _resolve_within(root_path, path)
        if _is_secret(target):
            raise ValueError(f"Refused: '{path}' is a secret file.")
        if set(target.relative_to(root_path).parts) & _PROTECTED_WRITE_DIRS:
            raise ValueError(f"Refused: '{path}' is in a protected directory.")
        if protect_self and (target == _PACKAGE_DIR or _PACKAGE_DIR in target.parents):
            raise ValueError(
                f"Refused: '{path}' is part of dbx-llm's own source. "
                "Run with --allow-self-edit to override."
            )
        return target

    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file (after user confirmation)."""
        try:
            target = _writable_target(path)
        except ValueError as exc:
            return str(exc)
        old = target.read_text(encoding="utf-8") if target.is_file() else ""
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        if not approve("write", path, diff):
            return "Cancelled by user; no change made."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {path}."

    def edit_file(path: str, old: str, new: str) -> str:
        """Replace one unique occurrence of ``old`` with ``new`` (after confirmation)."""
        try:
            target = _writable_target(path)
        except ValueError as exc:
            return str(exc)
        if not target.is_file():
            return f"Not found: '{path}'."
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            return f"No match for the given text in '{path}'."
        if count > 1:
            return f"Ambiguous: text appears {count} times in '{path}'. Add more context."
        updated = text.replace(old, new, 1)
        diff = "".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        if not approve("edit", path, diff):
            return "Cancelled by user; no change made."
        target.write_text(updated, encoding="utf-8")
        return f"Edited {path}."

    functions: dict[str, Callable] = {
        "list_files": list_files,
        "read_file": read_file,
        "search_code": search_code,
        "save_note": save_note,
    }
    if allow_write:
        functions["write_file"] = write_file
        functions["edit_file"] = edit_file

    schemas = [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in the repository, optionally filtered "
                "by a glob pattern (e.g. '**/*.py' or 'src/*').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "glob": {
                            "type": "string",
                            "description": "Optional glob to filter file paths.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a single repository file by "
                "its path relative to the repo root.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path relative to the repository root.",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "Case-insensitive substring search across repository "
                "files. Returns matching 'path:line: text' entries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for.",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_note",
                "description": "Append a durable fact or convention about this "
                "repository to AGENTS.md so it is remembered next session. Use for "
                "lasting insights, not transient details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "note": {
                            "type": "string",
                            "description": "A concise, factual note to remember.",
                        }
                    },
                    "required": ["note"],
                },
            },
        },
    ]
    if allow_write:
        schemas += [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or overwrite a file with new content. "
                    "The change is shown to the user as a diff and applied only "
                    "after they approve it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path relative to the repository root.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Full new file content.",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Replace one unique snippet of text in a file. "
                    "Provide enough context so 'old' matches exactly once. The "
                    "change is shown as a diff and applied only after user approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path relative to the repository root.",
                            },
                            "old": {
                                "type": "string",
                                "description": "Exact text to replace (must be unique).",
                            },
                            "new": {
                                "type": "string",
                                "description": "Replacement text.",
                            },
                        },
                        "required": ["path", "old", "new"],
                    },
                },
            },
        ]

    return functions, schemas


def read_memory(root: str | Path) -> str:
    """Return the AGENTS.md contents for ``root``, or '' if absent."""
    memory = Path(root).resolve() / MEMORY_FILENAME
    if memory.exists():
        return memory.read_text(encoding="utf-8")
    return ""


def build_repo_map(root: str | Path) -> str:
    """A flat, sorted list of repository files for startup orientation."""
    root_path = Path(root).resolve()
    files = sorted(
        f.relative_to(root_path).as_posix() for f in _iter_files(root_path)
    )
    if len(files) > _MAX_LIST_ENTRIES:
        files = files[:_MAX_LIST_ENTRIES] + ["... (truncated)"]
    return "\n".join(files)


# The one-shot task used by --scan / the GUI's "Scan / set memory" mode.
SCAN_TASK = (
    "Survey this entire repository and build its living memory.\n"
    "1. Use list_files to see the layout.\n"
    "2. read_file the important source files (entry points, core modules, config).\n"
    "3. For each durable, non-obvious fact you find — architecture, conventions, "
    "how components fit together, gotchas, build/run commands — call save_note "
    "with a concise one-line note.\n"
    "Skip transient details and anything already in AGENTS.md above. "
    "When you have covered the codebase, give a short summary of what you recorded."
)


def build_repo_system_prompt(
    root: str | Path,
    *,
    writable: bool = False,
    allow_self_edit: bool = False,
) -> str:
    """Assemble the repo agent's system prompt.

    Combines the ``repo_expert`` prompt, the repository root, a file map, the
    remembered AGENTS.md notes, and a mode-specific note describing whether
    editing is enabled. Shared by the CLI (``--repo`` / ``--scan``) and the
    Streamlit GUI so all front-ends stay in sync.
    """
    from dbx_llm.prompts import load_prompt

    root_path = Path(root).resolve()
    system = load_prompt("repo_expert")
    system += f"\n\n# Repository root\n{root_path}\n\n# Files\n{build_repo_map(root_path)}"
    memory = read_memory(root_path)
    if memory:
        system += f"\n\n# AGENTS.md (remembered notes)\n{memory}"
    if writable:
        system += (
            "\n\n# Editing enabled\nYou have write_file and edit_file. Every change "
            "is shown to the user as a diff and applied only after they confirm. "
            "Read a file before editing it and make minimal, targeted edits."
        )
        if allow_self_edit:
            system += (
                "\n\n# Self-editing enabled\nYou may also edit dbx-llm's own source. "
                "Be especially careful: changes here alter your own behavior."
            )
    else:
        system += (
            "\n\n# Read-only\nYou have no editing tools. Do not claim to modify files."
        )
    return system
