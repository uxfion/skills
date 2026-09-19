## Auto memory

When you first have a memory to save and your memory directory is not `.memory/` under the project root, ask the user once whether to switch this project to it and, if the current one holds memories, whether to move them along. On yes: create `.memory/`, merge `autoMemoryDirectory` with its absolute path into `.claude/settings.local.json`, move the memories if agreed (merging `MEMORY.md` if both exist), and use `.memory/` for the rest of this session, since the setting applies from the next launch. If the user declines, save that as a `project` memory so you do not ask again.


## When executing Python code or managing Python environments or dependencies, always use `uv`.
Never invoke directly: `python` `python3` `pip` `pip3` `pip-tools` `poetry` `conda` `virtualenv` `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, has deps) — deps inline (PEP 723) via `uv add PKG --script x.py`, then `uv run x.py`
- **One-off** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' … PY`  (never `python -c`)

Details → uv-python skill.

---
`hf` and `gh` cli are installed and authenticated. Use them within the scope of the current task’s authorization.

