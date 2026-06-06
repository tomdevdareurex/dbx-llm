# Handover — `dbx-llm`

A portable Python library + CLI to chat with **Databricks-hosted models**.
This document summarizes why it exists, how it was built, how it works, and the
relevant context from the original `risk.rmnp.cpme-mcp` repo it was extracted from.

---

## 1. Why this repo exists

The user wanted a **portable, installable library** to prompt Databricks-hosted
models — effectively a lightweight, model-selectable chat client they fully
control (a "substitute for GitHub Copilot" in spirit), where:

- They can pick **which Databricks model** to use.
- They can edit a **prompt file** to change behavior.
- It is **independent** — not tied to cPME, not tied to MCP.
- It is **importable** as a library to build new things on top of.

The key realization that made this simple: **Databricks model serving endpoints
are OpenAI-compatible**, and the Databricks SDK hands you a pre-authenticated
OpenAI client in one line. Everything in this repo is built on that.

---

## 2. The core idea (one line)

```python
from databricks.sdk import WorkspaceClient
client = WorkspaceClient().serving_endpoints.get_open_ai_client()
```

- `WorkspaceClient()` resolves auth automatically: env vars → `~/.databrickscfg`
  profile → OAuth (`databricks auth login`). **No tokens in code.**
- `.serving_endpoints.get_open_ai_client()` returns a standard OpenAI client
  already pointed at the workspace. From there it's normal
  `client.chat.completions.create(model=..., messages=...)`.
- The model name is just a **serving endpoint name** (e.g.
  `databricks-claude-opus-4-6`).

This is the same auth mechanism the original `cpme-agent` already uses, so on a
machine where that project works, this library needs **no extra setup**.

---

## 3. What was created

Location: `C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\dbx-llm\`

```
dbx-llm/
├── pyproject.toml        # installable; defines the `dbx-llm` command (hatchling)
├── README.md             # full workflow: auth, install, CLI, library, tools
├── handover.md           # this file
├── .gitignore            # ignores .env, caches, build artifacts, venv
├── .env.example          # auth template (copy to .env)
├── .env                  # local auth config (GITIGNORED) — DATABRICKS_CONFIG_PROFILE=DEFAULT
├── prompts/              # editable system prompts (plain markdown)
│   ├── default.md
│   └── coder.md
└── dbx_llm/
    ├── __init__.py       # public API: chat, get_client, list_models, load_prompt, list_prompts
    ├── __main__.py       # enables `python -m dbx_llm`
    ├── client.py         # CORE: auth + OpenAI client + list_models() + chat()
    ├── prompts.py        # load_prompt() / list_prompts()
    ├── cli.py            # interactive REPL (the `dbx-llm` command)
    └── tools.py          # OPTIONAL function/tool calling (core does NOT import it)
```

### Design decisions
- **Name:** dist `dbx-llm`, import package `dbx_llm`, console command `dbx-llm`.
  (Chosen over `databricks-copilot` to avoid GitHub Copilot naming collision.)
- **Tool-agnostic core:** plain chat needs no tools. Tool/function-calling lives
  in `dbx_llm/tools.py` and is opt-in only — the core stays dependency-light.
  **No MCP, no cPME, no MLflow** in this repo.
- **Prompts as files:** system prompts are plain `.md` files in `prompts/`.
  Edit a file → behavior changes. Add a file → select it with `--prompt <name>`.
  Override location with `DBX_LLM_PROMPT_DIR`.
- **`.env` is created AND gitignored** (per the user's explicit request).

---

## 4. How to use it

### Prerequisites
1. Python 3.10+.
2. Databricks CLI **installed and authenticated** (`databricks auth login` →
   creates an OAuth `DEFAULT` profile in `~/.databrickscfg`). Installing the CLI
   alone is NOT enough — an authenticated profile is required.
3. Model-serving access in the workspace.

> If `cpme-agent` already talks to Databricks on this machine, this repo reuses
> the same `DEFAULT` profile and needs no additional setup.

### Install
```powershell
cd "C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\dbx-llm"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

### CLI
```powershell
# IMPORTANT on this corporate machine: the generated dbx-llm.exe is blocked by
# group policy, so use the module form (identical behavior):
.\.venv\Scripts\python.exe -m dbx_llm --list-models
.\.venv\Scripts\python.exe -m dbx_llm --list-prompts
.\.venv\Scripts\python.exe -m dbx_llm --model databricks-claude-opus-4-6
.\.venv\Scripts\python.exe -m dbx_llm --prompt coder --model databricks-meta-llama-3-3-70b-instruct
```

### Library
```python
from dbx_llm import chat, list_models, load_prompt

print(list_models())
reply = chat(
    "databricks-claude-opus-4-6",
    [
        {"role": "system", "content": load_prompt("default")},
        {"role": "user", "content": "Explain a B-tree in one sentence."},
    ],
)
print(reply)
```

### Optional tool-calling
See `dbx_llm/tools.py::run_with_tools(model, messages, functions, tool_schemas)`.
This is where an MCP server or any other tool source could later be plugged in —
entirely optional and separate from the core.

---

## 5. Verification performed

