## Auto memory

When you first have a memory to save and your memory directory is not `.memory/` under the project root (the main worktree for Git repositories), ask the user once whether to switch this project to it and, if the current one holds memories, whether to move them along. On yes: create `.memory/`, merge `autoMemoryDirectory` with its absolute path into `.claude/settings.local.json`, move the memories if agreed (merging `MEMORY.md` if both exist), and use `.memory/` for the rest of this session, since the setting applies from the next launch. If the user declines, save that as a `project` memory so you do not ask again.

## Python

Always use `uv` to execute Python code and manage environments or dependencies.
Never invoke directly: `python`, `python3`, `pip`, `pip3`, `pip-tools`, `poetry`, `conda`, `virtualenv`, or `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, with dependencies) — declare inline dependencies (PEP 723), manually or with `uv add PKG --script x.py`, then `uv run x.py`
- **One-off code** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' CODE PY`  (never `python -c`)

See the `uv-python` skill for details.

## CLI tools

`hf` and `gh` are installed and authenticated. Use them within the scope of the current task’s authorization.
