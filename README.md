# dbx-llm

A small, **portable** Python library + CLI to chat with **Databricks-hosted models**.

Think of it as a
lightweight, model-selectable chat client you fully control.

---

## Contents

- [How it works](#how-it-works-the-whole-idea-in-one-line)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Install](#install) · [into another repo](#install-into-another-repo-or-another-machine)
- [CLI usage](#cli-usage-the-chat-client-workflow)
- [Repo agent (codebase expert)](#repo-agent-a-read-only-codebase-expert)
  - [How `AGENTS.md` memory is loaded](#how-the-agentsmd-memory-is-loaded)
  - [Seeding memory with a scan (`--scan`)](#seeding-its-memory-with-a-scan---scan)
  - [Letting it edit (opt-in)](#letting-it-edit-opt-in)
- [Browser GUI (Streamlit)](#browser-gui-streamlit)
- [Library usage](#library-usage-import-it-and-build-things)
- [Optional: tool / function calling](#optional-tool--function-calling)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Databricks connection](#databricks-connection)

---

## How it works (the whole idea in one line)

Databricks model serving endpoints are **OpenAI-compatible**. The Databricks SDK
hands you a ready-to-use OpenAI client that is already pointed at your workspace
and already authenticated:

```python
from databricks.sdk import WorkspaceClient
client = WorkspaceClient().serving_endpoints.get_open_ai_client()

from dbx_llm.client import _workspace
ep = _workspace().serving_endpoints.get("databricks-claude-opus-4-6")
print(ep)   # look at .config / .config.served_entities
```

Everything in this library is built on that single primitive. Your auth comes
from the Databricks CLI / `~/.databrickscfg` — **no tokens in code**.

---

## Project layout

```
dbx-llm/
├── pyproject.toml        # package metadata, the `dbx-llm` command, [ui] extra
├── README.md
├── QUICK_START.md        # condensed cheat-sheet for running it
├── .gitignore            # ignores .env, caches, build artifacts
├── .env.example          # template you copy to .env
├── .env                  # your local auth config (gitignored)
└── dbx_llm/
    ├── __init__.py       # public API: chat, list_models, load_prompt, ...
    ├── __main__.py       # enables `python -m dbx_llm`
    ├── client.py         # auth + OpenAI client + list_models + chat   (core)
    ├── prompts.py        # load_prompt / list_prompts (local + bundled fallback)
    ├── cli.py            # interactive REPL + `--gui` launcher
    ├── gui.py            # Streamlit GUI (ships in the package; `--gui` runs it)
    ├── tools.py          # OPTIONAL function/tool-calling loop (not used by core)
    ├── repo_tools.py     # sandboxed repo tools + shared repo system prompt
    └── _bundled_prompts/ # default/coder/repo_expert prompts shipped in the package
```

---

## Prerequisites

1. **Python 3.10+**
2. **Databricks CLI installed _and authenticated_.** Installing the CLI alone is
   not enough — you need a working profile. Create one once:
   ```bash
   databricks auth login
   ```
   This writes an OAuth `DEFAULT` profile to `~/.databrickscfg`. The `.env` in
   this repo already points at `DATABRICKS_CONFIG_PROFILE=DEFAULT`.
3. **Model-serving access** in your workspace (so you can call endpoints like
   `databricks-claude-opus-4-6`).

> If another Databricks project already runs on this machine, you're done — this
> library reuses the exact same auth and needs no extra setup.

---

## Install

From the repo root:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

python -m pip install -e .
```

Copy the env template (it's already filled with the default profile):

```bash
cp .env.example .env   # already present in this repo
```

### Install into another repo (or another machine)

`dbx-llm` is a normal installable package, so you can add it to a *different*
project's environment. Two ways:

**From this local folder** (best while developing — edits here are picked up live,
no push or auth needed):

```powershell
# editable link to this folder, with the Streamlit GUI extra
python -m pip install -e "C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\dbx-llm[ui]"
```

**From git** (best for another machine or a pinned version — requires the code to
be pushed first; this clones from GitHub rather than your disk):

```powershell
# latest pushed master
python -m pip install "git+https://github.com/tomdevdareurex/dbx-llm.git"

# with the Streamlit GUI extra
python -m pip install "dbx-llm[ui] @ git+https://github.com/tomdevdareurex/dbx-llm.git"

# pin to a branch / tag / commit
python -m pip install "git+https://github.com/tomdevdareurex/dbx-llm.git@master"

or 

python -m pip install --upgrade --force-reinstall --no-cache-dir "git+https://github.com/tomdevdareurex/dbx-llm@master"
```

> A git install fetches only what's **pushed**. Run `git push` first so your
> latest changes are included. If the GitHub repo is **private**, pip needs
> credentials — use a token (`git+https://<TOKEN>@github.com/...`) or SSH
> (`git+ssh://git@github.com/...`).
>
> The `default`, `coder`, and `repo_expert` prompts are **bundled inside the
> package**, so chat and the repo agent work anywhere with no extra setup. A
> local `prompts/` folder (or `DBX_LLM_PROMPT_DIR`) still takes priority when
> present, so you can add or override prompts per project.

---

## CLI usage (the "chat client" workflow)

```bash
# See which models you can pick (your workspace serving endpoints)
python -m dbx_llm --list-models

# See available prompt files
python -m dbx_llm --list-prompts

# Start chatting with a specific model + the default prompt
python -m dbx_llm --model databricks-claude-opus-4-6

# Use a different prompt (the bundled `coder`) and another model
python -m dbx_llm --prompt coder --model databricks-meta-llama-3-3-70b-instruct
```

> **Shortcut:** if the auto-generated `dbx-llm` launcher isn't blocked on your
> machine, you can drop the `python -m` prefix and just run `dbx-llm ...`. On
> locked-down / corporate machines the `.exe` is blocked by group policy, so use
> the `python -m dbx_llm ...` form shown above — it does exactly the same thing.

Inside the REPL, type a message and press Enter. Conversation history is kept
for the session. Press `Ctrl-C` to exit.

After each reply the CLI prints a short stats line — last-turn latency,
completion tokens, throughput (tok/s), context-window usage, and (in `--repo` /
`--scan` modes) the number of tool calls — the same numbers the GUI shows.

**Change behavior by editing prompts** — edit the bundled
`dbx_llm/_bundled_prompts/default.md` (changes are live with an editable `-e .`
install), or drop a `*.md` into a local `prompts/` folder (or set
`DBX_LLM_PROMPT_DIR`) to add or override prompts per project, then select them
with `--prompt <name>`.

---

## Repo agent (a read-only "codebase expert")

Run `dbx-llm` as an agent that can explore the repository it's launched in and
answer questions about it. It uses tool-calling to read files, list the tree,
and search the code — then answers from what it actually found.

```bash
# From inside any repository (defaults to the current directory):
python -m dbx_llm --repo

# Or point it at a specific path:
python -m dbx_llm --repo path/to/repo --model databricks-claude-opus-4-6
```

Then ask things like *"how does authentication work here?"* or *"where is the
CLI entry point?"* — the agent reads the relevant files before answering.

**Install it into another repo** so it's available there:

```bash
# from your other repo's environment
python -m pip install -e "path/to/dbx-llm"
python -m dbx_llm --repo
```

**What it can and can't do:**

- ✅ **Read-only by default.** It can `list_files`, `read_file`, and
  `search_code`. It **cannot** modify your files unless you pass `--write`.
- 🧠 **Living memory.** It reads an `AGENTS.md` file from the repo root at
  startup (if present) and can append durable notes to it via a `save_note`
  tool (and fully reconcile it during `--scan`), so it gets smarter about the
  repo over time.
- 🔒 **Sandboxed & safe.** All file access is confined to the repo root (no
  `..` escapes) and it refuses to read secrets such as `.env`.

### How the `AGENTS.md` memory is loaded

- **Per repo, at the root you point at.** Running inside this repo reads
  `./AGENTS.md`; running `--repo C:\other` reads `C:\other\AGENTS.md`. The
  installed dbx-llm package is never the memory location — the memory always
  lives in the codebase being explored.
- **Read once, at startup.** The file is loaded into the agent's *system
  prompt* when the session starts and stays in context for every message that
  session. It is **not** re-read on each prompt.
- **Notes saved mid-session** are appended to the file immediately, but the
  system-prompt snapshot isn't rebuilt — **restart** the session to fold new
  notes into the system prompt.
- **Plain chat does not read `AGENTS.md`.** Only `--repo` and `--scan` use it;
  plain chat uses the selected `<name>.md` system prompt instead.
- **Commit it (don't gitignore).** It's curated documentation that should
  travel with the repo so teammates and future sessions inherit the knowledge.
  Each target repo's own `.gitignore` governs its own `AGENTS.md`.

### Seeding & refreshing its memory with a scan (`--scan`)

To build or refresh the living memory, run a one-shot deep survey: the agent
walks the whole repo (`list_files` → `read_file`) and **reconciles** `AGENTS.md`
— it verifies the existing notes against the current code, fixes stale ones,
drops obsolete ones, adds new findings, and reorganizes everything into clear
sections — then exits.

```bash
python -m dbx_llm --scan --model databricks-claude-opus-4-6
python -m dbx_llm --scan --repo path/to/other-repo --model databricks-claude-opus-4-6
```

It's read-only apart from rewriting `AGENTS.md` (the repo is git-tracked, so
`git diff AGENTS.md` shows exactly what changed and `git checkout AGENTS.md`
undoes it), and it prints a summary of what it added, fixed, and removed. Re-run
it any time the codebase changes substantially.


### Letting it edit (opt-in)

Add `--write` to give the agent `write_file` and `edit_file` tools:

```bash
python -m dbx_llm --repo --write
```

Every change is **shown to you as a diff and applied only after you approve it**:

```
--- proposed edit: README.md ---
@@ ... @@
-old line
+new line
Apply this change? [y/N]
```

Type `y` to apply, anything else to cancel. Writes stay sandboxed to the repo
root and refuse secrets (`.env`) and the `.git/` directory. Since your repo is
version-controlled, `git diff` / `git checkout` are your safety net for undo.

**Self-protection.** When you run the agent on the dbx-llm repo itself, it
refuses to edit its own source by default, so it can't quietly rewrite its own
guardrails. If you actually want it to help develop dbx-llm, opt in:

```bash
python -m dbx_llm --repo --write --allow-self-edit
```

(Installed into any other repo, this has no effect — dbx-llm's source lives
outside that repo and is already out of reach.)

---

## Browser GUI (Streamlit)

The terminal CLI is the primary interface, but there's also an optional
Streamlit front-end that mirrors **all** of the CLI's modes in your browser. It
imports the same `dbx_llm` library, so nothing about the CLI changes.

The GUI **ships inside the package**, so once `dbx-llm[ui]` is installed you can
launch it from **any** repo or directory — no need to be in this checkout:

```bash
# one-time: install the optional UI dependency
python -m pip install "dbx-llm[ui]"        # or, in this repo: -e ".[ui]"

# launch from anywhere (opens a browser tab)
python -m dbx_llm --gui
```

The agent modes' **repo path** box defaults to the current working directory, so
run `python -m dbx_llm --gui` from the repo you want to explore. If the `[ui]`
extra isn't installed, the command prints a short install hint instead of
crashing.

Pick a **Mode** in the sidebar — each one is the GUI equivalent of a CLI flag:

| Mode | CLI equivalent | What it does |
| --- | --- | --- |
| 💬 **Chat** | `python -m dbx_llm` | Plain chat with a selectable system prompt (`default`, `coder`, …). Each prompt shows a one-line description. |
| 📖 **Repo Q&A (read-only)** | `python -m dbx_llm --repo` | Codebase-expert agent that explores a repo with read-only tools before answering. |
| ✏️ **Repo Write (edit with approval)** | `python -m dbx_llm --repo --write` | Same agent, allowed to edit files. Every change is shown as a **diff** and applied only after you click **✅ Approve** (or **❌ Reject**) — the browser equivalent of the terminal's `y/N` confirm. A checkbox enables `--allow-self-edit`. |
| 🧠 **Scan / set memory** | `python -m dbx_llm --repo --scan` | One-shot survey that records durable facts to `AGENTS.md`, then shows the summary and the current memory file. |

Shared sidebar controls: a **model dropdown**, a **repo path** box (for the repo
modes), and a clear-chat button. The diff-and-approve flow means editing is just
as safe in the browser as it is in the terminal.

---

## Library usage (import it and build things)

```python
from dbx_llm import chat, list_models, load_prompt

print(list_models())  # available Databricks serving endpoints

reply = chat(
    "databricks-claude-opus-4-6",
    [
        {"role": "system", "content": load_prompt("default")},
        {"role": "user", "content": "Explain a B-tree in one sentence."},
    ],
)
print(reply)
```

`chat()` accepts any extra OpenAI parameters (e.g. `temperature=0.2`) via
keyword arguments.

---

## Optional: tool / function calling

Plain chat needs **no tools**. If you want the model to call your own Python
functions, use `dbx_llm.tools.run_with_tools` — the core stays tool-free, so you
only pull this in when you need it.

```python
from dbx_llm.tools import run_with_tools

def get_weather(city: str) -> dict:
    return {"city": city, "temp_c": 21}

schemas = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]

answer = run_with_tools(
    "databricks-claude-opus-4-6",
    [{"role": "user", "content": "What's the weather in Berlin?"}],
    functions={"get_weather": get_weather},
    tool_schemas=schemas,
)
print(answer)
```

This is also where you could later plug in an MCP server or any other tool
source — it stays entirely optional and separate from the core.

---

## Configuration reference

| Variable | Purpose |
|---|---|
| `DATABRICKS_CONFIG_PROFILE` | Which `~/.databrickscfg` profile to use (default: `DEFAULT`). |
| `DATABRICKS_HOST` / `DATABRICKS_TOKEN` | Direct auth, overrides the profile. |
| `DBX_LLM_PROMPT_DIR` | Local prompt directory checked before the bundled prompts (default: `./prompts`). |

`.env` is **gitignored** — your credentials never get committed.

---

## Troubleshooting

- **`python -m dbx_llm --list-models` prints nothing / errors** → you're not
  authenticated. Run `databricks auth login` and confirm `databricks current-user me` works.
- **`Prompt '<name>' not found`** → no `<name>.md` exists in a local `prompts/`
  folder, `DBX_LLM_PROMPT_DIR`, or the bundled prompts. Check the spelling or add
  the file.
- **Auth picked the wrong workspace** → check `DATABRICKS_CONFIG_PROFILE` in
  `.env` and the matching entry in `~/.databrickscfg`.


## Databricks connection

Everything in dbx-llm talks to **one** thing: your Databricks workspace, over
HTTPS. The Databricks SDK (a local Python library) resolves your auth and points
the OpenAI client at the workspace. So all you need to set up is (1) the CLI and
(2) a working login.

### 1. Install the Databricks CLI

Full instructions: [Databricks CLI installation](https://docs.databricks.com/aws/en/dev-tools/cli/install).
Use **either** a package manager **or** a manual download.

**Option A — package manager (quickest where allowed):**

```bash
# Windows (winget)
winget install Databricks.DatabricksCLI

# macOS / Linux (Homebrew)
brew tap databricks/tap
brew install databricks

# macOS / Linux (curl, no Homebrew)
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

**Option B — manual download (no admin / locked-down Windows):**

1. Download the release ZIP for your OS/arch from the
   [Databricks CLI releases page](https://github.com/databricks/cli/releases)
   (e.g. `databricks_cli_1.1.0_windows_amd64.zip`).
2. Extract it to a folder, e.g.
   `C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\databricks_cli_1.1.0_windows_amd64`.
3. Add that folder to your **user PATH** so `databricks` works from any terminal.

**Why the PATH step matters.** The Databricks Python SDK (used at runtime) shells
out to `databricks.exe` to refresh your OAuth token automatically. It finds the
exe via PATH — it doesn't know where you extracted the ZIP. Without this step,
auth fails with `"cannot configure default credentials"`.

**Add it to PATH (PowerShell):**

```powershell
$cliPath     = "C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\databricks_cli_1.1.0_windows_amd64"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$cliPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$cliPath", "User")
}
```

What each line does:
- Line 1: the folder where `databricks.exe` lives (change to your extract path).
- Line 2: reads your current **user** PATH (no admin rights needed).
- Line 3: the `if` guard skips appending if the folder is already on PATH, so
  re-running this is safe (no duplicate entries).
- Line 4: appends the CLI folder and saves it permanently.

> **Restart required.** Close and reopen VS Code (or any terminal) so the new
> PATH takes effect — terminals inherit PATH from when their parent app started,
> so existing ones won't see the change.

Verify it's on your PATH (either option, in a **fresh** terminal):

```bash
databricks --version
```

> The CLI is a separate tool from the `databricks-sdk` Python package. dbx-llm
> uses the SDK at runtime, but you use the CLI **once** to create the login
> profile the SDK then reads.

### 2. Set up local authentication

To reach Databricks from your machine you need to authenticate. Choose one:

**Option 1: OAuth via the Databricks CLI (recommended)**

See the [CLI OAuth (U2M) docs](https://docs.databricks.com/aws/en/dev-tools/cli/authentication#oauth-user-to-machine-u2m-authentication).

```bash
databricks auth login --host https://<your-workspace-host>
```

This opens a browser SSO flow and writes an OAuth profile to `~/.databrickscfg`.
Point dbx-llm at that profile in your `.env`:

```bash
DATABRICKS_CONFIG_PROFILE="DEFAULT"   # change to the profile name you chose
```

**Option 2: Personal Access Token (PAT)**

> ⚠️ **PATs are often disabled by org policy (they are at Deutsche Börse).** Use
> Option 1 unless you know PATs are allowed in your workspace.

See the [PAT documentation](https://docs.databricks.com/aws/en/dev-tools/auth/pat#databricks-personal-access-tokens-for-workspace-users).

```bash
# Add these to your .env file (overrides the profile)
DATABRICKS_HOST="https://host.databricks.com"
DATABRICKS_TOKEN="dapi_token"
```

More detail: [Databricks SDK authentication docs](https://docs.databricks.com/aws/en/dev-tools/sdk-python#authenticate-the-databricks-sdk-for-python-with-your-databricks-account-or-workspace).

### 3. Verify the connection

Confirm auth works before running dbx-llm:

```bash
databricks current-user me      # should print your identity
python -m dbx_llm --list-models # should list your serving endpoints
```

If `current-user me` fails, the problem is network/auth (VPN, IP allowlist, or
Conditional Access), not dbx-llm.
