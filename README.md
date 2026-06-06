# dbx-llm

A small, **portable** Python library + CLI to chat with **Databricks-hosted models**.

No cPME, no MCP, no MLflow — just import it (or run the CLI) and build your own
things on top of any model served in your Databricks workspace. Think of it as a
lightweight, model-selectable chat client you fully control.

---

## How it works (the whole idea in one line)

Databricks model serving endpoints are **OpenAI-compatible**. The Databricks SDK
hands you a ready-to-use OpenAI client that is already pointed at your workspace
and already authenticated:

```python
from databricks.sdk import WorkspaceClient
client = WorkspaceClient().serving_endpoints.get_open_ai_client()
```

Everything in this library is built on that single primitive. Your auth comes
from the Databricks CLI / `~/.databrickscfg` — **no tokens in code**.

---

## Project layout

```
dbx-llm/
├── pyproject.toml        # package metadata + the `dbx-llm` command
├── README.md
├── .gitignore            # ignores .env, caches, build artifacts
├── .env.example          # template you copy to .env
├── .env                  # your local auth config (gitignored)
├── prompts/              # editable system prompts (plain markdown)
│   ├── default.md
│   └── coder.md
└── dbx_llm/
    ├── __init__.py       # public API: chat, list_models, load_prompt, ...
    ├── client.py         # auth + OpenAI client + list_models + chat   (core)
    ├── prompts.py        # load_prompt / list_prompts
    ├── cli.py            # interactive REPL (the `dbx-llm` command)
    └── tools.py          # OPTIONAL function/tool calling (not used by core)
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

pip install -e .
```

Copy the env template (it's already filled with the default profile):

```bash
cp .env.example .env   # already present in this repo
```

---

## CLI usage (the "chat client" workflow)

```bash
# See which models you can pick (your workspace serving endpoints)
dbx-llm --list-models

# See available prompt files
dbx-llm --list-prompts

# Start chatting with a specific model + the default prompt
dbx-llm --model databricks-claude-opus-4-6

# Use a different prompt file (prompts/coder.md) and another model
dbx-llm --prompt coder --model databricks-meta-llama-3-3-70b-instruct
```

> **Locked-down / corporate machines:** if running the `dbx-llm` command is
> blocked by group policy (it's an auto-generated `.exe`), use the module form
> instead — it does exactly the same thing:
>
> ```bash
> python -m dbx_llm --list-models
> python -m dbx_llm --model databricks-claude-opus-4-6
> ```

Inside the REPL, type a message and press Enter. Conversation history is kept
for the session. Press `Ctrl-C` to exit.

**Change behavior by editing prompts** — open `prompts/default.md`, change the
text, save, and the next run uses your new system prompt. Add new `*.md` files to
`prompts/` and select them with `--prompt <name>`.

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
| `DBX_LLM_PROMPT_DIR` | Custom directory for prompt files (default: `./prompts`). |

`.env` is **gitignored** — your credentials never get committed.

---

## Troubleshooting

- **`dbx-llm --list-models` prints nothing / errors** → you're not authenticated.
  Run `databricks auth login` and confirm `databricks current-user me` works.
- **`Prompt '<name>' not found`** → the file `prompts/<name>.md` doesn't exist,
  or you're running from a different directory (set `DBX_LLM_PROMPT_DIR`).
- **Auth picked the wrong workspace** → check `DATABRICKS_CONFIG_PROFILE` in
  `.env` and the matching entry in `~/.databrickscfg`.
