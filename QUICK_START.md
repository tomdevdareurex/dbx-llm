# dbx-llm — quick start

A condensed cheat-sheet for running dbx-llm. For the full guide, see
[README.md](README.md).

## Contents

- [First run (in this repo)](#first-run-in-this-repo)
- [Install](#install)
- [Options to run](#options-to-run)
  - [The flags](#the-flags-what-the-parser-understands)
  - [How the parser decides](#how-the-parser-decides-what-to-do)
  - [The three modes](#the-three-modes-you-actually-run)
  - [What "write / edit" means](#what-write--edit-actually-means-and-how-to-use-it)
  - [Combinations cheat-sheet](#combinations-cheat-sheet)
  - [How `AGENTS.md` memory works](#how-the-agentsmd-memory-works)
  - [GUI option (Streamlit)](#gui-option-streamlit)

## First run (in this repo)

```powershell
# 1. Create & activate a virtual env, then install (add ".[ui]" for the GUI)
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e .

# 2. Confirm Databricks auth works
databricks current-user me

# 3. See available models
.\.venv\Scripts\python.exe -m dbx_llm --list-models

# 4. Start chatting
.\.venv\Scripts\python.exe -m dbx_llm --model databricks-claude-opus-4-6
```

Inspect an endpoint's details (e.g. context window) from Python:

```python
from dbx_llm.client import _workspace

ep = _workspace().serving_endpoints.get("databricks-claude-opus-4-6")
print(ep)
```

# Install

## In this repo (development)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e .          # core
python -m pip install -e ".[ui]"    # + Streamlit GUI
```

## Into another repo / another machine

```powershell
# A) from this local folder, editable + GUI extra (edits here picked up live)
python -m pip install -e "C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\dbx-llm[ui]"

# B) from git — latest pushed master
python -m pip install "git+https://github.com/tomdevdareurex/dbx-llm.git"

# B) from git — with the Streamlit GUI extra
python -m pip install "dbx-llm[ui] @ git+https://github.com/tomdevdareurex/dbx-llm.git"

# B) from git — pin to a branch / tag / commit
python -m pip install "git+https://github.com/tomdevdareurex/dbx-llm.git@master"
```

Notes:
- A git install fetches only what's **pushed** — run `git push` first. If the
  GitHub repo is private, add a token (`git+https://<TOKEN>@github.com/...`) or
  use SSH (`git+ssh://git@github.com/...`).
- The `default`, `coder`, and `repo_expert` prompts are **bundled in the
  package**, so chat and the repo agent work in any repo with no setup. A local
  `prompts/` folder (or `DBX_LLM_PROMPT_DIR`) still wins when present, so you can
  override per project.
- Always run as `python -m dbx_llm ...` (the `dbx-llm.exe` launcher is blocked by
  corporate group policy).

# Options to run

## The flags (what the parser understands)

| Flag | Takes a value? | What it does |
|------|----------------|--------------|
| `--model NAME` | yes | Which Databricks serving endpoint to talk to. If omitted, it uses the first one in your list (which may be a dead endpoint), so always pass `--model databricks-claude-opus-4-6`. |
| `--prompt NAME` | yes | Which bundled/local system prompt to load in plain chat. Default is `default`. Only affects plain chat. |
| `--list-models` | no | Print available endpoints and exit. |
| `--list-prompts` | no | Print available prompt files and exit. |
| `--repo [PATH]` | optional | Run as a codebase-expert agent over PATH (defaults to current dir). Without `--write` it is **read-only**. |
| `--write` | no | Only meaningful with `--repo`. Lets the agent change files — but every change is shown as a diff and applied only after you type `y`. |
| `--allow-self-edit` | no | Only meaningful with `--write`. Lets the agent edit dbx-llm's *own* source. Off by default so it can't rewrite its own guardrails. |
| `--scan` | no | One-shot: survey the repo and reconcile `AGENTS.md` (verify, fix, drop stale, add new), then exit. Pair with `--repo PATH` to target another repo. |

## How the parser decides what to do

It checks in this order and stops at the first match:

1. `--gui` → launch the Streamlit GUI, exit.
2. `--list-models` → print models, exit.
3. `--list-prompts` → print prompts, exit.
4. `--scan` → run the one-shot survey, exit.
5. `--repo` present → start the interactive repo agent.
6. none of the above → start a plain chat session.

So `--scan` wins over `--repo`, and `--repo` wins over plain chat.
`--write` and `--allow-self-edit` are *modifiers* — they do nothing on their own.

## The three modes you actually run

> After each reply the CLI prints a stats line — latency, completion tokens,
> tok/s, context-window usage, and (in repo/scan modes) tool-call count.

### 1. Plain chat (no repo)
```powershell
# just talk to the model
python -m dbx_llm --model databricks-claude-opus-4-6

# pick a different system prompt (e.g. the bundled `coder`)
python -m dbx_llm --model databricks-claude-opus-4-6 --prompt coder
```

### 2. Repo agent (read the codebase, answer questions)
```powershell
# read-only: it can list/read/search files but NOT change them
python -m dbx_llm --repo --model databricks-claude-opus-4-6

# point it at a different repo
python -m dbx_llm --repo C:\path\to\other-repo --model databricks-claude-opus-4-6
```

### 3. Scan (build / refresh AGENTS.md memory, then exit)
```powershell
python -m dbx_llm --scan --model databricks-claude-opus-4-6
python -m dbx_llm --scan --repo C:\path\to\other-repo --model databricks-claude-opus-4-6
```

## What "write / edit" actually means (and how to use it)

By default the repo agent is **read-only**: it can look at your code and talk
about it, but it has no power to change a single file.

Adding `--write` gives it two extra tools — `write_file` (create/overwrite a
whole file) and `edit_file` (change a snippet inside a file). It does **not**
edit silently. The flow is always:

1. You ask it to do something ("rename this function", "add a docstring").
2. It proposes a change and prints a **diff** (red = removed, green = added).
3. It asks: `Apply this change? [y/N]`.
4. You type `y` to apply, or anything else (or Enter) to cancel.

```powershell
# read + write, with your confirmation on every change
python -m dbx_llm --repo --write --model databricks-claude-opus-4-6
```

Safety rails that stay on even with `--write`:
- changes are confined to the repo root (no `..` escapes),
- it refuses to touch secrets (`.env`) and the `.git/` folder,
- on the dbx-llm repo itself it refuses to edit its **own** source unless you
  also add `--allow-self-edit`.

```powershell
# only needed if you want it to help develop dbx-llm itself
python -m dbx_llm --repo --write --allow-self-edit --model databricks-claude-opus-4-6
```

Because your repo is in git, `git diff` / `git checkout .` is your undo button
if you approve something you didn't mean to.

## Combinations cheat-sheet

| Command | Valid? | Result |
|---------|--------|--------|
| `--model X` | ✅ | plain chat |
| `--repo` | ✅ | read-only agent |
| `--repo --write` | ✅ | agent that can edit (with confirmation) |
| `--repo --write --allow-self-edit` | ✅ | also allowed to edit dbx-llm's own code |
| `--scan` / `--scan --repo PATH` | ✅ | one-shot survey → reconcile AGENTS.md |
| `--write` alone (no `--repo`) | ⚠️ | parses fine but does nothing — plain chat ignores it |
| `--allow-self-edit` without `--write` | ⚠️ | parses fine but does nothing |
| `--scan --write` | ⚠️ | `--scan` wins; `--write` is ignored (scan rewrites AGENTS.md only) |

## How the AGENTS.md memory works

The repo agent keeps a *living memory* in an `AGENTS.md` file at the repo root.

- **Per repo.** It's always the `AGENTS.md` at the root you point at. In this
  repo it reads `./AGENTS.md`; with `--repo C:\other` it reads
  `C:\other\AGENTS.md`. The installed package is never the memory location.
- **Read once, at startup.** It's baked into the agent's system prompt when the
  session starts and stays in context for every message that session. It is NOT
  re-read on each prompt.
- **Mid-session notes** (via `save_note`) are appended to the file immediately;
  `--scan` instead **reconciles** the whole file (verify, fix, drop, add). Either
  way, to fold the changes into the system prompt you **restart** the session.
- **Plain chat ignores it.** Only `--repo` and `--scan` use `AGENTS.md`; plain
  chat uses the selected `<name>.md` prompt instead.
- **Commit it** (don't gitignore) so the knowledge travels with the repo.

## GUI option (Streamlit)

The terminal CLI above always works. There's also a Streamlit front-end that
mirrors **every** CLI mode in your browser, using the same library underneath.
It ships **inside the package**, so once `[ui]` is installed it launches from any
directory — no need to be in this checkout:

```powershell
# one-time: install the optional UI dependency
python -m pip install "dbx-llm[ui]"     # or, in this repo: -e ".[ui]"

# launch from anywhere (opens a browser tab)
python -m dbx_llm --gui
```

The agent modes' **repo path** box defaults to the current working directory, so
run `python -m dbx_llm --gui` from the repo you want to explore. Missing the
`[ui]` extra? The command prints an install hint instead of crashing.

Pick a **Mode** in the sidebar — it's the GUI version of the CLI flags:

- 💬 **Chat** = `python -m dbx_llm` — plain chat; pick a system prompt (each shows
  a short description).
- 📖 **Repo Q&A (read-only)** = `python -m dbx_llm --repo` — codebase expert that
  explores the repo before answering.
- ✏️ **Repo Write (edit with approval)** = `python -m dbx_llm --repo --write` —
  same agent, but it can edit. Each change appears as a **diff** with **Approve /
  Reject** buttons (the browser version of the terminal `y/N` prompt). A checkbox
  turns on `--allow-self-edit`.
- 🧠 **Scan / set memory** = `python -m dbx_llm --repo --scan` — surveys the repo
  and writes durable facts to `AGENTS.md`.

The repo modes have a **repo path** box; all modes share the model dropdown and a
clear-chat button.

