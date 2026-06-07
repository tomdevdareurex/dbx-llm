"""Interactive CLI: a portable chat over Databricks-hosted models."""

import argparse
import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from dbx_llm.client import chat, format_stats, list_models, new_stats
from dbx_llm.prompts import list_prompts, load_prompt


def _print_stats(stats: dict, model: str) -> None:
    """Print the shared one-line stats summary (latency, tokens, context, tools)."""
    line = format_stats(stats, model)
    if line:
        print(f"  {line}\n")

def _expand_attachments(text: str) -> str:
    """Inline the contents of any ``@<path>`` tokens found in the message.

    The chat client only sends text, so to let the model "read" a file the user
    references it with ``@path`` (e.g. ``@quick_checks.md``) and its contents are
    appended to the message before sending.
    """
    attachments = []
    for token in text.split():
        if token.startswith("@") and len(token) > 1:
            path = Path(token[1:])
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"  [could not read {path}: {exc}]")
                continue
            attachments.append(f"\n\n--- contents of {path} ---\n{content}")
    return text + "".join(attachments)


def _plain_chat_repl(model: str, system: str, prompt_name: str) -> None:
    """Plain chat: relay user messages to the model (no tools)."""
    history: list[dict] = [{"role": "system", "content": system}]
    stats = new_stats()
    print(f"Model:  {model}")
    print(f"Prompt: {prompt_name}")
    print("Type your message. Attach a file with @path. Ctrl-C to exit.\n")
    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        history.append({"role": "user", "content": _expand_attachments(user)})
        usage: dict = {}
        start = time.perf_counter()
        reply = chat(model, history, usage=usage)
        elapsed = time.perf_counter() - start
        history.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")
        if usage:
            stats["turns"] += 1
            stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
            stats["completion_tokens"] += usage.get("completion_tokens", 0)
            stats["total_tokens"] += usage.get("total_tokens", 0)
            stats["last_prompt_tokens"] = usage.get("prompt_tokens", 0)
            stats["last_completion_tokens"] = usage.get("completion_tokens", 0)
            stats["last_latency"] = elapsed
            stats["total_latency"] += elapsed
        _print_stats(stats, model)


def _repo_agent_repl(
    model: str,
    root: Path,
    allow_write: bool = False,
    allow_self_edit: bool = False,
) -> None:
    """Codebase-expert agent: explores the repository with sandboxed tools."""
    from dbx_llm.repo_tools import build_repo_system_prompt, build_repo_tools
    from dbx_llm.tools import run_with_tools

    functions, schemas = build_repo_tools(
        root, allow_write=allow_write, protect_self=not allow_self_edit
    )
    system = build_repo_system_prompt(
        root, writable=allow_write, allow_self_edit=allow_self_edit
    )

    history: list[dict] = [{"role": "system", "content": system}]
    stats = new_stats()
    mode = "read/write" if allow_write else "read-only"
    print(f"Model:  {model}")
    print(f"Repo:   {root}  (codebase-expert agent, {mode})")
    print("Ask about this repo. Attach a file with @path. Ctrl-C to exit.\n")
    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        history.append({"role": "user", "content": _expand_attachments(user)})
        start = time.perf_counter()
        reply = run_with_tools(model, history, functions, schemas, stats=stats)
        stats["last_latency"] = time.perf_counter() - start
        history.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")
        _print_stats(stats, model)


def _repo_scan(model: str, root: Path) -> None:
    """One-shot deep survey: read the repo and record durable facts to AGENTS.md."""
    from dbx_llm.repo_tools import (
        MEMORY_FILENAME,
        SCAN_TASK,
        build_repo_system_prompt,
        build_repo_tools,
    )
    from dbx_llm.tools import run_with_tools

    functions, schemas = build_repo_tools(root, allow_memory_rewrite=True)
    system = build_repo_system_prompt(root, writable=False)

    print(f"Model:  {model}")
    print(f"Repo:   {root}  (scanning into {MEMORY_FILENAME})\n")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": SCAN_TASK},
    ]
    stats = new_stats()
    start = time.perf_counter()
    summary = run_with_tools(model, messages, functions, schemas, max_turns=40, stats=stats)
    stats["last_latency"] = time.perf_counter() - start
    print(f"\n{summary}\n")
    _print_stats(stats, model)