- `pip install -e .` succeeded (exit code 0) into `.venv`.
- Imports clean: `from dbx_llm import chat, list_models, load_prompt, list_prompts`
  plus `dbx_llm.tools` — reports version `0.1.0`.
- `python -m dbx_llm --list-prompts` → prints `coder`, `default`.
- `list_prompts()` discovers both prompt files.
- NOT yet run live: `--list-models` (hits Databricks). Run it to confirm the
  end-to-end connection when desired.

### Known machine-specific gotcha
- **`dbx-llm.exe` is blocked by corporate group policy.** pip auto-generates this
  launcher shim for the `[project.scripts]` entry; the corporate allow-list
  rejects unapproved `.exe`s. Workaround (already documented + supported via
  `__main__.py`): run `python -m dbx_llm ...` instead. Identical code path.
- The repo lives under **OneDrive**; git + OneDrive both syncing `.git` can
  occasionally conflict. Not a blocker, just be aware. (Git is NOT yet
  initialized in this repo — it's currently a plain folder.)

---

## 6. Context from the original repo: `risk.rmnp.cpme-mcp`

This library was extracted/generalized from patterns in that repo. Relevant facts
in case they matter later:

### Repo structure (two deployables + scripts)
- `mcp-server/` — a FastMCP + FastAPI + uvicorn server that wraps the **cPME**
  OpenAPI spec (auto-fetched from SwaggerHub at startup). Exposes ~24 tools over
  an MCP `/mcp` endpoint. Runs on port **9001** locally.
- `cpme-agent/` — an agent stack:
  - `agent_server/` — the "AI brain" (OpenAI Agents SDK + `databricks_openai` +
    MLflow) that uses a Databricks-hosted model and connects to the MCP server.
    Runs on port **8000**.
  - `chat-ui/` — a TypeScript/React + Node frontend (monorepo with packages).
- Root PowerShell scripts: `create_apps.ps1`, `destroy_apps.ps1`,
  `redeploy_apps.ps1`, `get_environment.ps1`. Guide: `LOCAL_SETUP_GUIDE.md`.

### The two ways the original repo can run
- **Option A — VS Code Copilot direct:** VS Code Copilot Chat → MCP Server → cPME.
  Copilot itself is the AI brain (uses Copilot tokens). No Databricks needed.
  Configured via VS Code `mcp.json` pointing at `http://0.0.0.0:9001/mcp`.
- **Option B — Full agent stack:** Chat UI → Agent Server (Databricks Claude
  Opus brain, no Copilot tokens) → MCP Server → cPME.

### Key technical details carried over / worth knowing
- **Auth:** Databricks OAuth via CLI (`auth_type=databricks-cli`); PATs are
  disabled by org policy. `~/.databrickscfg` profile `DEFAULT`. This is the exact
  auth `dbx-llm` reuses.
- **Databricks model used by the agent:** `databricks-claude-opus-4-6`.
- **The wiring trick in `cpme-agent/agent_server/agent.py`:**
  `set_default_openai_client(AsyncDatabricksOpenAI())` +
  `set_default_openai_api("chat_completions")` routes the OpenAI Agents SDK to
  Databricks models. `dbx-llm` achieves the same Databricks routing more simply
  via `WorkspaceClient().serving_endpoints.get_open_ai_client()`.
- **SSL/corporate proxy:** the MCP server uses `verify=False` in its httpx calls
  (spec fetch + cPME base URL) to get through the corporate proxy. If `dbx-llm`
  ever hits SSL issues against Databricks, that's the analogous area to look at.
- **cPME API:** `https://cpme.eurex.com/api/v2.0` — Eurex Clearing Prisma Margin
  Estimator. It does **margin calculation only — NO live market prices.** (A bond
  price question earlier had to be answered from an external source, not cPME.)
- **MCP custom tools** (`mcp-server/server/tools.py`): health, get_current_user
  (Databricks-specific), get_products, get_series, contract dates, indicative
  margins, etc. `filtered_List_Series_of_a_Product` is commented out (a
  `List[Tuple]` JSON-Schema validation error).
- **Known design weakness in the MCP server:** the OpenAPI spec is fetched over
  the network at import time, so the server won't boot if SwaggerHub is
  unreachable.
- **Products seen in cPME** (futures): FGBL, FGBM, FGBS, FGBX, FGBC, CONF.

### Relationship between the two repos
- `dbx-llm` is **standalone** — it does NOT depend on `cpme-mcp` and contains no
  cPME code. It only shares the **Databricks auth + OpenAI-compatible client**
  pattern.
- If you ever want `dbx-llm` to call the cPME tools, the integration point is
  `dbx_llm/tools.py`: point an MCP/tool adapter at the cPME MCP server
  (`http://localhost:9001/mcp`) and pass the resulting tool schemas into
  `run_with_tools`. This stays optional and does not affect the core.

---

## 7. Suggested next steps (none done yet)

1. Run `python -m dbx_llm --list-models` to confirm the live Databricks
   connection and see selectable endpoints.
2. Optionally `git init` + first commit (repo is currently an untracked folder;
   `.gitignore` is already in place). Mind the OneDrive/git caveat above.
3. Optionally add a tool example wiring `tools.py` to the cPME MCP server.
4. Optionally add tests (a `dev` extra with `pytest` is already declared in
   `pyproject.toml`).
