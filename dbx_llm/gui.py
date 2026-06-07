"""Streamlit browser GUI for Databricks-hosted models.

This module ships *inside* the installed package, so it works from any repo or
machine without referencing the source checkout. Launch it with:

    python -m dbx_llm --gui

(That runs ``streamlit run`` on this file's installed path.) The repo root for
the agent modes defaults to the current working directory and can be changed in
the sidebar.

It mirrors the terminal CLI's modes ("parsers") in the browser:

- **Chat** — plain chat with a selectable system prompt (default / coder / ...).
- **Repo Q&A** — read-only codebase-expert agent over a repo.
- **Repo Write** — the same agent, allowed to edit files; every change is shown
  as a diff and applied only after you click Approve.
- **Scan / memory** — one-shot survey that records durable facts to AGENTS.md.

It uses the same ``dbx_llm`` library underneath, so the CLI keeps working
unchanged.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from dbx_llm import chat, list_models, list_prompts, load_prompt
from dbx_llm.repo_tools import (
    MEMORY_FILENAME,
    SCAN_TASK,
    build_repo_system_prompt,
    build_repo_tools,
    read_memory,
)
from dbx_llm.tools import run_with_tools

st.set_page_config(page_title="dbx-llm", page_icon="💬")

# Mode labels (mirror the CLI "parsers").
CHAT = "💬 Chat"
QA = "📖 Repo Q&A (read-only)"
WRITE = "✏️ Repo Write (edit with approval)"
SCAN = "🧠 Scan / set memory"

PREFERRED_MODEL = "databricks-claude-opus-4-6"

# Short, human descriptions for the bundled system prompts. Unknown prompts fall
# back to the first line of their file.
PROMPT_DESCRIPTIONS = {
    "default": "General-purpose, concise, honest assistant.",
    "coder": "Expert software engineer — idiomatic code with brief explanations.",
    "repo_expert": "Codebase expert that explores this repo with tools before answering.",
}


class _NeedApproval(Exception):
    """Raised by the preview confirm callback to surface a proposed edit's diff
    without writing anything to disk."""

    def __init__(self, action: str, rel_path: str, diff: str) -> None:
        super().__init__(rel_path)
        self.action = action
        self.rel_path = rel_path
        self.diff = diff


def _raise_confirm(action: str, rel_path: str, diff: str) -> bool:
    raise _NeedApproval(action, rel_path, diff)


# --- Pretty diff rendering -------------------------------------------------
_HUNK_RE = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

_DIFF_CSS = """
<style>
  body { margin: 0; }
  .diff {
    border: 1px solid #30363d; border-radius: 6px; overflow: hidden;
    background: #0d1117; color: #c9d1d9;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12.5px; line-height: 1.5;
  }
  .diff-head {
    display: flex; justify-content: space-between; align-items: center;
    background: #161b22; border-bottom: 1px solid #30363d;
    padding: 6px 12px; font-weight: 600;
  }
  .diff-head .add { color: #3fb950; }
  .diff-head .del { color: #f85149; }
  .diff table { border-collapse: collapse; width: 100%; }
  .diff td { padding: 0 10px; vertical-align: top; white-space: pre-wrap; word-break: break-word; }
  .diff td.ln {
    width: 1%; text-align: right; color: #6e7681; white-space: nowrap;
    user-select: none; border-right: 1px solid #21262d;
  }
  .diff td.sign { width: 1%; padding: 0 4px; color: #6e7681; user-select: none; }
  .diff tr.add { background: rgba(46,160,67,0.15); }
  .diff tr.add td.code { color: #aff5b4; }
  .diff tr.del { background: rgba(248,81,73,0.15); }
  .diff tr.del td.code { color: #ffdcd7; }
  .diff tr.hunk td { background: #161b22; color: #79c0ff; }
</style>
"""


def _diff_to_rows(diff: str) -> tuple[str, int, int]:
    """Turn a unified diff into styled <tr> rows + (added, removed) counts."""
    rows: list[str] = []
    old_ln = new_ln = 0
    adds = dels = 0
    for raw in diff.splitlines():
        if raw.startswith(("--- ", "+++ ")):
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if m:
                old_ln, new_ln = int(m.group(1)), int(m.group(2))
            rows.append(
                '<tr class="hunk"><td class="ln"></td><td class="ln"></td>'
                f'<td class="sign"></td><td class="code">{html.escape(raw)}</td></tr>'
            )
            continue
        sign, text = raw[:1], html.escape(raw[1:])
        if sign == "+":
            adds += 1
            rows.append(
                f'<tr class="add"><td class="ln"></td><td class="ln">{new_ln}</td>'
                f'<td class="sign">+</td><td class="code">{text}</td></tr>'
            )
            new_ln += 1
        elif sign == "-":
            dels += 1
            rows.append(
                f'<tr class="del"><td class="ln">{old_ln}</td><td class="ln"></td>'
                f'<td class="sign">-</td><td class="code">{text}</td></tr>'
            )
            old_ln += 1
        elif sign == "\\":  # "\ No newline at end of file"
            rows.append(
                '<tr><td class="ln"></td><td class="ln"></td>'
                f'<td class="sign"></td><td class="code">{html.escape(raw)}</td></tr>'
            )
        else:  # context line (leading space)
            rows.append(
                f'<tr><td class="ln">{old_ln}</td><td class="ln">{new_ln}</td>'
                f'<td class="sign"></td><td class="code">{text}</td></tr>'
            )
            old_ln += 1
            new_ln += 1
    return "\n".join(rows), adds, dels


def _render_diff(diff: str, rel_path: str) -> None:
    """Render a unified diff as a GitHub-style colored panel (no extra deps)."""
    if not diff.strip():
        st.caption("_(no textual changes)_")
        return
    body, adds, dels = _diff_to_rows(diff)
    n_rows = body.count("<tr")
    height = min(46 + n_rows * 21, 540)
    doc = (
        f"{_DIFF_CSS}"
        f'<div class="diff"><div class="diff-head">'
        f"<span>{html.escape(rel_path)}</span>"
        f'<span><span class="add">+{adds}</span>&nbsp;&nbsp;'
        f'<span class="del">\u2212{dels}</span></span></div>'
        f"<table>{body}</table></div>"
    )
    components.html(doc, height=height, scrolling=True)


@st.cache_data(show_spinner=False)
def _models() -> list[str]:
    return list_models()


# Family groups shown first, in this order; each group sorted alphabetically.
# Everything else follows, also alphabetically.
_MODEL_PRIORITY = ("claude", "gpt", "gemini", "llama")


def _model_sort_key(name: str) -> tuple[int, int, str]:
    lower = name.lower()
    # Models that don't start with "databricks" always sort to the end.
    not_databricks = 0 if lower.startswith("databricks") else 1
    for rank, family in enumerate(_MODEL_PRIORITY):
        if family in lower:  # "llama" matches "meta-llama-..."
            return (not_databricks, rank, lower)
    return (not_databricks, len(_MODEL_PRIORITY), lower)


def _sort_models(models: list[str]) -> list[str]:
    return sorted(models, key=_model_sort_key)


@st.cache_data(show_spinner=False)
def _prompts() -> list[str]:
    return list_prompts()


def _describe_prompt(name: str) -> str:
    if name in PROMPT_DESCRIPTIONS:
        return PROMPT_DESCRIPTIONS[name]
    try:
        first = load_prompt(name).strip().splitlines()
        return first[0] if first else ""
    except Exception:
        return ""


def _chat_system(prompt_name: str) -> dict:
    try:
        content = load_prompt(prompt_name)
    except FileNotFoundError:
        content = "You are a helpful assistant."
    return {"role": "system", "content": content}


# --- Sidebar ---------------------------------------------------------------
st.sidebar.title("dbx-llm")

models = _sort_models(_models())
if not models:
    st.error("No serving endpoints found. Run `databricks auth login` first.")
    st.stop()

mode = st.sidebar.radio("Mode", [CHAT, QA, WRITE, SCAN])

default_model_index = models.index(PREFERRED_MODEL) if PREFERRED_MODEL in models else 0
model = st.sidebar.selectbox("Model", models, index=default_model_index)


# ===========================================================================
# Mode: plain chat
# ===========================================================================
def render_chat() -> None:
    prompts = _prompts() or ["default"]
    default_index = prompts.index("default") if "default" in prompts else 0
    prompt_name = st.sidebar.selectbox("System prompt", prompts, index=default_index)
    st.sidebar.caption(_describe_prompt(prompt_name))

    if st.sidebar.button("Clear chat", use_container_width=True):
        st.session_state.pop("chat_view", None)
        st.rerun()

    # Reset when the prompt changes so the new system prompt applies.
    if st.session_state.get("chat_prompt") != prompt_name:
        st.session_state["chat_view"] = []
        st.session_state["chat_prompt"] = prompt_name
    st.session_state.setdefault("chat_view", [])

    st.title(CHAT)
    st.caption(f"Prompt: **{prompt_name}** — {_describe_prompt(prompt_name)}")

    for msg in st.session_state["chat_view"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Message"):
        st.session_state["chat_view"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        api_messages = [_chat_system(prompt_name)] + st.session_state["chat_view"]
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    reply = chat(model, api_messages)
                except Exception as exc:
                    reply = f"⚠️ Error talking to `{model}`: {exc}"
            st.markdown(reply)
        st.session_state["chat_view"].append({"role": "assistant", "content": reply})


# ===========================================================================
# Mode: repo Q&A (read-only)
# ===========================================================================
def render_qa() -> None:
    root = Path(st.sidebar.text_input("Repo path", value=".")).resolve()
    st.sidebar.caption(f"📁 {root}")
    st.sidebar.caption(_describe_prompt("repo_expert"))
    if st.sidebar.button("Clear chat", use_container_width=True):
        for key in ("qa_view", "qa_msgs", "qa_sig"):
            st.session_state.pop(key, None)
        st.rerun()

    functions, schemas = build_repo_tools(root)  # read-only + save_note

    sig = str(root)
    if st.session_state.get("qa_sig") != sig:
        st.session_state["qa_sig"] = sig
        st.session_state["qa_msgs"] = [
            {"role": "system", "content": build_repo_system_prompt(root, writable=False)}
        ]
        st.session_state["qa_view"] = []

    st.title(QA)
    st.caption(f"Read-only codebase expert over **{root}**")

    for msg in st.session_state["qa_view"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Ask about this repo"):
        st.session_state["qa_view"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state["qa_msgs"].append({"role": "user", "content": user_input})
        with st.chat_message("assistant"):
            with st.spinner("Exploring the repo…"):
                try:
                    reply = run_with_tools(
                        model, st.session_state["qa_msgs"], functions, schemas
                    )
                except Exception as exc:
                    reply = f"⚠️ Error: {exc}"
            st.markdown(reply)
        st.session_state["qa_view"].append({"role": "assistant", "content": reply})


# ===========================================================================
# Mode: repo Write (edit with per-edit approval)
# ===========================================================================
def render_write() -> None:
    root = Path(st.sidebar.text_input("Repo path", value=".")).resolve()
    allow_self_edit = st.sidebar.checkbox(
        "Allow editing dbx-llm's own source", value=False,
        help="Off by default so the agent can't rewrite its own guardrails.",
    )
    st.sidebar.caption(f"📁 {root}")
    if st.sidebar.button("Clear chat", use_container_width=True):
        for key in ("w_view", "w_msgs", "w_queue", "w_pending", "w_sig", "w_go", "w_decision"):
            st.session_state.pop(key, None)
        st.rerun()

    protect_self = not allow_self_edit
    fns_apply, schemas = build_repo_tools(
        root, allow_write=True, confirm=lambda *_: True, protect_self=protect_self
    )
    fns_preview, _ = build_repo_tools(
        root, allow_write=True, confirm=_raise_confirm, protect_self=protect_self
    )

    sig = f"{root}|{allow_self_edit}"
    if st.session_state.get("w_sig") != sig:
        st.session_state["w_sig"] = sig
        st.session_state["w_msgs"] = [
            {"role": "system", "content": build_repo_system_prompt(root, writable=True, allow_self_edit=allow_self_edit)}
        ]
        st.session_state["w_view"] = []
        st.session_state["w_queue"] = []
        st.session_state["w_pending"] = None
        st.session_state.pop("w_go", None)
        st.session_state.pop("w_decision", None)

    def _append_tool(call_id: str, content: str) -> None:
        st.session_state["w_msgs"].append(
            {"role": "tool", "tool_call_id": call_id, "content": json.dumps(content, default=str)}
        )

    def _run_until_pause() -> None:
        """Drive the tool loop until it finishes or needs an edit approval."""
        msgs = st.session_state["w_msgs"]
        queue = st.session_state["w_queue"]
        while True:
            # Need a new model turn?
            if not queue and st.session_state["w_pending"] is None:
                message = chat(model, msgs, tools=schemas)
                if not getattr(message, "tool_calls", None):
                    text = message.content or ""
                    msgs.append({"role": "assistant", "content": text})
                    st.session_state["w_view"].append({"role": "assistant", "content": text})
                    return
                msgs.append(message.model_dump(exclude_none=True))
                queue[:] = [
                    {"id": c.id, "name": c.function.name,
                     "args": json.loads(c.function.arguments or "{}")}
                    for c in message.tool_calls
                ]
            # Work through the queued tool calls.
            while queue:
                call = queue[0]
                name, args = call["name"], call["args"]
                if name in ("write_file", "edit_file"):
                    try:
                        result = fns_preview[name](**args)
                    except _NeedApproval as na:
                        st.session_state["w_pending"] = {
                            "id": call["id"], "name": name, "args": args,
                            "action": na.action, "rel": na.rel_path, "diff": na.diff,
                        }
                        return  # suspend for the Approve/Reject buttons
                    # No approval needed (refusal / no-match / ambiguous string).
                    _append_tool(call["id"], result)
                    queue.pop(0)
                else:
                    result = fns_apply[name](**args)
                    _append_tool(call["id"], result)
                    queue.pop(0)
            # Queue drained → loop back for the next model turn.

    st.title(WRITE)
    mode_note = "self-edit ON" if allow_self_edit else "own source protected"
    st.caption(f"Editing **{root}** with approval — {mode_note}")

    # Render history.
    for msg in st.session_state["w_view"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Resume after an approval decision.
    pending = st.session_state.get("w_pending")
    if pending is not None and "w_decision" in st.session_state:
        approved = st.session_state.pop("w_decision")
        if approved:
            result = fns_apply[pending["name"]](**pending["args"])
            _append_tool(pending["id"], result)
            st.session_state["w_view"].append(
                {"role": "assistant", "content": f"✅ Applied **{pending['action']}** to `{pending['rel']}`."}
            )
        else:
            _append_tool(pending["id"], "User rejected the edit; no change made.")
            st.session_state["w_view"].append(
                {"role": "assistant", "content": f"❌ Rejected **{pending['action']}** to `{pending['rel']}`."}
            )
        st.session_state["w_queue"].pop(0)
        st.session_state["w_pending"] = None
        with st.spinner("Continuing…"):
            _run_until_pause()
        st.rerun()

    # Show the pending diff + approval buttons.
    pending = st.session_state.get("w_pending")
    if pending is not None:
        with st.chat_message("assistant"):
            st.markdown(f"Proposed **{pending['action']}** to `{pending['rel']}`:")
            _render_diff(pending["diff"], pending["rel"])
            col_yes, col_no = st.columns(2)
            if col_yes.button("✅ Approve", use_container_width=True):
                st.session_state["w_decision"] = True
                st.rerun()
            if col_no.button("❌ Reject", use_container_width=True):
                st.session_state["w_decision"] = False
                st.rerun()
        return  # block further input until the edit is decided

    # Kick off a queued run (after submitting a message).
    if st.session_state.pop("w_go", False):
        with st.spinner("Working…"):
            try:
                _run_until_pause()
            except Exception as exc:
                st.session_state["w_view"].append(
                    {"role": "assistant", "content": f"⚠️ Error: {exc}"}
                )
        st.rerun()

    if user_input := st.chat_input("Ask the agent to explain or change the repo"):
        st.session_state["w_view"].append({"role": "user", "content": user_input})
        st.session_state["w_msgs"].append({"role": "user", "content": user_input})
        st.session_state["w_go"] = True
        st.rerun()


# ===========================================================================
# Mode: scan / set memory
# ===========================================================================
def render_scan() -> None:
    root = Path(st.sidebar.text_input("Repo path", value=".")).resolve()
    st.sidebar.caption(f"📁 {root}")

    st.title(SCAN)
    st.caption(
        f"One-shot survey of **{root}** → durable facts appended to "
        f"`{MEMORY_FILENAME}`. Read-only apart from that file."
    )

    if st.button("Run scan", type="primary"):
        functions, schemas = build_repo_tools(root)  # read-only + save_note
        messages = [
            {"role": "system", "content": build_repo_system_prompt(root, writable=False)},
            {"role": "user", "content": SCAN_TASK},
        ]
        with st.spinner("Scanning the repo… this can take a minute."):
            try:
                summary = run_with_tools(model, messages, functions, schemas, max_turns=40)
            except Exception as exc:
                summary = f"⚠️ Error: {exc}"
        st.session_state["scan_summary"] = summary

    if st.session_state.get("scan_summary"):
        st.subheader("Summary")
        st.markdown(st.session_state["scan_summary"])

    memory = read_memory(root)
    if memory:
        st.subheader(f"Current {MEMORY_FILENAME}")
        st.markdown(memory)


# --- Dispatch --------------------------------------------------------------
if mode == CHAT:
    render_chat()
elif mode == QA:
    render_qa()
elif mode == WRITE:
    render_write()
elif mode == SCAN:
    render_scan()
