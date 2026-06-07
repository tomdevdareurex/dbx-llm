# AGENTS.md

Living memory for this repository.

## Notes

- (2026-06-07) The recommended way to run the CLI is `python -m dbx_llm ...` (not the `dbx-llm` script entry point) because the auto-generated `.exe` launcher is blocked by corporate group policy on locked-down Windows machines. Both invoke the same `cli:main` function.
- (2026-06-07) Architecture: The package has a deliberate layered design — client.py (core auth+chat) has zero dependency on tools.py; tools.py is imported lazily only when --repo mode or tool-calling is needed. This keeps plain chat dependency-light.
- (2026-06-07) Auth mechanism: WorkspaceClient() resolves auth automatically via env vars (DATABRICKS_HOST/TOKEN) → ~/.databrickscfg profile (DATABRICKS_CONFIG_PROFILE, default "DEFAULT") → OAuth. PATs are disabled by org policy; OAuth via `databricks auth login` is the expected method.
- (2026-06-07) The OpenAI client is obtained via WorkspaceClient().serving_endpoints.get_open_ai_client() — a single call that returns a standard OpenAI client pre-wired with workspace URL and auth. Model names are just serving endpoint names (e.g. "databricks-claude-opus-4-6").
- (2026-06-07) Prompts are loaded from a `prompts/` directory relative to CWD by default; override with DBX_LLM_PROMPT_DIR env var. Each prompt is a plain .md file selected by stem name via --prompt flag.
- (2026-06-07) CLI has three modes: (1) plain chat REPL (default), (2) --repo agent REPL (tool-calling codebase expert, read-only or --write), (3) --scan (one-shot deep survey that populates AGENTS.md then exits, max 40 tool turns).
- (2026-06-07) The repo agent's tool-calling loop (tools.py:run_with_tools) defaults to max_turns=12 for interactive use, but --scan passes max_turns=40 for deeper exploration.
- (2026-06-07) Security sandbox in repo_tools.py: all paths resolved against root (no escape), .env/.pem/.key/id_rsa/.pfx files are blocked from reading, .git/ is blocked from writing, and dbx-llm's own source directory is write-protected unless --allow-self-edit is passed.
- (2026-06-07) File attachment syntax in the REPL: prefix a path with @ (e.g. "@README.md") in your message and its contents are inlined before sending to the model.
- (2026-06-07) Build system is hatchling (pyproject.toml). Dependencies: databricks-sdk>=0.30, openai>=1.40, python-dotenv>=1.0. Dev extra adds pytest>=8.0. Requires Python >=3.10.
- (2026-06-07) The chat() function in client.py has dual return types: returns a plain string (message.content) for simple chat, but returns the full OpenAI message object when tools= is provided, so callers can inspect tool_calls.
- (2026-06-07) WorkspaceClient and OpenAI client are both cached with @lru_cache(maxsize=1) in client.py — they are singletons for the process lifetime.
- (2026-06-07) The --write mode shows a unified diff to the user and requires interactive y/N confirmation before any file modification is applied. The confirm callback is injectable for testing.
- (2026-06-07) Skipped directories during repo traversal (_SKIP_DIRS): .git, .venv, venv, env, __pycache__, node_modules, dist, build, .pytest_cache, .ruff_cache, .mypy_cache, .idea, .vscode.
- (2026-06-07) Context-window protection limits in repo_tools.py: _MAX_FILE_BYTES=100,000, _MAX_SEARCH_HITS=100, _MAX_LIST_ENTRIES=2,000.
- (2026-06-07) Origin: this repo was extracted from the `risk.rmnp.cpme-mcp` project (Eurex cPME margin estimator agent). It shares the same Databricks auth pattern but has no dependency on cPME, MCP, or MLflow. Integration point for future MCP/tool sources is tools.py:run_with_tools.
- (2026-06-07) The repo lives under OneDrive on the developer's machine; git + OneDrive syncing .git can occasionally conflict. The .gitignore is already in place.