def _port_in_use(port: int) -> bool:
    """True if something is already *listening* on ``127.0.0.1:port``.

    We probe by connecting rather than binding: on Windows a bind test is
    unreliable because uvicorn binds ``0.0.0.0`` with ``SO_REUSEADDR``, so a
    second process can bind the same port and a ``127.0.0.1`` bind probe won't
    notice the existing ``0.0.0.0`` listener. ``connect_ex`` returning 0 means a
    listener accepted the connection, i.e. the port is taken.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _free_port(preferred: int = 8501) -> int:
    """Return an available TCP port, preferring ``preferred``.

    Streamlit binds 8501 by default and does *not* auto-increment, so launching
    a second GUI while one is already running silently collides on the same port
    (both terminals print 8501 and you end up viewing whichever process owns the
    socket). To let multiple repos run side by side, we pick the first port with
    no active listener, starting at ``preferred``, and pass it explicitly to
    ``streamlit run``.
    """
    for port in range(preferred, preferred + 100):
        if not _port_in_use(port):
            return port
    return preferred  # fall back; let Streamlit handle it


def _launch_gui() -> None:
    """Launch the packaged Streamlit GUI from any working directory.

    The GUI ships inside the installed package (``dbx_llm/gui.py``), so this
    works from any repo or machine without pointing at this source checkout.
    """
    if importlib.util.find_spec("streamlit") is None:
        print(
            "The browser GUI needs Streamlit. Install the optional extra:\n"
            '    python -m pip install "dbx-llm[ui]"\n'
            "or, from this repo:  python -m pip install -e \".[ui]\""
        )
        return
    gui_path = Path(__file__).resolve().parent / "gui.py"
    port = _free_port()
    print(f"Launching dbx-llm GUI on http://localhost:{port}  (cwd: {Path.cwd()})")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(gui_path),
            "--server.port",
            str(port),
        ]
    )


def main() -> None:
    load_dotenv(override=True)

    parser = argparse.ArgumentParser(
        prog="dbx-llm",
        description="Chat with Databricks-hosted models from your terminal.",
    )
    parser.add_argument("--model", help="Serving endpoint name to use.")
    parser.add_argument("--prompt", default="default", help="Prompt file in prompts/.")
    parser.add_argument("--list-models", action="store_true", help="List models and exit.")
    parser.add_argument("--list-prompts", action="store_true", help="List prompts and exit.")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the Streamlit browser GUI (needs the [ui] extra).",
    )
    parser.add_argument(
        "--repo",
        nargs="?",
        const=".",
        metavar="PATH",
        help="Run as a read-only codebase-expert agent over the given repo "
        "(defaults to the current directory).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Allow the repo agent to edit files (each change needs your confirmation).",
    )
    parser.add_argument(
        "--allow-self-edit",
        action="store_true",
        help="With --write, also let the agent edit dbx-llm's own source "
        "(off by default to protect its guardrails).",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="One-shot: deeply survey the repo and write findings to AGENTS.md, "
        "then exit. Use with --repo to set the target (defaults to current dir).",
    )
    args = parser.parse_args()

    if args.gui:
        _launch_gui()
        return
    if args.list_models:
        print("\n".join(list_models()))
        return
    if args.list_prompts:
        print("\n".join(list_prompts()))
        return

    models = list_models()
    if not models:
        print("No serving endpoints found. Run 'databricks auth login' first.")
        return

    model = args.model or models[0]

    if args.scan:
        root = Path(args.repo).resolve() if args.repo is not None else Path.cwd()
        _repo_scan(model, root)
        return

    if args.repo is not None:
        _repo_agent_repl(
            model, Path(args.repo).resolve(), args.write, args.allow_self_edit
        )
        return

    _plain_chat_repl(model, load_prompt(args.prompt), args.prompt)


if __name__ == "__main__":
    main()
